from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Optional
from app.database.models.channel import Channel


def get_channels_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="chan:add"),
            InlineKeyboardButton(text="📋 Kanallar ro'yxati", callback_data="chan:list:1"),
        ],
        [
            InlineKeyboardButton(text="🔍 Kanallarni tekshirish", callback_data="chan:check_all"),
        ],
        [
            InlineKeyboardButton(text="🏠 Bosh menyu", callback_data="nav:home"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_channels_list_keyboard(
    channels: List[Channel], page: int = 1, page_size: int = 6
) -> InlineKeyboardMarkup:
    total_pages = max(1, (len(channels) + page_size - 1) // page_size)
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * page_size
    current_channels = channels[start_idx : start_idx + page_size]

    keyboard = []
    for ch in current_channels:
        status_icon = "🟢" if ch.is_active else "⏸"
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=f"{status_icon} {ch.title}",
                    callback_data=f"chan:view:{ch.id}",
                )
            ]
        )

    # Pagination row
    nav_row = []
    if page > 1:
        nav_row.append(
            InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"chan:list:{page - 1}")
        )
    nav_row.append(
        InlineKeyboardButton(
            text=f"📄 {page}/{total_pages}", callback_data="noop"
        )
    )
    if page < total_pages:
        nav_row.append(
            InlineKeyboardButton(text="➡️ Keyingi", callback_data=f"chan:list:{page + 1}")
        )
    keyboard.append(nav_row)

    # Actions
    keyboard.append(
        [
            InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="chan:add"),
            InlineKeyboardButton(text="⬅️ Ortga", callback_data="chan:menu"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_channel_details_keyboard(channel: Channel) -> InlineKeyboardMarkup:
    status_text = "⏸ Qidiruvdan chiqarish" if channel.is_active else "▶️ Qidiruvga qo'shish"
    status_action = f"chan:toggle:{channel.id}"

    buttons = [
        [
            InlineKeyboardButton(
                text="🔍 Reklamalarni qidirish",
                callback_data=f"chan:scan_choice:{channel.id}",
            ),
        ],
        [
            InlineKeyboardButton(text=status_text, callback_data=status_action),
        ],
        [
            InlineKeyboardButton(
                text="🗑 Kanalni o'chirish",
                callback_data=f"chan:delete_confirm:{channel.id}",
            ),
        ],
        [
            InlineKeyboardButton(
                text="🔙 Kanallar ro'yxati", callback_data="chan:list:1"
            ),
            InlineKeyboardButton(text="🏠 Bosh menyu", callback_data="nav:home"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_scan_choice_keyboard(channel_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(
                text="📅 Oxirgi 7 kun",
                callback_data=f"chan:scan:{channel_id}:7",
            ),
            InlineKeyboardButton(
                text="🗓 Oxirgi 30 kun",
                callback_data=f"chan:scan:{channel_id}:30",
            ),
        ],
        [
            InlineKeyboardButton(
                text="📈 Oxirgi 365 kun",
                callback_data=f"chan:scan:{channel_id}:365",
            ),
            InlineKeyboardButton(
                text="📚 Barcha mavjud tarix",
                callback_data=f"chan:scan:{channel_id}:0",
            ),
        ],
        [
            InlineKeyboardButton(
                text="⬅️ Bekor qilish", callback_data=f"chan:view:{channel_id}"
            ),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_delete_confirmation_keyboard(channel_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(
                text="⚠️ Ha, o'chirilsin",
                callback_data=f"chan:delete_do:{channel_id}",
            ),
            InlineKeyboardButton(
                text="❌ Bekor qilish", callback_data=f"chan:view:{channel_id}"
            ),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_recent_ads_pagination_keyboard(
    post_url: str,
    current_page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    buttons = []

    # Open post URL
    if post_url and post_url.startswith("http"):
        buttons.append([InlineKeyboardButton(text="🔗 Postni ochish", url=post_url)])

    # Pagination controls
    nav_row = []
    if current_page > 1:
        nav_row.append(
            InlineKeyboardButton(
                text="⬅️ Oldingi", callback_data=f"ad:page:{current_page - 1}"
            )
        )
    nav_row.append(
        InlineKeyboardButton(
            text=f"📄 {current_page}/{total_pages}", callback_data="noop"
        )
    )
    if current_page < total_pages:
        nav_row.append(
            InlineKeyboardButton(
                text="➡️ Keyingi", callback_data=f"ad:page:{current_page + 1}"
            )
        )
    buttons.append(nav_row)

    # Actions
    buttons.append(
        [
            InlineKeyboardButton(text="📊 Excel yuklash", callback_data="export:recent"),
            InlineKeyboardButton(
                text="🔄 Yangilash", callback_data=f"ad:page:{current_page}"
            ),
        ]
    )
    buttons.append([InlineKeyboardButton(text="🏠 Bosh menyu", callback_data="nav:home")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_report_actions_keyboard(report_type: str) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(
                text="📊 Excel yuklash", callback_data=f"export:{report_type}"
            ),
            InlineKeyboardButton(
                text="🔄 Yangilash", callback_data=f"stats:refresh:{report_type}"
            ),
        ],
        [
            InlineKeyboardButton(text="🏠 Bosh menyu", callback_data="nav:home"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_settings_keyboard(auto_monitoring_enabled: bool) -> InlineKeyboardMarkup:
    auto_icon = "🟢 Yoqilgan" if auto_monitoring_enabled else "🔴 O'chirilgan"
    buttons = [
        [
            InlineKeyboardButton(
                text=f"🔄 Avto-monitoring: {auto_icon}",
                callback_data="set:toggle_auto",
            )
        ],
        [
            InlineKeyboardButton(
                text="🔑 Qidiruv kalitlari", callback_data="set:keywords"
            ),
            InlineKeyboardButton(
                text="⏱ Intervallar", callback_data="set:intervals"
            ),
        ],
        [
            InlineKeyboardButton(
                text="👥 Administratorlar", callback_data="set:admins"
            ),
            InlineKeyboardButton(
                text="📊 Tizim holati", callback_data="set:system_status"
            ),
        ],
        [
            InlineKeyboardButton(text="🏠 Bosh menyu", callback_data="nav:home"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
