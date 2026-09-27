import re
import json
import socket
import hashlib
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FutTimeout

import dns.resolver
import phonenumbers
from phonenumbers import geocoder as pn_geocoder, carrier as pn_carrier, timezone as pn_timezone

from m_util import http_get, is_cloudflare, HAS_CLOUDSCRAPER

try:
    import exifread
    HAS_EXIFREAD = True
except ImportError:
    HAS_EXIFREAD = False

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False


USERNAME_SITES = {
    "github": ("https://github.com/{}", ["Not Found"]),
    "gitlab": ("https://gitlab.com/{}", ["Page Not Found", "404"]),
    "reddit": ("https://www.reddit.com/user/{}", ["Sorry, nobody on Reddit"]),
    "telegram": ("https://t.me/{}", ["If you have Telegram, you can contact"]),
    "instagram": ("https://www.instagram.com/{}/", ["Sorry, this page isn't available"]),
    "tiktok": ("https://www.tiktok.com/@{}", ["Couldn't find this account"]),
    "twitch": ("https://www.twitch.tv/{}", ["Sorry. Unless you've got a time machine"]),
    "steam": ("https://steamcommunity.com/id/{}", ["The specified profile could not be found"]),
    "pinterest": ("https://www.pinterest.com/{}/", ["User not found"]),
    "soundcloud": ("https://soundcloud.com/{}", ["We can't find that user"]),
    "medium": ("https://medium.com/@{}", ["404"]),
    "devto": ("https://dev.to/{}", ["404"]),
    "habr": ("https://habr.com/ru/users/{}/", ["404", "Страница не найдена"]),
    "vk": ("https://vk.com/{}", ["404", "not found"]),
    "keybase": ("https://keybase.io/{}", ["not found"]),
    "aboutme": ("https://about.me/{}", ["404"]),
    "behance": ("https://www.behance.net/{}", ["404"]),
    "dribbble": ("https://dribbble.com/{}", ["404"]),
    "flickr": ("https://www.flickr.com/people/{}", ["404"]),
    "patreon": ("https://www.patreon.com/{}", ["404"]),
    "roblox": ("https://www.roblox.com/user.aspx?username={}", ["404"]),
    "spotify": ("https://open.spotify.com/user/{}", ["404"]),
    "trello": ("https://trello.com/{}", ["404"]),
    "wattpad": ("https://www.wattpad.com/user/{}", ["404"]),
    "youtube": ("https://www.youtube.com/@{}", ["404", "This page isn't available"]),
    "lastfm": ("https://www.last.fm/user/{}", ["404"]),
    "mastodon": ("https://mastodon.social/@{}", ["404"]),
    "codepen": ("https://codepen.io/{}", ["404"]),
    "replit": ("https://replit.com/@{}", ["404"]),
    "hackernews": ("https://news.ycombinator.com/user?id={}", ["No such user"]),
    "producthunt": ("https://www.producthunt.com/@{}", ["404"]),
    "gravatar": ("https://gravatar.com/{}", ["404"]),
    "dockerhub": ("https://hub.docker.com/u/{}", ["404"]),
    "npm": ("https://www.npmjs.com/~{}", ["404"]),
    "pypi": ("https://pypi.org/user/{}", ["404"]),
    "stackoverflow": ("https://stackoverflow.com/users/{}", ["404"]),
    "bitbucket": ("https://bitbucket.org/{}/", ["404"]),
}


def _check_username_site(site, template, not_found, username):
    url = template.format(username)
    r = http_get(url, timeout=8)
    if r is None:
        return {"site": site, "url": url, "exists": None, "status": None, "error": "network"}
    body_low = (r.text or "").lower()
    miss = any(m.lower() in body_low for m in not_found)
    exists = r.status_code == 200 and not miss
    if r.status_code in (401, 403):
        exists = "maybe"
    cf = is_cloudflare(r.text or '', r.headers)
    return {"site": site, "url": url, "exists": exists,
            "status": r.status_code, "size": len(r.text or ""),
            "cloudflare": cf}


def search_username(username, workers=12):
    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_check_username_site, site, tmpl, nf, username): site
            for site, (tmpl, nf) in USERNAME_SITES.items()
        }
        for f in as_completed(futures):
            try:
                results.append(f.result())
            except Exception as e:
                results.append({"site": futures[f], "error": str(e)})
    results.sort(key=lambda x: (x.get("exists") is not True,
                                x.get("exists") != "maybe",
                                x.get("site", "")))
    return results


def domain_subdomains_crtsh(domain):
    r = http_get(f"https://crt.sh/?q=%25.{domain}&output=json",
                 timeout=12, throttle=0.5)
    if not r:
        return []
    try:
        data = r.json()
    except json.JSONDecodeError:
        return []
    subs = set()
    for entry in data:
        for name in str(entry.get("name_value", "")).split("\n"):
            name = name.strip().lower()
            if name and "*" not in name and domain in name:
                subs.add(name)
    return sorted(subs)


def domain_dns_records(domain):
    out = {}
    for rtype in ("A", "AAAA", "MX", "NS", "TXT", "CNAME", "SOA"):
        try:
            answers = dns.resolver.resolve(domain, rtype, lifetime=3)
            out[rtype] = [str(a).strip('"') for a in answers]
        except Exception:
            out[rtype] = []
    return out


def _run_cmd(args, timeout=10):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return (r.stdout or '').strip(), (r.stderr or '').strip()
    except FileNotFoundError:
        return None, f"not found: {args[0]}"
    except subprocess.TimeoutExpired:
        return None, "timeout"
    except Exception as e:
        return None, str(e)


def domain_dig_short(domain):
    if not shutil.which('dig'):
        return {'available': False, 'note': 'dig не установлен'}
    out = {}
    for rtype in ('A', 'AAAA', 'MX', 'NS', 'TXT', 'CNAME', 'SOA'):
        stdout, err = _run_cmd(['dig', '+short', domain, rtype], timeout=5)
        if stdout:
            out[rtype] = [l for l in stdout.split('\n') if l.strip()]
        else:
            out[rtype] = []
    return {'available': True, 'records': out}


def domain_dig_full(domain):
    if not shutil.which('dig'):
        return {'available': False, 'note': 'dig не установлен'}
    out = {}
    for rtype in ('A', 'MX', 'NS', 'TXT'):
        stdout, err = _run_cmd(['dig', domain, rtype], timeout=5)
        if stdout:
            out[rtype] = stdout
        elif err:
            out[rtype] = f"[{err}]"
    return {'available': True, 'records': out}


_RDAP_BOOT_DNS = None
_RDAP_BOOT_IP = None


def _rdap_bootstrap_dns():
    global _RDAP_BOOT_DNS
    if _RDAP_BOOT_DNS is not None:
        return _RDAP_BOOT_DNS
    try:
        r = http_get("https://data.iana.org/rdap/dns.json",
                     timeout=5, throttle=0.2)
        _RDAP_BOOT_DNS = r.json().get("services", []) if r else []
    except Exception:
        _RDAP_BOOT_DNS = []
    return _RDAP_BOOT_DNS


def _rdap_bootstrap_ip():
    global _RDAP_BOOT_IP
    if _RDAP_BOOT_IP is not None:
        return _RDAP_BOOT_IP
    try:
        r = http_get("https://data.iana.org/rdap/ipv4.json",
                     timeout=5, throttle=0.2)
        _RDAP_BOOT_IP = r.json().get("services", []) if r else []
    except Exception:
        _RDAP_BOOT_IP = []
    return _RDAP_BOOT_IP


def _rdap_find_url(services, query):
    for svc in services:
        tlds, urls = svc[0], svc[1]
        for t in tlds:
            if query == t or query.endswith("." + t):
                return urls[0].rstrip('/')
    return None


