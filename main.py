"""
Главный orchestrator.

Запуск: python main.py

Что делает:
1. Ищет вакансии на hh.ru по запросам из .env
2. Фильтрует жёстко (зарплата, локация, чёрный список)
3. Убирает уже виденные (SQLite)
4. Анализирует через Claude — Tier + письмо
5. Добавляет в Google Sheets (или CSV если sheets не настроены)
"""

import sys
sys.stdout.reconfigure(encoding="utf-8")

import os
import csv
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from hh_client import HHClient
from filters import hard_filter
from claude_analyzer import ClaudeAnalyzer
from db import SeenDB


def write_to_csv(rows: list[dict], path: str = "results.csv") -> None:
    """Запасной вариант: пишем в CSV если Google Sheets не настроен."""
    file_path = Path(path)
    is_new = not file_path.exists()

    with open(path, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["Дата", "Tier", "Компания", "Вакансия", "Зарплата", "Локация", "Ссылка", "Письмо", "Reason"],
        )
        if is_new:
            writer.writeheader()
        writer.writerows(rows)
    print(f"  ✅ Записано в {path}")


def vacancy_to_row(vacancy: dict, tier: str, letter: str, reason: str) -> dict:
    """Превратить вакансию в строку для CSV/Sheets."""
    salary_info = vacancy.get("salary")
    if salary_info:
        sfrom = salary_info.get("from", "")
        sto = salary_info.get("to", "")
        cur = salary_info.get("currency", "RUR")
        if sfrom and sto:
            salary_str = f"{sfrom}-{sto} {cur}"
        elif sfrom:
            salary_str = f"от {sfrom} {cur}"
        elif sto:
            salary_str = f"до {sto} {cur}"
        else:
            salary_str = "?"
    else:
        salary_str = "не указана"

    return {
        "Дата": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "Tier": tier,
        "Компания": (vacancy.get("employer") or {}).get("name", "?"),
        "Вакансия": vacancy.get("name", ""),
        "Зарплата": salary_str,
        "Локация": (vacancy.get("area") or {}).get("name", "?"),
        "Ссылка": vacancy.get("alternate_url", ""),
        "Письмо": letter,
        "Reason": reason,
    }


def main():
    load_dotenv()

    # ─── Config ──────────────────────────────────────────────
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ ANTHROPIC_API_KEY не задан в .env")
        return

    base_url = os.getenv("ANTHROPIC_BASE_URL") or None
    sheet_id = os.getenv("SHEET_ID", "")
    creds_path = os.getenv("GOOGLE_CREDS_PATH", "./credentials.json")
    queries = [q.strip() for q in os.getenv("SEARCH_QUERIES", "Claude Code,AI разработчик").split(",")]
    min_salary = int(os.getenv("MIN_SALARY", "60000"))

    # ─── 1. Поиск ────────────────────────────────────────────
    print(f"\n🔍 Поиск по {len(queries)} запросам...")
    hh = HHClient(delay_sec=0.7)
    raw = hh.search_and_fetch(queries, per_page=50, max_total=80)
    print(f"\n  Всего загружено: {len(raw)}")

    # ─── 2. Жёсткий фильтр ───────────────────────────────────
    filtered = hard_filter(raw, min_salary=min_salary)

    # ─── 3. Дедупликация ─────────────────────────────────────
    db = SeenDB()
    new_vacancies = db.filter_unseen(filtered)
    print(f"\n  Новых (не виденных): {len(new_vacancies)}")

    if not new_vacancies:
        print("\n✅ Нет новых вакансий. Выхожу.")
        return

    # ─── 4. Claude-анализ ────────────────────────────────────
    print(f"\n🤖 Отправляю в Claude {len(new_vacancies)} вакансий...")
    if base_url:
        print(f"  Через прокси: {base_url}")
    analyzer = ClaudeAnalyzer(api_key=api_key, base_url=base_url)

    # Пытаемся подключить Google Sheets
    sheets = None
    if sheet_id and Path(creds_path).exists():
        try:
            from sheets import SheetsSync
            sheets = SheetsSync(creds_path=creds_path, sheet_id=sheet_id)
            print(f"  ✅ Google Sheets подключен")
        except Exception as e:
            print(f"  ⚠️  Google Sheets не подключен: {e}")
            print(f"     Буду писать в CSV.")

    rows_for_csv: list[dict] = []
    tier_counts = {"1": 0, "2": 0, "3": 0, "SKIP": 0}

    for i, (vid, vacancy) in enumerate(new_vacancies.items(), start=1):
        name = vacancy.get("name", "")[:60]
        print(f"\n  [{i}/{len(new_vacancies)}] {name}")

        try:
            result = analyzer.analyze(vacancy)
            tier = result.get("tier", "SKIP")
            letter = result.get("letter", "")
            reason = result.get("reason", "")

            tier_counts[tier] = tier_counts.get(tier, 0) + 1
            print(f"    → Tier {tier}: {reason[:80]}")

            # Записываем все кроме SKIP
            if tier != "SKIP":
                if sheets:
                    try:
                        sheets.add_vacancy(vacancy, tier=tier, letter=letter, reason=reason)
                    except Exception as e:
                        print(f"    ⚠️  Sheets error: {e}")
                        rows_for_csv.append(vacancy_to_row(vacancy, tier, letter, reason))
                else:
                    rows_for_csv.append(vacancy_to_row(vacancy, tier, letter, reason))

            # Запоминаем в БД (даже SKIP — чтоб не обрабатывать повторно)
            db.mark_seen(
                vacancy_id=vid,
                tier=tier,
                name=vacancy.get("name", ""),
                employer=(vacancy.get("employer") or {}).get("name", ""),
            )

        except Exception as e:
            print(f"    ❌ Ошибка: {e}")
            continue

    if rows_for_csv:
        write_to_csv(rows_for_csv)

    # ─── Итоги ───────────────────────────────────────────────
    print(f"\n{'='*50}")
    print(f"  Итого обработано: {len(new_vacancies)}")
    print(f"  Tier 1: {tier_counts['1']} ← откликаться обязательно")
    print(f"  Tier 2: {tier_counts['2']} ← откликаться стоит")
    print(f"  Tier 3: {tier_counts['3']} ← если время есть")
    print(f"  SKIP:   {tier_counts['SKIP']}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
