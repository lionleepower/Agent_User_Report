# Experiment 11: PageIndex comparison

**Complete** (2026-09-30, deepseek-flash non-thinking; not pooled with historical deepseek-chat). Controlled: 864/864 answers succeeded; official native: 23/24. This experiment cost CNY 9.02 by usage (experiment 12 cloud excluded); no provider bill was read.

| Questions | Whole | BM25 | Dense | PageIndex |
| --- | --- | --- | --- | --- |
| Clean (48) | 76.0% | 58.3% | 62.5% | 79.2% |
| Noisy (48) | 69.8% | 44.8% | 58.3% | 78.1% |
| Multi-hop (12, exploratory) | 83.3% | 50.0% | 83.3% | 100% (native 91.7%) |

Values are fully-correct rates. PageIndex beat BM25 by 20.8 / 33.3 points and dense by 16.7 / 19.8 (clean / noisy), with paired intervals excluding 0. Against whole it was +3.1 / +8.3, with intervals crossing 0, so the difference is not significant. End-to-end p50: PageIndex 6.4 s, whole 1.1 s. Per-question cost: PageIndex CNY 0.028, whole 0.004 (prefix-cache hit). Index builds: PageIndex 18.3 s / CNY 0.059; vectors 23.5 s / CNY 0.039.

See [report section 4.3](../report/REPORT.en.md#43-pageindex-the-student-who-reads-the-table-of-contents-round-2) and the [summary](results/summary.json) (runs, intervals, paired differences, amortization, cost by stage). Per-run records: [main](results/main.json), [multi](results/multi.json), [native](results/native.json), [pilot](results/preflight.json), [compatibility](results/compatibility.json), [index](results/index.json), [vectors](results/embeddings.json). Statistics: [stats.ts](stats.ts), [summarize.ts](summarize.ts).

The pinned public CS-Notes corpus passes the manifest check (170 documents). M tier: 37 documents, 200347 characters; 48 clean/noisy question pairs. Twelve cross-section composite questions (question text not included in this repository) have been checked against public evidence by the assistant; they are not an independently human-labelled multi-hop benchmark.

The local text PDF has 136 pages and 637 chunk/page mappings. Extracted text exactly matches the source after whitespace normalization. Pages 1, 69 and 136 were visually checked. Text, PDF, index and raw answers remain local.

The user approved the [26-wheel manifest](dependency-manifest.json), 48002472 bytes. All wheels were fetched over IPv4, SHA-256 verified and installed into an isolated overlay without changing the existing venv. PageIndex 0.2.10 imports successfully. No models were downloaded. All paid requests must use the shared budget gateway.
