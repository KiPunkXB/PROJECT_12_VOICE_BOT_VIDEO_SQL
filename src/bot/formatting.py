from __future__ import annotations


def format_numeric_response(value: int | float) -> str:
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return str(round(value, 2))
    return str(value)
