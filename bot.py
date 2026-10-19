import os
import asyncio
import aiosqlite
import random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
)

# Строго путь /data — этот путь forever (volume на Fly.io)
DBPATH = "/data/birthdays.sqlite"

GREETING_TEMPLATES = [
    "Поздравляю, {user}! Пусть впереди будет только хорошее, а все мечты — сбываются.",
    "С Днём рождения, {user}! Пусть будет много радости в жизни, сил и удачи!",
    "Дорогой {user}, пусть жизнь радует улыбками, крепким здоровьем и хорошей компанией!",
    "С праздником, {user}! Пусть будет вдохновение и счастье!"
]

async def init_db():
    async with aiosqlite.connect(DBPATH) as db:
        await db.execute(
            "CREATE TABLE IF NOT EXISTS birthdays (chat_id INTEGER, user_id INTEGER, user_name TEXT, date TEXT, PRIMARY KEY(chat_id, user_id))"
        )
        await db.commit()

async def add_birthday(chat_id, user_id, user_name, date_str):
    async with aiosqlite.connect(DBPATH) as db:
        await db.execute(
            "REPLACE INTO birthdays (chat_id, user_id, user_name, date) VALUES (?, ?, ?, ?)",
            (chat_id, user_id, user_name, date_str)
        )
        await db.commit()

async def remove_birthday(chat_id, user_id):
    async with aiosqlite.connect(DBPATH) as db:
        await db.execute(
            "DELETE FROM birthdays WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id)
        )
        await db.commit()

async def get_birthday(chat_id, user_id):
    async with aiosqlite.connect(DBPATH) as db:
        async with db.execute(
            "SELECT date, user_name FROM birthdays WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id)
        ) as cursor:
            return await cursor.fetchone()

async def get_birthdays(chat_id):
    async with aiosqlite.connect(DBPATH) as db:
        async with db.execute(
            "SELECT user_name, date FROM birthdays WHERE chat_id = ? ORDER BY date",
            (chat_id,)
        ) as cursor:
            return await cursor.fetchall()

def parse_date(text):
    for fmt in ("%d.%m.%Y", "%d.%m"):
        try:
            dt = datetime.strptime(text.strip(), fmt)
            return dt.replace(year=datetime.now().year).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Бот для дней рождения.\n"
        "Добавить ДР: /add 01.01\n"
        "Удалить: /delete\n"
        "Мой ДР: /mybirthday\n"
        "Список чата: /birthdays"
    )

async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if not context.args:
        await update.message.reply_text("Формат: /add 01.01")
        return
    date_str = context.args[0]
    date_iso = parse_date(date_str)
    if not date_iso:
        await update.message.reply_text("Неверный формат даты. Пример: /add 31.12 или /add 01.02.1983")
        return
    await add_birthday(chat.id, user.id, user.full_name, date_iso)
    await update.message.reply_text("Ваш день рождения сохранён!", reply_markup=InlineKeyboardMarkup(
        [[InlineKeyboardButton("Удалить", callback_data="delme")]]
    ))

async def delete_my_birthday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    await remove_birthday(chat.id, user.id)
    await update.message.reply_text("Ваш день рождения удалён.")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat = query.message.chat
    if query.data == "delme":
        await remove_birthday(chat.id, user.id)
        await query.edit_message_text("Ваш день рождения удалён.")

async def my_birthday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    bd = await get_birthday(chat.id, user.id)
    if bd:
        date = bd[0]
        await update.message.reply_text(f"Ваш день: {datetime.strptime(date, '%Y-%m-%d').strftime('%d.%m')}")
    else:
        await update.message.reply_text("Ваш день рождения не указан. Добавь: /add 01.01")

async def list_birthdays(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    bds = await get_birthdays(chat.id)
    if not bds:
        await update.message.reply_text("Список пуст.")
        return
    text = "Дни рождения этого чата:\n"
    for user_name, date in bds:
        d = datetime.strptime(date, "%Y-%m-%d")
        text += f"• {user_name}: {d.strftime('%d.%m')}\n"
    await update.message.reply_text(text)

async def congratulate_today(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    async with aiosqlite.connect(DBPATH) as db:
        async with db.execute("SELECT DISTINCT chat_id FROM birthdays") as cur:
            chat_ids = [row[0] for row in await cur.fetchall()]
        for chat_id in chat_ids:
            async with db.execute(
                "SELECT user_name FROM birthdays WHERE chat_id=? AND strftime('%d-%m', date)=?", 
                (chat_id, now.strftime('%d-%m'))
            ) as cur:
                users = [row[0] for row in await cur.fetchall()]
            for username in users:
                msg = random.choice(GREETING_TEMPLATES).format(user=username)
                try:
                    await context.bot.send_message(chat_id, msg)
                except Exception:
                    pass

async def main():
    await init_db()
    app = ApplicationBuilder().token(os.environ["BOT_TOKEN"]).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("delete", delete_my_birthday))
    app.add_handler(CommandHandler("mybirthday", my_birthday))
    app.add_handler(CommandHandler("birthdays", list_birthdays))
    app.add_handler(CallbackQueryHandler(button_callback))
    # ежедневное поздравление (в 9:00 по времени fly.io)
    app.job_queue.run_daily(congratulate_today, time=datetime.time(9, 0, 0))

    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
