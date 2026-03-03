from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from src.bot.formatting import format_numeric_response
from src.parser.rule_parser import parse_intent
from src.sql.engine import execute_intent


def build_router(pool, sql_timeout_seconds: float) -> Router:
    router = Router()

    @router.message(CommandStart())
    async def start_handler(message: Message) -> None:
        await message.answer(format_numeric_response(0))

    @router.message()
    async def query_handler(message: Message) -> None:
        text = message.text or ""
        intent = parse_intent(text)
        value = await execute_intent(
            pool=pool,
            intent=intent,
            sql_timeout_seconds=sql_timeout_seconds,
        )
        # Strict checker format: numeric string only.
        await message.answer(format_numeric_response(value))

    return router
