import asyncio
import aiohttp
import logging
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# ============ НАСТРОЙКИ ============
BOT_TOKEN = os.environ.get("BOT_TOKEN")
YOUR_TELEGRAM_ID = int(os.environ.get("YOUR_TELEGRAM_ID"))
CHECK_INTERVAL = 90
API_URL = "https://job-api.ozon.ru/v2/vacancy"

FILTERS = {
    "warehouse": "",
    "process": "",
    "date_from": "",
    "time_from": "",
}
# ===================================

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
seen_ids = set()


async def fetch_vacancies():
    params = {"limit": 100, "page": 1}
    headers = {"User-Agent": "Mozilla/5.0 (compatible; OzonMonitorBot/1.0)"}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(API_URL, params=params, headers=headers, timeout=20) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("items") or data.get("vacancies") or data.get("data") or []
                else:
                    logging.warning(f"API вернул статус {resp.status}")
                    return []
        except Exception as e:
            logging.error(f"Ошибка запроса: {e}")
            return []


def matches_filter(vacancy: dict) -> bool:
    if FILTERS["warehouse"]:
        wh = FILTERS["warehouse"].lower()
        candidates = [
            str(vacancy.get("warehouse_name", "")),
            str(vacancy.get("city_title", "")),
            str(vacancy.get("location", "")),
            str(vacancy.get("address", "")),
        ]
        if not any(wh in c.lower() for c in candidates if c):
            return False

    if FILTERS["process"]:
        pr = FILTERS["process"].lower()
        candidates = [
            str(vacancy.get("process", "")),
            str(vacancy.get("position_name", "")),
            str(vacancy.get("title", "")),
            str(vacancy.get("description", "")),
        ]
        if not any(pr in c.lower() for c in candidates if c):
            return False

    if FILTERS["date_from"]:
        raw_date = vacancy.get("date") or vacancy.get("start_date") or vacancy.get("shift_date")
        if raw_date:
            try:
                vac_date = str(raw_date)[:10]
                if vac_date < FILTERS["date_from"]:
                    return False
            except Exception:
                pass

    if FILTERS["time_from"]:
        raw_time = vacancy.get("start_time") or vacancy.get("time")
        if raw_time:
            try:
                vac_time = str(raw_time)[:5]
                if vac_time < FILTERS["time_from"]:
                    return False
            except Exception:
                pass
    return True


def format_vacancy(v: dict) -> str:
    title = v.get("title") or v.get("position_name") or v.get("name") or "Без названия"
    wh = v.get("warehouse_name") or v.get("city_title") or v.get("location") or "—"
    process = v.get("process") or v.get("employment_type") or "—"
    date = v.get("date") or v.get("start_date") or v.get("shift_date") or "—"
    time = v.get("start_time") or v.get("time") or "—"
    link = v.get("url") or v.get("external_url") or ""

    text = (
        f"🔔 <b>Новая подходящая смена!</b>\n\n"
        f"<b>{title}</b>\n"
        f"🏭 Склад: {wh}\n"
        f"⚙️ Процесс: {process}\n"
        f"📅 Дата: {date}\n"
        f"⏰ Время: {time}\n"
    )
    if link:
        text += f"\n🔗 <a href='{link}'>Открыть вакансию</a>"
    return text


async def check_loop():
    await asyncio.sleep(5)
    while True:
        try:
            vacancies = await fetch_vacancies()
            logging.info(f"Получено {len(vacancies)} вакансий")
            for v in vacancies:
                vid = v.get("id") or v.get("external_id") or hash(str(v))
                if vid in seen_ids:
                    continue
                seen_ids.add(vid)
                if matches_filter(v):
                    try:
                        await bot.send_message(
                            YOUR_TELEGRAM_ID,
                            format_vacancy(v),
                            parse_mode="HTML",
                            disable_web_page_preview=False,
                        )
                        logging.info(f"Отправлена вакансия {vid}")
                    except Exception as e:
                        logging.error(f"Не удалось отправить сообщение: {e}")
        except Exception as e:
            logging.error(f"Ошибка в цикле проверки: {e}")
        await asyncio.sleep(CHECK_INTERVAL)


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if message.from_user.id != YOUR_TELEGRAM_ID:
        return
    await message.answer(
        "👋 <b>Бот-мониторинг смен Ozon Job</b>\n\n"
        "Он проверяет вакансии и присылает уведомления.\n\n"
        "<b>Команды:</b>\n"
        "/filters — показать текущие фильтры\n"
        "/set_warehouse &lt;название&gt; — фильтр по складу\n"
        "/set_process &lt;процесс&gt; — фильтр по процессу\n"
        "/set_date &lt;ГГГГ-ММ-ДД&gt; — фильтр по дате (от)\n"
        "/set_time &lt;ЧЧ:ММ&gt; — фильтр по времени (от)\n"
        "/clear — сбросить все фильтры",
        parse_mode="HTML",
    )

@dp.message(Command("filters"))
async def cmd_filters(message: types.Message):
    if message.from_user.id != YOUR_TELEGRAM_ID:
        return
    text = (
        f"<b>Текущие фильтры:</b>\n"
        f"🏭 Склад: {FILTERS['warehouse'] or '—'}\n"
        f"⚙️ Процесс: {FILTERS['process'] or '—'}\n"
        f"📅 Дата от: {FILTERS['date_from'] or '—'}\n"
        f"⏰ Время от: {FILTERS['time_from'] or '—'}"
    )
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("set_warehouse"))
async def cmd_set_warehouse(message: types.Message):
    if message.from_user.id != YOUR_TELEGRAM_ID: return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2: return await message.answer("Использование: /set_warehouse Название")
    FILTERS["warehouse"] = parts[1].strip()
    await message.answer(f"✅ Фильтр по складу: <b>{FILTERS['warehouse']}</b>", parse_mode="HTML")

@dp.message(Command("set_process"))
async def cmd_set_process(message: types.Message):
    if message.from_user.id != YOUR_TELEGRAM_ID: return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2: return await message.answer("Использование: /set_process Сортировка")
    FILTERS["process"] = parts[1].strip()
    await message.answer(f"✅ Фильтр по процессу: <b>{FILTERS['process']}</b>", parse_mode="HTML")

@dp.message(Command("set_date"))
async def cmd_set_date(message: types.Message):
    if message.from_user.id != YOUR_TELEGRAM_ID: return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2: return await message.answer("Использование: /set_date 2026-12-01")
    FILTERS["date_from"] = parts[1].strip()
    await message.answer(f"✅ Дата от: <b>{FILTERS['date_from']}</b>", parse_mode="HTML")

@dp.message(Command("set_time"))
async def cmd_set_time(message: types.Message):
    if message.from_user.id != YOUR_TELEGRAM_ID: return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2: return await message.answer("Использование: /set_time 08:00")
    FILTERS["time_from"] = parts[1].strip()
    await message.answer(f"✅ Время от: <b>{FILTERS['time_from']}</b>", parse_mode="HTML")

@dp.message(Command("clear"))
async def cmd_clear(message: types.Message):
    if message.from_user.id != YOUR_TELEGRAM_ID: return
    for k in FILTERS: FILTERS[k] = ""
    await message.answer("🧹 Все фильтры сброшены.")

async def main():
    asyncio.create_task(check_loop())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())