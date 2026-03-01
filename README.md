# STT Gateway — Test Telegram Bot

Минимальный Telegram‑бот для тестирования STT Gateway. Принимает voice‑сообщения, отправляет аудио в STT Gateway и возвращает текст.

## Требования
- Python 3.11
- Созданный бот в Telegram (через @BotFather)
- Запущенный STT Gateway

## Быстрый старт (Windows 10)
1. Создайте venv:
```powershell
py -3.11 -m venv .venv
```
2. Активируйте venv:
```powershell
.\.venv\Scripts\Activate.ps1
```
3. Установите зависимости:
```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```
4. Создайте `.env` (см. `.env.example`).
5. Запуск:
```powershell
python bot.py
```

## Переменные окружения
- `TELEGRAM_BOT_TOKEN` — токен бота.
- `STT_URL` — URL STT Gateway, например: `http://localhost:8000/stt`.
- `STT_API_KEY` — API ключ STT Gateway.
- `STT_STREAM` — `true` или `false` (по умолчанию `false`).
- `STT_TIMEOUT_SECONDS` — таймаут запроса к STT (по умолчанию `180`).

## Примечания
- Бот сохраняет временные файлы в `./tmp` и удаляет после обработки.
- Для потокового режима SSE используется простое чтение `data:` строк.
