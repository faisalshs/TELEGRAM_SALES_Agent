import logging
from telegram.ext import Application

from .config import load_settings
from .bot import GeminiChat
from .handlers import BotHandlers

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main():
    cfg = load_settings()

    # Model + handlers
    chat_engine = GeminiChat(api_key=cfg.gemini_api_key)
    application = Application.builder().token(cfg.telegram_token).build()
    BotHandlers(chat_engine).register(application)

    # Construct webhook URL (Render sets RENDER_EXTERNAL_URL automatically)
    base_url = cfg.public_base_url  # may be empty on very first boot
    webhook_url = f"{base_url}/{cfg.telegram_token}" if base_url else None

    logger.info("Starting webhook on 0.0.0.0:%s (url_path=%s)", cfg.port, cfg.telegram_token)

    # No 'web_app' param here — just the core webhook server
    application.run_webhook(
        listen="0.0.0.0",
        port=cfg.port,
        url_path=cfg.telegram_token,
        webhook_url=webhook_url,           # if None on first boot, set PUBLIC_BASE_URL and redeploy once
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