def _rdap_fetch(url, timeout=6):
    try:
        r = http_get(url, timeout=timeout, throttle=0.2,
                     headers={'Accept': 'application/rdap+json, application/json'},
                     use_cloudscraper=False)
        if not r or r.status_code != 200:
            return {}
        return r.json()
    except Exception:
        return {}


def whois_domain_rdap(domain):
    services = _rdap_bootstrap_dns()
    base = _rdap_find_url(services, domain)
    data = {}
    if base:
        data = _rdap_fetch(f"{base}/domain/{domain}", timeout=6)
    if not data:
        data = _rdap_fetch(f"https://rdap.org/domain/{domain}", timeout=6)
    if not data:
        return {'available': False, 'note': 'RDAP не ответил',
                'parsed': {}, 'raw': {}}

    parsed = {}
    for ent in data.get('entities', []) or []:
        roles = ent.get('roles', []) or []
        vcard = ent.get('vcardArray', [])
        name = None
        email = None
        if isinstance(vcard, list) and len(vcard) > 1:
            for item in vcard[1]:
                if not isinstance(item, list) or len(item) < 4:
                    continue
                key, val = item[0], item[3]
                if key == 'fn' and not name:
                    name = val
                if key == 'email' and not email:
                    email = val
        if 'registrar' in roles:
            if name:
                parsed.setdefault('registrar', []).append(name)
            if email:
                parsed.setdefault('registrar email', []).append(email)
        if 'administrative' in roles and email:
            parsed.setdefault('admin email', []).append(email)
        if 'technical' in roles and email:
            parsed.setdefault('tech email', []).append(email)

    for ev in data.get('events', []) or []:
        action = (ev.get('eventAction') or '').lower()
        date = ev.get('eventDate')
        if not date:
            continue
        if action == 'registration':
            parsed.setdefault('creation date', []).append(date)
        elif action in ('expiration', 'expiry'):
            parsed.setdefault('expiry date', []).append(date)
        elif action == 'last changed':
            parsed.setdefault('updated date', []).append(date)

    for st in data.get('status', []) or []:
        parsed.setdefault('status', []).append(st)

    for ns in data.get('nameservers', []) or []:
        ldh = ns.get('ldhName')
        if ldh:
            parsed.setdefault('name server', []).append(ldh.lower())

    return {'available': True, 'parsed': parsed, 'raw': data,
            'source': 'rdap'}


def whois_ip_rdap(ip):
    services = _rdap_bootstrap_ip()
    base = None
    for svc in services:
        for cidr in svc[0]:
            net = cidr.split("/")[0]
            if ip.startswith(net.rsplit(".", 1)[0]):
                base = svc[1][0].rstrip('/')
                break
        if base:
            break

    data = {}
    if base:
        data = _rdap_fetch(f"{base}/ip/{ip}", timeout=6)
    if not data:
        data = _rdap_fetch(f"https://rdap.org/ip/{ip}", timeout=6)
    if not data:
        return {'available': False, 'note': 'RDAP не ответил',
                'parsed': {}, 'raw': {}}

    parsed = {}
    for k_src, k_dst in (('name', 'netname'), ('handle', 'handle'),
                         ('country', 'country')):
        v = data.get(k_src)
        if v:
            parsed.setdefault(k_dst, []).append(v)
    start = data.get('startAddress')
    end = data.get('endAddress')
    if start and end:
        parsed.setdefault('range', []).append(f"{start} - {end}")
    for ev in data.get('events', []) or []:
        action = (ev.get('eventAction') or '').lower()
        date = ev.get('eventDate')
        if not date:
            continue
        if action == 'registration':
            parsed.setdefault('registration', []).append(date)
        elif action == 'last changed':
            parsed.setdefault('updated', []).append(date)
    for ent in data.get('entities', []) or []:
        roles = ent.get('roles', []) or []
        vcard = ent.get('vcardArray', [])
        email = None
        org = None
        if isinstance(vcard, list) and len(vcard) > 1:
            for item in vcard[1]:
                if not isinstance(item, list) or len(item) < 4:
                    continue
                key, val = item[0], item[3]
                if key == 'email' and not email:
                    email = val
                if key in ('fn', 'org') and not org:
                    org = val
        if 'abuse' in roles and email:
            parsed.setdefault('abuse-mailbox', []).append(email)
        if 'registrant' in roles and org:
            parsed.setdefault('orgname', []).append(org)

    return {'available': True, 'parsed': parsed, 'raw': data,
            'source': 'rdap'}


def domain_whois(domain):
    if shutil.which('whois'):
        stdout, err = _run_cmd(['whois', domain], timeout=10)
        if stdout:
            parsed = {}
            keys = (
                'domain name', 'registrar', 'registrar url', 'creation date',
                'updated date', 'expiry date', 'expiration date', 'registry expiry date',
                'registrant name', 'registrant organization', 'registrant email',
                'admin email', 'tech email', 'name server', 'nserver', 'dnssec',
                'status', 'domain status', 'org', 'organization',
            )
            for line in stdout.split('\n'):
                if ':' not in line:
                    continue
                k, v = line.split(':', 1)
                kl = k.strip().lower()
                if kl in keys:
                    parsed.setdefault(kl, []).append(v.strip())
            return {'available': True, 'raw': stdout, 'parsed': parsed,
                    'source': 'whois'}
    return whois_domain_rdap(domain)


def ip_whois(ip):
    if shutil.which('whois'):
        stdout, err = _run_cmd(['whois', ip], timeout=10)
        if stdout:
            parsed = {}
            for line in stdout.split('\n'):
                if ':' not in line:
                    continue
                k, v = line.split(':', 1)
                kl = k.strip().lower()
                if kl in ('netname', 'orgname', 'org-name', 'org', 'country',
                          'descr', 'abuse-mailbox', 'cidr', 'inetnum', 'netrange',
                          'route', 'origin'):
                    parsed.setdefault(kl, []).append(v.strip())
            return {'available': True, 'raw': stdout, 'parsed': parsed,
                    'source': 'whois'}
    return whois_ip_rdap(ip)


def domain_rdap(domain):
    services = _rdap_bootstrap_dns()
    base = _rdap_find_url(services, domain)
    if base:
        d = _rdap_fetch(f"{base}/domain/{domain}", timeout=6)
        if d:
            return d
    return _rdap_fetch(f"https://rdap.org/domain/{domain}", timeout=6)


def _2ip_fetch(url, timeout=10):
    try:
        r = http_get(url, timeout=timeout, throttle=1.0,
                     headers={'Accept': 'application/json',
                              'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) '
                                            'AppleWebKit/537.36 (KHTML, like Gecko) '
                                            'Chrome/120.0.0.0 Safari/537.36'},
                     use_cloudscraper=True)
        if not r or r.status_code != 200:
            return {}
        txt = (r.text or '').strip()
        if not txt or txt.startswith('<'):
            return {}
        return r.json()
    except Exception:
        return {}


def ip_2ip(ip):
    url = f"https://2ip.io/pr/api/ip/{ip}?format=json"
    data = _2ip_fetch(url)
    if not data:
        url = f"https://api.2ip.io/{ip}?format=json"
        data = _2ip_fetch(url)

    if not data or not isinstance(data, dict):
        return {'available': False, 'url': url, 'fields': {}, 'raw': {}}

    src = data
    if 'ip' in data and isinstance(data['ip'], dict):
        src = data['ip']

    fields = {}
    mapping = {
        'ip': 'ip', 'country': 'country', 'country_code': 'country_code',
        'region': 'region', 'city': 'city', 'latitude': 'lat',
        'longitude': 'lon', 'time_zone': 'timezone', 'timezone': 'timezone',
        'isp': 'isp', 'org': 'org', 'asn': 'asn', 'as': 'as',
        'hostname': 'hostname', 'reverse': 'reverse', 'type': 'type',
        'hosting': 'hosting', 'proxy': 'proxy', 'vpn': 'vpn',
        'tor': 'tor', 'mobile': 'mobile',
    }
    for src_key, dst_key in mapping.items():
        if src_key in src and src[src_key] not in (None, '', []):
            fields[dst_key] = src[src_key]

    return {'available': True, 'url': url, 'fields': fields, 'raw': src}


