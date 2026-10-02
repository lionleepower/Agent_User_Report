"""Observe existing llama.cpp only: no model download, no cloud calls.

python local.py --raw <independent public run directory> --summary <repo summary>
Restart per repetition; 8 configs x 5 repeats. GPU memory is NOT KV usage.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import threading
import time
import urllib.request

DNS = socket.getaddrinfo
socket.getaddrinfo = lambda host, port, family=0, type=0, proto=0, flags=0: DNS(host, port, socket.AF_INET, type, proto, flags)


def post(base, route, body):
    request = urllib.request.Request(base + route, json.dumps(body, ensure_ascii=False).encode(), {'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def gpu():
    try:
        return int(subprocess.check_output(['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'], text=True, creationflags=subprocess.CREATE_NO_WINDOW).strip().splitlines()[0])
    except Exception:
        return None


def snapshot(base):
    try:
        with urllib.request.urlopen(base + '/metrics', timeout=5) as response:
            return response.read().decode()
    except Exception:
        return None


def complete(base, prompt, cache):
    start = time.perf_counter()
    request = urllib.request.Request(base + '/completion', json.dumps({'prompt': prompt, 'n_predict': 64, 'temperature': 0.2, 'seed': 7, 'stream': True, 'cache_prompt': cache, 'id_slot': 0}).encode(), {'Content-Type': 'application/json'})
    answer, first, last = '', None, {}
    with urllib.request.urlopen(request, timeout=120) as response:
        for line in response:
            if not line.startswith(b'data:'):
                continue
            payload = line[5:].strip()
            if payload == b'[DONE]':
                continue
            event = json.loads(payload)
            if event.get('content'):
                if first is None:
                    first = (time.perf_counter() - start) * 1000
                answer += event['content']
            if event.get('stop'):
                last = event
    if not last:
        raise RuntimeError('truncated completion')
    return {'answer': answer, 'firstAnswerMs': first, 'totalMs': (time.perf_counter() - start) * 1000, 'timings': last.get('timings'), 'tokensCached': last.get('tokens_cached'), 'tokensEvaluated': last.get('tokens_evaluated'), 'tokensPredicted': last.get('tokens_predicted'), 'truncated': last.get('truncated'), 'stoppedLimit': last.get('stopped_limit')}


def allocation(log):
    # Runtime log reports allocated K/V storage, never occupied GPU memory.
    match = re.search(r'size\s*=\s*([\d.]+)\s*MiB[^\n]*\bK\s*\(([^)]+)\)', log)
    if not match:
        match = re.search(r'KV[^\n]*?(?:size\s*=|buffer size\s*=)\s*([\d.]+)\s*MiB', log)
    return float(match[1]) if match else None


def metric(text, name):
    if not text:
        return None
    match = re.search(r'^' + re.escape(name) + r'\s+([\d.eE+-]+)$', text, re.M)
    return float(match[1]) if match else None


def main(args):
    if not os.environ.get('BENCH_BUDGET_CNY'):
        raise RuntimeError('explicit BENCH_BUDGET_CNY required even for free local experiment')
    inputdir = Path(args.raw)
    source = json.loads((inputdir / 'public-input.json').read_text(encoding='utf8'))
    runid = time.strftime('kv-local-%Y%m%dT%H%M%SZ', time.gmtime())
    raw = inputdir / runid
    raw.mkdir(exist_ok=False)
    bench = Path(os.environ['LOCALAPPDATA']) / 'llm-bench'
    exe = bench / 'llama.cpp/bin/llama-server.exe'
    model = bench / 'llm-models/Qwen3-4B-Instruct-2507-Q4_K_M.gguf'
    if not exe.is_file() or not model.is_file():
        raise RuntimeError('existing local runtime/model missing; do not download')
    digest = hashlib.sha256()
    with model.open('rb') as file:
        for block in iter(lambda: file.read(8 * 1024 * 1024), b''):
            digest.update(block)
    out = {'schemaVersion': 1, 'runId': runid, 'date': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'status': 'running', 'model': model.name, 'modelSha256': digest.hexdigest(), 'runtime': subprocess.check_output([str(exe), '--version'], stderr=subprocess.STDOUT, text=True).strip(), 'corpusCommit': source['commit'], 'plannedConfigs': 8, 'repetitions': args.repeats, 'outputLimit': 64, 'metricsMeaning': 'GPU memory = device total; allocation = runtime log; occupied KV bytes unavailable unless explicit metric', 'cloudCostCny': 0, 'rows': []}
    summary = Path(args.summary)
    summary.parent.mkdir(parents=True, exist_ok=True)
    base = 'http://127.0.0.1:18092'
    try:
        urllib.request.urlopen(base + '/health', timeout=1)
    except Exception:
        pass
    else:
        raise RuntimeError('reserved port already in use; do not stop unrelated service')
    for dtype in ['f16', 'q8_0']:
        for ctx in [8192, 16384]:
            for slots in [1, 2]:
                for repeat in range(args.repeats):
                    name = f'{dtype}-{ctx}-{slots}-{repeat}'
                    logpath = raw / (name + '.log')
                    baseline = gpu()
                    samples, finished = [], threading.Event()

                    def sample():
                        while not finished.is_set():
                            samples.append({'elapsedMs': round((time.perf_counter() - started) * 1000), 'gpuTotalUsedMiB': gpu()})
                            finished.wait(0.5)

                    command = [str(exe), '-m', str(model), '-ngl', '99', '-c', str(ctx), '-fa', 'on', '-ctk', dtype, '-ctv', dtype, '--jinja', '--port', '18092', '--host', '127.0.0.1', '--parallel', str(slots), '--metrics', '--slots', '--no-webui', '--no-context-shift', '-lv', '5', '--log-colors', 'off']
                    started = time.perf_counter()
                    rowbase = {'kvType': dtype, 'contextTotal': ctx, 'slots': slots, 'repeat': repeat, 'gpuBaselineMiB': baseline, 'commandFlags': command[3:]}
                    with logpath.open('w', encoding='utf8') as log:
                        child = subprocess.Popen(command, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
                        sampler = threading.Thread(target=sample, daemon=True)
                        sampler.start()
                        try:
                            for _ in range(240):
                                if child.poll() is not None:
                                    raise RuntimeError('runtime exited before ready')
                                try:
                                    with urllib.request.urlopen(base + '/health', timeout=1) as r:
                                        if r.status == 200:
                                            break
                                except Exception:
                                    time.sleep(0.25)
                            else:
                                raise RuntimeError('startup timeout')
                            loadms = (time.perf_counter() - started) * 1000
                            props = json.load(urllib.request.urlopen(base + '/slots', timeout=5))
                            capacity = props[0].get('n_ctx') if props else None
                            if capacity is None:
                                # Explicit log field checked after run; never assume ctx/slots.
                                capacity = None
                            for shape in ['retrieval', 'whole']:
                                messages = source[shape]
                                prompt = post(base, '/apply-template', {'messages': messages, 'add_generation_prompt': True})['prompt']
                                tokens = len(post(base, '/tokenize', {'content': prompt, 'add_special': True})['tokens'])
                                effective = capacity
                                if effective is None:
                                    log.flush()
                                    found = re.search(r'n_ctx_slot\s*=\s*(\d+)', logpath.read_text(encoding='utf8', errors='replace'))
                                    effective = int(found[1]) if found else None
                                if effective is None or tokens + 64 > effective:
                                    out['rows'].append({**rowbase, 'shape': shape, 'status': 'skipped_capacity', 'promptTokens': tokens, 'contextPerSlot': effective, 'loadMs': loadms})
                                    continue
                                for state in ['first_in_shape', 'shared_prefix', 'cache_disabled']:
                                    current = prompt
                                    if state != 'first_in_shape':
                                        followup = [dict(m) for m in messages]
                                        followup[-1]['content'] += ' 请简短回答。'
                                        current = post(base, '/apply-template', {'messages': followup, 'add_generation_prompt': True})['prompt']
                                    before = snapshot(base)
                                    currenttokens = len(post(base, '/tokenize', {'content': current, 'add_special': True})['tokens'])
                                    if currenttokens + 64 > effective:
                                        raise RuntimeError('follow-up exceeds observed slot capacity')
                                    result = complete(base, current, state == 'shared_prefix')
                                    after = snapshot(base)
                                    trace = {'result': result, 'metricsBefore': before, 'metricsAfter': after, 'slots': props}
                                    (raw / f'{name}-{shape}-{state}.json').write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding='utf8')
                                    cached_before = metric(before, 'llamacpp:prompt_tokens_cached_total')
                                    cached_after = metric(after, 'llamacpp:prompt_tokens_cached_total')
                                    out['rows'].append({**rowbase, 'shape': shape, 'state': state, 'status': 'ok', 'contextPerSlot': effective, 'promptTokens': currenttokens, 'loadMs': loadms, **{k: v for k, v in result.items() if k != 'answer'}, 'cachedPromptTokens': result.get('timings', {}).get('cache_n'), 'cachedMetricDelta': cached_after - cached_before if cached_after is not None and cached_before is not None else None, 'kvOccupiedBytes': None, 'kvOccupiedReason': 'runtime exposes cached prompt token counters, not occupied KV bytes', 'rawTrace': f'{runid}/{name}-{shape}-{state}.json'})
                        except Exception as error:
                            out['rows'].append({**rowbase, 'status': 'failed', 'reason': type(error).__name__ + ': ' + str(error)[:100]})
                        finally:
                            child.terminate()
                            try:
                                child.wait(timeout=10)
                            except subprocess.TimeoutExpired:
                                child.kill(); child.wait()
                            finished.set(); sampler.join(timeout=5)
                    logtext = logpath.read_text(encoding='utf8', errors='replace')
                    alloc = allocation(logtext)
                    occupied = [s['gpuTotalUsedMiB'] for s in samples if s['gpuTotalUsedMiB'] is not None]
                    peak = max(occupied) if occupied else None
                    for row in out['rows']:
                        if row.get('kvType') == dtype and row.get('contextTotal') == ctx and row.get('slots') == slots and row.get('repeat') == repeat:
                            row.update({'kvAllocatedMiB': alloc, 'gpuPeakTotalMiB': peak, 'gpuPeakDeltaMiB': peak - baseline if peak is not None and baseline is not None else None})
                    (raw / (name + '-gpu.json')).write_text(json.dumps(samples), encoding='utf8')
                    summary.write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n', encoding='utf8', newline='\n')
                    print(json.dumps({'config': name, 'rows': len(out['rows']), 'kvAllocatedMiB': alloc, 'gpuPeakMiB': peak}), flush=True)
    out['status'] = 'complete_with_failures' if any(r['status'] == 'failed' for r in out['rows']) else 'complete'
    summary.write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n', encoding='utf8', newline='\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--raw', required=True)
    parser.add_argument('--summary', required=True)
    parser.add_argument('--repeats', type=int, default=5)
    main(parser.parse_args())
