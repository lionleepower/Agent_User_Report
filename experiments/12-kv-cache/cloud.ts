/** DeepSeek provider cache observations, never interpreted as GPU KV memory. */
import { readFileSync, existsSync, copyFileSync } from 'node:fs';
import { join } from 'node:path';
import { streamChat } from '../lib/openai';
import { pct, writeJson } from '../lib/common';
import type { Msg } from '../../tools/retrieval-bench/lib/llm';
const raw = process.env.BENCH_RUN_DIR!;
if (!raw || !process.env.BENCH_GATEWAY || !process.env.BENCH_BUDGET_CNY) throw Error('use budget gateway');
const source = JSON.parse(readFileSync(join(raw, 'public-input.json'), 'utf8'));
const ep = { label: process.env.BENCH_LLM_MODEL!, model: process.env.BENCH_LLM_MODEL!, baseUrl: process.env.BENCH_LLM_BASE!, apiKey: process.env.BENCH_LLM_KEY!, strict: true };
const runId = `cloud-${new Date().toISOString().replace(/[:.]/g, '-')}`;
// No ledger file yet means no gateway request has been made.
/** only gateway 402 responses are budget stops; file paths such as budget-ledger.json must not match */
const BUDGET_STOP = /budget insufficient|HTTP 402/;
const ledger = () => (existsSync(process.env.BENCH_LEDGER!) ? JSON.parse(readFileSync(process.env.BENCH_LEDGER!, 'utf8')).entries : []) as { status: string; cny?: number; charged: number }[];
const totals = (e: ReturnType<typeof ledger>) => ({ requests: e.length, cnyByUsageAtPublishedRate: e.filter(x => x.status === 'metered').reduce((s, x) => s + (x.cny ?? 0), 0), unknownReservedCny: e.filter(x => x.status !== 'metered').reduce((s, x) => s + x.charged, 0) });
const limitations = ['first request is not guaranteed uncached', 'hit counts expose provider billing cache, not KV memory', 'concurrency 4 starts four requests on one prefix at once, so early requests may all miss'];
/** digits only for both variants, so stable and varying markers can tokenize alike */
const nonce = (shape: string, concurrency: number, variant: string, i: number) =>
  variant === 'stable' ? '00000000' : String(10000000 + ((Number(runId.replace(/\D/g, '').slice(-6)) * 131 + (shape === 'whole' ? 5000 : 0) + concurrency * 100 + i) % 90000000));
const marker = (n: string) => `实验标记=${n}\n`;
/** equal characters are not equal tokens: measure every marker before the run */
async function markerTokens(): Promise<Record<string, number>> {
  const all = new Set<string>();
  for (const shape of ['retrieval', 'whole']) for (const c of [1, 4]) for (const v of ['stable', 'varying']) for (let i = 0; i < 8; i++) all.add(nonce(shape, c, v, i));
  const out: Record<string, number> = {};
  for (const n of all) {
    // only usage matters here; a 1-token reply may be blank, so no strict answer check
    const r = await streamChat({ ...ep, strict: false }, [{ role: 'user', content: marker(n) }], 1);
    if (!(r.promptTokens > 0)) throw Error('marker token usage unavailable');
    out[n] = r.promptTokens;
  }
  return out;
}
async function main() {
  const out = 'experiments/12-kv-cache/results/cloud.json';
  if (existsSync(out)) copyFileSync(out, join(raw, `${runId}-previous-cloud-summary.json`));
  const initial = ledger().length;
  const tokens = await markerTokens();
  const lengths = [...new Set(Object.values(tokens))];
  if (lengths.length !== 1) {
    writeJson(out, { runId, date: new Date().toISOString(), status: 'aborted_marker_token_mismatch', model: ep.model, markerTokenLengths: lengths, usage: totals(ledger().slice(initial)) });
    throw Error('marker token lengths differ; varying prefix would not be token-equal');
  }
  const rows: any[] = [];
  let stopped = false;
  for (const shape of ['retrieval', 'whole']) for (const concurrency of [1, 4]) {
    // Interleave fixed/varying blocks; no claim that first request is uncached.
    for (const variant of (concurrency === 1 ? ['stable', 'varying'] : ['varying', 'stable'])) {
      if (stopped) break;
      const records: any[] = []; let next = 0;
      await Promise.all(Array.from({ length: concurrency }, async () => {
        while (next < 8 && !stopped) {
          const i = next++;
          const messages: Msg[] = source[shape].map((m: Msg) => ({ ...m }));
          messages[0].content = marker(nonce(shape, concurrency, variant, i)) + messages[0].content;
          try {
            const a = await streamChat(ep, messages, 200);
            writeJson(join(raw, `${runId}-${shape}-${concurrency}-${variant}-${i}.json`), a);
            records.push({ i, status: 'ok', firstAnswerMs: a.firstAnswerMs, totalMs: a.totalMs, promptTokens: a.promptTokens, cachedTokens: a.cachedTokens, completionTokens: a.completionTokens });
          } catch (e) { const budgetStop = BUDGET_STOP.test((e as Error).message); stopped ||= budgetStop; records.push({ i, status: 'failed', reason: budgetStop ? 'budget_stop' : 'request_failure' }); }
        }
      }));
      const good = records.filter(r => r.status === 'ok');
      rows.push({ shape, concurrency, variant, planned: 8, actual: records.length, errors: records.length - good.length, firstAnswerMsP50: good.length ? pct(good.map(r => r.firstAnswerMs), 50) : null, firstAnswerMsP95: good.length ? pct(good.map(r => r.firstAnswerMs), 95) : null, inputTokens: good.reduce((s, r) => s + r.promptTokens, 0), cachedTokens: good.reduce((s, r) => s + r.cachedTokens, 0), outputTokens: good.reduce((s, r) => s + r.completionTokens, 0), records });
      writeJson('experiments/12-kv-cache/results/cloud.json', { runId, date: new Date().toISOString(), status: stopped ? 'partial_budget_stop' : 'running', model: ep.model, markerTokens: lengths[0], rows, limitations });
      console.log(`${shape} c${concurrency} ${variant}: ${records.length}/8`);
    }
  }
  writeJson('experiments/12-kv-cache/results/cloud.json', { runId, date: new Date().toISOString(), status: stopped ? 'partial_budget_stop' : rows.some(r => r.errors) ? 'complete_with_failures' : 'complete', model: ep.model, markerTokens: lengths[0], rows, usage: totals(ledger().slice(initial)), costBasis: 'usage x verified peak list price; not a provider bill', limitations });
}
main().catch(e => { console.error(e.message); process.exitCode = 1; });
