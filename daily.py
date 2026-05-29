"""
Полный ежедневный цикл — одной командой.

Запуск:
    python daily.py

Что делает:
1. Ищет вакансии на hh.ru
2. Жёстко фильтрует
3. Дедуплицирует (SQLite + analyzed_vacancies.json)
4. Генерирует письма из шаблона
5. Дописывает в analyzed_vacancies.json (очередь бота)

После этого в Telegram-боте делаешь /reload — карточки готовы.
Никаких "попросить Claude разобрать" не нужно.
"""

import sys
sys.stdout.reconfigure(encoding="utf-8")

import os
import json
from pathlib import Path

from dotenv import load_dotenv

from hh_client import HHClient
from raberu import fetch_raberu_vacancies
from habr_client import fetch_habr_vacancies
from google_searcher import fetch_google_vacancies, fetch_google_companies
from email_sender import add_to_outreach_queue
from filters import hard_filter, extract_salary, has_ai_dev_keywords
from db import SeenDB
from letter_gen import generate_letter


def determine_tier(vacancy: dict) -> str:
    """
    Быстрая оценка тира на основе ключевиков + ЗП.

    Tier 1: Claude в названии + ЗП от 100к
    Tier 2: AI-направление + ЗП есть
    Tier 3: AI-ключевики где-то
    """
    name = (vacancy.get("name") or "").lower()
    description = (vacancy.get("_raw_description") or "").lower()
    salary = extract_salary(vacancy) or 0

    has_claude_in_name = any(k in name for k in ["claude code", "claude api", "claude", "вайб-кодер", "vibe coder"])

    if has_claude_in_name and salary >= 100000:
        return "1"
    if has_claude_in_name:
        return "2"
    if salary >= 100000 and has_ai_dev_keywords(vacancy):
        return "2"
    return "3"


def vacancy_to_card(vacancy: dict) -> dict:
    """Превратить вакансию hh_client в карточку для бота."""
    salary_info = vacancy.get("salary") or {}
    salary_from = salary_info.get("from")
    salary_to = salary_info.get("to")
    if salary_info.get("gross") and salary_from:
        salary_from = int(salary_from * 0.87)
    if salary_info.get("gross") and salary_to:
        salary_to = int(salary_to * 0.87)

    tier = determine_tier(vacancy)
    name = vacancy.get("name", "")
    company = (vacancy.get("employer") or {}).get("name", "")

    return {
        "id": vacancy["id"],
        "name": name,
        "company": company,
        "salary_from": salary_from,
        "salary_to": salary_to,
        "salary_currency": salary_info.get("currency", "RUR"),
        "salary_gross": False,  # уже сконвертировано выше
        "experience": (vacancy.get("experience") or {}).get("name", ""),
        "schedule": (vacancy.get("schedule") or {}).get("name", ""),
        "area": (vacancy.get("area") or {}).get("name", ""),
        "url": vacancy.get("alternate_url", ""),
        "source": vacancy.get("_source", "hh"),
        "tier": tier,
        "reason": f"Автоматическая оценка: Tier {tier}. Проверь требования глазами перед откликом.",
        "letter": generate_letter(vacancy),
    }


