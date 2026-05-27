"""
Пометить в SQLite вакансии, на которые уже откликнулся —
чтобы бот их больше не показывал.
"""

import sys
sys.stdout.reconfigure(encoding="utf-8")

from db import SeenDB


# Все вакансии (ID + название), на которые откликнулся
ALREADY_APPLIED = [
    ("133120704", "Манн-Рудницкая — AI Engineer"),
    ("132807106", "Qseller — Вайб-кодер на Claude Code"),
    ("132836189", "IQBIQ — AI Automation Builder"),
    ("133450899", "БестВей — AI-специалист / Prompt-инженер"),
    ("133455243", "Безлимит — AI Transformation Lead"),
    ("133486511", "Иванова — AI Product & Operations Lead"),
    ("133482220", "Galera Club — AI-инженер / Вайбкодер"),
    ("133085355", "РЕКРИО — Разработчик AI-интеграций"),
    ("133303355", "Sebekon — AI-интегратор (отказ)"),
    ("133464908", "Кириченко — AI-специалист в онлайн-школу"),
    ("132814689", "Стрит Лайт — Инженер внедрения"),
    ("133058376", "Renera Development — Специалист по внедрению AI"),
    ("133436384", "Аксенов — Специалист по нейросетям"),
]


def main():
    db = SeenDB()
    print(f"\nПомечаю {len(ALREADY_APPLIED)} вакансий как 'уже откликнулся':\n")

    for vid, title in ALREADY_APPLIED:
        was_seen = db.is_seen(vid)
        db.mark_seen(vacancy_id=vid, tier="applied", name=title)
        status = "✓ уже была" if was_seen else "+ добавил"
        print(f"  {status}  {vid}  {title}")

    print(f"\n✅ Готово. Эти вакансии больше не вылезут в поиске.")


if __name__ == "__main__":
    main()
