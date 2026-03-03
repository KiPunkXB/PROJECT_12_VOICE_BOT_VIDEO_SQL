from __future__ import annotations

_METRIC_LABELS: dict[str, str] = {
    "count": "видео",
    "views_count": "просмотры",
    "likes_count": "лайки",
    "comments_count": "комментарии",
    "reports_count": "жалобы",
    "delta_views_count": "прирост просмотров",
    "delta_likes_count": "прирост лайков",
    "delta_comments_count": "прирост комментариев",
    "delta_reports_count": "прирост жалоб",
}


def _fmt(n: int) -> str:
    """Format integer with thousands separator (space)."""
    return f"{n:,}".replace(",", " ")


def format_numeric_response(value: int | float) -> str:
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return str(round(value, 2))
    return str(value)


def format_video_detail(row: dict) -> str:
    lines = ["Видео " + str(row.get("id", "—"))]
    lines.append("Автор: " + str(row.get("creator_id", "—")))
    ts = row.get("video_created_at")
    lines.append("Опубликовано: " + (str(ts)[:10] if ts else "—"))
    lines.append("Просмотры: " + _fmt(int(row.get("views_count") or 0)))
    lines.append("Лайки: " + _fmt(int(row.get("likes_count") or 0)))
    lines.append("Комментарии: " + _fmt(int(row.get("comments_count") or 0)))
    lines.append("Жалобы: " + _fmt(int(row.get("reports_count") or 0)))
    return "\n".join(lines)


def format_top_creators(rows: list[dict]) -> str:
    metric = rows[0].get("_metric", "count")
    label = _METRIC_LABELS.get(metric, metric)
    header = f"Топ {len(rows)} авторов по {label}:"
    lines = [header]
    for rank, row in enumerate(rows, 1):
        lines.append(f"{rank}. {row['creator_id']} — {_fmt(row['value'])}")
    return "\n".join(lines)


def format_time_series(rows: list[dict]) -> str:
    metric = rows[0].get("_metric", "")
    label = _METRIC_LABELS.get(metric, metric)
    header = f"Динамика ({label}) по дням:"
    lines = [header]
    for row in rows:
        day = str(row["day"])[:10]  # YYYY-MM-DD -> DD part shown below
        # Reformat YYYY-MM-DD to DD.MM
        try:
            parts = day.split("-")
            day_fmt = f"{parts[2]}.{parts[1]}"
        except (IndexError, ValueError):
            day_fmt = day
        lines.append(f"{day_fmt} — {_fmt(row['value'])}")
    return "\n".join(lines)
