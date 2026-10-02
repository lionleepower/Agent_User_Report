# Experiment walkthrough: what was asked, compared, judged and concluded

[简体中文](WALKTHROUGH.zh-CN.md) · [Full report](REPORT.en.md) · [Beginner handbook](HANDBOOK.en.md)

This document answers the questions an interviewer asks first: **What exactly did you ask? Which approaches did you compare, and what are they like? How did you decide right from wrong? What do you recommend?** It starts with the evaluation flow and real examples, then gives one card per experiment.

> Example questions, answer points and gold passages are adapted from the public notes [CS-Notes](https://github.com/CyC2018/CS-Notes) (by CyC2018, CC BY-NC-SA 4.0); model answers are excerpts of raw experiment output. The examples are shared under the same license for non-commercial demonstration only; the full question bank is not included. The corpus and questions are in Chinese; English glosses and answer translations are added for reading.

## 1. How one question is evaluated

![The journey of one question](figures/eval-pipeline.en.svg)

In plain words:

1. **Prepare a question**: write it from one passage of the notes, and record "which passage holds the answer" plus 2–4 "answer points".
2. **Fetch material for the model**: this is the step being compared. The whole pack hands over everything; BM25, dense retrieval and PageIndex each pick a few passages.
3. **Let the model answer**: under a strict rule: answer only from the given material, and if it isn't there, say "not in the material". So "fetched the wrong material" turns straight into "wrong answer" instead of being covered up by the model's general knowledge.
4. **Let another model grade**: 0, 1 or 2 points against the answer points. The headline metric is the "fully correct" rate, the share scoring 2.
5. **Do the statistics**: average the two answers per question, count failures as wrong, compute intervals, and check whether a difference between two approaches is real.

### What the questions look like

| Type | Example question | Answer points (excerpt) | Gold passage |
| --- | --- | --- | --- |
| Direct | TCP/IP 体系结构跟 OSI 分层有什么不一样？ (How does TCP/IP layering differ from OSI?) | Only four layers; data link and physical layers merged into a network interface layer; doesn't strictly follow OSI layering | Network architecture › TCP/IP |
| Paraphrased | 在单向链表里删掉一个指定节点，怎么做到平均情况下不用从头遍历就能完成？ (How do you delete a given node from a singly linked list without walking from the head, on average?) | If it's not the tail, copy the next node's value and delete the next node, O(1); if it is the tail, walk from the head, O(N) | Delete a list node in O(1) › approach |
| Spoken noise | 嗯 那个踢西批 ip 体系结构跟 哦艾斯艾 分层有什么不一样 (the direct question as speech recognition might render it: "TCP" → "tee-see-pee", "OSI" → "oh-ess-eye", plus fillers) | Same as the direct one | Same |
| Cross-section | 结合反射与永久代章节，解释 JDK 1.7 及以前大量动态加载类时，Class 信息怎样产生、为何可能触发 Full GC，以及资料给出的处理办法。 (Using the reflection and PermGen sections: in JDK ≤ 1.7, when many classes load dynamically, how is Class information created, why can it trigger Full GC, and what fix does the material give?) | Every class has a Class object; classes load on first use; PermGen stores Class info; many classes can fill PermGen; without CMS, Full GC runs; enlarge PermGen or switch to CMS | Two passages: "Java basics › Reflection" and "Full GC triggers › PermGen out of space" |

Paraphrased questions deliberately avoid the source's words (the source says "delete a list node", the question says "remove a given node"), to test whether retrieval understands the same meaning said differently. Spoken-noise questions simulate speech-recognition typos, transliterations and fillers.

### One question, four approaches (real output)

**Example 1: an easy direct question, everyone gets it right**

Question: "How does TCP/IP layering differ from OSI?"

| Approach | Score | Answer (translated excerpt) |
| --- | --- | --- |
| Whole | 2 | TCP/IP has only four layers, merging the data link and physical layers of the five-layer model into a network interface layer… |
| BM25 | 2 | Almost word for word the same |
| Dense | 2 | Same |
| PageIndex | 2 | Same |

The question's words almost match the source, so every approach finds it. Easy questions don't separate the approaches.

**Example 2: spoken noise defeats keyword retrieval**

Question (spoken version): "Um, so, what's actually the difference between 互连网 (an internetwork) and 互联网 (the Internet)? I mean, people mix the two words up but they seem different, can you explain?"

| Approach | Score | Answer (translated) |
| --- | --- | --- |
| Whole | 2 | An internetwork connects many different networks, a network of networks; the Internet is the global internetwork. |
| BM25 | **0** | Not in the material. |
| Dense | 2 | An internetwork connects many different networks, a network of networks; the Internet is the global internetwork. |
| PageIndex | 2 | Same as whole |

BM25 didn't find the passage, most likely because the fillers ("um, so, I mean") diluted the keywords; dense retrieval searches by meaning and found it anyway.

**Example 3: finding "half" still isn't enough**

Question (paraphrased): "In a 2-D array where each row increases left to right and each column increases top to bottom, how do you efficiently find a target number?"

| Approach | Score | Answer (translated excerpt) |
| --- | --- | --- |
| Whole | 2 | Start at the top-right corner: go left if the target is smaller, down if larger… O(m+n) |
| BM25 | **0** | Not in the material. |
| Dense | **0** | The material mentions LeetCode 240 (search a sorted matrix) but only gives the problem and an example matrix, not a solution. |
| PageIndex | 2 | Start at the top-right corner… at most m+n steps |

The records show dense retrieval did put the gold passage into the evidence, yet what the model saw contained only "the problem and the example", not the solution (the solution may have been cut by the 2000-character evidence limit, or sits in a neighboring chunk). So the model honestly said "no solution given". **Finding the right passage is not the same as answering correctly.** PageIndex reads by page and got the full content this time.

**Example 4: so many typos that only the outline reader got it**

Question (spoken version): a question about "the LeetCode problem that splits linked-list nodes by position, odd positions first, then even", where speech recognition turned "linked list" (单链表) and "odd positions" (奇数位) into look-alike nonsense (单练表, 鸡数位, roughly "single-practice list" and "chicken-number positions").

| Approach | Score | Answer (translated) |
| --- | --- | --- |
| Whole | **0** | Not in the material. |
| BM25 | **0** | Not in the material |
| Dense | **0** | Not in the material |
| PageIndex | 2 | Input 1->2->3->4->5->NULL returns 1->3->5->2->4->NULL. |

Even the whole pack, with everything in front of it, didn't recognize the question. PageIndex got it right, presumably because it reads the outline first and matched a heading like "Linked lists › Group elements by odd/even position". This is one question; it doesn't show PageIndex is generally more robust to typos.

**Example 5: a cross-section question answered halfway scores 1**

For the cross-section question in the table above, the first answers were:

| Approach | Score | Why |
| --- | --- | --- |
| Whole | 1 | Explained PermGen and Full GC, but not how Class objects are created or how reflection loads classes |
| BM25 | 2 | Covered both sections |
| Dense | 1 | Like whole, only the PermGen half |
| PageIndex | 2 | Covered both sections |

1 point means "covered only part of the points". There are only 12 such questions, so treat their conclusions as indicative.

## 2. The four ways to fetch material, and recommendations

![Four ways to fetch material](figures/methods-compare.en.svg)

**How to choose**: up to 60k characters, send everything; beyond that, use dense retrieval (hybrid with BM25 as a fallback); PageIndex is accurate but about 5 s slower per question, so keep it for unhurried use.

## 3. One card per experiment

Every card follows the same order: what we wanted to know → what was compared → how → results → recommendation. Round 1 answered and judged with deepseek-chat (since retired); round 2 used deepseek-flash. The two rounds' numbers are never compared directly.

### Experiment 01: how big can the whole pack get?

- **Question**: if you send all the material to the model, at what size does it start to slip?
- **Compared**: whole pack, BM25, local bge hybrid retrieval, cloud DashScope dense retrieval.
- **How**: 44 questions whose answers sit in the first 8 documents; documents on other topics keep being added, growing the material from 22k to 129k characters; every size and method answers twice (88 answers per cell).
- **Results**: whole stays at 75% up to 85k characters and drops to 69% at 129k, with wrong answers rising from 2–5% to 10%; DashScope scores 76–77% at every size with no wrong answers; BM25 stays at 46–47%.
- **Recommendation**: send whole up to 60k characters; the project raised its whole-pack limit from 30k to 60k accordingly.

![Accuracy vs pack size](figures/01-accuracy-vs-size.svg)

### Experiment 01b: what if all the material is on one topic?

- **Question**: experiment 01 added unrelated documents, which doesn't make retrieval harder. What if the additions look alike?
- **How**: 26 identically structured design-pattern notes (23k → 69k characters, 22 questions); 5 Java notes (35k → 124k characters, 54 questions).
- **Results**: design patterns: whole and DashScope both hold 95.5%, BM25 falls from 59% to 50%. Java: whole 74% → 70%, DashScope steady at 76–78%, local bge hybrid 72% → 63%.
- **Recommendation**: past 100k characters of same-domain material, switch to good dense retrieval.

### Experiment 02: are LangChain and LlamaIndex better?

- **Question**: can mainstream frameworks beat a few hundred lines of hand-written code?
- **Compared**: the same 200k-character material and 48 questions, rebuilt with LangChain and LlamaIndex at default and tuned settings, against the hand-written implementation.
- **Results**:
  - Both frameworks' default BM25 splits on spaces, which fails on Chinese: only 27% of correct passages found. One line of Chinese segmentation lifts LangChain to 81%.
  - Tuned, LangChain dense reaches 67% and LlamaIndex 77%, in the same range as hand-written (69%); their lead comes mostly from sending the model more text.
  - The two frameworks plus dependencies are 103 Python packages, 346 MB.
- **Recommendation**: fine for Python prototypes; for desktop apps and latency-sensitive products, hand-written code fits better.

### Experiment 03: how much do speech-recognition typos hurt?

- **Question**: when questions come from speech recognition, how much do typos and transliterations cost retrieval?
- **How**: 48 questions rewritten to look like recognition output (see examples 2 and 4).
- **Results**: correct passage found: BM25 65% → 52%, local bge hybrid 88% → 79%, DashScope 94% → 85%. Fully correct end to end: BM25 38%, DashScope 60%.
- **Recommendation**: use dense retrieval for live speech; put both Chinese and English spellings of terms in headings.

### Experiment 04: how should material be chunked?

- **Compared**: chunk by heading vs fixed length; 200 / 400 / 800 / 1200 characters per chunk. Measured only whether the correct passage made the top 3.
- **Results**: chunking by heading is clearly better (DashScope 85% vs 79%); 200 characters is worst; dense retrieval does better on bigger chunks (85% → 92% → 96%), with overlapping intervals.
- **Recommendation**: chunk by heading, starting around 400 characters.

### Experiment 06: how many passages per answer?

- **Compared**: 3, 5 or 8 passages per answer.
- **Results**: 5 beat 3 by 6–12 points fully correct; 8 brings no consistent gain and delays the first token by about 0.1 s.
- **Recommendation**: 5 passages, at most 3 per document; the project moved from 3 to 5 accordingly.

### Experiment 07: which answer model?

- **Compared**: 4 cloud models (deepseek-chat, qwen3.8-flash, qwen3.7-plus, qwen3-8b) and 5 local ones (Qwen3 1.7B / 4B / 8B, Apertus-8B, a reasoning model).
- **Results (excerpt)**:

| Model | Fully correct (retrieval) | First answer token (retrieval) | Character |
| --- | --- | --- | --- |
| deepseek-chat (retired) | 70.8% | 0.69 s | Fast; no slowdown at 16 concurrent streams |
| qwen3.8-flash | 85.4% | 1.1 s | More accurate, but ~3 s to first token on the whole pack |
| Local Qwen3-4B Q4_K_M | 66.7% | 0.27 s | Runs on an 8 GB card, free |
| Local R1-distill reasoning model | 70% | 96 **s** | Thinks for over a minute first; unfit for real time |

- **Recommendation**: fast-first-token models for real time; more accurate models for unhurried tasks (review, writing material); a local 4B model offline.

### Experiment 07b: which embedding model?

- **Compared**: bge-small (CPU, 24 MB), Qwen3-Embedding-0.6B (local GPU), DashScope (cloud).
- **Results**: correct passage found 83.3% / 95.8% / 97.9%; under speech noise 77.1% / 91.7% / 91.7%.
- **Recommendation**: with a GPU, Qwen3-Embedding matches the cloud for free and offline; without one, bge-small hybrid with BM25.

### Experiment 08: is it worth letting an agent decide how to retrieve?

- **Compared**: an agent built from LangGraph's official tutorial (decide whether to retrieve → judge relevance → rewrite the question and retry if irrelevant → answer) vs single retrieval.
- **Results**: only about 4 points more fully correct, within the interval; rewriting triggered on just 2–4% of questions; 3 model calls per question, over 5 s end to end, about 15× the cost.
- **Recommendation**: single-hop Q&A doesn't need an agent loop.

### Experiment 09: what happens when many ask at once?

- **Results**: deepseek-chat kept its first token at 0.6–0.8 s from 1 to 16 concurrent streams; qwen3.8-flash rose from 1.3 to 2.5 s; 4 local slots carry about 4 real-time streams, and 8 start queuing.
- **Recommendation**: for a shared team service, pick a concurrency-insensitive cloud model; plan local concurrency by slot count.

### Experiment 11: is PageIndex (outline-reading retrieval) any good?

- **Compared**: whole, BM25, dense and PageIndex with the same answer model; retrieval methods capped at 5 passages and 2000 characters. 48 clean, 48 spoken and 12 cross-section questions, each answered twice: 864 answers, plus 24 with the official native flow.
- **Results**:

![PageIndex accuracy](figures/11-accuracy.svg)

  - PageIndex beats BM25 by 21–33 points and dense by 17–20, with intervals excluding 0: a real difference;
  - against whole it's only 3–8 points higher, with intervals crossing 0: **no telling which is better**;
  - the price: about 4 requests, 6.4 s and 0.028 CNY per question, vs 1 request, 1.1 s and 0.004 CNY for whole.
- **Recommendation**: not for real time; worth considering for offline Q&A and review.

### Experiment 12: how much does caching save?

- **Local**: switching the KV cache from f16 to q8_0 cuts its startup VRAM allocation by 46.875%; with a shared prefix, short requests' first token drops from about 0.2 s to about 0.04 s.
- **Cloud**: once requests with an identical start hit the cache, whole-pack input cost falls by about 96%, but the first token doesn't get consistently faster.
- **Recommendation**: put stable prompt content first and the changing question last; send a small prewarm request before starting.

### Bonus: letting an AI write your material

- **What**: a "material-writing prompt" for external AI assistants, tested for three rounds on two real job descriptions.
- **Results**: none of the six packs invented experience; coverage improved with each rule revision (whole-pack fully correct 20% → 37% and 43% → 60%); "add a keyword line after each section" didn't help and was dropped.

## 4. Limits of these conclusions

- 22–54 questions per group: ignore differences of a point or two;
- questions, answers and grading all come from the same vendor's models, with no human review of grading;
- speech noise is simulated by a model, not real recordings;
- only Chinese technical notes, one 8 GB laptop GPU and one network were tested;
- models and prices change; conclusions describe the tested conditions only.

More detail in the [full report](REPORT.en.md).
