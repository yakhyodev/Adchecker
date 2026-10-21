import asyncio
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from app.database.session import get_db_session
from app.services.channel_service import ChannelService
from app.services.monitoring import MonitoringService
from app.bot.states.forms import AddChannelState, ChannelPriceState
from app.bot.keyboards.inline import (
    get_channels_menu_keyboard,
    get_channels_list_keyboard,
    get_channel_details_keyboard,
    get_scan_choice_keyboard,
    get_delete_confirmation_keyboard,
)
from app.bot.keyboards.reply import get_cancel_keyboard, get_main_menu_keyboard
from app.core.security import escape_tg_html
from app.core.timezone import format_tashkent
from app.telegram_client.client import ChannelNotFoundError, ChannelAccessDeniedError
from app.core.logging import logger

router = Router(name="channels_router")


@router.message(F.text == "📢 Kanallar")
@router.message(Command("channels"))
async def handle_channels_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    text = (
        "📢 <b>KANALLARNI BOSHQARISH</b>\n\n"
        "Ushbu bo'limda IMKON reklamalari joylanadigan Telegram kanallarni qo'shishingiz, "
        "ulardagi reklamalarni qidirishingiz va monitoring holatini sozlashingiz mumkin."
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_channels_menu_keyboard())


@router.callback_query(F.data == "chan:menu")
async def callback_channels_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    text = (
        "📢 <b>KANALLARNI BOSHQARISH</b>\n\n"
        "Kerakli amalni tanlang:"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_channels_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "chan:add")
async def callback_add_channel_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddChannelState.waiting_for_url)
    text = (
        "➕ <b>YANGI KANAL QO'SHISH</b>\n\n"
        "Kanalning havolasini yoki username'ini yuboring.\n\n"
        "<i>Qabul qilinadigan formatlar:</i>\n"
        "• <code>https://t.me/kanal_nomi</code>\n"
        "• <code>https://t.me/s/kanal_nomi</code>\n"
        "• <code>@kanal_nomi</code>\n"
        "• <code>kanal_nomi</code>"
    )
    await callback.message.answer(text, parse_mode="HTML", reply_markup=get_cancel_keyboard())
    await callback.answer()


@router.message(AddChannelState.waiting_for_url)
async def process_channel_input(message: Message, state: FSMContext) -> None:
    raw_text = message.text.strip()
    if raw_text in ("⬅️ Ortga", "🏠 Bosh menyu"):
        await state.clear()
        await message.answer("Amal bekor qilindi.", reply_markup=get_main_menu_keyboard())
        return

    wait_msg = await message.answer("⏳ Kanal tekshirilmoqda, iltimos kuting...")

    try:
        async with get_db_session() as session:
            service = ChannelService(session)
            channel, is_new = await service.add_channel(raw_text)

            ch_title = escape_tg_html(channel.title)
            ch_url = escape_tg_html(channel.url)

            if not is_new:
                await wait_msg.edit_text(
                    f"⚠️ <b>Bu kanal allaqachon tizimga qo'shilgan!</b>\n\n"
                    f"📢 Kanal: <b>{ch_title}</b>\n"
                    f"🔗 Havola: {ch_url}\n"
                    f"Holati: {'🟢 Faol' if channel.is_active else '⏸ To\'xtatilgan'}",
                    parse_mode="HTML",
                    reply_markup=get_channel_details_keyboard(channel),
                )
            else:
                await wait_msg.edit_text(
                    f"✅ <b>Kanal muvaffaqiyatli qo‘shildi!</b>\n\n"
                    f"📢 Kanal: <b>{ch_title}</b>\n"
                    f"🔗 Havola: {ch_url}\n"
                    f"Monitoring: 🟢 Faol\n\n"
                    f"Endi ushbu kanaldan reklamalarni qidirishni boshlashingiz mumkin:",
                    parse_mode="HTML",
                    reply_markup=get_channel_details_keyboard(channel),
                )

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

        text = f"📋 <b>MONITORING KANALLARI RO'YXATI</b> (Jami: {len(channels)} ta):\n\nKanalni tanlang:"
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
        last_scan = format_tashkent(channel.last_scanned_at)
        cpm_info = f"{channel.cpm_price:,.2f} so'm" if channel.cpm_price else "Belgilanmagan"

        text = (
            f"📢 <b>KANAL MA'LUMOTLARI</b>\n\n"
            f"Nomi: <b>{ch_title}</b>\n"
            f"Havola: {ch_url}\n"
            f"Telegram ID: <code>{channel.telegram_channel_id}</code>\n"
            f"Monitoring holati: <b>{status_text}</b>\n"
            f"Bir reklama narxi (CPM): <b>{cpm_info}</b>\n"
            f"Oxirgi tekshirilgan vaqt: {last_scan}\n"
            f"Oxirgi post ID: <code>{channel.last_scanned_message_id or '—'}</code>"
        )
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=get_channel_details_keyboard(channel),
        )
        await callback.answer()


