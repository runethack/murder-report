#!/usr/bin/env python3
"""MURDER Report command-line entry point."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))
os.chdir(PROJECT_DIR)

REQUIRED = {
    "requests": "requests>=2.31",
    "dns": "dnspython>=2.4",
    "phonenumbers": "phonenumbers>=8.13",
    "rich": "rich>=13.0",
    "cloudscraper": "cloudscraper>=1.2.71",
    "bs4": "beautifulsoup4>=4.12",
}
OPTIONAL = {"exifread": "exifread>=3.0"}


def ensure_python_deps():
    missing = []
    for module, package in REQUIRED.items():
        try:
            __import__(module)
        except ImportError:
            missing.append(package)
    if missing:
        print("[*] Installing missing Python dependencies:")
        for package in missing:
            print(f"    - {package}")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])
        except subprocess.CalledProcessError:
            print(f"[!] Install manually: {sys.executable} -m pip install {' '.join(missing)}")
            raise SystemExit(1)
    for module, package in OPTIONAL.items():
        try:
            __import__(module)
        except ImportError:
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", package])
            except subprocess.CalledProcessError:
                print(f"[!] Optional dependency unavailable: {package}")


SYSTEM_PACKAGES = {
    "termux": {"curl": "curl", "whois": "whois", "dig": "dnsutils", "nmap": "nmap"},
    "apt": {"curl": "curl", "whois": "whois", "dig": "dnsutils", "nmap": "nmap", "nikto": "nikto"},
    "dnf": {"curl": "curl", "whois": "whois", "dig": "bind-utils", "nmap": "nmap", "nikto": "nikto"},
    "apk": {"curl": "curl", "whois": "whois", "dig": "bind-tools", "nmap": "nmap"},
    "brew": {"curl": "curl", "whois": "whois", "dig": "bind", "nmap": "nmap"},
}


def ensure_system_tools():
    # System tools are optional: never run a package manager automatically.
    tools = ("curl", "whois", "dig", "nmap")
    missing = [tool for tool in tools if not shutil.which(tool)]
    if missing:
        print(f"[!] Optional system tools not found: {', '.join(missing)}")
        print("    Install them with your OS package manager if needed.")


ensure_python_deps()
ensure_system_tools()

from m_util import console, show_banner, show_menu, show_user_results, save_and_report, new_trail, ask, ask_int, clear, search_username_live
import m_tools as tools


def _safe_name(value):
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value)


def _full_web_scan(target, full=False):
    host = tools._detect_real_host(target, tools.CULTURE_USER_AGENTS["chrome_linux"])
    base = tools._base_url(host)
    ua = tools._pick_best_ua(base)
    result = {"pathbrute": tools.scan_pathbrute(target, ua=ua, base=base, real_host=host)}
    if full:
        result["crawl"] = tools.scan_crawl(target, ua=ua, base=base, real_host=host)
        result["authbrute"] = tools.scan_authbrute(target, ua=ua, base=base, real_host=host)
    return result


def analyze(args):
    inputs = {}
    findings = {}
    if args.username:
        inputs["username"] = args.username
        findings["username"] = search_username_live(args.username, tools.USERNAME_SITES, tools._check_username_site, workers=15)
        findings["emails_real"] = tools.search_real_emails(args.username)
    if args.emails:
        inputs["emails_seed"] = args.emails
        findings["emails_real"] = tools.search_real_emails(args.emails)
    if args.domain:
        inputs["domain"] = args.domain
        findings["domain"] = tools.analyze_domain(args.domain)
        findings.update(_full_web_scan(args.domain, args.full))
    if args.email:
        inputs["email"] = args.email
        findings["email"] = tools.analyze_email(args.email)
    if args.phone:
        inputs["phone"] = args.phone
        findings["phone"] = tools.analyze_phone(args.phone, args.region)
        findings["whatsapp"] = tools.whatsapp_check(args.phone)
        findings["phone_reviews"] = tools.phone_reviews(args.phone)
    if args.ip:
        inputs["ip"] = args.ip
        findings["ip"] = tools.analyze_ip(args.ip)
        findings["geo_multi"] = tools.scan_geo_ip(args.ip)
        findings.update(_full_web_scan(args.ip, args.full))
        if args.full:
            findings["external"] = tools.scan_external(args.ip, args.ip)
    if args.image:
        inputs["image"] = args.image
        findings["image"] = {"exif": tools.image_exif(args.image), "reverse": tools.image_reverse_links(args.image)}
    if not findings:
        return False
    save_and_report({**new_trail(inputs), "findings": findings}, args.out)
    return True


def interactive():
    while True:
        clear()
        show_banner("MURDER REPORT")
        show_menu()
        choice = ask("[bold red]Выбор[/bold red]", default="0")
        if choice == "0":
            return
        try:
            if choice == "1":
                value = ask("[bold red]Username[/bold red]")
                args = argparse.Namespace(username=value, emails=None, domain=None, email=None, phone=None, region=None, ip=None, image=None, full=False, out=f"murder_username_{_safe_name(value)}")
                analyze(args)
            elif choice == "2":
                value = ask("[bold red]Домен[/bold red]")
                args = argparse.Namespace(username=None, emails=None, domain=value, email=None, phone=None, region=None, ip=None, image=None, full=False, out=f"murder_domain_{_safe_name(value)}")
                analyze(args)
            elif choice == "3":
                value = ask("[bold red]Email[/bold red]")
                args = argparse.Namespace(username=None, emails=None, domain=None, email=value, phone=None, region=None, ip=None, image=None, full=False, out=f"murder_email_{_safe_name(value)}")
                analyze(args)
            elif choice == "4":
                value = ask("[bold red]Телефон[/bold red]")
                args = argparse.Namespace(username=None, emails=None, domain=None, email=None, phone=value, region=None, ip=None, image=None, full=False, out=f"murder_phone_{_safe_name(value)}")
                analyze(args)
            elif choice == "5":
                value = ask("[bold red]IP[/bold red]")
                args = argparse.Namespace(username=None, emails=None, domain=None, email=None, phone=None, region=None, ip=value, image=None, full=False, out=f"murder_ip_{_safe_name(value)}")
                analyze(args)
            elif choice == "6":
                value = ask("[bold red]Путь к изображению[/bold red]")
                args = argparse.Namespace(username=None, emails=None, domain=None, email=None, phone=None, region=None, ip=None, image=value, full=False, out="murder_image")
                analyze(args)
            elif choice == "7":
                print("Комплексный режим используйте через CLI, передав несколько параметров.")
            elif choice == "8":
                files = sorted(PROJECT_DIR.glob("murder*.html"), key=lambda p: p.stat().st_mtime, reverse=True)
                for index, path in enumerate(files[:15], 1):
                    print(f"{index}. {path.name}")
            elif choice == "9":
                value = ask("[bold red]Username/имя[/bold red]")
                args = argparse.Namespace(username=None, emails=value, domain=None, email=None, phone=None, region=None, ip=None, image=None, full=False, out=f"murder_emails_{_safe_name(value)}")
                analyze(args)
        except KeyboardInterrupt:
            console.print("\n[yellow]Прервано[/yellow]")
        except Exception as exc:
            console.print(f"[red]Ошибка: {exc}[/red]")
        ask("\n[red]Enter для продолжения[/red]", default="")


def main():
    parser = argparse.ArgumentParser(prog="murder")
    parser.add_argument("-u", "--username")
    parser.add_argument("--emails")
    parser.add_argument("-d", "--domain")
    parser.add_argument("-e", "--email")
    parser.add_argument("-p", "--phone")
    parser.add_argument("--region")
    parser.add_argument("-i", "--ip")
    parser.add_argument("--image")
    parser.add_argument("-o", "--out", default="murder_report")
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()
    if not analyze(args):
        interactive()


if __name__ == "__main__":
    main()
