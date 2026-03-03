from __future__ import annotations

_METRIC_LABELS: dict[str, str] = {
    "views_count": "просмотров",
    "likes_count": "лайков",
    "comments_count": "комментариев",
    "reports_count": "жалоб",
    "delta_views_count": "прирост просмотров",
    "delta_likes_count": "прирост лайков",
    "delta_comments_count": "прирост комментариев",
    "delta_reports_count": "прирост жалоб",
}


def format_numeric_response(value: int | float) -> str:
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return str(value)
    return str(value)


def format_top_n(rows: list[dict]) -> str:
    if not rows:
        return "Нет данных"
    metric = rows[0].get("metric", "views_count")
    label = _METRIC_LABELS.get(metric, metric)
    lines = [f"🏆 Топ {len(rows)} видео по {label}:\n"]
    for i, row in enumerate(rows, start=1):
        value = f"{row['value']:,}".replace(",", "\u202f")  # неразрывный пробел
        lines.append(f"{i}. ID {row['video_id']} — {value}")
    return "\n".join(lines)
