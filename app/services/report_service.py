from datetime import datetime, date, timezone, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.advertisement import Advertisement
from app.database.repositories.ad_repo import AdRepository
from app.core.timezone import (
    to_tashkent,
    format_tashkent,
    get_date_range_boundaries_utc,
)


class ReportService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.ad_repo = AdRepository(session)

    async def get_period_report(
        self,
        start_utc: datetime,
        end_utc: datetime,
        channel_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Calculates comprehensive statistics for all ads posted within the UTC boundaries."""
        ads = await self.ad_repo.get_ads_in_period(start_utc, end_utc, channel_id)

        total_ads = len(ads)
        unique_channels = {ad.channel_id for ad in ads if ad.channel}
        total_channels = len(unique_channels)

        views_list = [ad.views for ad in ads if ad.views is not None]
        total_views = sum(views_list) if views_list else 0
        avg_views = round(total_views / len(views_list)) if views_list else 0

        reactions_list = [ad.reactions for ad in ads if ad.reactions is not None]
        total_reactions = sum(reactions_list) if reactions_list else 0

        forwards_list = [ad.forwards for ad in ads if ad.forwards is not None]
        total_forwards = sum(forwards_list) if forwards_list else 0

        # Find top ad
        top_ad = None
        if views_list:
            top_ad_obj = max(ads, key=lambda a: a.views or 0)
            top_ad = {
                "id": top_ad_obj.id,
                "channel_title": top_ad_obj.channel.title if top_ad_obj.channel else "",
                "views": top_ad_obj.views or 0,
                "reactions": top_ad_obj.reactions or 0,
                "post_url": top_ad_obj.post_url,
                "posted_at": format_tashkent(top_ad_obj.posted_at),
            }

        # Channel statistics breakdown
        channels_map: Dict[int, Dict[str, Any]] = {}
        for ad in ads:
            ch = ad.channel
            if not ch:
                continue
            if ch.id not in channels_map:
                channels_map[ch.id] = {
                    "id": ch.id,
                    "title": ch.title,
                    "url": ch.url,
                    "ads_count": 0,
                    "total_views": 0,
                    "views_count": 0,
                    "max_views": 0,
                    "total_reactions": 0,
                    "cpm_price": float(ch.cpm_price) if ch.cpm_price else None,
                    "last_ad_date": ad.posted_at,
                }

            entry = channels_map[ch.id]
            entry["ads_count"] += 1
            if ad.views is not None:
                entry["total_views"] += ad.views
                entry["views_count"] += 1
                if ad.views > entry["max_views"]:
                    entry["max_views"] = ad.views
            if ad.reactions is not None:
                entry["total_reactions"] += ad.reactions
            if ad.posted_at > entry["last_ad_date"]:
                entry["last_ad_date"] = ad.posted_at

        channel_stats: List[Dict[str, Any]] = []
        for ch_id, data in channels_map.items():
            cnt = data["views_count"]
            avg = round(data["total_views"] / cnt) if cnt > 0 else 0
            cpm = None
            if data["cpm_price"] and data["total_views"] > 0:
                # CPM = (cost / views) * 1000
                cpm = round((data["cpm_price"] / data["total_views"]) * 1000, 2)

            channel_stats.append(
                {
                    "channel_id": data["id"],
                    "title": data["title"],
                    "url": data["url"],
                    "ads_count": data["ads_count"],
                    "total_views": data["total_views"],
                    "avg_views": avg,
                    "max_views": data["max_views"],
                    "total_reactions": data["total_reactions"],
                    "cpm_price": data["cpm_price"],
                    "cpm": cpm,
                    "last_ad_date": format_tashkent(data["last_ad_date"], "%Y-%m-%d"),
                }
            )

        # Sort channels by total_views descending
        channel_stats.sort(key=lambda c: c["total_views"], reverse=True)

        # Daily breakdown (grouped by Tashkent date)
        daily_map: Dict[str, Dict[str, Any]] = {}
        for ad in ads:
            local_dt = to_tashkent(ad.posted_at)
            day_str = local_dt.strftime("%Y-%m-%d")
            if day_str not in daily_map:
                daily_map[day_str] = {
                    "date": day_str,
                    "ads_count": 0,
                    "total_views": 0,
                    "views_count": 0,
                }
            daily_map[day_str]["ads_count"] += 1
            if ad.views is not None:
                daily_map[day_str]["total_views"] += ad.views
                daily_map[day_str]["views_count"] += 1

        daily_stats = []
        for day_str in sorted(daily_map.keys()):
            d = daily_map[day_str]
            avg = round(d["total_views"] / d["views_count"]) if d["views_count"] > 0 else 0
            daily_stats.append(
                {
                    "date": day_str,
                    "ads_count": d["ads_count"],
                    "total_views": d["total_views"],
                    "avg_views": avg,
                }
            )

        # Monthly breakdown (for yearly view)
        monthly_map: Dict[str, Dict[str, Any]] = {}
        for ad in ads:
            local_dt = to_tashkent(ad.posted_at)
            m_str = local_dt.strftime("%Y-%m")
            if m_str not in monthly_map:
                monthly_map[m_str] = {
                    "month": m_str,
                    "ads_count": 0,
                    "total_views": 0,
                    "views_count": 0,
                }
            monthly_map[m_str]["ads_count"] += 1
            if ad.views is not None:
                monthly_map[m_str]["total_views"] += ad.views
                monthly_map[m_str]["views_count"] += 1

        monthly_stats = []
        for m_str in sorted(monthly_map.keys()):
            m = monthly_map[m_str]
            avg = round(m["total_views"] / m["views_count"]) if m["views_count"] > 0 else 0
            monthly_stats.append(
                {
                    "month": m_str,
                    "ads_count": m["ads_count"],
                    "total_views": m["total_views"],
                    "avg_views": avg,
                }
            )

        # Find latest updated at
        last_updated = None
        if ads:
            last_updated = max(ads, key=lambda a: a.last_updated_at).last_updated_at

        return {
            "start_dt": format_tashkent(start_utc),
            "end_dt": format_tashkent(end_utc),
            "total_ads": total_ads,
            "total_channels": total_channels,
            "total_views": total_views,
            "avg_views": avg_views,
            "total_reactions": total_reactions,
            "total_forwards": total_forwards,
            "top_ad": top_ad,
            "channel_stats": channel_stats,
            "daily_stats": daily_stats,
            "monthly_stats": monthly_stats,
            "last_updated_at": format_tashkent(last_updated),
            "ads": ads,
        }

    async def get_last_7_days_report(self) -> Dict[str, Any]:
        now_utc = datetime.now(timezone.utc)
        start_utc = now_utc - timedelta(days=7)
        return await self.get_period_report(start_utc, now_utc)

    async def get_last_30_days_report(self) -> Dict[str, Any]:
        now_utc = datetime.now(timezone.utc)
        start_utc = now_utc - timedelta(days=30)
        return await self.get_period_report(start_utc, now_utc)

    async def get_last_365_days_report(self) -> Dict[str, Any]:
        now_utc = datetime.now(timezone.utc)
        start_utc = now_utc - timedelta(days=365)
        return await self.get_period_report(start_utc, now_utc)

    async def get_custom_date_report(
        self, start_date: date, end_date: date
    ) -> Dict[str, Any]:
        start_utc, end_utc = get_date_range_boundaries_utc(start_date, end_date)
        return await self.get_period_report(start_utc, end_utc)
