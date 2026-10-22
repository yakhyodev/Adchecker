"""Interactive, per-request search over the channels registered in the database."""

import asyncio
import time
import uuid
from collections import OrderedDict
from datetime import date, datetime

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.keyboards.reply import get_cancel_keyboard, get_main_menu_keyboard
from app.core.logging import logger
from app.core.security import escape_tg_html
from app.core.timezone import format_tashkent, get_tashkent_now
from app.database.session import get_db_session
from app.reports.live_excel import generate_live_excel
from app.services.live_search import LiveSearchService, SearchRequest, SearchUnavailable, load_search_channels

router = Router(name="live_search_router")
service = LiveSearchService()
search_lock = asyncio.Lock()
running: dict[tuple[int, int], asyncio.Task] = {}
# Reports live only in bounded process memory, expire after 30 minutes, and are owner-scoped.
reports: OrderedDict = OrderedDict()


class SearchState(StatesGroup):
    start_date = State()
    end_date = State()
    keywords = State()
    running = State()


def cancel_search(chat_id: int, user_id: int) -> None:
    task = running.get((chat_id, user_id))
    if task and task is not asyncio.current_task():
        task.cancel()


def periods_keyboard(channel_id: int | None = None) -> InlineKeyboardMarkup:
    suffix = f":{channel_id}" if channel_id is not None else ""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🆕 Eng oxirgi reklamalar", callback_data=f"search:mode:latest{suffix}")],
        [InlineKeyboardButton(text="🗓 Shu oy", callback_data=f"search:mode:month{suffix}"),
         InlineKeyboardButton(text="📆 Sana oralig'i", callback_data=f"search:mode:custom{suffix}")],
        [InlineKeyboardButton(text="🏠 Bosh menyu", callback_data="nav:home")],
    ])


async def begin_search(message: Message, state: FSMContext, mode: str,
                       channel_id: int | None = None) -> None:
    cancel_search(message.chat.id, message.from_user.id)
    await state.clear()
    await state.update_data(mode=mode, channel_id=channel_id)
    if mode == "custom":
        await state.set_state(SearchState.start_date)
        await message.answer("Boshlanish sanasini YYYY-MM-DD formatida kiriting:",
                             reply_markup=get_cancel_keyboard())
    else:
        await ask_keywords(message, state)


async def ask_keywords(message: Message, state: FSMContext) -> None:
    await state.set_state(SearchState.keywords)
    await message.answer(
        "🔎 Qidiriladigan kalit so'z yoki iborani yozing.\n"
        "Masalan: <code>@imkonhelpbot</code> yoki <code>IMKON savdo</code>.\n"
        "Bir nechta muqobil kalitni vergul yoki yangi qator bilan ajrating. "
        "Ulardan bittasi qatnashgan post topiladi.", reply_markup=get_cancel_keyboard())


@router.message(Command("search", "excel"))
@router.message(F.text == "📊 Excel hisobot")
async def search_menu(message: Message, state: FSMContext) -> None:
    cancel_search(message.chat.id, message.from_user.id)
    await state.clear()
    await message.answer("Qaysi davrdagi reklamalarni qidiramiz?", reply_markup=periods_keyboard())


@router.message(Command("recent"))
@router.message(F.text == "🆕 Oxirgi reklamalar")
async def search_latest(message: Message, state: FSMContext) -> None:
    await begin_search(message, state, "latest")


@router.message(Command("stats_month"))
@router.message(F.text.in_({"🗓 Shu oy", "🗓 Oxirgi oy"}))
async def search_month(message: Message, state: FSMContext) -> None:
    await begin_search(message, state, "month")


@router.message(Command("custom_range"))
@router.message(F.text == "📆 Sana bo‘yicha")
async def search_custom(message: Message, state: FSMContext) -> None:
    await begin_search(message, state, "custom")


@router.message(Command("stats_week", "stats_year", "refresh"))
@router.message(F.text.in_({"📅 Oxirgi hafta", "📈 Oxirgi yil", "🔄 Statistikani yangilash"}))
async def legacy_search(message: Message, state: FSMContext) -> None:
    mode = "week" if message.text in ("/stats_week", "📅 Oxirgi hafta") else "year" if message.text in ("/stats_year", "📈 Oxirgi yil") else "latest"
    await begin_search(message, state, mode)


