/** New paired experiment only. All paid calls require the loopback budget gateway. */
import { spawn } from 'node:child_process';
import { readFileSync, existsSync, appendFileSync, copyFileSync } from 'node:fs';
import { join } from 'node:path';
import { createRequire } from 'node:module';
import { Bm25Index, buildKbQuery } from '../../shared/retrieval';
import { fullMessages, retrievedMessages, RULES, writeJson } from '../lib/common';
import { groups as groupStats, pairedDiffs } from './stats';
import { streamChat } from '../lib/openai';
import type { KbChunk } from '../../shared/retrieval';
import type { Msg } from '../../tools/retrieval-bench/lib/llm';
const require = createRequire(import.meta.url);
const { limitEvidence, coverage } = require('../lib/evidence.cjs');
type Question = { id: string; question: string; points: string[]; gold?: { chunk: string }; golds?: { chunk: string }[] };
type Input = { commit: string; docs: { name: string; text: string }[]; chunks: KbChunk[]; questions: Question[]; noisy: { id: string; asr: string }[]; multihop: Question[] };
const raw = process.env.BENCH_RUN_DIR!;
if (!raw || !process.env.BENCH_GATEWAY || !process.env.BENCH_BUDGET_CNY) throw Error('use with-keys.cjs + with-budget.cjs');
const source: Input = JSON.parse(readFileSync(join(raw, 'public-input.json'), 'utf8'));
const phase = process.argv[process.argv.indexOf('--phase') + 1];
if (!['compatibility', 'embeddings', 'preflight', 'main', 'multi', 'native'].includes(phase)) throw Error('explicit --phase required');
const ep = { label: process.env.BENCH_LLM_MODEL!, model: process.env.BENCH_LLM_MODEL!, baseUrl: process.env.BENCH_LLM_BASE!, apiKey: process.env.BENCH_LLM_KEY!, strict: true };
const index = new Bm25Index(source.chunks);
const runId = `${phase}-${new Date().toISOString().replace(/[:.]/g, '-')}`;
const output = join('experiments', '11-pageindex', 'results', `${phase}.json`);
// No ledger file yet means no gateway request has been made.
/** only gateway 402 responses are budget stops; file paths such as budget-ledger.json must not match */
const BUDGET_STOP = /budget insufficient|HTTP 402/;
const ledger = () => (existsSync(process.env.BENCH_LEDGER!) ? JSON.parse(readFileSync(process.env.BENCH_LEDGER!, 'utf8')).entries : []) as { status: string; cny?: number; charged: number; usage?: { prompt_tokens: number; cached_tokens: number; completion_tokens: number } }[];
const totals = (entries: ReturnType<typeof ledger>) => ({ requests: entries.length, cnyByUsageAtPublishedRate: entries.filter(e => e.status === 'metered').reduce((s, e) => s + (e.cny ?? 0), 0), unknownReservedCny: entries.filter(e => e.status !== 'metered').reduce((s, e) => s + e.charged, 0), inputTokens: entries.reduce((s, e) => s + (e.usage?.prompt_tokens ?? 0), 0), cachedTokens: entries.reduce((s, e) => s + (e.usage?.cached_tokens ?? 0), 0), outputTokens: entries.reduce((s, e) => s + (e.usage?.completion_tokens ?? 0), 0) });
async function api(url: string, body: object): Promise<any> {
  const r = await fetch(url, { method: 'POST', headers: { Authorization: `Bearer ${process.env.BENCH_GATE_TOKEN}`, 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal: AbortSignal.timeout(120000) });
  if (!r.ok) throw Error(`gateway HTTP ${r.status}`);
  return r.json();
}
async function embed(texts: string[]): Promise<number[][]> {
  const j = await api(process.env.BENCH_DASHSCOPE_BASE + '/embeddings', { model: 'text-embedding-v4', input: texts, dimensions: 1024, encoding_format: 'float' });
  if (j.data?.length !== texts.length) throw Error('embedding count mismatch');
  return j.data.sort((a: any, b: any) => a.index - b.index).map((a: any) => {
    if (!Array.isArray(a.embedding) || a.embedding.length !== 1024 || a.embedding.some((x: any) => !Number.isFinite(x))) throw Error('invalid embedding');
    const norm = Math.sqrt(a.embedding.reduce((s: number, x: number) => s + x * x, 0));
    if (!norm) throw Error('zero embedding');
    return a.embedding.map((x: number) => x / norm);
  });
}
async function python(mode: 'compat' | 'controlled' | 'native', q: Question) {
  const input = join(raw, `${runId}-question.json`), result = join(raw, `${runId}-sdk.json`);
  writeJson(input, { ...q, rules: RULES });
  const exe = join(process.env.LOCALAPPDATA!, 'llm-bench', 'experiments', 'venv', 'Scripts', 'python.exe');
  await new Promise<void>((resolve, reject) => {
    const child = spawn(exe, ['experiments/11-pageindex/adapter.py', mode, '--input', input, '--output', result], { stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true });
    let log = ''; child.stdout.on('data', b => { log += b.toString(); }); child.stderr.on('data', b => { log += b.toString(); });
    const timer = setTimeout(() => { child.kill(); reject(Error('SDK 120 second limit')); }, 125000);
    child.on('error', e => { clearTimeout(timer); reject(e); });
    child.on('exit', code => { clearTimeout(timer); if (code === 0) resolve(); else { appendFileSync(join(raw, `${runId}-sdk-errors.log`), log); reject(Error(BUDGET_STOP.test(log) ? 'budget stop' : 'SDK adapter failed')); } });
  });
  return JSON.parse(readFileSync(result, 'utf8'));
}
async function grade(q: Question, text: string) {
  const result = await streamChat(ep, [{ role: 'system', content: '你是严格的评测员，只输出 JSON。' }, { role: 'user', content: `问题：${q.question}\n参考要点：${q.points.join('\n')}\n待评回答：${text}\n评分：2=正确覆盖主要要点且没有错误；1=只覆盖部分要点或有小错；0=没答、说资料中没有、或答错。只输出 {"score":0|1|2}` }], 32);
  const matched = result.text.match(/\{[^}]*\}/);
  const score = matched ? JSON.parse(matched[0]).score : null;
  if (![0, 1, 2].includes(score)) throw Error('judge invalid JSON/score');
  return { score, raw: result.text };
}
async function main() {
  if (existsSync(output)) copyFileSync(output, join(raw, `${runId}-previous-${phase}-summary.json`));
  const initial = ledger().length;
  if (phase === 'compatibility') {
    // Same public prefix twice: cache fields must be observable (a hit is not guaranteed).
    const prefix = [{ role: 'system' as const, content: RULES }, { role: 'user' as const, content: `【参考资料】\n${source.chunks.slice(0, 3).map(c => c.text).join('\n')}\n【参考资料结束】\n\n面试官问：${source.questions[0].question}` }];
    const streams = [await streamChat(ep, prefix, 64), await streamChat(ep, prefix, 64)];
    const plain = await api(process.env.BENCH_LLM_BASE + '/chat/completions', { model: ep.model, messages: [{ role: 'user', content: '仅输出 JSON：{"ok":true}' }], max_tokens: 16, stream: false });
    const sdk = await python('compat', { id: 'compat', question: '', points: [] });
    const [embedding] = await embed(['公开语料连通性检查']);
    const entries = ledger().slice(initial);
    const checks = {
      streamFinalAnswer: streams.every(s => s.text.length > 0 && s.firstAnswerMs > 0),
      thinkingDisabled: streams.every(s => s.reasoningChars === 0) && !plain.choices?.[0]?.message?.reasoning_content,
      cacheFieldsObservable: Number.isInteger(plain.usage?.prompt_cache_hit_tokens) && Number.isInteger(plain.usage?.prompt_cache_miss_tokens),
      nonStreamAnswer: /true/.test(plain.choices?.[0]?.message?.content ?? ''),
      sdkThroughGateway: sdk.ok === true,
      dashscopeEmbedding: embedding.length === 1024,
      // 2 stream + 1 plain + 1 SDK + 1 embedding; anything else bypassed or retried
      ledgerAccountsEveryCall: entries.length === 5 && entries.every(e => e.status === 'metered'),
      noTruncation: entries.every((e: any) => !e.truncated),
    };
    const status = Object.values(checks).every(Boolean) ? 'complete' : 'failed_checks';
    writeJson(output, { runId, status, date: new Date().toISOString(), model: ep.model, checks, streams: streams.map(s => ({ firstTokenMs: s.firstTokenMs, firstAnswerMs: s.firstAnswerMs, totalMs: s.totalMs, promptTokens: s.promptTokens, cachedTokens: s.cachedTokens, completionTokens: s.completionTokens })), sdk: { finish: sdk.finish, totalMs: sdk.totalMs }, usage: totals(entries), costBasis: 'usage x verified peak list price; not a provider bill' });
    if (status !== 'complete') throw Error('compatibility checks failed: ' + Object.entries(checks).filter(([, v]) => !v).map(([k]) => k).join(', '));
    return;
  }
  if (phase === 'embeddings') {
    const t = performance.now(), vectors: number[][] = [];
    for (let i = 0; i < source.chunks.length; i += 10) vectors.push(...await embed(source.chunks.slice(i, i + 10).map(c => c.text)));
    writeJson(join(raw, 'vectors.json'), { commit: source.commit, ids: source.chunks.map(c => c.id), vectors });
    writeJson(output, { runId, status: 'complete', model: 'text-embedding-v4', source: source.commit, chunks: vectors.length, indexMs: performance.now() - t, usage: totals(ledger().slice(initial)) }); return;
  }
  if (!existsSync(join(raw, 'pageindex-id.json')) || !existsSync(join(raw, 'vectors.json'))) throw Error('official index and fresh public vector index required');
  const vectors = JSON.parse(readFileSync(join(raw, 'vectors.json'), 'utf8'));
  if (vectors.commit !== source.commit || vectors.ids.some((id: string, i: number) => id !== source.chunks[i].id)) throw Error('vector corpus mismatch');
  const clean = source.questions.map(q => ({ ...q, task: 'clean' }));
  const noise = source.questions.map(q => ({ ...q, question: source.noisy.find(n => n.id === q.id)!.asr, task: 'noise' }));
  const multi = source.multihop.map(q => ({ ...q, task: 'multi' }));
  const questions = phase === 'preflight' ? [...clean.slice(0, 4), ...noise.slice(0, 4), ...multi.slice(0, 4)] : phase === 'main' ? [...clean, ...noise] : multi;
  const methods = phase === 'native' ? ['native'] : ['whole', 'bm25', 'dense', 'pageindex'];
  const records: any[] = [], rawFile = join(raw, `${runId}-answers.jsonl`);
  // --resume keeps the successful records of an interrupted run of the same phase/model/corpus
  // and reruns only the rest; dropped failures are counted, never hidden.
  const previous = process.argv.includes('--resume') && existsSync(output) ? JSON.parse(readFileSync(output, 'utf8')) : null;
  if (process.argv.includes('--resume') && (!previous || previous.phase !== phase || previous.model !== ep.model || previous.corpusCommit !== source.commit)) throw Error('no compatible run to resume');
  const done = new Map<string, any>((previous?.records ?? []).filter((r: any) => r.status === 'ok').map((r: any) => [`${r.task}|${r.id}|${r.repeat}|${r.method}`, r]));
  const resumed = previous ? { runs: [...(previous.resumed?.runs ?? [previous.runId]), runId], keptRecords: done.size, droppedFailures: [...(previous.resumed?.droppedFailures ?? []), ...previous.records.filter((r: any) => r.status !== 'ok').map((r: any) => ({ runId: previous.runId, id: r.id, task: r.task, repeat: r.repeat, method: r.method, reason: r.reason }))], priorUsage: previous.usageAllRuns ?? previous.usage } : undefined;
  const allUsage = (now: ReturnType<typeof totals>) => resumed ? Object.fromEntries(Object.entries(now).map(([k, v]) => [k, v + (resumed.priorUsage?.[k] ?? 0)])) : now;
  let stopped = false;
  const repeats = phase === 'preflight' ? 1 : 2;
  for (let repeat = 0; repeat < repeats && !stopped; repeat++) {
    for (let qi = 0; qi < questions.length && !stopped; qi++) {
      const q = questions[qi];
      const shift = (qi + repeat) % methods.length;
      for (const method of [...methods.slice(shift), ...methods.slice(0, shift)]) {
        const kept = done.get(`${q.task}|${q.id}|${repeat}|${method}`);
        if (kept) { records.push(kept); continue; }
        const before = ledger().length, start = performance.now();
        let judgeFrom: number | undefined;
        let record: any = { id: q.id, task: q.task, repeat, method, status: 'failed', score: null };
        try {
          let hits: any[] = [], tree: any, answer: any;
          if (method === 'whole') hits = source.chunks.map(chunk => ({ chunk }));
          if (method === 'bm25') hits = index.search(buildKbQuery(q.question), { k: 20, perDoc: 3, relCut: 0.3, minCoverage: 0.12 });
          if (method === 'dense') {
            const [v] = await embed([q.question]);
            hits = source.chunks.map((chunk, i) => ({ chunk, score: v.reduce((s, x, j) => s + x * vectors.vectors[i][j], 0) })).sort((a, b) => b.score - a.score);
          }
          if (method === 'pageindex') {
            tree = await python('controlled', q);
            hits = tree.ids.map((id: string) => ({ chunk: source.chunks.find(c => c.id === id) }));
            if (hits.some(h => !h.chunk)) throw Error('unknown tree evidence');
          }
          if (method !== 'whole') hits = limitEvidence(hits);
          const retrievalMs = performance.now() - start;
          if (method === 'native') answer = await python('native', q);
          else answer = await streamChat(ep, method === 'whole' ? fullMessages(source.docs, q.question) : retrievedMessages(hits, q.question), 400);
          const firstAnswerMs = method === 'native' ? answer.firstAnswerMs : retrievalMs + answer.firstAnswerMs;
          const answerTotalMs = performance.now() - start;
          judgeFrom = ledger().length;
          const scoring = await grade(q, answer.text);
          const golds = q.golds ?? [q.gold!];
          record = { ...record, status: 'ok', score: scoring.score, evidenceCoverage: method === 'native' ? null : coverage(hits, golds), retrievalMs: method === 'native' ? null : retrievalMs, firstAnswerMs, totalMs: answerTotalMs, generationFirstMs: method === 'native' ? null : answer.firstAnswerMs, evidenceChars: method === 'whole' ? source.docs.reduce((s, d) => s + d.text.length, 0) : method === 'native' ? answer.evidenceChars ?? null : hits.reduce((s, h) => s + h.chunk.text.length, 0), searchCalls: tree?.searchCalls ?? null };
          appendFileSync(rawFile, JSON.stringify({ ...record, text: answer.text, judgeRaw: scoring.raw, treeTrace: tree?.trace, nativeTrace: method === 'native' ? answer : undefined }) + '\n');
        } catch (e) {
          const message = (e as Error).message;
          record.reason = BUDGET_STOP.test(message) ? 'budget_stop' : /SDK/.test(message) ? 'sdk_failure' : 'request_or_judge_failure';
          if (record.reason === 'budget_stop') stopped = true;
          appendFileSync(rawFile, JSON.stringify(record) + '\n');
        }
        // Query cost excludes the judge; judge cost is kept separately for stage totals.
        const spent = ledger().slice(before);
        const split = judgeFrom === undefined ? spent.length : judgeFrom - before;
        record.usage = totals(spent.slice(0, split)); record.judgeUsage = totals(spent.slice(split)); records.push(record);
        writeJson(output, { runId, date: new Date().toISOString(), status: 'running', phase, model: ep.model, corpusCommit: source.commit, planned: questions.length * repeats * methods.length, actual: records.length, repetitions: repeats, records, usage: totals(ledger().slice(initial)), usageAllRuns: allUsage(totals(ledger().slice(initial))), resumed });
        console.log(`${phase} ${q.task} ${qi + 1}/${questions.length} r${repeat + 1} ${method}: ${record.status}`);
        if (stopped) break;
      }
    }
  }
  const groups = groupStats(records, methods);
  const differences = pairedDiffs(records, methods);
  writeJson(output, { runId, date: new Date().toISOString(), status: stopped ? 'partial_budget_stop' : records.some(r => r.status !== 'ok') ? 'complete_with_failures' : 'complete', phase, model: ep.model, corpusCommit: source.commit, planned: questions.length * repeats * methods.length, actual: records.length, repetitions: repeats, records, groups, pairedDifferences: differences, usage: totals(ledger().slice(initial)), usageAllRuns: allUsage(totals(ledger().slice(initial))), resumed, statistics: 'question is the unit: repeats averaged per question; failures count as not fully correct; percentile bootstrap 2000x seed 7 over questions; paired differences only on questions both methods attempted', limitations: ['partial groups do not represent the full planned sample', 'native evidence length is the sum of observed page reads (repeats included); null when no page read was observed', 'tree adapter startup included in end-to-end latency', 'judge calls reported as judgeUsage, excluded from per-query cost and answer latency'] });
}
main().catch(e => { console.error(BUDGET_STOP.test(e.message) ? 'budget stop' : e.message); process.exitCode = 1; });
