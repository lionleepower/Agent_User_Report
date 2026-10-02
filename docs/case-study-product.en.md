# Product case study: deciding a knowledge-base design with experiment data

[简体中文](case-study-product.zh-CN.md) · [Home](../README.en.md) · [Full report](../experiments/report/REPORT.en.md)

This is a decision retrospective: should a real-time spoken Q&A product adopt RAG, and what kind? The focus is not technical detail but **how a vague question became testable hypotheses, and how data became product decisions**.

## 1. Users and the problem

**Scenario**: during a conversation, the user receives AI-generated answers they can say out loud right away. Answers draw on material the user imported: a résumé, job descriptions, notes of tens to hundreds of thousands of characters.

**What users care about most**:

| What the user feels | Product metric | Bar |
| --- | --- | --- |
| "If it takes forever to start, it's useless" | Time to first answer token (TTFT) | Within 2 s after the speaker stops; after speech recognition and endpointing, the model gets little more than 1 s |
| "It answered the wrong thing" | Fully-correct rate, wrong-answer rate | Higher is better; a wrong answer hurts more than "not in the material" |
| "Is my material uploaded?" "What does each answer cost?" | Whether material leaves the device; cost per question | No upload by default; cost per question in fractions of a cent |

**The team's choice**: the industry default is "RAG + vector database + agent framework". That stack adds latency, dependency weight and privacy questions. Without data, "should we adopt it?" is a matter of taste.

## 2. Turning the question into testable hypotheses

| ID | Hypothesis | If true, the product… | If false |
| --- | --- | --- | --- |
| H1 | With little material, sending it whole beats retrieval at acceptable cost | Sends whole and raises the whole-pack limit | Adopts retrieval early |
| H2 | Differences between retrieval methods outweigh "whole vs retrieval" | Invests in the retrieval method | Any method will do |
| H3 | Speech-recognition typos hurt keyword retrieval noticeably | Prefers dense retrieval for live speech | BM25 is enough |
| H4 | Small local embedding models are good enough | Defaults to local, no upload | Defaults to cloud with a privacy notice |
| H5 | Mainstream frameworks improve quality | Adopts a framework | Stays hand-written and light |
| H6 | Agent-style "read the table of contents" retrieval (PageIndex) is clearly better | Adopts it | Uses it only where it fits |
| H7 | Caching cuts both cost and latency | Designs prompts around the cache | Treats it as a cost tool only |

## 3. Experiment design: make conclusions trustworthy first

- **Public data**: a public Chinese computer-science note collection, no real user material, so results can be published and reproduced.
- **Let failures show**: the model must "answer only from the material and say so if it's not there". A missed passage becomes a wrong answer instead of being patched by the model's general knowledge.
- **Control variables**: each experiment changes one factor, such as only the retrieval method, only the model, or only the material size.
- **State uncertainty**: dozens of questions per group, every conclusion with a 95% interval, and paired comparisons by question. When an interval crosses 0, the report says "not significant".
- **Control cost**: run a small pilot, project the full cost from measured unit prices, and stop to re-approve before exceeding the budget. Round 2 made 3043 requests for 9.39 CNY against a 20 CNY total budget.

## 4. Results and decisions

| Hypothesis | Key data | Product decision |
| --- | --- | --- |
| H1 holds | Whole-pack accuracy holds at 75% up to 85k characters and only declines past 100k of same-domain material; under 0.01 CNY per question | **Raise the whole-pack limit from 30k to 60k characters**, with headroom |
| H2 holds | Same 200k characters: BM25 46% fully correct, cloud dense 69%; 5 passages beat 3 by 6–12 points | **Move retrieval from 3 to 5 passages**; invest in the method |
| H3 holds | On spoken-style questions, BM25 passage hits fall from 65% to 52%; dense only from 94% to 85% | **Prefer dense retrieval** for live speech |
| H4 holds | Local Qwen3-Embedding essentially ties cloud DashScope (95.8% vs 97.9%) | **Default to local embeddings (bge-small, no upload)**; cloud embeddings upload only after an explicit user click; a Qwen3-Embedding option for GPU users goes on the roadmap |
| H5 fails | Configured frameworks match hand-written code; Chinese defaults barely work; +346 MB of dependencies; the agent loop costs ~15× with no significant gain | **No framework**: keep a few hundred hand-written lines; no agent loop for single-hop Q&A |
| H6 partly holds | PageIndex is clearly more accurate than BM25 and dense, but not significantly different from whole; ~5 s slower and 6–7× costlier per question | **Not for real time**; a candidate for post-meeting review and offline Q&A |
| H7 partly holds | Prefix caching cuts whole-pack input cost by ~96% without consistently faster first tokens | Layer prompts as "stable prefix → material → question" and send a prewarm request before starting; **market the cache as a cost tool, not a latency tool** |

## 5. Trade-offs and risks

- **Accuracy vs speed**: more accurate cloud models (qwen3.8-flash / 3.7-plus) take nearly 3 s to the first token on a whole pack. The decision: fast-first-token models for real time, more accurate models for unhurried tasks (review, writing material), instead of picking one.
- **Privacy vs quality**: cloud embeddings are slightly better but require uploading and cost money. The decision: local by default, cloud by explicit choice, with honest product copy about the difference.
- **Vendor risk**: during the experiments, the provider retired round 1's deepseek-chat. Models must be swappable: the API layer speaks the OpenAI-compatible format, model names and prices live in configuration, and results from different models are never pooled.
- **Evaluation limits**: model-generated questions, a judge from the same vendor as the answerer, small samples, simulated speech noise. Conclusions guide direction under stated conditions; they are not universal truths.

## 6. If I did it again

- Validate on a **small sample of real user material** (with consent) to confirm the public-corpus findings transfer.
- Add **human spot checks of judging** to calibrate the LLM judge.
- Replace simulated noise with **real speech-recognition output**.
- Design an **asynchronous experience** for slow methods like PageIndex from the start (a short answer first, a detailed one after) instead of comparing them only on synchronous first-token latency.

## 7. My role

- Framed the problem and metrics: split "should we adopt RAG?" into 7 testable hypotheses across first-token latency, accuracy, cost and privacy.
- Designed and ran the experiments: 13 experiments with controlled variables, intervals and paired comparisons.
- Managed cost and risk: a total budget with per-stage caps, projections from pilot data, and stopping before overspend.
- Turned data into decisions: two parameter changes shipped directly (whole-pack limit 30k → 60k characters, retrieval 3 → 5 passages), and the data backed two designs: local-first embeddings with cloud on explicit consent, and no framework. Each comes with its evidence and the conditions it holds under.
