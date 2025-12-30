#!/usr/bin/env python3
"""
HTTP сервер для Arduino на Render.com
Простая версия с хранением в памяти
"""

import os
import json
import sqlite3
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import threading
import atexit

# ========== КОНФИГУРАЦИЯ ==========
app = Flask(__name__)
CORS(app)  # Разрешаем CORS для всех доменов

# На Render лучше использовать SQLite на постоянном диске,
# но для простоты будем хранить в памяти + файл для бэкапа
DB_PATH = '/tmp/arduino.db' if os.environ.get('RENDER') else 'arduino.db'
COMMANDS_FILE = 'commands.txt'

# Инициализация базы данных
def init_database():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sensor_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            temperature REAL,
            battery REAL,
            device_id TEXT DEFAULT 'arduino'
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS commands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            command TEXT,
            processed BOOLEAN DEFAULT 0
        )
    ''')
    
    # Создаём таблицу для логов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS server_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            level TEXT,
            message TEXT,
            ip TEXT
        )
    ''')
    
    conn.commit()
    conn.close()
    
    log_message("База данных инициализирована", "INFO")

# Логирование в базу данных
def log_message(message, level="INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}")
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO server_logs (level, message, ip) 
            VALUES (?, ?, ?)
        ''', (level, message, request.remote_addr if request else 'system'))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Ошибка логирования: {e}")

# ========== HTML ШАБЛОН ==========
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>🏠 Arduino Control - Render</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            color: white;
            padding: 20px;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
        }
        .card {
            background: rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 30px;
            margin: 20px 0;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
            border: 1px solid rgba(255, 255, 255, 0.2);
        }
        h1 { text-align: center; margin-bottom: 30px; }
        .status {
            display: flex;
            align-items: center;
            margin: 10px 0;
            padding: 10px;
            background: rgba(76, 175, 80, 0.2);
            border-radius: 10px;
        }
        .status-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: #4CAF50;
            margin-right: 10px;
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.5; }
            100% { opacity: 1; }
        }
        button {
            background: linear-gradient(135deg, #4CAF50 0%, #45a049 100%);
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 10px;
            cursor: pointer;
            font-size: 16px;
            margin: 5px;
            transition: all 0.3s;
        }
        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(0, 0, 0, 0.2);
        }
        button.off { background: linear-gradient(135deg, #f44336 0%, #d32f2f 100%); }
        .endpoint {
            background: rgba(0, 0, 0, 0.3);
            padding: 10px;
            border-radius: 8px;
            margin: 5px 0;
            font-family: monospace;
            font-size: 12px;
        }
        pre {
            background: rgba(0, 0, 0, 0.2);
            padding: 15px;
            border-radius: 8px;
            overflow-x: auto;
            margin-top: 15px;
            font-family: monospace;
        }
        .row {
            display: flex;
            flex-wrap: wrap;
            gap: 20px;
            margin-bottom: 20px;
        }
        .col {
            flex: 1;
            min-width: 300px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <h1>🏠 Arduino Control Panel</h1>
            <div class="status">
                <div class="status-dot"></div>
                <span>Сервер работает на Render.com</span>
            </div>
            <p><strong>URL для Arduino:</strong> <code>{{ server_url }}</code></p>
            <p><strong>База данных:</strong> SQLite (в памяти, данные временные)</p>
        </div>
        
        <div class="row">
            <div class="col">
                <div class="card">
                    <h2>⚡ Управление</h2>
                    <button onclick="sendCommand('PWR_ON')">Включить</button>
                    <button class="off" onclick="sendCommand('PWR_OFF')">Выключить</button>
                    <button onclick="sendCommand('GET_STATUS')">Статус</button>
                </div>
            </div>
            
            <div class="col">
                <div class="card">
                    <h2>📡 API Endpoints</h2>
                    <div class="endpoint">GET /report?temp=25.5&batt=12.3</div>
                    <div class="endpoint">GET /get_command</div>
                    <div class="endpoint">POST /command {"cmd": "..."}</div>
                    <div class="endpoint">GET /last_data</div>
                    <div class="endpoint">GET /stats</div>
                </div>
            </div>
        </div>
        
        <div class="card">
            <h2>📊 Последние данные</h2>
            <pre id="data">Загрузка...</pre>
            <button onclick="loadData()">Обновить</button>
        </div>
        
        <div class="card">
            <h2>⌨️ Ручная команда</h2>
            <input type="text" id="customCmd" placeholder="PWR_ON, PWR_OFF, GET_STATUS" 
                   style="width: 100%; padding: 12px; border-radius: 8px; border: 1px solid #ccc; margin-bottom: 10px;">
            <button onclick="sendCustomCommand()">Отправить</button>
        </div>
    </div>
    
    <script>
        const serverUrl = window.location.origin;
        
        async function sendCommand(cmd) {
            try {
                const response = await fetch(serverUrl + '/command', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ cmd: cmd })
                });
                if (response.ok) {
                    alert('✅ Команда отправлена: ' + cmd);
                } else {
                    alert('❌ Ошибка отправки');
                }
            } catch (error) {
                alert('❌ Ошибка сети: ' + error.message);
            }
        }
        
        async function loadData() {
            try {
                const response = await fetch(serverUrl + '/last_data');
                const data = await response.json();
                
                if (data.length > 0) {
                    const formatted = data.map(item => 
                        `[${item.timestamp}] 🌡 ${item.temperature}°C | 🔋 ${item.battery}V`
                    ).join('\\n');
                    
                    document.getElementById('data').textContent = formatted;
                } else {
                    document.getElementById('data').textContent = 'Нет данных от Arduino';
                }
            } catch (error) {
                document.getElementById('data').textContent = '❌ Ошибка загрузки';
            }
        }
        
        function sendCustomCommand() {
            const cmd = document.getElementById('customCmd').value.trim();
            if (cmd) {
                sendCommand(cmd);
                document.getElementById('customCmd').value = '';
            } else {
                alert('Введите команду!');
            }
        }
        
        // Автообновление каждые 10 секунд
        setInterval(loadData, 10000);
        loadData(); // Загружаем сразу
    </script>
</body>
</html>
'''

