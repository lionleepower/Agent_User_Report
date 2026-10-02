"""Official PageIndex local SDK, behind the shared gateway; no direct egress.

index / controlled / native modes. Raw SDK responses remain in the run folder.
"""
import argparse
import json
import os
from pathlib import Path
import re
import socket
import sys
import time
import urllib.request

DNS = socket.getaddrinfo


def local_dns(host, port, family=0, type=0, proto=0, flags=0):
    if host not in ('127.0.0.1', 'localhost'):
        raise RuntimeError('SDK direct egress blocked; shared gateway required')
    return DNS(host, port, socket.AF_INET, type, proto, flags)


socket.getaddrinfo = local_dns
os.environ.update({'HF_HUB_OFFLINE': '1', 'LITELLM_LOCAL_MODEL_COST_MAP': 'True', 'OPENAI_AGENTS_DISABLE_TRACING': '1', 'DO_NOT_TRACK': '1'})


# tiktoken cache key (sha1 of the official blob URL) -> tiktoken's pinned sha256.
TOKENIZERS = {'9b5ad71b2ce5302211f9c61530b329a4922fc6a4': '223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7'}  # cl100k_base


def offline_tokenizers(raw):
    """LiteLLM 1.97 loads cl100k_base at import but does not bundle it; reuse the
    hash-verified copy already installed in the venv instead of downloading."""
    import hashlib
    import shutil
    import sysconfig
    cache = raw / 'tiktoken-cache'
    cache.mkdir(exist_ok=True)
    source = Path(sysconfig.get_paths()['purelib']) / 'llama_index' / 'core' / '_static' / 'tiktoken_cache'
    for name, digest in TOKENIZERS.items():
        target = cache / name
        if not target.exists():
            shutil.copyfile(source / name, target)
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise RuntimeError('tokenizer cache hash mismatch')
    os.environ['CUSTOM_TIKTOKEN_CACHE_DIR'] = str(cache)


def request(body):
    req = urllib.request.Request(os.environ['BENCH_LLM_BASE'] + '/chat/completions', json.dumps(body, ensure_ascii=False).encode(), {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + os.environ['BENCH_GATE_TOKEN']})
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.load(response)


def scope(name):
    req = urllib.request.Request(os.environ['BENCH_GATEWAY'] + '/_scope', json.dumps({'name': name, 'maxCalls': 6}).encode(), {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + os.environ['BENCH_GATE_TOKEN']})
    with urllib.request.urlopen(req, timeout=5) as response:
        return json.load(response)


def pages_of(obj):
    found = set()
    if isinstance(obj, dict):
        for key, val in obj.items():
            if key in ('page_index', 'pageIndex', 'page', 'page_number') and isinstance(val, int):
                found.add(val)
            else:
                found.update(pages_of(val))
    elif isinstance(obj, list):
        for val in obj:
            found.update(pages_of(val))
    return found


def backend():
    # SDK and LiteLLM retries are disabled; each attempt would reserve budget again.
    return {'api_key': os.environ['BENCH_GATE_TOKEN'], 'base_url': os.environ['BENCH_LLM_BASE'], 'max_retries': 0}


def harden():
    import pageindex.utils as utils
    # The SDK loop retries 10 times unless a status is final; gateway budget
    # stops (402), failure limits (503) and invalid requests must end it.
    utils._UNRECOVERABLE_STATUS = frozenset(utils._UNRECOVERABLE_STATUS | {400, 402, 413, 422, 503})


def page_texts(obj):
    """(page, chars) for every {"page": int, "text": str} item in a tool envelope."""
    if isinstance(obj, dict):
        if isinstance(obj.get('page'), int) and isinstance(obj.get('text'), str):
            return [(obj['page'], len(obj['text']))]
        return [p for v in obj.values() for p in page_texts(v)]
    if isinstance(obj, list):
        return [p for v in obj for p in page_texts(v)]
    return []


