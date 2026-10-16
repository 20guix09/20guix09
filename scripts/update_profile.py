"""Generate README cards from public GitHub data. Python standard library only."""
import concurrent.futures
import datetime as dt
import json
import os
from pathlib import Path
import re
import urllib.request
from html import escape
from html.parser import HTMLParser
from urllib.parse import quote

USER = '20guix09'
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'assets' / 'profile'
GREEN, TEXT, MUTED, BG, BORDER = '#C5F265', '#F0F2EB', '#A8B29D', '#151813', '#35402D'


def fetch(url):
    headers = {'User-Agent': 'Guilherme-Profile-Cards', 'Accept': 'application/vnd.github+json'}
    if url.startswith('https://api.github.com/') and os.environ.get('GH_TOKEN'):
        headers['Authorization'] = 'Bearer ' + os.environ['GH_TOKEN']
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=40) as response:
        return response.read().decode('utf-8')


def api(path):
    return json.loads(fetch('https://api.github.com/' + path))


class Calendar(HTMLParser):
    def __init__(self):
        super().__init__()
        self.days, self.tooltips = {}, {}
        self.tip = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'td' and 'data-date' in a and 'data-level' in a:
            self.days[a['id']] = {'date': a['data-date'], 'level': int(a['data-level'])}
        if tag == 'tool-tip' and a.get('for', '').startswith('contribution-day-'):
            self.tip = a['for']

    def handle_data(self, data):
        if self.tip:
            self.tooltips[self.tip] = self.tooltips.get(self.tip, '') + data

    def handle_endtag(self, tag):
        if tag == 'tool-tip':
            self.tip = None


def text(x, y, value, size=16, color=TEXT, weight=400):
    return f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" font-weight="{weight}">{escape(str(value))}</text>'


def svg(title, w, h, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{escape(title, quote=True)}">'
            f'<title>{escape(title)}</title><rect x=".5" y=".5" width="{w-1}" height="{h-1}" rx="22" fill="{BG}" stroke="{BORDER}"/>'
            f'<g font-family="DejaVu Sans,Arial,sans-serif">{body}</g></svg>')


