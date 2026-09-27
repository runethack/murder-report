import re
import time
import random
import json
import html as html_mod
from datetime import datetime, timezone
from urllib.parse import urlparse
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt
from rich import box

console = Console()

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36",
]

_last_request = {}

try:
    import cloudscraper
    HAS_CLOUDSCRAPER = True
except ImportError:
    HAS_CLOUDSCRAPER = False

_cloudscraper_instance = None


def _get_cloudscraper():
    global _cloudscraper_instance
    if _cloudscraper_instance is None and HAS_CLOUDSCRAPER:
        try:
            _cloudscraper_instance = cloudscraper.create_scraper(
                browser={'browser': 'chrome', 'platform': 'linux', 'mobile': False},
                delay=2,
            )
        except Exception:
            _cloudscraper_instance = None
    return _cloudscraper_instance


def _throttle(host, min_interval=1.0):
    now = time.time()
    last = _last_request.get(host, 0)
    wait = min_interval - (now - last)
    if wait > 0:
        time.sleep(wait + random.uniform(0, 0.4))
    _last_request[host] = time.time()


def _build_session():
    s = requests.Session()
    retry = Retry(total=2, backoff_factor=1.0,
                  status_forcelist=[429, 500, 502, 503, 504],
                  allowed_methods=["GET", "HEAD"])
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s


SESSION = _build_session()


def is_cloudflare(text, headers=None):
    if not text:
        return False
    t = text.lower()
    markers = (
        'cf-browser-verification', 'cf-chl-', 'just a moment',
        'attention required! | cloudflare',
        'checking your browser before accessing',
        'cf_chl_opt', '__cf_chl', 'cloudflare ray id', 'error 1020',
    )
    if any(m in t for m in markers):
        return True
    if headers:
        srv = (headers.get('Server') or '').lower()
        if 'cloudflare' in srv:
            return True
    return False


def http_get(url, timeout=12, headers=None, allow_redirects=True, throttle=1.0,
             use_cloudscraper=True, **kw):
    host = urlparse(url).netloc
    _throttle(host, throttle)
    h = {"User-Agent": random.choice(USER_AGENTS),
         "Accept-Language": "en-US,en;q=0.9,ru;q=0.8"}
    if headers:
        h.update(headers)

    r = None
    try:
        r = SESSION.get(url, headers=h, timeout=timeout,
                        allow_redirects=allow_redirects, **kw)
    except requests.RequestException:
        r = None

    if r is not None and not is_cloudflare(r.text or '', r.headers):
        return r

    scraper = _get_cloudscraper() if use_cloudscraper else None
    if scraper is not None:
        try:
            r2 = scraper.get(url, headers=h, timeout=timeout,
                             allow_redirects=allow_redirects, **kw)
            if r2 is not None:
                return r2
        except Exception:
            pass
    return r


def search_username_live(username, sites, check_fn, workers=15):
    from concurrent.futures import ThreadPoolExecutor, as_completed

    total = len(sites)
    results = []
    done = 0

    status = console.status(f"[red]Проверяю {total} площадок...[/red]", spinner="dots")
    status.start()
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {}
            for site, (tmpl, nf) in sites.items():
                futures[pool.submit(check_fn, site, tmpl, nf, username)] = site

            for f in as_completed(futures):
                site = futures[f]
                done += 1
                try:
                    r = f.result()
                except Exception as e:
                    r = {"site": site, "exists": None, "error": str(e)}

                ex = r.get("exists") if isinstance(r, dict) else None
                if ex is True:
                    mark = "[green]есть[/green]"
                elif ex == "maybe":
                    mark = "[yellow]может[/yellow]"
                elif ex is False:
                    mark = "[dim]нет[/dim]"
                else:
                    mark = "[red]ошибка[/red]"

                status.update(
                    f"[red]{done}/{total}[/red] проверено  "
                    f"[dim]→[/dim] [bold]{site}[/bold]: {mark}"
                )
                results.append(r)
    finally:
        status.stop()

    results.sort(key=lambda x: (x.get("exists") is not True,
                                x.get("exists") != "maybe",
                                x.get("site", "")))
    return results


