"""
Модуль для работы с x-ui API
"""
import requests
import json
from typing import Optional, Dict, List, Any
from config import XUI_BASE_URL, XUI_USERNAME, XUI_PASSWORD


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
            login_url = f"{self.base_url}/login"
            response = self.session.post(
                login_url,
                json={
                    "username": self.username,
                    "password": self.password
                },
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    self.token = data.get("data", {}).get("token")
                    if self.token:
                        self.session.headers.update({
                            "Authorization": f"Bearer {self.token}"
                        })
                    return True
            return False
        except Exception as e:
            print(f"Ошибка авторизации: {e}")
            return False
    
    def _ensure_authenticated(self):
        """Проверка и обновление токена при необходимости"""
        if not self.token:
            if not self._login():
                raise Exception("Не удалось авторизоваться в x-ui")
    
    def get_inbounds(self) -> List[Dict[str, Any]]:
        """Получить список всех inbounds"""
        self._ensure_authenticated()
        
        try:
            url = f"{self.base_url}/panel/inbound/list"
            response = self.session.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    return data.get("obj", [])
            return []
        except Exception as e:
            print(f"Ошибка получения inbounds: {e}")
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
                    clients = inbound.get("clients", [])
                    return clients
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

