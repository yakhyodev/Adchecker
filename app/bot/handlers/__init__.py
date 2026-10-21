from aiogram import Router

from app.bot.handlers.start import router as start_router
from app.bot.handlers.channels import router as channels_router
from app.bot.handlers.recent import router as recent_router
from app.bot.handlers.statistics import router as statistics_router
from app.bot.handlers.reports import router as reports_router
from app.bot.handlers.settings import router as settings_router


def get_main_router() -> Router:
    main_router = Router(name="main_router")
    main_router.include_router(start_router)
    main_router.include_router(channels_router)
    main_router.include_router(recent_router)
    main_router.include_router(statistics_router)
    main_router.include_router(reports_router)
    main_router.include_router(settings_router)
    return main_router
