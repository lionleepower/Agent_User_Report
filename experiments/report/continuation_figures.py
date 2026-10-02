"""Additive plots for measured round-2 local KV results. No paid calls."""
import csv
import json
import os
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

HERE = Path(__file__).resolve().parent
for name in ('C:/Windows/Fonts/msyh.ttc', 'C:/Windows/Fonts/simhei.ttf'):
    if Path(name).exists():
        font_manager.fontManager.addfont(name)
        plt.rcParams['font.family'] = font_manager.FontProperties(fname=name).get_name()
        break
plt.rcParams.update({'svg.fonttype': 'none', 'axes.spines.top': False, 'axes.spines.right': False, 'axes.unicode_minus': False})


def save(fig, name, rows, note):
    fig.text(.02, .025, 'experiments/12-kv-cache/results/summary.json · 第二轮 round 2 · 5 restarts/config\nQwen3-4B-Instruct Q4_K_M · llama.cpp 11222 · ' + note, fontsize=7)
    fig.tight_layout(rect=(0, .10, 1, 1))
    svg = HERE / 'figures' / (name + '.svg')
    fig.savefig(svg, metadata={'Date': None})
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text(encoding='utf8').splitlines()) + '\n', encoding='utf8', newline='\n')
    if os.environ.get('PREVIEW_DIR'):
        fig.savefig(Path(os.environ['PREVIEW_DIR']) / (name + '.png'), dpi=120)
    plt.close(fig)
    with (HERE / 'data' / (name + '.csv')).open('w', newline='', encoding='utf8') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader(); writer.writerows(rows)


def main():
    source = HERE.parent / '12-kv-cache/results/summary.json'
    if not source.exists():
        print('skip: no measured local KV summary'); return
    data = json.loads(source.read_text(encoding='utf8'))
    if data['localStatus'] != 'complete':
        print('skip: local KV run incomplete'); return
    rows = data['rows']
    configs = {(r['kvType'], r['contextTotal'], r['slots']): r for r in rows}
    keys = sorted(configs, key=lambda k: (k[1], k[2], k[0]))
    fig, ax = plt.subplots(figsize=(8, 4.8))
    values = [configs[k]['kvAllocatedMiB'] for k in keys]
    ax.bar(range(8), values, color=['#0072B2' if k[0] == 'f16' else '#D55E00' for k in keys])
    ax.set_xticks(range(8), [f'{k[0]}\n{k[1]} / p{k[2]}' for k in keys])
    ax.set_ylabel('启动 KV 分配 / allocated MiB'); ax.set_title('KV 启动分配量：q8_0 比 f16 减少 46.875%')
    for i, v in enumerate(values): ax.text(i, v + 25, f'{v:g}', ha='center', fontsize=9)
    ax.set_ylim(0, 2650)
    save(fig, '12-kv-allocation', [{key: configs[k][key] for key in ('kvType', 'contextTotal', 'slots', 'contextPerSlot', 'kvAllocatedMiB', 'gpuPeakTotalMiBP50', 'gpuPeakDeltaMiBP50')} for k in keys], 'runtime allocation logs; occupied bytes unavailable')

    fig, axes = plt.subplots(1, 2, figsize=(12, 5.2))
    plotted = []
    for ax, shape in zip(axes, ['retrieval', 'whole']):
        valid = [k for k in keys if any(r['shape'] == shape and (r['kvType'], r['contextTotal'], r['slots']) == k for r in rows)]
        for state, offset, color in [('first_in_shape', -.24, '#0072B2'), ('shared_prefix', 0, '#009E73'), ('cache_disabled', .24, '#D55E00')]:
            pts = [next(r for r in rows if r['shape'] == shape and r['state'] == state and (r['kvType'], r['contextTotal'], r['slots']) == k) for k in valid]
            ax.bar([i + offset for i in range(len(valid))], [r['firstAnswerMsP50'] for r in pts], .23, color=color, label=state)
            plotted.extend({key: r[key] for key in ('kvType', 'contextTotal', 'slots', 'shape', 'state', 'n', 'firstAnswerMsP50', 'firstAnswerMsP95', 'cachedPromptTokensP50')} for r in pts)
        ax.set_xticks(range(len(valid)), [f'{k[0]}\n{k[1]}/p{k[2]}' for k in valid], fontsize=8)
        ax.set_title(shape); ax.set_ylabel('最终回答首字 p50 / ms'); ax.legend(fontsize=7, loc='upper center', bbox_to_anchor=(.5, 1.22), ncol=3)
    save(fig, '12-prefix-latency', plotted, 'median of 5; no CI; p95=max of 5 (CSV only)')

    fig, ax = plt.subplots(figsize=(8, 4.8))
    selected = [r for r in rows if r['state'] == 'shared_prefix']
    labels = [f"{r['kvType']} {r['contextTotal']}/p{r['slots']} {r['shape']}" for r in selected]
    ax.barh(labels, [r['cachedPromptTokensP50'] for r in selected], color='#009E73')
    ax.set_xlabel('实际复用 prompt token / timings.cache_n'); ax.set_title('运行时前缀复用；不是 KV 占用字节')
    save(fig, '12-prefix-tokens', [{key: r[key] for key in ('kvType', 'contextTotal', 'slots', 'shape', 'n', 'cachedPromptTokensP50')} for r in selected], 'timings.cache_n cross-checked against metric deltas')
    raw_root = os.environ.get('BENCH_RAW_DIR')
    if raw_root:
        root = Path(raw_root) / data['runId']
        fig, ax = plt.subplots(figsize=(9, 4.8)); timeline = []
        for dtype, ctx, slots in keys:
            name = f'{dtype}-{ctx}-{slots}-0-gpu.json'
            samples = json.loads((root / name).read_text(encoding='utf8'))
            samples = [s for s in samples if s['gpuTotalUsedMiB'] is not None]
            ax.plot([s['elapsedMs']/1000 for s in samples], [s['gpuTotalUsedMiB'] for s in samples], label=f'{dtype} {ctx}/p{slots}')
            timeline.extend({'kvType': dtype, 'contextTotal': ctx, 'slots': slots, 'repeat': 0, **s} for s in samples)
        ax.set_xlabel('服务启动后时间 / seconds'); ax.set_ylabel('GPU 总显存 / total used MiB'); ax.set_title('GPU 时间线：每组第 1 次独立启动（不是 KV 占用）'); ax.legend(fontsize=7, ncol=2)
        save(fig, '12-gpu-timeline', timeline, 'source: run GPU JSON; ~500 ms sampling; repeat 0 shown')
    else:
        print('skip GPU timeline: BENCH_RAW_DIR not supplied')
    print('wrote measured local KV SVGs and CSVs; PageIndex/cloud have no measured result')


if __name__ == '__main__':
    main()
