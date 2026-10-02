import { describe, expect, it } from 'vitest';
import { amortized, groups, pairedDiff, type Row } from './stats';

const row = (id: string, method: string, repeat: number, score: number | null, status = 'ok'): Row =>
  ({ id, task: 'clean', method, repeat, score, status, totalMs: 100, firstAnswerMs: 10 });

describe('experiment 11 statistics', () => {
  it('averages repeats within a question and counts failures as not correct', () => {
    const rows = [row('q1', 'bm25', 0, 2), row('q1', 'bm25', 1, null, 'failed'), row('q2', 'bm25', 0, 2), row('q2', 'bm25', 1, 2)];
    const [g] = groups(rows, ['bm25']) as any[];
    expect(g.questionsObserved).toBe(2);
    expect(g.responses).toBe(4);
    expect(g.failures).toBe(1);
    expect(g.fullyCorrect).toBe(0.75); // (0.5 + 1) / 2, not 3/3 successes
    expect(g.successfulLatency.n).toBe(3); // latency only from successful responses
  });

  it('pairs differences only on questions both methods attempted', () => {
    const rows = [row('q1', 'pageindex', 0, 2), row('q1', 'bm25', 0, 0), row('q2', 'pageindex', 0, 0), row('q2', 'bm25', 0, 0), row('q3', 'pageindex', 0, 2)];
    const d = pairedDiff(rows, 'clean', 'pageindex', 'bm25');
    expect(d.pairedQuestions).toBe(2);
    expect(d.diff).toBe(0.5);
    expect(d.aBetter).toBe(1);
    expect(d.bBetter).toBe(0);
  });

  it('reports missing metrics as null instead of zero', () => {
    const [g] = groups([row('q1', 'native', 0, 2)], ['native']) as any[];
    expect(g.evidenceCoverage).toBeNull();
    expect(g.perQuery).toBeNull();
    expect(pairedDiff([row('q1', 'a', 0, 2)], 'clean', 'a', 'b').diff).toBeNull();
    expect(amortized(null, 0.01)).toBeNull();
  });

  it('amortizes index cost over query counts', () => {
    expect(amortized(1, 0.01)).toEqual({ 1: 1.01, 10: 0.11, 100: 0.02 });
  });
});
