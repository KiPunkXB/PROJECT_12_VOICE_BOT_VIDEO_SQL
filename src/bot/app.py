from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher

from src.bot.handlers import build_router
from src.core.config import get_settings
from src.db.pool import create_pool


async def main() -> None:
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required in environment")

    pool = await create_pool(settings.database_url)
    bot = Bot(token=settings.telegram_bot_token)
    dispatcher = Dispatcher()
    dispatcher.include_router(build_router(pool, settings.sql_timeout_seconds))

    try:
        await dispatcher.start_polling(bot)
    finally:
        await pool.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

