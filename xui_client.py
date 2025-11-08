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
            login_url = f"{self.base_url}/panel/login"
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
                        logger.error(f"Авторизация не удалась: {data.get('msg', 'Unknown error')}")
                except json.JSONDecodeError as e:
                    logger.error(f"Ошибка парсинга JSON ответа: {e}, текст: {response.text[:200]}")
            else:
                logger.error(f"HTTP ошибка авторизации: {response.status_code}, текст: {response.text[:200]}")
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
            url = f"{self.base_url}/panel/inbound/list"
            logger.info(f"Запрос списка inbounds: {url}")
            
            response = self.session.get(url, timeout=10)
            logger.info(f"Ответ получения inbounds: статус {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    logger.info(f"Ответ API: success={data.get('success')}, obj type={type(data.get('obj'))}")
                    
                    if data.get("success"):
                        inbounds = data.get("obj", [])
                        logger.info(f"Получено inbounds: {len(inbounds) if inbounds else 0}")
                        if inbounds:
                            logger.info(f"Первый inbound: {inbounds[0] if inbounds else 'None'}")
                        return inbounds if inbounds else []
                    else:
                        error_msg = data.get('msg', 'Unknown error')
                        logger.error(f"Ошибка API: {error_msg}")
                except json.JSONDecodeError as e:
                    logger.error(f"Ошибка парсинга JSON: {e}, текст: {response.text[:500]}")
            else:
                logger.error(f"HTTP ошибка: {response.status_code}, ответ: {response.text[:500]}")
            return []
        except Exception as e:
            logger.error(f"Ошибка получения inbounds: {e}", exc_info=True)
            return []
    
    def get_inbound_clients(self, inbound_id: int) -> List[Dict[str, Any]]:
        """Получить список клиентов для конкретного inbound"""
        self._ensure_authenticated()
        
        try:
            url = f"{self.base_url}/panel/inbound/get/{inbound_id}"
            response = self.session.get(url, timeout=10)
            
            if response.status_code == 200:
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
                            except:
                                pass
                    
                    return clients if clients else []
            return []
        except Exception as e:
            print(f"Ошибка получения клиентов: {e}")
            return []
    
    def get_client_config(self, inbound_id: int, email: str, protocol: str = "vless") -> Optional[str]:
        """Получить конфигурацию клиента для подключения"""
        self._ensure_authenticated()
        
        try:
            url = f"{self.base_url}/panel/inbound/getClientTraffics/{email}"
            response = self.session.get(url, timeout=10)
            
            # Получаем детали inbound
            inbound_url = f"{self.base_url}/panel/inbound/get/{inbound_id}"
            inbound_response = self.session.get(inbound_url, timeout=10)
            
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
        
        # Определяем протокол из inbound
        inbound_url = f"{self.base_url}/panel/inbound/get/{inbound_id}"
        response = self.session.get(inbound_url, timeout=10)
        
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
        self._ensure_authenticated()
        
        try:
            # Получаем текущий inbound
            url = f"{self.base_url}/panel/inbound/get/{inbound_id}"
            response = self.session.get(url, timeout=10)
            
            if response.status_code != 200:
                return False
            
            data = response.json()
            if not data.get("success"):
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
            
            # Обновляем inbound
            update_url = f"{self.base_url}/panel/inbound/update/{inbound_id}"
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
            
            update_response = self.session.post(
                update_url,
                json=update_data,
                timeout=10
            )
            
            if update_response.status_code == 200:
                update_data = update_response.json()
                return update_data.get("success", False)
            
            return False
        except Exception as e:
            print(f"Ошибка добавления клиента: {e}")
            return False

