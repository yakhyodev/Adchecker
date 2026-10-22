from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from app.database.session import get_db_session
from app.services.channel_service import ChannelService
from app.bot.handlers.search import cancel_search, periods_keyboard, ask_keywords
from app.bot.states.forms import AddChannelState, ChannelPriceState
from app.bot.keyboards.inline import (
    get_channels_menu_keyboard,
    get_channels_list_keyboard,
    get_channel_details_keyboard,
    get_delete_confirmation_keyboard,
)
from app.bot.keyboards.reply import get_cancel_keyboard, get_main_menu_keyboard
from app.core.security import escape_tg_html
from app.telegram_client.client import ChannelNotFoundError, ChannelAccessDeniedError
from app.core.logging import logger

router = Router(name="channels_router")


@router.message(F.text == "📢 Kanallar")
@router.message(Command("channels"))
async def handle_channels_menu(message: Message, state: FSMContext) -> None:
    cancel_search(message.chat.id, message.from_user.id)
    await state.clear()
    text = (
        "📢 <b>KANALLARNI BOSHQARISH</b>\n\n"
        "Qidiruv faqat shu ro'yxatdagi faol kanallarda ishlaydi. "
        "Kanallarni bir xabarda qo'shish, ro'yxatdan ko'rish yoki olib tashlash mumkin."
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_channels_menu_keyboard())


@router.callback_query(F.data == "chan:menu")
async def callback_channels_menu(callback: CallbackQuery, state: FSMContext) -> None:
    cancel_search(callback.message.chat.id, callback.from_user.id)
    await state.clear()
    text = (
        "📢 <b>KANALLARNI BOSHQARISH</b>\n\n"
        "Kerakli amalni tanlang:"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_channels_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "chan:add", flags={"requires_write": True})
async def callback_add_channel_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    cancel_search(callback.message.chat.id, callback.from_user.id)
    await state.clear()
    await state.set_state(AddChannelState.waiting_for_url)
    text = (
        "➕ <b>YANGI KANAL QO'SHISH</b>\n\n"
        "Bir yoki ko'p kanal havolasi / username'ini yuboring. "
        "Ularni bo'shliq yoki yangi qator bilan ajrating.\n"
        "Barcha kanallar Telegram ID orqali saqlanadi, takroriylari qayta qo'shilmaydi.\n\n"
        "<i>Qabul qilinadigan formatlar:</i>\n"
        "• <code>https://t.me/kanal_nomi</code>\n"
        "• <code>https://t.me/s/kanal_nomi</code>\n"
        "• <code>@kanal_nomi</code>\n"
        "• <code>kanal_nomi</code>\n\n"
        "<code>@kanal_bir https://t.me/kanal_ikki\n@kanal_uch</code>"
    )
    await callback.message.answer(text, parse_mode="HTML", reply_markup=get_cancel_keyboard())
    await callback.answer()


