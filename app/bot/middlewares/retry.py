"""Retry Bot API rate limits at the session layer, including uploads and edits."""

import asyncio

from aiogram.client.session.middlewares.base import BaseRequestMiddleware
from aiogram.exceptions import TelegramRetryAfter


class RetryAfterMiddleware(BaseRequestMiddleware):
    def __init__(self, retries: int = 3):
        self.retries = retries

    async def __call__(self, make_request, bot, method):
        for attempt in range(self.retries + 1):
            try:
                return await make_request(bot, method)
            except TelegramRetryAfter as exc:
                if attempt == self.retries:
                    raise
                await asyncio.sleep(exc.retry_after)
