from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from src.core.config import Settings
from src.bot.formatting import format_numeric_response
from src.parser.hybrid_parser import parse_intent_hybrid
from src.sql.engine import execute_intent


START_MESSAGE = (
    "👋 Привет! Я бот аналитики видео.\n\n"
    "✨ Что умею:\n"
    "• считаю метрики по базе `videos` и `video_snapshots`;\n"
    "• понимаю запросы на русском;\n"
    "• отвечаю одним числом (формат для автопроверки).\n\n"
    "🧪 Примеры запросов:\n"
    "1) Сколько всего видео есть в системе?\n"
    "2) Сколько видео набрало больше 100 000 просмотров за всё время?\n"
    "3) На сколько просмотров в сумме выросли все видео 28 ноября 2025?\n"
    "4) Сколько разных видео получали новые просмотры 27 ноября 2025?\n\n"
    "ℹ️ Введи /help, если нужен мини-гайд."
)

HELP_MESSAGE = (
    "📌 Мини-гайд\n\n"
    "• Отправь текстовый запрос на русском.\n"
    "• В ответ вернется только число.\n"
    "• Поддерживаются даты вида: `28 ноября 2025`, `с 1 по 5 ноября 2025`.\n\n"
    "💡 Совет: формулируй вопрос коротко и конкретно.\n"
    "Например: `Сколько всего видео есть в системе?`"
)


def build_router(pool, settings: Settings) -> Router:
    router = Router()

    @router.message(CommandStart())
    async def start_handler(message: Message) -> None:
        await message.answer(START_MESSAGE)

    @router.message(Command("help"))
    async def help_handler(message: Message) -> None:
        await message.answer(HELP_MESSAGE)

    @router.message()
    async def query_handler(message: Message) -> None:
        text = message.text or ""
        intent = await parse_intent_hybrid(text, settings)
        value = await execute_intent(
            pool=pool,
            intent=intent,
            sql_timeout_seconds=settings.sql_timeout_seconds,
        )
        if isinstance(value, (int, float)):
            await message.answer(format_numeric_response(value))
        else:
            await message.answer(str(value))

    return router