def domain_2ip(domain):
    url = f"https://2ip.io/pr/api/whois/{domain}?format=json"
    data = _2ip_fetch(url)
    if not data:
        url = f"https://api.2ip.io/domain/{domain}?format=json"
        data = _2ip_fetch(url)
    if not data or not isinstance(data, dict):
        return {'available': False, 'url': url, 'fields': {}, 'raw': {}}

    fields = {}
    mapping = {
        'domain': 'domain', 'ip': 'ip', 'ns': 'ns', 'nserver': 'ns',
        'registrar': 'registrar', 'org': 'org',
        'created': 'created', 'creation_date': 'created',
        'updated': 'updated', 'updated_date': 'updated',
        'expires': 'expires', 'expiration_date': 'expires', 'paid_till': 'expires',
        'status': 'status', 'state': 'status',
        'persons': 'persons', 'emails': 'emails',
    }
    for src_key, dst_key in mapping.items():
        v = data.get(src_key)
        if v not in (None, '', []):
            fields[dst_key] = v
    return {'available': True, 'url': url, 'fields': fields, 'raw': data}


def analyze_domain(domain):
    return {
        "domain": domain,
        "dns": domain_dns_records(domain),
        "dig_short": domain_dig_short(domain),
        "dig_full": domain_dig_full(domain),
        "whois": domain_whois(domain),
        "subdomains": domain_subdomains_crtsh(domain),
        "rdap": domain_rdap(domain),
        "2ip": domain_2ip(domain),
    }


EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")

DISPOSABLE = {
    "mailinator.com", "10minutemail.com", "guerrillamail.com",
    "tempmail.com", "throwawaymail.com", "yopmail.com",
    "trashmail.com", "sharklasers.com", "getnada.com",
    "dispostable.com", "fakeinbox.com", "maildrop.cc",
}


def email_validate(email):
    return bool(EMAIL_RE.match(email))


def email_mx(email):
    domain = email.split("@", 1)[1]
    try:
        return [str(r.exchange).rstrip(".") for r in dns.resolver.resolve(domain, "MX", lifetime=3)]
    except Exception:
        return []


def email_is_disposable(email):
    domain = email.split("@", 1)[1].lower()
    return domain in DISPOSABLE


def email_gravatar(email):
    h = hashlib.md5(email.strip().lower().encode()).hexdigest()
    url = f"https://gravatar.com/avatar/{h}?d=404"
    r = http_get(url, timeout=6, throttle=0.5)
    exists = r is not None and r.status_code == 200
    return {"hash": h, "exists": exists,
            "profile": f"https://gravatar.com/{h}" if exists else None}


def email_breach(email):
    r = http_get(f"https://haveibeenpwned.com/account/{email}", timeout=8, throttle=1.0)
    if not r:
        return {"checked": False}
    low = r.text.lower()
    breached = "good news" not in low and "oh no" in low
    names = re.findall(r'class="[^"]*pwned-account[^"]*"[^>]*>([^<]+)<', r.text)
    return {"checked": True, "breached": breached, "brands": names[:30],
            "cloudflare": is_cloudflare(r.text or '', r.headers)}


def analyze_email(email):
    return {
        "email": email,
        "valid_syntax": email_validate(email),
        "mx": email_mx(email),
        "disposable": email_is_disposable(email),
        "gravatar": email_gravatar(email),
        "breach": email_breach(email),
    }


def analyze_phone(raw, region=None):
    raw = (raw or "").strip()
    raw_clean = re.sub(r'[^\d+]', '', raw)
    if raw_clean and not raw_clean.startswith('+'):
        raw_clean = '+' + raw_clean.lstrip('0')

    candidates = []
    if raw_clean:
        candidates.append(raw_clean)
        if raw_clean.startswith('8') and len(raw_clean) == 11:
            candidates.append('+7' + raw_clean[1:])
        if raw_clean.startswith('8') and len(raw_clean) == 10:
            candidates.append('+7' + raw_clean[1:])
        if raw_clean.startswith('+7') and len(raw_clean) == 10:
            candidates.append('+7' + raw_clean[2:])

    parsed = None
    used = raw_clean
    for cand in candidates:
        for region_hint in (region, "RU", "US", "GB", None):
            try:
                num = phonenumbers.parse(cand, region_hint)
                if phonenumbers.is_possible_number(num) or phonenumbers.is_valid_number(num):
                    parsed = num
                    used = cand
                    break
            except Exception:
                continue
        if parsed:
            break

    if parsed is None:
        try:
            parsed = phonenumbers.parse(raw, region or "RU")
            used = raw
        except phonenumbers.NumberParseException as e:
            return {"input": raw, "error": str(e)}

    num = parsed
    country_code = num.country_code
    national = num.national_number

    try:
        region_code = phonenumbers.region_code_for_number(num)
    except Exception:
        region_code = None

    try:
        region_geo = pn_geocoder.description_for_number(num, "ru") or \
                     pn_geocoder.description_for_number(num, "en") or ""
    except Exception:
        region_geo = ""

    try:
        carrier = pn_carrier.name_for_number(num, "ru") or \
                  pn_carrier.name_for_number(num, "en") or ""
    except Exception:
        carrier = ""

    try:
        timezones = list(pn_timezone.time_zones_for_number(num))
    except Exception:
        timezones = []

    try:
        number_type = phonenumbers.number_type(num)
        type_map = {
            phonenumbers.PhoneNumberType.MOBILE: "mobile",
            phonenumbers.PhoneNumberType.FIXED_LINE: "fixed_line",
            phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE: "fixed_or_mobile",
            phonenumbers.PhoneNumberType.TOLL_FREE: "toll_free",
            phonenumbers.PhoneNumberType.PREMIUM_RATE: "premium_rate",
            phonenumbers.PhoneNumberType.SHARED_COST: "shared_cost",
            phonenumbers.PhoneNumberType.VOIP: "voip",
            phonenumbers.PhoneNumberType.PERSONAL_NUMBER: "personal",
            phonenumbers.PhoneNumberType.PAGER: "pager",
            phonenumbers.PhoneNumberType.UAN: "uan",
            phonenumbers.PhoneNumberType.VOICEMAIL: "voicemail",
            phonenumbers.PhoneNumberType.UNKNOWN: "unknown",
        }
        number_type_str = type_map.get(number_type, "unknown")
    except Exception:
        number_type_str = "unknown"

    e164 = phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)
    international = phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
    national_fmt = phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.NATIONAL)
    rfc3966 = phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.RFC3966)

    digits_only = re.sub(r'\D', '', e164)
    links = {
        "wa": f"https://wa.me/{digits_only}",
        "telegram": f"https://t.me/+{digits_only}",
        "viber": f"viber://chat?number=%2B{digits_only}",
        "truecaller": f"https://www.truecaller.com/search/{region_code.lower() if region_code else ''}/{digits_only}",
    }

    return {
        "input": raw,
        "normalized": used,
        "valid": phonenumbers.is_valid_number(num),
        "possible": phonenumbers.is_possible_number(num),
        "e164": e164,
        "international": international,
        "national": national_fmt,
        "rfc3966": rfc3966,
        "country_code": country_code,
        "region_code": region_code,
        "region": region_geo,
        "carrier": carrier,
        "number_type": number_type_str,
        "timezones": timezones,
        "digits": digits_only,
        "links": links,
    }


