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
    "count": "видео",
}


def _fmt(value: int) -> str:
    return f"{value:,}".replace(",", "\u202f")  # неразрывный пробел


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
        lines.append(f"{i}. ID {row['video_id']} — {_fmt(row['value'])}")
    return "\n".join(lines)


def format_top_creators(rows: list[dict]) -> str:
    if not rows:
        return "Нет данных"
    metric = rows[0].get("metric", "count")
    label = _METRIC_LABELS.get(metric, metric)
    lines = [f"👤 Топ {len(rows)} авторов по {label}:\n"]
    for i, row in enumerate(rows, start=1):
        lines.append(f"{i}. {row['creator_id']} — {_fmt(row['value'])}")
    return "\n".join(lines)


def format_time_series(rows: list[dict]) -> str:
    if not rows:
        return "Нет данных"
    metric = rows[0].get("metric", "delta_views_count")
    label = _METRIC_LABELS.get(metric, metric)
    lines = [f"📈 {label.capitalize()} по дням:\n"]
    for row in rows:
        day = str(row["day"])[:10]  # YYYY-MM-DD
        lines.append(f"{day} — {_fmt(row['value'])}")
    return "\n".join(lines)


def format_video_detail(row: dict) -> str:
    if not row:
        return "Видео не найдено"
    pub = str(row.get("video_created_at", "—"))[:10]
    return (
        f"📹 Видео: {row.get('id', '—')}\n"
        f"👤 Автор: {row.get('creator_id', '—')}\n"
        f"📅 Опубликовано: {pub}\n"
        f"👁 Просмотры: {_fmt(int(row.get('views_count') or 0))}\n"
        f"❤️ Лайки: {_fmt(int(row.get('likes_count') or 0))}\n"
        f"💬 Комментарии: {_fmt(int(row.get('comments_count') or 0))}\n"
        f"🚩 Жалобы: {_fmt(int(row.get('reports_count') or 0))}"
    )
