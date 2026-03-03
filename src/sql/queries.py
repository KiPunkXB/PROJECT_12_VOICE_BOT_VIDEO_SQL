from __future__ import annotations

from src.parser.intents import Intent, IntentType

# ─── Вайтлисты (защита от SQL injection) ─────────────────────────────────────

ALLOWED_METRICS: dict[str, set[str]] = {
    "videos": {
        "*",
        "id",
        "creator_id",
        "views_count",
        "likes_count",
        "comments_count",
        "reports_count",
    },
    "video_snapshots": {
        "*",
        "video_id",
        "views_count",
        "likes_count",
        "comments_count",
        "reports_count",
        "delta_views_count",
        "delta_likes_count",
        "delta_comments_count",
        "delta_reports_count",
    },
}

ALLOWED_OPERATIONS: set[str] = {"SUM", "COUNT", "COUNT_DISTINCT", "AVG", "MAX", "MIN"}

ALLOWED_FILTER_FIELDS: dict[str, set[str]] = {
    "videos": {"views_count", "likes_count", "comments_count", "reports_count"},
    "video_snapshots": {
        "views_count",
        "likes_count",
        "comments_count",
        "reports_count",
        "delta_views_count",
        "delta_likes_count",
        "delta_comments_count",
        "delta_reports_count",
    },
}

DATE_FIELD: dict[str, str] = {
    "videos": "video_created_at",
    "video_snapshots": "created_at",
}

ALLOWED_TABLES: set[str] = {"videos", "video_snapshots"}


# ─── Вспомогательные функции ──────────────────────────────────────────────────

def _validate(table: str, operation: str, metric: str) -> None:
    if table not in ALLOWED_TABLES:
        raise ValueError(f"Unknown table: {table!r}")
    if operation not in ALLOWED_OPERATIONS:
        raise ValueError(f"Unknown operation: {operation!r}")
    if metric not in ALLOWED_METRICS[table]:
        raise ValueError(f"Unknown metric {metric!r} for table {table!r}")


def _build_where(
    table: str,
    filters: dict,
    param_offset: int = 1,
) -> tuple[str, list, int]:
    """Возвращает (WHERE clause, список значений, следующий индекс параметра)."""
    conditions: list[str] = []
    values: list = []
    i = param_offset
    date_col = DATE_FIELD[table]

    creator_id = filters.get("creator_id")
    if creator_id:
        conditions.append(f"creator_id = ${i}")
        values.append(str(creator_id))
        i += 1

    video_id = filters.get("video_id")
    if video_id:
        id_col = "id" if table == "videos" else "video_id"
        conditions.append(f"{id_col} = ${i}")
        values.append(str(video_id))
        i += 1

    date_from = filters.get("date_from")
    if date_from is not None:
        conditions.append(f"{date_col} >= ${i}")
        values.append(date_from)
        i += 1

    date_to = filters.get("date_to")
    if date_to is not None:
        conditions.append(f"{date_col} < ${i}")
        values.append(date_to)
        i += 1

    filter_field = filters.get("filter_field")
    filter_gt = filters.get("filter_gt")
    if filter_field is not None and filter_gt is not None:
        if filter_field not in ALLOWED_FILTER_FIELDS[table]:
            raise ValueError(f"Unknown filter_field: {filter_field!r}")
        conditions.append(f"{filter_field} > ${i}")
        values.append(int(filter_gt))
        i += 1

    delta_gt = filters.get("delta_gt")
    delta_gt_field = filters.get("delta_gt_field")
    if delta_gt is not None and delta_gt_field:
        if delta_gt_field not in ALLOWED_FILTER_FIELDS[table]:
            raise ValueError(f"Unknown delta_gt_field: {delta_gt_field!r}")
        conditions.append(f"{delta_gt_field} > ${i}")
        values.append(int(delta_gt))
        i += 1

    filter_eq_field = filters.get("filter_eq_field")
    filter_eq_value = filters.get("filter_eq_value")
    if filter_eq_field is not None and filter_eq_value is not None:
        if filter_eq_field not in ALLOWED_FILTER_FIELDS.get(table, set()):
            raise ValueError(f"Unknown filter_eq_field: {filter_eq_field!r}")
        conditions.append(f"{filter_eq_field} = ${i}")
        values.append(int(filter_eq_value))
        i += 1

    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    return where, values, i


# ─── Основная функция построения запроса ─────────────────────────────────────

def build_query(intent: Intent) -> tuple[str, tuple]:
    itype = intent.intent_type
    params = intent.params

    if itype == IntentType.AGGREGATE:
        operation: str = params["operation"]
        metric: str = params["metric"]
        table: str = params["table"]
        filters: dict = params.get("filters", {})

        _validate(table, operation, metric)

        if operation == "COUNT_DISTINCT":
            select = f"SELECT COUNT(DISTINCT {metric})"
        elif metric == "*":
            select = f"SELECT {operation}(*)"
        else:
            select = f"SELECT {operation}({metric})"

        where, values, _ = _build_where(table, filters)
        query = f"{select}::bigint FROM {table}{where};"
        return query, tuple(values)

    if itype == IntentType.LOOKUP_ID:
        id_field: str = params["id_field"]   # "creator_id" или "id"
        metric: str = params["metric"]
        table: str = params.get("table", "videos")
        filters: dict = params.get("filters", {})

        if table not in ALLOWED_TABLES:
            raise ValueError(f"Unknown table: {table!r}")

        where, values, _ = _build_where(table, filters)

        if id_field == "creator_id":
            aggregate: str = params.get("aggregate", "SUM")
            if aggregate == "COUNT" or metric == "*":
                order_expr = "COUNT(*)"
            else:
                if metric not in ALLOWED_METRICS[table] - {"*", "id", "creator_id"}:
                    raise ValueError(f"Unknown metric {metric!r} for LOOKUP_ID")
                order_expr = f"SUM({metric})"
            query = (
                f"SELECT creator_id FROM {table}{where} "
                f"GROUP BY creator_id ORDER BY {order_expr} DESC LIMIT 1;"
            )
        else:
            # id_field == "id" → ORDER BY метрику DESC LIMIT 1
            if metric not in ALLOWED_METRICS[table] - {"*", "creator_id"}:
                raise ValueError(f"Unknown metric {metric!r} for LOOKUP_ID")
            query = f"SELECT id FROM {table}{where} ORDER BY {metric} DESC LIMIT 1;"

        return query, tuple(values)

    if itype == IntentType.VIDEO_DATE_RANGE:
        return (
            """
            SELECT
              MIN(video_created_at)::date AS min_date,
              MAX(video_created_at)::date AS max_date
            FROM videos;
            """,
            (),
        )

    raise ValueError(f"Unsupported intent type: {itype}")
