"""
Поиск + фильтр вакансий. БЕЗ Claude API.

Запуск: python search.py

Что делает:
1. Ищет вакансии на hh.ru по запросам из .env
2. Жёстко фильтрует (зарплата, локация, чёрный список)
3. Убирает уже виденные (SQLite)
4. Сохраняет новые в pending_vacancies.json

Дальше Claude Code (я) сам разбирает этот JSON,
ставит Tier и пишет письма — без API, через подписку.
"""

import sys
sys.stdout.reconfigure(encoding="utf-8")

import os
import json
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from hh_client import HHClient
from filters import hard_filter
from db import SeenDB


def main():
    load_dotenv()

    queries_raw = os.getenv(
        "SEARCH_QUERIES",
        "Claude Code,AI разработчик,Prompt инженер,вайб кодер,AI специалист",
    )
    queries = [q.strip() for q in queries_raw.split(",") if q.strip()]
    min_salary = int(os.getenv("MIN_SALARY", "60000"))
    max_total = int(os.getenv("MAX_VACANCIES", "40"))  # hh.ru блокирует при >50

    # ─── 1. Поиск ────────────────────────────────────────────
    print(f"\n🔍 Поиск по {len(queries)} запросам...")
    hh = HHClient(delay_sec=0.7)
    raw = hh.search_and_fetch(queries, per_page=50, max_total=max_total)
    print(f"\n  Всего загружено: {len(raw)}")

    # ─── 2. Жёсткий фильтр ───────────────────────────────────
    filtered = hard_filter(raw, min_salary=min_salary)

    # ─── 3. Дедупликация ─────────────────────────────────────
    db = SeenDB()
    new_vacancies = db.filter_unseen(filtered)
    print(f"\n  Новых (не виденных): {len(new_vacancies)}")

    if not new_vacancies:
        print("\n✅ Нет новых вакансий. Выхожу.")
        # Сохраняем пустой файл чтобы Claude увидел "новых нет"
        Path("pending_vacancies.json").write_text(
            json.dumps([], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return

    # ─── 4. Упрощаем для Claude ──────────────────────────────
    # Оставляем только поля важные для скоринга
    simplified = []
    for vid, v in new_vacancies.items():
        salary = v.get("salary") or {}
        simplified.append({
            "id": vid,
            "name": v.get("name", ""),
            "company": (v.get("employer") or {}).get("name", ""),
            "salary_from": salary.get("from"),
            "salary_to": salary.get("to"),
            "salary_currency": salary.get("currency", "RUR"),
            "salary_gross": salary.get("gross", False),
            "experience": (v.get("experience") or {}).get("name", ""),
            "schedule": (v.get("schedule") or {}).get("name", ""),
            "area": (v.get("area") or {}).get("name", ""),
            "url": v.get("alternate_url", ""),
            "description": (v.get("_raw_description") or "")[:2500],
        })

        # Помечаем как seen — даже если не оценим, повторно не вылезет
        db.mark_seen(
            vacancy_id=vid,
            name=v.get("name", ""),
            employer=(v.get("employer") or {}).get("name", ""),
        )

    out_path = Path("pending_vacancies.json")
    out_path.write_text(
        json.dumps(simplified, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\n{'='*60}")
    print(f"✅ Сохранено {len(simplified)} вакансий в {out_path.name}")
    print(f"   Время: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}")
    print(f"\n💡 Скажи Claude Code: 'разбери pending_vacancies.json'")


if __name__ == "__main__":
    main()
