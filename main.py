import sqlite3
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = "8666912331:AAFo8_qxgVMU7d0ZtazShK9nKeFYlM-RJBw"
ADMIN_ID = 8167182526  # Твой Telegram ID
PRICE_TEXT = "150 руб."
PAYMENT_DETAILS = "Переведите на карту тбанк: 2200700586011735"
SUPPORT_USERNAME = "@belausn"
# ===============================

# Подключение к базе данных
conn = sqlite3.connect("users.db", check_same_thread=False)
cursor = conn.cursor()

# Создаём таблицу
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    purchase_count INTEGER DEFAULT 0
)
""")

# Проверяем и добавляем колонку purchase_count, если её нет
cursor.execute("PRAGMA table_info(users)")
columns = [col[1] for col in cursor.fetchall()]
if 'purchase_count' not in columns:
    cursor.execute("ALTER TABLE users ADD COLUMN purchase_count INTEGER DEFAULT 0")

conn.commit()


def get_user(user_id: int):
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    if user is None:
        cursor.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        return {"user_id": user_id, "purchase_count": 0}
    return {"user_id": user[0], "purchase_count": user[1]}


def add_purchase(user_id: int):
    cursor.execute("UPDATE users SET purchase_count = purchase_count + 1 WHERE user_id = ?", (user_id,))
    conn.commit()


main_keyboard = ReplyKeyboardMarkup([
    [KeyboardButton("🛒 Купить DNS")],
    [KeyboardButton("📊 Статистика"), KeyboardButton("🆘 Поддержка")]
], resize_keyboard=True)


# ========== /start ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    get_user(update.effective_user.id)
    await update.message.reply_text(
        "Привет! 👋\nЯ бот по продаже приватных DNS-серверов.\nВыберите действие:",
        reply_markup=main_keyboard
    )


# ========== ТЕКСТОВЫЕ СООБЩЕНИЯ ==========
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    # Если админ должен отправить файл покупателю
    if user_id == ADMIN_ID and 'admin_send_to' in context.user_data:
        await update.message.reply_text("❌ Отправьте файл как ДОКУМЕНТ, а не текстом.")
        return

    if text == "🛒 Купить DNS":
        context.user_data['waiting'] = True
        await update.message.reply_text(
            f"💳 Оплатите {PRICE_TEXT}:\n\n{PAYMENT_DETAILS}\n\n"
            f"📸 После оплаты пришлите сюда скриншот или фото чека."
        )

    elif text == "📊 Статистика":
        context.user_data['waiting'] = False
        user = get_user(user_id)
        await update.message.reply_text(f"📊 Ваша статистика:\n\n• Куплено DNS: {user['purchase_count']} шт.")

    elif text == "🆘 Поддержка":
        context.user_data['waiting'] = False
        await update.message.reply_text(f"📞 Связь с поддержкой: {SUPPORT_USERNAME}")

    elif context.user_data.get('waiting'):
        await update.message.reply_text("❌ Пожалуйста, пришлите фото или скриншот чека.")

    else:
        await update.message.reply_text("Используйте кнопки меню 👇", reply_markup=main_keyboard)


# ========== ФОТО (ЧЕКИ) ==========
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Если админ отправил фото вместо файла
    if user_id == ADMIN_ID and 'admin_send_to' in context.user_data:
        await update.message.reply_text("❌ Отправьте файл как ДОКУМЕНТ, а не как фото!")
        return

    if not context.user_data.get('waiting'):
        await update.message.reply_text("Сейчас я не ожидаю чек.\nНажмите «🛒 Купить DNS» для оформления заказа.")
        return

    context.user_data['waiting'] = False
    user = get_user(user_id)
    name = f"@{update.effective_user.username}" if update.effective_user.username else update.effective_user.first_name

    info = f"🆕 НОВЫЙ ЧЕК!\n\n👤 Пользователь: {name}\n🆔 ID: {user_id}\n📊 Покупок ранее: {user['purchase_count']}"

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Подтвердить", callback_data=f"ok_{user_id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"no_{user_id}")
        ]
    ])

    await context.bot.send_photo(ADMIN_ID, update.message.photo[-1].file_id, caption=info, reply_markup=keyboard)
    await update.message.reply_text("✅ Чек отправлен на проверку. Ожидайте.", reply_markup=main_keyboard)


# ========== ДОКУМЕНТЫ (ЧЕКИ И ФАЙЛЫ ОТ АДМИНА) ==========
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Если админ отправляет файл для покупателя
    if user_id == ADMIN_ID and 'admin_send_to' in context.user_data:
        buyer_id = context.user_data['admin_send_to']
        file_id = update.message.document.file_id
        file_name = update.message.document.file_name or "config.conf"

        try:
            await context.bot.send_document(
                chat_id=buyer_id,
                document=file_id,
                caption=f"✅ Ваша оплата подтверждена! Вот ваш файл: {file_name}",
                filename=file_name
            )
            await update.message.reply_text(f"✅ Файл отправлен покупателю (ID: {buyer_id})!")
            add_purchase(buyer_id)
            del context.user_data['admin_send_to']
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка при отправке: {e}")
        return

    # Обычный пользователь отправляет чек
    if not context.user_data.get('waiting'):
        await update.message.reply_text("Сейчас я не ожидаю чек.\nНажмите «🛒 Купить DNS» для оформления заказа.")
        return

    context.user_data['waiting'] = False
    user = get_user(user_id)
    name = f"@{update.effective_user.username}" if update.effective_user.username else update.effective_user.first_name

    info = f"🆕 НОВЫЙ ЧЕК!\n\n👤 Пользователь: {name}\n🆔 ID: {user_id}\n📊 Покупок ранее: {user['purchase_count']}"

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Подтвердить", callback_data=f"ok_{user_id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"no_{user_id}")
        ]
    ])

    await context.bot.send_document(ADMIN_ID, update.message.document.file_id, caption=info, reply_markup=keyboard)
    await update.message.reply_text("✅ Чек отправлен на проверку. Ожидайте.", reply_markup=main_keyboard)


# ========== ПОДТВЕРЖДЕНИЕ / ОТКЛОНЕНИЕ ==========
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("ok_"):
        buyer_id = int(data[3:])

        # Сохраняем ID покупателя и ждём файл от админа
        context.user_data['admin_send_to'] = buyer_id

        await query.edit_message_caption(caption=query.message.caption + "\n\n⏳ Отправьте файл для покупателя")
        await context.bot.send_message(
            ADMIN_ID,
            f"📂 Отправьте ФАЙЛ (как документ) для покупателя (ID: {buyer_id})."
        )

    elif data.startswith("no_"):
        buyer_id = int(data[3:])

        try:
            await context.bot.send_message(buyer_id, "❌ Чек отклонён. Свяжитесь с поддержкой.")
        except:
            pass

        await query.edit_message_caption(caption=query.message.caption + "\n\n❌ ОТКЛОНЕНО")


# ========== ЗАПУСК ==========
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(CallbackQueryHandler(handle_callback))

    print("✅ Бот запущен!")
    
    # Вот эту строку добавь — она сбрасывает старые обновления
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()