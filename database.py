"""
Модуль для работы с базой данных пользователей и лимитов
"""
import sqlite3
import logging
from typing import Optional, Dict, List, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class Database:
    """Класс для работы с базой данных SQLite"""
    
    def __init__(self, db_path: str = "bot.db"):
        self.db_path = db_path
        self.init_database()
    
    def get_connection(self):
        """Получить соединение с базой данных"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_database(self):
        """Инициализация базы данных"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Таблица доступа к боту
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alloved_users (
                username TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица пользователей
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                config_limit INTEGER DEFAULT 0,
                configs_created INTEGER DEFAULT 0,
                is_admin INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица выданных конфигов
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS issued_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                email TEXT,
                inbound_id INTEGER,
                issued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        """)
        
        # Таблица напоминаний
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                email TEXT,
                inbound_id INTEGER,
                expire_time INTEGER,
                reminder_10_days_sent INTEGER DEFAULT 0,
                reminder_3_days_sent INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
        """)
        
        conn.commit()
        conn.close()
        logger.info("База данных инициализирована")

    def add_allowed_user(self, username):
        """Открыть доступ пользователя в боту"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # Проверяем, существует ли пользователь
            cursor.execute("SELECT * FROM alloved_users WHERE username = ?", (username,))
            existing = cursor.fetchone()

            if existing:
                logger.info(f"У юзера {username} есть доступ к боту")
            else:
                cursor.execute("""
                    INSERT INTO alloved_users (username)
                    VALUES (?)
                """, (username,))
                logger.info(f"Юзеру {username} открыт доступ к боту")
            
            conn.commit()
            conn.close()
            return True

        except Exception as e:
            logger.error(f"Ошибка что то пошло не так (add_allowed_user) {username}: {e}")
            return False

    def get_allowed_user(self, username):
        """Проерка юреза доступа к боту"""
        try:
            result = False
            conn = self.get_connection()
            cursor = conn.cursor()

            # Проверяем, существует ли пользователь
            cursor.execute("SELECT * FROM alloved_users WHERE username = ?", (username,))
            existing = cursor.fetchone()

            if existing:
                logger.info(f"У юзера {username} есть доступ к боту")
                result = True
            else:
                logger.info(f"Юзеру {username} открыт доступ к боту")
            
            conn.commit()
            conn.close()
            return result

        except Exception as e:
            logger.error(f"Ошибка что то пошло не так (get_allowed_user) {username}: {e}")
            return False
    
    def add_user(self, user_id: int, username: Optional[str] = None, 
                 full_name: Optional[str] = None, config_limit: int = 1) -> bool:
        """Добавить пользователя или обновить его данные"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Проверяем, существует ли пользователь
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            existing = cursor.fetchone()
            
            if existing:
                # Обновляем только username и full_name, сохраняя лимит
                cursor.execute("""
                    UPDATE users SET username = ?, full_name = ?
                    WHERE user_id = ?
                """, (username, full_name, user_id))
                logger.info(f"Данные пользователя {user_id} обновлены")
            else:
                # Создаем нового пользователя с лимитом по умолчанию 1
                if config_limit == 0:
                    config_limit = 1
                cursor.execute("""
                    INSERT INTO users (user_id, username, full_name, config_limit)
                    VALUES (?, ?, ?, ?)
                """, (user_id, username, full_name, config_limit))
                logger.info(f"Пользователь {user_id} добавлен с лимитом {config_limit}")
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Ошибка добавления пользователя: {e}")
            return False
    
    def get_user(self, user_id: int) -> Optional[Dict]:
        """Получить информацию о пользователе"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return dict(row)
            return None
        except Exception as e:
            logger.error(f"Ошибка получения пользователя: {e}")
            return None
    
    def get_user_by_username(self, username: str) -> Optional[Dict]:
        """Получить пользователя по username"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Нормализуем username (убираем @ и приводим к нижнему регистру)
            normalized_username = username.lstrip('@').lower()
            
            # Ищем пользователя с учетом нормализации
            # Проверяем оба варианта: с @ и без, в разном регистре
            # Используем REPLACE для удаления @ и LOWER для приведения к нижнему регистру
            cursor.execute("""
                SELECT * FROM users 
                WHERE LOWER(REPLACE(username, '@', '')) = ?
            """, (normalized_username,))
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return dict(row)
            return None
        except Exception as e:
            logger.error(f"Ошибка получения пользователя по username: {e}")
            return None
    
    def set_config_limit(self, user_id: int, limit: int) -> bool:
        """Установить лимит конфигов для пользователя"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE users SET config_limit = ? WHERE user_id = ?
            """, (limit, user_id))
            
            conn.commit()
            conn.close()
            logger.info(f"Лимит для пользователя {user_id} установлен: {limit}")
            return True
        except Exception as e:
            logger.error(f"Ошибка установки лимита: {e}")
            return False
    
    def increment_configs_created(self, user_id: int, conn=None) -> bool:
        """Увеличить счетчик созданных конфигов"""
        try:
            # Если передано соединение, используем его, иначе создаем новое
            should_close = False
            if conn is None:
                conn = self.get_connection()
                should_close = True
            
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE users SET configs_created = configs_created + 1 
                WHERE user_id = ?
            """, (user_id,))
            
            if should_close:
                conn.commit()
                conn.close()
            return True
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower():
                # Если база заблокирована, пробуем еще раз с небольшой задержкой
                import time
                time.sleep(0.1)
                if conn is None:
                    conn = self.get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE users SET configs_created = configs_created + 1 
                    WHERE user_id = ?
                """, (user_id,))
                if should_close or conn is None:
                    conn.commit()
                    conn.close()
                return True
            logger.error(f"Ошибка увеличения счетчика: {e}")
            return False
        except Exception as e:
            logger.error(f"Ошибка увеличения счетчика: {e}")
            return False
    
    def can_create_config(self, user_id: int):
        """Проверить, может ли пользователь создать конфиг"""
        user = self.get_user(user_id)
        
        if not user:
            return False, "Пользователь не найден в базе. Обратитесь к администратору."
        
        limit = user.get("config_limit", 0)
        created = user.get("configs_created", 0)
        
        if limit == 0:
            return False, "Лимит конфигов не установлен. Обратитесь к администратору."
        
        if created >= limit:
            return False, f"Вы достигли лимита конфигов ({limit}). Использовано: {created}/{limit}"
        
        return True, f"Осталось конфигов: {limit - created - 1}/{limit}"
    
    def get_user_configs(self, user_id: int) -> List[Dict]:
        """Получить все конфиги пользователя"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT email, inbound_id, issued_at 
                FROM issued_configs 
                WHERE user_id = ?
                ORDER BY issued_at DESC
            """, (user_id,))
            
            rows = cursor.fetchall()
            conn.close()
            
            configs = []
            for row in rows:
                configs.append({
                    "email": row[0],
                    "inbound_id": row[1],
                    "issued_at": row[2]
                })
            
            return configs
        except Exception as e:
            logger.error(f"Ошибка получения конфигов пользователя: {e}")
            return []
    
    def record_issued_config(self, user_id: int, email: str, inbound_id: int) -> bool:
        """Записать выданный конфиг"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO issued_configs (user_id, email, inbound_id)
                VALUES (?, ?, ?)
            """, (user_id, email, inbound_id))
            
            # Используем то же соединение для увеличения счетчика
            self.increment_configs_created(user_id, conn)
            
            conn.commit()
            conn.close()
            return True
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower():
                # Если база заблокирована, пробуем еще раз с небольшой задержкой
                import time
                time.sleep(0.2)
                try:
                    conn = self.get_connection()
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO issued_configs (user_id, email, inbound_id)
                        VALUES (?, ?, ?)
                    """, (user_id, email, inbound_id))
                    self.increment_configs_created(user_id, conn)
                    conn.commit()
                    conn.close()
                    return True
                except Exception as retry_e:
                    logger.error(f"Ошибка записи конфига при повторной попытке: {retry_e}")
                    return False
            logger.error(f"Ошибка записи конфига: {e}")
            return False
        except Exception as e:
            logger.error(f"Ошибка записи конфига: {e}")
            return False
    
    def set_admin(self, user_id: int, is_admin: bool = True) -> bool:
        """Установить статус администратора"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE users SET is_admin = ? WHERE user_id = ?
            """, (1 if is_admin else 0, user_id))
            
            conn.commit()
            conn.close()
            logger.info(f"Статус администратора для {user_id}: {is_admin}")
            return True
        except Exception as e:
            logger.error(f"Ошибка установки админа: {e}")
            return False
    
    def is_admin(self, user_id: int) -> bool:
        """Проверить, является ли пользователь администратором"""
        user = self.get_user(user_id)
        if user:
            return bool(user.get("is_admin", 0))
        return False
    
    def get_all_users(self) -> List[Dict]:
        """Получить список всех пользователей"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM users ORDER BY created_at DESC")
            rows = cursor.fetchall()
            conn.close()
            
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка получения пользователей: {e}")
            return []
    
    def add_reminder(self, user_id: int, email: str, inbound_id: int, expire_time: int) -> bool:
        """Добавить напоминание о истечении конфига"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Удаляем старое напоминание если есть
            cursor.execute("""
                DELETE FROM reminders 
                WHERE user_id = ? AND email = ? AND inbound_id = ?
            """, (user_id, email, inbound_id))
            
            # Добавляем новое
            cursor.execute("""
                INSERT INTO reminders (user_id, email, inbound_id, expire_time)
                VALUES (?, ?, ?, ?)
            """, (user_id, email, inbound_id, expire_time))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Ошибка добавления напоминания: {e}")
            return False
    
    def get_pending_reminders(self, days_before: int) -> List[Dict]:
        """Получить напоминания, которые нужно отправить"""
        try:
            from datetime import datetime, timedelta
            import time
            
            target_time = datetime.now() + timedelta(days=days_before)
            target_timestamp = int(target_time.timestamp() * 1000)
            
            # Диапазон ±1 день для напоминаний
            time_range = 24 * 60 * 60 * 1000  # 1 день в миллисекундах
            
            conn = self.get_connection()
            cursor = conn.cursor()
            
            reminder_field = "reminder_10_days_sent" if days_before == 10 else "reminder_3_days_sent"
            
            cursor.execute(f"""
                SELECT * FROM reminders 
                WHERE expire_time >= ? AND expire_time <= ?
                AND {reminder_field} = 0
            """, (target_timestamp - time_range, target_timestamp + time_range))
            
            rows = cursor.fetchall()
            conn.close()
            
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка получения напоминаний: {e}")
            return []
    
    def mark_reminder_sent(self, reminder_id: int, days_before: int) -> bool:
        """Отметить напоминание как отправленное"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            reminder_field = "reminder_10_days_sent" if days_before == 10 else "reminder_3_days_sent"
            
            cursor.execute(f"""
                UPDATE reminders SET {reminder_field} = 1 WHERE id = ?
            """, (reminder_id,))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Ошибка отметки напоминания: {e}")
            return False
    
    def sync_reminders_from_xui(self, xui_client, user_id: int):
        """Синхронизировать напоминания из x-ui для пользователя"""
        try:
            inbounds = xui_client.get_inbounds()
            
            for inbound in inbounds:
                inbound_id = inbound.get("id")
                clients = xui_client.get_inbound_clients(inbound_id)
                
                for client in clients:
                    email = client.get("email")
                    expire_time = client.get("expireTime", 0)
                    
                    if expire_time > 0:
                        # Проверяем, есть ли этот конфиг в issued_configs для этого пользователя
                        conn = self.get_connection()
                        cursor = conn.cursor()
                        
                        cursor.execute("""
                            SELECT * FROM issued_configs 
                            WHERE user_id = ? AND email = ? AND inbound_id = ?
                        """, (user_id, email, inbound_id))
                        
                        if cursor.fetchone():
                            # Добавляем напоминание
                            self.add_reminder(user_id, email, inbound_id, expire_time)
                        
                        conn.close()
        except Exception as e:
            logger.error(f"Ошибка синхронизации напоминаний: {e}")
    
    def delete_user_data(self, username: str) -> Tuple[bool, str, Optional[int]]:
        """Удалить все данные пользователя по username
        
        Returns:
            tuple: (success: bool, message: str, user_id: Optional[int])
        """
        try:
            # Нормализуем username
            normalized_username = username.lstrip('@').lower()
            
            # Находим пользователя
            user = self.get_user_by_username(normalized_username)
            if not user:
                return False, f"Пользователь @{normalized_username} не найден в базе данных.", None
            
            user_id = user['user_id']
            
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Подсчитываем количество записей перед удалением
            cursor.execute("SELECT COUNT(*) FROM issued_configs WHERE user_id = ?", (user_id,))
            configs_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM reminders WHERE user_id = ?", (user_id,))
            reminders_count = cursor.fetchone()[0]
            
            # Удаляем данные из всех таблиц
            cursor.execute("DELETE FROM alloved_users WHERE username = ?", (normalized_username,))
            cursor.execute("DELETE FROM reminders WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM issued_configs WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
            
            conn.commit()
            conn.close()
            
            message = (
                f"✅ Данные пользователя @{normalized_username} (ID: {user_id}) успешно удалены:\n"
                f"• Удалено конфигов: {configs_count}\n"
                f"• Удалено напоминаний: {reminders_count}\n"
                f"• Удален пользователь из базы"
            )
            
            logger.info(f"Удалены данные пользователя {normalized_username} (ID: {user_id})")
            return True, message, user_id
            
        except Exception as e:
            logger.error(f"Ошибка удаления данных пользователя: {e}", exc_info=True)
            return False, f"Ошибка при удалении данных: {str(e)}", None

