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
        # virtual: video_created_at::date (для COUNT DISTINCT по дням публикаций)
        "publish_date",
        # дата публикации (используется для возврата даты конкретного видео)
        "video_created_at",
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
        # virtual: используется для AVG(COUNT(*) GROUP BY video_id)
        "snapshot_count",
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

# Виртуальные метрики → реальные SQL-выражения
VIRTUAL_METRIC_EXPR: dict[str, str] = {
    "publish_date": "video_created_at::date",
}

# Допустимые метрики для TOP_CREATORS (metric="count" → COUNT(*), иначе SUM(metric))
ALLOWED_TOP_CREATOR_METRICS: set[str] = {
    "count", "views_count", "likes_count", "comments_count", "reports_count",
}

# Допустимые метрики для TIME_SERIES (только delta_*)
ALLOWED_TIME_SERIES_METRICS: set[str] = {
    "delta_views_count", "delta_likes_count",
    "delta_comments_count", "delta_reports_count",
}


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

    hour_from = filters.get("hour_from")
    hour_to = filters.get("hour_to")
    if hour_from is not None and hour_to is not None:
        # "с 10:00 до 15:00" → hour>=10 AND hour<15 (верхняя граница исключительно)
        conditions.append(
            f"EXTRACT(HOUR FROM {date_col}) >= ${i} AND EXTRACT(HOUR FROM {date_col}) < ${i + 1}"
        )
        values.extend([int(hour_from), int(hour_to)])
        i += 2

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

    # filter_lt — WHERE field < value (например, delta_views_count < 0)
    filter_lt_field = filters.get("filter_lt_field")
    filter_lt_value = filters.get("filter_lt_value")
    if filter_lt_field is not None and filter_lt_value is not None:
        if filter_lt_field not in ALLOWED_FILTER_FIELDS.get(table, set()):
            raise ValueError(f"Unknown filter_lt_field: {filter_lt_field!r}")
        conditions.append(f"{filter_lt_field} < ${i}")
        values.append(int(filter_lt_value))
        i += 1

    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    return where, values, i


