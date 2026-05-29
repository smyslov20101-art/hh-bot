"""
Telegram-бот для отклика на вакансии.

Команды:
  /start — приветствие + первая вакансия
  /next — следующая вакансия
  /stats — статистика очереди
  /reload — перечитать analyzed_vacancies.json

Кнопки под карточкой:
  ✅ Откликнуться — отправить на hh.ru
  ⏭ Скип — пропустить
  ✉️ Письмо — показать сопроводительное
"""

import sys
sys.stdout.reconfigure(encoding="utf-8")

import os
import asyncio
import logging
from typing import Any

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from tg_queue import VacancyQueue
from tg_presenter import format_card, format_letter, format_stats
from hh_apply import HHApplier
from db import SeenDB
from email_sender import load_outreach_queue, save_outreach_queue, send_email


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# ─── Globals ───────────────────────────────────────────────
queue = VacancyQueue()
seen_db = SeenDB()
applier: HHApplier | None = None  # инициализируем когда есть токены hh.ru
sheets = None  # Google Sheets sync
ALLOWED_USER_ID: int | None = None  # ID владельца — только он может пользоваться


def update_sheet_status(vacancy: dict[str, Any], status: str) -> str:
    """
    Обновить статус в Google Sheets.
    Если вакансии нет в таблице — добавляет.
    Возвращает короткое сообщение для пользователя.
    """
    if sheets is None:
        return ""
    try:
        vid = vacancy["id"]
        if sheets.update_status(vid, status):
            return f"📊 Статус в таблице: «{status}»"
        # не нашли — добавим
        sheets.add_vacancy(
            vacancy,
            tier=vacancy.get("tier", "?"),
            letter=vacancy.get("letter", ""),
            status=status,
            notes=vacancy.get("reason", ""),
        )
        return f"📊 Добавил в таблицу со статусом «{status}»"
    except Exception as e:
        logger.exception("Sheets sync failed")
        return f"⚠️ Не смог обновить таблицу: {e}"


# ─── Keyboards ─────────────────────────────────────────────
def card_keyboard(vacancy_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Откликнуться", callback_data=f"apply:{vacancy_id}"),
            InlineKeyboardButton(text="⏭ Скип", callback_data=f"skip:{vacancy_id}"),
        ],
        [
            InlineKeyboardButton(text="✉️ Письмо", callback_data=f"letter:{vacancy_id}"),
        ],
    ])


def outreach_keyboard(outreach_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📧 Отправить письмо", callback_data=f"send_email:{outreach_id}"),
            InlineKeyboardButton(text="❌ Пропустить", callback_data=f"skip_email:{outreach_id}"),
        ],
    ])


# ─── Access control ────────────────────────────────────────
def is_allowed(user_id: int) -> bool:
    return ALLOWED_USER_ID is None or user_id == ALLOWED_USER_ID


# ─── Helpers ───────────────────────────────────────────────
def find_vacancy(vacancy_id: str) -> dict[str, Any] | None:
    for v in queue._vacancies:
        if v["id"] == vacancy_id:
            return v
    return None


async def send_next_card(bot: Bot, chat_id: int) -> None:
    """Отправить следующую вакансию из очереди."""
    queue.reload()
    v = queue.next_vacancy()
    if not v:
        stats = queue.stats()
        await bot.send_message(
            chat_id,
            "🎉 <b>Очередь пуста!</b>\n\n"
            f"Обработано: {stats['processed']} из {stats['total']}\n\n"
            "Запусти <code>python daily.py</code> для новой партии,\n"
            "потом напиши /reload — появятся новые карточки.",
        )
        return

    tier = v.get("tier", "?")
    reason = v.get("reason", "")
    card = format_card(v, tier=tier, reason=reason)
    await bot.send_message(
        chat_id,
        card,
        reply_markup=card_keyboard(v["id"]),
        disable_web_page_preview=True,
    )


# ─── Handlers ──────────────────────────────────────────────
async def handle_start(message: Message, bot: Bot) -> None:
    if not is_allowed(message.from_user.id):
        await message.answer("Этот бот не для тебя 🙂")
        return

    stats = queue.stats()
    await message.answer(
        "👋 Привет!\n\n"
        f"{format_stats(stats)}\n\n"
        "Команды:\n"
        "/next — следующая вакансия\n"
        "/stats — статистика\n"
        "/reload — перечитать файл с вакансиями"
    )
    if stats["pending"] > 0:
        await send_next_card(bot, message.chat.id)


