"""
Очередь проанализированных вакансий для Telegram-бота.

Читает analyzed_vacancies.json (формат от Claude Code).
Отслеживает текущую позицию для каждого пользователя.
"""

import json
from pathlib import Path
from typing import Any


QUEUE_PATH = Path("analyzed_vacancies.json")
STATE_PATH = Path("queue_state.json")


class VacancyQueue:
    """Очередь вакансий для показа в Telegram."""

    def __init__(self, queue_path: Path = QUEUE_PATH, state_path: Path = STATE_PATH):
        self.queue_path = queue_path
        self.state_path = state_path
        self._vacancies: list[dict[str, Any]] = []
        self._processed_ids: set[str] = set()
        self.reload()

    def reload(self) -> None:
        """Перечитать файлы с диска."""
        if self.queue_path.exists():
            self._vacancies = json.loads(self.queue_path.read_text(encoding="utf-8"))
        else:
            self._vacancies = []

        if self.state_path.exists():
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            self._processed_ids = set(state.get("processed", []))
        else:
            self._processed_ids = set()

    def _save_state(self) -> None:
        self.state_path.write_text(
            json.dumps({"processed": list(self._processed_ids)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def pending(self) -> list[dict[str, Any]]:
        """Вакансии, которые ещё не показаны или не обработаны."""
        return [v for v in self._vacancies if v["id"] not in self._processed_ids]

    def next_vacancy(self) -> dict[str, Any] | None:
        """Следующая вакансия в очереди."""
        pending = self.pending()
        return pending[0] if pending else None

    def mark_processed(self, vacancy_id: str) -> None:
        """Пометить вакансию как обработанную."""
        self._processed_ids.add(vacancy_id)
        self._save_state()

    def stats(self) -> dict[str, int]:
        """Сколько всего в очереди и сколько обработано."""
        return {
            "total": len(self._vacancies),
            "processed": len(self._processed_ids),
            "pending": len(self.pending()),
        }
