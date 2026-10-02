# 实验目录

[English](README.md) · [返回首页](../README.md) · [完整报告](report/REPORT.zh-CN.md)

两轮共 13 组实验。第一轮的回答和评分模型是 deepseek-chat（后来已下线），第二轮是 deepseek-flash（关闭思考），两轮数据不合并比较。

| 实验 | 问题 | 报告章节 | 结果 |
| --- | --- | --- | --- |
| 01 资料规模 | 整包能撑多大？加入无关文档扩容 | 第 3 节 | [summary](01-context-threshold/results/summary.json) |
| 01b 同主题扩容 | 干扰项和答案很像时呢？ | 第 3 节 | [设计模式](01b-same-topic/results/summary.json)、[Java](01b-same-topic/results/summary-java.json) |
| 02 框架 | LangChain / LlamaIndex 配好后能比手写好吗？ | 第 8 节 | [summary](02-frameworks/results/summary.json) |
| 03 语音噪声 | 识别错字对各检索方法的影响 | 第 5 节 | [summary](03-asr-noise/results/summary.json) |
| 04 切段 | 按标题还是固定长度？切多大？ | 4.2 节 | [summary](04-chunking/results/summary.json) |
| 06 每次给几段 | 3 / 5 / 8 段 | 4.2 节 | [summary](06-context-budget/results/summary.json) |
| 07 回答模型 | 云端 4 个、本地 5 个模型 | 第 6 节 | [summary](07-models/results/summary.json) |
| 07b 向量模型 | bge-small / Qwen3-Embedding / DashScope | 第 7 节 | [summary](07b-embeddings/results/summary.json) |
| 08 LangGraph | Agent 循环值不值 | 第 8 节 | [summary](08-langgraph/results/summary.json) |
| 09 并发 | 多人同时问会怎样 | 第 10 节 | [summary](09-concurrency/results/summary.json) |
| 11 PageIndex | 目录树检索 vs 整包 / BM25 / 向量 | 4.3 节 | [说明](11-pageindex/README.zh-CN.md)、[summary](11-pageindex/results/summary.json) |
| 12 KV cache | 本地 KV 量化与复用、云端前缀缓存 | 第 9 节 | [说明](12-kv-cache/README.zh-CN.md)、[summary](12-kv-cache/results/summary.json) |

## 代码快照

只包含关键的实验代码，用于阅读和审查：

- [`lib/`](lib/)：预算网关、持久账本、证据裁剪，以及它们的测试；
- [`11-pageindex/`](11-pageindex/)：运行器、PageIndex 适配器、统计、汇总、PDF 生成；
- [`12-kv-cache/`](12-kv-cache/)：本地 llama.cpp KV 实验、云端缓存实验、汇总；
- [`report/`](report/)：全部绘图脚本和 API 耗时测量脚本；
- [`02-frameworks/pipelines.py`](02-frameworks/pipelines.py)、[`08-langgraph/agent.py`](08-langgraph/agent.py)：第一轮用 LangChain / LlamaIndex / LangGraph 重建检索流程的脚本（小白手册第 7 章引用）。

部分脚本依赖原项目的内部模块（检索实现、语料加载、密钥读取工具），这些模块没有包含在这里，所以快照不能单独运行。本地数据目录名已做通用化处理。

## 没有包含的内容

- 语料正文、由语料生成的题目和答案要点（语料许可为 CC BY-NC-SA 4.0）；
- 模型的原始回答、评分原文、PDF、索引和工具调用轨迹（都会引用语料原文）；
- 原项目的应用代码和开发日志。
