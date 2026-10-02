# 小资料先别急着上 RAG

**个人知识库的检索、模型与框架实测**

[English](README.en.md) · [完整报告](experiments/report/REPORT.zh-CN.md) · [小白手册](experiments/report/HANDBOOK.zh-CN.md) · [产品案例](docs/case-study-product.zh-CN.md) · [工程亮点](docs/engineering-highlights.zh-CN.md)

我的一个个人项目要做实时语音问答：对方说完一句话，程序从我自己的资料里找出相关内容，让大模型生成一段能直接说出口的回答。说完两秒还没出字，这个回答就没用了，所以对**延迟、成本和准确率**都很敏感。

市面上的建议几乎都是“上 RAG、上向量库、上 Agent 框架”。我想用数据回答几个更朴素的问题：

- 资料多大时，才真的需要检索？
- 用哪种检索？关键词、向量，还是让模型自己翻目录（PageIndex）？
- LangChain、LlamaIndex、LangGraph 这些框架值不值得引入？
- 本地小模型、量化、KV cache、前缀缓存，到底能省多少钱、多少时间？

于是用公开的中文技术笔记做了两轮共 13 组可复现实验。

## 核心结论

1. **资料不多时，整包发给模型就是最好的“检索”。** 6 万字以内放心整包，8.5 万字以内答对率不变（75%），前缀缓存命中 97–98%，每题不到一分钱。
2. **检索时别只靠关键词。** BM25 完全正确 46–67%，向量检索 74–96%；语音识别的错字还会让 BM25 再掉十几个点。
3. **本地向量模型已经够用。** Qwen3-Embedding-0.6B 在笔记本显卡上和云端 DashScope 打成平手（找对段落 95.8% vs 97.9%）。
4. **PageIndex 像认真翻目录的好学生，也像好学生一样慢。** 比 BM25 高 21–33 个百分点、比向量高 17–20 个百分点，但和整包差异不显著，每题多花约 5 秒、贵 6–7 倍。
5. **实时场景看首字，非实时场景看准确。** 推理模型会先“想”一分多钟，不适合实时。
6. **框架没有魔法。** 配好之后和几百行手写代码同一水平，但中文默认配置基本不可用，还要背上 346 MB 依赖。
7. **缓存省钱，不一定省时间。** 本地 q8_0 让 KV cache 启动分配量少 46.875%；云端前缀缓存让整包输入费用降约 96%，首字却没有稳定变快。

![PageIndex 与其他方法的准确率](experiments/report/figures/11-accuracy.svg)

![资料规模与答对率](experiments/report/figures/01-accuracy-vs-size.svg)

## 按你的关注点阅读

| 你是 | 推荐先看 |
| --- | --- |
| 产品经理 / 关心“为什么这么决定” | [产品案例：用实验数据做知识库方案决策](docs/case-study-product.zh-CN.md) |
| Agent / AI 应用开发 | [工程亮点：预算网关、第三方 Agent SDK 接入与评测方法](docs/engineering-highlights.zh-CN.md) |
| 想看全部数据和方法 | [完整报告](experiments/report/REPORT.zh-CN.md)（中文，约 450 行，22 张图） |
| 刚入门，想先补概念 | [小白手册](experiments/report/HANDBOOK.zh-CN.md)：token、RAG、向量、Agent、GPU 显存、KV cache、网络、系统设计，配大量生活比喻 |

## 做了什么

- **13 组实验**：资料规模、同主题扩容、检索方法、切段、每次给几段、语音噪声、回答模型（云端 4 个、本地 5 个）、向量模型、框架（LangChain / LlamaIndex / LangGraph）、并发、PageIndex 对照、本地 KV cache、云端前缀缓存。
- **评测方法**：严格的“只根据资料回答”规则，让检索失误直接变成答错；按题 bootstrap 给出 95% 区间；方法之间按题配对比较；失败计入分母。
- **成本控制**：自己写了一个跨进程的预算网关，所有付费请求先按上限预留、拿到用量再结算，SDK 内部的调用和重试也逃不出预算。第二轮共 3043 次请求，按用量计 ¥9.39。
- **结论落地与依据**：整包上限从 3 万字提高到 6 万字；每次检索从 3 段改为 5 段（完全正确率 +6–12 个百分点）；不引入框架；本地 bge 向量为默认、云端向量需要用户明确同意。

## 仓库结构

```
README.md / README.en.md            首页
docs/
  case-study-product.*.md           产品经理视角：问题、假设、实验、决策、权衡
  engineering-highlights.*.md       Agent 开发视角：预算网关、SDK 接入、评测方法、踩坑
experiments/
  report/
    REPORT.zh-CN.md / REPORT.en.md  完整报告
    HANDBOOK.zh-CN.md / .en.md      小白手册
    figures/  data/                 全部图表（SVG）与绘图数据（CSV）
    *.py                            绘图和测量脚本
  lib/                              预算网关、账本、证据裁剪及其测试
  11-pageindex/                     PageIndex 对照：运行、适配器、统计、结果
  12-kv-cache/                      本地 KV 与云端前缀缓存：脚本与结果
  01-…/09-…/results/                第一轮各实验的汇总结果
```

## 关于可复现性

- 代码是**快照**，用于阅读和审查。部分脚本依赖原项目的内部模块（检索实现、密钥读取工具），单独拷出来不能直接运行。
- 所有图表都由 `experiments/report/` 下的脚本，从各实验的 `results/*.json` 生成。数字可以逐个追溯到汇总文件。
- 原始回答、评分原文、语料正文和题目原文不在仓库里：它们会引用语料原文，而且语料有独立的许可。

## 数据来源与许可

- 语料是公开的 [CS-Notes](https://github.com/CyC2018/CS-Notes)（CC BY-NC-SA 4.0），固定提交。本仓库不包含语料正文和由它生成的题目原文，只包含汇总结果。
- 代码按 [MIT 许可](LICENSE) 发布。
- 费用都是“接口用量 × 实验时的标价”，不是服务商账单；模型和价格会变，结论只代表实验时的条件。
