"""
Figures for the engineering report, drawn only from experiments/*/results/summary.json.

  "%LOCALAPPDATA%/llm-bench/experiments/venv/Scripts/python.exe" experiments/report/make_figures.py

Writes figures/<name>.svg and data/<name>.csv (the exact numbers plotted).
Every figure's footer names its source file, n and round (no dates); error bars / bands
are 95% bootstrap intervals over questions where the summary has them.
A figure whose data is missing is skipped with a message, never faked.
"""
import csv
import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
EXP = os.path.dirname(HERE)
FIG = os.path.join(HERE, "figures")
DATA = os.path.join(HERE, "data")
os.makedirs(FIG, exist_ok=True)
os.makedirs(DATA, exist_ok=True)

for f in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf"):
    if os.path.exists(f):
        font_manager.fontManager.addfont(f)
        plt.rcParams["font.family"] = font_manager.FontProperties(fname=f).get_name()
        break
plt.rcParams.update({"axes.unicode_minus": False, "svg.fonttype": "none", "figure.dpi": 100, "axes.grid": True, "grid.alpha": 0.3, "axes.spines.top": False, "axes.spines.right": False})

# one colour per method, used consistently across figures
C = {"full": "#4C72B0", "bm25": "#DD8452", "hybrid": "#55A868", "dense": "#C44E52", "cloud": "#4C72B0", "local": "#55A868"}
LABEL = {"full": "整包 whole", "bm25": "BM25", "hybrid": "BM25+bge 混合", "dense": "DashScope 向量"}


def load(rel, file="summary.json"):
    p = os.path.join(EXP, rel, "results", file)
    if not os.path.exists(p):
        print(f"skip: {rel} has no summary")
        return None
    return json.load(open(p, encoding="utf-8"))


def save(fig, name, rows, source, note=""):
    fig.text(0.01, 0.005, f"数据 data: experiments/{source}/results/summary.json  {note}", fontsize=7, color="#666")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    svg = os.path.join(FIG, f"{name}.svg")
    fig.savefig(svg, metadata={"Date": None})
    # LF, no trailing whitespace: matplotlib leaves spaces at the end of path lines
    with open(svg, encoding="utf-8") as fh:
        text = "\n".join(line.rstrip() for line in fh.read().splitlines()) + "\n"
    with open(svg, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    if os.environ.get("PREVIEW_DIR"):  # PNG copies for a quick visual check (not committed)
        fig.savefig(os.path.join(os.environ["PREVIEW_DIR"], f"{name}.png"), dpi=110)
    plt.close(fig)
    if rows:
        with open(os.path.join(DATA, f"{name}.csv"), "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
    print("wrote", name)


def size_curves(src, name, title, xkey="chars", methods=("full", "bm25", "hybrid", "dense"), file="summary.json"):
    d = load(src, file)
    if not d:
        return
    raw_rows = d["summary"] if "summary" in d else d["rows"]
    # repeated runs of one size (same chars) become one point: mean, with the widest interval
    grouped = {}
    for r in raw_rows:
        grouped.setdefault((r["method"], r[xkey]), []).append(r)
    rows = []
    for (m, x), rs in grouped.items():
        rows.append({"method": m, xkey: x, "fullCorrect": round(sum(r["fullCorrect"] for r in rs) / len(rs), 1),
                     "fullCorrectCI95": [min(r["fullCorrectCI95"][0] for r in rs), max(r["fullCorrectCI95"][1] for r in rs)], "runs": len(rs)})
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    out = []
    for m in methods:
        pts = sorted([r for r in rows if r["method"] == m], key=lambda r: r[xkey])
        if not pts:
            continue
        x = [r[xkey] / 1000 for r in pts]
        y = [r["fullCorrect"] for r in pts]
        lo = [r["fullCorrectCI95"][0] for r in pts]
        hi = [r["fullCorrectCI95"][1] for r in pts]
        ax.plot(x, y, marker="o", color=C[m], label=LABEL[m])
        ax.fill_between(x, lo, hi, color=C[m], alpha=0.12)
        out += [{"method": m, "kchars": a, "fullCorrect": b, "ci_lo": c, "ci_hi": e} for a, b, c, e in zip(x, y, lo, hi)]
    ax.set_xlabel("资料大小（千字） pack size (k chars)")
    ax.set_ylabel("完全正确 % fully correct")
    ax.set_ylim(0, 100)
    ax.set_title(title)
    ax.legend(loc="lower left", fontsize=8)
    n = d.get("needles", "?")
    reps = max(r["runs"] for r in rows)
    save(fig, name, out, src, f"n={n} 题/格 · 带 = 95% 区间{f' · 最大一档重复 {reps} 次取均值' if reps > 1 else ''} · 第一轮 round 1")


def fig_latency_cost():
    d = load("01-context-threshold")
    if not d:
        return
    rows = d["summary"]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 4))
    out = []
    for m in ("full", "bm25", "hybrid", "dense"):
        pts = sorted([r for r in rows if r["method"] == m], key=lambda r: r["chars"])
        x = [r["chars"] / 1000 for r in pts]
        a1.plot(x, [r["ttftP50"] for r in pts], marker="o", color=C[m], label=f"{LABEL[m]} p50")
        a1.plot(x, [r["ttftP90"] for r in pts], ls="--", color=C[m], alpha=0.6)
        a2.plot(x, [r["cnyPerAnswer"] * 100 for r in pts], marker="o", color=C[m], label=LABEL[m])
        out += [{"method": m, "kchars": r["chars"] / 1000, "ttftP50": r["ttftP50"], "ttftP90": r["ttftP90"], "fen_per_answer": round(r["cnyPerAnswer"] * 100, 3), "cacheHitShare": r["cacheHitShare"]} for r in pts]
    a1.set_title("首字延迟（实线 p50，虚线 p90） first token")
    a1.set_xlabel("资料大小（千字）")
    a1.set_ylabel("毫秒 ms")
    a1.legend(fontsize=7)
    a2.set_yscale("log")
    a2.set_title("每题费用（分，对数轴） cost per answer (fen, log)")
    a2.set_xlabel("资料大小（千字）")
    a2.legend(fontsize=7)
    save(fig, "01-latency-cost", out, "01-context-threshold", f"deepseek-chat · 每点 88 个回答 · 第一轮 round 1")


