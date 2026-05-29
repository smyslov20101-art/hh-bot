"""
Жёсткие фильтры вакансий — отсекаем то, что точно не подходит.

Строгие критерии (все обязательны):
1. ЗП указана (salary_from is not None)
2. Удалёнка ИЛИ гибрид в Москве
3. AI-разработка / AI-интеграция / Prompt-инжиниринг / Вайб-кодинг направление
4. НЕ маркетинг, НЕ дизайн, НЕ продажи, НЕ менеджмент
"""

from typing import Any


# Чёрный список — отсекаем по названию вакансии
BLACKLIST_KEYWORDS = [
    # продажи
    "sales", "продаж", "sdr", "b2b sales",
    "менеджер по продажам", "холодные звонки", "холодный обзвон",

    # маркетинг — отдельно отметил, что НЕ берём
    "маркетолог", "маркетинг", "marketing",
    "smm-", "smm специалист", "smm менеджер",
    "перформанс", "контент-менедж", "контент менедж",

    # не разработка
    "дизайнер", "designer", "верстальщик", "html-верстальщик",
    "тестировщик", "qa-инженер", "qa engineer",
    "технический писатель", "techwriter",

    # финансы / бухгалтерия
    "accountant", "бухгалтер", "финансист", "финансовый аналитик",
    "ar specialist", "ar accountant",

    # не наш стек
    "wordpress", "битрикс", "bitrix", "1с-битрикс", "1c-bitrix",
    "laravel", "php-разработчик", "php разработчик",
    "ios", "android-разработчик", "swift", "kotlin",
    "flutter",
    "c++", "c#-разработчик", "golang", "go-разработчик",
    "frontend", "фронтенд", "fullstack senior", "fullstack lead",

    # не его уровень / направление
    "ml engineer", "machine learning engineer", "data scientist",
    "data engineer", "mlops", "devops", "sre",
    "computer vision", "cv разработчик", "cv developer", "python cv",
    "аналитик данных", "data analyst", "bi-аналитик", "bi аналитик",
    "analytics engineer",
    "head of", "руководитель отдела", "руководитель направления",
    "team lead", "tech lead",
    "проджект-менеджер", "проджект менеджер", "project manager",
    "технический проджект", "technical project",
    "категорийный менеджер", "категорийный аналитик",
    "финансовый учёт", "бухгалтер",
    "support engineer", "support lead", "инженер поддержки",
    "l2 support", "l3 support",

    # слишком сениорные
    "senior ", "senior/", "senior |", "senior(", "senior,",
    "middle+", "middle +", "lead/", "lead ",
    "сеньор ", "лид ",
    "руководитель команды",

    # квантовая аналитика и трейдинг
    "quant", "trader", "quants",
]


# Позитивный фильтр — нужно чтобы что-то из этого упоминалось
AI_DEV_KEYWORDS = [
    # Claude
    "claude code", "claude api", "claude", "anthropic",

    # AI разработка
    "ai-разработчик", "ai разработчик", "ai engineer",
    "ai-инженер", "ai инженер", "ии-разработчик",
    "вайб-кодер", "вайб кодер", "вайбкодер",
    "vibe coder", "vibe-coder", "vibe coding", "vibe-coding",
    "vibecoding",

    # Prompt engineering
    "prompt engineer", "prompt-engineer", "prompt инженер",
    "промпт-инженер", "промпт инженер",

    # AI integration / automation
    "ai-интегратор", "ai интегратор", "ai automation",
    "ai-автоматизац", "ai автоматизац", "автоматизация на ai",
    "ai-специалист", "ai специалист",
    "внедрение ai", "внедрение ии", "внедрение нейросет",
    "ai implementation", "ai integration",

    # LLM / agents
    "llm", "llm-инженер", "ai-агент", "ai agent",
    "agentic", "tool calling",
]


def extract_salary(vacancy: dict[str, Any]) -> int | None:
    """
    Минимальная зарплата из вакансии (gross → net).
    Возвращает None если не указана.
    """
    salary = vacancy.get("salary")
    if not salary:
        return None

    salary_from = salary.get("from")
    if salary_from is None:
        return None

    currency = salary.get("currency", "RUR")
    # Конвертируем в рубли по приблизительному курсу
    RATES = {"RUR": 1, "RUB": 1, "USD": 90, "EUR": 100, "KZT": 0.2}
    rate = RATES.get(currency)
    if rate is None:
        return None  # неизвестная валюта — пропускаем
    salary_from = int(salary_from * rate)

    if salary.get("gross"):
        salary_from = int(salary_from * 0.87)

    return salary_from


