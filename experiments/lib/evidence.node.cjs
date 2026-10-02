const { test } = require('node:test');
const assert = require('node:assert/strict');
const { limitEvidence, coverage } = require('./evidence.cjs');
test('evidence enforces doc, count, length and duplicate limits', () => {
  const hits = Array.from({ length: 9 }, (_, i) => ({ chunk: { id: String(i), docName: i < 5 ? 'a' : 'b', text: '合成'.repeat(250) } }));
  const out = limitEvidence(hits);
  assert.equal(out.length, 4); assert.equal(out.filter(h => h.chunk.docName === 'a').length, 3);
  assert.equal(out.reduce((s, h) => s + h.chunk.text.length, 0), 2000);
  assert.deepEqual(limitEvidence([]), []);
  assert.equal(coverage(out, [{ chunk: '0' }, { chunk: '8' }]), 0.5);
  assert.equal(limitEvidence([hits[0], hits[0]]).length, 1);
});
