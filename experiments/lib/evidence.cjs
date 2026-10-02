function limitEvidence(hits, maxChars = 2000) {
  const docs = new Map(), selected = []; let left = maxChars;
  for (const hit of hits) {
    if (selected.length >= 5 || left <= 0) break;
    const c = hit.chunk;
    if ((docs.get(c.docName) ?? 0) >= 3 || selected.some(h => h.chunk.id === c.id)) continue;
    const text = c.text.slice(0, left);
    selected.push({ ...hit, chunk: { ...c, text } });
    docs.set(c.docName, (docs.get(c.docName) ?? 0) + 1); left -= text.length;
  }
  return selected;
}
function coverage(hits, golds) {
  // Exact gold chunk inclusion, not judged relevance or gold-answer leakage.
  return golds.filter(g => hits.some(h => h.chunk.id === g.chunk)).length / golds.length;
}
module.exports = { limitEvidence, coverage };