def observe_tools():
    """Record every official read tool the native agent runs. Tools look up
    _IMPLEMENTATIONS at call time, so wrapping the entries sees each call."""
    import pageindex.agent_tools as tools
    trace = []
    for name in ('browse_documents', 'get_document', 'get_document_structure', 'get_page_content'):
        original = tools._IMPLEMENTATIONS[name]
        def observed(client, *args, _name=name, _original=original, **kwargs):
            envelope, error = _original(client, *args, **kwargs)
            pages = page_texts(envelope) if _name == 'get_page_content' else []
            trace.append({'tool': _name, 'arguments': {k: v for k, v in kwargs.items() if not k.startswith('_')}, 'error': bool(error), 'pages': [p for p, _ in pages], 'chars': sum(n for _, n in pages)})
            return envelope, error
        tools._IMPLEMENTATIONS[name] = observed
    return trace


def client(raw):
    from pageindex import PageIndexClient
    harden()
    model = os.environ['BENCH_LLM_MODEL']
    # PageIndex 0.2.10 local mode: summary concurrency is the library default.
    return PageIndexClient(model=model, summary_model=model, storage_path=str(raw / 'pageindex-store'), index_backend=backend(), chat_backend=backend())


def controlled(pi, raw, question):
    from pageindex.agent_tools import call_tool
    docid = json.loads((raw / 'pageindex-id.json').read_text())['doc_id']
    source = json.loads((raw / 'public-input.json').read_text(encoding='utf8'))
    mapping = json.loads((raw / 'page-map.json').read_text(encoding='utf8'))
    tools = pi.as_openai_tools(doc_id=docid)
    schema = [{'type': 'function', 'function': {'name': t.name, 'description': t.description, 'parameters': t.params_json_schema}} for t in tools if t.name in ('get_document_structure', 'get_page_content')]
    messages = [{'role': 'system', 'content': '你只检索公开资料，不回答问题。先调用官方 get_document_structure 定位章节，再调用 get_page_content 阅读原文。工具输出 bench_chunks 是原文对应的可选片段。找到证据后仅输出 JSON {"evidence_ids":["实际读到的片段id"]}，最多5项，每篇最多3项。不要猜测不存在的片段。'}, {'role': 'user', 'content': f'文档：public-corpus.pdf\n问题：{question}'}]
    visited, trace = set(), []
    start = time.perf_counter()
    for turn in range(6):
        if time.perf_counter() - start > 120:
            raise RuntimeError('tree search time limit')
        reply = request({'model': os.environ['BENCH_LLM_MODEL'], 'messages': messages, 'tools': schema, 'max_tokens': 512, 'temperature': 0.2, 'stream': False})
        msg = reply['choices'][0]['message']
        trace.append(reply)
        calls = msg.get('tool_calls') or []
        if not calls:
            match = re.search(r'\{[\s\S]*\}', msg.get('content') or '')
            result = json.loads(match[0]) if match else {}
            ids = result.get('evidence_ids')
            if not isinstance(ids, list) or any(not isinstance(i, str) or i not in visited for i in ids):
                raise RuntimeError('tree selection missing or names unread evidence')
            return {'ids': ids, 'retrievalMs': (time.perf_counter() - start) * 1000, 'searchCalls': turn + 1, 'trace': trace}
        messages.append({k: v for k, v in msg.items() if k in ('role', 'content', 'tool_calls')})
        for call in calls:
            name = call['function']['name']
            if name not in ('get_document_structure', 'get_page_content'):
                raise RuntimeError('unapproved tree tool')
            arguments = json.loads(call['function']['arguments'])
            payload, error = call_tool(pi, name, arguments, doc_ids=[docid])
            envelope = json.loads(payload)
            if error:
                raise RuntimeError('official tree tool failed')
            if name == 'get_page_content':
                pages = pages_of(envelope)
                # Official page envelope versions differ; parsed request is also official read scope.
                if not pages:
                    from pageindex.agent_tools import _expand_pages
                    pages = set(_expand_pages(arguments['pages']))
                ids = {m['id'] for m in mapping if set(m['pages']) & pages}
                visited.update(ids)
                envelope['bench_chunks'] = [{'id': c['id'], 'doc': c['docName'], 'text': c['text']} for c in source['chunks'] if c['id'] in ids]
            trace.append({'tool': name, 'arguments': arguments, 'result': envelope})
            messages.append({'role': 'tool', 'tool_call_id': call['id'], 'content': json.dumps(envelope, ensure_ascii=False)})
    raise RuntimeError('tree search call limit')