def is_remote_or_moscow(vacancy: dict[str, Any]) -> bool:
    """Удалёнка или Москва (включая Московскую область и упоминание удалёнки в описании)."""
    schedule = vacancy.get("schedule") or {}
    schedule_id = schedule.get("id", "")
    if schedule_id in ("remote", "flexible"):
        return True

    schedule_name = (schedule.get("name") or "").lower()
    if "удал" in schedule_name or "remote" in schedule_name:
        return True

    area = vacancy.get("area") or {}
    area_name = (area.get("name") or "").lower()
    if area.get("id") == "1" or "москва" in area_name:
        return True

    # Московская область (id=2) — рядом с Москвой
    if area.get("id") == "2":
        return True

    # Проверяем описание на упоминание удалёнки / ГПХ
    description = (vacancy.get("_raw_description") or "").lower()
    remote_hints = ["удалённо", "удаленно", "удалённая", "дистанционно",
                    "из любой точки", "remote", "гпх", "самозанят"]
    if any(hint in description for hint in remote_hints):
        return True

    return False


# Стек JS/TS без Python — нам не подходит
JS_STACK_KEYWORDS = ["react", "angular", "vue", "next.js", "nestjs", "nest.js", "typescript", "javascript"]
PYTHON_KEYWORDS = ["python", "fastapi", "django", "flask", "aiogram", "питон"]


def has_blacklist_words(vacancy: dict[str, Any]) -> bool:
    """Чёрный список в названии."""
    name = (vacancy.get("name") or "").lower()
    return any(word in name for word in BLACKLIST_KEYWORDS)


def is_js_only_stack(vacancy: dict[str, Any]) -> bool:
    """True если вакансия — JS/TS-стек без Python (нам не подходит)."""
    name = (vacancy.get("name") or "").lower()
    description = (vacancy.get("_raw_description") or "").lower()
    haystack = name + " " + description

    js_count = sum(1 for kw in JS_STACK_KEYWORDS if kw in haystack)
    has_python = any(kw in haystack for kw in PYTHON_KEYWORDS)

    # 2+ JS-технологии в тексте и ни одного упоминания Python → фильтруем
    return js_count >= 2 and not has_python


def has_ai_dev_keywords(vacancy: dict[str, Any]) -> bool:
    """В названии или описании упоминается AI-разработка/Claude/промпт."""
    name = (vacancy.get("name") or "").lower()
    description = (vacancy.get("_raw_description") or "").lower()
    haystack = name + " " + description
    return any(keyword in haystack for keyword in AI_DEV_KEYWORDS)


def hard_filter(
    vacancies: dict[str, dict[str, Any]],
    min_salary: int = 60000,
    require_salary: bool = True,
    require_ai_keywords: bool = True,
) -> dict[str, dict[str, Any]]:
    """
    Строгий фильтр.

    Args:
        vacancies: вакансии для фильтра
        min_salary: минимальная ЗП в нет рублях
        require_salary: требовать чтобы ЗП была указана
        require_ai_keywords: требовать AI-ключевики в описании

    Returns:
        Только подходящие вакансии.
    """
    filtered: dict[str, dict[str, Any]] = {}
    stats = {
        "no_salary": 0,
        "low_salary": 0,
        "wrong_location": 0,
        "blacklist": 0,
        "js_only": 0,
        "no_ai_keywords": 0,
        "passed": 0,
    }

    for vid, vacancy in vacancies.items():
        # 1. Зарплата
        salary = extract_salary(vacancy)
        if salary is None:
            if require_salary:
                stats["no_salary"] += 1
                continue
        elif salary < min_salary:
            stats["low_salary"] += 1
            continue

        # 2. Локация / формат
        if not is_remote_or_moscow(vacancy):
            stats["wrong_location"] += 1
            continue

        # 3. Чёрный список в названии
        if has_blacklist_words(vacancy):
            stats["blacklist"] += 1
            continue

        # 4. JS-стек без Python — не наша история
        if is_js_only_stack(vacancy):
            stats["js_only"] += 1
            continue

        # 5. AI ключевики в описании
        if require_ai_keywords and not has_ai_dev_keywords(vacancy):
            stats["no_ai_keywords"] += 1
            continue

        stats["passed"] += 1
        filtered[vid] = vacancy

    print(f"\n  Жёсткий фильтр:")
    print(f"    Нет ЗП: {stats['no_salary']}")
    print(f"    ЗП ниже минимума: {stats['low_salary']}")
    print(f"    Не удалёнка/не Москва: {stats['wrong_location']}")
    print(f"    Чёрный список (маркетологи, не наш стек): {stats['blacklist']}")
    print(f"    JS-стек без Python: {stats['js_only']}")
    print(f"    Нет AI-ключевиков: {stats['no_ai_keywords']}")
    print(f"    ✅ Прошли: {stats['passed']}")

    return filtered
