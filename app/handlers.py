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

    # Build ffmpeg command
    # -vn: no video, -c:a libopus: opus codec, -b:a 48k reasonable bitrate
    # Output must be .oga (ogg container with opus)
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
            return

        try:
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

            # 1) Download Telegram voice note (OGG/Opus) to a temp file
            file = await context.bot.get_file(voice.file_id)
            temp_dir = Path("/tmp")
            temp_dir.mkdir(parents=True, exist_ok=True)
            ogg_path = temp_dir / f"voice_{user_id}.oga"
            await file.download_to_drive(str(ogg_path))

            # 2) Upload to Gemini for transcription (no transcoding needed)
            uploaded = genai.upload_file(path=str(ogg_path), mime_type="audio/ogg")
            transcription_prompt = ("Transcribe the following audio and identify its language "
                                    "(choose from English, Arabic, Hindi, or Bengali). "
                                    "Respond in the format: [LANGUAGE_CODE]: [Transcription]. For example: bn: কেমন আছেন?")
            model = self.chat_engine._model  # reuse configured model
            tr = model.generate_content([transcription_prompt, uploaded])
            genai.delete_file(uploaded.name)

            transcribed_text = (tr.text or "").strip()
            logger.info("Transcription: %s", transcribed_text)

            # 3) Parse "xx: text" format; fallback to detection
            if ":" in transcribed_text:
                lang_code, user_text = transcribed_text.split(":", 1)
                lang_code = (lang_code or "").strip().lower()
                user_text = (user_text or "").strip()
            else:
                user_text = transcribed_text
                lang_code = detect_language(user_text)

            if not user_text:
                await update.message.reply_text("Sorry, I couldn't understand that voice message. Please try again. 🎤")
                return

            await update.message.reply_text(f"Heard: *{user_text}*", parse_mode=ParseMode.MARKDOWN)

            # 4) Get chatbot reply text in same language
            reply_text = self.chat_engine.reply(user_id, user_text, lang_code)

            # 5) TTS using gTTS → MP3
            tts = gTTS(text=reply_text, lang=lang_code if lang_code in ("en","ar","hi","bn") else "en")
            mp3_buf = io.BytesIO()
            tts.write_to_fp(mp3_buf)
            mp3_buf.seek(0)
            mp3_bytes = mp3_buf.read()

            # 6) Convert MP3 → OGG Opus (true Telegram "voice") with ffmpeg, then send_voice
            out_oga = temp_dir / f"reply_{user_id}.oga"
            mp3_to_oga_ffmpeg(mp3_bytes, out_oga)

            with open(out_oga, "rb") as f:
                await context.bot.send_voice(chat_id=update.effective_chat.id, voice=f)

        except subprocess.CalledProcessError as ce:
            logger.error("ffmpeg conversion failed: %s", ce, exc_info=True)
            await update.message.reply_text("I generated a reply but couldn't format the voice properly. Try text for now, or contact support.")
        except Exception as e:
            logger.error("Error handling voice message: %s", e, exc_info=True)
            await update.message.reply_text("I'm sorry, I had trouble with that voice message. Please try again. 🎤")