def fig_position():
    d = load("01-context-threshold")
    if not d:
        return
    pos = d["fullByNeedlePosition"]
    fig, ax = plt.subplots(figsize=(5.5, 3.4))
    labels = [f"{int(p['from'] * 100)}–{int(p['to'] * 100)}%" for p in pos]
    ax.bar(labels, [p["fullCorrect"] for p in pos], color=C["full"])
    for i, p in enumerate(pos):
        ax.text(i, p["fullCorrect"] + 1.5, f"n={p['answers']}", ha="center", fontsize=8)
    ax.set_ylim(0, 100)
    ax.set_xlabel("答案所在位置（占整包的比例） answer position in the pack")
    ax.set_ylabel("完全正确 %")
    ax.set_title("整包：没有明显的“中间遗忘” no clear lost-in-the-middle")
    save(fig, "01-needle-position", [dict(p) for p in pos], "01-context-threshold")


def fig_frameworks():
    d = load("02-frameworks")
    if not d:
        return
    rows = [r for r in d["summary"] if "fullCorrect" in r]
    rows.sort(key=lambda r: r["fullCorrect"])
    fig, ax = plt.subplots(figsize=(8, 4.8))
    y = range(len(rows))
    col = ["#55A868" if r["config"].startswith("ours") else "#8172B2" if "llamaindex" in r["config"] else "#DD8452" for r in rows]
    ax.barh(list(y), [r["fullCorrect"] for r in rows], color=col, xerr=[[r["fullCorrect"] - r["fullCorrectCI95"][0] for r in rows], [r["fullCorrectCI95"][1] - r["fullCorrect"] for r in rows]], capsize=3)
    ax.set_yticks(list(y))
    ax.set_yticklabels([r["config"] for r in rows], fontsize=8)
    ax.set_xlabel("完全正确 % fully correct")
    ax.set_xlim(0, 100)
    ax.set_title("框架与自研实现（同一语料、同一模型与评分） frameworks vs hand-written")
    failed = [r["config"] for r in d["summary"] if "error" in r]
    save(fig, "02-frameworks", [{k: r.get(k) for k in ("config", "goldHit", "fullCorrect", "wrongOrEmpty", "contextCharsP50", "buildMs")} for r in rows], "02-frameworks", f"n={d['questions']} · 默认配置失败 failed: {', '.join(failed)} · 第一轮 round 1")


