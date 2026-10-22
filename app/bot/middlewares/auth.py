from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

from app.core.config import settings
from app.core.security import UserRole
from app.database.session import get_db_session
from app.database.repositories.admin_repo import AdminRepository
from app.core.logging import logger


class AuthMiddleware(BaseMiddleware):
    """Enforces administrator role-based access control (RBAC)."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = None
        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user

        if not user:
            # Anonymous/channel-authored updates cannot establish an authorized user.
            return

        user_id = user.id

        # Check DB session
        async with get_db_session() as session:
            admin_repo = AdminRepository(session)

            # Check if this user is configured in settings.ADMIN_IDS as superadmin
            if user_id in settings.ADMIN_IDS:
                await admin_repo.ensure_superadmins([user_id])

            admin = await admin_repo.get_by_tg_id(user_id)

            if not admin or not admin.is_active:
                logger.warning(
                    f"Ruxsatsiz kirishga urinish: user_id={user_id}, username={user.username}"
                )
                msg_text = "⛔ Ushbu botdan foydalanish uchun ruxsatingiz mavjud emas."
                if isinstance(event, Message):
                    await event.answer(msg_text)
                elif isinstance(event, CallbackQuery):
                    await event.answer(msg_text, show_alert=True)
                return

            handler_info = data.get("handler")
            requires_write = getattr(handler_info, "flags", {}).get("requires_write", False)
            if requires_write and admin.role not in (UserRole.ADMIN.value, UserRole.SUPERADMIN.value):
                text = "⛔ Ushbu amalni faqat administrator bajara oladi."
                if isinstance(event, CallbackQuery):
                    await event.answer(text, show_alert=True)
                else:
                    await event.answer(text)
                return

            # Update admin info if changed
            if admin.username != user.username or admin.full_name != user.full_name:
                admin.username = user.username
                admin.full_name = user.full_name
                await session.flush()

            # Attach admin details to data dictionary
            data["admin_user"] = admin
            data["admin_role"] = admin.role
            data["is_superadmin"] = admin.role == UserRole.SUPERADMIN.value

        return await handler(event, data)