# ========== FLASK ROUTES ==========
@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE, server_url=request.host_url)

# Эндпоинт для Arduino: отправка данных
@app.route('/report')
def report():
    try:
        # Получаем параметры
        temperature = request.args.get('temp', '0')
        battery = request.args.get('batt', '0')
        device_id = request.args.get('device', 'arduino')
        
        # Сохраняем в базу данных
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO sensor_data (temperature, battery, device_id) 
            VALUES (?, ?, ?)
        ''', (float(temperature), float(battery), device_id))
        conn.commit()
        conn.close()
        
        log_message(f"Данные от {device_id}: temp={temperature}, batt={battery}")
        
        return "OK", 200
    except Exception as e:
        log_message(f"Ошибка в /report: {e}", "ERROR")
        return "ERROR", 500

# Эндпоинт для Arduino: получение команды
@app.route('/get_command')
def get_command():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Ищем необработанную команду
        cursor.execute('''
            SELECT command FROM commands 
            WHERE processed = 0 
            ORDER BY timestamp ASC 
            LIMIT 1
        ''')
        row = cursor.fetchone()
        
        if row:
            cmd = row[0]
            # Помечаем как обработанную
            cursor.execute('''
                UPDATE commands 
                SET processed = 1 
                WHERE command = ? AND processed = 0
            ''', (cmd,))
            conn.commit()
            conn.close()
            
            log_message(f"Отдана команда Arduino: {cmd}")
            return cmd
        else:
            conn.close()
            return "NO_COMMAND"
    except Exception as e:
        log_message(f"Ошибка в /get_command: {e}", "ERROR")
        return "NO_COMMAND"

# Эндпоинт для добавления команд
@app.route('/command', methods=['POST'])
def add_command():
    try:
        data = request.get_json()
        if not data or 'cmd' not in data:
            return jsonify({"error": "No command"}), 400
        
        cmd = str(data['cmd']).strip().upper()
        
        # Сохраняем в базу данных
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO commands (command) VALUES (?)', (cmd,))
        conn.commit()
        conn.close()
        
        log_message(f"Добавлена команда: {cmd} (от {request.remote_addr})")
        
        return jsonify({"status": "ok", "command": cmd}), 200
    except Exception as e:
        log_message(f"Ошибка в /command: {e}", "ERROR")
        return jsonify({"error": str(e)}), 500

# Последние данные
@app.route('/last_data')
def last_data():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT timestamp, temperature, battery, device_id 
            FROM sensor_data 
            ORDER BY timestamp DESC 
            LIMIT 20
        ''')
        rows = cursor.fetchall()
        conn.close()
        
        data = [{
            'timestamp': row[0],
            'temperature': row[1],
            'battery': row[2],
            'device': row[3]
        } for row in rows]
        
        return jsonify(data), 200
    except Exception as e:
        log_message(f"Ошибка в /last_data: {e}", "ERROR")
        return jsonify([]), 200

# Статистика сервера
@app.route('/stats')
def stats():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM sensor_data')
        total_data = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM commands WHERE processed = 0')
        pending_commands = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM server_logs')
        total_logs = cursor.fetchone()[0]
        
        conn.close()
        
        stats = {
            'status': 'running',
            'server_time': datetime.now().isoformat(),
            'total_data_records': total_data,
            'pending_commands': pending_commands,
            'total_logs': total_logs,
            'database': DB_PATH,
            'platform': 'Render.com' if os.environ.get('RENDER') else 'Local'
        }
        
        return jsonify(stats), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Проверка работы сервера
@app.route('/ping')
def ping():
    return jsonify({
        'status': 'alive',
        'timestamp': datetime.now().isoformat(),
        'message': 'Arduino server on Render.com'
    }), 200

# ========== ЗАПУСК СЕРВЕРА ==========
if __name__ == '__main__':
    # Инициализация базы данных
    init_database()
    
    # Сообщение о запуске
    log_message("=" * 50)
    log_message("🚀 Arduino Server Starting...")
    log_message("=" * 50)
    log_message(f"📦 Database: {DB_PATH}")
    log_message("🌐 Endpoints:")
    log_message("  /           - Web interface")
    log_message("  /report     - Send data from Arduino")
    log_message("  /get_command - Get command for Arduino")
    log_message("  /command    - Add command (POST JSON)")
    log_message("  /last_data  - Last 20 records")
    log_message("  /stats      - Server statistics")
    log_message("  /ping       - Health check")
    log_message("=" * 50)
    
    # Получаем порт из переменной окружения (Render устанавливает PORT)
    port = int(os.environ.get('PORT', 8080))
    
    # Запускаем сервер
    app.run(
        host='0.0.0.0',  # Принимаем соединения со всех интерфейсов
        port=port,
        debug=False  # На продакшене debug=False
    )