def whatsapp_check(raw_phone, timeout=12):
    """
    Реальная проверка номера в WhatsApp через wa.me.
    wa.me отдаёт HTML-страницу на мобильном UA со словами:
      - "Chat with +7 ..." / "Чат с +7 ..." → номер зарегистрирован
      - "Continue to Chat" / "Продолжить в WhatsApp" → зарегистрирован
      - "phone number shared via url is invalid" / "недействителен" → не зарегистрирован
    """
    digits = re.sub(r'\D', '', raw_phone or '')
    if not digits:
        return {'registered': None, 'error': 'empty', 'method': None,
                'url': None, 'redirect': None, 'title': None, 'status': None}

    wa_digits = digits
    if wa_digits.startswith('8') and len(wa_digits) == 11:
        wa_digits = '7' + wa_digits[1:]

    url = f"https://wa.me/{wa_digits}"
    out = {'registered': None, 'method': None, 'url': url,
           'redirect': None, 'title': None, 'error': None, 'status': None}

    r = http_get(url, timeout=timeout, throttle=0.3,
                 headers={'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) '
                                        'AppleWebKit/537.36 (KHTML, like Gecko) '
                                        'Chrome/120.0.0.0 Safari/537.36',
                          'Accept-Language': 'en-US,en;q=0.9,ru;q=0.8'},
                 use_cloudscraper=True,
                 allow_redirects=True)

    if r is None:
        out['error'] = 'network'
        return out

    out['status'] = r.status_code
    out['redirect'] = r.url
    final = (r.url or '').lower()

    body = r.text or ''
    body_low = body.lower()

    m = re.search(r'<title[^>]*>([^<]+)</title>', body, re.I)
    if m:
        out['title'] = m.group(1).strip()

    # 1) редирект на "не установлен WhatsApp / invalid"
    if 'whatsapp.com/download' in final or 'invalid' in final:
        out['registered'] = False
        out['method'] = 'redirect_invalid'
        return out

    # 2) редирект на send — есть номер
    if 'api.whatsapp.com/send' in final or 'web.whatsapp.com/send' in final:
        out['registered'] = True
        out['method'] = 'redirect_send'
        return out

    # 3) HTML-маркеры "недействительный номер" (мультиязычные)
    invalid_markers = [
        'phone number shared via url is invalid',
        'номер телефона, указанный в ссылке, недействителен',
        'недействительный номер',
        '此电话号码无效',
        'номер недійсний',
        'ungültige telefonnummer',
        'numéro de téléphone non valide',
    ]
    if any(mk in body_low for mk in invalid_markers):
        out['registered'] = False
        out['method'] = 'html_invalid'
        return out

    # 4) HTML-маркеры "зарегистрирован" (чат + WhatsApp Web / download app)
    valid_markers = [
        'continue to chat',
        'use whatsapp web',
        'открыть whatsapp',
        'whatsapp web',
        'продолжить в whatsapp',
        '继续前往 whatsapp 网页版',
        'chat with +',
        'чат с +',
        '在 whatsapp 上与',
        'get whatsapp for',
    ]
    if any(mk in body_low for mk in valid_markers):
        out['registered'] = True
        out['method'] = 'html_chat'
        return out

    # 5) если страница скачивания с текстом "you don't have whatsapp" — считаем,
    #    что номер тоже не зарегистрирован (WhatsApp не знает, что с ним делать)
    if 'download whatsapp' in body_low and 'continue' not in body_low:
        out['registered'] = False
        out['method'] = 'html_download_only'
        return out

    out['error'] = 'undetermined'
    out['method'] = 'title_only'
    return out


def phone_reviews(raw_phone, total_timeout=25):
    digits = re.sub(r'\D', '', raw_phone)
    if not digits:
        return []

    digits_variants = {digits}
    if digits.startswith('7') and len(digits) == 11:
        digits_variants.add('8' + digits[1:])
    if digits.startswith('8') and len(digits) == 11:
        digits_variants.add('7' + digits[1:])

    sites = [
        {'site': 'whocall.su',        'url': f'https://whocall.su/{digits}/'},
        {'site': 'nomernoi.ru',       'url': f'https://www.nomernoi.ru/nomer/{digits}/'},
        {'site': 'кто-звонил.рф',     'url': f'https://кто-звонил.рф/{digits}/'},
        {'site': 'неберитрубку.рф',   'url': f'https://неберитрубку.рф/{digits}/'},
        {'site': 'tellows.ru',        'url': f'https://www.tellows.ru/num/{digits}'},
        {'site': 'ktozvonil.net',     'url': f'https://ktozvonil.net/{digits}'},
        {'site': 'shouldianswer.com', 'url': f'https://www.shouldianswer.com/phone-number/{digits}'},
    ]

    def _extract_next_data(soup):
        tag = soup.find('script', id='__NEXT_DATA__')
        if not tag or not tag.string:
            return None
        try:
            return json.loads(tag.string)
        except Exception:
            return None

    def _parse_jsonld_review(data):
        reviews = []
        rating_val = None
        found_number = False

        def walk(node):
            nonlocal rating_val, found_number
            if isinstance(node, dict):
                t = node.get('@type') or node.get('type') or ''
                t_str = str(t).lower()
                text_blob = json.dumps(node, ensure_ascii=False)
                digits_in_blob = re.sub(r'\D', '', text_blob)
                if any(v in digits_in_blob for v in digits_variants):
                    found_number = True
                if 'review' in t_str or 'rating' in t_str:
                    body = node.get('reviewBody') or node.get('description') or node.get('name') or ''
                    if body:
                        reviews.append(str(body))
                    rv = node.get('ratingValue')
                    if rv is not None and rating_val is None:
                        try:
                            rating_val = str(float(rv))
                        except (ValueError, TypeError):
                            pass
                if 'aggregaterating' in t_str and rating_val is None:
                    rv = node.get('ratingValue')
                    if rv is not None:
                        try:
                            rating_val = str(float(rv))
                        except (ValueError, TypeError):
                            pass
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)

        walk(data)

        if not reviews and not found_number:
            return None

        markers = ['мошенник', 'спам', 'scam', 'spam', 'реклама',
                   'fraud', 'робот', 'robot', 'не брать', 'навязчив',
                   'коллектор', 'опрос', 'банк']
        joined = ' '.join(reviews).lower()
        tags = [m for m in markers if m in joined]

        return {
            'reviews': len(reviews),
            'rating': rating_val,
            'tags': tags,
            'snippet': (reviews[0][:400] if reviews else ''),
        }

    def _parse_strict(html):
        if not HAS_BS4:
            return None
        try:
            soup = BeautifulSoup(html, 'html.parser')
        except Exception:
            return None

        parsed_data = None

        next_data = _extract_next_data(soup)
        if next_data:
            parsed_data = _parse_jsonld_review(next_data)

        if parsed_data is None:
            for tag in soup.find_all('script', type='application/ld+json'):
                if not tag.string:
                    continue
                try:
                    ld = json.loads(tag.string)
                except Exception:
                    continue
                parsed_data = _parse_jsonld_review(ld)
                if parsed_data:
                    break

        if parsed_data is None:
            blocks = []
            for el in soup.select('[itemprop="reviewBody"]'):
                t = el.get_text(' ', strip=True)
                if t:
                    blocks.append(t)
            if not blocks:
                for el in soup.select('[itemprop="review"]'):
                    t = el.get_text(' ', strip=True)
                    if t:
                        blocks.append(t)
            if blocks:
                markers = ['мошенник', 'спам', 'scam', 'spam', 'реклама',
                           'fraud', 'робот', 'robot', 'не брать',
                           'навязчив', 'коллектор', 'опрос', 'банк']
                joined = ' '.join(blocks).lower()
                tags = [m for m in markers if m in joined]
                rating_el = soup.select_one('[itemprop="ratingValue"]')
                rating = None
                if rating_el:
                    m = re.search(r'(\d+(?:[.,]\d+)?)',
                                  rating_el.get_text(' ', strip=True))
                    if m:
                        rating = m.group(1).replace(',', '.')
                parsed_data = {
                    'reviews': len(blocks),
                    'rating': rating,
                    'tags': tags,
                    'snippet': blocks[0][:400],
                }

        return parsed_data

    def fetch(site):
        out = {
            'site': site['site'],
            'url': site['url'],
            'rating': None,
            'reviews': 0,
            'snippet': '',
            'error': None,
            'cloudflare': False,
            'tags': [],
            'source': None,
        }
        try:
            r = http_get(site['url'], timeout=10, throttle=0.3,
                         headers={'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) '
                                                'AppleWebKit/537.36 (KHTML, like Gecko) '
                                                'Chrome/120.0.0.0 Safari/537.36',
                                  'Accept-Language': 'ru,en;q=0.8'},
                         use_cloudscraper=True)
            if r is None:
                out['error'] = 'network'
                return out
            if r.status_code != 200:
                out['error'] = f'http_{r.status_code}'
                return out
            html = r.text or ''
            if is_cloudflare(html, r.headers):
                out['cloudflare'] = True

            parsed = _parse_strict(html)
            if parsed:
                out['reviews'] = parsed['reviews']
                out['rating'] = parsed['rating']
                out['tags'] = parsed['tags']
                out['snippet'] = parsed['snippet']
            else:
                out['source'] = 'no_reliable_data'
        except Exception as e:
            out['error'] = str(e)
        return out

    results = []
    ex = ThreadPoolExecutor(max_workers=len(sites))
    futs = [ex.submit(fetch, s) for s in sites]
    try:
        for f in as_completed(futs, timeout=total_timeout):
            try:
                results.append(f.result(timeout=1))
            except Exception:
                pass
    except FutTimeout:
        pass
    finally:
        ex.shutdown(wait=False, cancel_futures=True)

    def rank(x):
        score = 0
        if x.get('reviews'): score -= 1000
        if x.get('rating'): score -= 500
        if x.get('tags'): score -= 250
        if x.get('snippet'): score -= 100
        if x.get('source') == 'no_reliable_data': score += 50
        if x.get('cloudflare'): score += 100
        if x.get('error'): score += 200
        return score
    results.sort(key=rank)
    return results


