from typing import Optional, List
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.administrator import Administrator
from app.core.security import UserRole


class AdminRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_tg_id(self, telegram_user_id: int) -> Optional[Administrator]:
        stmt = select(Administrator).where(
            Administrator.telegram_user_id == telegram_user_id
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_all(self) -> List[Administrator]:
        stmt = select(Administrator).order_by(Administrator.id.asc())
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def add(
        self,
        telegram_user_id: int,
        role: str = UserRole.ADMIN.value,
        username: Optional[str] = None,
        full_name: Optional[str] = None,
    ) -> Administrator:
        admin = await self.get_by_tg_id(telegram_user_id)
        if admin:
            admin.role = role
            admin.is_active = True
            if username:
                admin.username = username
            if full_name:
                admin.full_name = full_name
            await self.session.flush()
            return admin

        admin = Administrator(
            telegram_user_id=telegram_user_id,
            username=username,
            full_name=full_name,
            role=role,
            is_active=True,
        )
        self.session.add(admin)
        await self.session.flush()
        return admin

    async def update_role(self, telegram_user_id: int, role: str) -> bool:
        admin = await self.get_by_tg_id(telegram_user_id)
        if not admin:
            return False
        admin.role = role
        await self.session.flush()
        return True

    async def delete(self, telegram_user_id: int) -> bool:
        admin = await self.get_by_tg_id(telegram_user_id)
        if not admin:
            return False
        await self.session.delete(admin)
        await self.session.flush()
        return True

    async def ensure_superadmins(self, superadmin_ids: List[int]) -> None:
        """Ensures all IDs configured in settings are present as active superadmins."""
        for sa_id in superadmin_ids:
            admin = await self.get_by_tg_id(sa_id)
            if not admin:
                new_admin = Administrator(
                    telegram_user_id=sa_id,
                    role=UserRole.SUPERADMIN.value,
                    is_active=True,
                    full_name="Config Superadmin",
                )
                self.session.add(new_admin)
            else:
                admin.role = UserRole.SUPERADMIN.value
                admin.is_active = True
        await self.session.flush()