# The approved, hash-pinned dependency overlay; the base venv stays unchanged.
OVERLAY = Path(os.environ.get('LOCALAPPDATA', '')) / 'llm-bench' / 'experiments' / 'continuation-deps-2026-09-30' / 'site'


def main(args):
    if not OVERLAY.is_dir():
        raise RuntimeError('approved dependency overlay missing')
    sys.path.insert(0, str(OVERLAY))
    raw = Path(os.environ['BENCH_RUN_DIR'])
    offline_tokenizers(raw)
    pi = client(raw)
    if args.mode == 'compat':
        # The SDK's own LiteLLM lane, as indexing uses it, must reach the gateway.
        from pageindex.utils import _llm_backend, llm_completion
        token = _llm_backend.set(backend())
        try:
            start = time.perf_counter()
            text, finish = llm_completion(os.environ['BENCH_LLM_MODEL'], '仅输出 JSON：{"ok":true}', return_finish_reason=True)
            output = {'status': 'complete', 'mode': 'sdk-litellm', 'ok': 'true' in (text or ''), 'finish': finish, 'totalMs': (time.perf_counter() - start) * 1000}
        finally:
            _llm_backend.reset(token)
    elif args.mode == 'index':
        start = time.perf_counter()
        result = pi.submit_document(str(raw / 'public-corpus.pdf'), mode='flash', wait=True)
        (raw / 'pageindex-id.json').write_text(json.dumps(result), encoding='utf8')
        tree = pi.get_tree(result['doc_id'], node_summary=True, include_text=False)
        (raw / 'pageindex-tree.json').write_text(json.dumps(tree, ensure_ascii=False), encoding='utf8')
        output = {'status': 'complete', 'indexMs': (time.perf_counter() - start) * 1000, 'docId': result['doc_id'], 'sdkVersion': '0.2.10', 'mode': 'flash'}
    else:
        question = json.loads(Path(args.input).read_text(encoding='utf8'))
        scope(question['id'])
        try:
            if args.mode == 'controlled':
                output = controlled(pi, raw, question['question'])
            else:
                docid = json.loads((raw / 'pageindex-id.json').read_text())['doc_id']
                trace = observe_tools()
                start = time.perf_counter()
                # SDK streaming merges narration and final answer. Nonstream exposes
                # final_output reliably; final-answer TTFT is therefore unobservable.
                result = pi.chat_completions(messages=[{'role': 'system', 'content': question['rules']}, {'role': 'user', 'content': question['question']}], doc_id=docid, stream=False, max_turns=6, max_tokens=400, temperature=0.2)
                text = result['choices'][0]['message']['content']
                if not text:
                    raise RuntimeError('native SDK returned no final answer')
                reads = [t for t in trace if t['tool'] == 'get_page_content' and not t['error']]
                evidence_chars = sum(t['chars'] for t in reads) if reads else None
                output = {'text': text, 'firstAnswerMs': None, 'firstAnswerReason': 'SDK stream mixes narration and final answer; native run uses final_output', 'totalMs': (time.perf_counter() - start) * 1000, 'evidenceChars': evidence_chars, 'evidenceReason': 'sum of page text returned by successful get_page_content calls, repeats included' if reads else 'no successful page read observed', 'mode': 'official-native', 'toolTrace': trace, 'sdkResponse': result}
        finally:
            scope(None)
    Path(args.output).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps({'status': 'complete', 'mode': args.mode}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['compat', 'index', 'controlled', 'native'])
    parser.add_argument('--input')
    parser.add_argument('--output', required=True)
    main(parser.parse_args())
