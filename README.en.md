# Don't reach for RAG too early

**Measured retrieval, model and framework choices for a personal knowledge base**

[简体中文](README.md) · [Walkthrough](experiments/report/WALKTHROUGH.en.md) · [Full report](experiments/report/REPORT.en.md) · [Beginner handbook](experiments/report/HANDBOOK.en.md) · [Product case study](docs/case-study-product.en.md) · [Engineering highlights](docs/engineering-highlights.en.md)

## In 30 seconds

**The problem**: one of my personal projects does real-time spoken Q&A. When someone finishes a sentence, the program must find relevant content in my own notes and have an AI produce an answer I can say out loud, ideally starting within 2 seconds. So how should the AI "look things up"?

**What I did**: wrote over a hundred questions from a public Chinese technical note collection, then compared 4 ways for the AI to fetch material, 9 answer models, 3 embedding models and 3 mainstream frameworks. Every answer was graded by another AI against reference points.

**Three-line conclusion**:

1. **With little material (up to 60k Chinese characters), handing the AI everything beats every "lookup" method**, and thanks to caching it costs under 0.01 CNY per question.
2. **With more material, searching by meaning (dense retrieval) is far more accurate than searching by keywords**, especially when questions come from speech recognition with typos.
3. **Fancier approaches (letting the AI browse a table of contents, agent frameworks) are somewhat more accurate but add seconds per question**, which rules them out for real time.

![Four ways to fetch material](experiments/report/figures/methods-compare.en.svg)

## Key findings (with numbers)

1. **With little material, sending it whole is the best "retrieval".** Up to 60k characters, just send everything. Accuracy holds at 75% up to 85k characters, prefix-cache hits run 97–98%, and each question costs under 0.01 CNY.
2. **When you retrieve, don't rely on keywords alone.** BM25 gets 46–67% fully correct, dense retrieval 74–96%. Speech-recognition typos cost BM25 another ten-plus points.
3. **Local embedding models are good enough.** On a laptop GPU, Qwen3-Embedding-0.6B ties cloud DashScope: 95.8% vs 97.9% of correct passages found.
4. **PageIndex is a diligent student who reads the table of contents, and is just as slow.** It beats BM25 by 21–33 points and dense retrieval by 17–20, but its difference from sending everything is not significant, and it costs about 5 s more and 6–7× the price per question.
5. **For real time, watch the first token; otherwise, watch accuracy.** Reasoning models think for over a minute first, which rules them out for real time.
6. **Frameworks have no magic.** Configured properly, they match a few hundred lines of hand-written code; their Chinese defaults barely work, and they bring 346 MB of dependencies.
7. **Caching saves money, not necessarily time.** Locally, q8_0 cut KV-cache startup allocation by 46.875%. In the cloud, prefix-cache hits cut whole-pack input cost by about 96%, without consistently faster first tokens.

![PageIndex accuracy vs other methods](experiments/report/figures/11-accuracy.svg)

![Pack size vs accuracy](experiments/report/figures/01-accuracy-vs-size.svg)

## An example: one question, four approaches

Question: "In a 2-D array where each row increases left to right and each column increases top to bottom, how do you efficiently find a target number?" (a real experiment question, adapted from CS-Notes; answers translated from Chinese)

| Approach | Score (0–2) | Answer (excerpt) |
| --- | --- | --- |
| Whole pack | 2 | Start at the top-right corner: go left if the target is smaller, down if larger… O(m+n) |
| BM25 (keywords) | 0 | Not in the material. |
| Dense (meaning) | 0 | The material mentions LeetCode 240 but only gives the problem and an example matrix, not a solution. |
| PageIndex (outline) | 2 | Start at the top-right corner… at most m+n steps |

The question was paraphrased, so keywords didn't match and BM25 found nothing. Dense retrieval found the right section, but what the model saw had only the problem, not the solution. **Finding it isn't the same as answering it.** More real examples (speech typos, cross-section questions) and a detailed card per experiment are in the [walkthrough](experiments/report/WALKTHROUGH.en.md).

## Read by role

