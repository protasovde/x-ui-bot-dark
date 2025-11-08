"""
Telegram бот для выдачи VPN конфигураций из x-ui
"""
import logging
import asyncio
import os
from datetime import datetime, timedelta
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message, Chat, User, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
from xui_client import XUIClient
from database import Database
from config import (
    TELEGRAM_BOT_TOKEN, 
    ALLOWED_USERNAMES, 
    ADMIN_USERNAMES,
    REMINDER_CHECK_INTERVAL,
    REMINDER_DAYS
)

# Импортируем новые переменные с дефолтными значениями для обратной совместимости
try:
    from config import DEFAULT_INBOUND_ID
    # Если DEFAULT_INBOUND_ID None или не установлен, используем дефолт
    if DEFAULT_INBOUND_ID is None:
        DEFAULT_INBOUND_ID = 7
except ImportError:
    DEFAULT_INBOUND_ID = 7  # Дефолтное значение: inbound ID 7

try:
    from config import CONFIG_EXPIRY_DAYS
    # Если CONFIG_EXPIRY_DAYS не установлен, используем дефолт
    if CONFIG_EXPIRY_DAYS is None:
        CONFIG_EXPIRY_DAYS = 31
except ImportError:
    CONFIG_EXPIRY_DAYS = 31  # Дефолтное значение: 31 день

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация клиента x-ui и базы данных
xui_client = XUIClient()
db = Database()


def check_access(username: Optional[str]) -> bool:
    """Проверка доступа пользователя по username"""
    if not ALLOWED_USERNAMES:
        return True  # Открытый доступ
    if not username:
        return False  # Нет username - нет доступа
    # Нормализуем username (убираем @ если есть)
    username_normalized = username.lstrip('@').lower()
    return username_normalized in [u.lstrip('@').lower() for u in ALLOWED_USERNAMES]


def is_admin(username: Optional[str]) -> bool:
    """Проверка, является ли пользователь администратором по username"""
    if not username:
        return False
    # Нормализуем username (убираем @ если есть)
    username_normalized = username.lstrip('@').lower()
    
    # Проверяем в списке администраторов из config
    admin_list = [u.lstrip('@').lower() for u in ADMIN_USERNAMES]
    if username_normalized in admin_list:
        return True
    
    # Также проверяем в базе данных (для обратной совместимости)
    # Но это не используется, так как проверка идет только по username из config
    return False


async def save_bot_message_id(context: ContextTypes.DEFAULT_TYPE, user_id: int, message_id: int):
    """Сохранить message_id сообщения бота для возможного удаления"""
    try:
        if not hasattr(context, 'bot_data'):
            context.bot_data = {}
        bot_messages_key = f"bot_messages_{user_id}"
        if bot_messages_key not in context.bot_data:
            context.bot_data[bot_messages_key] = []
        context.bot_data[bot_messages_key].append(message_id)
        # Ограничиваем список последними 50 сообщениями, чтобы не накапливать слишком много
        if len(context.bot_data[bot_messages_key]) > 50:
            context.bot_data[bot_messages_key] = context.bot_data[bot_messages_key][-50:]
    except Exception as e:
        logger.debug(f"Не удалось сохранить message_id сообщения: {e}")


async def send_app_links(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int = None):
    """Отправить ссылки на приложения для iOS и Android"""
    app_links_text = """
📱 Приложения для подключения:

🍎 iOS (App Store):
• v2rayNG: https://apps.apple.com/app/v2rayng/id6446814690
• Shadowrocket: https://apps.apple.com/app/shadowrocket/id932747118

🤖 Android (Google Play):
• v2RayTun: https://play.google.com/store/apps/details?id=com.v2raytun.android
• v2rayNG (GitHub): https://github.com/2dust/v2rayNG/releases

💡 Рекомендуется использовать v2RayTun для Android и v2rayNG для iOS.
"""
    
    try:
        msg = await context.bot.send_message(
            chat_id=chat_id,
            text=app_links_text,
            parse_mode='HTML',
            disable_web_page_preview=False
        )
        # Сохраняем message_id для возможного удаления
        if user_id:
            await save_bot_message_id(context, user_id, msg.message_id)
    except Exception as e:
        logger.error(f"Ошибка при отправке ссылок на приложения: {e}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user_id = update.effective_user.id
    username = update.effective_user.username
    full_name = update.effective_user.full_name
    
    # Регистрируем пользователя в базе при первом запуске
    user = db.get_user(user_id)
    if not user:
        db.add_user(user_id, username, full_name, 1)  # Лимит по умолчанию: 1
        user = db.get_user(user_id)
    
    if not check_access(username):
        await update.message.reply_text(
            "❌ У вас нет доступа к этому боту.\n"
            "💡 Убедитесь, что у вас установлен username в настройках Telegram."
        )
        return
    
    # Проверяем наличие username
    if not username:
        welcome_text = """
❌ Для работы с ботом необходимо установить username в настройках Telegram.

📝 Подробная инструкция по добавлению username:

1️⃣ Откройте настройки Telegram:
   • Нажмите на иконку меню (три полоски) в левом верхнем углу
   • Или нажмите на ваше имя/аватар вверху экрана

2️⃣ Найдите раздел "Имя пользователя" (Username):
   • В настройках прокрутите вниз до раздела "Имя пользователя"
   • Или используйте поиск в настройках

3️⃣ Установите username:
   • Нажмите на "Имя пользователя"
   • Введите желаемый username (например: @myusername)
   • Нажмите "Сохранить" или галочку ✓

4️⃣ Вернитесь в бота:
   • Вернитесь в чат с ботом
   • Отправьте команду /start

💡 Username нужен для создания и получения конфигураций.
💡 Username должен быть уникальным и может содержать только буквы, цифры и подчеркивания.
"""
        # Добавляем Reply кнопку "Меню"
        reply_keyboard = [
            [KeyboardButton("Меню")]
        ]
        reply_markup = ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)
        await update.message.reply_text(welcome_text, reply_markup=reply_markup)
        return
    
    welcome_text = """
🤖 Привет! Я бот для получения VPN конфигураций.

📋 Что нужно сделать, чтобы начать:
1. ✅ У вас установлен username: @{username}
2. 📱 Используйте кнопки ниже для работы с ботом

📋 Доступные команды:
• ✨ Создать конфиг - создать новый конфиг на 31 день
• 📥 Скачать конфиг - получить ваш конфиг
• 📊 Информация - объем данных и срок действия
• 📹 Инструкция - видео инструкция по использованию
• 💬 Связь с администратором - связаться с админом

💡 Используйте кнопки ниже или команду /start для открытия меню.
""".format(username=username)
    
    # Добавляем Inline кнопки для быстрого доступа
    # 1 строка: Создать конфиг и Скачать конфиг
    # 2 строка: Информация и Инструкция
    # 3 строка: Связь с администратором
    inline_keyboard = [
        [
            InlineKeyboardButton("✨ Создать конфиг", callback_data="create_config"),
            InlineKeyboardButton("📥 Скачать конфиг", callback_data="download_config")
        ],
        [
            InlineKeyboardButton("📊 Информация", callback_data="config_info"),
            InlineKeyboardButton("📹 Инструкция", callback_data="instruction")
        ],
        [
            InlineKeyboardButton("💬 Связь с администратором", callback_data="contact_admin")
        ]
    ]
    inline_markup = InlineKeyboardMarkup(inline_keyboard)
    
    # Добавляем Reply кнопку "Меню"
    reply_keyboard = [
        [KeyboardButton("Меню")]
    ]
    reply_markup = ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)
    
    # Удаляем само сообщение с командой /start сразу
    try:
        await update.message.delete()
    except Exception as e:
        logger.debug(f"Не удалось удалить сообщение с командой /start: {e}")
    
    # Пытаемся удалить все предыдущие сообщения бота
    try:
        if hasattr(context, 'bot_data') and context.bot_data:
            # Получаем список всех сохраненных message_id сообщений бота для этого пользователя
            bot_messages_key = f"bot_messages_{user_id}"
            bot_messages = context.bot_data.get(bot_messages_key, [])
            
            # Удаляем все сохраненные сообщения бота
            for msg_id in bot_messages:
                try:
                    await context.bot.delete_message(
                        chat_id=update.message.chat_id,
                        message_id=msg_id
                    )
                except Exception as e:
                    logger.debug(f"Не удалось удалить сообщение {msg_id}: {e}")
            
            # Очищаем список сообщений
            context.bot_data[bot_messages_key] = []
    except Exception as e:
        logger.debug(f"Ошибка при попытке удалить предыдущие сообщения: {e}")
    
    # Отправляем новое сообщение с меню
    menu_msg = await context.bot.send_message(
        chat_id=update.message.chat_id,
        text=welcome_text,
        reply_markup=reply_markup
    )
    inline_msg = await context.bot.send_message(
        chat_id=update.message.chat_id,
        text="💡 Используйте кнопки выше для работы с ботом.",
        reply_markup=inline_markup
    )
    
    # Сохраняем message_id новых сообщений для возможного удаления
    await save_bot_message_id(context, user_id, menu_msg.message_id)
    await save_bot_message_id(context, user_id, inline_msg.message_id)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    username = update.effective_user.username
    
    if not check_access(username):
        await update.message.reply_text("❌ У вас нет доступа к этому боту.")
        return
    
    help_text = """
📖 Справка по использованию бота:

/create [inbound_id] - Создать нового клиента
Пример: /create или /create 5
💡 По умолчанию каждый пользователь может создать 1 клиента

/list - Показать список всех доступных inbounds с их ID

/clients <inbound_id> - Показать список всех клиентов для указанного inbound
Пример: /clients 1

/get <email> - Получить конфигурацию клиента по email
Пример: /get user@example.com

/myinfo - Показать информацию о вашем аккаунте

💡 Конфигурация будет отправлена в виде ссылки, которую можно импортировать в VPN клиент.
"""
    await update.message.reply_text(help_text)


