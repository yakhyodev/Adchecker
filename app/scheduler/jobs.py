import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.core.logging import logger
from app.core.timezone import format_tashkent
from app.core.security import escape_tg_html
from app.database.session import get_db_session
from app.database.repositories.admin_repo import AdminRepository
from app.database.repositories.settings_repo import SettingsRepository
from app.database.models.advertisement import Advertisement
from app.database.models.channel import Channel
from app.services.monitoring import MonitoringService
from app.bot.bot_instance import bot

scheduler = AsyncIOScheduler()


async def send_new_ad_notification(ad: Advertisement, channel: Channel) -> None:
    """Sends instant notification to active administrators when a new ad is found."""
    if not settings.NOTIFY_ADMINS_ON_NEW_AD:
        return

    ch_title = escape_tg_html(channel.title)
    posted_date = format_tashkent(ad.posted_at)
    views_str = f"{ad.views:,}" if ad.views is not None else "Hozircha yo'q"

    text = (
        "🆕 <b>YANGI IMKON REKLAMASI ANIQLANDI!</b>\n\n"
        f"📢 <b>Kanal:</b> {ch_title}\n"
        f"📅 <b>Sana:</b> {posted_date}\n"
        f"👁 <b>Ko'rishlar:</b> {views_str}\n"
        f"🔗 <b>Reklamani ochish:</b> {ad.post_url}"
    )

    try:
        async with get_db_session() as session:
            repo = AdminRepository(session)
            admins = await repo.get_all()
            for admin in admins:
                if admin.is_active:
                    try:
                        await bot.send_message(
                            chat_id=admin.telegram_user_id,
                            text=text,
                            parse_mode="HTML",
                            disable_web_page_preview=False,
                        )
                    except Exception as e:
                        logger.warning(
                            f"Admin {admin.telegram_user_id} ga bildirishnoma yuborilmadi: {e}"
                        )
    except Exception as e:
        logger.error(f"Bildirishnoma tarqatishda xatolik: {e}")


async def job_scan_new_ads() -> None:
    """Scheduled task to discover new ads across all active channels."""
    try:
        async with get_db_session() as session:
            settings_repo = SettingsRepository(session)
            if not await settings_repo.is_auto_monitoring_enabled():
                logger.info("Avto-monitoring o'chirilgan, skanerlash o'tkazib yuborildi")
                return

            mon_service = MonitoringService(session)
            res = await mon_service.run_incremental_scan(
                notify_callback=send_new_ad_notification
            )
            logger.info(
                f"Yangi reklamalarni skanerlash yakunlandi: "
                f"{res.get('new_ads_found', 0)} ta yangi reklama topildi"
            )
    except Exception as e:
        logger.error(f"job_scan_new_ads xatosi: {e}")


async def job_update_recent_stats() -> None:
    """Scheduled task to update stats for ads posted in the last 7 days."""
    try:
        async with get_db_session() as session:
            settings_repo = SettingsRepository(session)
            if not await settings_repo.is_auto_monitoring_enabled():
                return

            mon_service = MonitoringService(session)
            res = await mon_service.run_stats_update(update_type="recent")
            logger.info(
                f"Yaqindagi reklamalar statistikasi yangilandi: {res.get('updated', 0)} ta yangilandi"
            )
    except Exception as e:
        logger.error(f"job_update_recent_stats xatosi: {e}")


async def job_update_old_stats() -> None:
    """Scheduled task to update stats for older ads (> 7 days)."""
    try:
        async with get_db_session() as session:
            settings_repo = SettingsRepository(session)
            if not await settings_repo.is_auto_monitoring_enabled():
                return

            mon_service = MonitoringService(session)
            res = await mon_service.run_stats_update(update_type="old")
            logger.info(
                f"Eski reklamalar statistikasi yangilandi: {res.get('updated', 0)} ta yangilandi"
            )
    except Exception as e:
        logger.error(f"job_update_old_stats xatosi: {e}")


def setup_scheduler() -> AsyncIOScheduler:
    """Configures scheduled background jobs."""
    # 1. Scan new ads: default every 60 minutes
    scheduler.add_job(
        job_scan_new_ads,
        trigger=IntervalTrigger(minutes=settings.SCAN_INTERVAL_MINUTES),
        id="job_scan_new_ads",
        replace_existing=True,
    )

    # 2. Update recent stats (< 7 days): default every 3 hours
    scheduler.add_job(
        job_update_recent_stats,
        trigger=IntervalTrigger(hours=settings.RECENT_STATS_UPDATE_INTERVAL_HOURS),
        id="job_update_recent_stats",
        replace_existing=True,
    )

    # 3. Update older stats (> 7 days): default daily
    scheduler.add_job(
        job_update_old_stats,
        trigger=IntervalTrigger(hours=settings.OLD_STATS_UPDATE_INTERVAL_HOURS),
        id="job_update_old_stats",
        replace_existing=True,
    )

    return scheduler
