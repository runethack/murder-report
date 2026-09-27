#!/usr/bin/env python3
import sys
import os
import shutil
import subprocess

PROJECT_DIR = "/storage/emulated/10/murder"
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
try:
    os.chdir(PROJECT_DIR)
except Exception:
    pass


REQUIRED = {
    "requests": "requests>=2.31",
    "dns": "dnspython>=2.4",
    "phonenumbers": "phonenumbers>=8.13",
    "rich": "rich>=13.0",
    "cloudscraper": "cloudscraper>=1.2.71",
    "bs4": "beautifulsoup4>=4.12",
}

OPTIONAL = {
    "exifread": "exifread>=3.0",
}


def ensure_python_deps():
    missing = []
    for mod, pkg in REQUIRED.items():
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
    if missing:
        print("[*] pip: ставлю обязательные:")
        for p in missing:
            print(f"    - {p}")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])
            print("[+] Обязательные установлены.\n")
        except subprocess.CalledProcessError:
            print("[!] Не удалось поставить обязательные.")
            print(f"    Попробуй: {sys.executable} -m pip install " + " ".join(missing))
            sys.exit(1)

    opt_missing = []
    for mod, pkg in OPTIONAL.items():
        try:
            __import__(mod)
        except ImportError:
            opt_missing.append(pkg)
    if opt_missing:
        print("[*] pip: ставлю опциональные:")
        for p in opt_missing:
            print(f"    - {p}")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", *opt_missing])
            print("[+] Опциональные установлены.\n")
        except subprocess.CalledProcessError:
            print("[!] Опциональные не установились.\n")


SYS_TOOLS = {
    "curl":    {"termux": "curl",     "apt": "curl",     "dnf": "curl",     "apk": "curl",     "brew": "curl"},
    "whois":   {"termux": "whois",    "apt": "whois",    "dnf": "whois",    "apk": "whois",    "brew": "whois"},
    "dig":     {"termux": "dnsutils", "apt": "dnsutils", "dnf": "bind-utils", "apk": "bind-tools", "brew": "bind"},
    "nmap":    {"termux": "nmap",     "apt": "nmap",     "dnf": "nmap",     "apk": "nmap",     "brew": "nmap"},
    "whatweb": {"termux": "whatweb",  "apt": "whatweb",  "dnf": None,       "apk": None,       "brew": "whatweb"},
    "wafw00f": {"termux": "wafw00f",  "apt": None,       "dnf": None,       "apk": None,       "brew": None},
    "httpx":   {"termux": "httpx",    "apt": None,       "dnf": None,       "apk": None,       "brew": None},
    "subfinder": {"termux": "subfinder", "apt": None,    "dnf": None,       "apk": None,       "brew": None},
    "nuclei":  {"termux": "nuclei",   "apt": None,       "dnf": None,       "apk": None,       "brew": None},
    "nikto":   {"termux": "nikto",    "apt": "nikto",    "dnf": "nikto",    "apk": None,       "brew": None},
}


def _detect_pkg_manager():
    if os.environ.get("TERMUX_VERSION") or shutil.which("pkg"):
        return "termux", ["pkg", "install", "-y"]
    for mgr, cmd in (("apt", ["apt-get", "install", "-y"]),
                     ("dnf", ["dnf", "install", "-y"]),
                     ("apk", ["apk", "add"]),
                     ("brew", ["brew", "install"])):
        if shutil.which(mgr):
            return mgr, cmd
    return None, None


def ensure_system_tools(auto=True):
    pkg_mgr, install_cmd = _detect_pkg_manager()
    have, missing = [], []
    for tool in SYS_TOOLS:
        if shutil.which(tool):
            have.append(tool)
        else:
            missing.append(tool)
    if have:
        print(f"[+] В PATH уже есть: {', '.join(have)}")
    if not missing:
        print("[+] Все системные инструменты на месте.\n")
        return
    print(f"[*] Нет в PATH: {', '.join(missing)}")
    if not pkg_mgr:
        print("[!] Пакетный менеджер не найден — использую Python-фолбэки.\n")
        return
    if not auto:
        return
    print(f"[*] Пакетный менеджер: {pkg_mgr}. Ставлю недостающее...\n")
    env = os.environ.copy()
    env["DEBIAN_FRONTEND"] = "noninteractive"
    installed, failed = [], []
    for tool in missing:
        pkg_name = SYS_TOOLS[tool].get(pkg_mgr)
        if not pkg_name:
            failed.append(tool)
            continue
        print(f"    - {tool} → {pkg_name}")
        try:
            subprocess.check_call(install_cmd + [pkg_name], env=env)
            installed.append(tool)
        except Exception:
            failed.append(tool)
    print()
    if installed:
        print(f"[+] Установлены: {', '.join(installed)}")
    if failed:
        print(f"[!] Не удалось поставить: {', '.join(failed)}")


ensure_python_deps()
ensure_system_tools(auto=True)

from m_util import (
    console, show_banner, show_menu, show_user_results,
    save_and_report, new_trail, ask, ask_int, clear,
    search_username_live,
)
import m_tools as tools