def _esc(v):
    return html_mod.escape(str(v) if v is not None else '')


def _render_value(obj):
    if isinstance(obj, dict):
        rows = "".join(
            f"<tr><th>{_esc(k)}</th><td>{_render_value(v)}</td></tr>"
            for k, v in obj.items()
        )
        return f"<table class='kv'>{rows}</table>"
    if isinstance(obj, list):
        if not obj:
            return "<span class='muted'>—</span>"
        if all(not isinstance(i, (dict, list)) for i in obj):
            return "<ul class='list'>" + "".join(
                f"<li>{_esc(i)}</li>" for i in obj
            ) + "</ul>"
        return "<div class='nested'>" + "".join(
            f"<div class='nested-item'>{_render_value(i)}</div>" for i in obj
        ) + "</div>"
    if obj is True:
        return "<span class='ok'>true</span>"
    if obj is False:
        return "<span class='bad'>false</span>"
    if obj is None:
        return "<span class='muted'>null</span>"
    return _esc(obj)


def _section(title, content, count=None):
    badge = f"<span class='badge'>{count}</span>" if count is not None else ""
    return f"""
    <section class="card">
      <h2>{_esc(title)} {badge}</h2>
      <div class="card-body">{content}</div>
    </section>
    """


def report_to_json(data, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


def _build_tabs(findings):
    sections = []

    def add(tab_id, title, content_html):
        sections.append((tab_id, title, content_html))

    if 'domain' in findings:
        d = findings['domain']
        parts = []
        if d.get('dns'):
            rows = "".join(
                f"<tr><th>{_esc(k)}</th><td>{_render_value(v)}</td></tr>"
                for k, v in d['dns'].items() if v
            )
            parts.append(_section("DNS", f"<table class='kv'>{rows}</table>"))
        if d.get('dig_short', {}).get('available'):
            parts.append(_section("dig +short", _render_value(d['dig_short'].get('records', {}))))
        if d.get('whois', {}).get('available'):
            src = d['whois'].get('source', 'whois')
            parts.append(_section(f"WHOIS ({src})", _render_value(d['whois'].get('parsed', {}))))
        if d.get('2ip', {}).get('available'):
            parts.append(_section("2IP — домен", _render_value(d['2ip'].get('fields', {}))))
        if d.get('subdomains'):
            parts.append(_section("Субдомены (crt.sh)",
                                  _render_value(d['subdomains']),
                                  count=len(d['subdomains'])))
        add("tab-domain", "Домен", "".join(parts))

    if 'ip' in findings:
        ip = findings['ip']
        parts = []
        if ip.get('geo'):
            parts.append(_section("Гео (ip-api.com)", _render_value(ip['geo'])))
        if ip.get('whois', {}).get('available'):
            src = ip['whois'].get('source', 'whois')
            parts.append(_section(f"WHOIS IP ({src})", _render_value(ip['whois'].get('parsed', {}))))
        if ip.get('2ip', {}).get('available'):
            parts.append(_section("2IP — IP", _render_value(ip['2ip'].get('fields', {}))))
        if ip.get('reverse'):
            parts.append(_section("Reverse DNS", _render_value(ip['reverse'])))
        if findings.get('geo_multi'):
            rows = []
            for item in findings['geo_multi']:
                status = "ok" if item.get('data') else item.get('error', 'нет данных')
                cls = "ok" if item.get('data') else "bad"
                rows.append(
                    f"<tr><th>{_esc(item.get('source','?'))}</th>"
                    f"<td><span class='{cls}'>{_esc(status)}</span></td></tr>"
                )
            parts.append(_section("Гео-сервисы (мульти)",
                                  f"<table class='kv'>{''.join(rows)}</table>"))
        add("tab-ip", "IP", "".join(parts))

    if 'pathbrute' in findings:
        pb = findings['pathbrute'] or {}
        found = pb.get('found', [])
        if found:
            rows = []
            for item in found:
                note = []
                if item.get('dangerous'):
                    note.append(f"<span class='bad'>!! {_esc(item['dangerous'])}</span>")
                if item.get('spa_suspected'):
                    note.append("<span class='muted'>SPA</span>")
                rows.append(
                    "<tr>"
                    f"<td class='mono'>{_esc(item.get('code',''))}</td>"
                    f"<td class='num'>{_esc(item.get('size',''))}</td>"
                    f"<td class='mono path'>{_esc(item.get('path',''))}</td>"
                    f"<td class='mono muted'>{(_esc(item.get('ct','')) or '').split(';')[0]}</td>"
                    f"<td>{' '.join(note)}</td>"
                    "</tr>"
                )
            content = (
                "<table class='grid'>"
                "<thead><tr><th>Код</th><th>Размер</th><th>Путь</th>"
                "<th>Content-Type</th><th>Заметка</th></tr></thead>"
                f"<tbody>{''.join(rows)}</tbody></table>"
            )
        else:
            content = f"<p class='muted'>{_esc(pb.get('note', 'ничего не найдено'))}</p>"
        add("tab-paths", f"Пути ({len(found)})", content)

    if 'authbrute' in findings:
        ab = findings['authbrute'] or {}
        parts = []
        holes = ab.get('holes', [])
        if holes:
            rows = "".join(
                "<tr>"
                f"<td class='mono'>{_esc(h.get('code',''))}</td>"
                f"<td class='num'>{_esc(h.get('size',''))}</td>"
                f"<td class='mono path'>{_esc(h.get('path',''))}</td>"
                f"<td class='mono muted'>{(_esc(h.get('ct','')) or '').split(';')[0]}</td>"
                "</tr>"
                for h in holes
            )
            parts.append(_section(
                "!! ДЫРЫ: 200 без авторизации",
                "<table class='grid'><thead><tr><th>Код</th><th>Размер</th>"
                "<th>Путь</th><th>CT</th></tr></thead>"
                f"<tbody>{rows}</tbody></table>",
                count=len(holes)))
        found = ab.get('found', [])
        if found:
            rows = "".join(
                "<tr>"
                f"<td class='mono'>{'auth' if f.get('is_auth') else 'prot'}</td>"
                f"<td class='mono'>{_esc(f.get('code',''))}</td>"
                f"<td class='num'>{_esc(f.get('size',''))}</td>"
                f"<td class='mono path'>{_esc(f.get('path',''))}</td>"
                "</tr>"
                for f in found
            )
            parts.append(_section(
                "Все ответившие роуты",
                "<table class='grid'><thead><tr><th>Тип</th><th>Код</th>"
                "<th>Размер</th><th>Путь</th></tr></thead>"
                f"<tbody>{rows}</tbody></table>",
                count=len(found)))
        if not parts:
            parts.append("<p class='muted'>ничего не найдено</p>")
        add("tab-auth", f"Auth/OpenID ({len(found)})", "".join(parts))

    if 'crawl' in findings:
        cr = findings['crawl'] or {}
        parts = []
        sources = cr.get('sources', [])
        for s in sources:
            if s.get('source') in ('robots.txt', 'sitemap-link'):
                parts.append(_section(
                    s.get('source', ''),
                    f"<pre class='pre'>{_esc(s.get('content',''))}</pre>"))
        checked = cr.get('checked', [])
        if checked:
            rows = "".join(
                "<tr>"
                f"<td class='mono'>{_esc(c.get('code',''))}</td>"
                f"<td class='num'>{_esc(c.get('size',''))}</td>"
                f"<td class='mono path'>{_esc(c.get('path',''))}</td>"
                "</tr>"
                for c in checked
            )
            parts.append(_section(
                "Проверенные пути",
                "<table class='grid'><thead><tr><th>Код</th><th>Размер</th>"
                "<th>Путь</th></tr></thead>"
                f"<tbody>{rows}</tbody></table>",
                count=len(checked)))
        if not parts:
            parts.append("<p class='muted'>ничего не найдено</p>")
        add("tab-crawl", "Crawl", "".join(parts))

    if 'username' in findings:
        items = findings['username'] or []
        rows = []
        for r in items:
            ex = r.get('exists')
            if ex is True:
                st, cls = "есть", "ok"
            elif ex == "maybe":
                st, cls = "может быть", "warn"
            elif ex is False:
                st, cls = "нет", "muted"
            else:
                st, cls = "ошибка", "bad"
            link = r.get('url', '')
            url_html = f"<a href='{_esc(link)}' target='_blank' rel='noopener'>{_esc(link)}</a>" if link else ""
            rows.append(
                "<tr>"
                f"<td>{_esc(r.get('site',''))}</td>"
                f"<td><span class='{cls}'>{st}</span></td>"
                f"<td class='mono'>{url_html}</td>"
                "</tr>"
            )
        add("tab-username",
            f"Username ({len(items)})",
            "<table class='grid'><thead><tr><th>Сайт</th><th>Статус</th>"
            "<th>URL</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>")

    if 'emails_real' in findings or 'emails_generated' in findings:
        parts = []
        real = findings.get('emails_real') or {}
        real_emails = real.get('emails') or []

        if real_emails:
            rows = []
            for e in real_emails:
                mx = (e.get('mx') or ['—'])[0] if e.get('mx') else '—'
                grav = "<span class='ok'>yes</span>" if e.get('gravatar') else "<span class='muted'>no</span>"
                rows.append(
                    "<tr>"
                    f"<td class='mono'>{_esc(e.get('email',''))}</td>"
                    f"<td class='mono muted'>{_esc(mx)}</td>"
                    f"<td class='mono muted'>{_esc(', '.join(e.get('sources') or []))}</td>"
                    f"<td>{grav}</td>"
                    "</tr>"
                )
            parts.append(_section(
                "Реальные (из публичных источников)",
                "<table class='grid'><thead><tr>"
                "<th>Email</th><th>MX</th><th>Источник</th><th>Grav</th>"
                "</tr></thead>"
                f"<tbody>{''.join(rows)}</tbody></table>",
                count=len(real_emails)))

        srcs = real.get('sources') or []
        if srcs:
            rows = "".join(
                f"<tr><th>{_esc(s.get('source','?'))}</th>"
                f"<td class='mono'>{_esc(s.get('profile') or s.get('url') or '')}</td>"
                f"<td class='num'>{len(s.get('emails') or [])}</td></tr>"
                for s in srcs
            )
            parts.append(_section("Проверенные источники",
                                  f"<table class='kv'>{rows}</table>",
                                  count=len(srcs)))

        gen = findings.get('emails_generated') or []
        if gen:
            ok = [r for r in gen if r.get('has_mx')]
            if ok:
                rows = "".join(
                    "<tr>"
                    f"<td class='mono'>{_esc(r.get('email',''))}</td>"
                    f"<td class='mono muted'>{_esc(', '.join(r.get('mx') or []))}</td>"
                    f"<td class='mono'>{'<span class=&quot;bad&quot;>да</span>' if r.get('disposable') else ''}</td>"
                    "</tr>"
                    for r in ok[:200]
                )
                parts.append(_section(
                    "Генерированные (рабочий MX)",
                    "<table class='grid'><thead><tr>"
                    "<th>Email</th><th>MX</th><th>Disposable</th>"
                    "</tr></thead>"
                    f"<tbody>{rows}</tbody></table>",
                    count=len(ok)))

        if not parts:
            parts.append("<p class='muted'>Email не найдены</p>")

        add("tab-emails", "Email", "".join(parts))

    if 'email' in findings:
        add("tab-email", "Email", _render_value(findings['email']))

    if 'phone' in findings:
        parts = []
        parts.append(_render_value(findings['phone']))

        reviews = findings.get('phone_reviews') or []
        if reviews:
            rows = []
            for r in reviews:
                if r.get('error'):
                    status = f"<span class='bad'>{_esc(r['error'])}</span>"
                elif r.get('cloudflare'):
                    status = "<span class='warn'>CF</span>"
                elif r.get('source') == 'no_reliable_data':
                    status = "<span class='warn'>нет данных</span>"
                else:
                    status = "<span class='ok'>ok</span>"
                tags = r.get('tags') or []
                tags_html = " ".join(
                    f"<span class='bad'>{_esc(t)}</span>" for t in tags
                ) if tags else "<span class='muted'>—</span>"
                url = r.get('url') or ''
                rows.append(
                    "<tr>"
                    f"<td>{_esc(r.get('site',''))}</td>"
                    f"<td class='num'>{_esc(r.get('reviews') or 0)}</td>"
                    f"<td class='num'>{_esc(r.get('rating') or '—')}</td>"
                    f"<td>{tags_html}</td>"
                    f"<td><a href='{_esc(url)}' target='_blank' rel='noopener' class='mono'>открыть</a></td>"
                    f"<td>{status}</td>"
                    "</tr>"
                )
            parts.append(_section(
                "Отзывы о номере",
                "<table class='grid'><thead><tr>"
                "<th>Сайт</th><th>Отзывов</th><th>Рейтинг</th>"
                "<th>Теги</th><th>URL</th><th>Статус</th>"
                "</tr></thead>"
                f"<tbody>{''.join(rows)}</tbody></table>",
                count=len(reviews)))

        add("tab-phone", "Phone", "".join(parts))

    if 'whatsapp' in findings:
        wa = findings['whatsapp'] or {}
        reg = wa.get('registered')
        if reg is True:
            reg_html = "<span class='ok'>есть в WhatsApp</span>"
        elif reg is False:
            reg_html = "<span class='bad'>нет в WhatsApp</span>"
        else:
            reg_html = "<span class='warn'>не определено</span>"

        rows = [f"<tr><th>Регистрация</th><td>{reg_html}</td></tr>"]
        if wa.get('method'):
            rows.append(f"<tr><th>Метод</th><td class='mono'>{_esc(wa['method'])}</td></tr>")
        if wa.get('status'):
            rows.append(f"<tr><th>HTTP</th><td class='mono'>{_esc(wa['status'])}</td></tr>")
        if wa.get('url'):
            rows.append(f"<tr><th>Запрос</th><td class='mono'>{_esc(wa['url'])}</td></tr>")
        if wa.get('redirect'):
            rows.append(f"<tr><th>Редирект</th><td class='mono'>{_esc(wa['redirect'])}</td></tr>")
        if wa.get('title'):
            rows.append(f"<tr><th>Title</th><td>{_esc(wa['title'])}</td></tr>")
        if wa.get('error'):
            rows.append(f"<tr><th>Ошибка</th><td class='bad'>{_esc(wa['error'])}</td></tr>")

        parts = [f"<table class='kv'>{''.join(rows)}</table>"]

        ph = findings.get('phone') or {}
        wa_digits = re.sub(r'\D', '', ph.get('digits') or ph.get('e164') or '')
        if wa_digits.startswith('8') and len(wa_digits) == 11:
            wa_digits = '7' + wa_digits[1:]
        if wa_digits:
            parts.append(_section("Ссылки WhatsApp",
                f"<table class='kv'>"
                f"<tr><th>Чат</th><td><a href='https://wa.me/{wa_digits}' target='_blank' rel='noopener'>wa.me/{wa_digits}</a></td></tr>"
                f"<tr><th>Web</th><td><a href='https://web.whatsapp.com/send?phone={wa_digits}' target='_blank' rel='noopener'>web.whatsapp.com/send</a></td></tr>"
                f"<tr><th>API</th><td><a href='https://api.whatsapp.com/send?phone={wa_digits}' target='_blank' rel='noopener'>api.whatsapp.com/send</a></td></tr>"
                "</table>"))

        add("tab-whatsapp", "WhatsApp", "".join(parts))

    if 'image' in findings:
        add("tab-image", "Image", _render_value(findings['image']))

    if 'external' in findings and findings['external']:
        ext = findings['external']
        parts = "".join(
            _section(k, f"<pre class='pre'>{_esc(v)}</pre>")
            for k, v in ext.items()
        )
        add("tab-external", "Внешние тулзы", parts)

    raw_json = html_mod.escape(json.dumps(
        findings, ensure_ascii=False, indent=2, default=str))
    add("tab-raw", "Raw JSON", f"<pre class='pre raw'>{raw_json}</pre>")

    if not sections:
        return "", "", "<p class='muted'>Нет данных</p>"

    inputs_html = ""
    labels_html = ""
    panels_html = ""
    for i, (tab_id, title, content_html) in enumerate(sections):
        checked = " checked" if i == 0 else ""
        inputs_html += (
            f"<input type='radio' name='murdertab' id='{tab_id}' "
            f"class='tab-radio'{checked}>"
        )
        labels_html += f"<label for='{tab_id}' class='tab'>{_esc(title)}</label>"
        panels_html += f"<div class='panel' data-panel='{tab_id}'>{content_html}</div>"

    return inputs_html, labels_html, panels_html


CSS = """
  :root {
    --bg: #0e0e11;
    --card: #16161b;
    --card2: #1c1c22;
    --border: #2a2a33;
    --fg: #e6e6ea;
    --muted: #8a8a94;
    --red: #ff4d4d;
    --red2: #cc0000;
    --green: #5ddc7c;
    --yellow: #ffce56;
    --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 16px; background: var(--bg); color: var(--fg);
    font-family: -apple-system, system-ui, "Segoe UI", Roboto, sans-serif;
    font-size: 14px; line-height: 1.4;
  }
  h1 { margin: 0 0 6px; color: var(--red); font-size: 22px; letter-spacing: 1px; }
  h2 { margin: 0 0 10px; font-size: 15px; color: var(--red); font-weight: 600; }
  header {
    background: linear-gradient(180deg, #1a1a20 0%, #14141a 100%);
    border: 1px solid var(--border); border-radius: 12px;
    padding: 14px 16px; margin-bottom: 14px;
  }
  .meta { color: var(--muted); font-size: 12px; margin-top: 4px; }
  .chips { margin-top: 10px; display: flex; flex-wrap: wrap; gap: 6px; }
  .chip {
    background: #202027; border: 1px solid var(--border);
    padding: 3px 8px; border-radius: 999px; font-size: 12px;
  }
  .chip b { color: var(--red); }
  .tab-radio { position: absolute; left: -9999px; opacity: 0; }
  .tabs {
    display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 12px;
    border-bottom: 1px solid var(--border); padding-bottom: 8px;
  }
  .tab {
    background: transparent; color: var(--muted); border: 1px solid transparent;
    padding: 7px 12px; border-radius: 8px; cursor: pointer;
    font-size: 13px; user-select: none; display: inline-block;
    transition: background .1s, color .1s;
  }
  .tab:hover { color: var(--fg); background: #1c1c22; }
  .panels { position: relative; }
  .panel { display: none; }

  #tab-domain:checked   ~ .tabs label[for="tab-domain"],
  #tab-ip:checked       ~ .tabs label[for="tab-ip"],
  #tab-paths:checked    ~ .tabs label[for="tab-paths"],
  #tab-auth:checked     ~ .tabs label[for="tab-auth"],
  #tab-crawl:checked    ~ .tabs label[for="tab-crawl"],
  #tab-username:checked ~ .tabs label[for="tab-username"],
  #tab-emails:checked   ~ .tabs label[for="tab-emails"],
  #tab-email:checked    ~ .tabs label[for="tab-email"],
  #tab-phone:checked    ~ .tabs label[for="tab-phone"],
  #tab-whatsapp:checked ~ .tabs label[for="tab-whatsapp"],
  #tab-image:checked    ~ .tabs label[for="tab-image"],
  #tab-external:checked ~ .tabs label[for="tab-external"],
  #tab-raw:checked      ~ .tabs label[for="tab-raw"] {
    color: #fff; background: var(--red2); border-color: var(--red2);
  }

  #tab-domain:checked   ~ .panels [data-panel="tab-domain"],
  #tab-ip:checked       ~ .panels [data-panel="tab-ip"],
  #tab-paths:checked    ~ .panels [data-panel="tab-paths"],
  #tab-auth:checked     ~ .panels [data-panel="tab-auth"],
  #tab-crawl:checked    ~ .panels [data-panel="tab-crawl"],
  #tab-username:checked ~ .panels [data-panel="tab-username"],
  #tab-emails:checked   ~ .panels [data-panel="tab-emails"],
  #tab-email:checked    ~ .panels [data-panel="tab-email"],
  #tab-phone:checked    ~ .panels [data-panel="tab-phone"],
  #tab-whatsapp:checked ~ .panels [data-panel="tab-whatsapp"],
  #tab-image:checked    ~ .panels [data-panel="tab-image"],
  #tab-external:checked ~ .panels [data-panel="tab-external"],
  #tab-raw:checked      ~ .panels [data-panel="tab-raw"] {
    display: block;
  }

  .card {
    background: var(--card); border: 1px solid var(--border);
    border-radius: 10px; padding: 12px 14px; margin-bottom: 12px;
  }
  .card-body { overflow-x: auto; }
  .badge {
    background: var(--red2); color: #fff; border-radius: 999px;
    padding: 1px 8px; font-size: 11px; font-weight: 700; margin-left: 6px;
  }
  table.kv { width: 100%; border-collapse: collapse; font-size: 13px; }
  table.kv th {
    text-align: left; color: var(--muted); font-weight: 500;
    padding: 5px 10px 5px 0; vertical-align: top; white-space: nowrap;
    border-bottom: 1px solid var(--border);
  }
  table.kv td {
    padding: 5px 0; vertical-align: top; border-bottom: 1px solid var(--border);
    word-break: break-word;
  }
  table.grid { width: 100%; border-collapse: collapse; font-size: 12.5px; }
  table.grid th {
    text-align: left; color: var(--muted); font-weight: 600;
    padding: 6px 8px; border-bottom: 1px solid var(--border);
    background: var(--card2);
  }
  table.grid td {
    padding: 5px 8px; border-bottom: 1px solid var(--border);
    vertical-align: top;
  }
  table.grid tr:hover td { background: #1b1b22; }
  td.mono, .mono { font-family: var(--mono); font-size: 12px; }
  td.num { text-align: right; font-family: var(--mono); }
  td.path { word-break: break-all; }
  .muted { color: var(--muted); }
  .ok { color: var(--green); font-weight: 600; }
  .bad { color: var(--red); font-weight: 600; }
  .warn { color: var(--yellow); font-weight: 600; }
  ul.list { margin: 0; padding-left: 18px; }
  ul.list li { margin: 2px 0; }
  .nested { display: flex; flex-direction: column; gap: 6px; }
  .nested-item {
    background: var(--card2); border: 1px solid var(--border);
    border-radius: 8px; padding: 8px 10px;
  }
  pre.pre {
    background: var(--card2); border: 1px solid var(--border);
    border-radius: 8px; padding: 10px; overflow-x: auto;
    font-family: var(--mono); font-size: 12px; line-height: 1.45;
    white-space: pre-wrap; word-break: break-word;
  }
  pre.raw { max-height: 70vh; }
  a { color: var(--red); text-decoration: none; }
  a:hover { text-decoration: underline; }
"""


def report_to_html(data, path):
    findings = data.get('findings', {}) if isinstance(data, dict) else {}
    inputs_html, labels_html, panels_html = _build_tabs(findings)

    head = data.get('input', {}) if isinstance(data, dict) else {}
    head_html = "".join(
        f"<span class='chip'><b>{_esc(k)}:</b> {_esc(v)}</span>"
        for k, v in head.items()
    )

    doc = (
        "<!doctype html>\n"
        '<html lang="ru">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>MURDER Report</title>\n"
        "<style>" + CSS + "</style>\n"
        "</head>\n"
        "<body>\n"
        "<header>\n"
        "<h1>MURDER Report</h1>\n"
        f'<div class="meta">Сгенерировано: {_esc(datetime.now(timezone.utc).isoformat())}</div>\n'
        f'<div class="chips">{head_html}</div>\n'
        "</header>\n"
        + inputs_html +
        '<div class="tabs">' + labels_html + "</div>\n"
        '<div class="panels">' + panels_html + "</div>\n"
        "</body>\n"
        "</html>"
    )

    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)


