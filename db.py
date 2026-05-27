"""
SQLite для дедупликации.
Храним только ID уже обработанных вакансий.
"""

import sqlite3
from pathlib import Path


class SeenDB:
    """Простая БД для отслеживания уже обработанных вакансий."""

    def __init__(self, db_path: str = "seen.db"):
        self.path = Path(db_path)
        self._init_schema()

    def _init_schema(self) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS seen_vacancies (
                    vacancy_id TEXT PRIMARY KEY,
                    seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    tier TEXT,
                    name TEXT,
                    employer TEXT
                )
            """)

    def is_seen(self, vacancy_id: str) -> bool:
        with sqlite3.connect(self.path) as conn:
            cursor = conn.execute(
                "SELECT 1 FROM seen_vacancies WHERE vacancy_id = ?",
                (vacancy_id,),
            )
            return cursor.fetchone() is not None

    def mark_seen(
        self,
        vacancy_id: str,
        tier: str = "",
        name: str = "",
        employer: str = "",
    ) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO seen_vacancies
                (vacancy_id, tier, name, employer)
                VALUES (?, ?, ?, ?)
                """,
                (vacancy_id, tier, name, employer),
            )

    def filter_unseen(self, vacancies: dict) -> dict:
        """Вернуть только новые (ещё не виденные) вакансии."""
        return {vid: v for vid, v in vacancies.items() if not self.is_seen(vid)}