def build():
    repos = []
    page = 1
    while True:
        batch = api(f'users/{USER}/repos?per_page=100&page={page}')
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    own = [r for r in repos if not r['fork']]
    cal = Calendar()
    cal.feed(fetch(f'https://github.com/users/{USER}/contributions'))
    today = dt.datetime.now(dt.timezone.utc).date()
    cutoff = today - dt.timedelta(days=364)
    days = []
    for key, day in cal.days.items():
        date = dt.date.fromisoformat(day['date'])
        if cutoff <= date <= today:
            tip = cal.tooltips.get(key, '').strip()
            match = re.match(r'([\d,]+) contributions?\b', tip)
            if tip.startswith('No contributions'):
                count = 0
            elif match:
                count = int(match.group(1).replace(',', ''))
            else:
                raise ValueError('Contribution markup changed; previous cards preserved.')
            days.append(dict(day, count=count, date_obj=date))
    days.sort(key=lambda d: d['date'])
    if len(days) != 365:
        raise ValueError(f'Expected 365 calendar days, received {len(days)}; previous cards preserved.')
    def languages(repo):
        return api(f"repos/{USER}/{quote(repo['name'])}/languages")
    totals = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for result in pool.map(languages, own):
            for lang, amount in result.items():
                totals[lang] = totals.get(lang, 0) + amount
    if not totals:
        raise ValueError('No language data; previous cards preserved.')
    cards = {}
    contributions = sum(d['count'] for d in days)
    active = sum(d['count'] > 0 for d in days)
    for key, value, label in [('repos', len(repos), 'repositórios públicos'), ('contributions', contributions, 'contribuições · 365 dias'), ('days', active, 'dias com atividade')]:
        content = text(22, 32, 'GITHUB / DADOS PÚBLICOS', 11, GREEN, 700)
        content += text(22, 88, value, 43, TEXT, 700) + text(22, 118, label, 13, MUTED)
        cards[f'stats-{key}.svg'] = svg(f'{value} {label}', 270, 145, content)
    ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)
    shown = ranked[:5]
    if len(ranked) > 5:
        shown.append(('Outras', sum(v for _, v in ranked[5:])))
    total = sum(totals.values())
    colors = [GREEN, '#8FCB6A', '#5BAF80', '#58B6AF', '#7EA8D0', '#A8A0CC']
    body = text(28, 37, 'LINGUAGENS NO CÓDIGO', 13, GREEN, 700)
    body += text(28, 65, 'Distribuição por bytes · repositórios públicos próprios', 11, MUTED)
    x = 28
    for (_, value), color in zip(shown, colors):
        width = 504 * value / total
        body += f'<rect x="{x:.2f}" y="86" width="{width:.2f}" height="14" fill="{color}"/>'
        x += width
    for i, ((lang, value), color) in enumerate(zip(shown, colors)):
        x, y = 28 + (i % 2) * 264, 133 + (i // 2) * 32
        body += f'<circle cx="{x+5}" cy="{y-5}" r="5" fill="{color}"/>'
        body += text(x+18, y, f'{lang}  {100*value/total:.1f}%'.replace('.', ','), 14)
    cards['languages.svg'] = svg('Linguagens por bytes de código, não nível de domínio', 560, 222, body)
    body = text(28, 37, 'UM POUCO TODOS OS DIAS', 13, GREEN, 700)
    body += text(28, 65, f'{contributions} contribuições nos últimos 365 dias', 16)
    first = days[0]['date_obj']
    sunday = first - dt.timedelta(days=(first.weekday()+1) % 7)
    palette = ['#242C20', '#465E2C', '#6C913B', '#98C84E', GREEN]
    for day in days:
        index = (day['date_obj'] - sunday).days
        x, y = 28 + (index // 7) * 15, 88 + (index % 7) * 16
        body += f'<rect x="{x}" y="{y}" width="11" height="12" rx="3" fill="{palette[day["level"]]}"><title>{day["date"]}: {day["count"]} contribuições</title></rect>'
    body += text(28, 230, f'{days[0]["date_obj"]:%d/%m/%Y} — {today:%d/%m/%Y} · dados públicos do GitHub', 12, MUTED)
    body += text(651, 230, 'Menos', 11, MUTED)
    for i, color in enumerate(palette):
        body += f'<rect x="{695+i*17}" y="219" width="12" height="12" rx="3" fill="{color}"/>'
    body += text(787, 230, 'Mais', 11, MUTED)
    cards['activity.svg'] = svg('Calendário de contribuições públicas do GitHub', 854, 254, body)
    projects = [
        ('mirian', 'Mirian', 'Presença digital para serviços de beleza.', '01'),
        ('portfolio_Guilherme_Lima', 'Portfólio', 'Meu espaço para conectar design e código.', '02'),
        ('Madureira-Taekwondo', 'Madureira Taekwondo', 'Uma presença digital para o esporte.', '03'),
    ]
    by_name = {r['name']: r for r in repos}
    for name, title, desc, index in projects:
        r = by_name[name]
        body = text(28, 35, f'PROJETO {index}', 12, GREEN, 700)
        body += text(28, 78, title, 26, TEXT, 700)
        body += text(28, 110, desc, 15, MUTED)
        body += text(28, 155, r.get('language') or 'Código aberto', 13, GREEN)
        body += text(28, 188, 'VER REPOSITÓRIO', 11, MUTED, 700)
        cards[f'project-{index}.svg'] = svg(title + ' — abrir repositório', 560, 212, body)
    # Complete every request before replacing existing cards; failed fetches keep them intact.
    OUT.mkdir(parents=True, exist_ok=True)
    for name, contents in cards.items():
        temporary = OUT / (name + '.tmp')
        temporary.write_text(contents, encoding='utf-8')
        temporary.replace(OUT / name)
    print(f'Updated {len(cards)} cards: {len(repos)} repos, {contributions} contributions, {active} active days.')


if __name__ == '__main__':
    build()
