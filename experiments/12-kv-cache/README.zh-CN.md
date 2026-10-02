# 实验 12：KV cache 与前缀复用

状态：**本地与云端均已完成**（2026-09-30）。本地费用 ¥0（未计电费）；云端 deepseek-flash 按用量计 ¥0.376（97 次请求，含 33 次标记长度探测），未读取账单。

云端前缀缓存：检索（约 477 token）和整包（约 9350 token）两种形状 × 稳定 / 等长变化前缀 × 并发 1 / 4，每个条件 8 次，共 64/64 成功。运行前实测全部 33 个标记均为 11 token。
- 稳定前缀在首次请求之后按 256 token 的整数倍命中；变化前缀始终不命中。
- 并发 1 的首次请求未命中，说明"首次请求不保证未命中"。
- 在这两个规模下，命中没有带来稳定的首字改善；整包形状的输入费用下降约 96%。
- 这是服务商的计费缓存，不是 KV 显存。

数据：[云端逐条件](results/cloud.json)、[汇总](results/summary.json) 的 cloud 字段、[图](../report/figures/12-cloud-cache.svg)。

已有 Qwen3-4B-Instruct-2507 Q4_K_M，llama.cpp build 11222，RTX 4060 Laptop。`f16/q8_0 × 总上下文 8192/16384 × 槽位 1/2`，每配置独立重启 5 次。固定 slot 0 串行请求，不能当作并发吞吐测试。请求为固定短检索和 2.2 万字整包；输出上限 64 token，只比较延迟和资源，不比较答案质量。

- 150 次有效回答、30 次容量跳过、0 次运行失败。整包实测 8635 token，加输出余量后仅总上下文 16384、单槽配置可容纳；未自动缩小资料。
- KV **启动分配量**来自详细运行日志：8192 token 下 f16 1152 MiB、q8_0 612 MiB；16384 下 2304、1224 MiB。q8_0 分配量减少 46.875%，这是本模型配置的结果。
- `timings.cache_n` 与 Prometheus 缓存计数增量逐次一致。关闭复用时为 0；共享前缀后检索请求复用 535 token，整包复用 8630 token。
- 运行中 KV 占用字节未暴露，保存为 null。GPU 总显存及相对启动前增量另列，不代替 KV 指标。
- p50 取 5 次中位数；p95 为 5 次中的最大值，样本不足以稳定估计尾延迟。

数据：[分组汇总](results/summary.json)、[逐请求观测](results/local.json)、[预检](results/preflight-local.json)。预检不混入正式数据。原始回答、日志、GPU 时间线仅在本机独立 run 目录。

报告新增 4 张 SVG 和对应 CSV：[启动分配](../report/figures/12-kv-allocation.svg)、[首字延迟](../report/figures/12-prefix-latency.svg)、[复用 token](../report/figures/12-prefix-tokens.svg)、[GPU 时间线](../report/figures/12-gpu-timeline.svg)。时间线 CSV 只含数值指标；完整含正文日志不入库。生成：设置 BENCH_RAW_DIR 指向本轮公开实验目录，运行 `experiments/report/continuation_figures.py`；未指定原始目录时跳过时间线。

```powershell
$env:BENCH_BUDGET_CNY='20'
& '<bench>/experiments/venv/Scripts/python.exe' -m unittest discover -s experiments/12-kv-cache -p 'test_*.py'
& '<bench>/experiments/venv/Scripts/python.exe' experiments/12-kv-cache/local.py --raw '<bench>/experiments/continuation-2026-09-30' --summary experiments/12-kv-cache/results/local.json
& '<bench>/experiments/venv/Scripts/python.exe' experiments/12-kv-cache/summarize.py
```

Windows 详细日志可能混有非 UTF-8 字节：解析以替换解码读取 ASCII 指标；原始字节保留。首次正式启动因此中止，修正后完整重跑；失败记录不混入正式汇总。云端缓存命中与本地 KV 分配量不能互相替代。
