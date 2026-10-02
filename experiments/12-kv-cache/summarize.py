"""Validate local observations and produce answer-free grouped summary."""
import json
from pathlib import Path
import statistics

here = Path(__file__).parent
source = here / 'results/local.json'
data = json.loads(source.read_text(encoding='utf8'))
assert data['status'] == 'complete' and data['repetitions'] == 5
ok = [r for r in data['rows'] if r['status'] == 'ok']
skips = [r for r in data['rows'] if r['status'] == 'skipped_capacity']
assert len(ok) == 150 and len(skips) == 30
assert all(r['cachedPromptTokens'] == r['cachedMetricDelta'] for r in ok)
assert all(r['cachedPromptTokens'] == 0 for r in ok if r['state'] != 'shared_prefix')
assert all(r['cachedPromptTokens'] > 0 for r in ok if r['state'] == 'shared_prefix')
assert all(r['kvAllocatedMiB'] is not None and r['kvOccupiedBytes'] is None for r in ok)
assert all(r['promptTokens'] + 64 <= r['contextPerSlot'] for r in ok)
groups = {}
for row in ok:
    key = (row['kvType'], row['contextTotal'], row['slots'], row['shape'], row['state'])
    groups.setdefault(key, []).append(row)
rows = []
for (dtype, ctx, slots, shape, state), records in groups.items():
    assert len(records) == 5
    vals = sorted(r['firstAnswerMs'] for r in records)
    rows.append({'kvType': dtype, 'contextTotal': ctx, 'slots': slots, 'shape': shape, 'state': state, 'n': 5, 'contextPerSlot': records[0]['contextPerSlot'], 'firstAnswerMsP50': statistics.median(vals), 'firstAnswerMsP95': vals[-1], 'totalMsP50': statistics.median(r['totalMs'] for r in records), 'cachedPromptTokensP50': statistics.median(r['cachedPromptTokens'] for r in records), 'kvAllocatedMiB': records[0]['kvAllocatedMiB'], 'gpuPeakTotalMiBP50': statistics.median(r['gpuPeakTotalMiB'] for r in records), 'gpuPeakDeltaMiBP50': statistics.median(r['gpuPeakDeltaMiB'] for r in records), 'kvOccupiedBytes': None})
cloud_file = here / 'results/cloud.json'
cloud = {'status': 'not_run', 'actualRequests': 0}
if cloud_file.exists():
    c = json.loads(cloud_file.read_text(encoding='utf8'))
    assert all(r['actual'] == r['planned'] == 8 for r in c['rows']) or c['status'] != 'complete'
    cloud = {'status': c['status'], 'runId': c['runId'], 'model': c['model'], 'markerTokens': c.get('markerTokens'), 'actualRequests': sum(r['actual'] - r['errors'] for r in c['rows']), 'plannedRequests': sum(r['planned'] for r in c['rows']), 'markerProbeRequests': c['usage']['requests'] - sum(r['actual'] for r in c['rows']), 'costCny': c['usage']['cnyByUsageAtPublishedRate'], 'unknownReservedCny': c['usage']['unknownReservedCny'], 'costBasis': c.get('costBasis'), 'conditions': [{k: r[k] for k in ('shape', 'concurrency', 'variant', 'planned', 'actual', 'errors', 'inputTokens', 'cachedTokens', 'outputTokens', 'firstAnswerMsP50', 'firstAnswerMsP95')} for r in c['rows']], 'source': 'experiments/12-kv-cache/results/cloud.json', 'limitations': c.get('limitations', [])}
out = {'schemaVersion': 1, 'runId': data['runId'], 'date': data['date'], 'status': 'complete' if cloud['status'] == 'complete' else 'partial', 'localStatus': 'complete', 'cloud': cloud, 'corpusCommit': data['corpusCommit'], 'model': data['model'], 'modelSha256': data['modelSha256'], 'runtime': data['runtime'], 'priceBasis': 'local runs cost CNY 0 (electricity excluded); cloud cost in cloud.costCny', 'costCny': 0, 'validLocalRequests': len(ok), 'capacitySkips': len(skips), 'repetitions': 5, 'outputLimit': 64, 'rows': rows, 'source': 'experiments/12-kv-cache/results/local.json', 'limitations': ['serial requests pinned to slot 0; slot count is allocation configuration, not a concurrent-throughput test', 'p95 is largest of five measurements, not a stable tail estimate', 'GPU totals include other desktop processes; differences are not isolated KV usage', 'cached prompt counters do not report occupied KV bytes', 'first_in_shape forces no prompt reuse; server startup measured separately', '64 token output limit: latency/resource experiment, not answer quality or cache-quantization quality']}
(here / 'results/summary.json').write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n', encoding='utf8', newline='\n')
print(json.dumps({'validatedRequests': len(ok), 'skips': len(skips), 'groups': len(rows), 'costCny': 0}))
