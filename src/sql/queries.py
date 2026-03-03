from __future__ import annotations

from src.parser.intents import Intent, IntentType


def build_query(intent: Intent) -> tuple[str, tuple]:
    intent_type = intent.intent_type
    params = intent.params

    if intent_type == IntentType.COUNT_VIDEOS_ALL:
        return "SELECT COUNT(*)::bigint FROM videos;", ()

    if intent_type == IntentType.COUNT_VIDEOS_CREATOR_DATE_RANGE:
        return (
            """
            SELECT COUNT(*)::bigint
            FROM videos
            WHERE creator_id = $1
              AND video_created_at >= $2
              AND video_created_at < $3;
            """,
            (params["creator_id"], params["start"], params["end"]),
        )

    if intent_type == IntentType.COUNT_VIDEOS_VIEWS_GT:
        return (
            """
            SELECT COUNT(*)::bigint
            FROM videos
            WHERE views_count > $1;
            """,
            (params["threshold"],),
        )

    if intent_type == IntentType.SUM_DELTA_VIEWS_DAY:
        return (
            """
            SELECT COALESCE(SUM(delta_views_count), 0)::bigint
            FROM video_snapshots
            WHERE created_at >= $1
              AND created_at < $2;
            """,
            (params["start"], params["end"]),
        )

    if intent_type == IntentType.COUNT_DISTINCT_VIDEOS_WITH_NEW_VIEWS_DAY:
        return (
            """
            SELECT COUNT(DISTINCT video_id)::bigint
            FROM video_snapshots
            WHERE created_at >= $1
              AND created_at < $2
              AND delta_views_count > 0;
            """,
            (params["start"], params["end"]),
        )

    if intent_type == IntentType.VIDEO_DATE_RANGE:
        return (
            """
            SELECT
              MIN(video_created_at)::date AS min_date,
              MAX(video_created_at)::date AS max_date
            FROM videos;
            """,
            (),
        )

    raise ValueError(f"Unsupported intent type: {intent_type}")
