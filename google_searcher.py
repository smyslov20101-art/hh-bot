"""
Поиск вакансий и компаний через Google.

Два режима:
1. Поиск вакансий — «вайб кодер вакансия Москва», «AI разработчик ищем» и т.д.
2. Поиск компаний — «ищем AI специалиста», «нужен вайб-кодер» и т.д.

Возвращает {id: vacancy} совместимый с filters.py.
"""

import re
import time
import hashlib
from typing import Any

import httpx
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.google.com/",
}

# Запросы для поиска вакансий через Google
VACANCY_QUERIES = [
    "вайб кодер вакансия Москва 2026",
    "AI разработчик вакансия удалённо 2026",
    "prompt engineer вакансия Россия",
    "claude code разработчик вакансия",
    "вакансия python telegram bot автоматизация",
    "\"ищем вайб-кодера\" OR \"ищем вайбкодера\"",
    "\"AI специалист\" вакансия python удалённо",
]

# Запросы для поиска компаний которые ХОТЯТ AI (не объявили вакансию, но можно предложить)
COMPANY_QUERIES = [
    "\"ищем AI\" \"автоматизация\" стартап Москва контакты",
    "\"хотим внедрить AI\" компания Москва",
    "\"нужен разработчик\" python telegram бот компания",
    "\"ai автоматизация\" \"ищем\" стартап 2026",
]

# Сайты с которых НЕ берём (там есть свои парсеры)
BLOCKED_DOMAINS = [
    "hh.ru", "raberu.ru", "career.habr.com", "superjob.ru",
    "trudvsem.ru", "zarplata.ru", "headhunter.ru",
    "linkedin.com", "indeed.com",
]


def fetch_google_vacancies(
    queries: list[str] | None = None,
    delay_sec: float = 3.0,
) -> dict[str, dict[str, Any]]:
    """
    Ищет вакансии через Google.
    Возвращает {vacancy_id: vacancy}.
    """
    if queries is None:
        queries = VACANCY_QUERIES

    all_vacancies: dict[str, dict] = {}

    with httpx.Client(headers=HEADERS, timeout=15, follow_redirects=True) as client:
        for query in queries:
            try:
                results = _google_search(client, query)
                for r in results:
                    if _is_blocked_domain(r["url"]):
                        continue
                    vid = "google_" + hashlib.md5(r["url"].encode()).hexdigest()[:12]
                    if vid not in all_vacancies:
                        all_vacancies[vid] = _result_to_vacancy(vid, r)

                time.sleep(delay_sec)  # Google не любит частые запросы

            except Exception as e:
                print(f"  google ошибка ({query!r}): {e}")
                continue

    return all_vacancies


def fetch_google_companies(
    queries: list[str] | None = None,
    delay_sec: float = 3.0,
) -> list[dict[str, str]]:
    """
    Ищет компании которые могут нуждаться в AI-специалисте.
    Возвращает список {title, url, snippet} для аутрич-очереди.
    """
    if queries is None:
        queries = COMPANY_QUERIES

    companies: list[dict] = []
    seen_urls: set[str] = set()

    with httpx.Client(headers=HEADERS, timeout=15, follow_redirects=True) as client:
        for query in queries:
            try:
                results = _google_search(client, query)
                for r in results:
                    if r["url"] not in seen_urls and not _is_blocked_domain(r["url"]):
                        seen_urls.add(r["url"])
                        companies.append(r)
                time.sleep(delay_sec)
            except Exception as e:
                print(f"  google companies ошибка ({query!r}): {e}")

    return companies


# ── Внутренние функции ────────────────────────────────────────────────────────

def _google_search(client: httpx.Client, query: str) -> list[dict[str, str]]:
    """Делает поиск в Google и парсит результаты."""
    resp = client.get(
        "https://www.google.com/search",
        params={"q": query, "num": 10, "hl": "ru", "gl": "ru"},
    )
    if resp.status_code != 200:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    results = []

    # Google меняет классы, ищем по структуре
    for g in soup.find_all("div", class_=re.compile(r"^(g|tF2Cxc|MjjYud)")):
        a = g.find("a", href=True)
        if not a:
            continue
        href = a.get("href", "")
        if not href.startswith("http"):
            continue

        title_el = g.find(["h3", "h2"])
        title = title_el.get_text(strip=True) if title_el else href

        snippet_el = g.find("div", class_=re.compile(r"VwiC3b|s3v9rd|yDYNvb"))
        snippet = snippet_el.get_text(strip=True) if snippet_el else ""

        if title and href:
            results.append({"title": title, "url": href, "snippet": snippet})

    return results


def _is_blocked_domain(url: str) -> bool:
    """Проверяет что URL не с сайтов у которых есть свои парсеры."""
    return any(domain in url for domain in BLOCKED_DOMAINS)


def _result_to_vacancy(vid: str, result: dict) -> dict[str, Any]:
    """Конвертирует Google-результат в формат вакансии."""
    title = result["title"]
    snippet = result["snippet"]
    url = result["url"]
    combined = title + " " + snippet

    # Пытаемся угадать зарплату из сниппета
    salary = _parse_salary_from_text(snippet)

    is_remote = any(w in combined.lower() for w in
                    ["удалённо", "удаленно", "remote", "дистанцион", "из любой точки"])

    return {
        "id": vid,
        "name": title,
        "employer": {"name": _extract_domain(url)},
        "salary": salary,
        "schedule": {
            "id": "remote" if is_remote else "fullDay",
            "name": "Удалённая работа" if is_remote else "Неизвестно",
        },
        "area": {"id": "1", "name": "Москва"},
        "alternate_url": url,
        "_raw_description": combined,
        "_source": "google",
    }


def _parse_salary_from_text(text: str) -> dict | None:
    clean = text.replace("\xa0", "").replace(" ", "").lower()
    from_m = re.search(r"от(\d{4,7})", clean)
    to_m = re.search(r"до(\d{4,7})", clean)
    if not from_m and not to_m:
        return None
    return {
        "from": int(from_m.group(1)) if from_m else None,
        "to": int(to_m.group(1)) if to_m else None,
        "currency": "RUR",
        "gross": False,
    }


def _extract_domain(url: str) -> str:
    m = re.search(r"https?://(?:www\.)?([^/]+)", url)
    return m.group(1) if m else url
