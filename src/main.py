import asyncio
import os
import logging
import uvicorn
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    PreCheckoutQueryHandler,
    filters,
)

from src.config import settings
from src.utils.logger import setup_logging
from src.redis.client import init_redis, close_redis
from src.db.session import engine
from src.db.models import Base
from src.bot import handlers as bot_handlers
from src.bot.commands import (
    start_command,
    help_command,
    mode_command,
    programming_command,
    languages_command,
    exams_command,
    free_command,
    subscribe_command,
)
from src.bot.handlers import callback_handler, message_handler
from src.bot.payments import pre_checkout, successful_payment
from src.admin.app import create_admin_app
from src.services.subscription import expire_old_subscriptions
from src.services.notification import check_expiring_subscriptions
from src.ai.fallback import update_available_models

log = logging.getLogger(__name__)


async def create_tables() -> None:
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        log.info("Database tables created/verified")
    except Exception as e:
        log.warning("Failed to create tables: %s", e)


async def subscription_cleanup_task(interval: int = 3600) -> None:
    while True:
        try:
            expired = await expire_old_subscriptions()
            if expired:
                log.info("Expired %d subscriptions", expired)

            expiring = await check_expiring_subscriptions()
            if expiring and bot_handlers.application and bot_handlers.application.bot:
                bot = bot_handlers.application.bot
                for telegram_id, hours_left in expiring:
                    try:
                        text = (
                            f"⏳ <b>Подписка скоро истечёт</b>\n\n"
                            f"Осталось: <b>{hours_left}ч</b>\n"
                            f"/subscribe для продления."
                        )
                        await bot.send_message(chat_id=telegram_id, text=text, parse_mode="HTML")
                    except Exception as e:
                        log.warning("Failed to notify %d: %s", telegram_id, e)

        except Exception as e:
            log.error("Subscription cleanup error: %s", e)

        await asyncio.sleep(interval)


async def main() -> None:
    setup_logging()
    log.info("Starting Teach AI Bot...")

    await create_tables()

    await init_redis()
    log.info("Redis connected")

    asyncio.create_task(update_available_models())

    admin_app = create_admin_app()
    log.info("Admin app created")

    tg_app = Application.builder().token(settings.bot_token).build()
    bot_handlers.application = tg_app

    tg_app.add_handler(CommandHandler("start", start_command))
    tg_app.add_handler(CommandHandler("help", help_command))
    tg_app.add_handler(CommandHandler("mode", mode_command))
    tg_app.add_handler(CommandHandler("programming", programming_command))
    tg_app.add_handler(CommandHandler("languages", languages_command))
    tg_app.add_handler(CommandHandler("exams", exams_command))
    tg_app.add_handler(CommandHandler("free", free_command))
    tg_app.add_handler(CommandHandler("subscribe", subscribe_command))

    tg_app.add_handler(CallbackQueryHandler(callback_handler))
    tg_app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    tg_app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    asyncio.create_task(subscription_cleanup_task())

    async def run_bot():
        await tg_app.initialize()
        await tg_app.start()
        log.info("Bot started")
        await tg_app.updater.start_polling(drop_pending_updates=True)
        log.info("Polling started")
        try:
            await asyncio.Event().wait()
        finally:
            await tg_app.updater.stop()
            await tg_app.stop()
            await tg_app.shutdown()

    async def run_admin():
        port = int(os.environ.get("PORT", 8000))
        config = uvicorn.Config(
            admin_app,
            host="0.0.0.0",
            port=port,
            log_level="info",
            proxy_headers=True,
            forwarded_allow_ips="*",
        )
        server = uvicorn.Server(config)
        await server.serve()

    try:
        await asyncio.gather(run_bot(), run_admin())
    except KeyboardInterrupt:
        log.info("Shutting down...")
    finally:
        await close_redis()
        await engine.dispose()
        log.info("Shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