@router.message(AddChannelState.waiting_for_url, flags={"requires_write": True})
async def process_channel_input(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("Kanal havolalarini matn ko'rinishida yuboring.")
        return
    raw_text = message.text.strip()
    if raw_text in ("⬅️ Ortga", "🏠 Bosh menyu"):
        await state.clear()
        await message.answer("Amal bekor qilindi.", reply_markup=get_main_menu_keyboard())
        return

    wait_msg = await message.answer("⏳ Yuborilgan kanallar tekshirilib, Telegram ID bilan saqlanmoqda...")

    try:
        async with get_db_session() as session:
            service = ChannelService(session)
            results = await service.add_channels(raw_text)

        added = sum(item.status == "added" for item in results)
        duplicates = sum(item.status == "duplicate" for item in results)
        errors = sum(item.status == "error" for item in results)
        await wait_msg.edit_text(f"✅ Saqlandi: {added}\nℹ️ Avval saqlangan: {duplicates}\n⚠️ Saqlanmadi: {errors}")
        chunk = ""
        for item in results:
            label = escape_tg_html((item.title or item.supplied)[:150])
            detail = f"<code>{item.telegram_id}</code>" if item.telegram_id else escape_tg_html(item.detail)
            icon = {"added": "✅", "duplicate": "ℹ️", "error": "⚠️"}[item.status]
            line = f"{icon} {label} — {detail}\n"
            if len(chunk) + len(line) > 3500:
                await message.answer(chunk)
                chunk = ""
            chunk += line
        if chunk:
            await message.answer(chunk)

        await state.clear()
        await message.answer("Kerakli amalni tanlang:", reply_markup=get_main_menu_keyboard())

    except ChannelNotFoundError:
        await wait_msg.edit_text(
            "❌ <b>Kanal topilmadi!</b>\n\n"
            "Kanal username yoki havolasini to'g'ri kiritganingizni tekshiring.",
            parse_mode="HTML",
        )
    except ChannelAccessDeniedError:
        await wait_msg.edit_text(
            "🔒 <b>Kanalga kirish imkoni bo'lmadi!</b>\n\n"
            "Kanal yopiq (private) bo'lishi mumkin yoki ulangan Telegram akkauntida "
            "ushbu kanalga kirish ruxsati mavjud emas.",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Kanal qo'shishda xatolik: {e}")
        await wait_msg.edit_text(
            f"❌ Xatolik yuz berdi: {escape_tg_html(str(e))}",
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("chan:list:"))
async def callback_list_channels(callback: CallbackQuery) -> None:
    page = int(callback.data.split(":")[2])
    async with get_db_session() as session:
        service = ChannelService(session)
        channels = await service.list_all_channels()

        if not channels:
            await callback.message.edit_text(
                "📋 Hozircha hech qanday kanal qo'shilmagan.\n\n"
                "Yangi kanal qo'shish uchun quyidagi tugmani bosing:",
                reply_markup=get_channels_menu_keyboard(),
            )
            await callback.answer()
            return

        text = f"📋 <b>SAQLANGAN KANALLAR</b> (Jami: {len(channels)} ta):\n\nKanalni tanlang:"
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=get_channels_list_keyboard(channels, page=page),
        )
        await callback.answer()


@router.callback_query(F.data.startswith("chan:view:"))
async def callback_view_channel(callback: CallbackQuery) -> None:
    channel_id = int(callback.data.split(":")[2])
    async with get_db_session() as session:
        service = ChannelService(session)
        channel = await service.get_channel_by_id(channel_id)
        if not channel:
            await callback.answer("Kanal topilmadi!", show_alert=True)
            return

        ch_title = escape_tg_html(channel.title)
        ch_url = escape_tg_html(channel.url)
        status_text = "🟢 Faol" if channel.is_active else "⏸ To'xtatilgan"

        text = (
            f"📢 <b>KANAL MA'LUMOTLARI</b>\n\n"
            f"Nomi: <b>{ch_title}</b>\n"
            f"Havola: {ch_url}\n"
            f"Telegram ID: <code>{channel.telegram_channel_id}</code>\n"
            f"Qidiruv holati: <b>{status_text}</b>\n"
            "Kanal nomi yoki username'i o'zgarsa ham qidiruv Telegram ID orqali ishlaydi."
        )
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=get_channel_details_keyboard(channel),
        )
        await callback.answer()


@router.callback_query(F.data.startswith("chan:toggle:"), flags={"requires_write": True})
async def callback_toggle_channel(callback: CallbackQuery) -> None:
    channel_id = int(callback.data.split(":")[2])
    async with get_db_session() as session:
        service = ChannelService(session)
        channel = await service.get_channel_by_id(channel_id)
        if not channel:
            await callback.answer("Kanal topilmadi!", show_alert=True)
            return

        new_status = not channel.is_active
        await service.channel_repo.set_active(channel.id, new_status)
        channel.is_active = new_status

        status_str = "faollashtirildi" if new_status else "to'xtatildi"
        await callback.answer(f"Monitoring {status_str}!")
        await callback.message.edit_reply_markup(
            reply_markup=get_channel_details_keyboard(channel)
        )


@router.callback_query(F.data.startswith("chan:delete_confirm:"), flags={"requires_write": True})
async def callback_delete_confirm(callback: CallbackQuery) -> None:
    channel_id = int(callback.data.split(":")[2])
    text = (
        "⚠️ <b>Kanalni o'chirishni tasdiqlaysizmi?</b>\n\n"
        "Kanal saqlangan ro'yxatdan chiqariladi va keyingi qidiruvlarda qatnashmaydi."
    )
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_delete_confirmation_keyboard(channel_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("chan:delete_do:"), flags={"requires_write": True})
async def callback_delete_execute(callback: CallbackQuery) -> None:
    channel_id = int(callback.data.split(":")[2])
    async with get_db_session() as session:
        service = ChannelService(session)
        success = await service.remove_channel(channel_id)
        if success:
            await callback.answer("Kanal o'chirildi!", show_alert=True)
            channels = await service.list_all_channels()
            await callback.message.edit_text(
                "✅ Kanal muvaffaqiyatli o'chirildi.",
                reply_markup=get_channels_list_keyboard(channels, page=1),
            )
        else:
            await callback.answer("Xatolik: kanal topilmadi", show_alert=True)