def ip_geo(ip):
    r = http_get(
        f"http://ip-api.com/json/{ip}?fields=status,message,country,regionName,"
        f"city,zip,lat,lon,timezone,isp,org,as,asname,reverse,mobile,proxy,hosting,query",
        timeout=6, throttle=0.3, use_cloudscraper=False,
    )
    if not r:
        return {}
    try:
        return r.json()
    except Exception:
        return {}


def ip_rdap(ip):
    return whois_ip_rdap(ip).get('raw', {}) or {}


def _gethostbyaddr_safe(ip, timeout=2):
    with ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(socket.gethostbyaddr, ip)
        try:
            return fut.result(timeout=timeout)
        except Exception:
            return None


def ip_reverse(ip):
    out = []
    try:
        for r in dns.resolver.resolve_address(ip, lifetime=2):
            h = str(r.target).rstrip(".")
            if h and h not in out:
                out.append(h)
    except Exception:
        pass
    res = _gethostbyaddr_safe(ip, timeout=2)
    if res:
        host = res[0]
        if host not in out:
            out.append(host)
    return out


def analyze_ip(ip, total_timeout=25):
    result = {
        "ip": ip, "geo": {}, "rdap": {},
        "whois": {'available': False, 'note': 'таймаут', 'parsed': {}},
        "reverse": [], "2ip": {'available': False, 'fields': {}},
    }

    def do_geo():
        return ('geo', ip_geo(ip))

    def do_whois():
        return ('whois', ip_whois(ip))

    def do_reverse():
        return ('reverse', ip_reverse(ip))

    def do_2ip():
        return ('2ip', ip_2ip(ip))

    ex = ThreadPoolExecutor(max_workers=4)
    futs = {
        ex.submit(do_geo): 'geo',
        ex.submit(do_whois): 'whois',
        ex.submit(do_reverse): 'reverse',
        ex.submit(do_2ip): '2ip',
    }
    try:
        for f in as_completed(futs, timeout=total_timeout):
            try:
                key, val = f.result(timeout=1)
                result[key] = val
            except Exception:
                pass
    except FutTimeout:
        pass
    finally:
        ex.shutdown(wait=False, cancel_futures=True)

    if isinstance(result.get('whois'), dict):
        result['rdap'] = result['whois'].get('raw', {}) or {}
    return result


def _gps_to_deg(coord, ref):
    d, m, s = coord
    deg = float(d) + float(m) / 60 + float(s) / 3600
    if ref in ("S", "W"):
        deg = -deg
    return round(deg, 6)


def image_exif(path):
    import os
    out = {"path": path, "exif": {}, "gps": None, "engine": None}
    if not os.path.exists(path):
        out["error"] = "file not found"
        return out
    if HAS_EXIFREAD:
        try:
            with open(path, "rb") as f:
                tags = exifread.process_file(f, details=False)
            for k, v in tags.items():
                out["exif"][str(k)] = str(v)[:200]
            lat = tags.get("GPS GPSLatitude")
            lat_ref = tags.get("GPS GPSLatitudeRef")
            lon = tags.get("GPS GPSLongitude")
            lon_ref = tags.get("GPS GPSLongitudeRef")
            if lat and lat_ref and lon and lon_ref:
                lat_vals = [float(x.num) / float(x.den) for x in lat.values]
                lon_vals = [float(x.num) / float(x.den) for x in lon.values]
                lat_deg = _gps_to_deg(lat_vals, str(lat_ref))
                lon_deg = _gps_to_deg(lon_vals, str(lon_ref))
                out["gps"] = {"lat": lat_deg, "lon": lon_deg,
                              "maps": f"https://maps.google.com/?q={lat_deg},{lon_deg}"}
            out["engine"] = "exifread"
            return out
        except Exception as e:
            out["exifread_error"] = str(e)
    out["error"] = "exifread недоступен"
    return out


def image_reverse_links(path):
    return {
        "google_lens": "https://lens.google.com/uploadbyurl?url=<URL_изображения>",
        "yandex": "https://yandex.ru/images/search?rpt=imageview&url=<URL_изображения>",
        "bing": "https://www.bing.com/images/search?view=detailv2&iss=sbiupload",
        "tineye": "https://tineye.com/",
        "note": "Загрузите файл на публичный хост и подставьте URL.",
    }


def _clean_emails(raw):
    out = set()
    if raw is None:
        return []
    if isinstance(raw, list):
        for x in raw:
            for e in _clean_emails(x):
                out.add(e)
    elif isinstance(raw, dict):
        for v in raw.values():
            for e in _clean_emails(v):
                out.add(e)
    elif isinstance(raw, str):
        for m in re.findall(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}', raw):
            out.add(m.lower())
    return sorted(out)


def email_from_github(nick):
    out = {'source': 'github', 'url': f'https://api.github.com/users/{nick}',
           'emails': [], 'profile': None, 'found': False}
    r = http_get(out['url'], timeout=8, throttle=0.3,
                 headers={'Accept': 'application/vnd.github+json',
                          'User-Agent': 'Mozilla/5.0'})
    if not r or r.status_code != 200:
        return out
    try:
        data = r.json()
    except Exception:
        return out
    out['found'] = True
    out['profile'] = data.get('html_url')
    if data.get('email'):
        out['emails'].append(data['email'].lower())
    try:
        evr = http_get(f"https://api.github.com/users/{nick}/events/public?per_page=30",
                       timeout=8, throttle=0.3,
                       headers={'Accept': 'application/vnd.github+json',
                                'User-Agent': 'Mozilla/5.0'})
        if evr and evr.status_code == 200:
            evs = evr.json()
            for ev in evs or []:
                payload = ev.get('payload') or {}
                for c in (payload.get('commits') or []):
                    author = (c.get('author') or {}).get('email')
                    if author and 'users.noreply.github.com' not in author:
                        out['emails'].append(author.lower())
    except Exception:
        pass
    out['emails'] = sorted(set(out['emails']))
    return out


