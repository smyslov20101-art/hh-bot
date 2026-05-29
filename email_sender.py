"""
Email аутрич — отправка писем компаниям которые ищут AI-специалиста.

Схема:
1. google_searcher.fetch_google_companies() находит компании
2. email_sender.extract_email() вытаскивает email с их сайта
3. email_sender.generate_outreach_letter() генерирует письмо
4. Карточка уходит в Telegram — ты жмёшь ✅ → письмо отправлено
"""

import os
import re
import ssl
import smtplib
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Optional
import json

import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
SMTP_HOST = os.getenv("EMAIL_SMTP_HOST", "smtp.mail.ru")
SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", "465"))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9",
}

EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
)

OUTREACH_QUEUE_FILE = Path("outreach_queue.json")


# ── Поиск email на сайте компании ────────────────────────────────────────────

def extract_email_from_site(url: str, timeout: int = 10) -> Optional[str]:
    """
    Заходит на сайт компании и ищет email.
    Проверяет главную страницу + /contacts, /about, /contact.
    """
    pages_to_check = [url, url.rstrip("/") + "/contacts",
                      url.rstrip("/") + "/contact",
                      url.rstrip("/") + "/about"]

    with httpx.Client(headers=HEADERS, timeout=timeout, follow_redirects=True) as client:
        for page_url in pages_to_check:
            try:
                resp = client.get(page_url)
                if resp.status_code != 200:
                    continue

                # Ищем email в тексте страницы
                text = resp.text
                emails = EMAIL_RE.findall(text)

                # Фильтруем системные email (noreply, support@ и т.д.)
                skip = ["noreply", "no-reply", "donotreply", "example",
                        "test@", "info@test", "@sentry", "@github",
                        ".png", ".jpg", ".gif", ".svg"]
                for email in emails:
                    email_lower = email.lower()
                    if not any(s in email_lower for s in skip):
                        return email

            except Exception:
                continue

    return None


# ── Генерация письма ──────────────────────────────────────────────────────────

def generate_outreach_letter(company_name: str, company_url: str,
                              snippet: str = "") -> tuple[str, str]:
    """
    Генерирует тему и текст письма в стиле Михаила.
    Возвращает (subject, body).
    """
    subject = "Вайб-кодер ищет команду — AI автоматизация, Python, Telegram-боты"

    body = f"""Привет!

Меня зовут Михаил, я вайбкодер — специализируюсь на AI-автоматизации и Telegram-ботах.

Наткнулся на {company_name or company_url} и подумал что могу быть полезен — если у вас есть рутинные процессы которые можно автоматизировать через AI, или нужен Telegram-бот, интеграция с внешними сервисами — это как раз моё.

Работаю через Claude Code каждый день. Результат виден быстро, без воды.

Из последнего:
— Бот который мониторит вакансии и пишет персональные письма через AI
— REST API на FastAPI + PostgreSQL + Docker
— Telegram-боты с интеграциями

Всё на GitHub: github.com/smyslov20101-art

Если есть что обсудить — напишите, с удовольствием пообщаемся 🙂

Михаил Смыслов
smyslov_20101@mail.ru
"""
    return subject, body


# ── Отправка письма ───────────────────────────────────────────────────────────

def send_email(to_email: str, subject: str, body: str) -> bool:
    """
    Отправляет письмо через SMTP Mail.ru.
    Возвращает True если успешно.
    """
    if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
        print("  ❌ EMAIL_ADDRESS или EMAIL_PASSWORD не заданы в .env")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = EMAIL_ADDRESS
        msg["To"] = to_email

        msg.attach(MIMEText(body, "plain", "utf-8"))

        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as server:
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.sendmail(EMAIL_ADDRESS, to_email, msg.as_string())

        print(f"  ✅ Письмо отправлено → {to_email}")
        return True

    except Exception as e:
        print(f"  ❌ Ошибка отправки письма на {to_email}: {e}")
        return False


# ── Очередь аутрича ───────────────────────────────────────────────────────────

def load_outreach_queue() -> list[dict]:
    if not OUTREACH_QUEUE_FILE.exists():
        return []
    try:
        return json.loads(OUTREACH_QUEUE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_outreach_queue(queue: list[dict]) -> None:
    OUTREACH_QUEUE_FILE.write_text(
        json.dumps(queue, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def add_to_outreach_queue(company: dict) -> Optional[dict]:
    """
    Принимает компанию из google_searcher.
    Ищет email, генерирует письмо, добавляет в очередь.
    Возвращает карточку или None если email не найден.
    """
    url = company.get("url", "")
    title = company.get("title", url)
    snippet = company.get("snippet", "")

    print(f"  🔍 Ищем email на {url}...")
    email = extract_email_from_site(url)

    if not email:
        print(f"  ⚠️  Email не найден на {url}")
        return None

    company_name = title.split(" — ")[0].split(" | ")[0][:50]
    subject, body = generate_outreach_letter(company_name, url, snippet)

    card = {
        "id": f"outreach_{hash(email) % 10**8}",
        "company": company_name,
        "url": url,
        "email": email,
        "subject": subject,
        "body": body,
        "sent": False,
    }

    queue = load_outreach_queue()
    # Не дублируем если уже есть
    existing_emails = {item["email"] for item in queue}
    if email in existing_emails:
        return None

    queue.append(card)
    save_outreach_queue(queue)
    print(f"  📬 Добавлено в очередь: {email} ({company_name})")
    return card


# ── Тест соединения ───────────────────────────────────────────────────────────

def test_smtp_connection() -> bool:
    """Проверяет что SMTP работает."""
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as server:
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        print("✅ SMTP соединение успешно!")
        return True
    except Exception as e:
        print(f"❌ SMTP ошибка: {e}")
        return False


if __name__ == "__main__":
    test_smtp_connection()
