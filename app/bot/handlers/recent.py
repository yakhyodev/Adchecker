from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from app.database.session import get_db_session
from app.database.repositories.ad_repo import AdRepository
from app.database.repositories.snapshot_repo import SnapshotRepository
from app.bot.keyboards.inline import get_recent_ads_pagination_keyboard
from app.core.security import escape_tg_html, truncate_message
from app.core.timezone import format_tashkent

router = Router(name="recent_ads_router")


async def render_ad_page(ad_id: int, page: int, total_pages: int) -> tuple[str, str]:
    """Renders formatted ad details text and returns (text, post_url)."""
    async with get_db_session() as session:
        ad_repo = AdRepository(session)
        snap_repo = SnapshotRepository(session)

        ad = await ad_repo.get_by_id(ad_id)
        if not ad:
            return "Post topilmadi.", ""

        channel_title = escape_tg_html(ad.channel.title if ad.channel else "Noma'lum")
        posted_at_str = format_tashkent(ad.posted_at)
        updated_at_str = format_tashkent(ad.last_updated_at)
        views_str = f"{ad.views:,}" if ad.views is not None else "Noma'lum"
        reactions_str = f"{ad.reactions:,}" if ad.reactions is not None else "0"
        forwards_str = f"{ad.forwards:,}" if ad.forwards is not None else "0"
        media_str = ad.media_type or "matn"

        # Check 24-hour growth if available
        growth_info = await snap_repo.calculate_growth(ad.id, ad.views, hours_ago=24)
        growth_text = ""
        if growth_info:
            g_views = growth_info["growth_views"]
            g_pct = growth_info["growth_percent"]
            arrow = "📈 +" if g_views >= 0 else "📉 "
            growth_text = f"\n📊 <b>24 soatlik o'sish:</b> {arrow}{g_views:,} ({g_pct}%)"

        snippet = ""
        if ad.post_text:
            cleaned = truncate_message(ad.post_text.strip(), 180)
            snippet = f"\n\n💬 <i>\"{escape_tg_html(cleaned)}\"</i>"

        text = (
            f"🆕 <b>OXIRGI REKLAMALAR ({page}/{total_pages})</b>\n\n"
            f"📢 <b>Kanal:</b> {channel_title}\n"
            f"📅 <b>Joylashtirilgan sana:</b> {posted_at_str}\n"
            f"👁 <b>Ko'rishlar:</b> {views_str}\n"
            f"❤️ <b>Reaksiyalar:</b> {reactions_str}\n"
            f"↪️ <b>Forwardlar:</b> {forwards_str}\n"
            f"📁 <b>Media turi:</b> {media_str}"
            f"{growth_text}\n"
            f"🔄 <b>Statistika yangilangan:</b> {updated_at_str}"
            f"{snippet}"
        )
        return text, ad.post_url


@router.message(F.text == "🆕 Oxirgi reklamalar")
@router.message(Command("recent"))
async def handle_recent_ads(message: Message, state: FSMContext) -> None:
    await state.clear()
    async with get_db_session() as session:
        ad_repo = AdRepository(session)
        total_ads = await ad_repo.count_all()

        if total_ads == 0:
            await message.answer(
                "ℹ️ Hozircha bazada hech qanday reklama posti mavjud emas.\n\n"
                "Kanal qo'shish va qidirish uchun <b>📢 Kanallar</b> bo'limiga o'ting.",
                parse_mode="HTML",
            )
            return

        recent_ads = await ad_repo.get_recent(limit=1, offset=0)
        if not recent_ads:
            await message.answer("Postlar topilmadi.")
            return

        first_ad = recent_ads[0]
        text, post_url = await render_ad_page(first_ad.id, page=1, total_pages=total_ads)
        markup = get_recent_ads_pagination_keyboard(
            post_url=post_url, current_page=1, total_pages=total_ads
        )
        await message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data.startswith("ad:page:"))
async def callback_paginate_ads(callback: CallbackQuery) -> None:
    page = int(callback.data.split(":")[2])
    async with get_db_session() as session:
        ad_repo = AdRepository(session)
        total_ads = await ad_repo.count_all()

        if total_ads == 0:
            await callback.answer("Postlar mavjud emas", show_alert=True)
            return

        page = max(1, min(page, total_ads))
        ads = await ad_repo.get_recent(limit=1, offset=page - 1)
        if not ads:
            await callback.answer("Sahifa topilmadi", show_alert=True)
            return

        ad = ads[0]
        text, post_url = await render_ad_page(ad.id, page=page, total_pages=total_ads)
        markup = get_recent_ads_pagination_keyboard(
            post_url=post_url, current_page=page, total_pages=total_ads
        )
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
        await callback.answer()
