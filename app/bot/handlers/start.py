from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from app.bot.keyboards.reply import get_main_menu_keyboard
from app.core.security import escape_tg_html
from app.bot.handlers.search import cancel_search

router = Router(name="start_router")


@router.message(CommandStart())
async def handle_start(message: Message, state: FSMContext) -> None:
    await cancel_search(message.chat.id, message.from_user.id)
    await state.clear()
    first_name = escape_tg_html(message.from_user.first_name if message.from_user else "Foydalanuvchi")
    text = (
        f"📊 <b>IMKON REKLAMA MONITORING TIZIMI</b>\n\n"
        f"Assalomu alaykum, {first_name}!\n\n"
        "Saqlangan kanallardan kalit so'z va davr bo'yicha reklamalarni "
        "bevosita qidirib, Telegram havolalari, joriy ko'rilishlar va ulashishlar "
        "bilan Excel hisobot olishingiz mumkin.\n\n"
        f"Quyidagi menyudan kerakli bo'limni tanlang:"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_main_menu_keyboard())


@router.message(Command("help"))
async def handle_help(message: Message) -> None:
    text = (
        "📖 <b>BOTDAN FOYDALANISH YO'RIQNOMASI</b>\n\n"
        "🔹 <b>🆕 Oxirgi reklamalar:</b> Har saqlangan faol kanaldagi eng oxirgi mos reklama.\n"
        "🔹 <b>🗓 Shu oy:</b> Oyning 1-kunidan hozirgacha chiqqan mos reklamalar.\n"
        "🔹 <b>📆 Sana bo‘yicha:</b> Ikki sana oralig'idagi barcha mos reklamalar.\n"
        "🔹 Har qidiruvda kalit so'z yoki ibora kiritasiz.\n"
        "🔹 <b>📊 Excel:</b> Kanallar qatorlarda, sanalar bo'yicha reklama havolasi, ko'rilish va ulashishlar.\n"
        "🔹 <b>📢 Kanallar:</b> Bir xabarda ko'p kanal qo'shish, ro'yxat va o'chirish.\n"
        "🔹 Qidiruvni to'xtatish: /cancel.\n\n"
        "Sanalar Toshkent vaqti bo'yicha, boshlanish va tugash kunlari ham qo'shiladi. "
        "Topilmagan reklamalar qizil, tugamagan tekshiruvlar sariq belgilanadi."
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_main_menu_keyboard())


@router.message(F.text.in_(["🏠 Bosh menyu", "⬅️ Ortga"]))
@router.message(Command("cancel"))
async def handle_home_text(message: Message, state: FSMContext) -> None:
    await cancel_search(message.chat.id, message.from_user.id)
    await state.clear()
    await message.answer(
        "🏠 Asosiy menyudasiz:",
        reply_markup=get_main_menu_keyboard(),
    )


@router.callback_query(F.data == "nav:home")
async def handle_home_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await cancel_search(callback.message.chat.id, callback.from_user.id)
    await state.clear()
    await callback.message.delete()
    await callback.message.answer(
        "🏠 Asosiy menyudasiz:",
        reply_markup=get_main_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "noop")
async def handle_noop(callback: CallbackQuery) -> None:
    await callback.answer()
