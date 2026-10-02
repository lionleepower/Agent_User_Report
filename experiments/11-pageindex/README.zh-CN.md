# 实验 11：PageIndex 对照

状态：**已完成**（2026-09-30，deepseek-flash 非思考；与历史 deepseek-chat 不合并）。受控组 864/864 次回答成功，官方原生组 23/24。本实验累计按用量计 ¥9.02（不含实验 12 云端），未读取账单。

| 题型 | 整包 | BM25 | 向量 | PageIndex |
| --- | --- | --- | --- | --- |
| 干净 48 题 | 76.0% | 58.3% | 62.5% | 79.2% |
| 噪声 48 题 | 69.8% | 44.8% | 58.3% | 78.1% |
| 多跳 12 题（探索性） | 83.3% | 50.0% | 83.3% | 100%（原生 91.7%） |

表中为完全正确率。PageIndex 对 BM25 高 20.8 / 33.3 个百分点，对向量高 16.7 / 19.8 个百分点（干净 / 噪声），配对区间均不跨 0；对整包 +3.1 / +8.3，区间跨 0，差异不显著。端到端 p50：PageIndex 6.4 s，整包 1.1 s。单题费用：PageIndex ¥0.028，整包 ¥0.004（前缀缓存命中）。建索引：PageIndex 18.3 s / ¥0.059，向量 23.5 s / ¥0.039。

详见[报告第 4.3 节](../report/REPORT.zh-CN.md#43-pageindex会翻目录的好学生第二轮)和[汇总](results/summary.json)（含各 run、置信区间、配对差值、摊销和按阶段费用）。逐次记录：[main](results/main.json)、[multi](results/multi.json)、[native](results/native.json)、[预检](results/preflight.json)、[兼容检查](results/compatibility.json)、[索引](results/index.json)、[向量](results/embeddings.json)；统计代码见 [stats.ts](stats.ts)、[summarize.ts](summarize.ts)。

公开 CS-Notes 固定提交 `b70121d377cb6005eb65f12b098cd5decd905669`，170 篇文档通过仓库 manifest 校验。M 档 37 篇、200347 字；48 道干净题与噪声题完整配对。新增 12 道跨章节组合题（题目原文未包含在本仓库），已由助手逐题核对公开依据；不能将其称为独立人工标注的标准多跳数据集。

公开语料转为本机文本 PDF：136 页、637 个 chunk/page 映射，空白归一化后提取文本与源文逐字一致；第 1、69、136 页已渲染检查。正文、PDF、索引和原始回答不入库。

用户已批准 [26 个 hash-pinned 依赖](dependency-manifest.json)，共 48002472 字节，已通过 IPv4 下载并逐个校验 SHA-256，安装到独立 overlay；原实验 venv 保持原样。PageIndex 0.2.10 可导入。未下载模型。

准备：`npx vite-node experiments/lib/prepare.ts`；PDF：在批准的依赖 overlay 下运行 `pdf.py --raw <独立公开实验目录>`。所有付费请求必须经过预算 gateway，不直接使用 SDK 默认服务。

受控流程使用官方本地工具，最多 6 次模型请求，120 秒；共同回答客户端限制证据 5 段、每篇 3 段、2000 字。SDK 原生组单独保留完整响应和实际读页轨迹。SDK 流式输出会混入工具调用前的叙述，因此原生组使用官方非流式 final_output；最终回答首字为 null，不能用于首字排名。当前兼容性仅以模拟测试验证，未进行真实索引或回答。adapter 自行加载批准的 overlay，关闭 SDK 重试，并使用经哈希校验的本机 `cl100k_base` tokenizer（不下载）；统计见 `stats.ts`（以题为单位、配对差值、摊销），评分费用单列。

```powershell
$env:BENCH_BUDGET_CNY='20'
$env:NODE_OPTIONS='--dns-result-order=ipv4first'
# prices.json 已 approved；with-keys 是唯一凭据入口。compatibility 任一检查失败即停止。
npx electron tools/retrieval-bench/with-keys.cjs --profile "<app-profile-dir>" --run node experiments/lib/with-budget.cjs --stage preflight --run npx vite-node experiments/11-pageindex/run.ts --phase compatibility
# 依次使用 index 阶段运行 adapter.py index 与 --phase embeddings；然后 preflight/main/multi/native。
# 正式 main: main 阶段；multi/native: multi 阶段。各阶段上限不能自动借用 reserve。
```

离线验证：`python -m unittest discover -s experiments/11-pageindex -p test_adapter.py`；`npm run test:bench`；`npx vitest run experiments/lib/stream.test.ts`。题目统计按题配对，重复回答不视为独立题；未完成条件不可当作完整主对照。
