import asyncio
import json
import logging
import os
import re
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
QUIET_LOGGERS = os.getenv(
    "BOT_QUIET_LOGGERS",
    "telegram,telegram.ext,httpx,apscheduler",
)
for name in [item.strip() for item in QUIET_LOGGERS.split(",") if item.strip()]:
    logging.getLogger(name).setLevel(logging.WARNING)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
STT_URL = os.getenv("STT_URL", "http://localhost:8000/stt").strip()
STT_API_KEY = os.getenv("STT_API_KEY", "").strip()
STT_STREAM = os.getenv("STT_STREAM", "false").lower() == "true"
STT_TIMEOUT_SECONDS = float(os.getenv("STT_TIMEOUT_SECONDS", "180"))
STT_READ_TIMEOUT_SECONDS = float(os.getenv("STT_READ_TIMEOUT_SECONDS", "0"))
TG_MESSAGE_MAX_LEN = int(os.getenv("TG_MESSAGE_MAX_LEN", "3700"))

TMP_DIR = Path(os.getenv("BOT_TMP_DIR", "./tmp")).resolve()
TMP_DIR.mkdir(parents=True, exist_ok=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Пришли voice-сообщение. Я отправлю его в STT Gateway и верну текст."
    )


def _guess_suffix(filename: Optional[str], mime: Optional[str]) -> str:
    if filename and "." in filename:
        return "." + filename.split(".")[-1].lower()
    if mime == "audio/ogg" or mime == "audio/opus":
        return ".ogg"
    if mime == "audio/wav":
        return ".wav"
    if mime == "audio/mpeg":
        return ".mp3"
    return ".ogg"


async def _download_audio(update: Update) -> Optional[tuple[Path, str]]:
    if not update.message:
        return None

    attachment = None
    filename = None
    mime = None
    prefix = "audio"

    if update.message.voice:
        attachment = update.message.voice
        mime = "audio/ogg"
        prefix = "voice"
    elif update.message.audio:
        attachment = update.message.audio
        filename = update.message.audio.file_name
        mime = update.message.audio.mime_type
        prefix = "audio"
    elif update.message.document:
        attachment = update.message.document
        filename = update.message.document.file_name
        mime = update.message.document.mime_type
        prefix = "file"
        if mime and not mime.startswith("audio/") and mime not in ("application/ogg",):
            if filename and "." in filename:
                ext = filename.split(".")[-1].lower()
                if ext not in ("ogg", "opus", "wav", "mp3"):
                    return None
            else:
                return None
    else:
        return None

    suffix = _guess_suffix(filename, mime)
    file = await attachment.get_file()
    path = TMP_DIR / f"{prefix}_{attachment.file_id}{suffix}"
    await file.download_to_drive(custom_path=str(path))
    content_type = mime or "application/octet-stream"
    return path, content_type


async def _transcribe_non_stream(file_path: Path, content_type: str) -> str:
    headers = {"X-API-Key": STT_API_KEY}
    params = {"stream": "false"}
    read_timeout = STT_READ_TIMEOUT_SECONDS if STT_READ_TIMEOUT_SECONDS > 0 else None
    timeout = httpx.Timeout(
        connect=10.0,
        read=read_timeout,
        write=60.0,
        pool=10.0,
    )

    async with httpx.AsyncClient(timeout=timeout) as client:
        with file_path.open("rb") as f:
            files = {"file": (file_path.name, f, content_type)}
            resp = await client.post(STT_URL, headers=headers, params=params, files=files)
            resp.raise_for_status()
            data = resp.json()
            return data.get("text", "")


async def _transcribe_stream(file_path: Path, content_type: str) -> str:
    headers = {"X-API-Key": STT_API_KEY}
    params = {"stream": "true"}
    timeout = httpx.Timeout(STT_TIMEOUT_SECONDS)
    full_text_parts: list[str] = []

    async with httpx.AsyncClient(timeout=timeout) as client:
        with file_path.open("rb") as f:
            files = {"file": (file_path.name, f, content_type)}
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