def email_from_gitlab(nick):
    out = {'source': 'gitlab',
           'url': f'https://gitlab.com/api/v4/users?username={nick}',
           'emails': [], 'profile': None, 'found': False}
    r = http_get(out['url'], timeout=8, throttle=0.3)
    if not r or r.status_code != 200:
        return out
    try:
        data = r.json()
    except Exception:
        return out
    if not data:
        return out
    u = data[0]
    out['found'] = True
    out['profile'] = u.get('web_url')
    if u.get('public_email'):
        out['emails'].append(u['public_email'].lower())
    return out


def email_from_gravatar_profile(nick_or_email):
    key = nick_or_email.strip().lower()
    h = hashlib.md5(key.encode()).hexdigest()
    out = {'source': 'gravatar', 'hash': h,
           'url': f'https://gravatar.com/{h}.json',
           'emails': [], 'accounts': [], 'profile': None, 'found': False}
    r = http_get(out['url'], timeout=8, throttle=0.3)
    if not r or r.status_code != 200:
        return out
    try:
        data = r.json()
    except Exception:
        return out
    entry_raw = data.get('entry')
    entry = entry_raw[0] if isinstance(entry_raw, list) and entry_raw else (entry_raw if isinstance(entry_raw, dict) else {})
    out['found'] = True
    out['profile'] = entry.get('profileUrl') or f"https://gravatar.com/{h}"
    if entry.get('emails'):
        for e in entry['emails']:
            if isinstance(e, dict) and e.get('value'):
                out['emails'].append(e['value'].lower())
            elif isinstance(e, str):
                out['emails'].append(e.lower())
    for acc in entry.get('accounts') or []:
        out['accounts'].append({
            'shortname': acc.get('shortname'),
            'url': acc.get('url'),
            'username': acc.get('username'),
        })
    out['emails'] = sorted(set(out['emails']))
    return out


def email_from_keybase(nick):
    out = {'source': 'keybase',
           'url': f'https://keybase.io/_/api/1.0/user/lookup.json?username={nick}&fields=emails,proofs_summary,profile',
           'emails': [], 'found': False, 'profile': None}
    r = http_get(out['url'], timeout=8, throttle=0.3)
    if not r or r.status_code != 200:
        return out
    try:
        data = r.json()
    except Exception:
        return out
    them = (((data or {}).get('them') or [{}])[0]) or {}
    if not them:
        return out
    out['found'] = True
    for e in (them.get('emails') or []):
        if e.get('email'):
            out['emails'].append(e['email'].lower())
    out['profile'] = f"https://keybase.io/{nick}"
    out['emails'] = sorted(set(out['emails']))
    return out


def email_from_pgp(nick):
    out = {'source': 'pgp', 'emails': [], 'found': False,
           'url': f"https://keyserver.ubuntu.com/pks/lookup?search={nick}&op=index&options=mr"}
    r = http_get(out['url'], timeout=8, throttle=0.3)
    if r and r.status_code == 200 and r.text:
        for e in _clean_emails(r.text):
            out['emails'].append(e)
        if out['emails']:
            out['found'] = True
    return out


def _verify_email_mx(email):
    mx = email_mx(email)
    try:
        grav = email_gravatar(email).get('exists', False)
    except Exception:
        grav = False
    return {
        'email': email,
        'valid_syntax': email_validate(email),
        'mx': mx,
        'has_mx': bool(mx),
        'disposable': email_is_disposable(email),
        'gravatar': grav,
    }


def search_real_emails(nick, workers=6, total_timeout=25):
    sources = []
    all_emails = {}

    def run(src_name, fn, arg):
        try:
            res = fn(arg)
        except Exception as e:
            res = {'source': src_name, 'error': str(e), 'emails': []}
        return res

    tasks = [
        ('github',   email_from_github,   nick),
        ('gitlab',   email_from_gitlab,   nick),
        ('gravatar', email_from_gravatar_profile, nick),
        ('keybase',  email_from_keybase,  nick),
        ('pgp',      email_from_pgp,      nick),
    ]

    ex = ThreadPoolExecutor(max_workers=workers)
    futs = {ex.submit(run, n, f, a): n for n, f, a in tasks}
    try:
        for f in as_completed(futs, timeout=total_timeout):
            try:
                res = f.result(timeout=1)
            except Exception:
                continue
            sources.append(res)
            for e in (res.get('emails') or []):
                all_emails.setdefault(e, set()).add(res.get('source', '?'))
    except FutTimeout:
        pass
    finally:
        ex.shutdown(wait=False, cancel_futures=True)

    verified = []
    if all_emails:
        ex2 = ThreadPoolExecutor(max_workers=8)
        vf = {ex2.submit(_verify_email_mx, e): e for e in all_emails.keys()}
        try:
            for f in as_completed(vf, timeout=15):
                try:
                    v = f.result(timeout=1)
                except Exception:
                    continue
                v['sources'] = sorted(all_emails.get(v['email'], set()))
                verified.append(v)
        except FutTimeout:
            pass
        finally:
            ex2.shutdown(wait=False, cancel_futures=True)

    verified.sort(key=lambda x: (not x.get('has_mx'), x.get('email', '')))

    return {
        'nick': nick,
        'sources': sources,
        'emails': verified,
    }


STATUS_MEANING = {
    '200': 'есть', '201': 'создано', '204': 'пусто',
    '301': 'постоянный редирект', '302': 'временный редирект',
    '307': 'редирект (метод жив)', '308': 'редирект (метод жив)',
    '400': 'неправильный запрос', '401': 'нужна авторизация',
    '403': 'запрещено', '405': 'не тот метод', '418': 'чайник',
    '429': 'лимит', '500': 'ошибка', '502': 'шлюз',
    '503': 'недоступен', '504': 'таймаут шлюза', 'ERR': 'не ответил',
}

DANGEROUS_PATHS = {
    '/.git': 'git-репа', '/.git/config': 'креды git', '/.git/HEAD': 'git-репа',
    '/.env': 'ENV с секретами', '/.env.backup': 'бэкап ENV',
    '/.htaccess': 'apache config',
    '/phpinfo.php': 'phpinfo', '/info.php': 'phpinfo',
    '/admin': 'админка', '/admin.php': 'админка', '/wp-admin': 'wp админка',
    '/wp-login.php': 'wp логин', '/phpmyadmin': 'pma', '/pma': 'pma',
    '/adminer.php': 'adminer', '/backup': 'бэкапы', '/backups': 'бэкапы',
    '/server-status': 'apache status',
    '/actuator': 'spring', '/actuator/env': 'spring env',
    '/actuator/heapdump': 'spring heapdump',
    '/.DS_Store': 'метаданные macOS',
}

CULTURE_USER_AGENTS = {
    'chrome_linux': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'chrome_win':   'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'firefox':      'Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'safari':       'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
    'googlebot':    'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
    'curl':         'curl/8.0.1',
}

EXTERNAL_TOOLS = {
    'nmap':      ['nmap', '--version'],
    'subfinder': ['subfinder', '-version'],
    'whatweb':   ['whatweb', '--version'],
    'wafw00f':   ['wafw00f', '--version'],
    'nuclei':    ['nuclei', '-version'],
    'httpx':     ['httpx', '-version'],
    'nikto':     ['nikto', '-Version'],
}


def _which(cmd):
    try:
        subprocess.run(cmd, capture_output=True, timeout=4)
        return True
    except Exception:
        return False


def _available_tools():
    return {name: _which(cmd) for name, cmd in EXTERNAL_TOOLS.items()}