BANNER = r"""
 __    __     __  __     ______     _____     ______     ______    
/\ "-./  \   /\ \/\ \   /\  == \   /\  __-.  /\  ___\   /\  == \   
\ \ \-./\ \  \ \ \_\ \  \ \  __<   \ \ \/\ \ \ \  __\   \ \  __<   
 \ \_\ \ \_\  \ \_____\  \ \_\ \_\  \ \____-  \ \_____\  \ \_\ \_\ 
  \/_/  \/_/   \/_____/   \/_/ /_/   \/____/   \/_____/   \/_/ /_/ 
                                                                   
                                                 @@                                                 
                                                @@@@                                                
                            @@@                @@@@@                                                
                           @@@@@@@@@                                                                
                           @@@@@@@@@@@@@@@@@@@@@@@@@@@     @@@@                                     
                           @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@                                 
                          @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@                             
                          @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@                             
                          @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@                                 
                           @@@@@@@@@@@@@@@@  @@@@@@@@@      @@@@                                    
                           @@@@@@@@@@@@@       @@@@@@                                               
                            @@@@@@@@@@         @@@@@@                                               
                            @@@@@@@@@@         @@@@@@                                               
                             @@@@@@@@          @@@@@@                                               
                              @@@@@@@         %@@@@@@                                               
                               @@@@@@         @@@@@@@                                               
                                @@@@@         @@@@@@@                                               
                                  @@@@        @@@@@@@                                               
                                    @@        @@@@@@@                                               
                                              @@@@@@@                                               
                                              @@@@@@@                                               
                                              @@@@@@@                                               
                                              @@@@@@@                                               
                                              @@@@@@@                                               
                                              @@@@@@@                                               
                                              @@@@@@@                                               
                                              @@@@@@@                                               
                                              @@@@@@@                                               
                                              @@@@@@@                                               
                                              @@@@@@@                                               
                                              @@@@@@@                                               
                                              @@@@@@@                                               
                                              @@@@@@@                                               
                                              @@@@@@@                                               
                                              @@@@@@@                                               
                                                                                                    
                                              @@@@@@@                                               
                                              @@%##@@                                               
                                              @@@@@@@                                               
                                              @@@@@@@                                               
                                             @@@@@@@@                                               
                                             @@@@@@@@@                                              
                                             @@@@@@@@@                                              
                                             @@@@@@@@@                                              
                                             @@@@@@@@@                                              
                                            @@@@@@@@@@@                                             
                                            @@@@@@@@@@@                                             
                                           @@@@@@@@@@@@@                                            
                                             @@@@@@@@@                                              
                                               @@@@@                                                
                                                @@@                                                 
"""


QUICK_PATHS = [
    '/.env', '/.git/config', '/.git/HEAD',
    '/admin', '/administrator', '/wp-admin', '/wp-login.php',
    '/api', '/api/v1', '/api/swagger.json', '/swagger.json', '/openapi.json',
    '/graphql', '/phpinfo.php', '/server-status',
]


def quick_pathbrute(base, ua, timeout_per_path=2, total_timeout=10):
    from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FutTimeout
    from rich.table import Table
    from rich import box

    found = []
    ex = ThreadPoolExecutor(max_workers=15)
    futs = [ex.submit(tools._probe_path, base, p, ua, timeout_per_path)
            for p in QUICK_PATHS]
    try:
        for f in as_completed(futs, timeout=total_timeout):
            try:
                path, code, size, ct, body = f.result(timeout=1)
            except Exception:
                continue
            if code in ('200', '201', '204', '301', '302', '307', '308',
                        '400', '401', '403', '405', '418', '429',
                        '500', '502', '503', '504'):
                found.append((code, path, size, ct))
    except FutTimeout:
        console.print(f"[yellow]быстрый pathbrute: таймаут {total_timeout}s[/yellow]")
    finally:
        ex.shutdown(wait=False, cancel_futures=True)

    found.sort(key=lambda x: (x[0], x[1]))

    if found:
        t = Table(title=f"[bold red]Быстрый скан путей ({len(found)})[/bold red]",
                  box=box.SIMPLE_HEAVY, border_style="red", show_lines=False)
        t.add_column("Код", style="bold red", width=5)
        t.add_column("Размер", justify="right", width=9)
        t.add_column("Путь", style="red", overflow="fold")
        t.add_column("Заметка", overflow="fold")
        for code, path, size, ct in found:
            note = []
            if path in tools.DANGEROUS_PATHS:
                note.append(f"[bold red]!! {tools.DANGEROUS_PATHS[path]}[/bold red]")
            t.add_row(code, size, path, ' '.join(note))
        console.print(t)
    else:
        console.print("[yellow]быстрый скан: ничего важного не найдено[/yellow]")

    return {
        'base': base,
        'user_agent': ua,
        'total': len(QUICK_PATHS),
        'found': [
            {'code': code, 'path': path, 'size': size, 'ct': ct,
             'dangerous': tools.DANGEROUS_PATHS.get(path),
             'spa_suspected': False, 'body_snippet': ''}
            for code, path, size, ct in found
        ],
    }


def _ask_mode():
    console.print("[bold red]Режим:[/bold red] "
                  "[green]1[/green] — быстро (15 ключевых путей, ~10 сек), "
                  "[yellow]2[/yellow] — полно (40 путей + crawl + auth, ~1 мин)")
    mode = ask("[bold red]Выбор[/bold red]", default="1")
    return mode.strip() == "2"


COMMON_EMAIL_DOMAINS = [
    'gmail.com', 'yandex.ru', 'mail.ru', 'inbox.ru', 'list.ru',
    'bk.ru', 'ya.ru', 'rambler.ru', 'outlook.com', 'hotmail.com',
    'live.com', 'icloud.com', 'me.com', 'proton.me', 'protonmail.com',
    'yahoo.com', 'aol.com', 'zoho.com', 'gmx.com', 'fastmail.com',
    'vk.com', 'ok.ru',
]


def _gen_local_parts(seed):
    import re
    s = seed.strip().lower()
    if not s:
        return []
    cleaned = re.sub(r'[^a-z0-9._\-]', '', s)
    if not cleaned:
        return []

    parts = [p for p in re.split(r'[._\-]+', cleaned) if p]
    local = set()
    local.add(cleaned)
    local.add(cleaned.replace('.', ''))
    local.add(cleaned.replace('-', ''))
    local.add(cleaned.replace('_', ''))

    if len(parts) >= 2:
        first, last = parts[0], parts[-1]
        local.add(f"{first}.{last}")
        local.add(f"{first}{last}")
        local.add(f"{first}_{last}")
        local.add(f"{first}-{last}")
        local.add(f"{first[0]}{last}")
        local.add(f"{first}{last[0]}")
        local.add(f"{last}.{first}")
        local.add(f"{last}{first}")

    for base in list(local)[:6]:
        for n in ('1', '7', '77', '99', '01', '007', '2024', '2025'):
            local.add(f"{base}{n}")

    return sorted(p for p in local if 2 <= len(p) <= 40)


