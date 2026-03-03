from __future__ import annotations

from src.core.config import Settings
from src.parser.intents import Intent, IntentType
from src.parser.llm_parser import parse_intent_with_llm
from src.parser.rule_parser import parse_intent


async def parse_intent_hybrid(text: str, settings: Settings) -> Intent:
    intent = parse_intent(text)
    if intent.intent_type != IntentType.UNKNOWN:
        return intent
    return await parse_intent_with_llm(text, settings)

