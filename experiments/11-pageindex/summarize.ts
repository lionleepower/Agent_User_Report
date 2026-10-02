/**
 * Offline: merge the measured experiment 11 runs into results/summary.json.
 * No network, keys or corpus text. Ledger totals are read only for cost by stage.
 *
 *   npx vite-node experiments/11-pageindex/summarize.ts
 */
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { writeJson } from '../lib/common';
import { amortized, groups, pairedDiffs, type Row } from './stats';

const dir = 'experiments/11-pageindex/results';
const read = (name: string) => (existsSync(join(dir, name)) ? JSON.parse(readFileSync(join(dir, name), 'utf8')) : null);
const main = read('main.json'), multi = read('multi.json'), native = read('native.json');
const index = read('index.json'), embeddings = read('embeddings.json'), compatibility = read('compatibility.json'), pilot = read('preflight.json');
const previous = read('summary.json');
const ledgerFile = join(process.env.LOCALAPPDATA ?? '', 'llm-bench', 'experiments', 'continuation-2026-09-30', 'budget-ledger.json');
const ledger = existsSync(ledgerFile) ? JSON.parse(readFileSync(ledgerFile, 'utf8')) : null;

const methods = ['whole', 'bm25', 'dense', 'pageindex'];
const controlled: Row[] = [...(main?.records ?? []), ...(multi?.records ?? [])];
const run = (r: any) => r && { runIds: r.resumed?.runs ?? [r.runId], status: r.status, planned: r.planned, actual: r.actual, ok: r.records.filter((x: any) => x.status === 'ok').length, repetitions: r.repetitions, droppedFailures: r.resumed?.droppedFailures ?? [], usage: r.usageAllRuns ?? r.usage };
const byStage = ledger ? Object.fromEntries([...new Set<string>(ledger.entries.map((e: any) => e.stage))].map(stage => {
  const e = ledger.entries.filter((x: any) => x.stage === stage);
  return [stage, { requests: e.length, cnyByUsageAtPublishedRate: e.filter((x: any) => x.status === 'metered').reduce((s: number, x: any) => s + x.cny, 0), unknownReservedCny: e.filter((x: any) => x.status !== 'metered').reduce((s: number, x: any) => s + x.charged, 0), truncated: e.filter((x: any) => x.truncated).length }];
})) : null;

const controlledGroups = groups(controlled, methods);
const nativeGroups = native ? groups(native.records, ['native']) : [];
// Index cost is one-off; per-query cost is the measured mean of the clean + noise answers (judge excluded).
const perQuery = (method: string) => {
  const rows = (main?.records ?? []).filter((r: any) => r.method === method && r.usage);
  return rows.length ? rows.reduce((s: number, r: any) => s + r.usage.cnyByUsageAtPublishedRate, 0) / rows.length : null;
};
// PageIndex index calls are the index-stage deepseek-flash ledger entries (charged = settled or reserved).
const treeIndexCny = index && ledger ? ledger.entries.filter((e: any) => e.stage === 'index' && e.model === 'deepseek-flash').reduce((s: number, e: any) => s + e.charged, 0) : null;
const indexCny = { pageindex: treeIndexCny, dense: embeddings?.usage?.cnyByUsageAtPublishedRate ?? null, bm25: 0, whole: 0 };
const amortization = Object.fromEntries(methods.map(m => [m, { indexCny: indexCny[m as keyof typeof indexCny], perQueryCny: perQuery(m), totalPerQueryAt: amortized(indexCny[m as keyof typeof indexCny] ?? null, perQuery(m)) }]));

const complete = (r: any) => r && r.actual === r.planned && r.records.every((x: any) => x.status === 'ok');
writeJson(join(dir, 'summary.json'), {
  schemaVersion: 2,
  date: new Date().toISOString().slice(0, 10),
  status: main && multi && native ? (complete(main) && complete(multi) && complete(native) ? 'complete' : 'complete_with_failures_or_partial') : 'partial',
  model: 'deepseek-flash (DeepSeek-V4.1-Flash, non-thinking) for tree search, answers and judging; text-embedding-v4 1024-d for dense',
  corpusCommit: previous?.corpusCommit, corpus: previous?.corpus, questions: previous?.questions, pageindexVersion: '0.2.10',
  index: index && { status: index.status, mode: index.mode, indexMs: index.indexMs, cny: indexCny.pageindex },
  vectorIndex: embeddings && { status: embeddings.status, chunks: embeddings.chunks, indexMs: embeddings.indexMs, cny: embeddings.usage.cnyByUsageAtPublishedRate, requests: embeddings.usage.requests },
  compatibility: compatibility && { runId: compatibility.runId, status: compatibility.status, checks: compatibility.checks },
  pilot: pilot && { ...run(pilot), note: 'pilot 4 clean + 4 noise + 4 multi x 1; not pooled into formal results' },
  runs: { main: run(main), multi: run(multi), native: run(native) },
  controlled: { conditions: 'evidence <= 5 units, <= 3 per document, <= 2000 chars; same answer prompt; whole sends all 37 documents (200347 chars); PageIndex = official local tools in a controlled adapter, <= 6 tree-search model calls and 120 s per question', groups: controlledGroups, pairedDifferences: pairedDiffs(controlled, methods) },
  native: { conditions: 'official PageIndex chat_completions, non-stream final_output, max_turns 6; separate from controlled; final-answer TTFT unobservable (null)', groups: nativeGroups },
  amortization,
  costByStage: byStage,
  costBasis: 'usage x verified peak list price (DeepSeek peak; DashScope Beijing); unknown reservations listed separately; no provider bill was read',
  statistics: 'question is the unit: repeats averaged within a question; failures count as not fully correct; percentile bootstrap 2000x seed 7 over questions; paired differences only on questions both methods attempted; latency from successful responses only',
  limitations: [
    'questions were generated from and checked against pinned public excerpts by the assistant, not independently human-annotated; 12 multi-hop questions are exploratory',
    'the judge is the same deepseek-flash model as the answerer',
    'evidence coverage is exact inclusion of the gold chunk in the evidence sent; it does not prove the answer used it',
    'PageIndex latency includes Python SDK start-up per question',
    'deepseek-flash results are not pooled with historical deepseek-chat results',
    'results hold for this corpus, question types, model and hardware only',
  ],
});
console.log('wrote', join(dir, 'summary.json'));