def generate_emails(seed, domains=None, limit=60):
    domains = domains or COMMON_EMAIL_DOMAINS
    locals_ = _gen_local_parts(seed)
    out = []
    for d in domains:
        for l in locals_:
            out.append(f"{l}@{d}")
            if len(out) >= limit:
                return out
    return out


def _validate_emails_live(emails, workers=15):
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def check(em):
        mx = tools.email_mx(em)
        return {
            'email': em,
            'valid_syntax': tools.email_validate(em),
            'mx': mx,
            'has_mx': bool(mx),
            'disposable': tools.email_is_disposable(em),
        }

    results = []
    total = len(emails)
    done = 0
    status = console.status(f"[red]Проверяю {total} вариантов...[/red]", spinner="dots")
    status.start()
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {pool.submit(check, em): em for em in emails}
            for f in as_completed(futs):
                done += 1
                try:
                    r = f.result()
                except Exception as e:
                    r = {'email': futs[f], 'error': str(e), 'has_mx': False}
                status.update(f"[red]{done}/{total}[/red] проверено")
                results.append(r)
    finally:
        status.stop()
    return results


def _render_real_emails(real):
    from rich.table import Table
    from rich import box

    src_t = Table(title="[bold red]Источники[/bold red]",
                  box=box.SIMPLE_HEAVY, border_style="red")
    src_t.add_column("Источник", style="bold red", width=12)
    src_t.add_column("Профиль", style="red", overflow="fold")
    src_t.add_column("Email-ов", justify="right", width=10)
    for s in real.get('sources', []):
        prof = s.get('profile') or s.get('url') or ''
        if isinstance(prof, str) and len(prof) > 70:
            prof = prof[:67] + '...'
        src_t.add_row(s.get('source', '?'), str(prof), str(len(s.get('emails') or [])))
    console.print(src_t)

    emails = real.get('emails') or []
    if emails:
        t = Table(title=f"[bold red]Найденные email ({len(emails)})[/bold red]",
                  box=box.SIMPLE_HEAVY, border_style="red")
        t.add_column("Email", style="green", overflow="fold")
        t.add_column("MX", style="dim red", overflow="fold")
        t.add_column("Источник", style="dim")
        t.add_column("Grav", justify="center", width=5)
        for e in emails:
            mx = (e.get('mx') or ['—'])[0] if e.get('mx') else '—'
            grav = "[green]yes[/green]" if e.get('gravatar') else "[dim]no[/dim]"
            t.add_row(e.get('email', '?'), mx, ', '.join(e.get('sources') or []), grav)
        console.print(t)
    else:
        console.print("[yellow]Из публичных источников ничего не найдено[/yellow]")


def menu_username():
    username = ask("[bold red]Введите username[/bold red]")
    if not username.strip():
        console.print("[red]Пустой ввод[/red]")
        return
    console.print(f"\n[red]Ищу аккаунты:[/red] {username}\n")
    res = search_username_live(
        username, tools.USERNAME_SITES, tools._check_username_site, workers=15)
    trail = new_trail({"username": username})
    trail["findings"]["username"] = res
    show_user_results(res)

    console.print("\n[bold red]── Реальный поиск email по нику ──[/bold red]\n")
    with console.status("[red]Опрашиваю GitHub / GitLab / Gravatar / Keybase / PGP...[/red]"):
        real = tools.search_real_emails(username)
    _render_real_emails(real)
    trail["findings"]["emails_real"] = real

    console.print("\n[bold red]── Генерация возможных адресов ──[/bold red]\n")
    from rich.table import Table
    from rich import box
    gen_emails = generate_emails(username, limit=60)
    gen_results = []
    if gen_emails:
        console.print(f"[dim]Проверяю {len(gen_emails)} вариантов MX...[/dim]\n")
        gen_results = _validate_emails_live(gen_emails, workers=15)
        ok = [r for r in gen_results if r.get('has_mx')]
        t = Table(title=f"[bold red]Генерированные с рабочим MX ({len(ok)})[/bold red]",
                  box=box.SIMPLE_HEAVY, border_style="red")
        t.add_column("Email", style="green", overflow="fold")
        t.add_column("MX", style="dim red", overflow="fold")
        for r in ok[:40]:
            t.add_row(r['email'], ", ".join(r.get('mx') or [])[:60])
        console.print(t)
        trail["findings"]["emails_generated"] = gen_results

    save_and_report(trail, f"murder_username_{username}")


def menu_generate_emails():
    console.print("[red]Поиск email по нику / имени[/red]")
    seed = ask("[bold red]Ник / имя / username[/bold red]").strip()
    if not seed:
        console.print("[red]Пустой ввод[/red]")
        return

    console.print(f"\n[bold red]── Реальный поиск по {seed} ──[/bold red]\n")
    with console.status("[red]Опрашиваю GitHub / GitLab / Gravatar / Keybase / PGP...[/red]"):
        real = tools.search_real_emails(seed)
    _render_real_emails(real)

    console.print(f"\n[bold red]── Генерация возможных адресов ──[/bold red]\n")
    extra = ask("[bold red]Свой домен (через запятую, Enter — общие)[/bold red]",
                default="").strip()
    domains = None
    if extra:
        domains = [d.strip() for d in extra.split(',') if d.strip()]

    gen_emails = generate_emails(seed, domains=domains, limit=60)
    gen_results = []
    if gen_emails:
        console.print(f"[dim]Проверяю {len(gen_emails)} вариантов MX...[/dim]\n")
        gen_results = _validate_emails_live(gen_emails, workers=15)
        ok = [r for r in gen_results if r.get('has_mx')]
        from rich.table import Table
        from rich import box
        t = Table(title=f"[bold red]Генерированные с рабочим MX ({len(ok)})[/bold red]",
                  box=box.SIMPLE_HEAVY, border_style="red")
        t.add_column("Email", style="green", overflow="fold")
        t.add_column("MX", style="dim red", overflow="fold")
        for r in ok[:40]:
            t.add_row(r['email'], ", ".join(r.get('mx') or [])[:60])
        console.print(t)

    trail = new_trail({"email_seed": seed,
                       "email_domains": domains or COMMON_EMAIL_DOMAINS})
    trail["findings"]["emails_real"] = real
    if gen_results:
        trail["findings"]["emails_generated"] = gen_results
    save_and_report(trail, f"murder_emails_{seed}")