def fig_asr():
    d = load("03-asr-noise")
    if not d:
        return
    rs = d["retrieval"]
    methods = []
    for r in rs:
        if r["method"] not in methods:
            methods.append(r["method"])
    fig, ax = plt.subplots(figsize=(6.5, 3.4))
    out = []
    for i, m in enumerate(methods):
        clean = next(r["sec3"] for r in rs if r["method"] == m and r["variant"] == "clean")
        noisy = next(r["sec3"] for r in rs if r["method"] == m and r["variant"] == "asr")
        ax.plot([noisy, clean], [i, i], color="#999", zorder=1)
        ax.scatter([clean], [i], color="#4C72B0", zorder=2, label="干净 clean" if i == 0 else None)
        ax.scatter([noisy], [i], color="#C44E52", zorder=2, label="语音噪声 ASR-style" if i == 0 else None)
        out.append({"method": m, "clean": clean, "asr": noisy})
    ax.set_yticks(range(len(methods)))
    ax.set_yticklabels(methods)
    ax.set_xlim(40, 100)
    ax.set_xlabel("正确段落进入前 3 % gold section in top 3")
    ax.set_title("语音识别风格的提问让检索掉 8–12 个百分点")
    ax.legend(fontsize=8, loc="lower right")
    save(fig, "03-asr-noise", out, "03-asr-noise", f"n={rs[0]['n']} · 噪声为模型模拟 simulated · 第一轮 round 1")


def fig_chunking():
    d = load("04-chunking")
    if not d:
        return
    rows = d["rows"]
    fig, ax = plt.subplots(figsize=(6.8, 3.8))
    out = []
    colors = {"bm25": C["bm25"], "bge-small-zh": C["hybrid"], "dashscope-v4": C["dense"]}
    for ret, col in colors.items():
        pts = [r for r in rows if r["retriever"] == ret and r["chunker"].startswith("heading")]
        x = [int(r["chunker"].split("-")[1].split(" ")[0]) for r in pts]
        ax.plot(x, [r["goldTop3"] for r in pts], marker="o", color=col, label=ret)
        fixed = next(r for r in rows if r["retriever"] == ret and r["chunker"] == "fixed-400")
        ax.scatter([400], [fixed["goldTop3"]], marker="x", s=60, color=col)
        out += [{"retriever": ret, "target": a, "goldTop3": r["goldTop3"]} for a, r in zip(x, pts)] + [{"retriever": ret, "target": "fixed-400", "goldTop3": fixed["goldTop3"]}]
    ax.set_xlabel("按标题切段的目标长度（字）；× = 固定 400 字窗口")
    ax.set_ylabel("正确段落进入前 3 %")
    ax.set_ylim(40, 100)
    ax.set_title("切段：按标题切优于固定窗口，太碎会伤")
    ax.legend(fontsize=8)
    save(fig, "04-chunking", out, "04-chunking", f"n={d['questions']} · 第一轮 round 1")


def fig_budget():
    d = load("06-context-budget")
    if not d:
        return
    rows = d["rows"]
    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    out = []
    for m, col in (("bm25", C["bm25"]), ("hybrid-bge", C["hybrid"]), ("dense-dashscope", C["dense"])):
        pts = [r for r in rows if r["method"] == m]
        ax.errorbar([r["k"] for r in pts], [r["fullCorrect"] for r in pts], yerr=[[r["fullCorrect"] - r["fullCorrectCI95"][0] for r in pts], [r["fullCorrectCI95"][1] - r["fullCorrect"] for r in pts]], marker="o", capsize=3, color=col, label=m)
        out += [{"method": m, "k": r["k"], "fullCorrect": r["fullCorrect"], "contextCharsP50": r["contextCharsP50"], "ttftP50": r["ttftP50"]} for r in pts]
    ax.axvline(5, color="#999", ls=":")
    ax.text(5.1, 8, "产品取 5 段 app uses 5", fontsize=8, color="#666")
    ax.set_xticks([3, 5, 8])
    ax.set_xlabel("每次回答给模型的段数 passages per answer")
    ax.set_ylabel("完全正确 %")
    ax.set_ylim(0, 100)
    ax.set_title("检索段数：5 段比 3 段好，8 段不再稳定提升")
    ax.legend(fontsize=8)
    save(fig, "06-context-budget", out, "06-context-budget", f"n={d['questions']} · 第一轮 round 1")


