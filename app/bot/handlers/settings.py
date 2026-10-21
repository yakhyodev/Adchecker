import json
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from app.database.session import get_db_session
from app.database.repositories.settings_repo import SettingsRepository
from app.database.repositories.admin_repo import AdminRepository
from app.database.repositories.job_repo import JobRepository
from app.database.repositories.ad_repo import AdRepository
from app.database.repositories.channel_repo import ChannelRepository
from app.bot.states.forms import SettingsState
from app.bot.keyboards.inline import get_settings_keyboard
from app.bot.keyboards.reply import get_cancel_keyboard, get_main_menu_keyboard
from app.core.config import settings
from app.core.security import escape_tg_html
from app.telegram_client.client import telegram_client_manager

router = Router(name="settings_router")


@router.message(F.text == "⚙️ Sozlamalar")
@router.message(Command("settings"))
async def handle_settings_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    async with get_db_session() as session:
        repo = SettingsRepository(session)
        auto_enabled = await repo.is_auto_monitoring_enabled()

    text = (
        "⚙️ <b>TIZIM SOZLAMALARI VA BOSHQARUV</b>\n\n"
        "Quyidagi bo'limlardan birini tanlang:"
    )
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=get_settings_keyboard(auto_enabled),
    )


@router.callback_query(F.data == "set:toggle_auto", flags={"requires_write": True})
async def callback_toggle_auto(callback: CallbackQuery) -> None:
    async with get_db_session() as session:
        repo = SettingsRepository(session)
        current = await repo.is_auto_monitoring_enabled()
        new_val = not current
        await repo.set_auto_monitoring_enabled(new_val)

    status_str = "yoqildi" if new_val else "o'chirildi"
    await callback.answer(f"Avtomatik monitoring {status_str}!")
    await callback.message.edit_reply_markup(
        reply_markup=get_settings_keyboard(new_val)
    )


@router.callback_query(F.data == "set:keywords", flags={"requires_write": True})
async def callback_keywords(callback: CallbackQuery, state: FSMContext) -> None:
    async with get_db_session() as session:
        repo = SettingsRepository(session)
        keywords = await repo.get_search_keywords()

    kw_list = "\n".join([f"• <code>{escape_tg_html(k)}</code>" for k in keywords])
    text = (
        "🔑 <b>QIDIRUV KALITLARI</b>\n\n"
        "Hozirgi faol kalit so'zlar:\n"
        f"{kw_list}\n\n"
        "Yangi kalit so'zlarni kiritish uchun vergul bilan ajratib yozing yoki bekor qilishni bosing:"
    )
    await state.set_state(SettingsState.waiting_for_keyword)
    await callback.message.answer(text, parse_mode="HTML", reply_markup=get_cancel_keyboard())
    await callback.answer()


@router.message(SettingsState.waiting_for_keyword, flags={"requires_write": True})
async def process_new_keywords(message: Message, state: FSMContext) -> None:
    raw = message.text.strip()
    if raw in ("⬅️ Ortga", "🏠 Bosh menyu"):
        await state.clear()
        await message.answer("Bekor qilindi.", reply_markup=get_main_menu_keyboard())
        return

    new_keywords = [k.strip() for k in raw.split(",") if k.strip()]
    if not new_keywords:
        await message.answer("❌ Kamida bitta kalit so'z kiritishingiz kerak:")
        return

    async with get_db_session() as session:
        repo = SettingsRepository(session)
        await repo.set_search_keywords(new_keywords)

    await state.clear()
    await message.answer(
        f"✅ <b>Qidiruv kalitlari yangilandi:</b>\n"
        + "\n".join([f"• <code>{escape_tg_html(k)}</code>" for k in new_keywords]),
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard(),
    )


@router.callback_query(F.data == "set:intervals")
async def callback_intervals(callback: CallbackQuery) -> None:
    text = (
        "⏱ <b>REJALASHTIRILGAN INTERVALLAR</b>\n\n"
        f"• Yangi reklamalarni qidirish: <b>har {settings.SCAN_INTERVAL_MINUTES} daqiqada</b>\n"
        f"• Yangi postlar statistikasini yangilash (&lt; 7 kun): <b>har {settings.RECENT_STATS_UPDATE_INTERVAL_HOURS} soatda</b>\n"
        f"• Eski postlar statistikasini yangilash (&gt; 7 kun): <b>har {settings.OLD_STATS_UPDATE_INTERVAL_HOURS} soatda</b>\n\n"
        "<i>Eslatma: Intervallar .env yoki konfiguratsiya orqali boshqariladi.</i>"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Ortga", callback_data="nav:home")]]
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "set:admins")
async def callback_admins_list(callback: CallbackQuery) -> None:
    async with get_db_session() as session:
        repo = AdminRepository(session)
        admins = await repo.get_all()

    admin_lines = []
    for a in admins:
        role_badge = "👑 Superadmin" if a.role == "superadmin" else ("👨‍💼 Admin" if a.role == "admin" else "👀 Viewer")
        name = a.full_name or a.username or str(a.telegram_user_id)
        admin_lines.append(f"• <b>{escape_tg_html(name)}</b> (ID: <code>{a.telegram_user_id}</code>) — {role_badge}")

    text = (
        "👥 <b>ADMINISTRATORLAR RO'YXATI</b>\n\n"
        + "\n".join(admin_lines)
        + "\n\n<i>Superadminlar .env faylidagi ADMIN_IDS orqali belgilanadi.</i>"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Ortga", callback_data="nav:home")]]
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "set:system_status")
async def callback_system_status(callback: CallbackQuery) -> None:
    await callback.answer("Tizim holati tekshirilmoqda...")

    tg_auth = False
    try:
        tg_auth = await telegram_client_manager.is_authorized()
    except Exception:
        pass

    async with get_db_session() as session:
        ad_repo = AdRepository(session)
        ch_repo = ChannelRepository(session)
        job_repo = JobRepository(session)

        total_ads = await ad_repo.count_all()
        channels = await ch_repo.get_all(include_deleted=False)
        active_jobs = await job_repo.get_active_count()
        recent_jobs = await job_repo.get_recent(limit=3)

    jobs_str = "Hozirda faol vazifalar yo'q"
    if recent_jobs:
        jobs_str = "\n".join(
            [f"• [{j.job_type}] Holati: {j.status} (Ads: {j.ads_found})" for j in recent_jobs]
        )

    text = (
        "📊 <b>TIZIM HOLATI VA RESURSLAR</b>\n\n"
        f"🤖 Telegram Bot: 🟢 <b>Faol</b>\n"
        f"📡 Telethon MTProto: {'🟢 <b>Ulangan (Avtorizatsiyadan o\'tgan)</b>' if tg_auth else '🔴 <b>Ulanmagan / Sessiya kerak</b>'}\n"
        f"📢 Monitoringdagi kanallar: <b>{len(channels)} ta</b>\n"
        f"📝 Bazadagi jami reklamalar: <b>{total_ads} ta</b>\n"
        f"⚙️ Hozirda ishlayotgan vazifalar: <b>{active_jobs} ta</b>\n\n"
        f"<b>Oxirgi monitoring vazifalari:</b>\n{jobs_str}"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Ortga", callback_data="nav:home")]]
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
