"""
Форматирование вакансии в красивое сообщение для Telegram.

Использует HTML parse_mode aiogram (минимальное форматирование).
"""

from html import escape
from typing import Any


TIER_EMOJI = {
    "1": "🎯",
    "2": "📌",
    "3": "📋",
    "SKIP": "❌",
}


def format_salary(vacancy: dict[str, Any]) -> str:
    """Зарплата в виде строки."""
    sfrom = vacancy.get("salary_from")
    sto = vacancy.get("salary_to")
    if sfrom and sto:
        return f"{sfrom:,} – {sto:,} ₽".replace(",", " ")
    if sfrom:
        return f"от {sfrom:,} ₽".replace(",", " ")
    if sto:
        return f"до {sto:,} ₽".replace(",", " ")
    return "не указана"


def format_card(vacancy: dict[str, Any], tier: str, reason: str) -> str:
    """Главная карточка вакансии (без письма)."""
    emoji = TIER_EMOJI.get(tier, "📋")
    name = escape(vacancy.get("name", ""))
    company = escape(vacancy.get("company", "?"))
    salary = format_salary(vacancy)
    area = escape(vacancy.get("area", "?"))
    schedule = escape(vacancy.get("schedule", "?"))
    experience = escape(vacancy.get("experience", "?"))
    url = vacancy.get("url", "")

    lines = [
        f"{emoji} <b>Tier {tier}</b> · {salary}",
        f"<b>{name}</b>",
        f"<i>{company}</i>",
        "",
        f"📍 {area} · {schedule}",
        f"💼 Опыт: {experience}",
    ]
    if reason:
        lines.append("")
        lines.append(f"💡 {escape(reason)}")
    lines.append("")
    lines.append(f'<a href="{url}">Открыть на hh.ru</a>')

    return "\n".join(lines)


def format_letter(letter: str) -> str:
    """Сопроводительное письмо для отдельного сообщения."""
    safe = escape(letter)
    return f"<b>✉️ Сопроводительное письмо:</b>\n\n<pre>{safe}</pre>"


def format_stats(stats: dict[str, int]) -> str:
    """Статистика очереди."""
    return (
        f"📊 <b>Очередь:</b>\n"
        f"  Всего: {stats['total']}\n"
        f"  Обработано: {stats['processed']}\n"
        f"  Осталось: {stats['pending']}"
    )