def fig_models():
    d = load("07-models")
    if not d:
        return
    rows = [r for r in d["rows"] if r.get("n")]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4), sharey=True)
    out = []
    for ax, task in zip(axes, ("retrieval", "whole")):
        for r in [r for r in rows if r["task"] == task]:
            x = max(r["firstAnswerMsP50"], 1)
            col = C["cloud"] if r["kind"] == "cloud" else C["local"]
            ax.scatter([x], [r["fullCorrect"]], s=60, color=col, zorder=2)
            ax.errorbar([x], [r["fullCorrect"]], yerr=[[r["fullCorrect"] - r["fullCorrectCI95"][0]], [r["fullCorrectCI95"][1] - r["fullCorrect"]]], color=col, alpha=0.4, capsize=2)
            ax.annotate(r["model"].replace("dashscope:", "").replace("local:", ""), (x, r["fullCorrect"]), fontsize=7, xytext=(4, 3), textcoords="offset points")
            out.append({k: r.get(k) for k in ("model", "kind", "task", "n", "fullCorrect", "wrongOrEmpty", "firstAnswerMsP50", "tokensPerSecP50", "cnyPerAnswer", "vramMiB")})
        ax.set_xscale("log")
        ax.set_xlabel("首个回答字的延迟 p50（ms，对数轴） first answer token")
        ax.set_title({"retrieval": "检索场景（5 段资料）", "whole": "整包场景（2.2 万字）"}[task])
    axes[0].set_ylabel("完全正确 %")
    axes[0].set_ylim(0, 100)
    fig.suptitle("回答模型：蓝 = 云端，绿 = 本地（RTX 4060 笔记本 8 GB）", fontsize=11)
    save(fig, "07-models", out, "07-models", f"评分 judge: deepseek-chat · 第一轮 round 1")


def fig_embeddings():
    d = load("07b-embeddings")
    if not d:
        return
    rows = d["rows"]
    methods = []
    for r in rows:
        if r["method"] not in methods:
            methods.append(r["method"])
    fig, ax = plt.subplots(figsize=(8, 3.8))
    w = 0.38
    out = []
    for j, variant in enumerate(("clean", "asr")):
        vals = [next(r["goldTop5"] for r in rows if r["method"] == m and r["variant"] == variant) for m in methods]
        ax.bar([i + (j - 0.5) * w for i in range(len(methods))], vals, width=w, label={"clean": "干净 clean", "asr": "语音噪声 ASR-style"}[variant], color=["#4C72B0", "#C44E52"][j])
        out += [{"method": m, "variant": variant, "goldTop5": v} for m, v in zip(methods, vals)]
    ax.set_xticks(range(len(methods)))
    ax.set_xticklabels(methods, rotation=20, ha="right", fontsize=8)
    ax.set_ylabel("正确段落进入前 5 %")
    ax.set_ylim(0, 100)
    ax.set_title("向量模型对比 embedding models")
    ax.legend(fontsize=8)
    save(fig, "07b-embeddings", out, "07b-embeddings", f"n={d['questions']} · 第一轮 round 1")


