#!/usr/bin/env python3
import sys
import os
import shutil
import subprocess

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
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
    "curl": {"termux": "curl", "apt": "curl", "dnf": "curl", "apk": "curl", "brew": "curl"},
    "whois": {"termux": "whois", "apt": "whois", "dnf": "whois", "apk": "whois", "brew": "whois"},
    "dig": {"termux": "dnsutils", "apt": "dnsutils", "dnf": "bind-utils", "apk": "bind-tools", "brew": "bind"},
    "nmap": {"termux": "nmap", "apt": "nmap", "dnf": "nmap", "apk": "nmap", "brew": "nmap"},
    "whatweb": {"termux": "whatweb", "apt": "whatweb", "dnf": None, "apk": None, "brew": "whatweb"},
    "wafw00f": {"termux": "wafw00f", "apt": None, "dnf": None, "apk": None, "brew": None},
    "httpx": {"termux": "httpx", "apt": None, "dnf": None, "apk": None, "brew": None},
    "subfinder": {"termux": "subfinder", "apt": None, "dnf": None, "apk": None, "brew": None},
    "nuclei": {"termux": "nuclei", "apt": None, "dnf": None, "apk": None, "brew": None},
    "nikto": {"termux": "nikto", "apt": "nikto", "dnf": "nikto", "apk": None, "brew": None},
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

# import project modules after dependency setup
from m_util import (
    console, show_banner, show_menu, show_user_results,
    save_and_report, new_trail, ask, ask_int, clear,
    search_username_live,
)
import m_tools as tools


def main():
    import argparse
    parser = argparse.ArgumentParser(prog="murder")
    parser.add_argument("-u", "--username")
    parser.add_argument("-d", "--domain")
    parser.add_argument("-e", "--email")
    parser.add_argument("-p", "--phone")
    parser.add_argument("--region", default=None)
    parser.add_argument("-i", "--ip")
    parser.add_argument("--image")
    parser.add_argument("--emails", help="поиск email по нику/имени")
    parser.add_argument("--emails-domain", help="домен(ы) для генерации, через запятую")
    parser.add_argument("-o", "--out", default="murder_report")
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()

    if any([args.username, args.domain, args.email, args.phone, args.ip,
            args.image, args.emails]):
        trail = new_trail({})

        if args.username:
            trail["input"]["username"] = args.username
            res = search_username_live(args.username, tools.USERNAME_SITES, tools._check_username_site, workers=15)
            trail["findings"]["username"] = res
            show_user_results(res)
            real = tools.search_real_emails(args.username)
            trail["findings"]["emails_real"] = real

        if args.emails:
            real = tools.search_real_emails(args.emails)
            trail["input"]["emails_seed"] = args.emails
            trail["findings"]["emails_real"] = real

        if args.domain:
            trail["input"]["domain"] = args.domain
            trail["findings"]["domain"] = tools.analyze_domain(args.domain)

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

        if args.image:
            trail["input"]["image"] = args.image
            trail["findings"]["image"] = {
                "exif": tools.image_exif(args.image),
                "reverse": tools.image_reverse_links(args.image),
            }

        save_and_report(trail, args.out)
        return

    while True:
        clear()
        show_banner("MURDER REPORT")
        show_menu()
        choice = ask("[bold red]Выбор[/bold red]", default="0")
        if choice == "0":
            console.print("[red]Выход.[/red]")
            break
        try:
            if choice == "1":
                username = ask("[bold red]Введите username[/bold red]")
                res = search_username_live(username, tools.USERNAME_SITES, tools._check_username_site, workers=15)
                trail = new_trail({"username": username})
                trail["findings"]["username"] = res
                show_user_results(res)
                save_and_report(trail, f"murder_username_{username}")
            elif choice == "2":
                domain = ask("[bold red]Введите домен[/bold red]")
                trail = new_trail({"domain": domain})
                trail["findings"]["domain"] = tools.analyze_domain(domain)
                save_and_report(trail, f"murder_domain_{domain}")
            elif choice == "3":
                email = ask("[bold red]Введите email[/bold red]")
                trail = new_trail({"email": email})
                trail["findings"]["email"] = tools.analyze_email(email)
                save_and_report(trail, f"murder_email_{email.replace('@', '_at_')}")
            elif choice == "4":
                phone = ask("[bold red]Введите телефон[/bold red]")
                trail = new_trail({"phone": phone})
                trail["findings"]["phone"] = tools.analyze_phone(phone)
                trail["findings"]["whatsapp"] = tools.whatsapp_check(phone)
                save_and_report(trail, f"murder_phone_{phone.replace('+', '').replace(' ', '')}")
            elif choice == "5":
                ip = ask("[bold red]Введите IP[/bold red]")
                trail = new_trail({"ip": ip})
                trail["findings"]["ip"] = tools.analyze_ip(ip)
                save_and_report(trail, f"murder_ip_{ip.replace('.', '_')}")
            elif choice == "6":
                path = ask("[bold red]Путь к изображению[/bold red]")
                trail = new_trail({"image": path})
                trail["findings"]["image"] = {
                    "exif": tools.image_exif(path),
                    "reverse": tools.image_reverse_links(path),
                }
                save_and_report(trail, "murder_image")
            elif choice == "7":
                username = ask("[bold red]username[/bold red]", default="")
                domain = ask("[bold red]domain[/bold red]", default="")
                email = ask("[bold red]email[/bold red]", default="")
                trail = new_trail({})
                if username:
                    trail["findings"]["username"] = tools.search_real_emails(username)
                if domain:
                    trail["findings"]["domain"] = tools.analyze_domain(domain)
                if email:
                    trail["findings"]["email"] = tools.analyze_email(email)
                save_and_report(trail, "murder_complex")
            elif choice == "8":
                files = [f for f in os.listdir(PROJECT_DIR) if f.startswith("murder") and f.endswith(".html")]
                if files:
                    print("\n".join(f"{i}. {name}" for i, name in enumerate(sorted(files, reverse=True)[:10], 1)))
            elif choice == "9":
                seed = ask("[bold red]Ник / имя для генерации email[/bold red]")
                trail = new_trail({"email_seed": seed})
                trail["findings"]["emails_real"] = tools.search_real_emails(seed)
                save_and_report(trail, f"murder_emails_{seed}")
            else:
                console.print("[red]Неизвестный пункт[/red]")
        except KeyboardInterrupt:
            console.print("\n[yellow]Прервано[/yellow]")
        except Exception as e:
            console.print(f"[red]Ошибка: {e}[/red]")
        ask("\n[red]Enter для продолжения[/red]", default="")


if __name__ == "__main__":
    main()