def _resolve(target):
    try:
        socket.inet_aton(target)
        return target, True
    except OSError:
        pass
    try:
        return socket.gethostbyname(target), False
    except Exception:
        return target, False


def _curl(args, timeout=8):
    if not shutil.which('curl'):
        return None
    try:
        r = subprocess.run(['curl', '-s'] + args,
                           capture_output=True, text=True, timeout=timeout)
        return r.stdout
    except Exception:
        return None


def _detect_real_host(target, ua):
    _, is_ip = _resolve(target)
    if not is_ip:
        return target
    res = _gethostbyaddr_safe(target, timeout=2)
    if res:
        ptr = res[0]
        if ptr and not ptr.replace('.', '').isdigit():
            return ptr
    for proto in ('http://', 'https://'):
        out = _curl(['-s', '-I', '-L', '--max-time', '3', '-A', ua,
                     f'{proto}{target}'], timeout=5)
        if not out:
            continue
        for line in out.split('\n'):
            if line.lower().startswith('location:'):
                loc = line.split(':', 1)[1].strip()
                host = re.sub(r'^https?://', '', loc).split('/')[0].split(':')[0]
                if host and host != target:
                    return host
    return target


def _base_url(host):
    if host.startswith('http'):
        return host.rstrip('/')
    return f'https://{host}'.rstrip('/')


def _probe_path(base, path, ua, timeout=3):
    url = base + path
    if shutil.which('curl'):
        out = _curl(['-X', 'GET', '--max-time', str(timeout),
                     '-H', 'Accept: application/json',
                     '-H', f'User-Agent: {ua}',
                     '-o', '/dev/null',
                     '-w', '%{http_code}|%{size_download}|%{content_type}|%{redirect_url}',
                     '-L',
                     url], timeout=timeout + 1)
        if out:
            parts = (out.split('|') + ['', '', '', ''])[:4]
            code, size, ct, _redir = parts
            return path, code.strip(), size.strip(), ct.strip(), ''
    try:
        r = http_get(url, timeout=timeout, throttle=0.05,
                     headers={'User-Agent': ua, 'Accept': 'application/json'},
                     use_cloudscraper=True)
        if r is None:
            return path, 'ERR', '0', '', ''
        return (path, str(r.status_code), str(len(r.text or '')),
                r.headers.get('Content-Type', ''), '')
    except Exception:
        return path, 'ERR', '0', '', ''


def _pick_best_ua(base_url):
    def probe(name, ua):
        if shutil.which('curl'):
            out = _curl(['-o', '/dev/null', '-w', '%{http_code}|%{size_download}',
                         '-A', ua, '--max-time', '3', '-L', base_url], timeout=5)
            if out:
                try:
                    code, size = out.split('|')[:2]
                    return name, ua, code, int(size or 0)
                except Exception:
                    pass
        try:
            r = http_get(base_url, timeout=4, throttle=0.2,
                         headers={'User-Agent': ua},
                         use_cloudscraper=True)
            if r is None:
                return name, ua, 'ERR', 0
            return name, ua, str(r.status_code), len(r.text or '')
        except Exception:
            return name, ua, 'ERR', 0

    results = {}
    with ThreadPoolExecutor(max_workers=len(CULTURE_USER_AGENTS)) as ex:
        futs = [ex.submit(probe, n, u) for n, u in CULTURE_USER_AGENTS.items()]
        for f in as_completed(futs):
            name, ua, code, size = f.result()
            results[name] = (ua, code, size)

    best_ua, best_score = CULTURE_USER_AGENTS['chrome_linux'], -1
    for name, (ua, code, size) in results.items():
        score = 0
        if code == '200':
            score = size
        elif code in ('301', '302'):
            score = size // 2
        if score > best_score:
            best_score, best_ua = score, ua
    return best_ua


PATHBRUTE_PATHS = [
    '/api', '/api/v1', '/api/v2',
    '/api/docs', '/api/swagger.json', '/api/openapi.json',
    '/graphql', '/graphiql',
    '/swagger', '/swagger.json', '/swagger-ui',
    '/openapi.json', '/api-docs', '/docs', '/redoc',
    '/admin', '/admin/login', '/administrator',
    '/login', '/auth', '/oauth/token',
    '/wp-admin', '/wp-login.php', '/wp-json',
    '/.git/HEAD', '/.git/config', '/.env', '/.env.backup',
    '/.htaccess', '/phpinfo.php', '/info.php',
    '/server-status',
    '/actuator', '/actuator/env', '/actuator/heapdump',
    '/phpmyadmin', '/pma', '/adminer.php',
    '/robots.txt', '/sitemap.xml', '/security.txt',
    '/.well-known/security.txt',
    '/backup', '/backups', '/.DS_Store',
]

AUTHBRUTE_AUTH_PATHS = [
    '/oauth/token', '/oauth/authorize', '/oauth2/token',
    '/connect/token',
    '/.well-known/openid-configuration',
    '/.well-known/jwks.json',
    '/.well-known/oauth-authorization-server',
    '/jwt', '/api/token', '/auth/token',
    '/auth/login', '/sso/login',
]

AUTHBRUTE_PROTECTED_PATHS = [
    '/api/me', '/api/user', '/api/profile', '/api/account',
    '/api/admin', '/api/settings', '/api/config',
    '/me', '/profile', '/account', '/admin', '/dashboard',
    '/api/users', '/api/orders',
]


def _safe_scan(label, fn):
    try:
        res = fn()
        if res is None:
            return {'found': [], 'note': f'{label}: пустой результат'}
        return res
    except Exception as e:
        return {'found': [], 'note': f'{label} упал: {e}'}


def scan_pathbrute(target, ua=None, base=None, real_host=None,
                   workers=40, total_timeout=40):
    def _run():
        from m_util import console
        _base = base
        if _base is None:
            _rh = real_host or _detect_real_host(
                target, ua or CULTURE_USER_AGENTS['chrome_linux'])
            _base = _base_url(_rh)
        _ua = ua or _pick_best_ua(_base)

        found = []
        done = 0
        total = len(PATHBRUTE_PATHS)
        ex = ThreadPoolExecutor(max_workers=workers)
        futs = [ex.submit(_probe_path, _base, p, _ua) for p in PATHBRUTE_PATHS]
        try:
            for f in as_completed(futs, timeout=total_timeout):
                done += 1
                if done % 10 == 0:
                    console.print(f"[dim]  pathbrute {done}/{total}[/dim]")
                try:
                    path, code, size, ct, body = f.result(timeout=1)
                except Exception:
                    continue
                if code in ('200', '201', '204', '301', '302', '307', '308',
                            '400', '401', '403', '405', '418', '429',
                            '500', '502', '503', '504'):
                    found.append((code, path, size, ct, body))
        except FutTimeout:
            console.print(f"[yellow]  pathbrute: общий таймаут {total_timeout}s, "
                          f"успел {done}/{total}[/yellow]")
        finally:
            ex.shutdown(wait=False, cancel_futures=True)

        found.sort(key=lambda x: (x[0], x[1]))
        sizes_200 = {}
        for code, path, size, ct, body in found:
            if code == '200' and size.isdigit():
                sizes_200.setdefault(int(size), []).append(path)
        spa_sizes = {s for s, ps in sizes_200.items() if len(ps) >= 3}

        return {
            'real_host': real_host or target,
            'base': _base,
            'user_agent': _ua,
            'total': total,
            'found': [
                {
                    'code': code, 'path': path, 'size': size, 'ct': ct,
                    'dangerous': DANGEROUS_PATHS.get(path),
                    'spa_suspected': code == '200' and size.isdigit() and int(size) in spa_sizes,
                    'body_snippet': '',
                }
                for code, path, size, ct, body in found
            ],
        }

    return _safe_scan('pathbrute', _run)


