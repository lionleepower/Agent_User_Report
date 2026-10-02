const { test } = require('node:test');
const assert = require('node:assert/strict');
const { mkdtempSync, readFileSync, rmSync } = require('node:fs');
const { tmpdir } = require('node:os');
const { join } = require('node:path');
const { spawn } = require('node:child_process');
const http = require('node:http');
const { Ledger, gateway } = require('./gateway.cjs');
const { encryptedKeys } = require('../../tools/retrieval-bench/provider-keys.cjs');
const price = { hit: 0.2, miss: 2, out: 3 };
function fixture(t, cap = 1) {
  const dir = mkdtempSync(join(tmpdir(), 'bench-ledger-test-'));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const file = join(dir, 'ledger.json');
  return { file, ledger: new Ledger(file, cap, { test: cap }) };
}
test('provider keys prefer keyring, never borrow another provider key', () => {
  const s = { llm: { baseUrl: 'https://api.deepseek.com', apiKeyEnc: 'ds', keyring: { dashscope: { apiKeyEnc: 'filed' } } }, asr: { realtime: { baseUrl: 'https://dashscope.aliyuncs.com/api/v1', apiKeyEnc: 'old' } } };
  assert.deepEqual(encryptedKeys(s), { deepseek: 'ds', dashscope: 'filed' });
  assert.deepEqual(encryptedKeys({ llm: { baseUrl: 'https://api.deepseek.com.attacker.invalid', apiKeyEnc: 'wrong' } }), {});
});
test('reservations survive restart and missing usage never refunds', async t => {
  const { file, ledger } = fixture(t);
  const id = await ledger.reserve('test', 'synthetic', 0.8);
  await ledger.settle(id, undefined, price);
  await ledger.settle(id, { prompt_tokens: 2 }, price);
  const reopened = new Ledger(file, 1, { test: 1 });
  await assert.rejects(reopened.reserve('test', 'synthetic', 0.21), /budget/);
  await reopened.settle(id, { prompt_tokens: 100, completion_tokens: 10 }, price);
  assert.equal(JSON.parse(readFileSync(file)).entries[0].status, 'metered');
});
test('cross-process reservations cannot overrun a shared cap', async t => {
  const { file } = fixture(t);
  const moduleFile = require.resolve('./budget.cjs');
  const code = `const { Ledger } = require(${JSON.stringify(moduleFile)}); new Ledger(process.argv[1], 1, {test:1}).reserve('test','synthetic',0.4).then(()=>process.exit(0),()=>process.exit(2));`;
  const exits = await Promise.all(Array.from({ length: 5 }, () => new Promise(resolve => {
    const child = spawn(process.execPath, ['-e', code, file], { stdio: 'ignore' }); child.on('exit', resolve);
  })));
  assert.equal(exits.filter(x => x === 0).length, 2);
  assert.equal(JSON.parse(readFileSync(file)).entries.length, 2);
});
test('unexpected usage above reservation locks future calls', async t => {
  const { ledger } = fixture(t);
  const id = await ledger.reserve('test', 'synthetic', 0.00001);
  await ledger.settle(id, { prompt_tokens: 1000, completion_tokens: 10 }, price);
  await assert.rejects(ledger.reserve('test', 'synthetic', 0.001), /budget/);
});
test('stage cap and invalid values fail closed', async t => {
  const { file } = fixture(t);
  const ledger = new Ledger(file, 1, { test: 0.1 });
  await assert.rejects(ledger.reserve('test', 'synthetic', 0.11), /budget/);
  await assert.rejects(ledger.reserve('test', 'synthetic', NaN), /invalid/);
});
async function listen(server) { await new Promise(r => server.listen(0, '127.0.0.1', r)); return `http://127.0.0.1:${server.address().port}`; }

