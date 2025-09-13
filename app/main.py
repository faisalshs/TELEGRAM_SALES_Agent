import asyncio
import logging
from aiohttp import web
from telegram import Update

from .config import load_settings
from .bot import GeminiChat
from .handlers import BotHandlers
from .admin import mount_admin_routes

from telegram.ext import Application

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def async_main():
    cfg = load_settings()

    # Build PTB application
    application = Application.builder().token(cfg.telegram_token).build()

    # Chat engine (pass API key!)
    bot_engine = GeminiChat(api_key=cfg.gemini_api_key)

    # Register bot handlers
    handlers = BotHandlers(chat_engine=bot_engine)
    handlers.register(application)

    # --- Create aiohttp app (health + admin + Telegram webhook) ---
    web_app = web.Application()

    async def health(_req):
        return web.json_response({"status": "ok"})

    web_app.router.add_get("/", health)

    # Mount admin panel routes
    mount_admin_routes(web_app)

    # Telegram webhook endpoint: POST /<token>
    async def telegram_webhook(request: web.Request):
        try:
            data = await request.json()
        except Exception:
            return web.Response(status=400, text="Invalid JSON")

        update = Update.de_json(data, application.bot)
        await application.process_update(update)
        return web.Response(text="ok")

    web_app.router.add_post(f"/{cfg.telegram_token}", telegram_webhook)

    # Initialize + start PTB (without its own HTTP server)
    await application.initialize()
    await application.start()

    # Set webhook at Telegram so they call our aiohttp route
    webhook_url = None
    if cfg.public_base_url:
        webhook_url = f"{cfg.public_base_url.rstrip('/')}/{cfg.telegram_token}"

    if webhook_url:
        # drop_pending_updates=True ensures we don't get stale backlog on the first boot
        await application.bot.set_webhook(url=webhook_url, drop_pending_updates=True)
        logger.info("Webhook set to %s", webhook_url)
    else:
        logger.warning(
            "PUBLIC_BASE_URL/RENDER_EXTERNAL_URL not set. Telegram will not deliver updates. "
            "Set it and redeploy (or use MODE=polling locally)."
        )

    # Run aiohttp server (Render expects a single listening process on PORT)
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=cfg.port)
    logger.info("Starting aiohttp server on 0.0.0.0:%s", cfg.port)
    await site.start()

    # Keep running forever
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        # Graceful shutdown
        await application.stop()
        await application.shutdown()
        await runner.cleanup()


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
