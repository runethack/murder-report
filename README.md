# MURDER Report

MURDER Report — консольный Python-инструмент для первичного анализа открытых данных: username, доменов, email, телефонов, IP и изображений.

> Используйте программу только на своих системах или при наличии явного разрешения. Результаты внешних сервисов могут быть неполными или ошибочными.

## Возможности

- **Username:** поиск публичных профилей на поддерживаемых площадках и публичных email-источников.
- **Домен:** DNS, WHOIS/RDAP, субдомены, 2IP и проверка веб-путей.
- **Email:** синтаксис, MX, disposable-домены, Gravatar и доступная проверка утечек.
- **Телефон:** нормализация через `phonenumbers`, регион, оператор, тип номера, WhatsApp и публичные отзывы.
- **IP:** геолокация, WHOIS/RDAP, reverse DNS и дополнительные geo-источники.
- **Изображение:** EXIF/GPS и ссылки на сервисы обратного поиска.
- **Отчёты:** каждый запуск сохраняет JSON и HTML.
- **Веб-страница:** `index.html` делает запрос к `https://num.voxlink.ru/get/v2/?num=`.

## Установка

Требуется Python 3.9+.

```bash
git clone https://github.com/runethack/murder-report.git
cd murder-report
python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\\Scripts\\activate
python -m pip install -r requirements.txt
```

Системные программы `curl`, `whois`, `dig` и `nmap` необязательны. Они расширяют возможности, но программа не должна автоматически устанавливать их с правами администратора.

## Использование

```bash
python main.py                  # интерактивное меню
python main.py -u username      # username
python main.py -d example.com   # домен
python main.py -e user@example.com
python main.py -p +79001234567
python main.py -i 8.8.8.8
python main.py --image photo.jpg
python main.py --emails username
```

Несколько типов анализа можно объединить:

```bash
python main.py -u username -d example.com -e user@example.com -o report
```

## Агрессивный режим

`--full` включает активные проверки веб-цели: расширенный перебор путей, чтение `robots.txt`/sitemap, проверку auth/OAuth-путей и внешние инструменты для IP. Это создаёт дополнительные запросы, может сработать WAF/rate-limit и должно применяться только с разрешением владельца:

```bash
python main.py -d example.com --full
python main.py -i 8.8.8.8 --full
```

Без `--full` программа всё равно выполняет базовую веб-проверку путей для домена/IP. Не запускайте её против чужих целей.

## Результаты

```text
report.json   структурированные данные
report.html   читаемый HTML-отчёт
```

Имя задаётся через `-o`. Отчёты сохраняются в каталоге репозитория.

## Источник телефонных данных

В `index.html` используется:

```javascript
const API_URL = "https://num.voxlink.ru/get/v2/?num=";
```

Номер передаётся URL-кодированным параметром. API и его формат являются сторонним сервисом; при проблемах с CORS или доступностью запрос из браузера может не сработать.

## Структура

```text
main.py          CLI и интерактивное меню
m_tools.py       анализаторы и сетевые источники
m_util.py        HTTP-утилиты и генерация отчётов
index.html       отдельная веб-форма телефонного поиска
requirements.txt Python-зависимости
LICENSE          MIT License
```

## Лицензия

MIT License. Подробности — в `LICENSE`.