| You want | Start with |
| --- | --- |
| To see what was asked, compared and judged | [Walkthrough](experiments/report/WALKTHROUGH.en.md): evaluation flow, real questions and answers, one card per experiment |
| Product thinking: why these decisions | [Product case study: deciding a knowledge-base design with experiment data](docs/case-study-product.en.md) |
| Agent / AI application engineering | [Engineering highlights: budget gateway, integrating a third-party agent SDK, evaluation method](docs/engineering-highlights.en.md) |
| All the data and methods | [Full report](experiments/report/REPORT.en.md) (22 figures) |
| Concepts first, as a newcomer | [Beginner handbook](experiments/report/HANDBOOK.en.md): tokens, RAG, embeddings, agents, GPU memory, KV cache, networking and system design, with everyday analogies |

## How the experiments were run

![The journey of one question](experiments/report/figures/eval-pipeline.en.svg)

- **Questions**: written from passages of public notes, each with 2–4 answer points and the passage holding the answer. Four types: direct, paraphrased, spoken-noise, and cross-section composites.
- **Strict answer rule**: the model may answer only from the material it's given and must say "not in the material" otherwise, so a retrieval miss becomes a wrong answer instead of being hidden by general knowledge.
- **Grading**: another model scores 0 / 1 / 2 against the points; the headline metric is the share scoring 2 (fully correct). Two answers per question are averaged, failures count as wrong, 95% intervals are computed over questions, and methods are compared paired by question.
- **13 experiments**:

| Experiment | Question it answers |
| --- | --- |
| 01 / 01b Pack size | At what size does sending everything slip? What about same-topic material? |
| 02 Frameworks | Do configured LangChain / LlamaIndex beat hand-written code? |
| 03 Speech noise | How much do recognition typos cost retrieval? |
| 04 Chunking / 06 Passages | How to chunk material, and how many passages to give? |
| 07 Answer models | Which of 9 cloud and local models is fast and accurate? |
| 07b Embedding models | Can a small local model replace the cloud? |
| 08 LangGraph | Is it worth letting an agent decide how to retrieve? |
| 09 Concurrency | Does it slow down when many ask at once? |
| 11 PageIndex | Is outline-reading retrieval any good? |
| 12 Caching | How much do the local KV cache and cloud prefix cache save? |

- **Cost control**: a hand-written cross-process budget gateway. Every paid request reserves an upper bound first and settles on reported usage, so SDK-internal calls and retries cannot escape the budget. Round 2 made 3043 requests for 9.39 CNY by usage.
- **Findings shipped and designs backed**: the whole-pack limit rose from 30k to 60k characters; retrieval moved from 3 to 5 passages (+6–12 points fully correct); no framework adopted; local bge embeddings by default, with cloud embeddings only on explicit user consent.

## Repository layout

```
README.md / README.en.md            this page
docs/
  case-study-product.*.md           product view: problem, hypotheses, experiments, decisions, trade-offs
  engineering-highlights.*.md       agent-developer view: budget gateway, SDK integration, evaluation, pitfalls
experiments/
  report/
    WALKTHROUGH.zh-CN.md / .en.md   walkthrough: example questions, real answers, one card per experiment
    REPORT.zh-CN.md / REPORT.en.md  full report
    HANDBOOK.zh-CN.md / .en.md      beginner handbook
    figures/  data/                 all figures (SVG) and plotted data (CSV)
    *.py                            plotting and measurement scripts
  lib/                              budget gateway, ledger, evidence limits, and their tests
  11-pageindex/                     PageIndex comparison: runner, adapter, statistics, results
  12-kv-cache/                      local KV and cloud prefix cache: scripts and results
  01-…/09-…/results/                round-1 experiment summaries
```

## Reproducibility

- The code is a **snapshot** for reading and review. Some scripts depend on internal modules of the original project (the retrieval implementation, the key loader), so they do not run on their own.
- Every figure is generated by the scripts in `experiments/report/` from the experiments' `results/*.json`; each number traces back to a summary file.
- The full question bank, raw answers, judge text and corpus text are not included: they quote the corpus, which has its own license.

## Data and license

- Corpus: the public [CS-Notes](https://github.com/CyC2018/CS-Notes) (by CyC2018, CC BY-NC-SA 4.0) at a pinned commit. This repository contains neither its text nor the full question bank.
- The few example questions, answer points and answer excerpts on this page and in the [walkthrough](experiments/report/WALKTHROUGH.en.md) are adapted from CS-Notes and shared under CC BY-NC-SA 4.0 for non-commercial demonstration only.
- Code is released under the [MIT License](LICENSE).
- Costs are API usage × list price at the time, not provider bills. Models and prices change; conclusions describe the tested conditions only.
