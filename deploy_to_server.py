#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для развертывания на сервере через SSH
"""
import paramiko
import sys
import os

# Устанавливаем UTF-8 для Windows
if sys.platform == 'win32':
    os.system('chcp 65001 >nul 2>&1')
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

SERVER_IP = "103.113.71.160"
SERVER_USER = "root"
SERVER_PASS = "j926kPIY2M2A"

def execute_remote_commands():
    """Выполнение команд на удаленном сервере"""
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        print(f"Подключение к {SERVER_USER}@{SERVER_IP}...")
        ssh.connect(SERVER_IP, username=SERVER_USER, password=SERVER_PASS, timeout=10)
        print("Подключено!")
        
        # Выполняем все команды в одной сессии
        print("\nВыполняю команды на сервере...")
        commands = """
cd ~/x-ui-bot && \
echo 'Получаю обновления из git...' && \
git pull origin main && \
echo 'Устанавливаю зависимости...' && \
pip3 install -r requirements.txt --upgrade && \
echo 'Проверяю наличие config.py...' && \
[ ! -f config.py ] && cp config.py.example config.py || echo 'config.py уже существует' && \
echo 'Перезапускаю сервис...' && \
systemctl restart xui-bot && \
echo 'Проверяю статус...' && \
systemctl status xui-bot --no-pager -l | head -20 && \
echo 'Развертывание завершено!'
"""
        
        stdin, stdout, stderr = ssh.exec_command(commands)
        output = stdout.read().decode('utf-8', errors='ignore')
        errors = stderr.read().decode('utf-8', errors='ignore')
        
        if output:
            print(output)
        if errors:
            print(f"Предупреждения/ошибки: {errors}")
        
        # Проверяем логи
        print("\nПоследние логи:")
        stdin, stdout, stderr = ssh.exec_command("journalctl -u xui-bot -n 20 --no-pager")
        print(stdout.read().decode('utf-8', errors='ignore'))
        
        ssh.close()
        print("\nГотово!")
        
    except Exception as e:
        print(f"Ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    execute_remote_commands()