@router.callback_query(F.data.startswith("search:mode:"))
async def select_period(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split(":")
    mode = parts[2]
    if mode not in ("latest", "month", "custom"):
        await callback.answer("Davr topilmadi.")
        return
    await callback.answer()
    # Callback messages are authored by the bot, so cancellation uses the human ID.
    cancel_search(callback.message.chat.id, callback.from_user.id)
    await state.clear()
    await state.update_data(mode=mode, channel_id=int(parts[3]) if len(parts) > 3 else None)
    if mode == "custom":
        await state.set_state(SearchState.start_date)
        await callback.message.answer("Boshlanish sanasini YYYY-MM-DD formatida kiriting:",
                                      reply_markup=get_cancel_keyboard())
    else:
        await ask_keywords(callback.message, state)


def read_date(raw: str | None) -> date:
    if not raw:
        raise ValueError("Sana matn ko'rinishida bo'lsin.")
    parsed = datetime.strptime(raw.strip(), "%Y-%m-%d").date()
    if parsed.isoformat() != raw.strip():
        raise ValueError("YYYY-MM-DD formatidan foydalaning.")
    return parsed


@router.message(Command("channels"))
@router.message(F.text == "📢 Kanallar")
async def channels_menu_shortcut(message: Message, state: FSMContext) -> None:
    from app.bot.handlers.channels import handle_channels_menu
    await handle_channels_menu(message, state)


@router.message(SearchState.start_date)
async def receive_start_date(message: Message, state: FSMContext) -> None:
    try:
        start = read_date(message.text)
        if start > get_tashkent_now().date():
            await message.answer("Boshlanish sanasi kelajakda bo'lmasin. Sanani qayta kiriting.")
            return
        await state.update_data(start_date=start.isoformat())
        await state.set_state(SearchState.end_date)
        await message.answer("Tugash sanasini YYYY-MM-DD formatida kiriting (bu kun ham qo'shiladi):")
    except ValueError:
        await message.answer("Sanani YYYY-MM-DD ko'rinishida yozing. Masalan: 2026-10-01.")


@router.message(SearchState.end_date)
async def receive_end_date(message: Message, state: FSMContext) -> None:
    try:
        end = read_date(message.text)
        data = await state.get_data()
        start = date.fromisoformat(data["start_date"])
        SearchRequest.create("validation", "custom", start, end)
        await state.update_data(end_date=end.isoformat())
        await ask_keywords(message, state)
    except ValueError as exc:
        await message.answer(escape_tg_html(str(exc)) + "\nTugash sanasini qayta kiriting.")


def cache_report(owner, report) -> str:
    now = time.monotonic()
    for token, (_, expires, _) in list(reports.items()):
        if expires <= now:
            reports.pop(token)
    token = uuid.uuid4().hex[:12]
    reports[token] = (owner, now + 1800, report)
    while len(reports) > 8:
        reports.popitem(last=False)
    return token


def render_page(report, token: str, page: int = 1):
    rows = [(result, ad) for result in report.channels for ad in (result.ads or [None])]
    pages = max(1, (len(rows) + 4) // 5)
    page = max(1, min(page, pages))
    missing = sum(ch.status == "not_found" for ch in report.channels)
    failed = sum(ch.status == "error" for ch in report.channels)
    lines = ["<b>REKLAMA QIDIRUV NATIJASI</b>",
             f"Kalitlar: {escape_tg_html(', '.join(report.request.keywords)[:400])}",
             escape_tg_html(report.request.label),
             f"Kanallar: {len(report.channels)} · Reklamalar: {report.total_ads}",
             f"🔴 Topilmadi: {missing} · ⚠️ Tekshiruv tugamadi: {failed}",
             f"Statistika olingan vaqt: {format_tashkent(report.checked_at)}\n"]
    for result, ad in rows[(page - 1) * 5:page * 5]:
        title = escape_tg_html(result.channel.title[:150])
        if ad:
            views = f"{ad.views:,}" if ad.views is not None else "Noma'lum"
            shares = f"{ad.forwards:,}" if ad.forwards is not None else "Noma'lum"
            lines.append(f"📢 <b>{title}</b>\n{format_tashkent(ad.posted_at)}\n"
                         f"{ad.url}\n👁 {views} · ↪️ {shares}" +
                         (f"\n⚠️ {escape_tg_html(result.detail)}" if result.status == "error" else ""))
        else:
            lines.append(f"{'🔴' if result.status == 'not_found' else '⚠️'} <b>{title}</b> — {escape_tg_html(result.detail)}")
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"search:page:{token}:{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page}/{pages}", callback_data="noop"))
    if page < pages:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"search:page:{token}:{page + 1}"))
    keyboard = InlineKeyboardMarkup(inline_keyboard=[nav,
        [InlineKeyboardButton(text="📊 Excel yuklash", callback_data=f"search:excel:{token}")],
        [InlineKeyboardButton(text="🏠 Bosh menyu", callback_data="nav:home")]])
    return "\n\n".join(lines), keyboard


