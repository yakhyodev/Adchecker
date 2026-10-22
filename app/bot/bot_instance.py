from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import BotCommand, BotCommandScopeDefault

from app.core.config import settings
from app.bot.middlewares.auth import AuthMiddleware
from app.bot.handlers import get_main_router
from app.core.logging import logger

bot = Bot(
    token=settings.BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)

dp = Dispatcher()


async def setup_bot_commands(bot_instance: Bot) -> None:
    """Sets up the bot menu commands so they appear automatically when typing '/'."""
    commands = [
        BotCommand(command="start", description="🏠 Asosiy menyu"),
        BotCommand(command="recent", description="🆕 Oxirgi reklamalar"),
        BotCommand(command="search", description="🔎 Kalit so'z va davr bo'yicha qidirish"),
        BotCommand(command="channels", description="📢 Kanallarni boshqarish"),
        BotCommand(command="stats_month", description="🗓 Shu oydagi reklamalar"),
        BotCommand(command="custom_range", description="📆 Sana bo'yicha hisobot"),
        BotCommand(command="excel", description="📊 Excel hisobot yuklab olish"),
        BotCommand(command="cancel", description="⬅️ Qidiruv yoki amalni bekor qilish"),
        BotCommand(command="help", description="📖 Yordam va yo'riqnoma"),
    ]
    try:
        await bot_instance.set_my_commands(commands, scope=BotCommandScopeDefault())
        logger.info("Bot buyruqlari muvaffaqiyatli ro'yxatdan o'tkazildi")
    except Exception as e:
        logger.error(f"Bot buyruqlarini sozlashda xatolik: {e}")


def setup_dispatcher() -> Dispatcher:
    """Configures middleware and handlers on the dispatcher."""
    # Register Auth Middleware
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())

    # Include Main Router
    dp.include_router(get_main_router())
    return dp
