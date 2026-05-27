"""
Одноразовая OAuth-авторизация на hh.ru.

Запуск: python hh_auth.py

Выводит:
  1. Ссылку для авторизации в браузере
  2. После ввода code → access_token + refresh_token
  3. Сохраняет в .env

Документация: https://github.com/hhru/api/blob/master/docs/authorization.md
"""

import sys
sys.stdout.reconfigure(encoding="utf-8")

import os
import re
from pathlib import Path
from urllib.parse import urlencode

import httpx
from dotenv import load_dotenv


AUTHORIZE_URL = "https://hh.ru/oauth/authorize"
TOKEN_URL = "https://api.hh.ru/token"


def update_env(updates: dict[str, str]) -> None:
    """Обновить .env файл (добавить/заменить переменные)."""
    env_path = Path(".env")
    lines: list[str] = []
    keys = set(updates.keys())

    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            match = re.match(r"^([A-Z_]+)\s*=", line)
            if match and match.group(1) in keys:
                continue
            lines.append(line)

    for key, value in updates.items():
        lines.append(f"{key}={value}")

    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    load_dotenv()

    client_id = os.getenv("HH_CLIENT_ID") or input("HH_CLIENT_ID: ").strip()
    client_secret = os.getenv("HH_CLIENT_SECRET") or input("HH_CLIENT_SECRET: ").strip()
    redirect_uri = os.getenv("HH_REDIRECT_URI") or input(
        "HH_REDIRECT_URI (укажи как при регистрации, например https://example.com/): "
    ).strip()

    # Шаг 1: вывести URL авторизации
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
    }
    authorize = f"{AUTHORIZE_URL}?{urlencode(params)}"

    print("\n" + "=" * 70)
    print("Шаг 1. Открой эту ссылку в браузере, залогинься на hh.ru,")
    print("нажми «Разрешить». Тебя перебросит на redirect_uri с ?code=...")
    print("=" * 70)
    print(f"\n{authorize}\n")

    code = input("Вставь сюда code из URL после редиректа: ").strip()

    # Иногда пользователи вставляют весь URL — вытащим code
    match = re.search(r"[?&]code=([^&\s]+)", code)
    if match:
        code = match.group(1)

    # Шаг 2: обменять code на токены
    print("\nОбмениваю code на access_token...")
    response = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        },
        headers={"User-Agent": "JobSearchBot/1.0 (smyslov.20101@gmail.com)"},
        timeout=30.0,
    )

    if response.status_code != 200:
        print(f"\n❌ Ошибка ({response.status_code}): {response.text}")
        return

    tokens = response.json()
    access_token = tokens["access_token"]
    refresh_token = tokens.get("refresh_token", "")
    expires_in = tokens.get("expires_in", 0)

    print("\n✅ Получены токены:")
    print(f"   access_token:  {access_token[:30]}...")
    print(f"   refresh_token: {refresh_token[:30]}...")
    print(f"   expires_in:    {expires_in} сек ({expires_in // 86400} дней)")

    # Шаг 3: проверим что токен работает + получим resume_id
    print("\nПроверяю токен и беру список резюме...")
    r = httpx.get(
        "https://api.hh.ru/resumes/mine",
        headers={
            "Authorization": f"Bearer {access_token}",
            "User-Agent": "JobSearchBot/1.0 (smyslov.20101@gmail.com)",
        },
        timeout=30.0,
    )
    resume_id = ""
    if r.status_code == 200:
        resumes = r.json().get("items", [])
        print(f"\nНайдено резюме: {len(resumes)}")
        for i, res in enumerate(resumes, 1):
            print(f"  {i}. {res.get('title', '?')}  (id={res['id']})")
        if resumes:
            resume_id = resumes[0]["id"]
            print(f"\nАвтовыбрал первое: {resume_id}")
    else:
        print(f"⚠️  Не удалось получить резюме: {r.status_code} {r.text}")

    # Шаг 4: сохранить в .env
    update_env({
        "HH_CLIENT_ID": client_id,
        "HH_CLIENT_SECRET": client_secret,
        "HH_REDIRECT_URI": redirect_uri,
        "HH_ACCESS_TOKEN": access_token,
        "HH_REFRESH_TOKEN": refresh_token,
        "HH_RESUME_ID": resume_id,
    })
    print("\n✅ Сохранил всё в .env")


if __name__ == "__main__":
    main()