def save_and_report(trail, prefix="murder_report"):
    json_path = f"{prefix}.json"
    html_path = f"{prefix}.html"
    try:
        report_to_json(trail, json_path)
        report_to_html(trail, html_path)
        console.print(f"[green]JSON:[/green] {json_path}")
        console.print(f"[green]HTML:[/green] {html_path}")
    except Exception as e:
        console.print(f"[red]Не удалось сохранить отчёт: {e}[/red]")


def new_trail(inputs):
    return {
        "tool": "MURDER",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input": inputs,
        "findings": {},
    }


def show_banner(banner_text):
    console.print(f"[bold red]{banner_text}[/bold red]")
    console.print(Panel.fit("[bold red]MURDER[/bold red]", border_style="red"))


def show_menu():
    table = Table(title="[bold red]Главное меню[/bold red]", box=box.ROUNDED,
                  show_header=False, border_style="red")
    table.add_column("№", style="bold red", width=4)
    table.add_column("Действие", style="red")
    table.add_row("1", "Анализ по username")
    table.add_row("2", "Анализ по домену")
    table.add_row("3", "Анализ по email")
    table.add_row("4", "Анализ по телефону")
    table.add_row("5", "Анализ по IP")
    table.add_row("6", "Анализ изображения (EXIF)")
    table.add_row("7", "Комплексный анализ")
    table.add_row("8", "Открыть последний отчёт")
    table.add_row("9", "Поиск возможных email")
    table.add_row("0", "Выход")
    console.print(table)