def _build_join_where_snapshots(
    filters: dict,
    param_offset: int = 1,
) -> tuple[str, list, int]:
    """WHERE clause для: video_snapshots vs JOIN videos v ON v.id = vs.video_id.

    creator_id фильтрует по v.creator_id, всё остальное — по vs.*.
    """
    conditions: list[str] = []
    values: list = []
    i = param_offset

    creator_id = filters.get("creator_id")
    if creator_id:
        conditions.append(f"v.creator_id = ${i}")
        values.append(str(creator_id))
        i += 1

    video_id = filters.get("video_id")
    if video_id:
        conditions.append(f"vs.video_id = ${i}")
        values.append(str(video_id))
        i += 1

    date_from = filters.get("date_from")
    if date_from is not None:
        conditions.append(f"vs.created_at >= ${i}")
        values.append(date_from)
        i += 1

    date_to = filters.get("date_to")
    if date_to is not None:
        conditions.append(f"vs.created_at < ${i}")
        values.append(date_to)
        i += 1

    hour_from = filters.get("hour_from")
    hour_to = filters.get("hour_to")
    if hour_from is not None and hour_to is not None:
        # "с 10:00 до 15:00" → hour>=10 AND hour<15 (верхняя граница исключительно)
        conditions.append(
            f"EXTRACT(HOUR FROM vs.created_at) >= ${i} AND EXTRACT(HOUR FROM vs.created_at) < ${i + 1}"
        )
        values.extend([int(hour_from), int(hour_to)])
        i += 2

    filter_field = filters.get("filter_field")
    filter_gt = filters.get("filter_gt")
    if filter_field is not None and filter_gt is not None:
        if filter_field not in ALLOWED_FILTER_FIELDS["video_snapshots"]:
            raise ValueError(f"Unknown filter_field: {filter_field!r}")
        conditions.append(f"vs.{filter_field} > ${i}")
        values.append(int(filter_gt))
        i += 1

    filter_eq_field = filters.get("filter_eq_field")
    filter_eq_value = filters.get("filter_eq_value")
    if filter_eq_field is not None and filter_eq_value is not None:
        if filter_eq_field not in ALLOWED_FILTER_FIELDS.get("video_snapshots", set()):
            raise ValueError(f"Unknown filter_eq_field: {filter_eq_field!r}")
        conditions.append(f"vs.{filter_eq_field} = ${i}")
        values.append(int(filter_eq_value))
        i += 1

    filter_lt_field = filters.get("filter_lt_field")
    filter_lt_value = filters.get("filter_lt_value")
    if filter_lt_field is not None and filter_lt_value is not None:
        if filter_lt_field not in ALLOWED_FILTER_FIELDS.get("video_snapshots", set()):
            raise ValueError(f"Unknown filter_lt_field: {filter_lt_field!r}")
        conditions.append(f"vs.{filter_lt_field} < ${i}")
        values.append(int(filter_lt_value))
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

        # Специальный случай: AVG(snapshot_count) = среднее число замеров на видео
        # SQL: SELECT AVG(cnt)::bigint FROM (SELECT COUNT(*) AS cnt FROM video_snapshots [WHERE] GROUP BY video_id) AS _sub
        if operation == "AVG" and metric == "snapshot_count":
            where_inner, values, _ = _build_where(table, filters)
            inner = f"SELECT COUNT(*) AS _cnt FROM {table}{where_inner} GROUP BY video_id"
            query = f"SELECT AVG(_cnt)::bigint FROM ({inner}) AS _sub;"
            return query, tuple(values)

        # Если запрос к video_snapshots + фильтр по creator_id → нужен JOIN с videos
        needs_join = table == "video_snapshots" and "creator_id" in filters
        if needs_join:
            if operation == "COUNT_DISTINCT":
                select = f"SELECT COUNT(DISTINCT vs.{metric})"
            elif metric == "*":
                select = f"SELECT {operation}(*)"
            else:
                select = f"SELECT {operation}(vs.{metric})"
            where, values, _ = _build_join_where_snapshots(filters)
            query = (
                f"{select}::bigint "
                f"FROM video_snapshots vs JOIN videos v ON v.id = vs.video_id"
                f"{where};"
            )
        else:
            # Раскрываем виртуальный метрик в реальное SQL-выражение
            metric_expr = VIRTUAL_METRIC_EXPR.get(metric, metric)
            if operation == "COUNT_DISTINCT":
                select = f"SELECT COUNT(DISTINCT {metric_expr})"
            elif metric == "*":
                select = f"SELECT {operation}(*)"
            else:
                select = f"SELECT {operation}({metric_expr})"
            where, values, _ = _build_where(table, filters)
            # video_created_at возвращает дату — нельзя кастовать в bigint
            if metric == "video_created_at":
                query = f"{select}::date FROM {table}{where};"
            else:
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

    if itype == IntentType.VIDEO_DETAIL:
        video_id: str = params["video_id"]
        query = (
            "SELECT id, creator_id, video_created_at, views_count, likes_count, "
            "comments_count, reports_count FROM videos WHERE id = $1;"
        )
        return query, (video_id,)

    if itype == IntentType.TOP_CREATORS:
        metric: str = params["metric"]
        limit: int = int(params.get("limit", 10))
        filters: dict = params.get("filters", {})

        if metric not in ALLOWED_TOP_CREATOR_METRICS:
            raise ValueError(f"Unknown TOP_CREATORS metric: {metric!r}")

        where, values, i = _build_where("videos", filters)

        if metric == "count":
            select = "SELECT creator_id, COUNT(*) AS value"
        else:
            select = f"SELECT creator_id, SUM({metric}) AS value"

        values.append(limit)
        query = (
            f"{select} FROM videos{where} "
            f"GROUP BY creator_id ORDER BY value DESC LIMIT ${i};"
        )
        return query, tuple(values)

    if itype == IntentType.TIME_SERIES:
        metric: str = params["metric"]
        filters: dict = params.get("filters", {})
        limit: int | None = params.get("limit")
        order: str = str(params.get("order", "ASC")).upper()

        if metric not in ALLOWED_TIME_SERIES_METRICS:
            raise ValueError(f"Unknown TIME_SERIES metric: {metric!r}")
        if order not in {"ASC", "DESC"}:
            order = "ASC"

        where, values, i = _build_where("video_snapshots", filters)
        parts = [
            f"SELECT created_at::date AS day, SUM({metric}) AS value",
            f"FROM video_snapshots{where}",
            "GROUP BY day",
            f"ORDER BY day {order}",
        ]
        if limit is not None:
            values.append(int(limit))
            parts.append(f"LIMIT ${i}")
        query = " ".join(parts) + ";"
        return query, tuple(values)

    raise ValueError(f"Unsupported intent type: {itype}")
