from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Callable
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.channel import Channel
from app.database.models.advertisement import Advertisement
from app.database.repositories.channel_repo import ChannelRepository
from app.database.repositories.ad_repo import AdRepository
from app.database.repositories.snapshot_repo import SnapshotRepository
from app.database.repositories.job_repo import JobRepository
from app.database.repositories.settings_repo import SettingsRepository
from app.telegram_client.client import (
    TelegramClientManager,
    telegram_client_manager,
    TelegramFloodWaitException,
    TelegramClientError,
)
from app.core.logging import logger


class MonitoringService:
    def __init__(
        self,
        session: AsyncSession,
        tg_client: TelegramClientManager = telegram_client_manager,
    ):
        self.session = session
        self.tg_client = tg_client
        self.channel_repo = ChannelRepository(session)
        self.ad_repo = AdRepository(session)
        self.snapshot_repo = SnapshotRepository(session)
        self.job_repo = JobRepository(session)
        self.settings_repo = SettingsRepository(session)

    async def run_channel_initial_scan(
        self,
        channel_id: int,
        days_limit: Optional[int] = None,
        notify_callback: Optional[Callable[[Advertisement, Channel], Any]] = None,
    ) -> Dict[str, Any]:
        """Runs initial or on-demand scan for a single channel.
        Concurrency controlled: skips if another scan is in progress.
        """
        # Concurrency check
        if await self.job_repo.has_active_job(channel_id, "initial_scan"):
            return {
                "status": "already_running",
                "message": "Ushbu kanal uchun skanerlash jarayoni allaqachon davom etmoqda.",
            }

        channel = await self.channel_repo.get_by_id(channel_id)
        if not channel:
            return {"status": "error", "message": "Kanal bazadan topilmadi."}

        job = await self.job_repo.create_job(
            job_type="initial_scan", channel_id=channel_id, status="scanning"
        )

        min_date_utc = None
        if days_limit is not None and days_limit > 0:
            min_date_utc = datetime.now(timezone.utc) - timedelta(days=days_limit)

        keywords = await self.settings_repo.get_search_keywords()

        ads_found = 0
        posts_scanned = 0
        max_message_id = channel.last_scanned_message_id or 0

        try:
            target = channel.username or channel.telegram_channel_id
            resolved = await self.tg_client.resolve_channel(str(target))
            entity = resolved["entity"]

            async for ad_data in self.tg_client.scan_channel_ads(
                entity=entity,
                keywords=keywords,
                min_date_utc=min_date_utc,
            ):
                posts_scanned += 1
                msg_id = ad_data["message_id"]
                if msg_id > max_message_id:
                    max_message_id = msg_id

                ad, is_new = await self.ad_repo.upsert_ad(
                    channel_id=channel.id,
                    message_id=msg_id,
                    post_url=ad_data["post_url"],
                    post_text=ad_data["post_text"],
                    posted_at=ad_data["posted_at"],
                    media_type=ad_data["media_type"],
                    views=ad_data["views"],
                    reactions=ad_data["reactions"],
                    forwards=ad_data["forwards"],
                )

                # Record snapshot
                await self.snapshot_repo.add_snapshot(
                    advertisement_id=ad.id,
                    views=ad.views,
                    reactions=ad.reactions,
                    forwards=ad.forwards,
                    recorded_at=datetime.now(timezone.utc),
                )

                if is_new:
                    ads_found += 1
                    if notify_callback:
                        try:
                            await notify_callback(ad, channel)
                        except Exception as ne:
                            logger.error(f"Bildirishnoma yuborishda xatolik: {ne}")

            # Update channel scan metadata
            await self.channel_repo.update_scan_state(
                channel_id=channel.id,
                last_msg_id=max_message_id,
                scanned_at=datetime.now(timezone.utc),
            )

            await self.job_repo.update_status(
                job_id=job.id,
                status="completed",
                posts_scanned=posts_scanned,
                ads_found=ads_found,
            )

            return {
                "status": "completed",
                "channel_id": channel_id,
                "posts_scanned": posts_scanned,
                "ads_found": ads_found,
            }

        except TelegramFloodWaitException as fe:
            await self.job_repo.update_status(
                job_id=job.id,
                status="failed",
                posts_scanned=posts_scanned,
                ads_found=ads_found,
                error_message=f"FloodWait: {fe.seconds} soniya kuting",
            )
            return {"status": "flood_wait", "seconds": fe.seconds}
        except Exception as e:
            logger.error(f"Kanalni skanerlashda xatolik (ch={channel_id}): {e}")
            await self.job_repo.update_status(
                job_id=job.id,
                status="failed",
                posts_scanned=posts_scanned,
                ads_found=ads_found,
                error_message=str(e),
            )
            return {"status": "error", "message": str(e)}

    async def run_incremental_scan(
        self,
        notify_callback: Optional[Callable[[Advertisement, Channel], Any]] = None,
    ) -> Dict[str, Any]:
        """Scans all active channels for newly published ads since last scan."""
        channels = await self.channel_repo.get_all_active()
        keywords = await self.settings_repo.get_search_keywords()

        total_new_ads = 0
        total_scanned = 0

        for channel in channels:
            try:
                target = channel.username or channel.telegram_channel_id
                resolved = await self.tg_client.resolve_channel(str(target))
                entity = resolved["entity"]

                min_id = channel.last_scanned_message_id or 0
                max_msg_id = min_id

                async for ad_data in self.tg_client.scan_channel_ads(
                    entity=entity,
                    keywords=keywords,
                    min_id=min_id,
                ):
                    total_scanned += 1
                    msg_id = ad_data["message_id"]
                    if msg_id > max_msg_id:
                        max_msg_id = msg_id

                    ad, is_new = await self.ad_repo.upsert_ad(
                        channel_id=channel.id,
                        message_id=msg_id,
                        post_url=ad_data["post_url"],
                        post_text=ad_data["post_text"],
                        posted_at=ad_data["posted_at"],
                        media_type=ad_data["media_type"],
                        views=ad_data["views"],
                        reactions=ad_data["reactions"],
                        forwards=ad_data["forwards"],
                    )

                    await self.snapshot_repo.add_snapshot(
                        advertisement_id=ad.id,
                        views=ad.views,
                        reactions=ad.reactions,
                        forwards=ad.forwards,
                        recorded_at=datetime.now(timezone.utc),
                    )

                    if is_new:
                        total_new_ads += 1
                        if notify_callback:
                            try:
                                await notify_callback(ad, channel)
                            except Exception as ne:
                                logger.error(f"Bildirishnoma yuborish xatosi: {ne}")

                await self.channel_repo.update_scan_state(
                    channel_id=channel.id,
                    last_msg_id=max_msg_id,
                    scanned_at=datetime.now(timezone.utc),
                )

            except TelegramFloodWaitException as fe:
                logger.warning(f"Incremental scan to'xtatildi (FloodWait {fe.seconds}s)")
                break
            except Exception as e:
                logger.error(f"Incremental scan xatosi ({channel.title}): {e}")
                continue

        return {
            "status": "completed",
            "channels_scanned": len(channels),
            "new_ads_found": total_new_ads,
        }

    async def run_stats_update(self, update_type: str = "recent") -> Dict[str, Any]:
        """Updates views and reactions of existing ads in the database.
        - recent: ads posted in the last 7 days.
        - old: ads posted older than 7 days.
        """
        now = datetime.now(timezone.utc)
        if update_type == "recent":
            min_posted = now - timedelta(days=7)
            max_posted = None
        else:
            min_posted = None
            max_posted = now - timedelta(days=7)

        ads = await self.ad_repo.get_active_ads_for_stats_update(
            min_posted_at=min_posted,
            max_posted_at=max_posted,
        )

        updated_count = 0
        deleted_count = 0
        failed_count = 0

        # Group ads by channel for efficiency
        channel_cache: Dict[int, Any] = {}

        for ad in ads:
            try:
                channel = ad.channel
                if not channel or channel.is_deleted:
                    continue

                if channel.id not in channel_cache:
                    target = channel.username or channel.telegram_channel_id
                    resolved = await self.tg_client.resolve_channel(str(target))
                    channel_cache[channel.id] = resolved["entity"]

                entity = channel_cache[channel.id]
                is_available, views, reactions, forwards = (
                    await self.tg_client.fetch_message_stats(entity, ad.message_id)
                )

                if not is_available:
                    # Message was deleted from Telegram
                    await self.ad_repo.mark_as_deleted(ad.id)
                    deleted_count += 1
                else:
                    # Update metrics and create snapshot
                    ad.views = views
                    ad.reactions = reactions
                    ad.forwards = forwards
                    ad.last_updated_at = now
                    await self.snapshot_repo.add_snapshot(
                        advertisement_id=ad.id,
                        views=views,
                        reactions=reactions,
                        forwards=forwards,
                        recorded_at=now,
                    )
                    updated_count += 1

            except TelegramFloodWaitException as fe:
                logger.warning(f"Stats update to'xtatildi (FloodWait {fe.seconds}s)")
                failed_count += 1
                break
            except Exception as e:
                logger.error(f"Ad {ad.id} statistikasini yangilashda xato: {e}")
                failed_count += 1
                continue

        return {
            "status": "partial" if failed_count else "completed",
            "type": update_type,
            "updated": updated_count,
            "deleted": deleted_count,
            "failed": failed_count,
        }
