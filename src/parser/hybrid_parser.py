from __future__ import annotations

import logging
from collections import OrderedDict

from src.core.config import Settings
from src.parser.intents import Intent, IntentType
from src.parser.llm_parser import parse_intent_with_llm
from src.parser.rule_parser import normalize_text, parse_intent

logger = logging.getLogger(__name__)
_intent_cache: "OrderedDict[str, Intent]" = OrderedDict()

_UNKNOWN_INTENT = Intent(IntentType.UNKNOWN, {})

# Minimum set of keywords that must appear for a query to be analytics-related.
# If none of these are found → skip LLM entirely (saves API call).
_ANALYTICS_KEYWORDS = {
    "видео", "автор", "создател", "креатор",
    "просмотр", "лайк", "коммент", "жалоб",
    "замер", "прирост", "delta", "снэпшот",
    "диапазон", "период", "дата",
    "сколько", "топ", "максимал", "минимал", "средн",
    "когда", "выход", "опубликован",
}


def _looks_like_analytics(normalized: str) -> bool:
    """Return True if the query contains at least one analytics keyword."""
    return any(kw in normalized for kw in _ANALYTICS_KEYWORDS)


async def parse_intent_hybrid(text: str, settings: Settings) -> Intent:
    normalized = normalize_text(text)
    if settings.hybrid_intent_cache_size > 0:
        cached = _intent_cache.get(normalized)
        if cached is not None:
            if settings.llm_debug_logging:
                logger.info("Hybrid cache hit: intent=%s text=%r", cached.intent_type.value, text)
            _intent_cache.move_to_end(normalized)
            return cached

    intent = parse_intent(text)
    if settings.llm_debug_logging:
        logger.info("Rule parser result: intent=%s text=%r", intent.intent_type.value, text)
    if intent.intent_type != IntentType.UNKNOWN:
        if settings.hybrid_intent_cache_size > 0:
            _intent_cache[normalized] = intent
            _intent_cache.move_to_end(normalized)
            while len(_intent_cache) > settings.hybrid_intent_cache_size:
                _intent_cache.popitem(last=False)
        return intent
    if not _looks_like_analytics(normalized):
        if settings.llm_debug_logging:
            logger.info("Pre-filter: no analytics keywords, skip LLM text=%r", text)
        return _UNKNOWN_INTENT
    if settings.llm_debug_logging:
        logger.info("Rule parser returned UNKNOWN, fallback to LLM")
    llm_intent = await parse_intent_with_llm(text, settings)
    if settings.hybrid_intent_cache_size > 0:
        _intent_cache[normalized] = llm_intent
        _intent_cache.move_to_end(normalized)
        while len(_intent_cache) > settings.hybrid_intent_cache_size:
            _intent_cache.popitem(last=False)
    return llm_intent
