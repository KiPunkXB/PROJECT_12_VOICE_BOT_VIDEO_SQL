from __future__ import annotations

import logging

from src.core.config import Settings
from src.parser.intents import Intent, IntentType
from src.parser.llm_parser import parse_intent_with_llm
from src.parser.rule_parser import parse_intent

logger = logging.getLogger(__name__)


async def parse_intent_hybrid(text: str, settings: Settings) -> Intent:
    intent = parse_intent(text)
    if settings.llm_debug_logging:
        logger.info("Rule parser result: intent=%s text=%r", intent.intent_type.value, text)
    if intent.intent_type != IntentType.UNKNOWN:
        return intent
    if settings.llm_debug_logging:
        logger.info("Rule parser returned UNKNOWN, fallback to LLM")
    return await parse_intent_with_llm(text, settings)
