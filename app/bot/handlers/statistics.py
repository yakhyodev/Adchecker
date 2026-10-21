import asyncio
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from app.database.session import get_db_session
from app.services.report_service import ReportService
from app.services.monitoring import MonitoringService
from app.bot.keyboards.inline import get_report_actions_keyboard
from app.core.security import escape_tg_html

router = Router(name="statistics_router")


def format_summary_message(title: str, report: dict, period_type: str) -> str:
    """Formats report summary for Telegram message."""
    total_ads = report["total_ads"]
    total_channels = report["total_channels"]
    total_views = report["total_views"]
    avg_views = report["avg_views"]
    total_reactions = report["total_reactions"]
    start_dt = report["start_dt"]
    end_dt = report["end_dt"]
    last_up = report["last_updated_at"]

    if total_ads == 0:
        return (
            f"{title}\n\n"
            f"📅 <b>Davr:</b> {start_dt} — {end_dt}\n\n"
            f"ℹ️ Ushbu davrda hech qanday reklama posti topilmadi."
        )

    lines = [
        f"{title}\n",
        f"📅 <b>Davr:</b> {start_dt} — {end_dt}",
        f"📊 <b>Reklamalar soni:</b> {total_ads} ta",
        f"📢 <b>Qatnashgan kanallar:</b> {total_channels} ta",
        f"👁 <b>Umumiy ko'rishlar:</b> {total_views:,}",
        f"📈 <b>O'rtacha ko'rish (har bir post):</b> {avg_views:,}",
        f"❤️ <b>Reaksiyalar yig'indisi:</b> {total_reactions:,}",
    ]

    # Top Ad
    top_ad = report.get("top_ad")
    if top_ad:
        lines.append(
            f"\n🔥 <b>Eng ko'p ko'rilgan reklama:</b>\n"
            f"• Kanal: <b>{escape_tg_html(top_ad['channel_title'])}</b>\n"
            f"• Ko'rishlar: <b>{top_ad['views']:,}</b> | Reaksiyalar: <b>{top_ad['reactions']:,}</b>\n"
            f"• Havola: {top_ad['post_url']}"
        )

    # Top Channels
    channel_stats = report.get("channel_stats", [])
    if channel_stats:
        lines.append("\n🏆 <b>Eng samarali kanallar (Top 5):</b>")
        for i, ch in enumerate(channel_stats[:5], start=1):
            cpm_str = f" | CPM: {ch['cpm']:,.2f} so'm" if ch.get("cpm") else ""
            lines.append(
                f"{i}. <b>{escape_tg_html(ch['title'])}</b>: {ch['total_views']:,} ko'rish "
                f"({ch['ads_count']} ta post, o'rtacha: {ch['avg_views']:,}{cpm_str})"
            )

    # Monthly breakdown for year
    monthly_stats = report.get("monthly_stats", [])
    if period_type == "year" and monthly_stats:
        lines.append("\n📆 <b>Oylik xulosa (so'nggi oylar):</b>")
        for m in monthly_stats[-6:]:
            lines.append(
                f"• {m['month']}: {m['ads_count']} ta post | {m['total_views']:,} ko'rish"
            )

    lines.append(f"\n🔄 <i>Statistikalar oxirgi yangilangan: {last_up}</i>")
    return "\n".join(lines)


@router.message(F.text == "📅 Oxirgi hafta")
@router.message(Command("stats_week"))
async def handle_stats_week(message: Message, state: FSMContext) -> None:
    await state.clear()
    wait_msg = await message.answer("⏳ 7 kunlik ma'lumotlar tahlil qilinmoqda...")
    async with get_db_session() as session:
        service = ReportService(session)
        rep = await service.get_last_7_days_report()
        text = format_summary_message("📅 <b>OXIRGI 7 KUNLIK REKLAMA STATISTIKASI</b>", rep, "week")
        await wait_msg.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=get_report_actions_keyboard("week"),
            disable_web_page_preview=True,
        )


