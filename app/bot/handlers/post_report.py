"""Isolated post-link flow; existing channel/keyword search remains unchanged."""

import asyncio
import uuid

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, Message

from app.bot.keyboards.reply import get_cancel_keyboard, get_main_menu_keyboard
from app.bot.operations import begin_operation, cancel_operation, finish_operation
from app.core.logging import logger
from app.core.security import escape_tg_html
from app.core.timezone import format_tashkent
from app.reports.post_excel import generate_post_excel
from app.services.post_report import MISSING, PostReportService, PostReportUnavailable, parse_post_link

navigation_router = Router(name="post_report_navigation")
router = Router(name="post_report_flow")
navigation_router.message.filter(F.chat.type == "private")
router.message.filter(F.chat.type == "private")
service = PostReportService()
report_slots = asyncio.Semaphore(1)


class PostReportState(StatesGroup):
    link = State()
    running = State()


def display(value):
    return f"{value:,}" if isinstance(value, int) else MISSING


def summary(report):
    post = report.source
    lines = ["<b>POST HISOBOTI</b>", escape_tg_html(post.title or MISSING),
             escape_tg_html(post.post_url or MISSING),
             f"Chiqarilgan vaqt: {format_tashkent(post.published_at) if post.published_at else MISSING} (Toshkent)",
             f"Ko'rishlar: {display(post.views)}", f"Reaksiyalar: {display(post.reactions)}",
             f"Ulashishlar: {display(post.shares)}", f"Public Shares: {display(report.public_shares)}",
             f"Private Shares: {display(report.private_shares)}",
             f"Hisobot vaqti: {format_tashkent(report.checked_at)} (Toshkent)"]
    if not report.forwards_complete:
        lines.append("Public forwardlar hisoboti to'liq olinmadi.")
        lines.append(escape_tg_html(report.notice or "Ma'lumot topilmadi. Ulangan akkauntning kanalga kirish va admin huquqini tekshiring."))
    elif not report.forwards:
        lines.append(f"Public kanal/guruh postlari: {MISSING}.")
    return "\n".join(lines)


async def safe_answer(message, text, **kwargs):
    try:
        return await message.answer(text, **kwargs)
    except TelegramAPIError as exc:
        logger.info("Post hisoboti: holat xabari yuborilmadi (%s)", type(exc).__name__)
        return None


async def show_status(message, wait, text):
    if wait is not None:
        try:
            await wait.edit_text(text, disable_web_page_preview=True)
            return
        except TelegramAPIError as exc:
            logger.info("Post hisoboti: holat xabari yangilanmadi (%s)", type(exc).__name__)
    await safe_answer(message, text, disable_web_page_preview=True)


def is_post_link(text):
    if not isinstance(text, str):
        return False
    try:
        parse_post_link(text)
        return True
    except ValueError:
        return False


@navigation_router.message(Command("post"))
@navigation_router.message(F.text == "📋 Post hisoboti")
async def open_post_report(message: Message, state: FSMContext, command: CommandObject = None):
    await cancel_operation(message.chat.id, message.from_user.id)
    await state.clear()
    if command and command.args:
        await run_report(message, state, command.args)
        return
    await state.set_state(PostReportState.link)
    await message.answer("Asosiy kanaldagi post havolasini yuboring.\n"
                         "Masalan: https://t.me/imkonsavdomarkazi/5644",
                         reply_markup=get_cancel_keyboard())


@navigation_router.message(StateFilter(None), F.text.func(is_post_link))
async def direct_post_link(message: Message, state: FSMContext):
    await run_report(message, state, message.text)


@router.message(PostReportState.link)
async def receive_post_link(message: Message, state: FSMContext):
    await run_report(message, state, message.text or "")


async def run_report(message, state, raw_link):
    try:
        parse_post_link(raw_link)
    except ValueError as exc:
        await state.set_state(PostReportState.link)
        await message.answer(escape_tg_html(str(exc)), reply_markup=get_cancel_keyboard())
        return
    owner = (message.chat.id, message.from_user.id)
    task = await begin_operation(*owner)
    operation_id = uuid.uuid4().hex
    wait = None
    try:
        await state.set_state(PostReportState.running)
        await state.update_data(operation_id=operation_id)
        if report_slots.locked():
            await safe_answer(message, "Post hisoboti navbatga qo'shildi. To'xtatish: /cancel")
        async with report_slots:
            wait = await safe_answer(message, "Telegram taqdim etgan post statistikasi olinmoqda.\nTo'xtatish: /cancel",
                                     reply_markup=get_cancel_keyboard())
            report = await service.collect(raw_link)
            buffer = await asyncio.to_thread(generate_post_excel, report)
            await show_status(message, wait, summary(report))
            filename = "Post_hisoboti.xlsx" if report.forwards_complete else "Post_hisoboti_qisman.xlsx"
            await message.answer_document(BufferedInputFile(buffer.getvalue(), filename=filename))
    except asyncio.CancelledError:
        if wait:
            await show_status(message, wait, "Post hisoboti bekor qilindi.")
    except PostReportUnavailable as exc:
        await show_status(message, wait, escape_tg_html(str(exc)))
    except Exception as exc:
        # No secrets, message bodies or raw RPC error strings are logged.
        logger.warning("Post hisobotini olish/yuborish tugamadi (%s)", type(exc).__name__)
        await show_status(message, wait, "Post hisobotini olish yoki yuborish tugamadi. Qayta urinib ko'ring.")
    finally:
        if finish_operation(owner, task):
            data = await state.get_data()
            if data.get("operation_id") == operation_id:
                await state.clear()
                await safe_answer(message, "Asosiy menyu:", reply_markup=get_main_menu_keyboard())


@router.message(PostReportState.running)
async def while_running(message: Message):
    await message.answer("Post statistikasi olinmoqda. To'xtatish: /cancel")