def fig_langgraph():
    d = load("08-langgraph")
    e2 = load("02-frameworks")
    if not d or not e2:
        return
    base = d["singlePassBaselines"]
    bars = [("ours DashScope 单次", base["clean"].get("ours-dense-dashscope"), base["asr"].get("ours-dense-dashscope")),
            ("LangChain 单次", base["clean"].get("langchain-dense-fixed"), None),
            ("LangGraph agentic", next(r["fullCorrect"] for r in d["rows"] if r["variant"] == "clean"), next(r["fullCorrect"] for r in d["rows"] if r["variant"] == "asr"))]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 3.8))
    for j, (lab, col) in enumerate((("干净 clean", "#4C72B0"), ("语音噪声 ASR", "#C44E52"))):
        vals = [b[1 + j] if b[1 + j] is not None else 0 for b in bars]
        a1.bar([i + (j - 0.5) * 0.38 for i in range(len(bars))], vals, width=0.38, color=col, label=lab)
        for i, b in enumerate(bars):
            if b[1 + j] is None:
                a1.text(i + (j - 0.5) * 0.38, 2, "未测 n/a", ha="center", fontsize=7, color="#666")
    a1.set_xticks(range(len(bars)))
    a1.set_xticklabels([b[0] for b in bars], fontsize=8)
    a1.set_ylim(0, 100)
    a1.set_ylabel("完全正确 %")
    a1.legend(fontsize=8)
    a1.set_title("答对率 accuracy")
    rows = d["rows"]
    a2.bar([r["variant"] for r in rows], [r["totalMsP50"] for r in rows], color="#8172B2")
    for i, r in enumerate(rows):
        a2.text(i, r["totalMsP50"], f"{r['llmCallsMean']} 次调用/题", ha="center", va="bottom", fontsize=8)
    a2.set_ylabel("端到端中位 ms end-to-end p50")
    a2.set_title("代价 cost of the agent loop")
    save(fig, "08-langgraph", [{k: r.get(k) for k in ("variant", "fullCorrect", "llmCallsMean", "rewroteShare", "firstAnswerMsP50", "totalMsP50", "cnyPerQuestion")} for r in rows], "08-langgraph", f"n={rows[0]['n']} · 第一轮 round 1")


def fig_concurrency():
    d = load("09-concurrency")
    if not d or "cloud" not in d:
        return
    fig, ax = plt.subplots(figsize=(7.2, 4))
    out = []
    series = {}
    for r in d["cloud"] + (d.get("local") if isinstance(d.get("local"), list) else []):
        series.setdefault(f"{r['endpoint']} · {r['shape']}", []).append(r)
    for (name, pts), col in zip(series.items(), ["#4C72B0", "#C44E52", "#DD8452", "#55A868"]):
        x = [p["concurrency"] for p in pts]
        ax.plot(x, [p["firstTokenMsP50"] for p in pts], marker="o", color=col, label=f"{name} p50")
        ax.plot(x, [p["firstTokenMsP95"] for p in pts], ls="--", color=col, alpha=0.6)
        out += [{"series": name, **{k: p[k] for k in ("concurrency", "firstTokenMsP50", "firstTokenMsP95", "errors", "requestsPerMin")}} for p in pts]
    ax.set_xscale("log", base=2)
    ax.set_xticks([1, 2, 4, 8, 16])
    ax.set_xticklabels(["1", "2", "4", "8", "16"])
    ax.set_xlabel("同时进行的请求数 concurrency")
    ax.set_ylabel("首字延迟 ms（实线 p50，虚线 p95）")
    ax.set_title("并发对首字延迟的影响")
    ax.legend(fontsize=7)
    save(fig, "09-concurrency", out, "09-concurrency", f"每档 24 个请求 · 第一轮 round 1")


size_curves("01-context-threshold", "01-accuracy-vs-size", "资料变大（加入无关文档）：答对率 vs 资料大小")
size_curves("01b-same-topic", "01b-accuracy-vs-size", "资料变大（同一主题“设计模式”）：答对率 vs 资料大小")
size_curves("01b-same-topic", "01b-java-accuracy-vs-size", "资料变大（同一领域 Java 笔记）：答对率 vs 资料大小", file="summary-java.json")
fig_latency_cost()
fig_position()
fig_frameworks()
fig_asr()
fig_chunking()
fig_budget()
fig_models()
fig_embeddings()
fig_langgraph()
fig_concurrency()

# New results are additive; missing measured data is skipped explicitly.
from continuation_figures import main as continuation_figures
continuation_figures()
