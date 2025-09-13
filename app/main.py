import logging
from telegram.ext import Application
from aiohttp import web
from .config import load_settings
from .bot import GeminiChat
from .handlers import BotHandlers
from .admin import mount_admin_routes

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

def main():
    cfg = load_settings()

    # Configure Gemini (done inside bot/handlers as needed)
    application = Application.builder().token(cfg.telegram_token).build()

    # Register handlers
    bot = GeminiChat()
    handlers = BotHandlers(bot)
    handlers.register(application)

    # Build aiohttp web_app to serve health + admin panel
    web_app = web.Application()
    async def health(request):
        return web.json_response({"status": "ok"})
    web_app.router.add_get("/", health)
    mount_admin_routes(web_app)

    if cfg.mode == "polling":
        logger.info("MODE=polling -> starting polling")
        application.run_polling(drop_pending_updates=True)
        return

    # Webhook mode (Render)
    webhook_url = None
    if cfg.public_base_url:
        webhook_url = f"{cfg.public_base_url.rstrip('/')}/{cfg.telegram_token}"

    logger.info("Starting webhook on 0.0.0.0:%s (url_path=%s)", cfg.port, cfg.telegram_token)
    application.run_webhook(
        listen="0.0.0.0",
        port=cfg.port,
        url_path=cfg.telegram_token,
        webhook_url=webhook_url,
        drop_pending_updates=True,
        web_app=web_app,
    )

if __name__ == "__main__":
    main()
