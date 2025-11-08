"""
Модуль для работы с x-ui API
"""
import requests
import json
import logging
from typing import Optional, Dict, List, Any
from config import XUI_BASE_URL, XUI_USERNAME, XUI_PASSWORD

logger = logging.getLogger(__name__)


class XUIClient:
    """Клиент для работы с x-ui API"""
    
    def __init__(self):
        self.base_url = XUI_BASE_URL.rstrip('/')
        self.username = XUI_USERNAME
        self.password = XUI_PASSWORD
        self.session = requests.Session()
        self.token = None
        
    def _login(self) -> bool:
        """Авторизация в x-ui панели"""
        try:
            # Пробуем оба варианта - /panel/panel/login и /panel/login
            login_urls = [
                f"{self.base_url}/panel/panel/login",
                f"{self.base_url}/panel/login"
            ]
            
            for login_url in login_urls:
                logger.info(f"Попытка авторизации в x-ui: {login_url}")
            
                response = self.session.post(
                    login_url,
                    json={
                        "username": self.username,
                        "password": self.password
                    },
                    timeout=10
                )
                
                logger.info(f"Ответ авторизации: статус {response.status_code}")
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        logger.info(f"Ответ авторизации: {data}")
                        
                        if data.get("success"):
                            # Токен может быть в cookies или в заголовках
                            # Проверяем cookies
                            cookies = response.cookies
                            logger.info(f"Cookies получены: {len(cookies)} штук")
                            
                            if cookies:
                                # Ищем токен в cookies
                                for cookie in cookies:
                                    logger.info(f"Cookie: {cookie.name} = {cookie.value[:20]}...")
                                    if 'token' in cookie.name.lower() or 'auth' in cookie.name.lower():
                                        self.token = cookie.value
                                        logger.info(f"Токен найден в cookie: {cookie.name}")
                                        break
                            
                            # Если токен не найден в cookies, пробуем в JSON
                            if not self.token:
                                self.token = data.get("data", {}).get("token")
                                if self.token:
                                    logger.info("Токен найден в JSON ответе")
                            
                            # Если токен найден, добавляем в заголовки
                            if self.token:
                                self.session.headers.update({
                                    "Authorization": f"Bearer {self.token}"
                                })
                                logger.info("Токен добавлен в заголовки")
                            else:
                                # Если токен не найден, используем cookies напрямую
                                # x-ui может использовать cookie-based аутентификацию
                                logger.info("Токен не найден, используем cookie-based аутентификацию")
                            
                            return True
                        else:
                            logger.warning(f"Авторизация не удалась для {login_url}: {data.get('msg', 'Unknown error')}")
                    except json.JSONDecodeError as e:
                        logger.warning(f"Ошибка парсинга JSON ответа для {login_url}: {e}, текст: {response.text[:200]}")
                else:
                    logger.warning(f"HTTP ошибка авторизации для {login_url}: {response.status_code}, текст: {response.text[:200]}")
            
            # Если все варианты не сработали
            logger.error("Все варианты URL для авторизации не сработали")
            return False
        except Exception as e:
            logger.error(f"Ошибка авторизации: {e}", exc_info=True)
            return False
    
    def _ensure_authenticated(self):
        """Проверка и обновление токена при необходимости"""
        # Всегда переавторизуемся для надежности
        # x-ui может использовать cookie-based аутентификацию, которая работает через сессию
        if not self._login():
            raise Exception("Не удалось авторизоваться в x-ui")
    
    def get_inbounds(self) -> List[Dict[str, Any]]:
        """Получить список всех inbounds"""
        try:
            self._ensure_authenticated()
        except Exception as e:
            logger.error(f"Ошибка авторизации: {e}")
            return []
        
        try:
            # Пробуем разные варианты URL и методов
            # 3x-ui (форк x-ui от MHSanaei)
            # Источники:
            # - GitHub: https://github.com/MHSanaei/3x-ui
            # - Postman коллекция: https://www.postman.com/hsanaei/3x-ui/collection/q1l5l0u/3x-ui
            # webBasePath: /panel/ - базовый путь веб-интерфейса
            # Подтвержденный путь для 3x-ui: /panel/panel/inbounds
            # Приоритет: сначала пробуем наиболее вероятные варианты для 3x-ui
            url_methods = [
                # Подтвержденный путь для 3x-ui (без /list)
                (f"{self.base_url}/panel/panel/inbounds", "GET"),
                (f"{self.base_url}/panel/panel/inbounds", "POST"),
                # Варианты с /api/ для 3x-ui
                (f"{self.base_url}/panel/panel/api/inbounds/list", "GET"),
                (f"{self.base_url}/panel/panel/api/inbounds/list", "POST"),
                (f"{self.base_url}/panel/panel/api/inbounds", "GET"),
                (f"{self.base_url}/panel/panel/api/inbounds", "POST"),
                # Стандартные endpoints согласно документации
                (f"{self.base_url}/panel/api/inbounds/list", "GET"),
                (f"{self.base_url}/panel/api/inbounds/list", "POST"),
                (f"{self.base_url}/panel/api/inbounds", "GET"),
                (f"{self.base_url}/panel/api/inbounds", "POST"),
                # Варианты без /api/
                (f"{self.base_url}/panel/inbounds/list", "GET"),
                (f"{self.base_url}/panel/inbounds/list", "POST"),
                (f"{self.base_url}/panel/inbounds", "GET"),
                (f"{self.base_url}/panel/inbounds", "POST"),
            ]
            
            for url, method in url_methods:
                logger.info(f"Попытка запроса списка inbounds: {method} {url}")
                try:
                    # Устанавливаем заголовки для JSON API
                    headers = {
                        "Accept": "application/json",
                        "Content-Type": "application/json"
                    }
                    
                    if method == "GET":
                        response = self.session.get(url, headers=headers, timeout=10, allow_redirects=True)
                    else:
                        # Пробуем POST с пустым телом и с пустым JSON объектом
                        # Некоторые версии x-ui требуют определенный формат
                        try:
                            response = self.session.post(url, json={}, headers=headers, timeout=10, allow_redirects=True)
                        except:
                            # Если не сработало, пробуем без json
                            response = self.session.post(url, data={}, headers=headers, timeout=10, allow_redirects=True)
                    
                    logger.info(f"Ответ получения inbounds: статус {response.status_code}, Content-Type: {response.headers.get('Content-Type', 'unknown')}")
                    
                    if response.status_code == 200:
                        # Проверяем, что ответ JSON, а не HTML
                        content_type = response.headers.get('Content-Type', '').lower()
                        if 'application/json' not in content_type and 'text/html' in content_type:
                            logger.debug(f"Получен HTML вместо JSON для {method} {url}, пробуем следующий вариант")
                            continue
                        
                        try:
                            data = response.json()
                            logger.info(f"Ответ API: success={data.get('success')}, obj type={type(data.get('obj'))}")
                            
                            if data.get("success"):
                                inbounds = data.get("obj", [])
                                logger.info(f"✅ Успешно получено inbounds: {len(inbounds) if inbounds else 0}")
                                if inbounds:
                                    logger.info(f"Первый inbound: {inbounds[0] if inbounds else 'None'}")
                                return inbounds if inbounds else []
                            else:
                                error_msg = data.get('msg', 'Unknown error')
                                logger.warning(f"API вернул success=False: {error_msg}")
                        except json.JSONDecodeError as e:
                            # Если получили HTML вместо JSON, пробуем следующий вариант
                            if response.text.strip().startswith('<!DOCTYPE') or response.text.strip().startswith('<html'):
                                logger.debug(f"Получен HTML вместо JSON для {method} {url}, пробуем следующий вариант")
                                continue
                            logger.warning(f"Ошибка парсинга JSON: {e}, текст: {response.text[:200]}")
                    elif response.status_code == 404:
                        # 404 - просто пробуем следующий вариант
                        logger.debug(f"404 для {method} {url}")
                    else:
                        # Если не 404, возможно это правильный URL, но с ошибкой
                        logger.warning(f"HTTP ошибка для {method} {url}: {response.status_code}, ответ: {response.text[:200]}")
                        # Если получили ответ (не 404), возможно это правильный URL, но с ошибкой авторизации
                        # Попробуем переавторизоваться и повторить запрос
                        if response.status_code in [401, 403]:
                            logger.info(f"Получен {response.status_code}, пробуем переавторизоваться...")
                            if self._login():
                                # Повторяем запрос после переавторизации
                                if method == "GET":
                                    retry_response = self.session.get(url, timeout=10)
                                else:
                                    retry_response = self.session.post(url, json={}, timeout=10)
                                
                                if retry_response.status_code == 200:
                                    try:
                                        retry_data = retry_response.json()
                                        if retry_data.get("success"):
                                            inbounds = retry_data.get("obj", [])
                                            logger.info(f"✅ Успешно получено inbounds после переавторизации: {len(inbounds) if inbounds else 0}")
                                            return inbounds if inbounds else []
                                    except:
                                        pass
                except Exception as e:
                    logger.warning(f"Ошибка при запросе {method} {url}: {e}")
            
            # Если все URL не сработали, возвращаем пустой список
            logger.error("Все варианты URL и методов не сработали")
            return []
        except Exception as e:
            logger.error(f"Ошибка получения inbounds: {e}", exc_info=True)
            return []
    
    def get_inbound_clients(self, inbound_id: int) -> List[Dict[str, Any]]:
        """Получить список клиентов для конкретного inbound"""
        try:
            self._ensure_authenticated()
        except Exception as e:
            logger.error(f"Ошибка авторизации: {e}")
            return []
        
        try:
            # Используем данные из списка inbounds - там уже есть вся информация
            # Источники: https://github.com/MHSanaei/3x-ui
            inbounds = self.get_inbounds()
            inbound = next((i for i in inbounds if i.get("id") == inbound_id), None)
            
            if not inbound:
                logger.error(f"Inbound {inbound_id} не найден в списке")
                return []
            
            # Парсим settings
            settings_str = inbound.get("settings", "{}")
            settings = json.loads(settings_str) if settings_str else {}
            
            # Получаем клиентов из settings
            clients = settings.get("clients", [])
            
            logger.info(f"Получено клиентов для inbound {inbound_id}: {len(clients) if clients else 0}")
            return clients if clients else []
        except Exception as e:
            logger.error(f"Ошибка получения клиентов: {e}", exc_info=True)
            return []
    
    def get_client_config(self, inbound_id: int, email: str, protocol: str = "vless") -> Optional[str]:
        """Получить конфигурацию клиента для подключения"""
        self._ensure_authenticated()
        
        try:
            # Используем данные из списка inbounds - там уже есть вся информация
            # Источники: https://github.com/MHSanaei/3x-ui
            inbounds = self.get_inbounds()
            inbound = next((i for i in inbounds if i.get("id") == inbound_id), None)
            
            if not inbound:
                logger.error(f"Inbound {inbound_id} не найден в списке")
                return None
            
            # Парсим settings и streamSettings
            settings_str = inbound.get("settings", "{}")
            settings = json.loads(settings_str) if settings_str else {}
            
            stream_settings_str = inbound.get("streamSettings", "{}")
            stream_settings = json.loads(stream_settings_str) if stream_settings_str else {}
            
            # Получаем клиента
            clients = settings.get("clients", [])
            client = next((c for c in clients if c.get("email") == email), None)
            
            if not client:
                logger.warning(f"Клиент с email {email} не найден в inbound {inbound_id}")
                return None
            
            # Формируем конфигурацию в зависимости от протокола
            if protocol.lower() == "vless":
                return self._generate_vless_config(
                    client.get("id"),
                    inbound.get("port"),
                    inbound.get("remark", "Server"),
                    stream_settings
                )
            elif protocol.lower() == "vmess":
                return self._generate_vmess_config(
                    client.get("id"),
                    inbound.get("port"),
                    inbound.get("remark", "Server"),
                    stream_settings
                )
            elif protocol.lower() == "trojan":
                return self._generate_trojan_config(
                    client.get("password"),
                    inbound.get("port"),
                    inbound.get("remark", "Server"),
                    stream_settings
                )
            
            return None
        except Exception as e:
            logger.error(f"Ошибка получения конфигурации: {e}", exc_info=True)
            return None
    
    def _generate_vless_config(self, uuid: str, port: int, remark: str, stream_settings: dict) -> str:
        """Генерация VLESS конфигурации"""
        network = stream_settings.get("network", "tcp")
        security = stream_settings.get("security", "none")
        host = stream_settings.get("wsSettings", {}).get("headers", {}).get("Host", "")
        path = stream_settings.get("wsSettings", {}).get("path", "/")
        
        # Получаем IP сервера из base_url или используем домен
        server = self.base_url.split("://")[1].split(":")[0] if "://" in self.base_url else "your-server.com"
        
        # Формируем VLESS ссылку
        config = f"vless://{uuid}@{server}:{port}?type={network}&security={security}"
        
        # Обработка Reality параметров
        if security == "reality":
            reality_settings = stream_settings.get("realitySettings", {})
            reality_config = reality_settings.get("settings", {})
            
            # Public Key (pbk) - обязательный параметр для Reality
            public_key = reality_config.get("publicKey", "")
            if public_key:
                config += f"&pbk={public_key}"
            
            # Fingerprint (fp) - отпечаток сертификата
            fingerprint = reality_config.get("fingerprint", "chrome")
            if fingerprint:
                config += f"&fp={fingerprint}"
            
            # Server Name (sni) - имя сервера для TLS handshake
            server_name = reality_config.get("serverName", "")
            if not server_name:
                # Если serverName не указан, используем первый из serverNames
                server_names = reality_settings.get("serverNames", [])
                if server_names:
                    server_name = server_names[0]
            
            if server_name:
                config += f"&sni={server_name}"
            
            # Short ID (sid) - короткий идентификатор
            short_ids = reality_settings.get("shortIds", [])
            if short_ids:
                # Используем первый доступный shortId
                short_id = short_ids[0] if isinstance(short_ids[0], str) else str(short_ids[0])
                config += f"&sid={short_id}"
            
            # SpiderX (spx) - путь для обхода проверки
            spider_x = reality_config.get("spiderX", "/")
            if spider_x:
                config += f"&spx={spider_x}"
        
        # Обработка WebSocket параметров
        if network == "ws":
            if host:
                config += f"&host={host}"
            if path:
                config += f"&path={path}"
        
        # Добавляем remark в конец
        config += f"#{remark}"
        
        return config
    
    def _generate_vmess_config(self, uuid: str, port: int, remark: str, stream_settings: dict) -> str:
        """Генерация VMESS конфигурации"""
        import base64
        
        network = stream_settings.get("network", "tcp")
        security = stream_settings.get("security", "none")
        host = stream_settings.get("wsSettings", {}).get("headers", {}).get("Host", "")
        path = stream_settings.get("wsSettings", {}).get("path", "/")
        
        server = self.base_url.split("://")[1].split(":")[0] if "://" in self.base_url else "your-server.com"
        
        vmess_config = {
            "v": "2",
            "ps": remark,
            "add": server,
            "port": str(port),
            "id": uuid,
            "aid": "0",
            "net": network,
            "type": "none",
            "host": host,
            "path": path,
            "tls": security if security in ["tls", "reality"] else "none"
        }
        
        config_json = json.dumps(vmess_config, separators=(',', ':'))
        config_base64 = base64.b64encode(config_json.encode()).decode()
        
        return f"vmess://{config_base64}"
    
    def _generate_trojan_config(self, password: str, port: int, remark: str, stream_settings: dict) -> str:
        """Генерация Trojan конфигурации"""
        security = stream_settings.get("security", "tls")
        host = stream_settings.get("wsSettings", {}).get("headers", {}).get("Host", "")
        path = stream_settings.get("wsSettings", {}).get("path", "/")
        
        server = self.base_url.split("://")[1].split(":")[0] if "://" in self.base_url else "your-server.com"
        
        config = f"trojan://{password}@{server}:{port}?security={security}"
        
        if host:
            config += f"&host={host}&path={path}"
        
        config += f"#{remark}"
        
        return config
    
    def get_user_configs(self, inbound_id: int, base_username: str) -> List[Dict[str, Any]]:
        """Получить список всех конфигов пользователя (username, username_1, username_2, ...)"""
        try:
            self._ensure_authenticated()
        except Exception as e:
            logger.error(f"Ошибка авторизации: {e}")
            return []
        
        try:
            # Получаем список inbounds
            inbounds = self.get_inbounds()
            inbound = next((i for i in inbounds if i.get("id") == inbound_id), None)
            
            if not inbound:
                logger.warning(f"Inbound {inbound_id} не найден")
                return []
            
            # Парсим settings
            settings_str = inbound.get("settings", "{}")
            settings = json.loads(settings_str) if settings_str else {}
            
            # Получаем существующих клиентов
            clients = settings.get("clients", [])
            
            # Находим все конфиги пользователя
            user_configs = []
            for client in clients:
                client_email = client.get("email", "")
                if client_email == base_username:
                    # Базовый email без номера
                    user_configs.append({
                        "email": client_email,
                        "number": 0,
                        "client": client
                    })
                elif client_email.startswith(f"{base_username}_"):
                    # Email с номером (username_N)
                    suffix = client_email[len(f"{base_username}_"):]
                    try:
                        number = int(suffix)
                        user_configs.append({
                            "email": client_email,
                            "number": number,
                            "client": client
                        })
                    except ValueError:
                        # Если не число, игнорируем
                        pass
            
            # Сортируем по номеру
            user_configs.sort(key=lambda x: x["number"])
            logger.info(f"Найдено конфигов для {base_username}: {len(user_configs)}")
            return user_configs
            
        except Exception as e:
            logger.error(f"Ошибка получения конфигов пользователя: {e}", exc_info=True)
            return []
    
    def get_next_available_email(self, inbound_id: int, base_username: str, excluded_emails: Optional[List[str]] = None) -> str:
        """Получить следующий доступный email с итерирующимся номером для пользователя
        
        Если есть конфиги username, username_1, username_2, то вернет username_3
        Если нет конфигов, вернет username_1 (первый конфиг)
        
        Args:
            inbound_id: ID inbound
            base_username: Базовое имя пользователя
            excluded_emails: Список email, которые нужно исключить из поиска (например, уже попробованные)
        """
        if excluded_emails is None:
            excluded_emails = []
        
        try:
            self._ensure_authenticated()
        except Exception as e:
            logger.error(f"Ошибка авторизации: {e}")
            return f"{base_username}_1"  # Возвращаем дефолт при ошибке
        
        try:
            # Получаем список inbounds
            inbounds = self.get_inbounds()
            inbound = next((i for i in inbounds if i.get("id") == inbound_id), None)
            
            if not inbound:
                logger.warning(f"Inbound {inbound_id} не найден, используем дефолтный email")
                return f"{base_username}_1"
            
            # Парсим settings
            settings_str = inbound.get("settings", "{}")
            settings = json.loads(settings_str) if settings_str else {}
            
            # Получаем существующих клиентов
            clients = settings.get("clients", [])
            logger.info(f"Найдено клиентов в inbound {inbound_id}: {len(clients)}")
            
            # Находим все email, которые начинаются с base_username
            # Проверяем точное совпадение (username) и с номерами (username_1, username_2, ...)
            used_numbers = set()
            has_base_email = False
            
            # Логируем клиентов с нужным префиксом
            matching_clients = [c.get("email", "") for c in clients if c.get("email", "").startswith(base_username)]
            if matching_clients:
                logger.info(f"Найдены клиенты с префиксом {base_username}: {matching_clients}")
            
            # Сначала обрабатываем excluded_emails - они должны быть исключены независимо от того,
            # существуют ли они в x-ui (например, если попытка создания не удалась)
            logger.info(f"Обработка excluded_emails для {base_username}: {excluded_emails}")
            for excluded_email in excluded_emails:
                if excluded_email == base_username:
                    has_base_email = True
                    used_numbers.add(0)
                    logger.info(f"Исключен базовый email {excluded_email} (номер 0)")
                elif excluded_email.startswith(f"{base_username}_"):
                    suffix = excluded_email[len(f"{base_username}_"):]
                    try:
                        number = int(suffix)
                        used_numbers.add(number)
                        logger.info(f"Исключен email {excluded_email} (номер {number}) из списка доступных")
                    except ValueError:
                        logger.warning(f"Не удалось извлечь номер из excluded_email: {excluded_email}")
                        pass
            
            # Теперь обрабатываем существующих клиентов
            for client in clients:
                client_email = client.get("email", "")
                
                # Пропускаем email, которые уже в excluded_emails (чтобы не дублировать)
                if client_email in excluded_emails:
                    continue
                
                if client_email == base_username:
                    has_base_email = True
                    used_numbers.add(0)  # Базовый email считаем как номер 0
                elif client_email.startswith(f"{base_username}_"):
                    # Извлекаем номер из email вида username_N
                    suffix = client_email[len(f"{base_username}_"):]
                    try:
                        number = int(suffix)
                        used_numbers.add(number)
                    except ValueError:
                        # Если не число, игнорируем
                        pass
            
            # Находим следующий доступный номер
            logger.info(f"Используемые номера для {base_username}: {sorted(used_numbers)}")
            if not has_base_email and 0 not in used_numbers:
                # Если базового email нет, используем его (но пользователь хочет с номерами, так что начинаем с 1)
                # Но для совместимости, если есть старые конфиги без номера, пропускаем их
                next_number = 1
            else:
                # Ищем минимальный свободный номер, начиная с 1
                next_number = 1
                while next_number in used_numbers:
                    logger.debug(f"Номер {next_number} занят, пробуем следующий...")
                    next_number += 1
            
            next_email = f"{base_username}_{next_number}"
            logger.info(f"Следующий доступный email для {base_username}: {next_email} (исключено: {len(excluded_emails)} email, использованные номера: {sorted(used_numbers)})")
            return next_email
            
        except Exception as e:
            logger.error(f"Ошибка определения следующего email: {e}", exc_info=True)
            return f"{base_username}_1"  # Возвращаем дефолт при ошибке
    
    def get_client_config_by_email(self, email: str, inbound_id: Optional[int] = None) -> Optional[str]:
        """Получить конфигурацию клиента по email"""
        try:
            self._ensure_authenticated()
        except Exception as e:
            logger.error(f"Ошибка авторизации: {e}")
            return None
        
        try:
            # Используем данные из списка inbounds - там уже есть вся информация
            # Источники: https://github.com/MHSanaei/3x-ui
            inbounds = self.get_inbounds()
            
            if inbound_id is None:
                # Ищем во всех inbounds
                for inbound in inbounds:
                    settings_str = inbound.get("settings", "{}")
                    settings = json.loads(settings_str) if settings_str else {}
                    clients = settings.get("clients", [])
                    if any(c.get("email") == email for c in clients):
                        inbound_id = inbound.get("id")
                        break
                
                if inbound_id is None:
                    logger.warning(f"Клиент с email {email} не найден ни в одном inbound")
                    return None
            
            # Находим inbound по ID
            inbound = next((i for i in inbounds if i.get("id") == inbound_id), None)
            if not inbound:
                logger.error(f"Inbound {inbound_id} не найден в списке")
                return None
            
            # Определяем протокол из inbound
            protocol = inbound.get("protocol", "vless").lower()
            return self.get_client_config(inbound_id, email, protocol)
        except Exception as e:
            logger.error(f"Ошибка получения конфигурации по email: {e}", exc_info=True)
            return None
    
    def add_client_to_inbound(self, inbound_id: int, email: str, 
                              uuid: Optional[str] = None, 
                              expire_time: Optional[int] = None,
                              total_traffic: Optional[int] = None) -> bool:
        """Добавить клиента к inbound"""
        try:
            self._ensure_authenticated()
        except Exception as e:
            logger.error(f"Ошибка авторизации: {e}")
            return False
        
        try:
            logger.info(f"Добавление клиента {email} к inbound {inbound_id}")
            
            # Получаем список inbounds - там уже есть вся информация
            # Источники: https://github.com/MHSanaei/3x-ui
            # Postman коллекция: https://www.postman.com/hsanaei/3x-ui/collection/q1l5l0u/3x-ui
            inbounds = self.get_inbounds()
            inbound = next((i for i in inbounds if i.get("id") == inbound_id), None)
            
            if not inbound:
                logger.error(f"Inbound {inbound_id} не найден в списке")
                return False
            
            # Парсим settings
            settings_str = inbound.get("settings", "{}")
            settings = json.loads(settings_str) if settings_str else {}
            
            # Получаем существующих клиентов
            clients = settings.get("clients", [])
            
            # Проверяем, не существует ли уже клиент с таким email
            if any(c.get("email") == email for c in clients):
                logger.warning(f"Клиент с email {email} уже существует")
                return False  # Клиент уже существует
            
            # Генерируем UUID если не указан
            import uuid as uuid_lib
            if not uuid:
                uuid = str(uuid_lib.uuid4())
            
            # Генерируем subId
            import random
            import string
            sub_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=16))
            
            # Создаем нового клиента согласно документации 3x-ui
            # Источники: https://postman.com/hsanaei/3x-ui/collection/q1l5l0u/3x-ui
            new_client = {
                "id": uuid,
                "flow": "",
                "email": email,
                "limitIp": 0,
                "totalGB": total_traffic if total_traffic else 0,
                "expiryTime": expire_time if expire_time else 0,
                "enable": True,
                "tgId": "",
                "subId": sub_id,
                "comment": "",
                "reset": 0
            }
            
            # Используем правильный endpoint для добавления клиента в 3x-ui
            # Источники: https://postman.com/hsanaei/3x-ui/collection/q1l5l0u/3x-ui
            # Endpoint: /panel/api/inbounds/addClient
            add_client_urls = [
                f"{self.base_url}/panel/api/inbounds/addClient",
                f"{self.base_url}/panel/panel/api/inbounds/addClient",
                f"{self.base_url}/panel/panel/api/inbound/addClient",
                f"{self.base_url}/panel/api/inbound/addClient",
            ]
            
            # Подготавливаем данные для добавления клиента
            add_client_data = {
                "id": inbound_id,
                "settings": json.dumps({
                    "clients": [new_client]
                })
            }
            
            add_client_response = None
            for test_url in add_client_urls:
                logger.info(f"Попытка добавления клиента через {test_url}")
                try:
                    test_response = self.session.post(
                        test_url,
                        json=add_client_data,
                        headers={
                            "Accept": "application/json",
                            "Content-Type": "application/json"
                        },
                        timeout=10
                    )
                    logger.info(f"Ответ добавления клиента: статус {test_response.status_code}")
                    
                    if test_response.status_code == 200:
                        try:
                            result = test_response.json()
                            if result.get("success"):
                                logger.info(f"✅ Клиент {email} успешно добавлен к inbound {inbound_id} через {test_url}")
                                return True
                            else:
                                logger.warning(f"API вернул success=False для {test_url}: {result.get('msg', 'Unknown error')}")
                        except json.JSONDecodeError:
                            logger.warning(f"Ошибка парсинга JSON для {test_url}")
                    else:
                        logger.warning(f"HTTP ошибка для {test_url}: {test_response.status_code}, текст: {test_response.text[:200]}")
                except Exception as e:
                    logger.warning(f"Ошибка при запросе {test_url}: {e}")
            
            # Если addClient не сработал, пробуем через update
            logger.info("Пробуем добавить клиента через update inbound")
            clients.append(new_client)
            settings["clients"] = clients
            
            # Подготавливаем данные для обновления
            update_data = {
                "id": inbound_id,
                "settings": json.dumps(settings),
                "streamSettings": inbound.get("streamSettings", "{}"),
                "sniffing": inbound.get("sniffing", "{}"),
                "remark": inbound.get("remark", ""),
                "protocol": inbound.get("protocol", ""),
                "port": inbound.get("port", 0),
                "listen": inbound.get("listen", ""),
                "tag": inbound.get("tag", ""),
                "up": inbound.get("up", 0),
                "down": inbound.get("down", 0)
            }
            
            # Обновляем inbound - пробуем разные варианты URL для 3x-ui
            update_urls_to_try = [
                f"{self.base_url}/panel/api/inbound/update/{inbound_id}",
                f"{self.base_url}/panel/panel/api/inbound/update/{inbound_id}",
                f"{self.base_url}/panel/panel/inbound/update/{inbound_id}",
                f"{self.base_url}/panel/inbound/update/{inbound_id}",
            ]
            
            for test_url in update_urls_to_try:
                logger.info(f"Попытка обновления inbound {inbound_id}: {test_url}")
                try:
                    test_response = self.session.post(
                        test_url,
                        json=update_data,
                        headers={
                            "Accept": "application/json",
                            "Content-Type": "application/json"
                        },
                        timeout=10
                    )
                    logger.info(f"Ответ обновления inbound: статус {test_response.status_code}")
                    
                    if test_response.status_code == 200:
                        try:
                            update_result = test_response.json()
                            success = update_result.get("success", False)
                            if success:
                                logger.info(f"✅ Клиент {email} успешно добавлен к inbound {inbound_id} через update")
                                return True
                            else:
                                logger.warning(f"API вернул success=False для {test_url}: {update_result.get('msg', 'Unknown error')}")
                        except json.JSONDecodeError as e:
                            logger.warning(f"Ошибка парсинга JSON для {test_url}: {e}")
                    else:
                        logger.warning(f"HTTP ошибка для {test_url}: {test_response.status_code}, текст: {test_response.text[:200]}")
                except Exception as e:
                    logger.warning(f"Ошибка при запросе {test_url}: {e}")
            
            logger.error("Все варианты URL для добавления клиента не сработали")
            return False
        except Exception as e:
            logger.error(f"Ошибка добавления клиента: {e}", exc_info=True)
            return False
    
    def update_client_expiry(self, inbound_id: int, email: str, add_days: int = 31) -> bool:
        """Обновить срок действия клиента (продлить на указанное количество дней)"""
        try:
            self._ensure_authenticated()
        except Exception as e:
            logger.error(f"Ошибка авторизации: {e}")
            return False
        
        try:
            logger.info(f"Продление конфига для {email} на {add_days} дней в inbound {inbound_id}")
            
            # Получаем список inbounds
            inbounds = self.get_inbounds()
            inbound = next((i for i in inbounds if i.get("id") == inbound_id), None)
            
            if not inbound:
                logger.error(f"Inbound {inbound_id} не найден в списке")
                return False
            
            # Парсим settings
            settings_str = inbound.get("settings", "{}")
            settings = json.loads(settings_str) if settings_str else {}
            
            # Получаем существующих клиентов
            clients = settings.get("clients", [])
            
            # Находим клиента по email
            client = next((c for c in clients if c.get("email") == email), None)
            
            if not client:
                logger.error(f"Клиент с email {email} не найден в inbound {inbound_id}")
                return False
            
            # Вычисляем новый срок действия
            import time
            current_time = int(time.time() * 1000)  # Текущее время в миллисекундах
            current_expiry = client.get("expiryTime", 0)
            
            # Если срок действия уже истек или не установлен, устанавливаем с текущего момента
            if current_expiry == 0 or current_expiry < current_time:
                new_expiry = current_time + (add_days * 24 * 60 * 60 * 1000)
            else:
                # Продлеваем существующий срок
                new_expiry = current_expiry + (add_days * 24 * 60 * 60 * 1000)
            
            # Обновляем expireTime клиента
            client["expiryTime"] = new_expiry
            
            # Обновляем settings
            settings["clients"] = clients
            updated_settings = json.dumps(settings, indent=2)
            
            # Подготавливаем данные для обновления inbound
            update_data = {
                "id": inbound_id,
                "up": inbound.get("up", 0),
                "down": inbound.get("down", 0),
                "total": inbound.get("total", 0),
                "remark": inbound.get("remark", ""),
                "enable": inbound.get("enable", True),
                "expiryTime": inbound.get("expiryTime", 0),
                "listen": inbound.get("listen", ""),
                "port": inbound.get("port", 0),
                "protocol": inbound.get("protocol", "vless"),
                "settings": updated_settings,
                "streamSettings": inbound.get("streamSettings", "{}"),
                "sniffing": inbound.get("sniffing", "{}"),
                "tag": inbound.get("tag", "")
            }
            
            # Обновляем inbound - пробуем разные варианты URL для 3x-ui
            # Используем те же пути, что и для добавления клиента, но для обновления
            update_urls_to_try = [
                # Варианты с /inbounds/ (с 's') - как в addClient и get_inbounds
                f"{self.base_url}/panel/api/inbounds/update/{inbound_id}",
                f"{self.base_url}/panel/panel/api/inbounds/update/{inbound_id}",
                # Варианты с /inbound/ (без 's')
                f"{self.base_url}/panel/api/inbound/update/{inbound_id}",
                f"{self.base_url}/panel/panel/api/inbound/update/{inbound_id}",
                # Варианты без /api/
                f"{self.base_url}/panel/panel/inbound/update/{inbound_id}",
                f"{self.base_url}/panel/inbound/update/{inbound_id}",
            ]
            
            for test_url in update_urls_to_try:
                logger.info(f"Попытка обновления клиента через {test_url}")
                try:
                    test_response = self.session.post(
                        test_url,
                        json=update_data,
                        headers={
                            "Accept": "application/json",
                            "Content-Type": "application/json"
                        },
                        timeout=10
                    )
                    logger.info(f"Ответ обновления клиента: статус {test_response.status_code}")
                    
                    if test_response.status_code == 200:
                        try:
                            result = test_response.json()
                            if result.get("success"):
                                from datetime import datetime
                                new_expiry_date = datetime.fromtimestamp(new_expiry / 1000)
                                logger.info(f"✅ Срок действия конфига для {email} продлен до {new_expiry_date.strftime('%Y-%m-%d %H:%M')}")
                                return True
                            else:
                                logger.warning(f"API вернул success=False для {test_url}: {result.get('msg', 'Unknown error')}")
                        except json.JSONDecodeError as e:
                            logger.warning(f"Ошибка парсинга JSON для {test_url}: {e}")
                    else:
                        logger.warning(f"HTTP ошибка для {test_url}: {test_response.status_code}, текст: {test_response.text[:200]}")
                except Exception as e:
                    logger.warning(f"Ошибка при запросе {test_url}: {e}")
            
            logger.error("Все варианты URL для обновления клиента не сработали")
            return False
        except Exception as e:
            logger.error(f"Ошибка обновления срока действия клиента: {e}", exc_info=True)
            return False