def scan_crawl(target, ua=None, base=None, real_host=None,
               workers=40, max_paths=80, total_timeout=20):
    def _run():
        from m_util import console
        _base = base
        if _base is None:
            _rh = real_host or _detect_real_host(
                target, ua or CULTURE_USER_AGENTS['chrome_linux'])
            _base = _base_url(_rh)
        _ua = ua or _pick_best_ua(_base)

        found_paths = set()
        sources = []

        r = http_get(_base + '/robots.txt', timeout=3, throttle=0.05,
                     headers={'User-Agent': _ua}, use_cloudscraper=True)
        out = r.text if r is not None else None
        if out and not out.strip().startswith('<'):
            sources.append({'source': 'robots.txt', 'content': out[:2000]})
            for line in out.split('\n'):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                low = line.lower()
                if low.startswith(('disallow:', 'allow:')):
                    p = line.split(':', 1)[1].strip()
                    if p and p != '/' and not p.startswith('*'):
                        found_paths.add(p)
                elif low.startswith('sitemap:'):
                    sm = line.split(':', 1)[1].strip()
                    if not sm.startswith('http') and 'http' in line:
                        sm = 'http' + line.split('http', 1)[1]
                    sources.append({'source': 'sitemap-link', 'content': sm})

        for sm_url in [_base + '/sitemap.xml'] + [
            s['content'] for s in sources if s['source'] == 'sitemap-link'
        ][:2]:
            r = http_get(sm_url, timeout=4, throttle=0.05,
                         headers={'User-Agent': _ua}, use_cloudscraper=True)
            out = r.text if r is not None else None
            if not out:
                continue
            locs = re.findall(r'<loc>\s*([^<\s]+)\s*</loc>', out)
            for loc in locs:
                m = re.match(r'https?://[^/]+(/.*)?', loc)
                if m:
                    p = m.group(1) or '/'
                    if p != '/':
                        found_paths.add(p)

        found_paths = sorted(p for p in found_paths if p and len(p) < 200)[:max_paths]

        checks = []
        done = 0
        total = len(found_paths)
        if total == 0:
            return {
                'base': _base,
                'user_agent': _ua,
                'sources': sources,
                'checked': [],
            }

        ex = ThreadPoolExecutor(max_workers=workers)
        futs = [ex.submit(_probe_path, _base, p, _ua) for p in found_paths]
        try:
            for f in as_completed(futs, timeout=total_timeout):
                done += 1
                if done % 20 == 0 and total > 20:
                    console.print(f"[dim]  crawl {done}/{total}[/dim]")
                try:
                    path, code, size, ct, body = f.result(timeout=1)
                except Exception:
                    continue
                checks.append({
                    'path': path, 'code': code, 'size': size, 'ct': ct,
                    'dangerous': DANGEROUS_PATHS.get(path),
                })
        except FutTimeout:
            console.print(f"[yellow]  crawl: общий таймаут {total_timeout}s, "
                          f"успел {done}/{total}[/yellow]")
        finally:
            ex.shutdown(wait=False, cancel_futures=True)

        checks.sort(key=lambda x: (x['code'], x['path']))
        return {
            'base': _base,
            'user_agent': _ua,
            'sources': sources,
            'checked': checks,
        }

    return _safe_scan('crawl', _run)


def scan_authbrute(target, ua=None, base=None, real_host=None,
                   workers=40, total_timeout=25):
    def _run():
        from m_util import console
        _base = base
        if _base is None:
            _rh = real_host or _detect_real_host(
                target, ua or CULTURE_USER_AGENTS['chrome_linux'])
            _base = _base_url(_rh)
        _ua = ua or _pick_best_ua(_base)

        all_paths = AUTHBRUTE_AUTH_PATHS + AUTHBRUTE_PROTECTED_PATHS
        auth_set = set(AUTHBRUTE_AUTH_PATHS)

        found = []
        done = 0
        total = len(all_paths)
        ex = ThreadPoolExecutor(max_workers=workers)
        futs = [ex.submit(_probe_path, _base, p, _ua) for p in all_paths]
        try:
            for f in as_completed(futs, timeout=total_timeout):
                done += 1
                if done % 10 == 0:
                    console.print(f"[dim]  authbrute {done}/{total}[/dim]")
                try:
                    path, code, size, ct, body = f.result(timeout=1)
                except Exception:
                    continue
                if code in ('200', '201', '204', '301', '302', '307', '308',
                            '400', '401', '403', '405', '429', '500', '502', '503'):
                    found.append({
                        'path': path, 'code': code, 'size': size, 'ct': ct,
                        'body': '', 'is_auth': path in auth_set,
                    })
        except FutTimeout:
            console.print(f"[yellow]  authbrute: общий таймаут {total_timeout}s, "
                          f"успел {done}/{total}[/yellow]")
        finally:
            ex.shutdown(wait=False, cancel_futures=True)

        found.sort(key=lambda x: x['path'])
        holes = [
            f for f in found
            if not f['is_auth'] and f['code'] == '200'
            and f['size'].isdigit() and int(f['size']) > 0
        ]

        return {
            'base': _base,
            'user_agent': _ua,
            'total_checked': total,
            'found': found,
            'holes': holes,
        }

    return _safe_scan('authbrute', _run)


def scan_geo_ip(ip, ua=None, total_timeout=15):
    ua = ua or CULTURE_USER_AGENTS['chrome_linux']
    endpoints = [
        ('ip-api.com', f'http://ip-api.com/json/{ip}?fields=status,country,regionName,city,lat,lon,isp,org,as,reverse,proxy,hosting,query'),
        ('ipwho.is',   f'https://ipwho.is/{ip}'),
        ('ipinfo.io',  f'https://ipinfo.io/{ip}/json'),
    ]

    def fetch(name, url):
        try:
            r = http_get(url, timeout=5, throttle=0.1,
                         headers={'User-Agent': ua},
                         use_cloudscraper=False)
            if r is None:
                return {'source': name, 'url': url, 'data': None, 'error': 'network'}
            body = r.text or ''
            if not body or body.strip().startswith('<'):
                return {'source': name, 'url': url, 'data': None, 'error': 'empty'}
            return {'source': name, 'url': url, 'data': body.strip()}
        except Exception as e:
            return {'source': name, 'url': url, 'data': None, 'error': str(e)}

    results = []
    ex = ThreadPoolExecutor(max_workers=len(endpoints))
    futs = [ex.submit(fetch, n, u) for n, u in endpoints]
    try:
        for f in as_completed(futs, timeout=total_timeout):
            try:
                results.append(f.result(timeout=1))
            except Exception:
                pass
    except FutTimeout:
        results.append({'source': '?', 'url': '', 'data': None,
                        'error': f'общий таймаут {total_timeout}s'})
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    return results


def _run(cmd, timeout):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (r.stdout or r.stderr or '').strip()
    except subprocess.TimeoutExpired:
        return '[таймаут]'
    except Exception as e:
        return f'[ошибка: {e}]'


def scan_external(target, ip):
    tools_ = _available_tools()
    out = {}
    is_ip = False
    try:
        socket.inet_aton(target)
        is_ip = True
    except OSError:
        pass

    if tools_.get('nmap') and is_ip:
        out['nmap'] = _run(['nmap', '-sV', '-T4', '--top-ports', '100', ip], 180)
    if tools_.get('subfinder') and not is_ip:
        out['subfinder'] = _run(['subfinder', '-d', target, '-silent'], 120)
    if tools_.get('whatweb'):
        out['whatweb'] = _run(['whatweb', '-a', '1', target], 60)
    if tools_.get('wafw00f'):
        out['wafw00f'] = _run(['wafw00f', target], 40)
    if tools_.get('httpx'):
        out['httpx'] = _run(['httpx', '-u', target, '-silent',
                             '-status-code', '-title', '-tech-detect'], 40)
    return out