async def myinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать информацию о пользователе"""
    user_id = update.effective_user.id
    username = update.effective_user.username
    
    if not check_access(username):
        await update.message.reply_text("❌ У вас нет доступа к этому боту.")
        return
    
    user = db.get_user(user_id)
    if not user:
        await update.message.reply_text("❌ Пользователь не найден в базе.")
        return
    
    limit = user.get("config_limit", 0)
    created = user.get("configs_created", 0)
    remaining = max(0, limit - created)
    
    info_text = f"""
📊 Информация о вашем аккаунте:

🆔 ID: {user_id}
👤 Имя: {user.get('full_name', 'N/A')}
📝 Username: @{user.get('username', 'N/A')}

📦 Лимит конфигов: {limit}
✅ Использовано: {created}
⏳ Осталось: {remaining}

💡 Обратитесь к администратору для увеличения лимита.
"""
    
    await update.message.reply_text(info_text)


# ========== АДМИНСКИЕ КОМАНДЫ ==========

async def admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Справка по админским командам"""
    username = update.effective_user.username
    
    if not is_admin(username):
        await update.message.reply_text("❌ У вас нет прав администратора.")
        return
    
    help_text = """
🔧 Админские команды:

/adduser <username> <limit> - Добавить пользователя по username и установить лимит
Пример: /adduser @username 5

/setlimit <username> <limit> - Изменить лимит конфигов для пользователя
Пример: /setlimit @username 10

/extend <username> [days] - Продлить срок действия конфига на указанное количество дней
Пример: /extend @username 31
💡 Если days не указан, по умолчанию продлевается на 31 день

/deleteuser <username> - Удалить все данные пользователя из базы данных
Пример: /deleteuser @username
⚠️ ВНИМАНИЕ: Удаляет все данные пользователя (конфиги, напоминания, пользователя)

/users - Показать список всех пользователей

/sync_reminders - Синхронизировать напоминания из x-ui

/cleardb - Очистить всю базу данных (удалить все данные)

💡 Username можно указывать с @ или без него.
"""
    await update.message.reply_text(help_text)


async def add_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавить пользователя (админ)"""
    username = update.effective_user.username
    
    if not is_admin(username):
        await update.message.reply_text("❌ У вас нет прав администратора.")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "❌ Использование: /adduser <username> <limit>\n"
            "Пример: /adduser @username 5"
        )
        return
    
    try:
        username = context.args[0].lstrip('@')
        limit = int(context.args[1])
        
        # Получаем информацию о пользователе из Telegram
        # Для этого нужно найти пользователя по username
        # В Telegram Bot API нет прямого способа получить user_id по username
        # Поэтому нужно попросить пользователя написать боту
        
        await update.message.reply_text(
            f"⏳ Ищу пользователя @{username}...\n\n"
            "💡 Если пользователь не найден, попросите его написать боту /start, "
            "а затем используйте команду /setlimit для установки лимита."
        )
        
        # Попробуем найти пользователя в базе по username
        user = db.get_user_by_username(username)
        if user:
            db.set_config_limit(user['user_id'], limit)
            await update.message.reply_text(
                f"✅ Пользователь @{username} найден. Лимит установлен: {limit}"
            )
        else:
            await update.message.reply_text(
                f"⚠️ Пользователь @{username} не найден в базе.\n"
                "Попросите его написать боту /start, затем используйте /setlimit."
            )
            
    except ValueError:
        await update.message.reply_text("❌ Лимит должен быть числом.")
    except Exception as e:
        logger.error(f"Ошибка в add_user_command: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")


async def set_limit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Установить лимит конфигов (админ)"""
    username = update.effective_user.username
    
    if not is_admin(username):
        await update.message.reply_text("❌ У вас нет прав администратора.")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "❌ Использование: /setlimit <username> <limit>\n"
            "Пример: /setlimit @username 10"
        )
        return
    
    try:
        username = context.args[0].lstrip('@')
        limit = int(context.args[1])
        
        user = db.get_user_by_username(username)
        if not user:
            await update.message.reply_text(
                f"❌ Пользователь @{username} не найден в базе.\n"
                "Попросите его написать боту /start."
            )
            return
        
        db.set_config_limit(user['user_id'], limit)
        await update.message.reply_text(
            f"✅ Лимит для @{username} установлен: {limit} конфигов"
        )
        
        # Уведомляем пользователя
        try:
            await context.bot.send_message(
                chat_id=user['user_id'],
                text=f"📢 Уведомление:\nВаш лимит конфигов изменен на {limit}."
            )
        except:
            pass  # Пользователь может заблокировать бота
            
    except ValueError:
        await update.message.reply_text("❌ Лимит должен быть числом.")
    except Exception as e:
        logger.error(f"Ошибка в set_limit_command: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")


