"""Date prompts and one sequential worker for the owned channel's post range."""

import asyncio
import tempfile
import time
import uuid
from collections import deque
from datetime import datetime
from pathlib import Path
from threading import Event

from aiogram import F, Router
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter, TelegramServerError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import FSInputFile, Message

from app.bot.handlers import post_report
from app.bot.keyboards.reply import get_cancel_keyboard, get_main_menu_keyboard
from app.bot.operations import begin_operation, cancel_operation, finish_operation
from app.core.logging import logger
from app.core.security import escape_tg_html
from app.core.timezone import get_tashkent_now
from app.reports.post_range_excel import generate_post_range_excel
from app.services.post_range import PostRange, PostRangeService, RangeStore
from app.services.post_report import PostReportUnavailable
from app.telegram_client.client import telegram_client_manager

navigation_router = Router(name="post_range_navigation")
router = Router(name="post_range_flow")
navigation_router.message.filter(F.chat.type == "private")
router.message.filter(F.chat.type == "private")
service = PostRangeService(telegram_client_manager)
WORK_ROOT = Path("data/post_reports")


class PostRangeState(StatesGroup):
    start = State()
    end = State()
    running = State()


def read_date(value):
    parsed = datetime.strptime(value or "", "%Y-%m-%d").date()
    if parsed.isoformat() != value:
        raise ValueError
    return parsed


@navigation_router.message(Command("posts_range"))
@navigation_router.message(F.text == "🗓 Postlar hisoboti")
async def open_range(message: Message, state: FSMContext):
    await cancel_operation(message.chat.id, message.from_user.id)
    await state.clear()
    await state.set_state(PostRangeState.start)
    await message.answer("IMKON kanalidagi barcha postlar uchun boshlanish sanasini YYYY-MM-DD formatida kiriting:",
                         reply_markup=get_cancel_keyboard())


@router.message(PostRangeState.start)
async def receive_start(message: Message, state: FSMContext):
    try:
        start = read_date((message.text or "").strip())
        if start > get_tashkent_now().date():
            raise ValueError
    except ValueError:
        await message.answer("Boshlanish sanasini YYYY-MM-DD formatida, kelajakda bo'lmagan sana bilan kiriting.")
        return
    await state.update_data(start=start.isoformat())
    await state.set_state(PostRangeState.end)
    await message.answer("Tugash sanasini YYYY-MM-DD formatida kiriting (bu kun ham qo'shiladi):")


@router.message(PostRangeState.end)
async def receive_end(message: Message, state: FSMContext):
    try:
        end = read_date((message.text or "").strip())
        data = await state.get_data()
        selected = PostRange.create(read_date(data["start"]), end)
    except (ValueError, KeyError):
        await message.answer("Tugash sanasini YYYY-MM-DD formatida kiriting. U boshlanish sanasidan kichik yoki kelajakda bo'lmasin.")
        return
    await run_range(message, state, selected)


async def export_range(store, path, **bounds):
    stop = Event()
    worker = asyncio.create_task(asyncio.to_thread(generate_post_range_excel, store, path, stop, **bounds))
    try:
        await asyncio.shield(worker)
    except asyncio.CancelledError:
        stop.set()
        # Wait for the writer to stop before closing SQLite/removing its files.
        await asyncio.shield(asyncio.gather(worker, return_exceptions=True))
        raise


async def export_files(store, path, max_bytes=49 * 1024 * 1024, max_rows=1048575):
    """Split from the disk spool when Telegram cannot accept one large workbook."""
    destinations = store.db.execute("SELECT COUNT(*) FROM destinations").fetchone()[0]
    pending = deque((offset, min(max_rows, destinations - offset), 0, store.post_count)
                    for offset in range(0, destinations, max_rows))
    if not pending:
        pending.append((0, 0, 0, store.post_count))
    files, split = [], len(pending) > 1
    while pending:
        offset, rows, post_offset, posts = pending.popleft()
        target = path if not split else path.with_name(f"{path.stem}_qism{len(files) + 1:03}.xlsx")
        await export_range(store, target, destination_offset=offset, destination_limit=rows,
                           post_offset=post_offset, post_limit=posts)
        if target.stat().st_size <= max_bytes:
            files.append(target)
            continue
        target.unlink()
        split = True
        if rows > 1:
            half = rows // 2
            pieces = [(offset, half, post_offset, posts), (offset + half, rows - half, post_offset, posts)]
        elif posts > 1:
            half = posts // 2
            pieces = [(offset, rows, post_offset, half), (offset, rows, post_offset + half, posts - half)]
        else:
            raise PostReportUnavailable("Bitta postning Excel natijasi Telegram fayl chegarasidan katta.")
        pending.extendleft(reversed(pieces))
    return files


