# 🎙️ STT Bot — Telegram аудио → текст

Полноценный Telegram‑бот для расшифровки аудиосообщений. Принимает voice‑сообщения, отправляет их в STT Gateway и возвращает текст пользователю в ответе.  
Добавьте бота в группу, выдайте нужные права — и он будет переводить **все аудиосообщения** от любых участников. ✅

---

## ✨ Возможности
- 🗣️ Расшифровка голосовых сообщений в личных чатах
- 👥 Работа в группах: транскрибация **всех** voice‑сообщений
- 🔁 Потоковый и обычный режимы обработки
- ⏱️ Настраиваемые таймауты и параметры STT
- 🧹 Авто‑очистка временных файлов

---

## 🧠 Как это работает

```mermaid
sequenceDiagram
    autonumber
    participant User as Пользователь
    participant TG as Telegram
    participant Bot as STT Bot
    participant STT as STT Gateway

    User->>TG: Отправляет voice
    TG->>Bot: Доставляет voice
    Bot->>STT: POST /stt (audio/ogg)
    STT-->>Bot: Текст
    Bot-->>TG: Ответ пользователю
```

---

## 🗺️ Архитектура (схема)

```
┌────────────┐   voice    ┌───────────┐   audio/ogg   ┌─────────────┐
│ Telegram   │──────────▶ │  STT Bot  │──────────────▶│ STT Gateway │
└────────────┘  updates   └───────────┘    response   └─────────────┘
                        ▲                     │
                        └──── text reply ─────┘
```

---

## ✅ Требования
- Python 3.11
- Созданный бот в Telegram (через @BotFather)
- Запущенный STT Gateway

---

## 🚀 Быстрый старт (Windows 10/11)
1. Создайте виртуальное окружение:
```powershell
py -3.11 -m venv .venv
```
2. Активируйте окружение:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```
3. Установите зависимости:
```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```
4. Создайте `.env` (см. `.env.example`)
5. Запуск:
```powershell
python bot.py
```

---

## 🐧 Деплой на Ubuntu/Linux (systemd)

Ниже — безопасный и удобный способ запуска бота как сервиса с автозапуском и автоперезапуском.

### 1) Подготовка сервера
```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv
sudo adduser --system --group --home /opt/stt-bot sttbot
```

### 2) Развертывание кода
Скопируйте проект в `/opt/stt-bot` (например, через `git clone` или `scp`) и выставьте владельца:
```bash
sudo mkdir -p /opt/stt-bot
sudo chown -R sttbot:sttbot /opt/stt-bot
```

### 3) Установка зависимостей
```bash
sudo -u sttbot python3.11 -m venv /opt/stt-bot/.venv
sudo -u sttbot /opt/stt-bot/.venv/bin/python -m pip install --upgrade pip
sudo -u sttbot /opt/stt-bot/.venv/bin/pip install -r /opt/stt-bot/requirements.txt
```

### 4) Настройка окружения
Создайте файл `/opt/stt-bot/.env` по примеру `.env.example`:
```bash
sudo -u sttbot nano /opt/stt-bot/.env
```

### 5) systemd unit
Создайте файл `/etc/systemd/system/stt-bot.service`:
```ini
[Unit]
Description=STT Telegram Bot
After=network.target

[Service]
User=sttbot
Group=sttbot
WorkingDirectory=/opt/stt-bot
EnvironmentFile=/opt/stt-bot/.env
ExecStart=/opt/stt-bot/.venv/bin/python /opt/stt-bot/bot.py
Restart=always
RestartSec=3
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
```

### 6) Запуск и автозапуск
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now stt-bot
```

### 7) Проверка статуса и логов
```bash
sudo systemctl status stt-bot
sudo journalctl -u stt-bot -f
```

---

## ⚙️ Переменные окружения
- `TELEGRAM_BOT_TOKEN` — токен Telegram‑бота
- `STT_URL` — URL STT Gateway, например `http://localhost:8000/stt`
- `STT_API_KEY` — API‑ключ STT Gateway
- `STT_STREAM` — `true` или `false` (по умолчанию `false`)
- `STT_TIMEOUT_SECONDS` — таймаут запроса к STT (по умолчанию `180`)
- `BOT_TMP_DIR` — путь для временных файлов (по умолчанию `./tmp`)
- `BOT_LOG_LEVEL` — уровень логирования (по умолчанию `INFO`)
- `BOT_QUIET_LOGGERS` — список логгеров для подавления шума (по умолчанию `telegram,telegram.ext,httpx,apscheduler`)

---

## 👥 Работа в группах
Чтобы бот обрабатывал аудио в группе:
1. Добавьте бота в группу, сделайте админом
2. Выдайте права на чтение сообщений и голосовых
3. Убедитесь, что бот **не ограничен** и видит все сообщения

После этого бот будет автоматически расшифровывать **каждое** voice‑сообщение в группе. 💬

---

## 🧪 Режимы работы
- Обычный режим: один запрос → один ответ
- Потоковый режим: читает SSE и собирает полный текст

Переключение через `STT_STREAM=true|false`.

---

## 🧰 Troubleshooting
- Бот не отвечает: проверьте `TELEGRAM_BOT_TOKEN`
- STT ошибки: проверьте `STT_URL` и `STT_API_KEY`
- Долгая обработка: увеличьте `STT_TIMEOUT_SECONDS`
- Шум в логах: настройте `BOT_LOG_LEVEL` и `BOT_QUIET_LOGGERS`

---

## 🔐 Безопасность
- Храните `.env` вне публичного доступа
- Не публикуйте `TELEGRAM_BOT_TOKEN` и `STT_API_KEY`

---

## 📦 Что внутри
- `bot.py` — основной код бота
- `requirements.txt` — зависимости
- `.env.example` — шаблон окружения

---

## 📄 Лицензия
Добавьте файл лицензии, если требуется для вашего проекта.