@router.callback_query(F.data.startswith("chan:toggle:"))
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


@router.callback_query(F.data.startswith("chan:delete_confirm:"))
async def callback_delete_confirm(callback: CallbackQuery) -> None:
    channel_id = int(callback.data.split(":")[2])
    text = (
        "⚠️ <b>Kanalni o'chirishni tasdiqlaysizmi?</b>\n\n"
        "Kanal monitoringdan chiqariladi. Tarixiy reklama statistikasi bazada saqlanib qoladi."
    )
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_delete_confirmation_keyboard(channel_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("chan:delete_do:"))
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


@router.callback_query(F.data.startswith("chan:scan_choice:"))
async def callback_scan_choice(callback: CallbackQuery) -> None:
    channel_id = int(callback.data.split(":")[2])
    text = (
        "🔍 <b>REKLAMALARNI QIDIRISH</b>\n\n"
        "Qaysi davr uchun reklamalarni qidirish kerak?"
    )
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_scan_choice_keyboard(channel_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("chan:scan:"))
async def callback_execute_scan(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    channel_id = int(parts[2])
    days = int(parts[3])

    period_desc = f"oxirgi {days} kun" if days > 0 else "barcha mavjud tarix"
    await callback.message.edit_text(
        f"⏳ <b>{period_desc.capitalize()} bo'yicha qidiruv boshlandi...</b>\n\n"
        f"Kanal xabarlari tahlil qilinmoqda, bu biroz vaqt olishi mumkin.",
        parse_mode="HTML",
    )
    await callback.answer()

    # Async background task
    async def _async_scan():
        async with get_db_session() as session:
            mon_service = MonitoringService(session)
            res = await mon_service.run_channel_initial_scan(
                channel_id=channel_id,
                days_limit=days if days > 0 else None,
            )
            ch_service = ChannelService(session)
            ch = await ch_service.get_channel_by_id(channel_id)

            if res.get("status") == "completed":
                ans_text = (
                    f"✅ <b>Qidiruv yakunlandi!</b>\n\n"
                    f"📢 Kanal: <b>{escape_tg_html(ch.title if ch else '')}</b>\n"
                    f"🔍 Ko'rib chiqilgan xabarlar: <b>{res.get('posts_scanned', 0)} ta</b>\n"
                    f"🎯 Topilgan yangi reklamalar: <b>{res.get('ads_found', 0)} ta</b>"
                )
            elif res.get("status") == "already_running":
                ans_text = "⚠️ Ushbu kanal uchun tekshiruv allaqachon bajarilmoqda."
            elif res.get("status") == "flood_wait":
                ans_text = f"⏳ Telegram cheklovi: {res.get('seconds')} soniya kuting."
            else:
                ans_text = f"❌ Qidiruvda xatolik: {escape_tg_html(res.get('message', 'Noma\'lum xato'))}"

            try:
                await callback.message.edit_text(
                    ans_text,
                    parse_mode="HTML",
                    reply_markup=get_channel_details_keyboard(ch) if ch else None,
                )
            except Exception:
                pass

    asyncio.create_task(_async_scan())


@router.callback_query(F.data.startswith("chan:price:"))
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


@router.message(ChannelPriceState.waiting_for_cpm)
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
