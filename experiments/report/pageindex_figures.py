"""Figures for measured round-2 PageIndex and cloud-cache results. No paid calls.

Reads experiments/11-pageindex/results/summary.json and experiments/12-kv-cache/results/cloud.json;
skips any figure whose source is missing or incomplete instead of drawing unmeasured data.
"""
import csv
import json
import os
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for name in ('C:/Windows/Fonts/msyh.ttc', 'C:/Windows/Fonts/simhei.ttf'):
    if Path(name).exists():
        font_manager.fontManager.addfont(name)
        plt.rcParams['font.family'] = font_manager.FontProperties(fname=name).get_name()
        break
plt.rcParams.update({'svg.fonttype': 'none', 'axes.spines.top': False, 'axes.spines.right': False, 'axes.unicode_minus': False})
METHODS = ['whole', 'bm25', 'dense', 'pageindex']
LABEL = {'whole': '整包 whole', 'bm25': 'BM25', 'dense': '向量 dense', 'pageindex': 'PageIndex', 'native': 'PageIndex 原生'}
COLOR = {'whole': '#0072B2', 'bm25': '#E69F00', 'dense': '#009E73', 'pageindex': '#D55E00', 'native': '#CC79A7'}
TASK = {'clean': '干净 clean', 'noise': '噪声 noise', 'multi': '多跳 multi（探索性）'}


def save(fig, name, rows, source, note):
    fig.text(.02, .025, f'{source} · 第二轮 round 2 · deepseek-flash (non-thinking)\n{note}', fontsize=7)
    fig.tight_layout(rect=(0, .10, 1, 1))
    svg = HERE / 'figures' / (name + '.svg')
    fig.savefig(svg, metadata={'Date': None})
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text(encoding='utf8').splitlines()) + '\n', encoding='utf8', newline='\n')
    if os.environ.get('PREVIEW_DIR'):
        fig.savefig(Path(os.environ['PREVIEW_DIR']) / (name + '.png'), dpi=120)
    plt.close(fig)
    with (HERE / 'data' / (name + '.csv')).open('w', newline='', encoding='utf8') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def pageindex(data):
    src = 'experiments/11-pageindex/results/summary.json'
    groups = data['controlled']['groups'] + data['native']['groups']
    tasks = [t for t in TASK if any(g['task'] == t for g in groups)]

    # 1. fully-correct rate with question-level bootstrap CI
    fig, ax = plt.subplots(figsize=(9, 5))
    rows, width = [], .16
    for mi, method in enumerate(METHODS + ['native']):
        for ti, task in enumerate(tasks):
            g = next((g for g in groups if g['task'] == task and g['method'] == method), None)
            if not g:
                continue
            lo, hi = g['fullyCorrectCI95']
            x = ti + (mi - 2) * width
            ax.bar(x, g['fullyCorrect'], width, color=COLOR[method], label=LABEL[method])
            ax.errorbar(x, g['fullyCorrect'], [[g['fullyCorrect'] - lo], [hi - g['fullyCorrect']]], color='#333', capsize=2, lw=.8)
            rows.append({'task': task, 'method': method, 'questions': g['questionsObserved'], 'responses': g['responses'], 'failures': g['failures'], 'fullyCorrect': round(g['fullyCorrect'], 4), 'ci95Low': round(lo, 4), 'ci95High': round(hi, 4), 'zeroOrFailed': round(g['zeroOrFailed'], 4)})
    # one legend entry per method, whichever task it first appears in
    seen = {}
    for h, l in zip(*ax.get_legend_handles_labels()):
        seen.setdefault(l, h)
    ax.legend(seen.values(), seen.keys(), fontsize=8, ncol=5, loc='upper center', bbox_to_anchor=(.5, 1.13))
    ax.set_xticks(range(len(tasks)), [TASK[t] for t in tasks])
    ax.set_ylim(0, 1.05)
    ax.set_ylabel('完全正确率 / fully correct')
    save(fig, '11-accuracy', rows, src, 'bars: question-level mean of 2 answers; whiskers: 95% percentile bootstrap over questions (2000x, seed 7); native kept separate from controlled')

    # 2. paired differences PageIndex minus each method
    diffs = data['controlled']['pairedDifferences']
    fig, ax = plt.subplots(figsize=(8, 4.6))
    rows, labels = [], []
    for i, d in enumerate(diffs):
        lo, hi = d['diffCI95']
        ax.errorbar(d['diff'], i, xerr=[[d['diff'] - lo], [hi - d['diff']]], fmt='o', color=COLOR[d['b']], capsize=3)
        labels.append(f"{TASK[d['task']]}: PageIndex − {LABEL[d['b']]}")
        rows.append({'task': d['task'], 'a': d['a'], 'b': d['b'], 'pairedQuestions': d['pairedQuestions'], 'diff': round(d['diff'], 4), 'ci95Low': round(lo, 4), 'ci95High': round(hi, 4), 'aBetter': d['aBetter'], 'bBetter': d['bBetter']})
    ax.axvline(0, color='#888', lw=.8)
    ax.set_yticks(range(len(labels)), labels, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel('完全正确率差值（按题配对）/ paired difference')
    save(fig, '11-paired-diff', rows, src, 'per-question difference of fully-correct rates; 95% percentile bootstrap over paired questions (2000x, seed 7); an interval crossing 0 is not a difference')

    # 3. latency and model calls
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(11, 4.6))
    rows = []
    shown = [m for m in METHODS + ['native'] if any(g['method'] == m for g in groups)]
    for i, method in enumerate(shown):
        gs = [g for g in groups if g['method'] == method]
        for j, g in enumerate(gs):
            lat = g['successfulLatency']
            x = i + (j - (len(gs) - 1) / 2) * .25
            ax.bar(x, lat['totalMsP50'] / 1000, .23, color=COLOR[method], alpha=[1, .7, .45][j % 3])
            ax.plot([x, x], [lat['totalMsP50'] / 1000, lat['totalMsP95'] / 1000], color='#333', lw=.8)
            q = g['perQuery'] or {}
            rows.append({'task': g['task'], 'method': method, 'successful': lat['n'], 'totalMsP50': round(lat['totalMsP50']), 'totalMsP95': round(lat['totalMsP95']), 'firstAnswerMsP50': lat['firstAnswerMsP50'] and round(lat['firstAnswerMsP50']), 'meanModelRequestsPerQuery': q.get('requests') and round(q['requests'], 3), 'meanInputTokens': q.get('inputTokens') and round(q['inputTokens']), 'meanCachedTokens': q.get('cachedTokens') and round(q['cachedTokens'])})
        reqs = [g['perQuery']['requests'] for g in gs if g['perQuery']]
        ax2.bar(i, sum(reqs) / len(reqs), color=COLOR[method])
    ax.set_xticks(range(len(shown)), [LABEL[m] for m in shown], fontsize=8)
    ax.set_ylabel('端到端总耗时 p50（线至 p95）/ s')
    ax2.set_xticks(range(len(shown)), [LABEL[m] for m in shown], fontsize=8)
    ax2.set_ylabel('每题模型/向量请求数（不含评分）')
    save(fig, '11-latency-calls', rows, src, 'successful responses only; bars per task in order clean/noise/multi; PageIndex includes Python SDK start-up; judge calls excluded')

    # 4. per-query cost and amortized index cost
    am = data['amortization']
    fig, ax = plt.subplots(figsize=(8, 4.6))
    rows = []
    for i, method in enumerate(METHODS):
        a = am[method]
        if a['perQueryCny'] is None:
            continue
        at = a['totalPerQueryAt'] or {}
        for k, n in enumerate(('1', '10', '100')):
            ax.bar(i + (k - 1) * .25, at.get(n, a['perQueryCny']) * 100, .23, color=COLOR[method], alpha=[1, .7, .45][k])
        rows.append({'method': method, 'indexCny': a['indexCny'], 'perQueryCny': round(a['perQueryCny'], 6), 'at1': at.get('1') and round(at['1'], 6), 'at10': at.get('10') and round(at['10'], 6), 'at100': at.get('100') and round(at['100'], 6)})
    ax.set_yscale('log')
    ax.set_xticks(range(len(METHODS)), [LABEL[m] for m in METHODS])
    ax.set_ylabel('每题费用（分，含建索引摊销）/ CNY cents, log')
    ax.set_title('左→右：摊到 1 / 10 / 100 次查询')
    save(fig, '11-cost-amortization', rows, src, 'usage x verified peak list price, clean + noise answers, judge excluded; index = one-off build cost; not a provider bill')


