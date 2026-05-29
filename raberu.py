"""
Парсер вакансий с raberu.ru (публичного API нет — парсим HTML).
Возвращает {vacancy_id: vacancy} в формате совместимом с hh_client / filters.py.
"""

import re
import time
from typing import Any

import httpx
from bs4 import BeautifulSoup

BASE_URL = "https://raberu.ru"
VACANCIES_URL = "https://raberu.ru/moscow/vacancies"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Запросы специфичные для raberu
RABERU_QUERIES = [
    "AI разработчик",
    "вайб кодер",
    "prompt engineer",
    "claude",
    "автоматизация python",
    "telegram бот python",
    "AI специалист",
]


def fetch_raberu_vacancies(
    queries: list[str] | None = None,
    pages_per_query: int = 2,
    delay_sec: float = 1.2,
) -> dict[str, dict[str, Any]]:
    """
    Ищет вакансии на raberu.ru по ключевым словам.
    Возвращает {vacancy_id: vacancy} — формат совместим с hard_filter().
    """
    if queries is None:
        queries = RABERU_QUERIES

    all_vacancies: dict[str, dict] = {}

    with httpx.Client(headers=HEADERS, timeout=15, follow_redirects=True) as client:
        for query in queries:
            for page in range(1, pages_per_query + 1):
                try:
                    resp = client.get(
                        VACANCIES_URL,
                        params={
                            "search": query,
                            "sort": "publishedAt",
                            "order": "DESC",
                            "page": page,
                        },
                    )
                    if resp.status_code != 200:
                        print(f"  raberu: {query!r} стр.{page} → HTTP {resp.status_code}")
                        break

                    page_vacs = _parse_page(resp.text)
                    before = len(all_vacancies)
                    all_vacancies.update(page_vacs)
                    new_count = len(all_vacancies) - before

                    if new_count == 0:
                        break  # пустая страница — дальше нет смысла

                    time.sleep(delay_sec)

                except Exception as e:
                    print(f"  raberu ошибка ({query!r} стр.{page}): {e}")
                    break

    return all_vacancies


# ── Парсинг страницы ──────────────────────────────────────────────────────────

VACANCY_URL_RE = re.compile(r"/(?:moscow/)?vacancy/([\w-]+)$")


def _parse_page(html: str) -> dict[str, dict[str, Any]]:
    """Парсит одну страницу выдачи — возвращает словарь вакансий."""
    soup = BeautifulSoup(html, "html.parser")
    vacancies: dict[str, dict] = {}
    seen: set[str] = set()

    for a_tag in soup.find_all("a", href=VACANCY_URL_RE):
        href = a_tag.get("href", "")
        m = VACANCY_URL_RE.search(href)
        if not m:
            continue

        raw_id = m.group(1)
        vid = "raberu_" + raw_id  # префикс чтобы не пересекаться с hh.ru ID
        if vid in seen:
            continue
        seen.add(vid)

        title = a_tag.get_text(strip=True)
        if not title or len(title) < 3:
            continue

        card = _find_card(a_tag)
        card_text = card.get_text(" ", strip=True) if card else title
        url = BASE_URL + href if href.startswith("/") else href

        salary = _parse_salary(card_text)
        schedule_id, schedule_name = _parse_schedule(card_text)
        company = _parse_company(card)

        vacancies[vid] = {
            "id": vid,
            "name": title,
            "employer": {"name": company},
            "salary": salary,
            "schedule": {"id": schedule_id, "name": schedule_name},
            "area": {"id": "1", "name": "Москва"},
            "alternate_url": url,
            "_raw_description": card_text,
            "_source": "raberu",
        }

    return vacancies


# ── Вспомогательные функции ───────────────────────────────────────────────────

def _find_card(link_tag) -> Any | None:
    """Поднимаемся по DOM пока не найдём блок-карточку вакансии."""
    el = link_tag.parent
    for _ in range(8):
        if el is None:
            return None
        if el.name in ("article", "li", "div", "section"):
            if len(el.get_text(strip=True)) > 50:
                return el
        el = el.parent
    return None


def _parse_salary(text: str) -> dict | None:
    """Извлекает зарплату из текста карточки."""
    clean = text.replace("\xa0", "").replace(" ", "").lower()

    from_m = re.search(r"от(\d{4,7})", clean)
    to_m = re.search(r"до(\d{4,7})", clean)
    range_m = re.search(r"(\d{4,7})[–—\-](\d{4,7})", clean)

    salary_from = int(from_m.group(1)) if from_m else None
    salary_to = int(to_m.group(1)) if to_m else None

    if range_m and not salary_from:
        salary_from = int(range_m.group(1))
        salary_to = int(range_m.group(2))

    if not salary_from and not salary_to:
        return None

    gross = bool(re.search(r"до вычета|gross", text.lower()))
    return {
        "from": salary_from,
        "to": salary_to,
        "currency": "RUR",
        "gross": gross,
    }


def _parse_schedule(text: str) -> tuple[str, str]:
    """Определяет тип графика из текста карточки."""
    t = text.lower()
    if any(w in t for w in ["удалённ", "удален", "удалён", "remote", "дистанцион",
                              "из любой точки"]):
        return "remote", "Удалённая работа"
    if "гибкий" in t:
        return "flexible", "Гибкий график"
    return "fullDay", "Полный день"


def _parse_company(card) -> str:
    """Ищет название компании в карточке."""
    if card is None:
        return ""
    for a in card.find_all("a", href=re.compile(r"/(company|employer|org)/")):
        name = a.get_text(strip=True)
        if name:
            return name
    return ""
