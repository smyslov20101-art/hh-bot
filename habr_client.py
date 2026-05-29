"""
Парсер вакансий с career.habr.com.
Возвращает {vacancy_id: vacancy} в формате совместимом с filters.py.
"""

import re
import time
from typing import Any

import httpx
from bs4 import BeautifulSoup

BASE_URL = "https://career.habr.com"
SEARCH_URL = "https://career.habr.com/vacancies"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

HABR_QUERIES = [
    "AI разработчик",
    "вайб кодер",
    "claude",
    "prompt engineer",
    "LLM",
    "AI автоматизация",
    "python telegram bot",
]


def fetch_habr_vacancies(
    queries: list[str] | None = None,
    pages_per_query: int = 2,
    delay_sec: float = 1.5,
) -> dict[str, dict[str, Any]]:
    """
    Ищет вакансии на career.habr.com.
    Возвращает {vacancy_id: vacancy} совместимый с hard_filter().
    """
    if queries is None:
        queries = HABR_QUERIES

    all_vacancies: dict[str, dict] = {}

    with httpx.Client(headers=HEADERS, timeout=15, follow_redirects=True) as client:
        for query in queries:
            for page in range(1, pages_per_query + 1):
                try:
                    params: dict = {
                        "q": query,
                        "type": "all",
                        "page": page,
                    }
                    resp = client.get(SEARCH_URL, params=params)
                    if resp.status_code != 200:
                        print(f"  habr: {query!r} стр.{page} → HTTP {resp.status_code}")
                        break

                    page_vacs = _parse_page(resp.text)
                    before = len(all_vacancies)
                    all_vacancies.update(page_vacs)
                    new_count = len(all_vacancies) - before

                    if new_count == 0:
                        break

                    time.sleep(delay_sec)

                except Exception as e:
                    print(f"  habr ошибка ({query!r} стр.{page}): {e}")
                    break

    return all_vacancies


VACANCY_URL_RE = re.compile(r"/vacancies/(\d+)")


def _parse_page(html: str) -> dict[str, dict[str, Any]]:
    """Парсит одну страницу выдачи Habr Career."""
    soup = BeautifulSoup(html, "html.parser")
    vacancies: dict[str, dict] = {}
    seen: set[str] = set()

    for a_tag in soup.find_all("a", href=VACANCY_URL_RE):
        href = a_tag.get("href", "")
        m = VACANCY_URL_RE.search(href)
        if not m:
            continue

        vid = "habr_" + m.group(1)
        if vid in seen:
            continue
        seen.add(vid)

        title = a_tag.get_text(strip=True)
        if not title or len(title) < 3:
            continue

        # Ищем карточку-контейнер
        card = _find_card(a_tag)
        card_text = card.get_text(" ", strip=True) if card else title
        url = BASE_URL + href if href.startswith("/") else href

        salary = _parse_salary(card_text)
        is_remote = _check_remote(card_text)
        company = _parse_company(card)

        vacancies[vid] = {
            "id": vid,
            "name": title,
            "employer": {"name": company},
            "salary": salary,
            "schedule": {
                "id": "remote" if is_remote else "fullDay",
                "name": "Удалённая работа" if is_remote else "Полный день",
            },
            "area": {"id": "1", "name": "Москва"},
            "alternate_url": url,
            "_raw_description": card_text,
            "_source": "habr",
        }

    return vacancies


def _find_card(link_tag) -> Any | None:
    """Поднимаемся по DOM чтобы найти карточку вакансии."""
    el = link_tag.parent
    for _ in range(10):
        if el is None:
            return None
        if el.name in ("article", "li", "div", "section"):
            text = el.get_text(strip=True)
            if len(text) > 60:
                return el
        el = el.parent
    return None


def _parse_salary(text: str) -> dict | None:
    """Извлекает зарплату из текста карточки."""
    clean = text.replace("\xa0", "").replace(" ", "").lower()

    from_m = re.search(r"от(\d{4,8})", clean)
    to_m = re.search(r"до(\d{4,8})", clean)

    if not from_m and not to_m:
        return None

    return {
        "from": int(from_m.group(1)) if from_m else None,
        "to": int(to_m.group(1)) if to_m else None,
        "currency": "RUR",
        "gross": False,
    }


def _check_remote(text: str) -> bool:
    """Проверяет есть ли удалёнка."""
    t = text.lower()
    return any(w in t for w in ["удалённо", "удаленно", "можно удалённо", "remote", "дистанцион"])


def _parse_company(card) -> str:
    """Ищет название компании в карточке."""
    if card is None:
        return ""
    for a in card.find_all("a", href=re.compile(r"/companies/")):
        name = a.get_text(strip=True)
        if name and len(name) > 1:
            return name
    return ""