async def list_users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать список всех пользователей (админ)"""
    username = update.effective_user.username
    
    if not is_admin(username):
        await update.message.reply_text("❌ У вас нет прав администратора.")
        return
    
    users = db.get_all_users()
    
    if not users:
        await update.message.reply_text("📭 В базе нет пользователей.")
        return
    
    text = "📋 Список пользователей:\n\n"
    
    for user in users:
        user_id_db = user.get("user_id")
        username = user.get("username", "N/A")
        full_name = user.get("full_name", "N/A")
        limit = user.get("config_limit", 0)
        created = user.get("configs_created", 0)
        is_admin_user = "🔧" if user.get("is_admin") else ""
        
        text += f"{is_admin_user} @{username} ({full_name})\n"
        text += f"   ID: {user_id_db}\n"
        text += f"   Лимит: {limit} | Использовано: {created}\n"
        text += "─" * 30 + "\n\n"
    
    await update.message.reply_text(text)


async def clear_database_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Очистить всю базу данных (админ)"""
    username = update.effective_user.username
    
    if not is_admin(username):
        await update.message.reply_text("❌ У вас нет прав администратора.")
        return
    
    try:
        # Получаем соединение с базой данных
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Получаем список всех таблиц
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        
        if not tables:
            await update.message.reply_text("ℹ️ База данных пуста.")
            conn.close()
            return
        
        # Отключаем проверку внешних ключей для быстрой очистки
        cursor.execute("PRAGMA foreign_keys = OFF;")
        
        # Очищаем каждую таблицу
        cleared_tables = []
        for table in tables:
            table_name = table[0]
            cursor.execute(f"DELETE FROM {table_name};")
            cursor.execute(f"DELETE FROM sqlite_sequence WHERE name='{table_name}';")  # Сбрасываем автоинкремент
            cleared_tables.append(table_name)
        
        # Включаем обратно проверку внешних ключей
        cursor.execute("PRAGMA foreign_keys = ON;")
        
        conn.commit()
        conn.close()
        
        result_text = f"✅ База данных успешно очищена!\n\n"
        result_text += f"📋 Очищено таблиц: {len(cleared_tables)}\n"
        for table_name in cleared_tables:
            result_text += f"• {table_name}\n"
        
        await update.message.reply_text(result_text)
        
    except Exception as e:
        logger.error(f"Ошибка при очистке базы данных: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Ошибка при очистке базы данных: {str(e)}")


async def delete_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удалить все данные пользователя из базы (админ)"""
    username = update.effective_user.username
    
    if not is_admin(username):
        await update.message.reply_text("❌ У вас нет прав администратора.")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text(
            "❌ Использование: /deleteuser <username>\n"
            "Пример: /deleteuser @username\n"
            "💡 Username можно указывать с @ или без него.\n"
            "⚠️ ВНИМАНИЕ: Эта команда удалит ВСЕ данные пользователя из базы данных!"
        )
        return
    
    try:
        target_username = context.args[0]
        
        # Удаляем данные пользователя
        success, message, user_id = db.delete_user_data(target_username)
        
        if success:
            await update.message.reply_text(message)
        else:
            await update.message.reply_text(f"❌ {message}")
            
    except Exception as e:
        logger.error(f"Ошибка в delete_user_command: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")


async def extend_config_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Продлить срок действия конфига на +31 день (админ)"""
    username = update.effective_user.username
    
    if not is_admin(username):
        await update.message.reply_text("❌ У вас нет прав администратора.")
        return
    
    if len(context.args) < 1:
        await update.message.reply_text(
            "❌ Использование: /extend <username или email> [days]\n"
            "Пример: /extend @username 31\n"
            "Пример: /extend username_1 31\n"
            "💡 Если days не указан, по умолчанию продлевается на 31 день.\n"
            "💡 Можно указать username или email с номером (например, username_1)."
        )
        return
    
    try:
        target_input = context.args[0].lstrip('@')
        add_days = int(context.args[1]) if len(context.args) > 1 else 31
        
        inbound_id = DEFAULT_INBOUND_ID
        
        # Определяем, что передано: username или email с номером
        # Если содержит _ и число в конце (например, username_1), это email
        import re
        email_pattern = re.compile(r'^(.+)_(\d+)$')
        match = email_pattern.match(target_input)
        
        email = None
        if match:
            # Это email с номером (например, iccceee_boy_1)
            email = target_input
            logger.info(f"Используется email с номером: {email}")
        else:
            # Это username, нужно найти конфиги пользователя
            user_configs = xui_client.get_user_configs(inbound_id, target_input)
            if not user_configs:
                await update.message.reply_text(
                    f"❌ Конфиги для @{target_input} не найдены в x-ui.\n"
                    "💡 Пользователь должен сначала создать конфиг через бота.\n"
                    "💡 Или укажите email с номером (например, username_1)."
                )
                return
            
            # Используем последний конфиг (с максимальным номером)
            last_config = user_configs[-1]
            email = last_config["email"]
            logger.info(f"Найден последний конфиг для {target_input}: {email}")
        
        # Проверяем, существует ли конфиг для этого email
        clients = xui_client.get_inbound_clients(inbound_id)
        client = next((c for c in clients if c.get("email") == email), None)
        
        if not client:
            await update.message.reply_text(
                f"❌ Конфиг для {email} не найден в x-ui.\n"
                "💡 Проверьте правильность email."
            )
            return
        
        # Получаем текущий срок действия
        current_expiry = client.get("expireTime", 0)
        from datetime import datetime
        if current_expiry > 0:
            current_expiry_date = datetime.fromtimestamp(current_expiry / 1000)
            current_expiry_str = current_expiry_date.strftime("%Y-%m-%d %H:%M")
        else:
            current_expiry_str = "Без ограничений"
        
        # Продлеваем конфиг
        await update.message.reply_text(f"⏳ Продлеваю конфиг для {email} на {add_days} дней...")
        
        success = xui_client.update_client_expiry(inbound_id, email, add_days)
        
        if success:
            # Получаем новый срок действия
            clients = xui_client.get_inbound_clients(inbound_id)
            client = next((c for c in clients if c.get("email") == email), None)
            
            if client:
                new_expiry = client.get("expireTime", 0)
                if new_expiry > 0:
                    new_expiry_date = datetime.fromtimestamp(new_expiry / 1000)
                    new_expiry_str = new_expiry_date.strftime("%Y-%m-%d %H:%M")
                else:
                    new_expiry_str = "Без ограничений"
            else:
                new_expiry_str = "Не удалось получить"
            
            result_text = f"""
✅ Конфиг для {email} успешно продлен!

📅 Текущий срок действия: {current_expiry_str}
📅 Новый срок действия: {new_expiry_str}
➕ Продлено на: {add_days} дней

💡 Конфиг не был удален и не требует перевыпуска.
"""
            await update.message.reply_text(result_text)
        else:
            await update.message.reply_text(
                f"❌ Не удалось продлить конфиг для {email}.\n"
                "💡 Проверьте логи для получения подробной информации."
            )
            
    except ValueError:
        await update.message.reply_text("❌ Количество дней должно быть числом.")
    except Exception as e:
        logger.error(f"Ошибка в extend_config_command: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")


