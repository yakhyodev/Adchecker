from datetime import datetime, date
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from app.database.session import get_db_session
from app.services.report_service import ReportService
from app.reports.excel_generator import generate_ads_excel_report
from app.bot.states.forms import CustomDateRangeState
from app.bot.keyboards.reply import get_cancel_keyboard, get_main_menu_keyboard
from app.bot.keyboards.inline import get_report_actions_keyboard
from app.bot.handlers.statistics import format_summary_message
from app.core.timezone import get_tashkent_now, format_tashkent

router = Router(name="reports_router")


def get_excel_periods_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="📅 Oxirgi hafta", callback_data="export:week"),
            InlineKeyboardButton(text="🗓 Oxirgi oy", callback_data="export:month"),
        ],
        [
            InlineKeyboardButton(text="📈 Oxirgi yil", callback_data="export:year"),
            InlineKeyboardButton(text="📚 Barcha vaqt", callback_data="export:all"),
        ],
        [
            InlineKeyboardButton(text="📆 Sana bo'yicha", callback_data="export:custom_prompt"),
        ],
        [
            InlineKeyboardButton(text="🏠 Bosh menyu", callback_data="nav:home"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(F.text == "📊 Excel hisobot")
@router.message(Command("excel"))
async def handle_excel_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    text = (
        "📊 <b>EXCEL HISOBOT YUKLAB OLISH</b>\n\n"
        "Qaysi davr uchun Excel hisobot kerakligini tanlang:\n\n"
        "<i>Fayl tarkibi:</i>\n"
        "1. Barcha reklamalar ro'yxati va havolalari\n"
        "2. Kanallar statistikasi va reytingi\n"
        "3. Umumiy ko'rsatkichlar hisoboti\n"
        "4. Kunlik ko'rishlar statistikasi"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_excel_periods_keyboard())


@router.message(F.text == "📆 Sana bo‘yicha")
@router.message(Command("custom_range"))
async def handle_custom_range_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(CustomDateRangeState.waiting_for_start_date)
    text = (
        "📆 <b>SANA ORALIG'I BO'YICHA HISOBOT</b>\n\n"
        "Boshlanish sanasini <code>YYYY-MM-DD</code> formatida kiriting:\n\n"
        "<i>Masalan:</i> <code>2026-10-01</code>"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_cancel_keyboard())


@router.callback_query(F.data == "export:custom_prompt")
async def callback_custom_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CustomDateRangeState.waiting_for_start_date)
    text = (
        "📆 <b>SANA ORALIG'INI KIRITISH</b>\n\n"
        "Boshlanish sanasini <code>YYYY-MM-DD</code> formatida kiriting:\n\n"
        "<i>Masalan:</i> <code>2026-10-01</code>"
    )
    await callback.message.answer(text, parse_mode="HTML", reply_markup=get_cancel_keyboard())
    await callback.answer()


@router.message(CustomDateRangeState.waiting_for_start_date)
async def process_start_date(message: Message, state: FSMContext) -> None:
    raw = message.text.strip()
    if raw in ("⬅️ Ortga", "🏠 Bosh menyu"):
        await state.clear()
        await message.answer("Bekor qilindi.", reply_markup=get_main_menu_keyboard())
        return

    try:
        start_date = datetime.strptime(raw, "%Y-%m-%d").date()
        await state.update_data(start_date=start_date.isoformat())
        await state.set_state(CustomDateRangeState.waiting_for_end_date)
        await message.answer(
            f"✅ Boshlanish sanasi: <b>{start_date}</b>\n\n"
            f"Endi tugash sanasini <code>YYYY-MM-DD</code> formatida kiriting:\n\n"
            f"<i>Masalan:</i> <code>2026-10-21</code>",
            parse_mode="HTML",
            reply_markup=get_cancel_keyboard(),
        )
    except ValueError:
        await message.answer(
            "❌ <b>Noto'g'ri sana formati!</b>\n\n"
            "Iltimos, sanani <code>YYYY-MM-DD</code> ko'rinishida kiriting (masalan: <code>2026-10-01</code>):",
            parse_mode="HTML",
        )


@router.message(CustomDateRangeState.waiting_for_end_date)
async def process_end_date(message: Message, state: FSMContext) -> None:
    raw = message.text.strip()
    if raw in ("⬅️ Ortga", "🏠 Bosh menyu"):
        await state.clear()
        await message.answer("Bekor qilindi.", reply_markup=get_main_menu_keyboard())
        return

    try:
        end_date = datetime.strptime(raw, "%Y-%m-%d").date()
        data = await state.get_data()
        start_date = date.fromisoformat(data["start_date"])

        if start_date > end_date:
            await message.answer(
                f"❌ <b>Boshlanish sanasi ({start_date}) tugash sanasidan ({end_date}) katta bo'lishi mumkin emas!</b>\n\n"
                "Iltimos, qaytadan to'g'ri tugash sanasini kiriting:",
                parse_mode="HTML",
            )
            return

        wait_msg = await message.answer("⏳ Ma'lumotlar tahlil qilinmoqda...")

        async with get_db_session() as session:
            service = ReportService(session)
            rep = await service.get_custom_date_report(start_date, end_date)

            title = f"📆 <b>HISOBOT: {start_date} — {end_date}</b>"
            text = format_summary_message(title, rep, "custom")

            custom_cb = f"export:custom:{start_date.isoformat()}:{end_date.isoformat()}"
            actions_kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="📊 Excel hisobotni yuklash", callback_data=custom_cb),
                    ],
                    [
                        InlineKeyboardButton(text="🏠 Bosh menyu", callback_data="nav:home"),
                    ],
                ]
            )

            await wait_msg.edit_text(
                text,
                parse_mode="HTML",
                reply_markup=actions_kb,
                disable_web_page_preview=True,
            )

        await state.clear()
        await message.answer("Asosiy menyu:", reply_markup=get_main_menu_keyboard())

    except ValueError:
        await message.answer(
            "❌ Noto'g'ri sana formati! Iltimos, <code>YYYY-MM-DD</code> formatida kiriting:",
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("export:"))
async def callback_export_excel(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    rep_type = parts[1]

    if rep_type == "custom_prompt":
        return

    await callback.answer("Excel fayl tayyorlanmoqda...")
    wait_msg = await callback.message.answer("⏳ Excel hisobot generatsiya qilinmoqda...")

    try:
        async with get_db_session() as session:
            service = ReportService(session)

            if rep_type == "week":
                rep = await service.get_last_7_days_report()
            elif rep_type == "month":
                rep = await service.get_last_30_days_report()
            elif rep_type == "year":
                rep = await service.get_last_365_days_report()
            elif rep_type == "all":
                # Beginning of epoch to now
                start_all = datetime(2020, 1, 1)
                rep = await service.get_period_report(start_all, get_tashkent_now())
            elif rep_type == "custom":
                s_date = date.fromisoformat(parts[2])
                e_date = date.fromisoformat(parts[3])
                rep = await service.get_custom_date_report(s_date, e_date)
            else:
                rep = await service.get_last_7_days_report()

            # Generate workbook in memory
            excel_bytes = generate_ads_excel_report(rep)

            # Determine filename: IMKON_Ads_Report_YYYY-MM-DD_YYYY-MM-DD.xlsx
            s_str = rep["start_dt"][:10].replace(" ", "_")
            e_str = rep["end_dt"][:10].replace(" ", "_")
            filename = f"IMKON_Ads_Report_{s_str}_{e_str}.xlsx"

            input_file = BufferedInputFile(excel_bytes.getvalue(), filename=filename)

            caption = (
                f"📊 <b>IMKON Reklama Monitoring Hisoboti</b>\n\n"
                f"📅 Davr: <b>{rep['start_dt']} — {rep['end_dt']}</b>\n"
                f"📝 Jami reklamalar: <b>{rep['total_ads']} ta</b>\n"
                f"👁 Jami ko'rishlar: <b>{rep['total_views']:,}</b>\n"
                f"📈 O'rtacha ko'rish: <b>{rep['avg_views']:,}</b>"
            )

            await callback.message.answer_document(
                document=input_file,
                caption=caption,
                parse_mode="HTML",
            )
            await wait_msg.delete()

    except Exception as e:
        await wait_msg.edit_text(f"❌ Excel faylni yaratishda xatolik: {e}")
