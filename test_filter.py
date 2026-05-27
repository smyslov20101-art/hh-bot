"""Прогнать строгий фильтр по существующему pending_vacancies.json."""

import sys
sys.stdout.reconfigure(encoding="utf-8")

import json
from pathlib import Path

from filters import hard_filter, extract_salary


def main():
    data = json.loads(Path("pending_vacancies.json").read_text(encoding="utf-8"))

    # Восстановим в формат hh_client
    vacancies = {}
    for v in data:
        vacancies[v["id"]] = {
            "name": v["name"],
            "employer": {"name": v["company"]},
            "salary": {
                "from": v.get("salary_from"),
                "to": v.get("salary_to"),
                "currency": v.get("salary_currency", "RUR"),
                "gross": v.get("salary_gross", False),
            } if v.get("salary_from") else None,
            "schedule": {"name": v.get("schedule", "")},
            "area": {"name": v.get("area", ""), "id": "1" if "Москва" in v.get("area", "") else ""},
            "alternate_url": v.get("url", ""),
            "_raw_description": v.get("description", ""),
        }

    filtered = hard_filter(vacancies, min_salary=60000)

    print(f"\n{'='*60}")
    print(f"Прошли строгий фильтр ({len(filtered)} вакансий):")
    print(f"{'='*60}")
    for vid, v in filtered.items():
        name = v["name"]
        company = v["employer"]["name"]
        salary = extract_salary(v)
        url = v["alternate_url"]
        print(f"\n• {name}")
        print(f"  {company} | от {salary} ₽")
        print(f"  {url}")


if __name__ == "__main__":
    main()
