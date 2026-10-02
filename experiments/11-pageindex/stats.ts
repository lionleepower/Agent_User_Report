/**
 * Pure statistics for experiment 11. The question is the unit: repeats of one
 * question are averaged first, failures count as not correct, and method
 * differences are paired on the questions both methods attempted.
 */
import { bootstrap, mean, pct } from '../lib/common';

export interface Usage { requests: number; cnyByUsageAtPublishedRate: number; unknownReservedCny: number; inputTokens: number; cachedTokens: number; outputTokens: number }
export interface Row {
  id: string; task: string; repeat: number; method: string; status: string; score: number | null;
  firstAnswerMs?: number | null; totalMs?: number; evidenceCoverage?: number | null; evidenceChars?: number | null; searchCalls?: number | null;
  /** retrieval + answer calls of this query, judge excluded */
  usage?: Usage;
}

const correct = (r: Row) => (r.status === 'ok' && r.score === 2 ? 1 : 0);
const zero = (r: Row) => (r.status !== 'ok' || r.score === 0 ? 1 : 0);
const nums = (xs: (number | null | undefined)[]) => xs.filter((x): x is number => Number.isFinite(x));

/** per-question mean of f over repeats, keyed by question id */
export function perQuestion(rows: Row[], f: (r: Row) => number): Map<string, number> {
  const ids = [...new Set(rows.map(r => r.id))];
  return new Map(ids.map(id => [id, mean(rows.filter(r => r.id === id).map(f))]));
}

export function groups(records: Row[], methods: string[]) {
  const out: Record<string, unknown>[] = [];
  for (const task of [...new Set(records.map(r => r.task))]) for (const method of methods) {
    const rows = records.filter(r => r.task === task && r.method === method);
    if (!rows.length) continue;
    const byQ = [...perQuestion(rows, correct).values()];
    const good = rows.filter(r => r.status === 'ok');
    const first = nums(good.map(r => r.firstAnswerMs)), total = nums(good.map(r => r.totalMs));
    const withUsage = rows.filter(r => r.usage);
    out.push({
      task, method, questionsObserved: byQ.length, responses: rows.length, failures: rows.length - good.length,
      fullyCorrect: mean(byQ), fullyCorrectCI95: bootstrap(byQ),
      zeroOrFailed: mean([...perQuestion(rows, zero).values()]),
      // coverage = exact gold chunk among evidence actually sent; null for methods without inspectable evidence
      evidenceCoverage: good.some(r => r.evidenceCoverage != null) ? mean(nums(good.map(r => r.evidenceCoverage))) : null,
      meanEvidenceChars: good.some(r => r.evidenceChars != null) ? mean(nums(good.map(r => r.evidenceChars))) : null,
      successfulLatency: { firstAnswerMsP50: first.length ? pct(first, 50) : null, firstAnswerMsP95: first.length ? pct(first, 95) : null, totalMsP50: total.length ? pct(total, 50) : null, totalMsP95: total.length ? pct(total, 95) : null, n: good.length },
      meanSearchCalls: good.some(r => r.searchCalls != null) ? mean(nums(good.map(r => r.searchCalls))) : null,
      perQuery: withUsage.length ? {
        requests: mean(withUsage.map(r => r.usage!.requests)), inputTokens: mean(withUsage.map(r => r.usage!.inputTokens)),
        cachedTokens: mean(withUsage.map(r => r.usage!.cachedTokens)), outputTokens: mean(withUsage.map(r => r.usage!.outputTokens)),
        cnyByUsage: mean(withUsage.map(r => r.usage!.cnyByUsageAtPublishedRate)), unknownReservedCny: withUsage.reduce((s, r) => s + r.usage!.unknownReservedCny, 0),
      } : null,
    });
  }
  return out;
}

/** A minus B fully-correct rate over questions both attempted, bootstrap over questions */
export function pairedDiff(records: Row[], task: string, a: string, b: string) {
  const qa = perQuestion(records.filter(r => r.task === task && r.method === a), correct);
  const qb = perQuestion(records.filter(r => r.task === task && r.method === b), correct);
  const ds = [...qa.keys()].filter(id => qb.has(id)).map(id => qa.get(id)! - qb.get(id)!);
  return { task, a, b, pairedQuestions: ds.length, diff: ds.length ? mean(ds) : null, diffCI95: ds.length ? bootstrap(ds) : null, aBetter: ds.filter(d => d > 0).length, bBetter: ds.filter(d => d < 0).length };
}

export function pairedDiffs(records: Row[], methods: string[], reference = 'pageindex') {
  if (!methods.includes(reference)) return [];
  return [...new Set(records.map(r => r.task))].flatMap(task => methods.filter(m => m !== reference).map(m => pairedDiff(records, task, reference, m)));
}

/** one-off index cost spread over n queries, plus the measured per-query cost */
export function amortized(indexCny: number | null, perQueryCny: number | null, ns = [1, 10, 100]) {
  if (indexCny == null || perQueryCny == null) return null;
  return Object.fromEntries(ns.map(n => [n, indexCny / n + perQueryCny]));
}
