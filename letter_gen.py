"""
Генератор уникальных сопроводительных писем под конкретную вакансию.

Анализирует название и описание вакансии → подбирает нужный акцент → строит письмо.
Без API, без платежей — чистый Python.
"""


def generate_letter(vacancy: dict) -> str:
    name = (vacancy.get("name") or "").lower()
    desc = (vacancy.get("_raw_description") or "").lower()
    text = name + " " + desc

    # ── Что ищет работодатель ─────────────────────────────────
    wants_claude    = any(k in text for k in ["claude code", "claude api", "claude", "anthropic"])
    wants_prompt    = any(k in text for k in ["промпт", "prompt", "prompting", "промптинг"])
    wants_agents    = any(k in text for k in ["агент", "agent", "multi-agent", "мультиагент"])
    wants_automation= any(k in text for k in ["автоматизац", "automation", "automate"])
    wants_llm       = any(k in text for k in ["llm", "gpt", "chatgpt", "нейросет", "language model", "openai"])
    wants_telegram  = any(k in text for k in ["telegram", "телеграм", "tg", "бот"])
    wants_n8n       = "n8n" in text
    wants_training  = any(k in text for k in ["обучен", "обучать", "обучение", "обучи", "тренинг", "наставник"])
    wants_integration = any(k in text for k in ["интеграц", "integration", "api", "апи"])
    wants_sheets    = any(k in text for k in ["google sheets", "таблиц", "excel", "spreadsheet"])
    wants_vibe      = any(k in text for k in ["вайб", "vibe", "вайбкод"])

    # ── Вступление ───────────────────────────────────────────
    if wants_claude or wants_vibe:
        intro = (
            "Работаю с Claude Code как основным инструментом ежедневно — "
            "именно это ключевое требование в вашей вакансии."
        )
    elif wants_prompt:
        intro = (
            "Занимаюсь prompt-инжинирингом и разработкой на Claude Code ежедневно — "
            "строю реальные продукты, а не просто пишу запросы."
        )
    elif wants_agents:
        intro = (
            "Строю AI-агентов на Python + Claude API — "
            "от идеи до рабочего продукта с нуля."
        )
    elif wants_automation:
        intro = (
            "Специализируюсь на автоматизации с AI: "
            "строю рабочие инструменты на Python + Claude Code, деплою на VPS."
        )
    elif wants_llm:
        intro = (
            "Работаю с LLM и AI-инструментами ежедневно: "
            "Claude Code, Claude API, REST API — использую в реальных проектах."
        )
    else:
        intro = "Работаю с Claude Code и AI-инструментами как основным стеком ежедневно."

    # ── Порядок проектов ─────────────────────────────────────
    project_idea = (
        "idea-to-code-bot — AI-агент: идея текстом → план → ZIP с рабочим кодом\n"
        "(Python, aiogram 3, Claude API, async)\n"
        "github.com/smyslov20101-art/idea-to-code-bot"
    )
    project_wife = (
        "wife-bot — Telegram-бот с LLM + автоматические уведомления\n"
        "(Python, SQLite, python-telegram-bot, VPS)\n"
        "github.com/smyslov20101-art/wife-bot"
    )
    project_hh = (
        "hh-bot — автопоиск AI-вакансий на hh.ru + Telegram-бот + Google Sheets\n"
        "(Python, httpx, aiogram 3, SQLite, gspread)\n"
        "github.com/smyslov20101-art/hh-bot"
    )

    # Выбираем какой проект ставить первым
    if wants_agents or wants_automation or wants_prompt:
        projects = [project_idea, project_wife]
    elif wants_telegram:
        projects = [project_wife, project_idea]
    elif wants_sheets or wants_integration:
        projects = [project_hh, project_idea]
    else:
        projects = [project_idea, project_wife]

    portfolio = "\n\n".join(projects)

    # ── Стек ─────────────────────────────────────────────────
    stack_parts = ["Python", "Claude Code", "Claude API", "REST API", "Git", "деплой на VPS"]
    if wants_n8n:
        stack_parts.insert(2, "n8n")
    if wants_sheets:
        stack_parts.insert(-1, "Google Sheets API")
    if wants_telegram:
        stack_parts.insert(-1, "aiogram 3")

    stack = ", ".join(stack_parts)

    # ── Заключение ───────────────────────────────────────────
    if wants_training:
        closing = (
            "Умею объяснять технологии простым языком — могу обучать сотрудников. "
            "Готов к тестовому заданию."
        )
    elif wants_vibe or wants_claude:
        closing = (
            "Вайб-кодинг — мой основной подход к разработке. "
            "Готов к тестовому заданию."
        )
    else:
        closing = "Интересна именно AI-разработка и интеграции. Готов к тестовому заданию."

    # ── Собираем письмо ──────────────────────────────────────
    letter = (
        f"Здравствуйте!\n\n"
        f"{intro}\n\n"
        f"Портфолио:\n\n"
        f"{portfolio}\n\n"
        f"Стек: {stack}.\n"
        f"{closing}\n\n"
        f"GitHub: github.com/smyslov20101-art"
    )

    return letter