def load_analyzed() -> list[dict]:
    """Прочитать текущую очередь бота."""
    path = Path("analyzed_vacancies.json")
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_analyzed(data: list[dict]) -> None:
    Path("analyzed_vacancies.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main():
    load_dotenv()

    queries = [q.strip() for q in os.getenv(
        "SEARCH_QUERIES",
        "Claude Code,AI разработчик,Prompt инженер,вайб кодер,AI специалист",
    ).split(",") if q.strip()]
    min_salary = int(os.getenv("MIN_SALARY", "60000"))
    max_total = int(os.getenv("MAX_VACANCIES", "40"))

    # ─── 1. Поиск hh.ru ──────────────────────────────────────
    print(f"\n🔍 [hh.ru] Поиск по {len(queries)} запросам...")
    hh = HHClient(delay_sec=0.7)
    raw_hh = hh.search_and_fetch(queries, per_page=50, max_total=max_total)
    print(f"  hh.ru загружено: {len(raw_hh)}")

    # ─── 1b. Поиск raberu.ru ──────────────────────────────────
    print(f"\n🔍 [raberu.ru] Парсим вакансии...")
    try:
        raw_raberu = fetch_raberu_vacancies()
        print(f"  raberu.ru загружено: {len(raw_raberu)}")
    except Exception as e:
        print(f"  raberu.ru ошибка: {e} — пропускаем")
        raw_raberu = {}

    # ─── 1c. Поиск Habr Career ────────────────────────────────
    print(f"\n🔍 [habr.career] Парсим вакансии...")
    try:
        raw_habr = fetch_habr_vacancies()
        print(f"  habr career загружено: {len(raw_habr)}")
    except Exception as e:
        print(f"  habr career ошибка: {e} — пропускаем")
        raw_habr = {}

    # ─── 1d. Поиск через Google ───────────────────────────────
    print(f"\n🔍 [google] Ищем вакансии в интернете...")
    try:
        raw_google = fetch_google_vacancies()
        print(f"  google загружено: {len(raw_google)}")
    except Exception as e:
        print(f"  google ошибка: {e} — пропускаем")
        raw_google = {}

    # Объединяем все источники
    raw = {**raw_hh, **raw_raberu, **raw_habr, **raw_google}
    print(f"\n  📊 Загружено всего: {len(raw)}")
    print(f"     hh.ru: {len(raw_hh)} | raberu: {len(raw_raberu)} | habr: {len(raw_habr)} | google: {len(raw_google)}")

    # ─── 2. Строгий фильтр ───────────────────────────────────
    filtered = hard_filter(raw, min_salary=min_salary)

    # ─── 3. Дедупликация по SQLite + analyzed_vacancies.json ──
    db = SeenDB()
    existing = load_analyzed()
    existing_ids = {v["id"] for v in existing}

    new_vacancies = []
    for vid, v in filtered.items():
        if db.is_seen(vid):
            continue
        if vid in existing_ids:
            continue
        new_vacancies.append(v)
        db.mark_seen(
            vacancy_id=vid,
            name=v.get("name", ""),
            employer=(v.get("employer") or {}).get("name", ""),
        )

    print(f"\n  Уже видели: {len(filtered) - len(new_vacancies)}")
    print(f"  ✨ Новых для бота: {len(new_vacancies)}")

    if not new_vacancies:
        print("\n✅ Нет новых вакансий. Заходи позже.")
        return

    # ─── 4. Генерируем карточки ──────────────────────────────
    new_cards = [vacancy_to_card(v) for v in new_vacancies]

    # Сортируем по тиру (1 → 2 → 3)
    new_cards.sort(key=lambda c: c["tier"])

    # ─── 5. Дописываем в очередь бота ────────────────────────
    merged = new_cards + existing  # новые в начало
    save_analyzed(merged)

    print(f"\n{'='*60}")
    print(f"✅ Добавлено в analyzed_vacancies.json: {len(new_cards)}")
    print(f"   Всего в очереди: {len(merged)}")
    print(f"{'='*60}")
    print(f"\n📱 Открой бот → /reload — карточки готовы.")

    # ─── 6. Аутрич — ищем компании через Google ──────────────
    print(f"\n{'='*60}")
    print(f"📬 Ищем компании для аутрича через Google...")
    try:
        companies = fetch_google_companies()
        print(f"  Найдено компаний: {len(companies)}")
        added = 0
        for company in companies:
            card = add_to_outreach_queue(company)
            if card:
                added += 1
        if added > 0:
            print(f"  ✅ Добавлено в аутрич-очередь: {added}")
            print(f"  📱 В боте → /outreach — смотри письма и жми «Отправить»")
        else:
            print(f"  ℹ️  Новых email не найдено")
    except Exception as e:
        print(f"  Аутрич ошибка: {e} — пропускаем")
    print(f"\n📊 Распределение:")
    tier_counts: dict = {}
    for c in new_cards:
        tier_counts[c["tier"]] = tier_counts.get(c["tier"], 0) + 1
    for t in sorted(tier_counts.keys()):
        print(f"   Tier {t}: {tier_counts[t]}")


if __name__ == "__main__":
    main()