def _split_long_text_by_words(text: str, max_len: int) -> list[str]:
    if len(text) <= max_len:
        return [text]
    parts: list[str] = []
    remaining = text
    while len(remaining) > max_len:
        split_at = remaining.rfind(" ", 0, max_len + 1)
        if split_at <= 0:
            split_at = max_len
        chunk = remaining[:split_at].rstrip()
        if not chunk:
            chunk = remaining[:max_len]
            split_at = max_len
        parts.append(chunk)
        remaining = remaining[split_at:].lstrip()
    if remaining:
        parts.append(remaining)
    return parts


def _split_text_for_telegram(text: str, max_len: int) -> list[str]:
    if not text:
        return [""]
    if max_len <= 0:
        return [text]

    sentences = re.split(r"(?<=[.!?…])\s+", text.strip())
    chunks: list[str] = []
    current = ""

    for sentence in sentences:
        if not sentence:
            continue
        if len(sentence) > max_len:
            for part in _split_long_text_by_words(sentence, max_len):
                if current:
                    chunks.append(current)
                    current = ""
                chunks.append(part)
            continue

        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) <= max_len:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = sentence

    if current:
        chunks.append(current)
    return chunks


async def _send_text_chunks(
    update: Update,
    processing_message,
    text: str,
    max_len: int,
) -> None:
    chunks = _split_text_for_telegram(text, max_len)
    if len(chunks) == 1:
        if processing_message:
            await processing_message.edit_text(chunks[0])
        else:
            await update.message.reply_text(chunks[0])
        return

    total = len(chunks)
    first = f"1/{total} {chunks[0]}"
    if processing_message:
        await processing_message.edit_text(first)
    else:
        await update.message.reply_text(first)
    for idx, chunk in enumerate(chunks[1:], start=2):
        await update.message.reply_text(f"{idx}/{total} {chunk}")


async def on_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not BOT_TOKEN:
        await update.message.reply_text("TELEGRAM_BOT_TOKEN не задан.")
        return
    if not STT_API_KEY:
        await update.message.reply_text("STT_API_KEY не задан.")
        return

    downloaded = await _download_audio(update)
    if not downloaded:
        await update.message.reply_text("Не удалось скачать аудио.")
        return
    file_path, content_type = downloaded

    await update.message.reply_text("Принял, обрабатываю. Отправлю результат позже.")
    chat_id = update.effective_chat.id
    reply_to_message_id = update.message.message_id
    context.application.create_task(
        _process_voice(
            file_path=file_path,
            content_type=content_type,
            chat_id=chat_id,
            reply_to_message_id=reply_to_message_id,
            bot=context.bot,
        )
    )


async def _process_voice(
    file_path: Path,
    content_type: str,
    chat_id: int,
    reply_to_message_id: int,
    bot,
) -> None:
    try:
        if STT_STREAM:
            text = await _transcribe_stream(file_path, content_type)
        else:
            text = await _transcribe_non_stream(file_path, content_type)
        if not text:
            text = "Пустой результат."

        async def send_chunk(text_chunk: str) -> None:
            await bot.send_message(
                chat_id=chat_id,
                text=text_chunk,
                reply_to_message_id=reply_to_message_id,
            )

        chunks = _split_text_for_telegram(text, TG_MESSAGE_MAX_LEN)
        if len(chunks) == 1:
            await send_chunk(chunks[0])
        else:
            total = len(chunks)
            await send_chunk(f"1/{total} {chunks[0]}")
            for idx, chunk in enumerate(chunks[1:], start=2):
                await send_chunk(f"{idx}/{total} {chunk}")
    except httpx.HTTPStatusError as exc:
        await bot.send_message(
            chat_id=chat_id,
            text=f"Ошибка STT: {exc.response.text}",
            reply_to_message_id=reply_to_message_id,
        )
    except Exception as exc:
        logger.exception("Failed to transcribe")
        await bot.send_message(
            chat_id=chat_id,
            text=f"Ошибка: {exc}",
            reply_to_message_id=reply_to_message_id,
        )
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
    audio_filter = (
        filters.VOICE
        | filters.AUDIO
        | filters.Document.AUDIO
        | filters.Document.MimeType("application/ogg")
        | filters.Document.MimeType("audio/ogg")
        | filters.Document.MimeType("audio/opus")
        | filters.Document.MimeType("audio/wav")
        | filters.Document.MimeType("audio/mpeg")
    )
    app.add_handler(MessageHandler(audio_filter, on_voice))

    logger.info("Test bot started")
    app.run_polling()


if __name__ == "__main__":
    main()
