# 预算网关与持久账本

[English](README-budget.en.md) · [工程亮点](../../docs/engineering-highlights.zh-CN.md)

第二轮实验的所有付费请求都经过这里。设计说明见[工程亮点第 1 节](../../docs/engineering-highlights.zh-CN.md)。

## 文件

| 文件 | 作用 |
| --- | --- |
| `budget.cjs` | 持久账本：跨进程目录锁、原子写入、预留与结算、阶段上限 |
| `gateway.cjs` | 本机网关：鉴权、模型白名单、`max_tokens` 上限、预留 → 转发 → 结算、流式解析、失败熔断 |
| `with-budget.cjs` | 启动网关并运行实验子进程；子进程只拿到临时令牌，拿不到真实 Key |
| `prices.json` | 已核验的模型价格（元 / 百万 token）与思考模式设置 |
| `evidence.cjs` | 检索证据裁剪：最多 5 段、每篇 3 段、共 2000 字 |
| `infrastructure.node.cjs`、`evidence.node.cjs` | Node 原生测试 |

## 规则

- **预留上限**：输入按“请求的 UTF-8 字节数 + 4096”估算 token（字节级分词器下，token 数不会超过字节数），按未命中缓存的价格计；输出按强制的 `max_tokens` 计。只允许纯文本消息和价格表里的模型。
- **结算**：响应带有效用量，且流式响应完整收到 `[DONE]` 后，才按用量结算。缺用量、HTTP 错误、断流和未完成的请求保留全部预留。预留不是实扣，但也不会被当作免费。
- **重试**：网关本身不重试；每次重试都重新预留。同一网关进程累计 5 次上游失败后返回 503，不再转发。
- **默认值**：请求没给 `max_tokens` 时取上限 4096，避免 SDK 的输出被悄悄截断；`finish_reason=length` 会记入账本。调用方传入的 `reasoning_effort` / `reasoning` 会被删除，思考模式只由价格表配置决定。
- **额度**：总上限 ¥20，另有各阶段上限，阶段之间不能自动借用。上限调整记录在账本的 `capHistory` 里。
- **恢复**：锁不会按时间自动删除，避免两个进程同时持有锁；进程崩溃后，要先检查运行中的进程和账本再恢复。账本不包含提示词、回答、Key 或错误响应正文。

## 测试

10 个测试，覆盖：密钥按服务商绑定、缺用量不退款与重启恢复、跨进程并发不超额、用量异常时锁定、阶段上限、流式截断与失败重试、默认 `max_tokens` 与思考参数、失败熔断，以及证据裁剪的条数、篇数、总长度和去重。

```
node --test experiments/lib/infrastructure.node.cjs experiments/lib/evidence.node.cjs
```

（`infrastructure.node.cjs` 在文件开头引入了原项目的密钥读取模块，本仓库没有这个模块，所以单独运行前要删掉这行引入和第一项测试；`evidence.node.cjs` 可以直接运行。）