def _render_domain(res):
    from rich.table import Table
    from rich import box

    dns_t = Table(title="[bold red]DNS[/bold red]",
                  box=box.SIMPLE_HEAVY, border_style="red", show_lines=False)
    dns_t.add_column("Тип", style="bold red", width=6)
    dns_t.add_column("Значения", style="red")
    any_dns = False
    for rtype, vals in (res.get('dns') or {}).items():
        if vals:
            any_dns = True
            dns_t.add_row(rtype, "\n".join(str(v) for v in vals[:10]))
    if any_dns:
        console.print(dns_t)
    else:
        console.print("[yellow]DNS: пусто[/yellow]")

    wh = res.get('whois') or {}
    if wh.get('available'):
        parsed = wh.get('parsed') or {}
        src = wh.get('source', 'whois')
        if parsed:
            t = Table(title=f"[bold red]WHOIS ({src})[/bold red]",
                      box=box.SIMPLE_HEAVY, border_style="red")
            t.add_column("Поле", style="bold red")
            t.add_column("Значение", style="red")
            for k, vs in parsed.items():
                t.add_row(k, "\n".join(vs[:5]))
            console.print(t)

    d2 = res.get('2ip') or {}
    if d2.get('available'):
        fields = d2.get('fields') or {}
        if fields:
            t = Table(title="[bold red]2IP — домен[/bold red]",
                      box=box.SIMPLE_HEAVY, border_style="red")
            t.add_column("Поле", style="bold red")
            t.add_column("Значение", style="red")
            for k, v in fields.items():
                t.add_row(k, "\n".join(str(x) for x in v) if isinstance(v, list) else str(v))
            console.print(t)


def _render_ip(res, geo_multi=None):
    from rich.table import Table
    from rich import box

    g = res.get('geo') or {}
    t = Table(title="[bold red]IP — ip-api.com[/bold red]",
              box=box.SIMPLE_HEAVY, border_style="red")
    t.add_column("Поле", style="bold red")
    t.add_column("Значение", style="red")
    any_g = False
    for k, v in (('country', g.get('country')), ('region', g.get('regionName')),
                 ('city', g.get('city')), ('zip', g.get('zip')),
                 ('lat', g.get('lat')), ('lon', g.get('lon')),
                 ('timezone', g.get('timezone')), ('isp', g.get('isp')),
                 ('org', g.get('org')), ('as', g.get('as')),
                 ('reverse', g.get('reverse')), ('proxy', g.get('proxy')),
                 ('hosting', g.get('hosting'))):
        if v not in (None, '', []):
            any_g = True
            t.add_row(k, str(v))
    if any_g:
        console.print(t)
    else:
        console.print("[yellow]IP geo: пусто[/yellow]")

    wh = res.get('whois') or {}
    if wh.get('available'):
        parsed = wh.get('parsed') or {}
        src = wh.get('source', 'whois')
        if parsed:
            t = Table(title=f"[bold red]WHOIS IP ({src})[/bold red]",
                      box=box.SIMPLE_HEAVY, border_style="red")
            t.add_column("Поле", style="bold red")
            t.add_column("Значение", style="red")
            for k, vs in parsed.items():
                t.add_row(k, "\n".join(vs[:5]))
            console.print(t)

    ip2 = res.get('2ip') or {}
    if ip2.get('available'):
        fields = ip2.get('fields') or {}
        if fields:
            t = Table(title="[bold red]2IP — IP[/bold red]",
                      box=box.SIMPLE_HEAVY, border_style="red")
            t.add_column("Поле", style="bold red")
            t.add_column("Значение", style="red")
            for k, v in fields.items():
                t.add_row(k, "\n".join(str(x) for x in v) if isinstance(v, list) else str(v))
            console.print(t)

    if geo_multi:
        t = Table(title="[bold red]Гео-сервисы (мульти)[/bold red]",
                  box=box.SIMPLE_HEAVY, border_style="red")
        t.add_column("Источник", style="bold red", width=16)
        t.add_column("Статус", style="red")
        for item in geo_multi:
            if item.get('data'):
                status = "[green]ok[/green]"
            else:
                status = f"[red]{item.get('error', 'нет данных')}[/red]"
            t.add_row(item.get('source', '?'), status)
        console.print(t)