def show_user_results(results):
    if not results:
        console.print("[yellow]Ничего не найдено (пустой результат)[/yellow]")
        return

    t = Table(title="[bold red]Найденные аккаунты[/bold red]",
              box=box.SIMPLE_HEAVY, border_style="red")
    t.add_column("Сайт", style="bold red")
    t.add_column("Статус")
    t.add_column("URL", style="dim red")

    found_count = 0
    maybe_count = 0
    err_count = 0
    for r in results:
        if not isinstance(r, dict):
            continue
        ex = r.get("exists")
        if ex is True:
            status = "[green]есть[/green]"
            found_count += 1
        elif ex == "maybe":
            status = "[yellow]может быть[/yellow]"
            maybe_count += 1
        elif ex is False:
            status = "[red]нет[/red]"
        else:
            status = "[dim]ошибка[/dim]"
            err_count += 1
        if r.get("cloudflare"):
            status += " [yellow]CF[/yellow]"
        t.add_row(r.get("site", "?"), status, r.get("url", ""))
    console.print(t)
    console.print(
        f"\n[green]есть: {found_count}[/green]  "
        f"[yellow]может быть: {maybe_count}[/yellow]  "
        f"[red]ошибка/сеть: {err_count}[/red]  "
        f"всего: {len(results)}\n"
    )


def ask(prompt_text, default=None):
    return Prompt.ask(prompt_text, default=default) if default is not None else Prompt.ask(prompt_text)


def ask_int(prompt_text, default=0):
    return IntPrompt.ask(prompt_text, default=default)


def clear():
    import os
    os.system("cls" if os.name == "nt" else "clear")