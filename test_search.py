"""Быстрый тест: ищет вакансии и показывает что нашёл (без Claude)."""

import sys
sys.stdout.reconfigure(encoding="utf-8")

from hh_client import HHClient
from filters import hard_filter


def main():
    hh = HHClient(delay_sec=0.7)
    queries = ["Claude Code", "AI разработчик"]
    raw = hh.search_and_fetch(queries, per_page=20, max_total=10)
    print(f"\nВсего загружено: {len(raw)}")

    filtered = hard_filter(raw, min_salary=60000)

    print(f"\n{'='*60}")
    print(f"Топ-10 после фильтра:")
    print(f"{'='*60}")
    for i, (vid, v) in enumerate(list(filtered.items())[:10], 1):
        name = v.get("name", "")
        employer = (v.get("employer") or {}).get("name", "?")
        salary = v.get("salary") or {}
        sfrom = salary.get("from") or "?"
        area = (v.get("area") or {}).get("name", "?")
        url = v.get("alternate_url", "")
        print(f"\n{i}. {name}")
        print(f"   {employer} | {area} | от {sfrom}")
        print(f"   {url}")


if __name__ == "__main__":
    main()