async def handle_next(message: Message, bot: Bot) -> None:
    if not is_allowed(message.from_user.id):
        return
    await send_next_card(bot, message.chat.id)


async def handle_stats(message: Message) -> None:
    if not is_allowed(message.from_user.id):
        return
    queue.reload()
    await message.answer(format_stats(queue.stats()))


async def handle_reload(message: Message) -> None:
    if not is_allowed(message.from_user.id):
        return
    queue.reload()
    await message.answer("🔄 Перечитал. " + format_stats(queue.stats()).split("\n", 1)[1])


async def handle_outreach(message: Message, bot: Bot) -> None:
    """Показывает следующую компанию из очереди аутрича."""
    if not is_allowed(message.from_user.id):
        return

    outreach_queue = load_outreach_queue()
    pending = [o for o in outreach_queue if not o.get("sent")]

    if not pending:
        await message.answer(
            "📭 Очередь аутрича пуста.\n\n"
            "Запусти <code>python daily.py</code> — бот найдёт новые компании."
        )
        return

    item = pending[0]
    text = (
        f"📬 <b>Аутрич — компания найдена</b>\n\n"
        f"🏢 <b>{item['company']}</b>\n"
        f"🔗 {item['url']}\n"
        f"📧 {item['email']}\n\n"
        f"<b>Тема:</b> {item['subject']}\n\n"
        f"<b>Письмо:</b>\n<pre>{item['body'][:800]}</pre>"
    )
    await message.answer(
        text,
        reply_markup=outreach_keyboard(item["id"]),
        disable_web_page_preview=True,
    )
    await message.answer(f"Ещё в очереди: {len(pending) - 1} компаний")


async def handle_email_callback(callback: CallbackQuery, bot: Bot) -> None:
    """Обрабатывает кнопки аутрича: отправить / пропустить."""
    if not is_allowed(callback.from_user.id):
        return

    data = callback.data or ""
    action, outreach_id = data.split(":", 1)

    outreach_queue = load_outreach_queue()
    item = next((o for o in outreach_queue if o["id"] == outreach_id), None)
    if not item:
        await callback.answer("Не найдено в очереди", show_alert=True)
        return

    if action == "skip_email":
        item["sent"] = True
        item["skipped"] = True
        save_outreach_queue(outreach_queue)
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("❌ Пропустил эту компанию.")
        await callback.answer()
        return

    if action == "send_email":
        await callback.answer("Отправляю...")
        ok = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: send_email(item["email"], item["subject"], item["body"]),
        )
        if ok:
            item["sent"] = True
            save_outreach_queue(outreach_queue)
            await callback.message.edit_reply_markup(reply_markup=None)
            await callback.message.answer(
                f"✅ Письмо отправлено на {item['email']}!\n"
                f"Компания: {item['company']}"
            )
        else:
            await callback.message.answer("❌ Не удалось отправить. Проверь SMTP настройки.")
        return


