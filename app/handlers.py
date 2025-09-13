from pathlib import Path
import json
import logging
import io
import os
import subprocess
from pathlib import Path

from telegram import Update
from telegram.constants import ParseMode, ChatAction
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters

from gtts import gTTS
import google.generativeai as genai

from .bot import detect_language, GeminiChat, LANG_MAP

logger = logging.getLogger(__name__)

# Admin-store aware catalog loader
def _get_catalog_path() -> Path:
    try:
        root = Path(__file__).resolve().parent.parent
        store_path = root / "data" / "admin_store.json"
        store = {}
        if store_path.exists():
            try:
                store = json.loads(store_path.read_text(encoding="utf-8"))
            except Exception:
                store = {}
        rel = store.get("catalog_file") or "product_data/jatri_books_info.md"
        p = root / rel
        return p if p.exists() else (root / "product_data" / "jatri_books_info.md")
    except Exception:
        root = Path(__file__).resolve().parent.parent
        return root / "product_data" / "jatri_books_info.md"


def mp3_to_oga_ffmpeg(mp3_bytes: bytes, out_path: Path):
    """
    Convert MP3 bytes to OGG/Opus voice format using ffmpeg.
    Telegram expects OGG Opus for send_voice.
    """
    tmp_dir = Path("/tmp")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    mp3_path = tmp_dir / "reply.mp3"
    with open(mp3_path, "wb") as f:
        f.write(mp3_bytes)

    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(mp3_path),
        "-vn",
        "-c:a", "libopus",
        "-b:a", "48k",
        "-f", "ogg",
        str(out_path)
    ]
    subprocess.run(cmd, check=True, capture_output=True)


class BotHandlers:
    def __init__(self, chat_engine: GeminiChat):
        self.chat_engine = chat_engine

    def register(self, application):
        application.add_handler(CommandHandler("start", self.start))
        application.add_handler(CommandHandler("help", self.help_command))
        application.add_handler(CommandHandler("clear", self.clear_chat_history))
        application.add_handler(MessageHandler(filters.VOICE, self.handle_voice_message))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_message))

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        await update.message.reply_text(
            f"Hello, {user.first_name}! 👋 Welcome to Jatri Bookstore. 📚\n\n"
            "I'm Leo, your personal guide. I can help you find a great Thriller or Self-Help book from our special campaign offer. I can assist in English, Bengali, Hindi, and Arabic.\n\n"
            "What kind of book are you in the mood for today?"
        )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "I can help you with our book offers in English, Arabic, Hindi, and Bengali.\n\n"
            "**COMMANDS:**\n"
            "✅ /start - To begin our conversation.\n"
            "ℹ️ /help - To see this message again.\n"
            "🔄 /clear - To start a fresh conversation with me.",
            parse_mode=ParseMode.MARKDOWN
        )

    async def clear_chat_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        self.chat_engine.clear(user_id)
        await update.message.reply_text("Our conversation history has been cleared. ✨\nLet's find you a great book!")

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
        user_id = update.effective_user.id
        voice = update.message.voice
        if not voice:
            await update.message.reply_text("I couldn't find a voice message. Please try again. 🎤")
