# Experiments

[简体中文](README.zh-CN.md) · [Home](../README.en.md) · [Full report](report/REPORT.en.md)

Thirteen experiments in two rounds. Round 1 answered and judged with deepseek-chat (since retired); round 2 used deepseek-flash with thinking disabled. The two rounds are never pooled.

| Experiment | Question | Report section | Results |
| --- | --- | --- | --- |
| 01 Pack size | How far does sending everything go? Grown with unrelated documents | 3 | [summary](01-context-threshold/results/summary.json) |
| 01b Same-topic growth | What if distractors look like the answers? | 3 | [design patterns](01b-same-topic/results/summary.json), [Java](01b-same-topic/results/summary-java.json) |
| 02 Frameworks | Do configured LangChain / LlamaIndex beat hand-written code? | 8 | [summary](02-frameworks/results/summary.json) |
| 03 Speech noise | How recognition typos affect each retrieval method | 5 | [summary](03-asr-noise/results/summary.json) |
| 04 Chunking | By heading or fixed length? How big? | 4.2 | [summary](04-chunking/results/summary.json) |
| 06 Passages per answer | 3 / 5 / 8 passages | 4.2 | [summary](06-context-budget/results/summary.json) |
| 07 Answer models | 4 cloud and 5 local models | 6 | [summary](07-models/results/summary.json) |
| 07b Embedding models | bge-small / Qwen3-Embedding / DashScope | 7 | [summary](07b-embeddings/results/summary.json) |
| 08 LangGraph | Is an agent loop worth it? | 8 | [summary](08-langgraph/results/summary.json) |
| 09 Concurrency | What happens when many ask at once? | 10 | [summary](09-concurrency/results/summary.json) |
| 11 PageIndex | Table-of-contents retrieval vs whole / BM25 / dense | 4.3 | [notes](11-pageindex/README.md), [summary](11-pageindex/results/summary.json) |
| 12 KV cache | Local KV quantization and reuse, cloud prefix cache | 9 | [notes](12-kv-cache/README.md), [summary](12-kv-cache/results/summary.json) |

## Code snapshot

Only key experiment code is included, for reading and review:

- [`lib/`](lib/): budget gateway, persistent ledger, evidence limits, and their tests;
- [`11-pageindex/`](11-pageindex/): runner, PageIndex adapter, statistics, summarizer, PDF builder;
- [`12-kv-cache/`](12-kv-cache/): local llama.cpp KV experiment, cloud cache experiment, summarizer;
- [`report/`](report/): all plotting scripts and the API timing probe;
- [`02-frameworks/pipelines.py`](02-frameworks/pipelines.py), [`08-langgraph/agent.py`](08-langgraph/agent.py): the round-1 scripts that rebuilt retrieval in LangChain / LlamaIndex / LangGraph (cited in handbook chapter 7).

Some scripts depend on internal modules of the original project (the retrieval implementation, corpus loader and key loader) that are not included, so the snapshot does not run on its own. Local data directory names have been made generic.

## Not included

- Corpus text, and questions and answer points derived from it (the corpus is CC BY-NC-SA 4.0);
- Raw model answers, judge text, PDFs, indexes and tool traces (all quote the corpus);
- The original project's application code and development logs.
