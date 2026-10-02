"""Free timing probe for the handbook: where the time of one HTTPS API call goes.

Runs `curl -4` against public API hosts WITHOUT any key (the server answers 401,
no model is called, no cost) and splits each request into DNS / TCP connect /
TLS handshake / waiting for the first byte. Only timings are kept; IP addresses
are not stored, just whether they fall in 198.18.0.0/15 (the fake-IP range a
local TUN proxy hands out, in which case DNS and TCP are answered locally).

  python experiments/report/api_timing.py
"""
import csv
import ipaddress
import os
import subprocess
import sys
import time
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

HERE = Path(__file__).resolve().parent
HOSTS = {
    'DeepSeek': 'https://api.deepseek.com/models',
    'DashScope': 'https://dashscope.aliyuncs.com/compatible-mode/v1/models',
}
SAMPLES = 5
FAKE_IP = ipaddress.ip_network('198.18.0.0/15')
FMT = '%{time_namelookup} %{time_connect} %{time_appconnect} %{time_starttransfer} %{http_code} %{http_version} %{remote_ip}'

for name in ('C:/Windows/Fonts/msyh.ttc', 'C:/Windows/Fonts/simhei.ttf'):
    if Path(name).exists():
        font_manager.fontManager.addfont(name)
        plt.rcParams['font.family'] = font_manager.FontProperties(fname=name).get_name()
        break
plt.rcParams.update({'svg.fonttype': 'none', 'axes.spines.top': False, 'axes.spines.right': False})


def probe(url):
    out = subprocess.run(['curl', '-4', '-s', '-o', os.devnull, '--max-time', '15', '-w', FMT, url], capture_output=True, text=True, check=True).stdout.split()
    dns, tcp, tls, ttfb = (float(x) * 1000 for x in out[:4])
    # curl reports cumulative times; convert to the duration of each stage
    return {'dnsMs': round(dns, 1), 'tcpMs': round(tcp - dns, 1), 'tlsMs': round(tls - tcp, 1), 'waitMs': round(ttfb - tls, 1), 'totalMs': round(ttfb, 1), 'httpCode': out[4], 'httpVersion': out[5], 'fakeIpTunProxy': ipaddress.ip_address(out[6]) in FAKE_IP}


TEXT = {
    'zh': {'stages': ['DNS 解析', 'TCP 连接', 'TLS 握手', '等待服务器首字节'], 'x': '毫秒 / ms',
           'title': '一次 HTTPS 请求的时间花在哪\n（未带 Key，服务器返回 401，不调用模型）',
           'foot': '每个地址 {n} 次新连接 · 单一网络环境的少量采样',
           'tun': '本机经 TUN 模式代理（fake-IP 198.18.0.0/15）：DNS 与 TCP 在本机完成，TLS 才真正连到服务器', 'direct': '直连，无代理', 'suffix': ''},
    'en': {'stages': ['DNS lookup', 'TCP connect', 'TLS handshake', 'Waiting for first byte'], 'x': 'milliseconds',
           'title': 'Where the time of one HTTPS request goes\n(no key sent: the server answers 401, no model is called)',
           'foot': '{n} fresh connections per host · a few samples from one network',
           'tun': 'Behind a local TUN-mode proxy (fake IPs in 198.18.0.0/15): DNS and TCP complete locally; only TLS reaches the server',
           'direct': 'Direct connection, no proxy', 'suffix': '.en'},
}


def plot(rows, lang):
    t = TEXT[lang]
    fig, ax = plt.subplots(figsize=(9, 4.6))
    keys = [('dnsMs', '#56B4E9'), ('tcpMs', '#009E73'), ('tlsMs', '#E69F00'), ('waitMs', '#D55E00')]
    labels = [f"{r['host']} #{r['sample']}" for r in rows]
    left = [0.0] * len(rows)
    for (key, color), label in zip(keys, t['stages']):
        vals = [float(r[key]) for r in rows]
        ax.barh(labels, vals, left=left, color=color, label=label)
        left = [a + b for a, b in zip(left, vals)]
    ax.invert_yaxis()
    ax.set_xlabel(t['x'])
    ax.set_title(t['title'], fontsize=11)
    ax.legend(fontsize=8, ncol=2, loc='lower right')
    tun = all(str(r['fakeIpTunProxy']) == 'True' for r in rows)
    foot = 'experiments/report/data/handbook-api-timing.csv · ' + t['foot'].format(n=SAMPLES)
    fig.text(.01, .01, foot + '\n' + (t['tun'] if tun else t['direct']), fontsize=7, color='#666')
    fig.tight_layout(rect=(0, .08, 1, 1))
    svg = HERE / 'figures' / f"handbook-api-timing{t['suffix']}.svg"
    fig.savefig(svg, metadata={'Date': None})
    if os.environ.get('PREVIEW_DIR'):
        fig.savefig(Path(os.environ['PREVIEW_DIR']) / f"handbook-api-timing{t['suffix']}.png", dpi=110)
    plt.close(fig)
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text(encoding='utf8').splitlines()) + '\n', encoding='utf8', newline='\n')
    return tun


def main():
    data = HERE / 'data' / 'handbook-api-timing.csv'
    if '--plot-only' in sys.argv:
        # redraw both language versions from the saved measurement, without probing again
        with data.open(encoding='utf8') as f:
            rows = list(csv.DictReader(f))
    else:
        rows = []
        for host, url in HOSTS.items():
            for i in range(SAMPLES):
                rows.append({'host': host, 'sample': i + 1, **probe(url)})
                time.sleep(1)
        with data.open('w', newline='', encoding='utf8') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n')
            w.writeheader()
            w.writerows(rows)
    tun = [plot(rows, lang) for lang in TEXT][0]
    print('\n'.join(f"{r['host']} #{r['sample']}: dns {r['dnsMs']} tcp {r['tcpMs']} tls {r['tlsMs']} wait {r['waitMs']} total {r['totalMs']} ({r['httpCode']}, HTTP/{r['httpVersion']})" for r in rows))
    print('fake-IP TUN proxy on every sample:', tun)


if __name__ == '__main__':
    main()
