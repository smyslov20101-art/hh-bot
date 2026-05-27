"""
Отклик на вакансию через hh.ru API.

Используем OAuth токен. Лимит — не больше 15 откликов в день,
случайная задержка чтобы не сработала анти-бот защита.
"""

import random
import time
from typing import Any

import httpx


class HHApplier:
    """Отправка откликов на hh.ru через API."""

    BASE_URL = "https://api.hh.ru"

    def __init__(self, access_token: str, resume_id: str | None = None):
        self.access_token = access_token
        self.resume_id = resume_id
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "User-Agent": "JobSearchBot/1.0 (smyslov.20101@gmail.com)",
        }

    def get_my_resumes(self) -> list[dict[str, Any]]:
        """Получить все резюме пользователя."""
        with httpx.Client(headers=self.headers, timeout=30.0) as client:
            r = client.get(f"{self.BASE_URL}/resumes/mine")
            r.raise_for_status()
            return r.json().get("items", [])

    def auto_pick_resume(self) -> str | None:
        """Автоматически выбрать самое подходящее резюме (первое из активных)."""
        resumes = self.get_my_resumes()
        if not resumes:
            return None
        # Берём первое (на hh.ru обычно сверху самое актуальное)
        return resumes[0]["id"]

    def apply(
        self,
        vacancy_id: str,
        message: str,
        resume_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Откликнуться на вакансию.

        Args:
            vacancy_id: ID вакансии
            message: сопроводительное письмо
            resume_id: ID резюме (если не задан — берём self.resume_id)

        Returns:
            {"ok": True, "negotiation_id": "...", "raw": {...}}
            или {"ok": False, "error": "..."}
        """
        rid = resume_id or self.resume_id
        if not rid:
            return {"ok": False, "error": "Не задан resume_id"}

        # Случайная задержка — выглядим как живой пользователь
        delay = random.uniform(2, 8)
        time.sleep(delay)

        data = {
            "vacancy_id": vacancy_id,
            "resume_id": rid,
            "message": message,
        }

        with httpx.Client(headers=self.headers, timeout=30.0) as client:
            r = client.post(f"{self.BASE_URL}/negotiations", data=data)

        if r.status_code in (201, 204):
            try:
                body = r.json() if r.text else {}
            except Exception:
                body = {}
            return {"ok": True, "negotiation_id": body.get("id"), "raw": body}

        try:
            err_body = r.json()
        except Exception:
            err_body = {"text": r.text}
        return {
            "ok": False,
            "status": r.status_code,
            "error": err_body,
        }
