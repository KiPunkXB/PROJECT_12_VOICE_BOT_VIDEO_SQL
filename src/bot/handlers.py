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
    "📌 Полный гайд по боту аналитики\n"
    "Бот всегда возвращает одно число или ID.\n\n"

    "━━━ 📊 МЕТРИКИ ━━━\n"
    "Итоговые (накоплено за всё время):\n"
    "  • просмотры\n"
    "  • лайки\n"
    "  • комментарии\n"
    "  • жалобы\n\n"
    "Приросты за замер (почасово):\n"
    "  • прирост просмотров\n"
    "  • прирост лайков\n"
    "  • прирост комментариев\n"
    "  • прирост жалоб\n\n"

    "━━━ ⚙️ ОПЕРАЦИИ ━━━\n"
    "  • сколько / количество → COUNT\n"
    "  • сумма / всего → SUM\n"
    "  • среднее → AVG\n"
    "  • максимум → MAX\n"
    "  • минимум → MIN\n"
    "  • сколько уникальных → COUNT DISTINCT\n\n"

    "━━━ 🔎 ФИЛЬТРЫ ━━━\n"
    "  • по дате: в ноябре / 28 ноября 2025 / с 1 по 5 ноября\n"
    "  • по создателю: у автора <ID>\n"
    "  • по видео: у видео <ID>\n"
    "  • по порогу: больше 100000 / свыше 50000\n"
    "  • без метрики: без просмотров / без лайков\n\n"

    "━━━ 💡 ПРИМЕРЫ ━━━\n\n"
    "Количество:\n"
    "  Сколько всего видео?\n"
    "  Сколько видео в ноябре 2025?\n"
    "  Сколько видео выпустил автор abc123?\n"
    "  Сколько всего авторов?\n"
    "  Сколько видео без просмотров?\n"
    "  Сколько видео с просмотрами больше 100000?\n\n"
    "Суммы:\n"
    "  Сколько просмотров набрала система?\n"
    "  Сколько лайков за ноябрь 2025?\n"
    "  Сколько комментариев у автора abc123?\n"
    "  Сколько лайков у видео ecd8a4e4-1f24?\n"
    "  Прирост просмотров 28 ноября 2025\n\n"
    "Среднее / макс / мин:\n"
    "  Средние просмотры на видео\n"
    "  Максимальные лайки за октябрь\n"
    "  Минимальные жалобы\n"
    "  Максимальный прирост просмотров\n\n"
    "Кто лучший / какое видео:\n"
    "  Какой автор получил больше всего лайков?\n"
    "  Какой создатель выпустил больше всего видео?\n"
    "  Какое видео самое просматриваемое?\n"
    "  Какое видео получило больше всего жалоб?\n\n"
    "Диапазон дат:\n"
    "  За какой период есть видео?\n"
    "  Диапазон дат видео в базе"
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