def _render_culture(pb, cr, ab, ext=None):
    from rich.table import Table
    from rich import box

    if isinstance(pb, dict) and pb.get('found'):
        t = Table(title=f"[bold red]Пути ({len(pb['found'])})[/bold red]",
                  box=box.SIMPLE_HEAVY, border_style="red", show_lines=False)
        t.add_column("Код", style="bold red", width=5)
        t.add_column("Размер", justify="right", width=9)
        t.add_column("Путь", style="red", overflow="fold")
        t.add_column("Тип", style="dim", width=18)
        t.add_column("Заметка", overflow="fold")
        for item in pb['found'][:60]:
            note = []
            if item.get('dangerous'):
                note.append(f"[bold red]!! {item['dangerous']}[/bold red]")
            if item.get('spa_suspected'):
                note.append("[dim]SPA[/dim]")
            ct = (item.get('ct') or '').split(';')[0][:18]
            t.add_row(item['code'], item['size'], item['path'], ct, ' '.join(note))
        console.print(t)
    elif isinstance(pb, dict) and pb.get('note'):
        console.print(f"[yellow]Пути: {pb['note']}[/yellow]")
    elif isinstance(pb, dict):
        console.print("[yellow]Пути: ничего не найдено[/yellow]")

    if isinstance(cr, dict):
        sources = cr.get('sources') or []
        checked = cr.get('checked') or []
        if sources or checked:
            console.print(f"[green]robots/sitemap источников:[/green] {len(sources)}, "
                          f"путей проверено: {len(checked)}")
        elif cr.get('note'):
            console.print(f"[yellow]Crawl: {cr['note']}[/yellow]")

    if isinstance(ab, dict) and (ab.get('found') or ab.get('note') or ab.get('holes')):
        if ab.get('note'):
            console.print(f"[yellow]Auth: {ab['note']}[/yellow]")
        else:
            console.print(f"[green]authbrute: проверено {ab.get('total_checked', 0)}, "
                          f"отозвалось {len(ab.get('found') or [])}, "
                          f"дыр {len(ab.get('holes') or [])}[/green]")
        holes = ab.get('holes') or []
        if holes:
            t = Table(title="[bold red]!! ДЫРЫ[/bold red]",
                      box=box.SIMPLE_HEAVY, border_style="red")
            t.add_column("Код", width=5)
            t.add_column("Размер", justify="right", width=9)
            t.add_column("Путь", style="red", overflow="fold")
            t.add_column("Content-Type", style="dim", overflow="fold")
            for h in holes:
                t.add_row(h.get('code', ''), h.get('size', ''),
                          h.get('path', ''), (h.get('ct') or '').split(';')[0])
            console.print(t)

    if ext:
        console.print("[green]внешние инструменты:[/green] " +
                      ', '.join(f"{k}({len(v)}b)" for k, v in ext.items()))


def menu_domain():
    domain = ask("[bold red]Введите домен[/bold red] (например example.com)")
    if not domain.strip():
        console.print("[red]Пустой ввод[/red]")
        return

    full = _ask_mode()

    console.print(f"\n[red]Анализирую домен:[/red] {domain}\n")
    trail = new_trail({"domain": domain})

    console.print("[dim]→ DNS / whois / RDAP / 2IP...[/dim]")
    try:
        res = tools.analyze_domain(domain)
        trail["findings"]["domain"] = res
        _render_domain(res)
    except Exception as e:
        console.print(f"[red]Базовый анализ домена упал: {e}[/red]")

    console.print(f"\n[bold red]── Авторазведка {domain} ──[/bold red]\n")

    ua = tools.CULTURE_USER_AGENTS['chrome_linux']
    base = tools._base_url(domain)
    real_host = domain
    try:
        real_host = tools._detect_real_host(
            domain, tools.CULTURE_USER_AGENTS['chrome_linux'])
        base = tools._base_url(real_host)
        console.print(f"[green]base:[/green] {base}")
    except Exception as e:
        console.print(f"[red]real_host упал: {e}[/red]")

    try:
        console.print("[dim]→ подбор UA...[/dim]")
        ua = tools._pick_best_ua(base)
        console.print(f"[green]UA:[/green] {ua[:60]}...\n")
    except Exception:
        pass

    if not full:
        console.print("[dim]→ быстрый скан путей...[/dim]")
        pb = quick_pathbrute(base, ua)
        trail["findings"]["pathbrute"] = pb
        _render_culture(pb, None, None)
    else:
        pb = cr = ab = None
        try:
            console.print("[dim]→ брутфорс путей...[/dim]")
            pb = tools.scan_pathbrute(domain, ua=ua, base=base, real_host=real_host)
            trail["findings"]["pathbrute"] = pb
        except Exception as e:
            console.print(f"[red]pathbrute упал: {e}[/red]")
        try:
            console.print("[dim]→ robots/sitemap...[/dim]")
            cr = tools.scan_crawl(domain, ua=ua, base=base, real_host=real_host)
            trail["findings"]["crawl"] = cr
        except Exception as e:
            console.print(f"[red]crawl упал: {e}[/red]")
        try:
            console.print("[dim]→ auth / OpenID...[/dim]")
            ab = tools.scan_authbrute(domain, ua=ua, base=base, real_host=real_host)
            trail["findings"]["authbrute"] = ab
        except Exception as e:
            console.print(f"[red]authbrute упал: {e}[/red]")
        _render_culture(pb, cr, ab)

    save_and_report(trail, f"murder_domain_{domain}")


def menu_email():
    email = ask("[bold red]Введите email[/bold red]")
    if "@" not in email:
        console.print("[red]Некорректный email[/red]")
        return
    console.print(f"\n[red]Анализирую email:[/red] {email}\n")
    res = tools.analyze_email(email)
    trail = new_trail({"email": email})
    trail["findings"]["email"] = res
    console.print(f"[green]Синтаксис валиден:[/green] {res['valid_syntax']}")
    console.print(f"[green]MX-серверы:[/green] {res['mx']}")
    console.print(f"[green]Disposable:[/green] {res['disposable']}")
    console.print(f"[green]Gravatar:[/green] {res['gravatar']['exists']}")
    if res["breach"].get("checked"):
        console.print(f"[green]Утечки:[/green] {res['breach']['breached']}")
        if res["breach"]["brands"]:
            console.print(f"[red]Бренды: {', '.join(res['breach']['brands'][:10])}[/red]")
    save_and_report(trail, f"murder_email_{email.replace('@','_at_')}")


