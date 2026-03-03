from __future__ import annotations

import logging
from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

logger = logging.getLogger(__name__)

from src.core.config import Settings
from src.bot.formatting import format_numeric_response
from src.parser.hybrid_parser import parse_intent_hybrid
from src.parser.intents import IntentType
from src.sql.engine import execute_intent


START_MESSAGE = (
    "👋 Привет! Я бот аналитики видео.\n\n"
    "✨ Что умею:\n"
    "• считаю любые метрики: просмотры, лайки, комментарии, жалобы;\n"
    "• фильтрую по дате, создателю, конкретному видео;\n"
    "• понимаю запросы на русском (в том числе с опечатками);\n"
    "• нахожу автора или видео с максимальной метрикой.\n\n"
    "🧪 Примеры запросов:\n"
    "1) Сколько всего видео в системе?\n"
    "2) Сколько лайков у видео 42?\n"
    "3) Прирост просмотров 28 ноября 2025\n"
    "4) Какой автор получил больше всего лайков?\n"
    "5) Сколько видео у создателя abc за ноябрь?\n"
    "6) Средние просмотры на видео\n\n"
    "ℹ️ Введи /help, если нужен мини-гайд."
)

HELP_MESSAGE = (
    "📌 Мини-гайд\n\n"
    "• Отправь текстовый запрос на русском.\n"
    "• Поддерживаемые метрики: просмотры, лайки, комментарии, жалобы.\n"
    "• Поддерживаемые операции: сколько, сумма, среднее, максимум, минимум.\n"
    "• Фильтры: по дате, по создателю, по ID видео, по порогу.\n"
    "• Поддерживаются даты вида: `28 ноября 2025`, `с 1 по 5 ноября 2025`.\n\n"
    "💡 Примеры:\n"
    "• `Сколько видео в августе?`\n"
    "• `Сумма лайков за ноябрь 2025`\n"
    "• `Какой автор выпустил больше всего видео?`\n"
    "• `Видео с просмотрами больше 100000`"
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
        try:
            intent = await parse_intent_hybrid(text, settings)
            if intent.intent_type == IntentType.UNKNOWN:
                await message.answer("❓ Не понял запрос. Попробуй переформулировать.")
                return
            value = await execute_intent(
                pool=pool,
                intent=intent,
                sql_timeout_seconds=settings.sql_timeout_seconds,
            )
        except Exception as exc:
            logger.exception("query_handler error for text=%r: %s", text, exc)
            await message.answer("⚠️ Не удалось выполнить запрос. Попробуй переформулировать.")
            return

        if isinstance(value, (int, float)):
            await message.answer(format_numeric_response(value))
        else:
            await message.answer(str(value))

    return router
