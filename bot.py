import os
import random
import asyncpg
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

GREETING_TEMPLATES = [
    "Поздравляем, {user}! Желаем радости и удачи на весь год!",
    "С Днём рождения, {user}! Пусть счастья будет как можно больше!",
    "Дорогой {user}, пусть все мечты исполняются!",
    "С праздником, {user}! Пусть всегда будет повод для улыбки и побед!"
]

DBURI = os.environ["DATABASE_URL"]
TOKEN = os.environ["BOT_TOKEN"]

async def pg_connect():
    pool = await asyncpg.create_pool(dsn=DBURI)
    async with pool.acquire() as conn:
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS birthdays (chat_id BIGINT, user_id BIGINT, user_name TEXT, date DATE, PRIMARY KEY (chat_id, user_id))"
        )
    return pool

async def add_birthday(pool, chat_id, user_id, user_name, date_):
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO birthdays VALUES ($1, $2, $3, $4) ON CONFLICT (chat_id, user_id) DO UPDATE SET user_name=$3, date=$4",
            chat_id, user_id, user_name, date_
        )

async def remove_birthday(pool, chat_id, user_id):
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM birthdays WHERE chat_id=$1 AND user_id=$2", chat_id, user_id)

async def get_birthday(pool, chat_id, user_id):
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT date, user_name FROM birthdays WHERE chat_id=$1 AND user_id=$2", chat_id, user_id)

async def get_birthdays(pool, chat_id):
    async with pool.acquire() as conn:
        return await conn.fetch("SELECT user_name, date FROM birthdays WHERE chat_id=$1 ORDER BY date", chat_id)

def parse_date(text: str):
    for fmt in ("%d.%m.%Y", "%d.%m"):
        try:
            d = datetime.strptime(text, fmt)
            return datetime(datetime.now().year, d.month, d.day).date()
        except Exception:
            continue
    return None

# Хендлеры
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Бот для дней рождения.\n"
        "Добавить ДР: /add 01.01\n"
        "Удалить: /delete\n"
        "Мой ДР: /mybirthday\n"
        "Список чата: /birthdays"
    )

async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pool = context.application.bot_data["pool"]
    user = update.effective_user
    chat = update.effective_chat
    if not context.args:
        await update.message.reply_text("Формат: /add 01.01")
        return
    date_ = parse_date(context.args[0])
    if not date_:
        await update.message.reply_text("Неверный формат даты. Введите: /add 31.12 или /add 01.02.1983")
        return
    await add_birthday(pool, chat.id, user.id, user.full_name, date_)
    await update.message.reply_text("Ваш день рождения сохранён!", reply_markup=InlineKeyboardMarkup(
        [[InlineKeyboardButton("Удалить", callback_data="delme")]]
    ))

async def delete_my_birthday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pool = context.application.bot_data["pool"]
    user = update.effective_user
    chat = update.effective_chat
    await remove_birthday(pool, chat.id, user.id)
    await update.message.reply_text("Ваш день рождения удалён.")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    pool = context.application.bot_data["pool"]
    user = query.from_user
    chat = query.message.chat
    if query.data == "delme":
        await remove_birthday(pool, chat.id, user.id)
        await query.edit_message_text("Ваш день рождения удалён.")

async def my_birthday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pool = context.application.bot_data["pool"]
    user = update.effective_user
    chat = update.effective_chat
    bd = await get_birthday(pool, chat.id, user.id)
    if bd:
        await update.message.reply_text(f"Ваш день: {bd['date'].strftime('%d.%m')}")
    else:
        await update.message.reply_text("Не найдено")

async def list_birthdays(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pool = context.application.bot_data["pool"]
    chat = update.effective_chat
    lst = await get_birthdays(pool, chat.id)
    if not lst:
        await update.message.reply_text("Список пуст.")
        return
    text = "Дни рождения:\n" + "\n".join(f"{row['user_name']}: {row['date'].strftime('%d.%m')}" for row in lst)
    await update.message.reply_text(text)

# MAIN PROGRAM
async def main():
    pool = await pg_connect()
    app = ApplicationBuilder().token(TOKEN).build()
    app.bot_data["pool"] = pool

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("delete", delete_my_birthday))
    app.add_handler(CommandHandler("mybirthday", my_birthday))
    app.add_handler(CommandHandler("birthdays", list_birthdays))
    app.add_handler(CallbackQueryHandler(button_callback))

    await app.run_polling()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