def menu_phone():
    phone = ask("[bold red]Введите телефон[/bold red] (например +79001234567)")
    if not phone.strip():
        console.print("[red]Пустой ввод[/red]")
        return
    console.print(f"\n[red]Анализирую телефон:[/red] {phone}\n")
    res = tools.analyze_phone(phone, region=None)

    trail = new_trail({"phone": phone, "region_auto": res.get("region_code")})
    trail["findings"]["phone"] = res

    from rich.table import Table
    from rich import box

    if res.get("error"):
        console.print(f"[red]Ошибка: {res['error']}[/red]")
    else:
        t = Table(title="[bold red]Телефон[/bold red]",
                  box=box.SIMPLE_HEAVY, border_style="red")
        t.add_column("Поле", style="bold red")
        t.add_column("Значение", style="red")
        rows = [
            ("input",           res.get("input")),
            ("normalized",      res.get("normalized")),
            ("валиден",         "да" if res.get("valid") else "нет"),
            ("возможен",        "да" if res.get("possible") else "нет"),
            ("E164",            res.get("e164")),
            ("международный",   res.get("international")),
            ("национальный",    res.get("national")),
            ("RFC3966",         res.get("rfc3966")),
            ("код страны",      res.get("country_code")),
            ("код региона",     res.get("region_code") or "—"),
            ("регион",          res.get("region") or "—"),
            ("оператор",        res.get("carrier") or "—"),
            ("тип номера",      res.get("number_type") or "—"),
            ("таймзоны",        ", ".join(res.get("timezones") or []) or "—"),
            ("цифры",           res.get("digits")),
        ]
        for k, v in rows:
            if v not in (None, ""):
                t.add_row(k, str(v))
        console.print(t)

        links = res.get("links") or {}
        if links:
            link_t = Table(title="[bold red]Ссылки[/bold red]",
                           box=box.SIMPLE_HEAVY, border_style="red")
            link_t.add_column("Сервис", style="bold red")
            link_t.add_column("URL", style="red", overflow="fold")
            for name, url in links.items():
                if url:
                    link_t.add_row(name, url)
            console.print(link_t)

    console.print("\n[bold red]── WhatsApp ──[/bold red]\n")
    with console.status("[red]Проверяю наличие в WhatsApp...[/red]"):
        wa = tools.whatsapp_check(phone)
    trail["findings"]["whatsapp"] = wa
    if wa.get('registered') is True:
        console.print(f"[green]есть в WhatsApp[/green] ({wa.get('method')})")
    elif wa.get('registered') is False:
        console.print(f"[red]нет в WhatsApp[/red] ({wa.get('method')})")
    else:
        console.print(f"[yellow]не определено: {wa.get('error')}[/yellow]")
    if wa.get('redirect'):
        console.print(f"[dim]redirect: {wa['redirect']}[/dim]")

    console.print("\n[bold red]── Отзывы о номере ──[/bold red]\n")
    with console.status("[red]Опрашиваю whocall, nomernoi, kto-zvonil, tellows...[/red]"):
        reviews = tools.phone_reviews(phone)
    trail["findings"]["phone_reviews"] = reviews

    rev_t = Table(title="[bold red]Отзывы и рейтинг[/bold red]",
                  box=box.SIMPLE_HEAVY, border_style="red", show_lines=False)
    rev_t.add_column("Сайт", style="bold red", width=18)
    rev_t.add_column("Отзывов", justify="right", width=8)
    rev_t.add_column("Рейтинг", justify="right", width=8)
    rev_t.add_column("Теги", style="yellow", overflow="fold")
    rev_t.add_column("Статус", style="red", overflow="fold")
    for r in reviews:
        if r.get('error'):
            status = f"[red]{r['error']}[/red]"
        elif r.get('cloudflare'):
            status = "[yellow]CF[/yellow]"
        elif r.get('source') == 'no_reliable_data':
            status = "[yellow]нет данных[/yellow]"
        else:
            status = "[green]ok[/green]"
        tags = ", ".join(r.get('tags') or [])
        rev_t.add_row(
            r.get('site', '?'),
            str(r.get('reviews') or '—'),
            str(r.get('rating') or '—'),
            tags,
            status,
        )
    console.print(rev_t)

    save_and_report(trail, f"murder_phone_{phone.replace('+','').replace(' ','')}")


def menu_ip():
    ip = ask("[bold red]Введите IP[/bold red]")
    if not ip.strip():
        console.print("[red]Пустой ввод[/red]")
        return

    full = _ask_mode()

    console.print(f"\n[red]Анализирую IP:[/red] {ip}\n")
    trail = new_trail({"ip": ip})

    console.print("[dim]→ geo / RDAP / whois / reverse / 2IP...[/dim]")
    res = {"ip": ip, "geo": {}, "whois": {}, "reverse": [], "2ip": {}}
    try:
        res = tools.analyze_ip(ip)
        trail["findings"]["ip"] = res
    except Exception as e:
        console.print(f"[red]Базовый анализ IP упал: {e}[/red]")
        trail["findings"]["ip"] = res

    console.print(f"\n[bold red]── Авторазведка {ip} ──[/bold red]\n")

    ua = tools.CULTURE_USER_AGENTS['chrome_linux']
    base = tools._base_url(ip)
    real_host = ip
    try:
        real_host = tools._detect_real_host(
            ip, tools.CULTURE_USER_AGENTS['chrome_linux'])
        base = tools._base_url(real_host)
        if real_host != ip:
            console.print(f"[yellow]реальный хост:[/yellow] {real_host}")
        console.print(f"[green]base:[/green] {base}")
    except Exception as e:
        console.print(f"[red]real_host упал: {e}[/red]")

    try:
        console.print("[dim]→ подбор UA...[/dim]")
        ua = tools._pick_best_ua(base)
        console.print(f"[green]UA:[/green] {ua[:60]}...\n")
    except Exception:
        pass

    geo_multi = None
    try:
        console.print("[dim]→ гео по IP (мульти)...[/dim]")
        geo_multi = tools.scan_geo_ip(ip, ua=ua)
        trail["findings"]["geo_multi"] = geo_multi
    except Exception as e:
        console.print(f"[red]geo multi упал: {e}[/red]")

    _render_ip(res, geo_multi)

    if not full:
        console.print("[dim]→ быстрый скан путей...[/dim]")
        pb = quick_pathbrute(base, ua)
        trail["findings"]["pathbrute"] = pb
        _render_culture(pb, None, None)
    else:
        pb = cr = ab = ext = None
        try:
            console.print("[dim]→ брутфорс путей...[/dim]")
            pb = tools.scan_pathbrute(ip, ua=ua, base=base, real_host=real_host)
            trail["findings"]["pathbrute"] = pb
        except Exception as e:
            console.print(f"[red]pathbrute упал: {e}[/red]")
        try:
            console.print("[dim]→ robots/sitemap...[/dim]")
            cr = tools.scan_crawl(ip, ua=ua, base=base, real_host=real_host)
            trail["findings"]["crawl"] = cr
        except Exception as e:
            console.print(f"[red]crawl упал: {e}[/red]")
        try:
            console.print("[dim]→ auth / OpenID...[/dim]")
            ab = tools.scan_authbrute(ip, ua=ua, base=base, real_host=real_host)
            trail["findings"]["authbrute"] = ab
        except Exception as e:
            console.print(f"[red]authbrute упал: {e}[/red]")
        try:
            console.print("[dim]→ внешние инструменты...[/dim]")
            ext = tools.scan_external(ip, ip)
            trail["findings"]["external"] = ext
        except Exception as e:
            console.print(f"[red]external упал: {e}[/red]")
        _render_culture(pb, cr, ab, ext=ext)

    save_and_report(trail, f"murder_ip_{ip.replace('.','_')}")


