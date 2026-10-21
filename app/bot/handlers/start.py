from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from app.bot.keyboards.reply import get_main_menu_keyboard
from app.core.security import escape_tg_html

router = Router(name="start_router")


@router.message(CommandStart())
async def handle_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    first_name = escape_tg_html(message.from_user.first_name if message.from_user else "Foydalanuvchi")
    text = (
        f"📊 <b>IMKON REKLAMA MONITORING TIZIMI</b>\n\n"
        f"Assalomu alaykum, {first_name}!\n\n"
        f"Ushbu bot orqali Telegram kanallardagi <b>IMKON</b> savdo markazining "
        f"reklama postlarini avtomatik monitoring qilish, ko'rishlar soni va statistika tarixini kuzatish "
        f"hamda Excel hisobotlarni yuklab olishingiz mumkin.\n\n"
        f"Quyidagi menyudan kerakli bo'limni tanlang:"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_main_menu_keyboard())


@router.message(Command("help"))
async def handle_help(message: Message) -> None:
    text = (
        "📖 <b>BOTDAN FOYDALANISH YO'RIQNOMASI</b>\n\n"
        "🔹 <b>🆕 Oxirgi reklamalar:</b> Kanallarda aniqlangan eng so'nggi reklama postlarini ko'rish.\n"
        "🔹 <b>📅 Oxirgi hafta:</b> So'nggi 7 kunlik umumiy va kanallar kesimidagi statistika.\n"
        "🔹 <b>🗓 Oxirgi oy:</b> So'nggi 30 kunlik kengaytirilgan hisobot va haftalik dinamika.\n"
        "🔹 <b>📈 Oxirgi yil:</b> 365 kunlik oylik xulosa va umumiy natijalar.\n"
        "🔹 <b>📆 Sana bo‘yicha:</b> Istalgan sana oralig'ini tanlab hisobot olish.\n"
        "🔹 <b>📊 Excel hisobot:</b> Professional 4 varaqli Excel hisobotni yuklab olish.\n"
        "🔹 <b>📢 Kanallar:</b> Reklama joylanadigan kanallarni qo'shish, ko'rish va boshqarish.\n"
        "🔹 <b>🔄 Statistikani yangilash:</b> Reklamalarning hozirgi ko'rishlar sonini yangilash.\n"
        "🔹 <b>⚙️ Sozlamalar:</b> Qidiruv kalitlari, avto-monitoring va tizim holati.\n\n"
        "<i>Qidiruv standarti:</i> <code>@imkonhelpbot</code>"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_main_menu_keyboard())


@router.message(F.text.in_(["🏠 Bosh menyu", "⬅️ Ortga"]))
async def handle_home_text(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "🏠 Asosiy menyudasiz:",
        reply_markup=get_main_menu_keyboard(),
    )


@router.callback_query(F.data == "nav:home")
async def handle_home_callback(callback: CallbackQuery, state: FSMContext) -> None:
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
