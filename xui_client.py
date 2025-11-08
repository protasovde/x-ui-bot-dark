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
            # Пробуем разные варианты URL для 3x-ui
            # Список inbounds работает через /panel/panel/api/inbounds/list
            # Для получения конкретного inbound пробуем разные варианты
            urls_to_try = [
                # Варианты с /get/
                (f"{self.base_url}/panel/panel/api/inbound/get/{inbound_id}", "GET"),
                (f"{self.base_url}/panel/panel/api/inbound/get/{inbound_id}", "POST"),
                (f"{self.base_url}/panel/api/inbound/get/{inbound_id}", "GET"),
                (f"{self.base_url}/panel/api/inbound/get/{inbound_id}", "POST"),
                (f"{self.base_url}/panel/panel/inbound/get/{inbound_id}", "GET"),
                (f"{self.base_url}/panel/panel/inbound/get/{inbound_id}", "POST"),
                (f"{self.base_url}/panel/inbound/get/{inbound_id}", "GET"),
                (f"{self.base_url}/panel/inbound/get/{inbound_id}", "POST"),
                # Варианты без /get/ (прямой доступ по ID)
                (f"{self.base_url}/panel/panel/api/inbound/{inbound_id}", "GET"),
                (f"{self.base_url}/panel/panel/api/inbound/{inbound_id}", "POST"),
                (f"{self.base_url}/panel/api/inbound/{inbound_id}", "GET"),
                (f"{self.base_url}/panel/api/inbound/{inbound_id}", "POST"),
                # Старые варианты для совместимости
                (f"{self.base_url}/xui/inbound/get/{inbound_id}", "GET"),
                (f"{self.base_url}/api/inbound/get/{inbound_id}", "GET"),
                (f"{self.base_url}/inbound/get/{inbound_id}", "GET"),
            ]
            
            response = None
            for url, method in urls_to_try:
                logger.info(f"Попытка запроса клиентов для inbound {inbound_id}: {method} {url}")
                try:
                    if method == "GET":
                        test_response = self.session.get(url, timeout=10)
                    else:
                        test_response = self.session.post(url, json={}, timeout=10)
                    
                    logger.info(f"Ответ получения клиентов: статус {test_response.status_code}")
                    
                    if test_response.status_code == 200:
                        # Проверяем, что это JSON, а не HTML
                        content_type = test_response.headers.get('Content-Type', '').lower()
                        if 'application/json' in content_type:
                            response = test_response
                            break
                        else:
                            logger.debug(f"Получен не-JSON ответ для {method} {url}, пробуем следующий вариант")
                    else:
                        logger.warning(f"HTTP ошибка для {method} {url}: {test_response.status_code}")
                except Exception as e:
                    logger.warning(f"Ошибка при запросе {method} {url}: {e}")
            
            if not response:
                logger.error("Все варианты URL для получения клиентов не сработали")
                return []
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    if data.get("success"):
                        inbound = data.get("obj", {})
                        
                        # Клиенты могут быть в поле "clients" или в "settings" как JSON строка
                        clients = inbound.get("clients", [])
                        
                        # Если клиентов нет, пробуем извлечь из settings
                        if not clients:
                            settings_str = inbound.get("settings", "")
                            if settings_str:
                                try:
                                    settings = json.loads(settings_str)
                                    clients = settings.get("clients", [])
                                    logger.info(f"Клиенты найдены в settings: {len(clients)}")
                                except json.JSONDecodeError as e:
                                    logger.error(f"Ошибка парсинга settings: {e}")
                        
                        logger.info(f"Получено клиентов: {len(clients) if clients else 0}")
                        return clients if clients else []
                    else:
                        logger.error(f"Ошибка API: {data.get('msg', 'Unknown error')}")
                except json.JSONDecodeError as e:
                    logger.error(f"Ошибка парсинга JSON: {e}, текст: {response.text[:500]}")
            else:
                logger.error(f"HTTP ошибка: {response.status_code}, ответ: {response.text[:500]}")
            return []
        except Exception as e:
            logger.error(f"Ошибка получения клиентов: {e}", exc_info=True)
            return []
    
    def get_client_config(self, inbound_id: int, email: str, protocol: str = "vless") -> Optional[str]:
        """Получить конфигурацию клиента для подключения"""
        self._ensure_authenticated()
        
        try:
            # Получаем детали inbound - пробуем разные варианты URL
            urls_to_try = [
                f"{self.base_url}/xui/inbound/get/{inbound_id}",
                f"{self.base_url}/panel/inbound/get/{inbound_id}",
                f"{self.base_url}/api/inbound/get/{inbound_id}",
                f"{self.base_url}/inbound/get/{inbound_id}"
            ]
            
            inbound_response = None
            for url in urls_to_try:
                test_response = self.session.get(url, timeout=10)
                if test_response.status_code == 200:
                    inbound_response = test_response
                    break
            
            if not inbound_response:
                return None
            
            if inbound_response.status_code == 200:
                inbound_data = inbound_response.json()
                if inbound_data.get("success"):
                    inbound = inbound_data.get("obj", {})
                    settings = json.loads(inbound.get("settings", "{}"))
                    stream_settings = json.loads(inbound.get("streamSettings", "{}"))
                    
                    # Получаем клиента
                    clients = settings.get("clients", [])
                    client = next((c for c in clients if c.get("email") == email), None)
                    
                    if not client:
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
            print(f"Ошибка получения конфигурации: {e}")
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
        
        if network == "ws":
            config += f"&host={host}&path={path}"
        
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
    
    def get_client_config_by_email(self, email: str, inbound_id: Optional[int] = None) -> Optional[str]:
        """Получить конфигурацию клиента по email"""
        if inbound_id is None:
            # Ищем во всех inbounds
            inbounds = self.get_inbounds()
            for inbound in inbounds:
                clients = self.get_inbound_clients(inbound.get("id"))
                if any(c.get("email") == email for c in clients):
                    inbound_id = inbound.get("id")
                    break
            
            if inbound_id is None:
                return None
        
            # Определяем протокол из inbound - пробуем разные варианты URL
            urls_to_try = [
                f"{self.base_url}/panel/panel/inbound/get/{inbound_id}",
                f"{self.base_url}/panel/inbound/get/{inbound_id}",
                f"{self.base_url}/xui/inbound/get/{inbound_id}",
                f"{self.base_url}/api/inbound/get/{inbound_id}",
                f"{self.base_url}/inbound/get/{inbound_id}"
            ]
            
            response = None
            for url in urls_to_try:
                test_response = self.session.get(url, timeout=10)
                if test_response.status_code == 200:
                    response = test_response
                    break
            
            if not response:
                return None
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                inbound = data.get("obj", {})
                protocol = inbound.get("protocol", "vless").lower()
                return self.get_client_config(inbound_id, email, protocol)
        
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
            # Получаем текущий inbound
            # Получаем текущий inbound - пробуем разные варианты URL для 3x-ui
            # Источники: https://github.com/MHSanaei/3x-ui
            # Список inbounds работает через /panel/panel/api/inbounds/list
            # Для получения конкретного inbound пробуем разные варианты
            urls_to_try = [
                # Варианты с /get/
                (f"{self.base_url}/panel/panel/api/inbound/get/{inbound_id}", "GET"),
                (f"{self.base_url}/panel/panel/api/inbound/get/{inbound_id}", "POST"),
                (f"{self.base_url}/panel/api/inbound/get/{inbound_id}", "GET"),
                (f"{self.base_url}/panel/api/inbound/get/{inbound_id}", "POST"),
                (f"{self.base_url}/panel/panel/inbound/get/{inbound_id}", "GET"),
                (f"{self.base_url}/panel/panel/inbound/get/{inbound_id}", "POST"),
                (f"{self.base_url}/panel/inbound/get/{inbound_id}", "GET"),
                (f"{self.base_url}/panel/inbound/get/{inbound_id}", "POST"),
                # Варианты без /get/ (прямой доступ по ID)
                (f"{self.base_url}/panel/panel/api/inbound/{inbound_id}", "GET"),
                (f"{self.base_url}/panel/panel/api/inbound/{inbound_id}", "POST"),
                (f"{self.base_url}/panel/api/inbound/{inbound_id}", "GET"),
                (f"{self.base_url}/panel/api/inbound/{inbound_id}", "POST"),
                # Старые варианты для совместимости
                (f"{self.base_url}/xui/inbound/get/{inbound_id}", "GET"),
                (f"{self.base_url}/api/inbound/get/{inbound_id}", "GET"),
                (f"{self.base_url}/inbound/get/{inbound_id}", "GET"),
            ]
            
            response = None
            for url, method in urls_to_try:
                logger.info(f"Попытка запроса inbound {inbound_id}: {method} {url}")
                try:
                    if method == "GET":
                        test_response = self.session.get(url, timeout=10)
                    else:
                        test_response = self.session.post(url, json={}, timeout=10)
                    
                    logger.info(f"Ответ получения inbound: статус {test_response.status_code}")
                    
                    if test_response.status_code == 200:
                        # Проверяем, что это JSON, а не HTML
                        content_type = test_response.headers.get('Content-Type', '').lower()
                        if 'application/json' in content_type:
                            response = test_response
                            break
                        else:
                            logger.debug(f"Получен не-JSON ответ для {method} {url}, пробуем следующий вариант")
                    else:
                        logger.warning(f"HTTP ошибка для {method} {url}: {test_response.status_code}")
                except Exception as e:
                    logger.warning(f"Ошибка при запросе {method} {url}: {e}")
            
            if not response:
                logger.error("Все варианты URL для получения inbound не сработали")
                return False
            
            if response.status_code != 200:
                logger.error(f"HTTP ошибка получения inbound: {response.status_code}, текст: {response.text[:500]}")
                return False
            
            try:
                data = response.json()
            except json.JSONDecodeError as e:
                logger.error(f"Ошибка парсинга JSON: {e}, текст: {response.text[:500]}")
                return False
            
            if not data.get("success"):
                logger.error(f"Ошибка API: {data.get('msg', 'Unknown error')}")
                return False
            
            inbound = data.get("obj", {})
            
            # Парсим settings
            settings_str = inbound.get("settings", "{}")
            settings = json.loads(settings_str) if settings_str else {}
            
            # Получаем существующих клиентов
            clients = settings.get("clients", [])
            
            # Проверяем, не существует ли уже клиент с таким email
            if any(c.get("email") == email for c in clients):
                return False  # Клиент уже существует
            
            # Генерируем UUID если не указан
            import uuid as uuid_lib
            if not uuid:
                uuid = str(uuid_lib.uuid4())
            
            # Создаем нового клиента
            new_client = {
                "id": uuid,
                "email": email,
                "limitIp": 0,
                "totalGB": total_traffic if total_traffic else 0,
                "expiryTime": expire_time if expire_time else 0,
                "enable": True,
                "tgId": "",
                "subId": ""
            }
            
            # Добавляем клиента в список
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
            # Источники: https://github.com/MHSanaei/3x-ui
            # Postman коллекция: https://www.postman.com/hsanaei/3x-ui/collection/q1l5l0u/3x-ui
            update_urls_to_try = [
                f"{self.base_url}/panel/panel/inbound/update/{inbound_id}",
                f"{self.base_url}/panel/panel/api/inbound/update/{inbound_id}",
                f"{self.base_url}/panel/api/inbound/update/{inbound_id}",
                f"{self.base_url}/panel/inbound/update/{inbound_id}",
                f"{self.base_url}/xui/inbound/update/{inbound_id}",
                f"{self.base_url}/api/inbound/update/{inbound_id}",
                f"{self.base_url}/inbound/update/{inbound_id}"
            ]
            
            update_url = None
            update_response = None
            
            for test_url in update_urls_to_try:
                logger.info(f"Попытка обновления inbound {inbound_id}: {test_url}")
                test_response = self.session.post(
                    test_url,
                    json=update_data,
                    timeout=10
                )
                logger.info(f"Ответ обновления inbound: статус {test_response.status_code}")
                
                if test_response.status_code == 200:
                    update_url = test_url
                    update_response = test_response
                    break
                else:
                    logger.warning(f"HTTP ошибка для {test_url}: {test_response.status_code}")
            
            if not update_response:
                logger.error("Все варианты URL для обновления inbound не сработали")
                return False
            
            logger.info(f"Обновление inbound {inbound_id}: {update_url}")
            
            if update_response.status_code == 200:
                try:
                    update_result = update_response.json()
                    success = update_result.get("success", False)
                    if success:
                        logger.info(f"Клиент {email} успешно добавлен к inbound {inbound_id}")
                    else:
                        logger.error(f"Ошибка обновления inbound: {update_result.get('msg', 'Unknown error')}")
                    return success
                except json.JSONDecodeError as e:
                    logger.error(f"Ошибка парсинга JSON ответа: {e}, текст: {update_response.text[:500]}")
            else:
                logger.error(f"HTTP ошибка обновления inbound: {update_response.status_code}, текст: {update_response.text[:500]}")
            
            return False
        except Exception as e:
            logger.error(f"Ошибка добавления клиента: {e}", exc_info=True)
            return False