@router.message(F.text == "🗓 Oxirgi oy")
@router.message(Command("stats_month"))
async def handle_stats_month(message: Message, state: FSMContext) -> None:
    await state.clear()
    wait_msg = await message.answer("⏳ 30 kunlik ma'lumotlar tahlil qilinmoqda...")
    async with get_db_session() as session:
        service = ReportService(session)
        rep = await service.get_last_30_days_report()
        text = format_summary_message("🗓 <b>OXIRGI 30 KUNLIK REKLAMA STATISTIKASI</b>", rep, "month")
        await wait_msg.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=get_report_actions_keyboard("month"),
            disable_web_page_preview=True,
        )


@router.message(F.text == "📈 Oxirgi yil")
@router.message(Command("stats_year"))
async def handle_stats_year(message: Message, state: FSMContext) -> None:
    await state.clear()
    wait_msg = await message.answer("⏳ 365 kunlik ma'lumotlar tahlil qilinmoqda...")
    async with get_db_session() as session:
        service = ReportService(session)
        rep = await service.get_last_365_days_report()
        text = format_summary_message("📈 <b>OXIRGI 365 KUNLIK REKLAMA STATISTIKASI</b>", rep, "year")
        await wait_msg.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=get_report_actions_keyboard("year"),
            disable_web_page_preview=True,
        )


@router.callback_query(F.data.startswith("stats:refresh:"))
async def callback_refresh_stats_view(callback: CallbackQuery) -> None:
    rep_type = callback.data.split(":")[2]
    await callback.answer("Statistika qayta yuklanmoqda...")
    async with get_db_session() as session:
        service = ReportService(session)
        if rep_type == "week":
            rep = await service.get_last_7_days_report()
            title = "📅 <b>OXIRGI 7 KUNLIK REKLAMA STATISTIKASI</b>"
        elif rep_type == "month":
            rep = await service.get_last_30_days_report()
            title = "🗓 <b>OXIRGI 30 KUNLIK REKLAMA STATISTIKASI</b>"
        elif rep_type == "year":
            rep = await service.get_last_365_days_report()
            title = "📈 <b>OXIRGI 365 KUNLIK REKLAMA STATISTIKASI</b>"
        else:
            rep = await service.get_last_7_days_report()
            title = "📊 <b>REKLAMA STATISTIKASI</b>"

        text = format_summary_message(title, rep, rep_type)
        try:
            await callback.message.edit_text(
                text,
                parse_mode="HTML",
                reply_markup=get_report_actions_keyboard(rep_type),
                disable_web_page_preview=True,
            )
        except Exception:
            pass


@router.message(F.text == "🔄 Statistikani yangilash")
@router.message(Command("refresh"))
async def handle_manual_refresh(message: Message, state: FSMContext) -> None:
    await state.clear()
    wait_msg = await message.answer(
        "🔄 <b>Statistikalarni yangilash boshlandi...</b>\n\n"
        "Barcha kanallardagi yangi reklamalar tekshirilmoqda va mavjud postlarning "
        "ko'rishlar soni yangilanmoqda. Bu biroz vaqt olishi mumkin.",
        parse_mode="HTML",
    )

    async def _do_refresh():
        try:
            async with get_db_session() as session:
                mon_service = MonitoringService(session)
                disc_res = await mon_service.run_incremental_scan()
                stat_res = await mon_service.run_stats_update(update_type="recent")

                text = (
                    "✅ <b>Statistikalar muvaffaqiyatli yangilandi!</b>\n\n"
                    f"📢 Tekshirilgan kanallar: <b>{disc_res.get('channels_scanned', 0)} ta</b>\n"
                    f"🎯 Yangi topilgan reklamalar: <b>{disc_res.get('new_ads_found', 0)} ta</b>\n"
                    f"🔄 Ko'rishlari yangilangan postlar: <b>{stat_res.get('updated', 0)} ta</b>\n"
                    f"🗑 O'chirilgan postlar qayd etildi: <b>{stat_res.get('deleted', 0)} ta</b>"
                )
                await wait_msg.edit_text(text, parse_mode="HTML")
        except Exception as e:
            await wait_msg.edit_text(f"❌ Yangilashda xatolik yuz berdi: {escape_tg_html(str(e))}")

    asyncio.create_task(_do_refresh())