async def handle_callback(callback: CallbackQuery, bot: Bot) -> None:
    if not is_allowed(callback.from_user.id):
        await callback.answer("Не для тебя", show_alert=True)
        return

    data = callback.data or ""
    if ":" not in data:
        return
    action, vacancy_id = data.split(":", 1)

    vacancy = find_vacancy(vacancy_id)
    if not vacancy:
        await callback.answer("Вакансия не найдена в очереди", show_alert=True)
        return

    if action == "letter":
        letter = vacancy.get("letter", "")
        if not letter:
            await callback.answer("Письмо не сгенерировано", show_alert=True)
            return
        await callback.message.answer(format_letter(letter))
        await callback.answer()
        return

    if action == "skip":
        queue.mark_processed(vacancy_id)
        seen_db.mark_seen(
            vacancy_id=vacancy_id,
            tier="skipped",
            name=vacancy.get("name", ""),
            employer=vacancy.get("company", ""),
        )
        sheet_msg = update_sheet_status(vacancy, "Пропущена")
        await callback.message.edit_reply_markup(reply_markup=None)
        text = "⏭ Пропустил."
        if sheet_msg:
            text += f"\n{sheet_msg}"
        await callback.message.answer(text)
        await callback.answer()
        await send_next_card(bot, callback.message.chat.id)
        return

    if action == "apply":
        letter = vacancy.get("letter", "")
        if not letter:
            await callback.answer("Письма нет — Claude Code не успел", show_alert=True)
            return

        if applier is None:
            # Ручной режим — показываем письмо, помечаем как откликнулся
            await callback.message.answer(
                "✅ Помечено как «Откликнулся».\n"
                "API закрыт — открой ссылку и вставь письмо вручную:\n\n"
                f"{format_letter(letter)}",
            )
            queue.mark_processed(vacancy_id)
            seen_db.mark_seen(
                vacancy_id=vacancy_id,
                tier="applied",
                name=vacancy.get("name", ""),
                employer=vacancy.get("company", ""),
            )
            sheet_msg = update_sheet_status(vacancy, "Откликнулся")
            if sheet_msg:
                await callback.message.answer(sheet_msg)
            await callback.message.edit_reply_markup(reply_markup=None)
            await callback.answer()
            await send_next_card(bot, callback.message.chat.id)
            return

        await callback.answer("Отправляю отклик...")
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: applier.apply(vacancy_id=vacancy_id, message=letter),
        )
        if result.get("ok"):
            queue.mark_processed(vacancy_id)
            seen_db.mark_seen(
                vacancy_id=vacancy_id,
                tier="applied",
                name=vacancy.get("name", ""),
                employer=vacancy.get("company", ""),
            )
            sheet_msg = update_sheet_status(vacancy, "Откликнулся")
            await callback.message.edit_reply_markup(reply_markup=None)
            text = f"✅ Откликнулся на «{vacancy.get('name', '')}»"
            if sheet_msg:
                text += f"\n{sheet_msg}"
            await callback.message.answer(text)
        else:
            await callback.message.answer(
                f"❌ Ошибка отклика: <code>{result.get('error')}</code>"
            )
        await send_next_card(bot, callback.message.chat.id)
        return


# ─── Bootstrap ─────────────────────────────────────────────
async def main() -> None:
    load_dotenv()

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("❌ TELEGRAM_BOT_TOKEN не задан в .env")
        return

    global ALLOWED_USER_ID
    raw_user = os.getenv("TELEGRAM_USER_ID", "").strip()
    if raw_user:
        ALLOWED_USER_ID = int(raw_user)

    # Инициализация Google Sheets, если настроены
    global sheets
    sheet_id = os.getenv("SHEET_ID", "").strip()
    creds_path = os.getenv("GOOGLE_CREDS_PATH", "./credentials.json").strip()
    if sheet_id and os.path.exists(creds_path):
        try:
            from sheets import SheetsSync
            sheets = SheetsSync(creds_path=creds_path, sheet_id=sheet_id)
            logger.info("Google Sheets: подключен")
        except Exception as e:
            logger.warning(f"Google Sheets: не подключен ({e})")
    else:
        logger.info("Google Sheets: не настроен")

    # Инициализация hh.ru API клиента, если есть токен
    hh_token = os.getenv("HH_ACCESS_TOKEN", "").strip()
    hh_resume_id = os.getenv("HH_RESUME_ID", "").strip() or None
    global applier
    if hh_token:
        applier = HHApplier(access_token=hh_token, resume_id=hh_resume_id)
        if not hh_resume_id:
            try:
                applier.resume_id = applier.auto_pick_resume()
                logger.info(f"Автовыбрал resume_id: {applier.resume_id}")
            except Exception as e:
                logger.warning(f"Не смог получить резюме: {e}")
        logger.info("hh.ru API: подключен")
    else:
        logger.info("hh.ru API: НЕ подключен — отклики будут только показываться")

    bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    dp.message.register(handle_start, Command("start"))
    dp.message.register(handle_next, Command("next"))
    dp.message.register(handle_stats, Command("stats"))
    dp.message.register(handle_reload, Command("reload"))
    dp.message.register(handle_outreach, Command("outreach"))
    dp.callback_query.register(handle_email_callback, F.data.regexp(r"^(send_email|skip_email):"))
    dp.callback_query.register(handle_callback, F.data.regexp(r"^(apply|skip|letter):"))

    me = await bot.get_me()
    logger.info(f"Бот запущен: @{me.username}")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
