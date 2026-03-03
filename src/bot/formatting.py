from __future__ import annotations


def format_numeric_response(value: int | float) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()