def cloud(data):
    src = 'experiments/12-kv-cache/results/cloud.json'
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(11, 4.6))
    rows, labels = [], []
    for i, r in enumerate(data['rows']):
        good = [x for x in r['records'] if x['status'] == 'ok']
        hit = r['cachedTokens'] / r['inputTokens'] if r['inputTokens'] else None
        color = '#009E73' if r['variant'] == 'stable' else '#D55E00'
        labels.append(f"{r['shape']} c{r['concurrency']} {r['variant']}")
        if hit is not None:
            ax.barh(i, hit * 100, color=color)
            # label every bar so a 0% hit reads as measured zero, not missing data
            ax.text(hit * 100 + 1, i, f'{hit * 100:.1f}%', va='center', fontsize=8)
        if r['firstAnswerMsP50'] is not None:
            ax2.barh(i, r['firstAnswerMsP50'], color=color)
            ax2.plot([r['firstAnswerMsP50'], r['firstAnswerMsP95']], [i, i], color='#333', lw=.8)
        rows.append({'shape': r['shape'], 'concurrency': r['concurrency'], 'variant': r['variant'], 'planned': r['planned'], 'ok': len(good), 'inputTokens': r['inputTokens'], 'cachedTokens': r['cachedTokens'], 'cachedShare': hit and round(hit, 4), 'firstAnswerMsP50': r['firstAnswerMsP50'], 'firstAnswerMsP95': r['firstAnswerMsP95']})
    for a in (ax, ax2):
        a.set_yticks(range(len(labels)), labels, fontsize=8)
        a.invert_yaxis()
    ax.set_xlabel('缓存命中 token 占比 / %')
    ax2.set_xlabel('最终回答首字 p50（线至 p95）/ ms')
    save(fig, '12-cloud-cache', rows, src, f"8 requests per condition; marker {data.get('markerTokens')} tokens for every nonce; provider billing cache, not KV memory; first request not guaranteed uncached")


def main():
    summary = ROOT / '11-pageindex/results/summary.json'
    data = json.loads(summary.read_text(encoding='utf8')) if summary.exists() else None
    if data and data.get('schemaVersion') == 2 and data['controlled']['groups']:
        pageindex(data)
    else:
        print('skip PageIndex figures: no measured summary')
    cloud_file = ROOT / '12-kv-cache/results/cloud.json'
    c = json.loads(cloud_file.read_text(encoding='utf8')) if cloud_file.exists() else None
    if c and c.get('rows'):
        cloud(c)
    else:
        print('skip cloud figure: no measured run')


if __name__ == '__main__':
    main()
