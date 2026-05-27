"""
Claude анализирует вакансию: ставит Tier и генерирует письмо.

Один запрос на вакансию = один tier + одно письмо.
Используется prompt caching для статичной части (профиль кандидата).
"""

import json
import re
from typing import Any

from anthropic import Anthropic


# Профиль кандидата (статичная часть промпта — кешируется)
CANDIDATE_PROFILE = """
Кандидат: Михаил Смыслов, 24 года, Москва.

Технический стек:
- Python 3.11+ (1+ год, средний уровень)
- Claude Code (основной рабочий инструмент, ежедневно)
- Claude API / Anthropic SDK
- ChatGPT, prompt engineering
- aiogram 3 / python-telegram-bot
- REST API, async/await
- SQLite, базовый SQL
- Git, GitHub
- Деплой на VPS (linux)

Опыт: коммерческого нет, есть реальные pet-проекты:

1. idea-to-code-bot — AI-агент: пользователь пишет идею текстом,
   бот через Claude API генерирует план, пишет код, упаковывает в ZIP.
   Стек: Python, aiogram 3, Claude API, async.
   github.com/smyslov20101-art/idea-to-code-bot

2. wife-bot — Telegram-бот с LLM-диалогом и автоматическими
   персональными уведомлениями на основе астро-транзитов.
   Стек: Python, python-telegram-bot, skyfield, SQLite, VPS.
   github.com/smyslov20101-art/wife-bot

Ожидаемая зарплата: от 60 000 ₽.
Формат: удалёнка или офис/гибрид в Москве.
Цель: первая коммерческая работа в направлении AI/Python разработки.

Критерии Tier:

Tier 1 (откликаться обязательно):
  - Claude Code / Claude API прямо в требованиях ИЛИ
  - AI-инженер / Prompt-инженер / Вайб-кодер направление
  - ЗП от 100к и реалистичные требования

Tier 2 (откликаться стоит):
  - AI-специалист / автоматизация на AI
  - Python-разработчик с AI-уклоном
  - ЗП от 60к, удалёнка

Tier 3 (откликаться если время есть):
  - Просто Python джун
  - AI без конкретики
  - Слабые условия но реалистичные требования

SKIP:
  - Senior уровень, требуют 3+ лет коммерческого опыта
  - Не наш стек (Laravel, WordPress, Bitrix, iOS, Android, DevOps, Data Science)
  - Офис не в Москве
  - Зарплата меньше 50к
  - Подозрительные конторы (Effective Mobile-подобные схемы)
"""


SYSTEM_PROMPT = f"""Ты — опытный карьерный консультант, помогающий джуну искать первую работу.
Твоя задача: оценить вакансию и при необходимости написать сопроводительное письмо.

{CANDIDATE_PROFILE}

ВАЖНО: возвращай ТОЛЬКО валидный JSON, ничего больше. Никаких комментариев перед или после JSON.
"""


def build_user_prompt(vacancy: dict[str, Any]) -> str:
    """Собрать промпт для конкретной вакансии."""
    salary_info = vacancy.get("salary")
    if salary_info:
        salary_str = f"{salary_info.get('from', '?')} - {salary_info.get('to', '?')} {salary_info.get('currency', 'RUR')}"
        if salary_info.get("gross"):
            salary_str += " (gross)"
    else:
        salary_str = "не указана"

    schedule = (vacancy.get("schedule") or {}).get("name", "не указан")
    experience = (vacancy.get("experience") or {}).get("name", "не указан")
    employer = (vacancy.get("employer") or {}).get("name", "?")
    area = (vacancy.get("area") or {}).get("name", "?")
    name = vacancy.get("name", "")

    snippet = vacancy.get("snippet") or {}
    requirement = snippet.get("requirement", "")
    responsibility = snippet.get("responsibility", "")

    return f"""Оцени вакансию и при необходимости напиши сопроводительное письмо.

Название: {name}
Компания: {employer}
Локация: {area}
Зарплата: {salary_str}
График: {schedule}
Опыт: {experience}

Требования: {requirement}

Обязанности: {responsibility}

Ответь в формате JSON:
{{
  "tier": "1" | "2" | "3" | "SKIP",
  "reason": "коротко 1 предложение почему именно этот tier",
  "letter": "сопроводительное письмо (только если tier 1, 2 или 3, иначе пустая строка)"
}}

Если tier 1/2/3 — напиши письмо в формате:
- Начало: "Здравствуйте!"
- 1 абзац: как стек кандидата подходит под эту конкретную вакансию (упомяни 1-2 ключевых требования)
- Портфолио (оба проекта с github ссылками)
- Концовка: "Готов к тестовому заданию. GitHub: github.com/smyslov20101-art"

Письмо короткое (10-15 строк), без воды, упоминай конкретно эту вакансию."""


def extract_json(text: str) -> dict[str, Any]:
    """Достать JSON из ответа Claude (может быть обёрнут в ```json)."""
    # Убираем markdown-обёртку если есть
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        text = match.group(1)
    else:
        # Берём от первой { до последней }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            text = text[start : end + 1]

    return json.loads(text)


class ClaudeAnalyzer:
    """Оценка вакансий через Claude API (или через прокси)."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-5",
        base_url: str | None = None,
    ):
        # base_url поддерживает прокси типа ProxyAPI.ru:
        # base_url="https://api.proxyapi.ru/anthropic"
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = Anthropic(**kwargs)
        self.model = model

    def analyze(self, vacancy: dict[str, Any]) -> dict[str, Any]:
        """
        Проанализировать одну вакансию.

        Returns:
            {"tier": "1"|"2"|"3"|"SKIP", "reason": str, "letter": str}
        """
        user_prompt = build_user_prompt(vacancy)

        response = self.client.messages.create(
            model=self.model,
            max_tokens=1500,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},  # кешируем профиль
                }
            ],
            messages=[{"role": "user", "content": user_prompt}],
        )

        text = response.content[0].text
        try:
            return extract_json(text)
        except json.JSONDecodeError as e:
            print(f"  ⚠️  Не смог распарсить JSON от Claude: {e}")
            print(f"     Ответ: {text[:200]}")
            return {"tier": "SKIP", "reason": f"parse error: {e}", "letter": ""}
