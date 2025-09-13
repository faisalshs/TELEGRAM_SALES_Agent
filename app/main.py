import asyncio
import logging
import os

from aiohttp import web
from telegram.ext import Application

from .config import load_settings
from .bot import GeminiChat
from .handlers import BotHandlers

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

async def health(_request):
    return web.json_response({"status": "ok"})

async def main():
    cfg = load_settings()

    chat_engine = GeminiChat(api_key=cfg.gemini_api_key)

    application = Application.builder().token(cfg.telegram_token).build()
    BotHandlers(chat_engine).register(application)

    # Build aiohttp app for extra routes (like health check)
    web_app = web.Application()
    web_app.router.add_get("/", health)

    # Prefer Render's public URL if available
    base_url = cfg.public_base_url
    if not base_url:
        logger.warning("PUBLIC_BASE_URL not set yet; webhook may not receive updates until it is set.")
    webhook_url = f"{base_url}/{cfg.telegram_token}" if base_url else None

    logger.info("Starting webhook server on 0.0.0.0:%s", cfg.port)
    application.run_webhook(
        listen="0.0.0.0",
        port=cfg.port,
        url_path=cfg.telegram_token,
        webhook_url=webhook_url,  # can be None on first boot; set later if needed
        web_app=web_app,
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
