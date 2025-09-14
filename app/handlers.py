import io
import os
import shutil
import subprocess
import tempfile
import logging
from pathlib import Path
from typing import Optional, Tuple

from telegram import Update, InputFile
from telegram.constants import ChatAction
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters

from gtts import gTTS
import google.generativeai as genai

from .bot import detect_language, GeminiChat

logger = logging.getLogger(__name__)

# ----------------------------
# Helpers: TTS and conversion
# ----------------------------

def _tts_to_mp3_bytes(text: str, lang_code: str) -> bytes:
    """Use gTTS to synthesize MP3 into memory."""
    buf = io.BytesIO()
    lc = (lang_code or "en").split("-")[0]
    gTTS(text=text, lang=lc).write_to_fp(buf)
    return buf.getvalue()

def _mp3_to_ogg_opus(mp3_bytes: bytes) -> Optional[bytes]:
    """Convert MP3 bytes to Opus-in-Ogg using ffmpeg. Return None if conversion fails or ffmpeg missing."""
    if not mp3_bytes:
        return None
    if shutil.which("ffmpeg") is None:
        logger.warning("ffmpeg not found; cannot create Telegram voice bubble. Falling back to MP3/audio.")
        return None

    with tempfile.TemporaryDirectory() as td:
        mp3_path = Path(td) / "reply.mp3"
        ogg_path = Path(td) / "reply.ogg"
        mp3_path.write_bytes(mp3_bytes)

        cmd = [
            "ffmpeg", "-y",
            "-i", str(mp3_path),
            "-vn",
            "-ac", "1",
            "-ar", "48000",
            "-c:a", "libopus",
            "-b:a", "64k",
            str(ogg_path),
        ]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode != 0 or not ogg_path.exists():
            logger.error("ffmpeg conversion failed: rc=%s, stderr=%s", proc.returncode, proc.stderr.decode(errors="ignore"))
            return None
        return ogg_path.read_bytes()

async def _send_voice_from_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, lang_code: str):
    """Send a Telegram voice bubble; fall back to MP3 audio if needed."""
    if not text:
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.RECORD_VOICE)

    try:
        mp3 = _tts_to_mp3_bytes(text, lang_code)
    except Exception as e:
        logger.exception("gTTS failed: %s", e)
        await update.message.reply_text("Sorry, I couldn't generate the voice reply right now. 🛠️")
        return

    ogg = None
    try:
        ogg = _mp3_to_ogg_opus(mp3)
    except Exception as e:
        logger.exception("ffmpeg conversion error: %s", e)

    try:
        if ogg is not None:
            await update.message.reply_voice(voice=InputFile(io.BytesIO(ogg), filename="reply.ogg"))
        else:
            await update.message.reply_audio(audio=InputFile(io.BytesIO(mp3), filename="reply.mp3"))
    except Exception as e:
        logger.exception("Failed sending voice/audio: %s", e)
        await update.message.reply_text("Sorry, I couldn't send the voice reply. 🛠️")

# ----------------------------
# Helpers: Telegram voice -> bytes and transcription
# ----------------------------

async def _download_voice_bytes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[Tuple[bytes, str]]:
    """Download Telegram voice message; returns (bytes, mime_type)."""
    voice = update.message.voice
    if not voice:
        return None
    try:
        file = await context.bot.get_file(voice.file_id)
        buf = io.BytesIO()
        await file.download_to_memory(out=buf)
        return buf.getvalue(), "audio/ogg"  # Telegram voice bubbles are Opus-in-Ogg
    except Exception as e:
        logger.exception("Failed to download voice file: %s", e)
        return None

def _transcribe_with_gemini(audio_bytes: bytes, mime_type: str) -> Optional[str]:
    """Transcribe audio using Gemini 1.5 Flash via file upload."""
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        with tempfile.NamedTemporaryFile(delete=False, suffix=".oga") as f:
            f.write(audio_bytes)
            tmp_path = f.name
        gfile = genai.upload_file(tmp_path, mime_type=mime_type)
        try:
            prompt = "Transcribe the audio exactly as spoken. Respond with only the transcript text."
            resp = model.generate_content([prompt, gfile])
            txt = (resp.text or "").strip()
            return txt or None
        finally:
            try:
                genai.delete_file(gfile.name)
            except Exception:
                pass
            try:
                os.remove(tmp_path)
            except Exception:
                pass
    except Exception as e:
        logger.exception("Gemini transcription failed: %s", e)
        return None

# ----------------------------
# Bot Handlers
# ----------------------------

class BotHandlers:
    def __init__(self, chat_engine: GeminiChat):
        # genai.configure(api_key=...) is already done by GeminiChat initializer
        self.chat_engine = chat_engine

    def register(self, application):
        # Commands
        application.add_handler(CommandHandler("start", self.start))
        application.add_handler(CommandHandler("help", self.help_command))
        application.add_handler(CommandHandler("clear", self.clear_chat_history))

        # Voice first so it doesn't get swallowed by TEXT filter
        application.add_handler(MessageHandler(filters.VOICE, self.handle_voice_message))
        # Plain text
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_message))

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        await update.message.reply_text(
            f"Hello, {user.first_name}! 👋 Welcome to Jatri Bookstore. 📚\n\n"
            "Send me a message or a voice note—I'll reply in the same language."
        )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "I can chat in English, Bengali, Hindi, and Arabic.\n"
            "• Send text: I reply with text.\n"
            "• Send a voice message: I reply with voice too.\n"
            "Commands: /start /help /clear"
        )

    async def clear_chat_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.chat_engine.clear(update.effective_user.id)
        await update.message.reply_text("Your chat history is cleared. 🧹")

    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        user_message = update.message.text or ""
        lang_code = detect_language(user_message)

        try:
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
            reply = self.chat_engine.reply(user_id, user_message, lang_code)
            await update.message.reply_text(reply)
        except Exception as e:
            logger.error("Error in handle_text_message: %s", e, exc_info=True)
            await update.message.reply_text("I'm sorry, I'm having a technical issue. Please try again in a moment. 🛠️")

    async def handle_voice_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Reply with voice when customer sends a voice message."""
        user_id = update.effective_user.id

        dl = await _download_voice_bytes(update, context)
        if not dl:
            await update.message.reply_text("I couldn't fetch your voice message. Please try again. 🎤")
            return

        audio_bytes, mime_type = dl

        # Transcribe
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        transcript = _transcribe_with_gemini(audio_bytes, mime_type)
        if not transcript:
            await update.message.reply_text("Sorry, I couldn't understand that voice message. Could you try again?")
            return

        lang_code = detect_language(transcript)

        # Generate reply with existing core logic
        try:
            reply = self.chat_engine.reply(user_id, transcript, lang_code)
        except Exception as e:
            logger.exception("Chat engine failed on transcript: %s", e)
            await update.message.reply_text("I'm having trouble forming a reply right now. Please try again. 🛠️")
            return

        # Send both text and voice
        try:
            await update.message.reply_text(reply)
        except Exception:
            pass

        await _send_voice_from_text(update, context, reply, lang_code)
