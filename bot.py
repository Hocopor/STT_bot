import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

load_dotenv()

LOG_LEVEL = os.getenv("BOT_LOG_LEVEL", "INFO")
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger("stt-test-bot")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
STT_URL = os.getenv("STT_URL", "http://localhost:8000/stt").strip()
STT_API_KEY = os.getenv("STT_API_KEY", "").strip()
STT_STREAM = os.getenv("STT_STREAM", "false").lower() == "true"
STT_TIMEOUT_SECONDS = float(os.getenv("STT_TIMEOUT_SECONDS", "180"))

TMP_DIR = Path(os.getenv("BOT_TMP_DIR", "./tmp")).resolve()
TMP_DIR.mkdir(parents=True, exist_ok=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Пришли voice-сообщение. Я отправлю его в STT Gateway и верну текст."
    )


async def _download_voice(update: Update) -> Optional[Path]:
    if not update.message or not update.message.voice:
        return None

    voice = update.message.voice
    file = await update.message.effective_attachment.get_file()
    suffix = ".ogg"
    path = TMP_DIR / f"voice_{voice.file_id}{suffix}"
    await file.download_to_drive(custom_path=str(path))
    return path


async def _transcribe_non_stream(file_path: Path) -> str:
    headers = {"X-API-Key": STT_API_KEY}
    params = {"stream": "false"}
    timeout = httpx.Timeout(STT_TIMEOUT_SECONDS)

    async with httpx.AsyncClient(timeout=timeout) as client:
        with file_path.open("rb") as f:
            files = {"file": (file_path.name, f, "audio/ogg")}
            resp = await client.post(STT_URL, headers=headers, params=params, files=files)
            resp.raise_for_status()
            data = resp.json()
            return data.get("text", "")


async def _transcribe_stream(file_path: Path) -> str:
    headers = {"X-API-Key": STT_API_KEY}
    params = {"stream": "true"}
    timeout = httpx.Timeout(STT_TIMEOUT_SECONDS)
    full_text_parts: list[str] = []

    async with httpx.AsyncClient(timeout=timeout) as client:
        with file_path.open("rb") as f:
            files = {"file": (file_path.name, f, "audio/ogg")}
            async with client.stream(
                "POST",
                STT_URL,
                headers=headers,
                params=params,
                files=files,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    payload = line[6:]
                    try:
                        data = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    if data.get("final"):
                        text = data.get("full_text", "")
                        if text:
                            full_text_parts.append(text)
                        break
                    chunk_text = data.get("text")
                    if chunk_text:
                        full_text_parts.append(chunk_text)

    return " ".join(full_text_parts).strip()


async def on_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not BOT_TOKEN:
        await update.message.reply_text("TELEGRAM_BOT_TOKEN не задан.")
        return
    if not STT_API_KEY:
        await update.message.reply_text("STT_API_KEY не задан.")
        return

    file_path = await _download_voice(update)
    if not file_path:
        await update.message.reply_text("Не удалось скачать voice.")
        return

    processing_message = None
    try:
        processing_message = await update.message.reply_text("Обрабатываю...")
        if STT_STREAM:
            text = await _transcribe_stream(file_path)
        else:
            text = await _transcribe_non_stream(file_path)
        if not text:
            text = "Пустой результат."
        if processing_message:
            await processing_message.edit_text(text)
        else:
            await update.message.reply_text(text)
    except httpx.HTTPStatusError as exc:
        if processing_message:
            await processing_message.edit_text(f"Ошибка STT: {exc.response.text}")
        else:
            await update.message.reply_text(f"Ошибка STT: {exc.response.text}")
    except Exception as exc:
        logger.exception("Failed to transcribe")
        if processing_message:
            await processing_message.edit_text(f"Ошибка: {exc}")
        else:
            await update.message.reply_text(f"Ошибка: {exc}")
    finally:
        try:
            file_path.unlink(missing_ok=True)
        except Exception:
            pass


def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.VOICE, on_voice))

    logger.info("Test bot started")
    app.run_polling()


if __name__ == "__main__":
    main()