async def sync_reminders_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Синхронизировать напоминания из x-ui (админ)"""
    username = update.effective_user.username
    
    if not is_admin(username):
        await update.message.reply_text("❌ У вас нет прав администратора.")
        return
    
    try:
        await update.message.reply_text("⏳ Синхронизирую напоминания из x-ui...")
        
        users = db.get_all_users()
        synced_count = 0
        
        for user in users:
            user_id_db = user.get("user_id")
            db.sync_reminders_from_xui(xui_client, user_id_db)
            synced_count += 1
        
        await update.message.reply_text(
            f"✅ Синхронизация завершена. Обработано пользователей: {synced_count}"
        )
        
    except Exception as e:
        logger.error(f"Ошибка в sync_reminders_command: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")


# ========== ОСНОВНЫЕ КОМАНДЫ ==========

async def list_inbounds(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /list - показать список inbounds"""
    username = update.effective_user.username
    
    if not check_access(username):
        await update.message.reply_text("❌ У вас нет доступа к этому боту.")
        return
    
    try:
        loading_msg = await update.message.reply_text("⏳ Получаю список серверов...")
        inbounds = xui_client.get_inbounds()
        
        if not inbounds:
            await loading_msg.edit_text("❌ Не удалось получить список inbounds или список пуст.")
            return
        
        text = "📋 Список доступных inbounds:\n\n"
        keyboard = []
        
        for inbound in inbounds:
            inbound_id = inbound.get("id")
            remark = inbound.get("remark", f"Inbound {inbound_id}")
            protocol = inbound.get("protocol", "unknown")
            port = inbound.get("port", "N/A")
            traffic = inbound.get("up", 0) + inbound.get("down", 0)
            
            text += f"🆔 ID: {inbound_id}\n"
            text += f"📝 Название: {remark}\n"
            text += f"🔌 Протокол: {protocol.upper()}\n"
            text += f"🚪 Порт: {port}\n"
            text += f"📊 Трафик: {traffic / (1024**3):.2f} GB\n"
            text += "─" * 20 + "\n\n"
        
        # Добавляем кнопки для каждого inbound в одну строку (2 кнопки в ряд)
        buttons_per_row = 2
        for i, inbound in enumerate(inbounds):
            inbound_id = inbound.get("id")
            remark = inbound.get("remark", f"Inbound {inbound_id}")
            
            if i % buttons_per_row == 0:
                # Начинаем новую строку
                keyboard.append([])
            
            # Добавляем кнопку для получения клиентов
            keyboard[-1].append(
                InlineKeyboardButton(
                    f"📋 {remark[:15]}",
                    callback_data=f"clients_{inbound_id}"
                )
            )
        
        if not keyboard or not any(keyboard):
            await loading_msg.edit_text("❌ Не удалось создать кнопки.")
            return
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        total_buttons = sum(len(row) for row in keyboard)
        logger.info(f"Отправляю список inbounds с {len(keyboard)} строками кнопок, всего {total_buttons} кнопок")
        
        try:
            await loading_msg.edit_text(text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения с кнопками: {e}")
            await loading_msg.edit_text(f"❌ Ошибка при отправке кнопок: {str(e)}")
        
    except Exception as e:
        logger.error(f"Ошибка в list_inbounds: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")


async def list_clients(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /clients"""
    username = update.effective_user.username
    
    if not check_access(username):
        await update.message.reply_text("❌ У вас нет доступа к этому боту.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "❌ Укажите ID inbound.\nПример: /clients 1"
        )
        return
    
    try:
        inbound_id = int(context.args[0])
        await update.message.reply_text(f"⏳ Получаю список клиентов для inbound {inbound_id}...")
        
        clients = xui_client.get_inbound_clients(inbound_id)
        
        if not clients:
            await update.message.reply_text(f"❌ Не найдено клиентов для inbound {inbound_id}.")
            return
        
        text = f"📋 Клиенты для inbound {inbound_id}:\n\n"
        keyboard = []
        
        for client in clients:
            email = client.get("email", "N/A")
            total = client.get("total", 0)
            expire = client.get("expireTime", 0)
            
            text += f"📧 Email: {email}\n"
            text += f"📊 Трафик: {total / (1024**3):.2f} GB\n"
            if expire > 0:
                expire_date = datetime.fromtimestamp(expire / 1000)
                text += f"⏰ Истекает: {expire_date.strftime('%Y-%m-%d %H:%M')}\n"
            text += "─" * 20 + "\n\n"
            
            # Добавляем кнопку для получения конфигурации
            keyboard.append([
                InlineKeyboardButton(
                    f"📥 Получить конфиг ({email})",
                    callback_data=f"get_{inbound_id}_{email}"
                )
            ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(text, reply_markup=reply_markup)
        
    except ValueError:
        await update.message.reply_text("❌ ID inbound должен быть числом.")
    except Exception as e:
        logger.error(f"Ошибка в list_clients: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")


async def get_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /get"""
    user_id = update.effective_user.id
    username = update.effective_user.username
    
    if not check_access(username):
        await update.message.reply_text("❌ У вас нет доступа к этому боту.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "❌ Укажите email клиента.\nПример: /get user@example.com"
        )
        return
    
    # Проверяем лимит
    can_create, message = db.can_create_config(user_id)
    if not can_create:
        await update.message.reply_text(f"❌ {message}")
        return
    
    email = " ".join(context.args)
    
    try:
        await update.message.reply_text(f"⏳ Получаю конфигурацию для {email}...")
        
        # Находим inbound для этого email
        inbounds = xui_client.get_inbounds()
        target_inbound = None
        target_inbound_id = None
        
        for inbound in inbounds:
            inbound_id = inbound.get("id")
            clients = xui_client.get_inbound_clients(inbound_id)
            if any(c.get("email") == email for c in clients):
                target_inbound = inbound
                target_inbound_id = inbound_id
                break
        
        if not target_inbound:
            await update.message.reply_text(
                f"❌ Не удалось найти конфигурацию для {email}."
            )
            return
        
        protocol = target_inbound.get("protocol", "vless").lower()
        config = xui_client.get_client_config(target_inbound_id, email, protocol)
        
        if not config:
            await update.message.reply_text(
                f"❌ Не удалось получить конфигурацию для {email}."
            )
            return
        
        # Записываем выдачу конфига
        db.record_issued_config(user_id, email, target_inbound_id)
        
        # Получаем информацию о клиенте для напоминаний
        clients = xui_client.get_inbound_clients(target_inbound_id)
        client = next((c for c in clients if c.get("email") == email), None)
        
        if client and client.get("expireTime", 0) > 0:
            db.add_reminder(user_id, email, target_inbound_id, client.get("expireTime"))
        
        # Не используем Markdown для конфигурации, так как она содержит специальные символы
        await update.message.reply_text(
            f"✅ Конфигурация для {email}:\n\n"
            f"{config}"
        )
        
        # Также отправляем как обычный текст для удобства копирования
        await update.message.reply_text(config)
        
        # Обновляем информацию о лимите
        user = db.get_user(user_id)
        if user:
            limit = user.get("config_limit", 0)
            created = user.get("configs_created", 0)
            remaining = max(0, limit - created)
            await update.message.reply_text(
                f"📊 Осталось конфигов: {remaining}/{limit}"
            )
        
    except Exception as e:
        logger.error(f"Ошибка в get_config: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")


async def create_client(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /create - создать нового клиента"""
    user_id = update.effective_user.id
    username = update.effective_user.username
    
    if not check_access(username):
        await update.message.reply_text("❌ У вас нет доступа к этому боту.")
        return
    
    # Проверяем лимит
    can_create, message = db.can_create_config(user_id)
    if not can_create:
        await update.message.reply_text(f"❌ {message}")
        return
    
    # Если указан inbound_id в аргументах, создаем сразу
    if context.args:
        try:
            inbound_id = int(context.args[0]) if context.args else DEFAULT_INBOUND_ID
            await _create_client_for_inbound(update, context, user_id, username, inbound_id)
            return
        except ValueError:
            await update.message.reply_text("❌ ID inbound должен быть числом.")
            return
    
    # Иначе показываем список inbounds с кнопками
    try:
        loading_msg = await update.message.reply_text("⏳ Получаю список серверов...")
        inbounds = xui_client.get_inbounds()
        
        logger.info(f"Получено inbounds: {len(inbounds) if inbounds else 0}")
        
        if not inbounds:
            await loading_msg.edit_text(
                "❌ Не удалось получить список inbounds или список пуст.\n"
                "Проверьте подключение к x-ui панели."
            )
            return
        
        text = "📋 Выберите сервер для создания клиента:\n\n"
        keyboard = []
        
        for inbound in inbounds:
            inbound_id = inbound.get("id")
            remark = inbound.get("remark", f"Inbound {inbound_id}")
            protocol = inbound.get("protocol", "unknown")
            port = inbound.get("port", "N/A")
            
            text += f"🆔 ID: {inbound_id}\n"
            text += f"📝 Название: {remark}\n"
            text += f"🔌 Протокол: {protocol.upper()}\n"
            text += f"🚪 Порт: {port}\n"
            text += "─" * 20 + "\n\n"
        
        # Добавляем кнопки для каждого inbound в одну строку (2 кнопки в ряд)
        buttons_per_row = 2
        for i, inbound in enumerate(inbounds):
            inbound_id = inbound.get("id")
            remark = inbound.get("remark", f"Inbound {inbound_id}")
            
            if i % buttons_per_row == 0:
                # Начинаем новую строку
                keyboard.append([])
            
            # Добавляем кнопку для создания клиента
            keyboard[-1].append(
                InlineKeyboardButton(
                    f"✨ {remark[:15]}",
                    callback_data=f"create_{inbound_id}"
                )
            )
        
        if not keyboard or not any(keyboard):
            await loading_msg.edit_text(
                "❌ Не удалось создать кнопки для выбора сервера."
            )
            return
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        total_buttons = sum(len(row) for row in keyboard)
        logger.info(f"Отправляю сообщение с {len(keyboard)} строками кнопок, всего {total_buttons} кнопок")
        
        try:
            await loading_msg.edit_text(text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения с кнопками: {e}")
            await loading_msg.edit_text(f"❌ Ошибка при отправке кнопок: {str(e)}")
        
    except Exception as e:
        logger.error(f"Ошибка в create_client: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")


async def _create_client_for_inbound(update: Update, context: ContextTypes.DEFAULT_TYPE, 
                                     user_id: int, username: Optional[str], inbound_id: int):
    """Создать клиента для указанного inbound"""
    try:
        # Проверяем лимит еще раз
        can_create, message = db.can_create_config(user_id)
        if not can_create:
            if hasattr(update, 'message') and update.message:
                await update.message.reply_text(f"❌ {message}")
            elif hasattr(update, 'callback_query'):
                await update.callback_query.answer(f"❌ {message}", show_alert=True)
            return
        
        # Показываем сообщение о создании
        if hasattr(update, 'callback_query'):
            await update.callback_query.answer("⏳ Создаю конфиг...")
            await update.callback_query.edit_message_text("⏳ Создаю конфиг...")
        else:
            await update.message.reply_text("⏳ Создаю конфиг...")
        
        # Получаем следующий доступный email с номером (username_1, username_2, и т.д.)
        if not username:
            error_msg = "❌ У вас не установлен username в настройках Telegram."
            if hasattr(update, 'callback_query'):
                await update.callback_query.edit_message_text(error_msg)
            else:
                await update.message.reply_text(error_msg)
            return
        
        # Вычисляем expire_time в миллисекундах (31 день)
        from datetime import datetime, timedelta
        expire_date = datetime.now() + timedelta(days=CONFIG_EXPIRY_DAYS)
        expire_time = int(expire_date.timestamp() * 1000)
        
        # Пытаемся создать конфиг с повторными попытками (на случай race condition)
        max_attempts = 3
        success = False
        email = None
        attempted_emails = []  # Список email, которые уже были попробованы
        
        for attempt in range(max_attempts):
            # Получаем следующий доступный email, исключая уже попробованные
            email = xui_client.get_next_available_email(inbound_id, username, excluded_emails=attempted_emails)
            logger.info(f"Попытка {attempt + 1}/{max_attempts}: Используется email {email} для пользователя {username}")
            
            # Добавляем email в список попробованных
            attempted_emails.append(email)
            
            # Пытаемся добавить клиента
            success = xui_client.add_client_to_inbound(inbound_id, email, expire_time=expire_time)
            
            if success:
                logger.info(f"✅ Конфиг успешно создан с email {email}")
                break
            else:
                logger.warning(f"⚠️ Попытка {attempt + 1} не удалась для email {email}, пробуем следующий...")
                # Увеличиваем задержку перед следующей попыткой, чтобы x-ui успел обновить данные
                import asyncio
                await asyncio.sleep(1.5)  # Увеличено с 0.5 до 1.5 секунд
        
        if not success:
            attempted_list = ", ".join(attempted_emails) if attempted_emails else "нет"
            error_msg = (
                f"❌ Не удалось создать клиента после {max_attempts} попыток.\n"
                f"💡 Попробованные email: {attempted_list}\n"
                f"💡 Возможно, все доступные номера заняты или произошла ошибка."
            )
            logger.error(f"Не удалось создать клиента для {username} после {max_attempts} попыток. Попробованные email: {attempted_list}")
            if hasattr(update, 'callback_query'):
                await update.callback_query.edit_message_text(error_msg)
            else:
                await update.message.reply_text(error_msg)
            return
        
        # Получаем конфигурацию
        inbounds = xui_client.get_inbounds()
        inbound = next((i for i in inbounds if i.get("id") == inbound_id), None)
        
        if not inbound:
            error_msg = "❌ Не удалось получить информацию о inbound."
            if hasattr(update, 'callback_query'):
                await update.callback_query.edit_message_text(error_msg)
            else:
                await update.message.reply_text(error_msg)
            return
        
        protocol = inbound.get("protocol", "vless").lower()
        config = xui_client.get_client_config(inbound_id, email, protocol)
        
        if not config:
            error_msg = (
                f"✅ Клиент создан, но не удалось получить конфигурацию.\n"
                f"Email: {email}\n"
                f"Inbound ID: {inbound_id}"
            )
            if hasattr(update, 'callback_query'):
                await update.callback_query.edit_message_text(error_msg)
            else:
                await update.message.reply_text(error_msg)
            return
        
        # Записываем выдачу конфига
        db.record_issued_config(user_id, email, inbound_id)
        
        # Отправляем результат
        # Не используем Markdown для конфигурации, так как она содержит специальные символы
        result_text = (
            f"✅ Клиент успешно создан!\n\n"
            f"📧 Email: {email}\n"
            f"🆔 Inbound ID: {inbound_id}\n\n"
            f"Конфигурация:"
        )
        
        if hasattr(update, 'callback_query'):
            chat_id = update.callback_query.message.chat_id
            await update.callback_query.edit_message_text(result_text)
            # Отправляем конфигурацию отдельным сообщением
            config_msg = await context.bot.send_message(chat_id=chat_id, text=config)
            # Сохраняем message_id для возможного удаления
            await save_bot_message_id(context, user_id, config_msg.message_id)
        else:
            await update.message.reply_text(result_text)
            config_msg = await update.message.reply_text(config)
            # Сохраняем message_id для возможного удаления
            await save_bot_message_id(context, user_id, config_msg.message_id)
        
        # Обновляем информацию о лимите
        user = db.get_user(user_id)
        if user:
            limit = user.get("config_limit", 1)
            created = user.get("configs_created", 0)
            remaining = max(0, limit - created)
            limit_msg = f"📊 Осталось конфигов: {remaining}/{limit}"
            
            if hasattr(update, 'callback_query'):
                chat_id = update.callback_query.message.chat_id
                await context.bot.send_message(chat_id=chat_id, text=limit_msg)
            else:
                await update.message.reply_text(limit_msg)
        
    except Exception as e:
        logger.error(f"Ошибка в _create_client_for_inbound: {e}", exc_info=True)
        error_msg = f"❌ Ошибка: {str(e)}\n\nВозвращаюсь в главное меню..."
        
        # Показываем стартовое меню после ошибки
        if hasattr(update, 'callback_query'):
            query = update.callback_query
            user_id = query.from_user.id
            username = query.from_user.username
            
            # Получаем информацию о пользователе
            user = db.get_user(user_id)
            limit = user.get("config_limit", 0) if user else 0
            created = user.get("configs_created", 0) if user else 0
            
            welcome_text = """
🤖 Привет! Я бот для получения VPN конфигураций.

📋 Доступные команды:
• Создание конфига
• Скачивание конфига
• Информация о конфиге
• Связь с администратором

💡 Используйте кнопки ниже для работы с ботом.
"""
            
            # Добавляем кнопки для быстрого доступа
            keyboard = [
                [
                    InlineKeyboardButton("✨ Создать конфиг", callback_data="create_config")
                ],
                [
                    InlineKeyboardButton("📥 Скачать конфиг", callback_data="download_config")
                ],
                [
                    InlineKeyboardButton("📊 Информация о конфиге", callback_data="config_info")
                ],
                [
                    InlineKeyboardButton("💬 Связь с администратором", callback_data="contact_admin")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(error_msg + "\n\n" + welcome_text, reply_markup=reply_markup)
        else:
            await update.message.reply_text(error_msg)
            # Вызываем start для показа меню
            await start(update, context)


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на inline кнопки"""
    query = update.callback_query
    user_id = query.from_user.id
    username = query.from_user.username
    
    if not check_access(username):
        await query.answer("❌ У вас нет доступа к этому боту.", show_alert=True)
        return
    
    await query.answer()
    
    data = query.data
    
    try:
        # Обработка кнопок меню
        if data == "create_config":
            # Создаем конфиг сразу для захардкоженного inbound
            await _create_client_for_inbound(update, context, user_id, username, DEFAULT_INBOUND_ID)
            return
        elif data == "download_config":
            await query.answer("Получаю ваш конфиг...")
            
            # Проверяем наличие username
            if not username:
                await query.edit_message_text(
                    "❌ У вас не установлен username в настройках Telegram.\n"
                    "💡 Установите username в настройках Telegram для получения конфига."
                )
                return
            
            inbound_id = DEFAULT_INBOUND_ID
            
            await query.edit_message_text("⏳ Получаю конфигурацию...")
            
            # Получаем все конфиги пользователя
            user_configs = xui_client.get_user_configs(inbound_id, username)
            
            if not user_configs:
                await query.edit_message_text(
                    "❌ У вас нет созданных конфигов.\n"
                    "💡 Используйте кнопку '✨ Создать конфиг' для создания нового конфига."
                )
                return
            
            # Берем последний конфиг (с максимальным номером)
            last_config = user_configs[-1]
            email = last_config["email"]
            
            # Получаем протокол из inbound
            inbounds = xui_client.get_inbounds()
            inbound = next((i for i in inbounds if i.get("id") == inbound_id), None)
            
            if inbound:
                protocol = inbound.get("protocol", "vless").lower()
                config = xui_client.get_client_config(inbound_id, email, protocol)
                
                if config:
                    # Записываем выдачу конфига
                    db.record_issued_config(user_id, email, inbound_id)
                    
                    # Получаем информацию о клиенте для напоминаний
                    client = last_config["client"]
                    
                    if client and client.get("expireTime", 0) > 0:
                        db.add_reminder(user_id, email, inbound_id, client.get("expireTime"))
                    
                    # Если у пользователя несколько конфигов, показываем информацию
                    config_info = ""
                    if len(user_configs) > 1:
                        config_info = f"📋 У вас {len(user_configs)} конфигов. Показан последний ({email}):\n\n"
                    
                    # Не используем Markdown для конфигурации, так как она содержит специальные символы
                    await query.edit_message_text(
                        f"{config_info}✅ Конфигурация для {email}:\n\n"
                        f"{config}"
                    )
                    
                    # Отправляем конфигурацию отдельным сообщением
                    config_msg = await context.bot.send_message(
                        chat_id=query.message.chat_id,
                        text=config
                    )
                    # Сохраняем message_id для возможного удаления
                    await save_bot_message_id(context, user_id, config_msg.message_id)
                else:
                    await query.edit_message_text(
                        f"❌ Конфиг для {email} не найден.\n"
                        "💡 Используйте кнопку '✨ Создать конфиг' для создания нового конфига."
                    )
            else:
                await query.edit_message_text("❌ Не удалось получить информацию о сервере.")
            return
        elif data == "config_info":
            await query.answer("Показываю информацию о конфиге...")
            
            # Проверяем наличие username
            if not username:
                await query.edit_message_text(
                    "❌ У вас не установлен username в настройках Telegram.\n"
                    "💡 Установите username в настройках Telegram для просмотра информации о конфиге."
                )
                return
            
            inbound_id = DEFAULT_INBOUND_ID
            
            # Получаем все конфиги пользователя
            user_configs = xui_client.get_user_configs(inbound_id, username)
            
            if not user_configs:
                await query.edit_message_text(
                    "❌ У вас нет созданных конфигов.\n"
                    "💡 Используйте кнопку '✨ Создать конфиг' для создания нового конфига."
                )
                return
            
            # Формируем информацию о всех конфигах
            from datetime import datetime
            
            info_text = f"📊 Информация о ваших конфигах:\n\n"
            info_text += f"📋 Всего конфигов: {len(user_configs)}\n\n"
            
            for i, config_data in enumerate(user_configs, 1):
                email = config_data["email"]
                client = config_data["client"]
                
                # Получаем данные о трафике
                total_traffic = client.get("total", 0)  # в байтах
                up_traffic = client.get("up", 0)  # в байтах
                down_traffic = client.get("down", 0)  # в байтах
                
                # Конвертируем в GB
                total_gb = total_traffic / (1024 ** 3)
                up_gb = up_traffic / (1024 ** 3)
                down_gb = down_traffic / (1024 ** 3)
                
                # Получаем информацию о сроке действия
                expire_time = client.get("expireTime", 0)
                if expire_time > 0:
                    expire_date = datetime.fromtimestamp(expire_time / 1000)
                    now = datetime.now()
                    days_remaining = (expire_date - now).days
                    expire_str = expire_date.strftime("%Y-%m-%d %H:%M")
                else:
                    days_remaining = "∞"
                    expire_str = "Без ограничений"
                
                info_text += f"━━━━━━━━━━━━━━━━━━━━\n"
                info_text += f"📧 Конфиг #{i}: {email}\n"
                info_text += f"📈 Трафик: {total_gb:.2f} GB (↑{up_gb:.2f} ↓{down_gb:.2f})\n"
                info_text += f"⏰ Осталось дней: {days_remaining}\n"
                info_text += f"📅 До: {expire_str}\n\n"
            
            await query.edit_message_text(info_text)
            return
        elif data == "instruction":
            await query.answer("Показываю инструкцию...")
            
            instruction_text = """
📹 Инструкция по использованию бота:

1️⃣ Создание конфига:
• Нажмите кнопку "✨ Создать конфиг"
• Конфиг будет создан автоматически на 31 день

2️⃣ Получение конфига:
• Нажмите кнопку "📥 Скачать конфиг"
• Скопируйте полученную конфигурацию

3️⃣ Информация о конфиге:
• Нажмите кнопку "📊 Информация"
• Узнайте объем трафика и срок действия

💡 Для работы с ботом необходим username в Telegram!
"""
            
            await query.edit_message_text(instruction_text)
            
            # Отправляем видео из файла instruction.mp4
            try:
                # Получаем путь к файлу относительно текущей директории скрипта
                script_dir = os.path.dirname(os.path.abspath(__file__))
                video_path = os.path.join(script_dir, "instruction.mp4")
                
                if os.path.exists(video_path):
                    with open(video_path, 'rb') as video_file:
                        video_msg = await context.bot.send_video(
                            chat_id=query.message.chat_id,
                            video=video_file,
                            caption="📹 Видео инструкция по использованию бота"
                        )
                        # Сохраняем message_id для возможного удаления
                        await save_bot_message_id(context, user_id, video_msg.message_id)
                    logger.info(f"Видео инструкция отправлена из файла: {video_path}")
                else:
                    logger.warning(f"Файл видео инструкции не найден: {video_path}")
                    # Пытаемся отправить по file_id, если файл не найден
                    try:
                        from config import INSTRUCTION_VIDEO_FILE_ID
                        if INSTRUCTION_VIDEO_FILE_ID:
                            video_msg = await context.bot.send_video(
                                chat_id=query.message.chat_id,
                                video=INSTRUCTION_VIDEO_FILE_ID,
                                caption="📹 Видео инструкция по использованию бота"
                            )
                            # Сохраняем message_id для возможного удаления
                            await save_bot_message_id(context, user_id, video_msg.message_id)
                    except ImportError:
                        pass
            except Exception as e:
                logger.error(f"Ошибка при отправке видео инструкции: {e}")
                # Пытаемся отправить по file_id в случае ошибки
                try:
                    from config import INSTRUCTION_VIDEO_FILE_ID
                    if INSTRUCTION_VIDEO_FILE_ID:
                        video_msg = await context.bot.send_video(
                            chat_id=query.message.chat_id,
                            video=INSTRUCTION_VIDEO_FILE_ID,
                            caption="📹 Видео инструкция по использованию бота"
                        )
                        # Сохраняем message_id для возможного удаления
                        await save_bot_message_id(context, user_id, video_msg.message_id)
                except ImportError:
                    pass
            
            # Отправляем ссылки на приложения
            await send_app_links(context, query.message.chat_id, user_id)
            
            return
        elif data == "contact_admin":
            await query.answer("Открываю контакты администратора...")
            admin_text = """
💬 Связь с администратором:

👤 Администратор:
• @ImmoLateNeltharion

📝 Для связи с администратором:
1. Напишите администратору в Telegram
2. Укажите ваш username: @{username}
3. Опишите вашу проблему или вопрос

💡 Администратор может помочь с:
• Увеличением лимита конфигов
• Решением технических проблем
• Вопросами по использованию бота
""".format(username=username or "не указан")
            
            await query.edit_message_text(admin_text)
            return
        elif data.startswith("create_"):
            # Создать клиента для inbound (старая логика, оставляем для совместимости)
            inbound_id = int(data.split("_")[1])
            await _create_client_for_inbound(update, context, user_id, username, inbound_id)
            
        elif data.startswith("clients_"):
            # Показать клиентов для inbound
            inbound_id = int(data.split("_")[1])
            
            await query.edit_message_text(f"⏳ Получаю список клиентов...")
            
            clients = xui_client.get_inbound_clients(inbound_id)
            
            if not clients:
                await query.edit_message_text(f"❌ Не найдено клиентов для inbound {inbound_id}.")
                return
            
            text = f"📋 Клиенты для inbound {inbound_id}:\n\n"
            keyboard = []
            
            for client in clients:
                email = client.get("email", "N/A")
                total = client.get("total", 0)
                expire = client.get("expireTime", 0)
                
                text += f"📧 Email: {email}\n"
                text += f"📊 Трафик: {total / (1024**3):.2f} GB\n"
                if expire > 0:
                    expire_date = datetime.fromtimestamp(expire / 1000)
                    text += f"⏰ Истекает: {expire_date.strftime('%Y-%m-%d %H:%M')}\n"
                text += "─" * 20 + "\n\n"
            
            # Добавляем кнопки для каждого клиента в одну строку (2 кнопки в ряд)
            buttons_per_row = 2
            for i, client in enumerate(clients):
                email = client.get("email", "N/A")
                
                if i % buttons_per_row == 0:
                    # Начинаем новую строку
                    keyboard.append([])
                
                # Добавляем кнопку для получения конфига
                keyboard[-1].append(
                    InlineKeyboardButton(
                        f"📥 {email[:15]}",
                        callback_data=f"get_{inbound_id}_{email}"
                    )
                )
            
            if not keyboard or not any(keyboard):
                await query.edit_message_text("❌ Не удалось создать кнопки для клиентов.")
                return
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            total_buttons = sum(len(row) for row in keyboard)
            logger.info(f"Отправляю список клиентов с {len(keyboard)} строками кнопок, всего {total_buttons} кнопок")
            
            try:
                await query.edit_message_text(text, reply_markup=reply_markup)
            except Exception as e:
                logger.error(f"Ошибка при отправке сообщения с кнопками: {e}")
                await query.edit_message_text(f"❌ Ошибка при отправке кнопок: {str(e)}")
            
        elif data.startswith("get_"):
            # Получить конфигурацию
            parts = data.split("_", 2)
            if len(parts) >= 3:
                inbound_id = int(parts[1])
                email = parts[2]
                
                # Проверяем лимит
                can_create, message = db.can_create_config(user_id)
                if not can_create:
                    await query.answer(message, show_alert=True)
                    return
                
                await query.edit_message_text(f"⏳ Получаю конфигурацию для {email}...")
                
                # Получаем протокол из inbound
                inbounds = xui_client.get_inbounds()
                inbound = next((i for i in inbounds if i.get("id") == inbound_id), None)
                
                if inbound:
                    protocol = inbound.get("protocol", "vless").lower()
                    config = xui_client.get_client_config(inbound_id, email, protocol)
                    
                    if config:
                        # Записываем выдачу конфига
                        db.record_issued_config(user_id, email, inbound_id)
                        
                        # Получаем информацию о клиенте для напоминаний
                        clients = xui_client.get_inbound_clients(inbound_id)
                        client = next((c for c in clients if c.get("email") == email), None)
                        
                        if client and client.get("expireTime", 0) > 0:
                            db.add_reminder(user_id, email, inbound_id, client.get("expireTime"))
                        
                        # Не используем Markdown для конфигурации, так как она содержит специальные символы
                        await query.edit_message_text(
                            f"✅ Конфигурация для {email}:\n\n"
                            f"{config}"
                        )
                        
                        # Отправляем конфигурацию отдельным сообщением
                        await context.bot.send_message(
                            chat_id=query.message.chat_id,
                            text=config
                        )
                        
                        # Обновляем информацию о лимите
                        user = db.get_user(user_id)
                        if user:
                            limit = user.get("config_limit", 0)
                            created = user.get("configs_created", 0)
                            remaining = max(0, limit - created)
                            await context.bot.send_message(
                                chat_id=query.message.chat_id,
                                text=f"📊 Осталось конфигов: {remaining}/{limit}"
                            )
                    else:
                        await query.edit_message_text(f"❌ Не удалось получить конфигурацию для {email}.")
                else:
                    await query.edit_message_text(f"❌ Inbound {inbound_id} не найден.")
                    
    except Exception as e:
        logger.error(f"Ошибка в button_callback: {e}")
        await query.edit_message_text(f"❌ Ошибка: {str(e)}")


# ========== СИСТЕМА НАПОМИНАНИЙ ==========

async def check_and_send_reminders(context: ContextTypes.DEFAULT_TYPE):
    """Проверка и отправка напоминаний"""
    try:
        for days in REMINDER_DAYS:
            reminders = db.get_pending_reminders(days)
            
            for reminder in reminders:
                user_id = reminder.get("user_id")
                email = reminder.get("email")
                expire_time = reminder.get("expire_time")
                reminder_id = reminder.get("id")
                
                expire_date = datetime.fromtimestamp(expire_time / 1000)
                
                message = f"""
⏰ Напоминание о истечении VPN конфигурации

📧 Email: {email}
📅 Истекает через: {days} дней
🗓️ Дата истечения: {expire_date.strftime('%Y-%m-%d %H:%M')}

💡 Не забудьте продлить или создать новый конфиг!
"""
                
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=message
                    )
                    db.mark_reminder_sent(reminder_id, days)
                    logger.info(f"Напоминание отправлено пользователю {user_id} для {email} за {days} дней")
                except Exception as e:
                    logger.error(f"Ошибка отправки напоминания: {e}")
                    
    except Exception as e:
        logger.error(f"Ошибка в check_and_send_reminders: {e}")


def main():
    """Главная функция для запуска бота"""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN не установлен! Установите его в переменных окружения или config.py")
        return
    
    # Создаем приложение
    async def set_bot_description(app: Application):
        """Установить описание бота при инициализации"""
        try:
            await app.bot.set_my_description(
                description="Здесь вы можете получить свой конфиг для vless. Для начала нажмите /start"
            )
            logger.info("Описание бота установлено")
        except Exception as e:
            logger.error(f"Ошибка при установке описания бота: {e}")
    
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(set_bot_description).build()
    
    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("myinfo", myinfo_command))
    application.add_handler(CommandHandler("list", list_inbounds))
    application.add_handler(CommandHandler("clients", list_clients))
    application.add_handler(CommandHandler("get", get_config))
    application.add_handler(CommandHandler("create", create_client))
    
    # Админские команды
    application.add_handler(CommandHandler("adminhelp", admin_help))
    application.add_handler(CommandHandler("adduser", add_user_command))
    application.add_handler(CommandHandler("setlimit", set_limit_command))
    application.add_handler(CommandHandler("extend", extend_config_command))
    application.add_handler(CommandHandler("users", list_users_command))
    application.add_handler(CommandHandler("cleardb", clear_database_command))
    application.add_handler(CommandHandler("deleteuser", delete_user_command))
    application.add_handler(CommandHandler("sync_reminders", sync_reminders_command))
    
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Обработчик для кнопки "Меню" (Reply Keyboard)
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex("^Меню$"), start))
    
    # Настраиваем периодическую проверку напоминаний (если JobQueue доступен)
    job_queue = application.job_queue
    if job_queue is not None:
        job_queue.run_repeating(
            check_and_send_reminders,
            interval=REMINDER_CHECK_INTERVAL,
            first=10  # Первая проверка через 10 секунд после запуска
        )
        logger.info("Система напоминаний активирована")
    else:
        logger.warning("JobQueue не установлен. Напоминания отключены. Установите: pip install 'python-telegram-bot[job-queue]'")
    
    # Запускаем бота
    logger.info("Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
