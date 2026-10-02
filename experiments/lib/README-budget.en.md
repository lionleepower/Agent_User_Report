# Budget gateway and persistent ledger

[简体中文](README-budget.zh-CN.md) · [Engineering highlights](../../docs/engineering-highlights.en.md)

Every paid request in round 2 went through this code. The design is explained in [section 1 of the engineering highlights](../../docs/engineering-highlights.en.md).

## Files

| File | Role |
| --- | --- |
| `budget.cjs` | Persistent ledger: cross-process directory lock, atomic writes, reserve and settle, stage caps |
| `gateway.cjs` | Local gateway: auth, model allowlist, `max_tokens` cap, reserve → forward → settle, stream parsing, failure breaker |
| `with-budget.cjs` | Starts the gateway and runs the experiment child; the child gets a temporary token, never the real keys |
| `prices.json` | Verified model prices (CNY per million tokens) and thinking-mode settings |
| `evidence.cjs` | Evidence trimming: at most 5 units, 3 per document, 2000 characters |
| `infrastructure.node.cjs`, `evidence.node.cjs` | Native Node tests |

## Rules

- **Reservation bound**: input tokens are bounded by "request UTF-8 bytes + 4096" (with byte-level tokenizers, tokens never exceed bytes) at the uncached price; output by the enforced `max_tokens`. Only text messages and models in the price table are allowed.
- **Settlement**: usage is settled only when the response carries valid usage and, for streams, `[DONE]` arrived. Missing usage, HTTP errors, truncated streams and unfinished requests keep their full reservation. A reservation is not a charge, but it is never treated as free.
- **Retries**: the gateway itself never retries; each retry reserves again. After 5 upstream failures in one gateway process it returns 503 and stops forwarding.
- **Defaults**: with no `max_tokens`, the 4096 ceiling applies so SDK output isn't silently truncated, and `finish_reason=length` is recorded in the ledger. Caller-supplied `reasoning_effort` / `reasoning` are stripped; thinking mode comes only from the price table.
- **Limits**: a 20 CNY total, plus per-stage caps that can't borrow from each other. Cap changes are recorded in the ledger's `capHistory`.
- **Recovery**: the lock never expires on a timer, so two processes can't both hold it. After a crash, check running processes and the ledger before recovering. The ledger holds no prompts, answers, keys or error bodies.

## Tests

Ten tests cover provider-bound keys, no refunds on missing usage and recovery after restart, concurrent processes not overspending, locking on anomalous usage, stage caps, stream truncation and failed retries, the default `max_tokens` and thinking parameters, the failure breaker, and evidence limits (count, per document, total length, deduplication).

```
node --test experiments/lib/infrastructure.node.cjs experiments/lib/evidence.node.cjs
```

(`infrastructure.node.cjs` imports the original project's key-loader module at the top, which is not included here; to run it on its own, remove that import and the first test. `evidence.node.cjs` runs as is.)