async def send_file(message, path, progress, *, sleep=asyncio.sleep):
    attempts = 0
    while True:
        try:
            await message.answer_document(FSInputFile(path))
            return
        except TelegramRetryAfter as exc:
            seconds = exc.retry_after + 1
        except (TelegramNetworkError, TelegramServerError):
            attempts += 1
            seconds = min(60, 5 * 2**min(attempts - 1, 4))
        await progress("wait", f"Fayl yuborilishi uchun {seconds} soniya kutilmoqda. Natija saqlangan.")
        while seconds > 0:
            step = min(seconds, 30)
            await sleep(step)
            seconds -= step


async def run_range(message, state, selected):
    owner = (message.chat.id, message.from_user.id)
    task = await begin_operation(*owner)
    operation_id = uuid.uuid4().hex
    wait = None
    try:
        await state.set_state(PostRangeState.running)
        await state.update_data(operation_id=operation_id)
        if post_report.report_slots.locked():
            await post_report.safe_answer(message, "Postlar hisoboti navbatda. To'xtatish: /cancel")
        # The batch and single-post reports share one slot, including Telegram waits.
        async with post_report.report_slots:
            wait = await post_report.safe_answer(message, "Postlar ketma-ket olinmoqda. To'xtatish: /cancel",
                                                 reply_markup=get_cancel_keyboard())
            last_status = 0.0

            async def progress(stage, text):
                nonlocal last_status
                if stage not in ("wait", "resume") and time.monotonic() - last_status < 5:
                    return
                last_status = time.monotonic()
                await post_report.show_status(message, wait, escape_tg_html(text) + "\nTo'xtatish: /cancel")

            WORK_ROOT.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="range-", dir=WORK_ROOT) as directory:
                store = RangeStore(Path(directory) / "working.sqlite3")
                try:
                    try:
                        await service.collect(selected, store, progress)
                    except PostReportUnavailable as exc:
                        if not store.post_count:
                            raise
                        store.collection_complete = False
                        store.collection_notice = str(exc)
                    if not store.post_count:
                        await post_report.show_status(message, wait, "Tanlangan sanalarda post topilmadi.")
                        return
                    count, partial = store.post_count, store.partial_count
                    incomplete = bool(partial or not store.collection_complete)
                    await post_report.show_status(message, wait, f"{count} ta post olindi. Excel jadvali diskka yozilmoqda.\nTo'xtatish: /cancel")
                    suffix = "_qisman" if incomplete else ""
                    path = Path(directory) / f"Postlar_{selected.start}_{selected.end}{suffix}.xlsx"
                    files = await export_files(store, path)
                    for number, file_path in enumerate(files, 1):
                        await progress("file", f"Excel yuborilmoqda: {number}/{len(files)}.")
                        await send_file(message, file_path, progress)
                    await post_report.show_status(message, wait,
                        f"{'Qisman hisobot' if incomplete else 'Hisobot'} tayyor: {count} ta post.\nDavr: {selected.start} — {selected.end} (Toshkent)."
                        + (f"\nExcel {len(files)} ta faylga bo'lindi." if len(files) > 1 else "")
                        + (f"\n{partial} ta postning ayrim ma'lumotlari topilmadi; faylda qisman deb belgilangan." if partial else "")
                        + ("\nTekshiruv to'liq tugamadi: " + escape_tg_html(store.collection_notice) if not store.collection_complete else ""))
                finally:
                    store.close()
    except asyncio.CancelledError:
        await post_report.show_status(message, wait, "Postlar hisoboti bekor qilindi.")
    except PostReportUnavailable as exc:
        await post_report.show_status(message, wait, escape_tg_html(str(exc)))
    except Exception as exc:
        logger.warning("Sana oralig'idagi post hisoboti tugamadi (%s)", type(exc).__name__)
        await post_report.show_status(message, wait, "Postlar hisobotini olish yoki yuborish tugamadi. Qayta urinib ko'ring.")
    finally:
        if finish_operation(owner, task):
            if (await state.get_data()).get("operation_id") == operation_id:
                await state.clear()
                await post_report.safe_answer(message, "Asosiy menyu:", reply_markup=get_main_menu_keyboard())


@router.message(PostRangeState.running)
async def while_running(message: Message):
    await message.answer("Postlar hisoboti davom etmoqda. Telegram kutishidan keyin o'zi davom etadi. To'xtatish: /cancel")