async def send_excel(message: Message, report) -> None:
    buffer = await asyncio.to_thread(generate_live_excel, report)
    await message.answer_document(BufferedInputFile(buffer.getvalue(), filename="Reklama_hisoboti.xlsx"),
                                  caption="Reklama havolalari, joriy ko'rilishlar va ulashishlar.\n"
                                          "Qizil: topilmadi. Sariq: tekshiruv tugamadi.")


@router.message(SearchState.keywords)
async def execute_search(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    try:
        request = SearchRequest.create(message.text or "", data["mode"],
            date.fromisoformat(data["start_date"]) if data.get("start_date") else None,
            date.fromisoformat(data["end_date"]) if data.get("end_date") else None)
    except ValueError as exc:
        await message.answer(escape_tg_html(str(exc)))
        return
    if search_lock.locked():
        await message.answer("Hozir boshqa qidiruv ishlayapti. Tugagach kalit so'zni qayta yuboring.")
        return
    owner = (message.chat.id, message.from_user.id)
    task = asyncio.current_task()
    running[owner] = task
    wait = None
    try:
        async with search_lock:
            await state.set_state(SearchState.running)
            async with get_db_session() as session:
                channels = await load_search_channels(session, data.get("channel_id"))
            if not channels:
                await message.answer("Qidiruv uchun faol kanal yo'q. 📢 Kanallar bo'limida kanal qo'shing yoki faollashtiring.",
                                     reply_markup=get_main_menu_keyboard())
                return
            wait = await message.answer("⏳ Saqlangan kanallardan bevosita qidirilmoqda.\n"
                "Matn, izoh va havolalar tekshiriladi. Katta tarix vaqt olishi mumkin.\n"
                "To'xtatish: /cancel", reply_markup=get_cancel_keyboard())
            last_update = 0.0
            async def progress(done, total, title, scanned):
                nonlocal last_update
                if time.monotonic() - last_update < 5:
                    return
                last_update = time.monotonic()
                try:
                    await wait.edit_text(f"⏳ Tekshirilgan kanallar: {done}/{total}\n"
                        f"Kanal: {escape_tg_html(title[:150])}\nKo'rilgan xabarlar: {scanned}\nTo'xtatish: /cancel")
                except TelegramBadRequest:
                    pass
            report = await service.search(channels, request, progress)
            token = cache_report(owner, report)
            text, keyboard = render_page(report, token)
            await wait.edit_text(text, reply_markup=keyboard, disable_web_page_preview=True)
            await send_excel(message, report)
    except asyncio.CancelledError:
        if wait:
            try:
                await wait.edit_text("Qidiruv bekor qilindi.")
            except TelegramBadRequest:
                pass
    except SearchUnavailable as exc:
        await message.answer(escape_tg_html(str(exc)))
    except Exception as exc:
        logger.warning("Bevosita qidiruv bajarilmadi: %s", type(exc).__name__)
        await message.answer("Qidiruv yoki hisobotni yuborish tugamadi. Natija chiqqan bo'lsa, Excel yuklashni qayta bosing.")
    finally:
        if running.get(owner) is task:
            running.pop(owner, None)
            if await state.get_state() == SearchState.running.state:
                await state.clear()
                await message.answer("Asosiy menyu:", reply_markup=get_main_menu_keyboard())


@router.callback_query(F.data.startswith("search:page:"))
@router.callback_query(F.data.startswith("search:excel:"))
async def cached_result(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    token = parts[2]
    entry = reports.get(token)
    if not entry or entry[1] <= time.monotonic() or entry[0] != (callback.message.chat.id, callback.from_user.id):
        if entry and entry[1] <= time.monotonic():
            reports.pop(token, None)
        await callback.answer("Natija muddati tugagan yoki bu sizning hisobotingiz emas. Yangi qidiruv boshlang.", show_alert=True)
        return
    await callback.answer()
    report = entry[2]
    if parts[1] == "excel":
        await send_excel(callback.message, report)
    else:
        try:
            text, keyboard = render_page(report, token, int(parts[3]))
            await callback.message.edit_text(text, reply_markup=keyboard, disable_web_page_preview=True)
        except (ValueError, TelegramBadRequest):
            pass


@router.message(SearchState.running)
async def while_running(message: Message) -> None:
    await message.answer("Qidiruv davom etmoqda. To'xtatish uchun /cancel yuboring.")
