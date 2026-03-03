from __future__ import annotations

import re

from src.bot.formatting import format_numeric_response


NUMERIC_PATTERN = re.compile(r"^\s*-?\d+(\.\d+)?\s*$")


def test_response_is_numeric_only() -> None:
    outputs = [
        format_numeric_response(0),
        format_numeric_response(42),
        format_numeric_response(-5),
        format_numeric_response(3.14),
        format_numeric_response(2.0),
    ]
    for output in outputs:
        assert NUMERIC_PATTERN.match(output), output


def test_response_has_no_prefix_text() -> None:
    result = format_numeric_response(42)
    assert "Ответ" not in result
    assert result == "42"