@router.callback_query(F.data.startswith("chan:scan_choice:"), flags={"requires_write": True})
async def callback_scan_choice(callback: CallbackQuery, state: FSMContext) -> None:
    channel_id = int(callback.data.split(":")[2])
    cancel_search(callback.message.chat.id, callback.from_user.id)
    await state.clear()
    await state.update_data(channel_id=channel_id)
    text = (
        "🔍 <b>REKLAMALARNI QIDIRISH</b>\n\n"
        "Qaysi davr uchun reklamalarni qidirish kerak?"
    )
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=periods_keyboard(channel_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("chan:scan:"), flags={"requires_write": True})
async def callback_execute_scan(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split(":")
    channel_id = int(parts[2])
    days = int(parts[3])

    cancel_search(callback.message.chat.id, callback.from_user.id)
    await state.clear()
    await state.update_data(channel_id=channel_id, mode={7: "week", 30: "month", 365: "year"}.get(days, "latest"))
    await callback.answer()
    await ask_keywords(callback.message, state)


@router.callback_query(F.data.startswith("chan:price:"), flags={"requires_write": True})
async def callback_price_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    channel_id = int(callback.data.split(":")[2])
    await state.set_state(ChannelPriceState.waiting_for_cpm)
    await state.update_data(channel_id=channel_id)

    text = (
        "💵 <b>REKLAMA NARXI / CPM KIRITISH</b>\n\n"
        "Ushbu kanaldagi reklama joylashtirish narxini so'mda kiriting (masalan: <code>500000</code> yoki <code>1200000</code>).\n"
        "Bekor qilish uchun 0 kiriting."
    )
    await callback.message.answer(text, parse_mode="HTML", reply_markup=get_cancel_keyboard())
    await callback.answer()


@router.message(ChannelPriceState.waiting_for_cpm, flags={"requires_write": True})
async def process_channel_price(message: Message, state: FSMContext) -> None:
    raw = message.text.strip().replace(" ", "").replace(",", ".")
    if raw in ("⬅️ Ortga", "🏠 Bosh menyu"):
        await state.clear()
        await message.answer("Bekor qilindi.", reply_markup=get_main_menu_keyboard())
        return

    try:
        price_val = float(raw)
        data = await state.get_data()
        channel_id = data.get("channel_id")

        async with get_db_session() as session:
            service = ChannelService(session)
            if price_val <= 0:
                await service.set_cpm_price(channel_id, None)
                msg = "✅ Kanal reklama narxi tozalandi."
            else:
                await service.set_cpm_price(channel_id, price_val)
                msg = f"✅ Reklama narxi o'rnatildi: {price_val:,.2f} so'm"

            ch = await service.get_channel_by_id(channel_id)

        await state.clear()
        await message.answer(msg, reply_markup=get_main_menu_keyboard())
        if ch:
            await message.answer(
                f"📢 <b>{escape_tg_html(ch.title)}</b>",
                parse_mode="HTML",
                reply_markup=get_channel_details_keyboard(ch),
            )

    except ValueError:
        await message.answer("❌ Noto'g'ri son kiritildi. Faqat raqamlardan foydalaning:")


@router.callback_query(F.data == "chan:check_all")
async def callback_check_all_channels(callback: CallbackQuery) -> None:
    await callback.message.edit_text("⏳ Kanallar tekshirilmoqda...")
    await callback.answer()

    async with get_db_session() as session:
        service = ChannelService(session)
        channels = await service.list_active_channels()

        report_lines = []
        for ch in channels:
            health = await service.check_channel_health(ch.id)
            if health["status"] == "ok":
                report_lines.append(f"🟢 <b>{escape_tg_html(ch.title)}</b> — Aloqa yaxshi")
            else:
                report_lines.append(f"🔴 <b>{escape_tg_html(ch.title)}</b> — {health.get('message', 'Xato')}")

        res_text = (
            f"🔍 <b>KANALLARNI TEKSHIRISH NATIJALARI</b> (Jami: {len(channels)}):\n\n"
            + "\n".join(report_lines)
        )
        await callback.message.edit_text(
            res_text,
            parse_mode="HTML",
            reply_markup=get_channels_menu_keyboard(),
        )