test('query scopes cap calls and reject wrong gateway credentials before charging', async t => {
  const { file, ledger } = fixture(t); let count = 0;
  const upstream = http.createServer((req, res) => { count++; req.resume(); res.end(JSON.stringify({ choices: [], usage: { prompt_tokens: 1, completion_tokens: 1 } })); });
  const base = await listen(upstream);
  const server = gateway({ ledger, stage: 'test', token: 'synthetic', routes: { mock: { base, key: 'synthetic', models: { mock: { resource: 'chat/completions', price } } } } });
  const local = await listen(server);
  t.after(() => { upstream.closeAllConnections(); upstream.close(); server.closeAllConnections(); server.close(); });
  const post = (path, body, key = 'synthetic') => fetch(local + path, { method: 'POST', headers: { Authorization: `Bearer ${key}` }, body: JSON.stringify(body) });
  assert.equal((await post('/_scope', { name: 'query', maxCalls: 1 })).status, 200);
  const request = { model: 'mock', messages: [{ role: 'user', content: 'synthetic' }], max_tokens: 1 };
  assert.equal((await post('/mock/chat/completions', request, 'wrong')).status, 401);
  assert.equal((await post('/mock/chat/completions', request)).status, 200);
  assert.equal((await post('/mock/chat/completions', request)).status, 502);
  assert.equal(count, 1); assert.equal(JSON.parse(readFileSync(file)).entries.length, 1);
});
test('stream usage settles only after DONE; failures and retries retain reservations', async t => {
  const { file, ledger } = fixture(t);
  let mode = 'good', count = 0;
  const upstream = http.createServer((req, res) => {
    count++; req.resume();
    if (mode === 'http') { res.writeHead(429).end('sensitive upstream details'); return; }
    res.writeHead(200, { 'Content-Type': 'text/event-stream' });
    res.write('data: {"choices":[{"delta":{"content":"合成"}}]}\n\n');
    res.write('data: {"usage":{"prompt_tokens":10,"completion_tokens":2}}\n\n');
    res.end(mode === 'good' ? 'data: [DONE]\n\n' : '');
  });
  const base = await listen(upstream);
  const server = gateway({ ledger, stage: 'test', routes: { synthetic: { base, key: 'synthetic-test-key', models: { test: { resource: 'chat/completions', price } } } } });
  const local = await listen(server);
  t.after(() => { upstream.closeAllConnections(); upstream.close(); server.closeAllConnections(); server.close(); });
  const call = async () => {
    const r = await fetch(local + '/synthetic/chat/completions', { method: 'POST', body: JSON.stringify({ model: 'test', messages: [{ role: 'user', content: 'synthetic' }], stream: true, max_tokens: 10 }) });
    return { status: r.status, body: await r.text() };
  };
  await call(); mode = 'truncated'; await call(); mode = 'http'; const failed = await call(); await call();
  assert.equal(count, 4); assert.equal(failed.status, 429); assert.ok(!failed.body.includes('sensitive'));
  assert.deepEqual(JSON.parse(readFileSync(file)).entries.map(x => x.status), ['metered', 'unknown', 'unknown', 'unknown']);
});
test('absent max_tokens uses the ceiling, reasoning overrides are stripped, truncation is recorded', async t => {
  const { file, ledger } = fixture(t); const seen = [];
  const upstream = http.createServer(async (req, res) => {
    let body = ''; for await (const part of req) body += part; seen.push(JSON.parse(body));
    res.end(JSON.stringify({ choices: [{ message: { content: '合成' }, finish_reason: 'length' }], usage: { prompt_tokens: 1, completion_tokens: 1, prompt_cache_hit_tokens: 0 } }));
  });
  const base = await listen(upstream);
  const extra = { thinking: { type: 'disabled' } };
  const server = gateway({ ledger, stage: 'test', routes: { mock: { base, key: 'synthetic', models: { mock: { resource: 'chat/completions', price, extra } } } } });
  const local = await listen(server);
  t.after(() => { upstream.closeAllConnections(); upstream.close(); server.closeAllConnections(); server.close(); });
  const r = await fetch(local + '/mock/chat/completions', { method: 'POST', body: JSON.stringify({ model: 'mock', messages: [{ role: 'user', content: 'synthetic' }], reasoning_effort: 'high', thinking: { type: 'enabled' } }) });
  assert.equal(r.status, 200); await r.text();
  assert.equal(seen[0].max_tokens, 4096); assert.equal(seen[0].reasoning_effort, undefined); assert.deepEqual(seen[0].thinking, extra.thinking);
  const [entry] = JSON.parse(readFileSync(file)).entries;
  assert.equal(entry.status, 'metered'); assert.equal(entry.truncated, true);
});
test('failure limit stops forwarding without new reservations', async t => {
  const { file, ledger } = fixture(t); let count = 0;
  const upstream = http.createServer((req, res) => { count++; req.resume(); res.writeHead(500).end(); });
  const base = await listen(upstream);
  const server = gateway({ ledger, stage: 'test', maxFailures: 2, routes: { mock: { base, key: 'synthetic', models: { mock: { resource: 'chat/completions', price } } } } });
  const local = await listen(server);
  t.after(() => { upstream.closeAllConnections(); upstream.close(); server.closeAllConnections(); server.close(); });
  const statuses = [];
  for (let i = 0; i < 4; i++) {
    const r = await fetch(local + '/mock/chat/completions', { method: 'POST', body: JSON.stringify({ model: 'mock', messages: [{ role: 'user', content: 'synthetic' }], max_tokens: 1 }) });
    statuses.push(r.status); await r.text();
  }
  assert.deepEqual(statuses, [500, 500, 503, 503]); assert.equal(count, 2);
  assert.deepEqual(JSON.parse(readFileSync(file)).entries.map(x => x.status), ['unknown', 'unknown']);
});
