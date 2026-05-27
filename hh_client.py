"""
Клиент для hh.ru через парсинг публичных страниц.

API hh.ru теперь требует OAuth, поэтому используем парсинг:
1. Поисковая страница даёт ID вакансий
2. Страница вакансии даёт детали (JSON-LD + data-qa атрибуты)

Запросы делаются с задержкой чтобы не упереться в rate limit.
"""

import re
import time
import json
from typing import Any

import httpx
from bs4 import BeautifulSoup


BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


class HHClient:
    """Клиент для hh.ru через HTML-парсинг."""

    def __init__(self, delay_sec: float = 1.0):
        self.delay = delay_sec
        self.headers = {
            "User-Agent": BROWSER_UA,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        }
        self.client = httpx.Client(
            headers=self.headers,
            timeout=30.0,
            follow_redirects=True,
        )

    def __del__(self):
        try:
            self.client.close()
        except Exception:
            pass

    def search_ids(
        self,
        text: str,
        area: int = 1,  # 1 = Москва
        per_page: int = 50,
    ) -> list[str]:
        """
        Получить список ID вакансий со страницы поиска.

        Returns:
            Список ID (строки).
        """
        url = "https://hh.ru/search/vacancy"
        params = {
            "text": text,
            "area": area,
            "items_on_page": per_page,
            "order_by": "publication_time",
        }
        response = self.client.get(url, params=params)
        response.raise_for_status()

        # Извлекаем все упоминания /vacancy/{id}
        ids = re.findall(r"/vacancy/(\d+)", response.text)
        # Уникальные, сохраняя порядок
        seen = set()
        unique_ids: list[str] = []
        for vid in ids:
            if vid not in seen:
                seen.add(vid)
                unique_ids.append(vid)
        return unique_ids

    def get_vacancy(self, vacancy_id: str, retries: int = 3) -> dict[str, Any] | None:
        """
        Получить детали одной вакансии (парсинг страницы).

        Args:
            vacancy_id: ID вакансии
            retries: сколько раз пробовать при сетевых ошибках

        Returns:
            Словарь с полями (формат совместим с api.hh.ru).
            None если 404 или превышены попытки.
        """
        url = f"https://hh.ru/vacancy/{vacancy_id}"
        last_error: Exception | None = None

        for attempt in range(retries):
            try:
                response = self.client.get(url)
                response.raise_for_status()
                return self._parse_vacancy(response.text, vacancy_id, url)
            except httpx.HTTPStatusError as e:
                # 404, 403 — больше пробовать смысла нет
                if e.response.status_code in (404, 403, 410):
                    return None
                last_error = e
            except (httpx.RemoteProtocolError, httpx.ReadTimeout, httpx.ConnectError) as e:
                last_error = e
                # пересоздаём клиент — сервер обрубил соединение
                self._reset_client()

            # Экспоненциальная пауза перед повтором
            time.sleep(2 ** attempt)

        print(f"    ⚠️  {vacancy_id}: не загрузил после {retries} попыток ({last_error})")
        return None

    def _reset_client(self) -> None:
        """Пересоздать HTTP-клиент (на случай разорванного соединения)."""
        try:
            self.client.close()
        except Exception:
            pass
        self.client = httpx.Client(
            headers=self.headers,
            timeout=30.0,
            follow_redirects=True,
        )

    def _parse_vacancy(
        self,
        html: str,
        vacancy_id: str,
        url: str,
    ) -> dict[str, Any]:
        """Разобрать HTML страницы вакансии в структуру."""
        soup = BeautifulSoup(html, "html.parser")

        # JSON-LD имеет надёжные поля
        jsonld = self._extract_jsonld(soup)

        title = self._text_by_qa(soup, "vacancy-title") or jsonld.get("title", "")
        company = (
            self._text_by_qa(soup, "vacancy-company-name")
            or (jsonld.get("hiringOrganization") or {}).get("name", "")
        )
        salary_text = self._text_by_qa(soup, "vacancy-salary")
        experience = self._text_by_qa(soup, "vacancy-experience")
        description = self._text_by_qa(soup, "vacancy-description")
        hiring_formats = self._text_by_qa(soup, "vacancy-hiring-formats")

        # Адрес/локация
        location = jsonld.get("jobLocation", {})
        address = location.get("address", {}) if isinstance(location, dict) else {}
        city = address.get("addressLocality", "")

        # Парсим зарплату из текста
        salary_info = self._parse_salary(salary_text or "")

        return {
            "id": vacancy_id,
            "name": title,
            "alternate_url": url,
            "employer": {"name": company},
            "salary": salary_info,
            "experience": {"name": experience},
            "schedule": {"name": hiring_formats},
            "area": {"name": city, "id": "1" if "Москва" in city else ""},
            "snippet": {
                "requirement": description[:1500] if description else "",
                "responsibility": "",
            },
            "_raw_description": description,
            "_raw_salary": salary_text,
        }

    @staticmethod
    def _text_by_qa(soup: BeautifulSoup, qa: str) -> str:
        """Достать текст элемента по data-qa атрибуту."""
        el = soup.find(attrs={"data-qa": qa})
        if el is None:
            return ""
        return el.get_text(" ", strip=True)

    @staticmethod
    def _extract_jsonld(soup: BeautifulSoup) -> dict[str, Any]:
        """Найти JSON-LD JobPosting на странице."""
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                if isinstance(data, dict) and data.get("@type") == "JobPosting":
                    return data
            except (json.JSONDecodeError, AttributeError):
                continue
        return {}

    @staticmethod
    def _parse_salary(text: str) -> dict[str, Any] | None:
        """
        Распарсить текстовое представление зарплаты.

        Примеры:
            "от 100 000 ₽ за месяц на руки"
            "от 150 000 до 250 000 ₽ за месяц до вычета налогов"
        """
        if not text:
            return None

        # Убираем неразрывные пробелы и лишнее
        clean = text.replace(" ", " ").replace(" ", " ")

        # Ищем числа (5-7 цифр)
        nums = [int(n.replace(" ", "")) for n in re.findall(r"\d[\d ]{3,}", clean)]
        if not nums:
            return None

        is_gross = "до вычета" in clean.lower() or "gross" in clean.lower()
        currency = "RUR"
        if "$" in clean or "USD" in clean.upper():
            currency = "USD"
        elif "€" in clean or "EUR" in clean.upper():
            currency = "EUR"

        salary_from: int | None = nums[0] if nums else None
        salary_to: int | None = nums[1] if len(nums) > 1 else None

        # Эвристика: если "от X" без "до" — только from; если "до X" — только to
        lower = clean.lower()
        if "от " in lower and "до " not in lower:
            salary_to = None
        elif "до " in lower and "от " not in lower:
            salary_to = salary_from
            salary_from = None

        return {
            "from": salary_from,
            "to": salary_to,
            "currency": currency,
            "gross": is_gross,
        }

    def search_and_fetch(
        self,
        queries: list[str],
        per_page: int = 50,
        max_total: int = 100,
    ) -> dict[str, dict[str, Any]]:
        """
        Поиск по нескольким запросам + загрузка деталей.

        Returns:
            {vacancy_id: vacancy_dict}
        """
        # Шаг 1: собираем все ID
        all_ids: list[str] = []
        seen_ids: set[str] = set()

        for query in queries:
            print(f"  → Ищу: {query}")
            ids = self.search_ids(text=query, per_page=per_page)
            new_count = 0
            for vid in ids:
                if vid not in seen_ids:
                    seen_ids.add(vid)
                    all_ids.append(vid)
                    new_count += 1
            print(f"    нашёл {len(ids)} (новых: {new_count}, всего: {len(all_ids)})")
            time.sleep(self.delay)

        # Ограничение
        all_ids = all_ids[:max_total]

        # Шаг 2: загружаем детали
        print(f"\n  Загружаю детали для {len(all_ids)} вакансий...")
        result: dict[str, dict[str, Any]] = {}
        for i, vid in enumerate(all_ids, 1):
            vacancy = self.get_vacancy(vid)
            if vacancy:
                result[vid] = vacancy
            if i % 10 == 0:
                print(f"    {i}/{len(all_ids)} (загружено: {len(result)})")
            # Каждые 25 запросов — пауза побольше, чтобы не упереться в антибот
            if i % 25 == 0 and i < len(all_ids):
                print(f"    ⏸  Пауза 10 сек чтобы не словить блок...")
                time.sleep(10)
            else:
                time.sleep(self.delay)

        return result
