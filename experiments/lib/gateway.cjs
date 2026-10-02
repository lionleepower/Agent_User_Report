// One loopback gateway for Node/Python and SDK calls. No automatic retries.
const http = require('node:http');
const https = require('node:https');
const { StringDecoder } = require('node:string_decoder');
const { Ledger } = require('./budget.cjs');
function gateway({ ledger, routes, stage, token, maxFailures = 5 }) {
  // Upstream failures keep unknown reservations; SDK retry loops must not
  // multiply them, so this process stops forwarding after maxFailures.
  let scope, failures = 0;
  return http.createServer(async (req, res) => {
    let ticket;
    try {
      const url = new URL(req.url, 'http://localhost');
      if (token && req.headers.authorization !== `Bearer ${token}`) { res.writeHead(401).end(); return; }
      if (req.method === 'POST' && url.pathname === '/_scope') {
        let body = ''; for await (const part of req) body += part;
        const s = JSON.parse(body);
        if (s.name === null) scope = undefined;
        else {
          if (typeof s.name !== 'string' || s.name.length > 80 || !Number.isInteger(s.maxCalls) || s.maxCalls < 1 || s.maxCalls > 6) throw Error('invalid scope');
          scope = { calls: 0, max: s.maxCalls, deadline: Date.now() + 120000 };
        }
        res.writeHead(200).end('{}'); return;
      }
      const route = routes[url.pathname.split('/')[1]];
      const resource = url.pathname.split('/').slice(2).join('/');
      if (req.method !== 'POST' || !route || !['chat/completions', 'embeddings'].includes(resource)) { res.writeHead(404).end(); return; }
      const parts = []; let bytes = 0;
      for await (const b of req) { parts.push(b); bytes += b.length; if (bytes > 4000000) throw Error('request too large'); }
      const body = Buffer.concat(parts).toString('utf8');
      const j = JSON.parse(body);
      const spec = route.models[j.model];
      if (!spec || spec.resource !== resource) throw Error('unpriced or disallowed model');
      if (resource === 'chat/completions') {
        if (!Array.isArray(j.messages)) throw Error('messages required');
        for (const m of j.messages) {
          if (Array.isArray(m.content) && m.content.every(p => p.type === 'text' && typeof p.text === 'string')) m.content = m.content.map(p => p.text).join('\n');
          if (typeof m.content !== 'string' && m.content !== null) throw Error('only text messages permitted');
        }
        // SDK indexing calls send no max_tokens; a small default would silently
        // truncate official summaries/JSON, so absent means the 4096 ceiling.
        j.max_tokens = Math.min(j.max_tokens ?? j.max_completion_tokens ?? 4096, 4096);
        if (!Number.isInteger(j.max_tokens) || j.max_tokens < 1) throw Error('invalid max_tokens');
        delete j.max_completion_tokens;
        // Only the priced extra (e.g. thinking disabled) decides reasoning mode.
        delete j.reasoning_effort; delete j.reasoning;
        if (j.stream) j.stream_options = { include_usage: true };
        if (spec.extra) Object.assign(j, spec.extra);
      }
      const data = JSON.stringify(j);
      if (!route.key) throw Error('key missing');
      if (failures >= maxFailures) throw Error('gateway failure limit reached');
      if (scope) {
        if (scope.calls >= scope.max || Date.now() >= scope.deadline) throw Error('query call/time limit reached');
        scope.calls++;
      }
      const inputUpper = Buffer.byteLength(data, 'utf8') + 4096;
      const upper = (inputUpper * spec.price.miss + (j.max_tokens ?? 0) * spec.price.out) / 1e6;
      ticket = await ledger.reserve(stage, j.model, upper);
      const target = new URL(route.base.replace(/\/+$/, '') + '/' + resource);
      const transport = target.protocol === 'https:' ? https : http;
      await new Promise((resolve, reject) => {
        const upstream = transport.request(target, { method: 'POST', family: 4, headers: { Authorization: `Bearer ${route.key}`, 'Content-Type': 'application/json' }, timeout: 120000 }, async r => {
          if (r.statusCode !== 200) { failures++; r.resume(); res.writeHead(r.statusCode ?? 502).end(JSON.stringify({ error: 'upstream rejected request' })); resolve(); return; }
          res.writeHead(200, { 'Content-Type': r.headers['content-type'] ?? 'application/json' });
          let buffer = '', usage, done = false, finish;
          const decoder = new StringDecoder('utf8');
          try {
            for await (const chunk of r) {
              buffer += decoder.write(chunk);
              if (j.stream) {
                let nl;
                while ((nl = buffer.indexOf('\n')) >= 0) {
                  const line = buffer.slice(0, nl).trim(); buffer = buffer.slice(nl + 1);
                  if (line.startsWith('data:')) {
                    const payload = line.slice(5).trim();
                    if (payload === '[DONE]') done = true;
                    else { const event = JSON.parse(payload); if (event.usage) usage = event.usage; finish = event.choices?.[0]?.finish_reason ?? finish; }
                  }
                }
              }
              res.write(chunk);
            }
            buffer += decoder.end();
            if (!j.stream) { const whole = JSON.parse(buffer); usage = whole.usage; finish = whole.choices?.[0]?.finish_reason; done = true; }
            if (resource === 'embeddings' && usage && Number.isInteger(usage.prompt_tokens)) usage = { ...usage, completion_tokens: 0 };
            const settled = done ? await ledger.settle(ticket, usage, spec.price, { truncated: finish === 'length' }) : false;
            if (!settled) failures++;
            res.end(); resolve();
          } catch (e) { res.destroy(); reject(e); }
        });
        upstream.on('timeout', () => upstream.destroy(Error('upstream timeout')));
        // Socket timeout is idle-only; enforce a wall-clock deadline as well.
        const remaining = scope ? Math.max(1, scope.deadline - Date.now()) : 120000;
        const wallTimer = setTimeout(() => upstream.destroy(Error('query wall-clock limit')), Math.min(120000, remaining));
        upstream.on('close', () => clearTimeout(wallTimer));
        upstream.on('error', reject);
        req.on('aborted', () => upstream.destroy(Error('client aborted')));
        upstream.end(data);
      });
    } catch (e) {
      if (ticket) failures++;
      if (/failure limit/.test(e.message) && !res.headersSent) { res.writeHead(503, { 'Content-Type': 'application/json' }).end(JSON.stringify({ error: 'gateway failure limit reached' })); return; }
      if (!res.headersSent) res.writeHead(/budget/.test(e.message) ? 402 : 502, { 'Content-Type': 'application/json' }).end(JSON.stringify({ error: /budget/.test(e.message) ? 'budget insufficient' : 'gateway request failed' }));
      else res.destroy();
    }
  });
}
module.exports = { gateway, Ledger };
