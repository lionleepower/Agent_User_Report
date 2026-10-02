# Experiment 12: KV cache and prefix reuse

**Local and cloud runs complete** (2026-09-30). Local cost: CNY 0 (electricity not measured). Cloud deepseek-flash: CNY 0.376 by usage (97 requests, including 33 marker-length probes); no provider bill was read.

Cloud prefix cache: retrieval (~477 tokens) and whole (~9350 tokens) shapes × stable / token-equal varying prefix × concurrency 1 / 4, 8 requests per condition, 64/64 ok. All 33 markers measured 11 tokens before the run.
- Stable prefixes hit in multiples of 256 tokens after the first request; varying prefixes never hit.
- The first concurrency-1 request missed, so a first request is not guaranteed to miss.
- Hits gave no consistent first-token gain at these sizes; whole-shape input cost fell about 96%.
- This is the provider's billing cache, not KV memory.

Data: [per-condition records](results/cloud.json), the cloud field of the [summary](results/summary.json), and the [figure](../report/figures/12-cloud-cache.svg).

Existing Qwen3-4B-Instruct-2507 Q4_K_M, llama.cpp build 11222, RTX 4060 Laptop. Eight configurations: f16/q8_0, total context 8192/16384, one/two slots. Five independent restarts per configuration. Requests run serially on slot 0; this is not a concurrent throughput benchmark. Generation is capped at 64 tokens and answer quality is not evaluated.

150 successful requests, 30 capacity skips, no runtime failures. The 22k-character pack measures 8635 input tokens and fits only the 16384-token, single-slot configurations with output headroom.

Runtime logs report allocated KV storage of 1152/612 MiB (f16/q8_0, 8192 context), and 2304/1224 MiB (16384 context): 46.875% less allocated storage with q8_0 for this model. Occupied KV bytes are unavailable, recorded as null. GPU device-wide memory is reported separately.

Per-request `timings.cache_n` agrees with the increment in the Prometheus cache counter. No reuse gives zero; shared-prefix requests reuse 535 tokens for short retrieval and 8630 for the whole pack. p95 is the maximum of five observations, not a stable tail estimate.

[Grouped summary](results/summary.json), [individual measurements](results/local.json), [separate preflight](results/preflight-local.json). Answers, logs and GPU time series remain in local run directories. See [Chinese instructions](README.zh-CN.md) for commands. The first formal attempt stopped on mixed-encoding Windows logs; the corrected full rerun is the reported source.
