// Cross-process, fail-closed ledger. Entries contain no prompts, keys or answers.
const fs = require('node:fs');
const path = require('node:path');
const { randomUUID } = require('node:crypto');
const sleep = ms => new Promise(r => setTimeout(r, ms));
class Ledger {
  constructor(file, cap, caps) {
    if (!Number.isFinite(cap) || cap <= 0 || cap > 20) throw Error('invalid budget (0 < cap <= 20 required)');
    if (!caps || Object.values(caps).some(x => !Number.isFinite(x) || x < 0)) throw Error('invalid stage caps');
    this.file = file; this.cap = cap; this.caps = caps;
  }
  async transaction(fn) {
    fs.mkdirSync(path.dirname(this.file), { recursive: true });
    const lock = this.file + '.lock';
    const until = Date.now() + 10000;
    for (;;) {
      try { fs.mkdirSync(lock); break; } catch (e) {
        if (e.code !== 'EEXIST' || Date.now() > until) throw Error('ledger locked; inspect before recovery');
        await sleep(10);
      }
    }
    try {
      const data = fs.existsSync(this.file) ? JSON.parse(fs.readFileSync(this.file, 'utf8')) : { version: 1, cap: this.cap, caps: this.caps, entries: [] };
      if (data.version !== 1 || data.cap !== this.cap || JSON.stringify(data.caps) !== JSON.stringify(this.caps) || !Array.isArray(data.entries)) throw Error('ledger configuration mismatch');
      if (data.entries.some(e => !Number.isFinite(e.charged) || e.charged < 0)) throw Error('ledger corrupted');
      const result = fn(data);
      const tmp = this.file + '.' + randomUUID() + '.tmp';
      fs.writeFileSync(tmp, JSON.stringify(data, null, 2) + '\n', { flag: 'wx' });
      try { fs.renameSync(tmp, this.file); } catch (e) { fs.unlinkSync(tmp); throw e; }
      return result;
    } finally { fs.rmdirSync(lock); }
  }
  async reserve(stage, model, upper) {
    if (!Number.isFinite(upper) || upper <= 0 || !(stage in this.caps)) throw Error('invalid reservation');
    return this.transaction(d => {
      const total = d.entries.reduce((s, x) => s + x.charged, 0);
      const subtotal = d.entries.filter(x => x.stage === stage).reduce((s, x) => s + x.charged, 0);
      if (d.capExceeded || total + upper > this.cap || subtotal + upper > this.caps[stage]) throw Error('budget insufficient for next request');
      const id = randomUUID();
      d.entries.push({ id, stage, model, reserved: upper, charged: upper, status: 'unknown', started: new Date().toISOString() });
      return id;
    });
  }
  /** Returns true only when valid usage replaced the reservation. */
  async settle(id, usage, price, meta = {}) {
    if (!usage || !Number.isInteger(usage.prompt_tokens) || usage.prompt_tokens < 0 || !Number.isInteger(usage.completion_tokens) || usage.completion_tokens < 0) return false;
    const hit = usage.prompt_cache_hit_tokens ?? usage.prompt_tokens_details?.cached_tokens ?? 0;
    if (!Number.isInteger(hit) || hit < 0 || hit > usage.prompt_tokens) return false;
    return this.transaction(d => {
      const e = d.entries.find(x => x.id === id);
      if (!e || e.status !== 'unknown') throw Error('invalid settlement');
      const cny = (hit * price.hit + (usage.prompt_tokens - hit) * price.miss + usage.completion_tokens * price.out) / 1e6;
      e.usage = { prompt_tokens: usage.prompt_tokens, cached_tokens: hit, completion_tokens: usage.completion_tokens };
      e.cny = cny; e.charged = cny; e.status = cny > e.reserved ? 'reservation_exceeded' : 'metered';
      e.finished = new Date().toISOString();
      if (meta.truncated) e.truncated = true;
      if (cny > e.reserved) d.capExceeded = true;
      return true;
    });
  }
}
module.exports = { Ledger };
