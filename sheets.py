"""
Синхронизация статусов вакансий с Google Sheets.

Структура таблицы (колонки A..I):
A: №   B: Tier   C: Компания   D: Вакансия   E: Зарплата
F: Статус   G: Ссылка   H: Заметки   I: Письмо
"""

from datetime import datetime
from typing import Any

import gspread
from oauth2client.service_account import ServiceAccountCredentials


SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

HEADERS = [
    "№", "Tier", "Компания", "Вакансия", "Зарплата",
    "Статус", "Ссылка", "Заметки", "Письмо",
]

# Индексы колонок (1-based, как в gspread)
COL_TIER = 2
COL_COMPANY = 3
COL_NAME = 4
COL_SALARY = 5
COL_STATUS = 6
COL_URL = 7
COL_NOTES = 8
COL_LETTER = 9


class SheetsSync:
    """Работа с Google Sheets через сервисный аккаунт."""

    def __init__(self, creds_path: str, sheet_id: str):
        creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, SCOPES)
        client = gspread.authorize(creds)
        self.sheet = client.open_by_key(sheet_id).sheet1

    def find_row_by_vacancy_id(self, vacancy_id: str) -> int | None:
        """
        Найти номер строки по vacancy_id (ищем в колонке Ссылка).

        Returns:
            Номер строки (1-based) или None.
        """
        urls = self.sheet.col_values(COL_URL)
        for idx, url in enumerate(urls, start=1):
            if not url:
                continue
            # URL может быть в формате HYPERLINK или просто строкой
            if vacancy_id in url:
                return idx
        return None

    def update_status(self, vacancy_id: str, status: str) -> bool:
        """
        Обновить статус вакансии по ID. Если строки нет — вернёт False.
        """
        row = self.find_row_by_vacancy_id(vacancy_id)
        if row is None:
            return False
        self.sheet.update_cell(row, COL_STATUS, status)
        return True

    def add_vacancy(
        self,
        vacancy: dict[str, Any],
        tier: str,
        letter: str,
        status: str = "Новая",
        notes: str = "",
    ) -> int:
        """
        Добавить вакансию в конец таблицы.

        Returns:
            Номер новой строки.
        """
        salary_from = vacancy.get("salary_from")
        salary_to = vacancy.get("salary_to")
        if salary_from and salary_to:
            salary_str = f"{salary_from:,}-{salary_to:,} RUR".replace(",", " ")
        elif salary_from:
            salary_str = f"от {salary_from:,} RUR".replace(",", " ")
        elif salary_to:
            salary_str = f"до {salary_to:,} RUR".replace(",", " ")
        else:
            salary_str = "не указана"

        url = vacancy.get("url", "")
        row_number = len(self.sheet.col_values(1)) + 1

        row = [
            row_number - 1,
            tier,
            vacancy.get("company", "?"),
            vacancy.get("name", ""),
            salary_str,
            status,
            f'=HYPERLINK("{url}","{url}")' if url else "",
            notes,
            letter,
        ]
        self.sheet.append_row(row, value_input_option="USER_ENTERED")
        return row_number
