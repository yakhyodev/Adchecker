from aiogram import Router

from app.bot.handlers.start import router as start_router
from app.bot.handlers.channels import router as channels_router
from app.bot.handlers.search import router as search_router
from app.bot.handlers.post_report import navigation_router as post_navigation_router, router as post_report_router
from app.bot.handlers.post_range import navigation_router as range_navigation_router, router as post_range_router


def get_main_router() -> Router:
    main_router = Router(name="main_router")
    main_router.include_router(start_router)
    main_router.include_router(range_navigation_router)
    main_router.include_router(post_navigation_router)
    main_router.include_router(search_router)
    main_router.include_router(post_range_router)
    main_router.include_router(post_report_router)
    main_router.include_router(channels_router)
    return main_router