def menu_image():
    path = ask("[bold red]Путь к изображению[/bold red]")
    if not os.path.exists(path):
        console.print("[red]Файл не найден[/red]")
        return
    console.print(f"\n[red]Анализирую изображение:[/red] {path}\n")
    res = {"exif": tools.image_exif(path),
           "reverse": tools.image_reverse_links(path)}
    trail = new_trail({"image": path})
    trail["findings"]["image"] = res
    if res["exif"].get("gps"):
        console.print(f"[green]GPS:[/green] {res['exif']['gps']}")
    else:
        console.print("[yellow]GPS в EXIF не найден[/yellow]")
    console.print(f"[green]Движок:[/green] {res['exif'].get('engine', 'none')}")
    console.print(f"[green]EXIF-полей:[/green] {len(res['exif'].get('exif', {}))}")
    save_and_report(trail, "murder_image")


def menu_complex():
    console.print("[red]Комплексный анализ: username + domain + email (Enter — пропустить)[/red]")
    username = ask("[bold red]username[/bold red]", default="")
    domain = ask("[bold red]domain[/bold red]", default="")
    email = ask("[bold red]email[/bold red]", default="")
    inputs = {}
    trail = None

    if username:
        console.print(f"\n[red]→ username:[/red] {username}")
        res = search_username_live(
            username, tools.USERNAME_SITES, tools._check_username_site, workers=15)
        inputs["username"] = username
        trail = new_trail(inputs)
        trail["findings"]["username"] = res
        show_user_results(res)

    if domain:
        console.print(f"\n[red]→ домен:[/red] {domain}")
        res = tools.analyze_domain(domain)
        inputs["domain"] = domain
        if trail is None:
            trail = new_trail(inputs)
        trail["findings"]["domain"] = res
        _render_domain(res)

        real_host = tools._detect_real_host(
            domain, tools.CULTURE_USER_AGENTS['chrome_linux'])
        base = tools._base_url(real_host)
        ua = tools._pick_best_ua(base)

        console.print("[dim]→ быстрый pathbrute...[/dim]")
        trail["findings"]["pathbrute"] = quick_pathbrute(base, ua)
        _render_culture(trail["findings"]["pathbrute"], None, None)

    if email:
        console.print(f"\n[red]→ email:[/red] {email}")
        res = tools.analyze_email(email)
        inputs["email"] = email
        if trail is None:
            trail = new_trail(inputs)
        trail["findings"]["email"] = res
        console.print(f"  MX: {res['mx']}")

    if trail is None:
        console.print("[red]Ничего не введено[/red]")
        return
    save_and_report(trail, "murder_complex")


def menu_open_report():
    files = [f for f in os.listdir(PROJECT_DIR) if f.startswith("murder") and f.endswith(".html")]
    if not files:
        console.print("[yellow]Отчётов не найдено[/yellow]")
        return
    files.sort(key=lambda x: os.path.getmtime(os.path.join(PROJECT_DIR, x)), reverse=True)
    from rich.table import Table
    from rich import box
    t = Table(title="[bold red]Последние отчёты[/bold red]",
              box=box.SIMPLE, border_style="red")
    t.add_column("№", style="bold red")
    t.add_column("Файл", style="red")
    for i, f in enumerate(files[:15], 1):
        t.add_row(str(i), f)
    console.print(t)
    idx = ask_int("[bold red]Номер для открытия (0 — отмена)[/bold red]", default=0)
    if idx <= 0 or idx > len(files):
        return
    path = os.path.join(PROJECT_DIR, files[idx - 1])
    console.print(f"[green]Файл:[/green] {path}")
    console.print("[yellow]Открой его вручную через файловый менеджер.[/yellow]")


def run_menu():
    while True:
        clear()
        show_banner(BANNER)
        show_menu()
        choice = ask("[bold red]Выбор[/bold red]", default="0")
        if choice == "0":
            console.print("[red]Выход.[/red]")
            break
        try:
            if choice == "1":
                menu_username()
            elif choice == "2":
                menu_domain()
            elif choice == "3":
                menu_email()
            elif choice == "4":
                menu_phone()
            elif choice == "5":
                menu_ip()
            elif choice == "6":
                menu_image()
            elif choice == "7":
                menu_complex()
            elif choice == "8":
                menu_open_report()
            elif choice == "9":
                menu_generate_emails()
            else:
                console.print("[red]Неизвестный пункт[/red]")
        except KeyboardInterrupt:
            console.print("\n[yellow]Прервано[/yellow]")
        except Exception as e:
            console.print(f"[red]Ошибка: {e}[/red]")
        ask("\n[red]Enter для продолжения[/red]", default="")


