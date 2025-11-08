"""
Telegram бот для выдачи VPN конфигураций из x-ui
"""
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message, Chat, User
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
    DEFAULT_INBOUND_ID,
    ADMIN_USERNAMES,
    REMINDER_CHECK_INTERVAL,
    REMINDER_DAYS
)

# Импортируем CONFIG_EXPIRY_DAYS с дефолтным значением для обратной совместимости
try:
    from config import CONFIG_EXPIRY_DAYS
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
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)


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

/users - Показать список всех пользователей

/sync_reminders - Синхронизировать напоминания из x-ui

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
        
        # Используем username как email клиента
        email = username
        
        # Вычисляем expire_time в миллисекундах (31 день)
        from datetime import datetime, timedelta
        expire_date = datetime.now() + timedelta(days=CONFIG_EXPIRY_DAYS)
        expire_time = int(expire_date.timestamp() * 1000)
        
        # Добавляем клиента с expire_time
        success = xui_client.add_client_to_inbound(inbound_id, email, expire_time=expire_time)
        
        if not success:
            error_msg = "❌ Не удалось создать клиента. Возможно, клиент с таким email уже существует."
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
            await context.bot.send_message(chat_id=chat_id, text=config)
        else:
            await update.message.reply_text(result_text)
            await update.message.reply_text(config)
        
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
            
            # Получаем конфиг по username (email = username)
            email = username
            inbound_id = DEFAULT_INBOUND_ID
            
            await query.edit_message_text("⏳ Получаю конфигурацию...")
            
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
            
            email = username
            inbound_id = DEFAULT_INBOUND_ID
            
            # Получаем информацию о клиенте из x-ui
            clients = xui_client.get_inbound_clients(inbound_id)
            client = next((c for c in clients if c.get("email") == email), None)
            
            if not client:
                await query.edit_message_text(
                    f"❌ Конфиг для {email} не найден.\n"
                    "💡 Используйте кнопку '✨ Создать конфиг' для создания нового конфига."
                )
                return
            
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
                from datetime import datetime
                expire_date = datetime.fromtimestamp(expire_time / 1000)
                now = datetime.now()
                days_remaining = (expire_date - now).days
                expire_str = expire_date.strftime("%Y-%m-%d %H:%M")
            else:
                days_remaining = "∞"
                expire_str = "Без ограничений"
            
            info_text = f"""
📊 Информация о вашем конфиге:

📧 Email: {email}
🆔 Inbound ID: {inbound_id}

📈 Трафик:
• Отправлено: {up_gb:.2f} GB
• Получено: {down_gb:.2f} GB
• Всего: {total_gb:.2f} GB

⏰ Срок действия:
• Осталось дней: {days_remaining}
• Дата окончания: {expire_str}
"""
            
            await query.edit_message_text(info_text)
            return
        elif data == "contact_admin":
            await query.answer("Открываю контакты администратора...")
            admin_text = """
💬 Связь с администратором:

👤 Администраторы:
• @ImmoLateNeltharion
• @r00tfu11

📝 Для связи с администратором:
1. Напишите одному из администраторов в Telegram
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
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
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
    application.add_handler(CommandHandler("users", list_users_command))
    application.add_handler(CommandHandler("sync_reminders", sync_reminders_command))
    
    application.add_handler(CallbackQueryHandler(button_callback))
    
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
