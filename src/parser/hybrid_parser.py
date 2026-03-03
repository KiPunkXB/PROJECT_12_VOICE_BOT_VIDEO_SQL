from __future__ import annotations

import logging
from collections import OrderedDict

from src.core.config import Settings
from src.parser.intents import Intent, IntentType
from src.parser.llm_parser import parse_intent_with_llm
from src.parser.rule_parser import normalize_text, parse_intent

logger = logging.getLogger(__name__)
_intent_cache: "OrderedDict[str, Intent]" = OrderedDict()


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
    if settings.llm_debug_logging:
        logger.info("Rule parser returned UNKNOWN, fallback to LLM")
    llm_intent = await parse_intent_with_llm(text, settings)
    if settings.hybrid_intent_cache_size > 0:
        _intent_cache[normalized] = llm_intent
        _intent_cache.move_to_end(normalized)
        while len(_intent_cache) > settings.hybrid_intent_cache_size:
            _intent_cache.popitem(last=False)
    return llm_intent