def main():
    import argparse
    p = argparse.ArgumentParser(prog="murder")
    p.add_argument("-u", "--username")
    p.add_argument("-d", "--domain")
    p.add_argument("-e", "--email")
    p.add_argument("-p", "--phone")
    p.add_argument("--region", default=None)
    p.add_argument("-i", "--ip")
    p.add_argument("--image")
    p.add_argument("--emails", help="поиск email по нику/имени")
    p.add_argument("--emails-domain", help="домен(ы) для генерации, через запятую")
    p.add_argument("-o", "--out", default="murder_report")
    p.add_argument("--full", action="store_true")
    args = p.parse_args()

    if any([args.username, args.domain, args.email, args.phone, args.ip,
            args.image, args.emails]):
        trail = new_trail({})
        if args.username:
            trail["input"]["username"] = args.username
            res = search_username_live(
                args.username, tools.USERNAME_SITES, tools._check_username_site,
                workers=15)
            trail["findings"]["username"] = res
            show_user_results(res)
            real = tools.search_real_emails(args.username)
            _render_real_emails(real)
            trail["findings"]["emails_real"] = real
        if args.emails:
            real = tools.search_real_emails(args.emails)
            trail["input"]["emails_seed"] = args.emails
            trail["findings"]["emails_real"] = real
            _render_real_emails(real)
            doms = None
            if args.emails_domain:
                doms = [d.strip() for d in args.emails_domain.split(',') if d.strip()]
            gen_emails = generate_emails(args.emails, domains=doms, limit=60)
            if gen_emails:
                gen_results = _validate_emails_live(gen_emails, workers=15)
                trail["findings"]["emails_generated"] = gen_results
                ok = [r for r in gen_results if r.get('has_mx')]
                from rich.table import Table
                from rich import box
                t = Table(title=f"[bold red]Генерированные с рабочим MX ({len(ok)})[/bold red]",
                          box=box.SIMPLE_HEAVY, border_style="red")
                t.add_column("Email", style="green", overflow="fold")
                t.add_column("MX", style="dim red", overflow="fold")
                for r in ok[:80]:
                    t.add_row(r['email'], ", ".join(r.get('mx') or [])[:60])
                console.print(t)
        if args.domain:
            trail["input"]["domain"] = args.domain
            trail["findings"]["domain"] = tools.analyze_domain(args.domain)
            _render_domain(trail["findings"]["domain"])
            real_host = tools._detect_real_host(
                args.domain, tools.CULTURE_USER_AGENTS['chrome_linux'])
            base = tools._base_url(real_host)
            ua = tools._pick_best_ua(base)
            if args.full:
                trail["findings"]["pathbrute"] = tools.scan_pathbrute(
                    args.domain, ua=ua, base=base, real_host=real_host)
                trail["findings"]["crawl"] = tools.scan_crawl(
                    args.domain, ua=ua, base=base, real_host=real_host)
                trail["findings"]["authbrute"] = tools.scan_authbrute(
                    args.domain, ua=ua, base=base, real_host=real_host)
                _render_culture(
                    trail["findings"]["pathbrute"],
                    trail["findings"]["crawl"],
                    trail["findings"]["authbrute"],
                )
            else:
                trail["findings"]["pathbrute"] = quick_pathbrute(base, ua)
                _render_culture(trail["findings"]["pathbrute"], None, None)
        if args.email:
            trail["input"]["email"] = args.email
            trail["findings"]["email"] = tools.analyze_email(args.email)
        if args.phone:
            trail["input"]["phone"] = args.phone
            trail["findings"]["phone"] = tools.analyze_phone(args.phone, args.region)
            trail["findings"]["whatsapp"] = tools.whatsapp_check(args.phone)
            trail["findings"]["phone_reviews"] = tools.phone_reviews(args.phone)
        if args.ip:
            trail["input"]["ip"] = args.ip
            trail["findings"]["ip"] = tools.analyze_ip(args.ip)
            real_host = tools._detect_real_host(
                args.ip, tools.CULTURE_USER_AGENTS['chrome_linux'])
            base = tools._base_url(real_host)
            ua = tools._pick_best_ua(base)
            trail["findings"]["geo_multi"] = tools.scan_geo_ip(args.ip, ua=ua)
            _render_ip(trail["findings"]["ip"], trail["findings"]["geo_multi"])
            if args.full:
                trail["findings"]["pathbrute"] = tools.scan_pathbrute(
                    args.ip, ua=ua, base=base, real_host=real_host)
                trail["findings"]["crawl"] = tools.scan_crawl(
                    args.ip, ua=ua, base=base, real_host=real_host)
                trail["findings"]["authbrute"] = tools.scan_authbrute(
                    args.ip, ua=ua, base=base, real_host=real_host)
                trail["findings"]["external"] = tools.scan_external(args.ip, args.ip)
                _render_culture(
                    trail["findings"]["pathbrute"],
                    trail["findings"]["crawl"],
                    trail["findings"]["authbrute"],
                    ext=trail["findings"]["external"],
                )
            else:
                trail["findings"]["pathbrute"] = quick_pathbrute(base, ua)
                _render_culture(trail["findings"]["pathbrute"], None, None)
        if args.image:
            trail["input"]["image"] = args.image
            trail["findings"]["image"] = {
                "exif": tools.image_exif(args.image),
                "reverse": tools.image_reverse_links(args.image),
            }
        save_and_report(trail, args.out)
    else:
        run_menu()


if __name__ == "__main__":
    main()()