from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Returns the primary ReplyKeyboardMarkup for administrators."""
    keyboard = [
        [
            KeyboardButton(text="🆕 Oxirgi reklamalar"),
            KeyboardButton(text="🗓 Shu oy"),
        ],
        [
            KeyboardButton(text="📆 Sana bo‘yicha"),
            KeyboardButton(text="📊 Excel hisobot"),
        ],
        [
            KeyboardButton(text="📢 Kanallar"),
            KeyboardButton(text="📋 Post hisoboti"),
        ],
    ]
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        is_persistent=True,
    )


def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Returns a simple keyboard with Back and Main Menu buttons."""
    keyboard = [
        [
            KeyboardButton(text="⬅️ Ortga"),
            KeyboardButton(text="🏠 Bosh menyu"),
        ]
    ]
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
    )
