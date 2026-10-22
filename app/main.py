import asyncio
import signal
import sys

from app.core.config import settings
from app.core.logging import setup_logging, logger
from app.database.session import init_db, close_db, get_db_session
from app.database.repositories.admin_repo import AdminRepository
from app.telegram_client.client import telegram_client_manager
from app.bot.bot_instance import bot, dp, setup_dispatcher, setup_bot_commands
from app.scheduler.jobs import scheduler


async def on_startup() -> None:
    logger.info("IMKON Ads Monitoring System ishga tushmoqda...")

    # 1. Initialize database schema
    logger.info("Ma'lumotlar bazasi jadvallari tekshirilmoqda...")
    await init_db()

    # 2. Ensure Superadmins from settings
    if settings.ADMIN_IDS:
        logger.info(f"Superadminlar tekshirilmoqda: {settings.ADMIN_IDS}")
        async with get_db_session() as session:
            repo = AdminRepository(session)
            await repo.ensure_superadmins(settings.ADMIN_IDS)

    # 3. Connect MTProto Telethon client
    try:
        await telegram_client_manager.start()
        is_auth = await telegram_client_manager.is_authorized()
        if is_auth:
            logger.info("✅ Telethon MTProto client avtorizatsiyadan o'tgan")
        else:
            logger.warning(
                "⚠️ Telethon client avtorizatsiyadan o'tmagan! "
                "Iltimos, 'python scripts/telegram_login.py' skriptini ishga tushiring."
            )
    except Exception as e:
        logger.error(f"Telethon ulanishida ogohlantirish: {e}")

    # 4. Set up bot commands in Telegram
    await setup_bot_commands(bot)

    # Searches now run only on user request. Keep existing historical data intact.
    logger.info("✅ Bevosita qidiruv rejimi: fon skanerlashi va statistikani bazaga yig'ish o'chirilgan")


async def on_shutdown() -> None:
    logger.info("Tizim to'xtatilmoqda...")

    # Stop scheduler
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler to'xtatildi")

    # Disconnect Telethon
    try:
        await telegram_client_manager.disconnect()
    except Exception:
        pass

    # Close bot session
    try:
        await bot.session.close()
    except Exception:
        pass

    # Close database pool
    await close_db()
    logger.info("Tizim muvaffaqiyatli to'xtatildi")


async def main() -> None:
    setup_logging(settings.LOG_LEVEL)
    settings.validate_runtime()
    setup_dispatcher()

    try:
        await on_startup()
        logger.info("Telegram Bot polling boshlandi...")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await on_shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Dastur foydalanuvchi tomonidan to'xtatildi")
