from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from openai import AsyncOpenAI

from src.core.config import Settings
from src.parser.intents import Intent, IntentType
from src.sql.queries import (
    ALLOWED_METRICS,
    ALLOWED_OPERATIONS,
    ALLOWED_TOP_CREATOR_METRICS,
    ALLOWED_TIME_SERIES_METRICS,
)

logger = logging.getLogger(__name__)

COMPACT_SYSTEM_PROMPT = """You are an NLU parser for Russian video analytics queries.
Return ONLY JSON with one of intent_type:
- AGGREGATE
- LOOKUP_ID
- VIDEO_DATE_RANGE
- VIDEO_DETAIL
- TOP_CREATORS
- TIME_SERIES
- UNKNOWN

AGGREGATE format:
{"intent_type":"AGGREGATE","operation":"COUNT|SUM|AVG|MAX|MIN|COUNT_DISTINCT","metric":"<field> or *","table":"videos|video_snapshots","filters":{"creator_id":null,"video_id":null,"date_from":"YYYY-MM-DD|null","date_to":"YYYY-MM-DD|null","hour_from":null,"hour_to":null,"filter_field":null,"filter_gt":null,"filter_lt_field":null,"filter_lt_value":null,"filter_eq_field":null,"filter_eq_value":null}}

LOOKUP_ID format:
{"intent_type":"LOOKUP_ID","id_field":"creator_id|id","aggregate":"SUM|COUNT","metric":"<field> or *","table":"videos","filters":{}}

VIDEO_DATE_RANGE format:
{"intent_type":"VIDEO_DATE_RANGE"}

VIDEO_DETAIL format:
{"intent_type":"VIDEO_DETAIL","video_id":"<uuid>"}

TOP_CREATORS format:
{"intent_type":"TOP_CREATORS","metric":"count|views_count|likes_count|comments_count|reports_count","limit":10,"filters":{"date_from":null,"date_to":null}}

TIME_SERIES format:
{"intent_type":"TIME_SERIES","metric":"delta_views_count|delta_likes_count|delta_comments_count|delta_reports_count","filters":{"date_from":"YYYY-MM-DD","date_to":"YYYY-MM-DD"},"limit":null,"order":"ASC|DESC"}

UNKNOWN format:
{"intent_type":"UNKNOWN"}

Rules:
1) No SQL text, JSON only.
2) If unsure -> UNKNOWN.
3) If query asks ONLY the date range (period) of all videos in DB -> VIDEO_DATE_RANGE. "Список/покажи все" → UNKNOWN.
4) growth/increase/new views -> metric delta_* in video_snapshots.
5) if month mentioned without year, use 2025.
6) UUID with dashes => video_id; 32-char hex => creator_id.
7) "Кто/какой автор/самый популярный автор" (ONE result) → LOOKUP_ID id_field=creator_id. "Какое видео/топ видео по X/самое X видео" → LOOKUP_ID id_field=id.
8) "Сколько видео создал/выпустил автор X" → AGGREGATE COUNT(*), NOT LOOKUP_ID.
9) EXACT field names: views_count, likes_count, comments_count, reports_count, delta_views_count, delta_likes_count, delta_comments_count, delta_reports_count.
10) "без X" → filter_eq_field=X_count, filter_eq_value=0.
11) "с X / с жалобами" → filter_field=X_count, filter_gt=0.
12) "сколько просмотров/лайков/комментариев/жалоб" → AGGREGATE SUM(X_count).
13) "максимальное/минимальное количество X у одного видео" → AGGREGATE MAX/MIN(X_count).
14) "топ N авторов по X" (explicit N or plural "авторов") → TOP_CREATORS. Single "какой автор" → LOOKUP_ID.
15) "динамика / по дням / прирост по дням" → TIME_SERIES (date_from+date_to required). "В какой день макс" → TIME_SERIES limit=1 order=DESC.
16) "статистика/покажи/расскажи про видео <UUID>" → VIDEO_DETAIL with video_id.
17) TIME_SERIES without dates → UNKNOWN.

Examples:
"какой создатель выпустил больше всего видео"
{"intent_type":"LOOKUP_ID","id_field":"creator_id","aggregate":"COUNT","metric":"*","table":"videos","filters":{}}

"кто самый популярный автор по просмотрам"
{"intent_type":"LOOKUP_ID","id_field":"creator_id","aggregate":"SUM","metric":"views_count","table":"videos","filters":{}}

"топ видео по лайкам"
{"intent_type":"LOOKUP_ID","id_field":"id","metric":"likes_count","table":"videos","filters":{}}

"какое видео самое просматриваемое"
{"intent_type":"LOOKUP_ID","id_field":"id","metric":"views_count","table":"videos","filters":{}}

"сколько видео создал автор abc123"
{"intent_type":"AGGREGATE","operation":"COUNT","metric":"*","table":"videos","filters":{"creator_id":"abc123"}}

"сколько видео без просмотров"
{"intent_type":"AGGREGATE","operation":"COUNT","metric":"*","table":"videos","filters":{"filter_eq_field":"views_count","filter_eq_value":0}}

"сколько видео без лайков"
{"intent_type":"AGGREGATE","operation":"COUNT","metric":"*","table":"videos","filters":{"filter_eq_field":"likes_count","filter_eq_value":0}}

"сколько видео с жалобами"
{"intent_type":"AGGREGATE","operation":"COUNT","metric":"*","table":"videos","filters":{"filter_field":"reports_count","filter_gt":0}}

"сколько видео с лайками больше 50000 за ноябрь"
{"intent_type":"AGGREGATE","operation":"COUNT","metric":"*","table":"videos","filters":{"filter_field":"likes_count","filter_gt":50000,"date_from":"2025-11-01","date_to":"2025-11-30"}}

"сколько комментариев за октябрь"
{"intent_type":"AGGREGATE","operation":"SUM","metric":"comments_count","table":"videos","filters":{"date_from":"2025-10-01","date_to":"2025-10-31"}}

"сколько жалоб за весь период"
{"intent_type":"AGGREGATE","operation":"SUM","metric":"reports_count","table":"videos","filters":{}}

"максимальное количество просмотров у одного видео"
{"intent_type":"AGGREGATE","operation":"MAX","metric":"views_count","table":"videos","filters":{}}

"сколько видео получили новые просмотры 27 ноября"
{"intent_type":"AGGREGATE","operation":"COUNT_DISTINCT","metric":"video_id","table":"video_snapshots","filters":{"date_from":"2025-11-27","date_to":"2025-11-27","filter_field":"delta_views_count","filter_gt":0}}

"сколько уникальных видео хотя бы раз показали отрицательный прирост просмотров"
{"intent_type":"AGGREGATE","operation":"COUNT_DISTINCT","metric":"video_id","table":"video_snapshots","filters":{"filter_lt_field":"delta_views_count","filter_lt_value":0}}

"сколько замеров где просмотры меньше 1000"
{"intent_type":"AGGREGATE","operation":"COUNT","metric":"*","table":"video_snapshots","filters":{"filter_lt_field":"views_count","filter_lt_value":1000}}

"прирост просмотров 28 ноября 2025"
{"intent_type":"AGGREGATE","operation":"SUM","metric":"delta_views_count","table":"video_snapshots","filters":{"date_from":"2025-11-28","date_to":"2025-11-28"}}

"сколько лайков у видео ecd8a4e4-1f24"
{"intent_type":"AGGREGATE","operation":"SUM","metric":"likes_count","table":"videos","filters":{"video_id":"ecd8a4e4-1f24"}}

"покажи список всех видео"
{"intent_type":"UNKNOWN"}

"динамика просмотров по дням за ноябрь"
{"intent_type":"TIME_SERIES","metric":"delta_views_count","filters":{"date_from":"2025-11-01","date_to":"2025-11-30"},"limit":null,"order":"ASC"}

"прирост лайков по дням за октябрь 2025"
{"intent_type":"TIME_SERIES","metric":"delta_likes_count","filters":{"date_from":"2025-10-01","date_to":"2025-10-31"},"limit":null,"order":"ASC"}

"в какой день был максимальный прирост просмотров за ноябрь"
{"intent_type":"TIME_SERIES","metric":"delta_views_count","filters":{"date_from":"2025-11-01","date_to":"2025-11-30"},"limit":1,"order":"DESC"}

"самый активный день по лайкам за октябрь"
{"intent_type":"TIME_SERIES","metric":"delta_likes_count","filters":{"date_from":"2025-10-01","date_to":"2025-10-31"},"limit":1,"order":"DESC"}

"динамика без дат"
{"intent_type":"UNKNOWN"}

"топ 5 авторов по лайкам"
{"intent_type":"TOP_CREATORS","metric":"likes_count","limit":5,"filters":{}}

"топ 3 автора по просмотрам за ноябрь"
{"intent_type":"TOP_CREATORS","metric":"views_count","limit":3,"filters":{"date_from":"2025-11-01","date_to":"2025-11-30"}}

"у каких авторов больше всего видео"
{"intent_type":"TOP_CREATORS","metric":"count","limit":10,"filters":{}}

"топ 10 авторов по жалобам"
{"intent_type":"TOP_CREATORS","metric":"reports_count","limit":10,"filters":{}}

"покажи статистику видео ecd8a4e4-1f24-4b0a-9c3d-000000000000"
{"intent_type":"VIDEO_DETAIL","video_id":"ecd8a4e4-1f24-4b0a-9c3d-000000000000"}

"расскажи про видео abc-123"
{"intent_type":"VIDEO_DETAIL","video_id":"abc-123"}

"что у видео fde42b07-37f4-4db7-95b4-d850a5e78693"
{"intent_type":"VIDEO_DETAIL","video_id":"fde42b07-37f4-4db7-95b4-d850a5e78693"}

"сколько всего авторов"
{"intent_type":"AGGREGATE","operation":"COUNT_DISTINCT","metric":"creator_id","table":"videos","filters":{}}

"самый продуктивный автор"
{"intent_type":"LOOKUP_ID","id_field":"creator_id","aggregate":"COUNT","metric":"*","table":"videos","filters":{}}

"какой автор выпустил больше всего видео за ноябрь"
{"intent_type":"LOOKUP_ID","id_field":"creator_id","aggregate":"COUNT","metric":"*","table":"videos","filters":{"date_from":"2025-11-01","date_to":"2025-11-30"}}

"сколько всего замеров в системе"
{"intent_type":"AGGREGATE","operation":"COUNT","metric":"*","table":"video_snapshots","filters":{}}

"среднее количество замеров на видео"
{"intent_type":"AGGREGATE","operation":"AVG","metric":"snapshot_count","table":"video_snapshots","filters":{}}
"""


SYSTEM_PROMPT = """You are an NLU parser for video analytics queries on a platform.
Convert the Russian user query into an intent JSON object.
Reply with ONLY valid JSON — no explanations, no SQL, no markdown.

━━━━━━━━━━━━━━━━━ DATABASE SCHEMA ━━━━━━━━━━━━━━━━━━━

Table videos (final cumulative stats per video):
  id (= video_id)    — video identifier
  creator_id         — content creator identifier
  video_created_at   — video publish datetime
  views_count        — total views
  likes_count        — total likes
  comments_count     — total comments
  reports_count      — total reports

Table video_snapshots (hourly measurements):
  video_id           — reference to video
  created_at         — measurement timestamp (hourly)
  views_count        — views at measurement time
  likes_count        — likes at measurement time
  comments_count     — comments at measurement time
  reports_count      — reports at measurement time
  delta_views_count  — views growth since last measurement
  delta_likes_count  — likes growth since last measurement
  delta_comments_count — comments growth since last measurement
  delta_reports_count  — reports growth since last measurement

━━━━━━━━━━━━━━━━━ INTENT TYPES ━━━━━━━━━━━━━━━━━━━━━━

1. AGGREGATE — aggregation, returns one number
2. LOOKUP_ID — returns one ID (creator_id or video id)
3. VIDEO_DATE_RANGE — global date range of all videos in DB
4. VIDEO_DETAIL — all fields of ONE video by ID
5. TOP_CREATORS — list of top N creators grouped by metric
6. TIME_SERIES — daily totals of a delta metric over a date range
7. UNKNOWN — query is not about video analytics

━━━━━━━━━━━━━━━━━ RESPONSE FORMATS ━━━━━━━━━━━━━━━━━━

AGGREGATE:
{"intent_type":"AGGREGATE","operation":"COUNT|SUM|AVG|MAX|MIN|COUNT_DISTINCT","metric":"<field> or *","table":"videos|video_snapshots","filters":{"creator_id":null,"video_id":null,"date_from":"YYYY-MM-DD|null","date_to":"YYYY-MM-DD|null","hour_from":null,"hour_to":null,"filter_field":null,"filter_gt":null,"filter_lt_field":null,"filter_lt_value":null,"filter_eq_field":null,"filter_eq_value":null}}

LOOKUP_ID (returns creator_id of most active author):
{"intent_type":"LOOKUP_ID","id_field":"creator_id","aggregate":"SUM|COUNT","metric":"<field> or *","table":"videos","filters":{}}

LOOKUP_ID (returns video id with max metric):
{"intent_type":"LOOKUP_ID","id_field":"id","metric":"<field>","table":"videos","filters":{}}

VIDEO_DATE_RANGE:
{"intent_type":"VIDEO_DATE_RANGE"}

VIDEO_DETAIL:
{"intent_type":"VIDEO_DETAIL","video_id":"<id>"}

TOP_CREATORS:
{"intent_type":"TOP_CREATORS","metric":"count|views_count|likes_count|comments_count|reports_count","limit":10,"filters":{"date_from":null,"date_to":null}}

TIME_SERIES:
{"intent_type":"TIME_SERIES","metric":"delta_views_count|delta_likes_count|delta_comments_count|delta_reports_count","filters":{"date_from":"YYYY-MM-DD","date_to":"YYYY-MM-DD"},"limit":null,"order":"ASC|DESC"}

UNKNOWN:
{"intent_type":"UNKNOWN"}

━━━━━━━━━━━━━━━━━ RULES ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1) Return ONLY JSON — no explanations, no SQL.
2) COUNT(*) to count videos/rows.
3) SUM(field) to sum values.
4) delta_* fields ONLY in video_snapshots.
5) Growth/increase/change/new → delta_* in video_snapshots.
6) Cumulative stats (no "growth"/"increase" words) → videos table.
7) date_from and date_to are INCLUSIVE; code adds +1 day for < comparison.
8) If year not specified → use 2025.
9) filter_field+filter_gt for "more than N / exceeded N / above N".
9b) filter_lt_field+filter_lt_value for "less than N / below N / negative (< 0) / decreased".
10) filter_eq_field+filter_eq_value for "exactly 0 / no views / no likes".
11) UNKNOWN if query is not about video analytics.
12) Do not invent creator_id if not explicitly stated in the query.
12b) Determine ID type by format:
     - UUID with hyphens (xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx) → video_id
     - Hex without hyphens (32 chars, e.g. df5973c0...) → creator_id
     This rule takes priority over query context.
13) For delta_* metrics by a specific author — use table=video_snapshots with creator_id in filters (JOIN added automatically).
13b) For cumulative metrics (views_count, likes_count etc.) by author — table=videos.
14) "Top video by X" → LOOKUP_ID with id_field="id" and metric X.
15) "Which/best author" → LOOKUP_ID with id_field="creator_id".
16) "Which video is most X" → LOOKUP_ID with id_field="id".
17) Author by video count: aggregate="COUNT", metric="*".
18) Author by metric sum: aggregate="SUM", metric=<field>.
19) "Which author has videos without X" → LOOKUP_ID creator_id + filter_eq_field+filter_eq_value=0.
20) "In which month/day/year..." → UNKNOWN (bot cannot answer with a date/month).
21) "Are there videos without X" → AGGREGATE COUNT with filter_eq_value=0.
22) "System/platform/database/service" = all videos in videos table, no filters.
23) hour_from and hour_to — integers 0–23, filter by snapshot hour ("from 10:00 to 15:00" → hour_from=10, hour_to=15; upper bound exclusive: covers 10,11,12,13,14). Both fields required together.
24) "Average number of snapshots per video" → AGGREGATE, operation=AVG, metric=snapshot_count, table=video_snapshots. Never use metric="*" with operation=AVG.
25) "How many distinct days did creator X publish videos" → AGGREGATE, operation=COUNT_DISTINCT, metric=publish_date, table=videos, filters with creator_id and/or dates.
26) "When was video UUID published/released", "publish date of video UUID" → AGGREGATE, operation=MIN, metric=video_created_at, table=videos, filters={video_id: UUID}. Do NOT use VIDEO_DATE_RANGE for such queries! VIDEO_DATE_RANGE is ONLY the global date range of all videos without a specific video.
27) "Статистика/расскажи/покажи про видео <ID>", "что у видео <ID>" → VIDEO_DETAIL with video_id=<ID>.
28) "Топ N авторов по X", "у каких авторов больше всего X" (result is a list of authors) → TOP_CREATORS. metric=count for video count, metric=X_count for metric. limit=N (default 10). "Какой автор/кто" (single result) → LOOKUP_ID.
29) "Динамика/прирост X по дням за [период]" → TIME_SERIES. metric=delta_X_count. date_from+date_to required (YYYY-MM-DD). order=ASC (default) or DESC. limit optional (use for "в какой день макс" → limit=1 order=DESC).
30) TIME_SERIES without explicit date range → UNKNOWN.

━━━━━━━━━━━━━━━━━ ПРИМЕРЫ ━━━━━━━━━━━━━━━━━━━━━━━━━━━

Query: "сколько всего видео?"
{"intent_type":"AGGREGATE","operation":"COUNT","metric":"*","table":"videos","filters":{}}

Query: "скока видосов"
{"intent_type":"AGGREGATE","operation":"COUNT","metric":"*","table":"videos","filters":{}}

Query: "сколько видео в августе 2025"
{"intent_type":"AGGREGATE","operation":"COUNT","metric":"*","table":"videos","filters":{"date_from":"2025-08-01","date_to":"2025-08-31"}}

Query: "сколько видео в мае и октябре"
{"intent_type":"AGGREGATE","operation":"COUNT","metric":"*","table":"videos","filters":{"date_from":"2025-05-01","date_to":"2025-10-31"}}

Query: "сколько видео с просмотрами больше 100000"
{"intent_type":"AGGREGATE","operation":"COUNT","metric":"*","table":"videos","filters":{"filter_field":"views_count","filter_gt":100000}}

Query: "сколько видео без просмотров"
{"intent_type":"AGGREGATE","operation":"COUNT","metric":"*","table":"videos","filters":{"filter_eq_field":"views_count","filter_eq_value":0}}

Query: "сколько видео без лайков"
{"intent_type":"AGGREGATE","operation":"COUNT","metric":"*","table":"videos","filters":{"filter_eq_field":"likes_count","filter_eq_value":0}}

Query: "сколько видео с жалобами"
{"intent_type":"AGGREGATE","operation":"COUNT","metric":"*","table":"videos","filters":{"filter_field":"reports_count","filter_gt":0}}

Query: "сколько всего создателей / авторов / креаторов"
{"intent_type":"AGGREGATE","operation":"COUNT_DISTINCT","metric":"creator_id","table":"videos","filters":{}}

Query: "суммарные просмотры всех видео"
{"intent_type":"AGGREGATE","operation":"SUM","metric":"views_count","table":"videos","filters":{}}

Query: "сколько просмотров набрала система"
{"intent_type":"AGGREGATE","operation":"SUM","metric":"views_count","table":"videos","filters":{}}

Query: "сколько лайков в системе"
{"intent_type":"AGGREGATE","operation":"SUM","metric":"likes_count","table":"videos","filters":{}}

Query: "сколько жалоб в системе за ноябрь"
{"intent_type":"AGGREGATE","operation":"SUM","metric":"reports_count","table":"videos","filters":{"date_from":"2025-11-01","date_to":"2025-11-30"}}

Query: "сколько комментариев у видео ecd8a4e4-1f24"
{"intent_type":"AGGREGATE","operation":"SUM","metric":"comments_count","table":"videos","filters":{"video_id":"ecd8a4e4-1f24"}}

Query: "сколько лайков у видео abc-123 за ноябрь"
{"intent_type":"AGGREGATE","operation":"SUM","metric":"likes_count","table":"videos","filters":{"video_id":"abc-123","date_from":"2025-11-01","date_to":"2025-11-30"}}

Query: "средние просмотры на видео"
{"intent_type":"AGGREGATE","operation":"AVG","metric":"views_count","table":"videos","filters":{}}

Query: "средние лайки за октябрь"
{"intent_type":"AGGREGATE","operation":"AVG","metric":"likes_count","table":"videos","filters":{"date_from":"2025-10-01","date_to":"2025-10-31"}}

Query: "максимальные просмотры"
{"intent_type":"AGGREGATE","operation":"MAX","metric":"views_count","table":"videos","filters":{}}

Query: "максимальные лайки за ноябрь"
{"intent_type":"AGGREGATE","operation":"MAX","metric":"likes_count","table":"videos","filters":{"date_from":"2025-11-01","date_to":"2025-11-30"}}

Query: "минимальные жалобы"
{"intent_type":"AGGREGATE","operation":"MIN","metric":"reports_count","table":"videos","filters":{}}

Query: "максимальное количество просмотров у одного видео"
{"intent_type":"AGGREGATE","operation":"MAX","metric":"views_count","table":"videos","filters":{}}

Query: "сколько комментариев за октябрь"
{"intent_type":"AGGREGATE","operation":"SUM","metric":"comments_count","table":"videos","filters":{"date_from":"2025-10-01","date_to":"2025-10-31"}}

Query: "сколько жалоб за весь период"
{"intent_type":"AGGREGATE","operation":"SUM","metric":"reports_count","table":"videos","filters":{}}

Query: "сколько видео с лайками больше 50000 за ноябрь"
{"intent_type":"AGGREGATE","operation":"COUNT","metric":"*","table":"videos","filters":{"filter_field":"likes_count","filter_gt":50000,"date_from":"2025-11-01","date_to":"2025-11-30"}}

Query: "прирост просмотров 28 ноября 2025"
{"intent_type":"AGGREGATE","operation":"SUM","metric":"delta_views_count","table":"video_snapshots","filters":{"date_from":"2025-11-28","date_to":"2025-11-28"}}

Query: "суммарный прирост лайков за ноябрь 2025"
{"intent_type":"AGGREGATE","operation":"SUM","metric":"delta_likes_count","table":"video_snapshots","filters":{"date_from":"2025-11-01","date_to":"2025-11-30"}}

Query: "максимальный прирост просмотров за день"
{"intent_type":"AGGREGATE","operation":"MAX","metric":"delta_views_count","table":"video_snapshots","filters":{}}

Query: "сколько видео получили новые просмотры 27 ноября"
{"intent_type":"AGGREGATE","operation":"COUNT_DISTINCT","metric":"video_id","table":"video_snapshots","filters":{"date_from":"2025-11-27","date_to":"2025-11-27","filter_field":"delta_views_count","filter_gt":0}}

Query: "сколько видео выпустил создатель abc123"
{"intent_type":"AGGREGATE","operation":"COUNT","metric":"*","table":"videos","filters":{"creator_id":"abc123"}}

Query: "сколько видео выпустил создатель abc123 в мае"
{"intent_type":"AGGREGATE","operation":"COUNT","metric":"*","table":"videos","filters":{"creator_id":"abc123","date_from":"2025-05-01","date_to":"2025-05-31"}}

Query: "сколько лайков получил создатель abc123"
{"intent_type":"AGGREGATE","operation":"SUM","metric":"likes_count","table":"videos","filters":{"creator_id":"abc123"}}

Query: "сколько лайков набрал df5973c05d90471ca1a7511e2560cfbf"
{"intent_type":"AGGREGATE","operation":"SUM","metric":"likes_count","table":"videos","filters":{"creator_id":"df5973c05d90471ca1a7511e2560cfbf"}}

Query: "сколько лайков набрал fde42b07-37f4-4db7-95b4-d850a5e78693"
{"intent_type":"AGGREGATE","operation":"SUM","metric":"likes_count","table":"videos","filters":{"video_id":"fde42b07-37f4-4db7-95b4-d850a5e78693"}}

Query: "сколько просмотров набрал fde42b07-37f4-4db7-95b4-d850a5e78693"
{"intent_type":"AGGREGATE","operation":"SUM","metric":"views_count","table":"videos","filters":{"video_id":"fde42b07-37f4-4db7-95b4-d850a5e78693"}}

Query: "сколько лайков у abc1-2345-6789-abcd-000000000000"
{"intent_type":"AGGREGATE","operation":"SUM","metric":"likes_count","table":"videos","filters":{"video_id":"abc1-2345-6789-abcd-000000000000"}}

Query: "сколько просмотров набрал abc123"
{"intent_type":"AGGREGATE","operation":"SUM","metric":"views_count","table":"videos","filters":{"creator_id":"abc123"}}

Query: "сколько лайко набрал abc123"
{"intent_type":"AGGREGATE","operation":"SUM","metric":"likes_count","table":"videos","filters":{"creator_id":"abc123"}}

Query: "сколько жалоб заработал xyz"
{"intent_type":"AGGREGATE","operation":"SUM","metric":"reports_count","table":"videos","filters":{"creator_id":"xyz"}}

Query: "сколько комментариев у автора abc за октябрь"
{"intent_type":"AGGREGATE","operation":"SUM","metric":"comments_count","table":"videos","filters":{"creator_id":"abc","date_from":"2025-10-01","date_to":"2025-10-31"}}

Query: "сколько просмотров набрал автор xyz за ноябрь"
{"intent_type":"AGGREGATE","operation":"SUM","metric":"views_count","table":"videos","filters":{"creator_id":"xyz","date_from":"2025-11-01","date_to":"2025-11-30"}}

Query: "какой автор получил больше всего лайков"
{"intent_type":"LOOKUP_ID","id_field":"creator_id","aggregate":"SUM","metric":"likes_count","table":"videos","filters":{}}

Query: "какой создатель выпустил больше всего видео"
{"intent_type":"LOOKUP_ID","id_field":"creator_id","aggregate":"COUNT","metric":"*","table":"videos","filters":{}}

Query: "какой автор получил больше всего жалоб"
{"intent_type":"LOOKUP_ID","id_field":"creator_id","aggregate":"SUM","metric":"reports_count","table":"videos","filters":{}}

Query: "кто самый популярный автор по просмотрам"
{"intent_type":"LOOKUP_ID","id_field":"creator_id","aggregate":"SUM","metric":"views_count","table":"videos","filters":{}}

Query: "какой автор выпустил больше всего видео за ноябрь"
{"intent_type":"LOOKUP_ID","id_field":"creator_id","aggregate":"COUNT","metric":"*","table":"videos","filters":{"date_from":"2025-11-01","date_to":"2025-11-30"}}

Query: "у какого автора есть видео без просмотров"
{"intent_type":"LOOKUP_ID","id_field":"creator_id","aggregate":"COUNT","metric":"*","table":"videos","filters":{"filter_eq_field":"views_count","filter_eq_value":0}}

Query: "у какого автора есть видео без лайков"
{"intent_type":"LOOKUP_ID","id_field":"creator_id","aggregate":"COUNT","metric":"*","table":"videos","filters":{"filter_eq_field":"likes_count","filter_eq_value":0}}

Query: "сколько авторов имеют видео без просмотров"
{"intent_type":"AGGREGATE","operation":"COUNT_DISTINCT","metric":"creator_id","table":"videos","filters":{"filter_eq_field":"views_count","filter_eq_value":0}}

Query: "есть видео без просмотров в мае"
{"intent_type":"AGGREGATE","operation":"COUNT","metric":"*","table":"videos","filters":{"filter_eq_field":"views_count","filter_eq_value":0,"date_from":"2025-05-01","date_to":"2025-05-31"}}

Query: "сколько замеров где прирост просмотров отрицательный"
{"intent_type":"AGGREGATE","operation":"COUNT","metric":"*","table":"video_snapshots","filters":{"filter_lt_field":"delta_views_count","filter_lt_value":0}}

Query: "сколько уникальных видео хотя бы раз показали отрицательный прирост просмотров"
{"intent_type":"AGGREGATE","operation":"COUNT_DISTINCT","metric":"video_id","table":"video_snapshots","filters":{"filter_lt_field":"delta_views_count","filter_lt_value":0}}

Query: "сколько уникальных видео имели отрицательный прирост лайков"
{"intent_type":"AGGREGATE","operation":"COUNT_DISTINCT","metric":"video_id","table":"video_snapshots","filters":{"filter_lt_field":"delta_likes_count","filter_lt_value":0}}

Query: "сколько раз прирост лайков был отрицательным"
{"intent_type":"AGGREGATE","operation":"COUNT","metric":"*","table":"video_snapshots","filters":{"filter_lt_field":"delta_likes_count","filter_lt_value":0}}

Query: "сколько замеров с просмотрами меньше 1000"
{"intent_type":"AGGREGATE","operation":"COUNT","metric":"*","table":"video_snapshots","filters":{"filter_lt_field":"views_count","filter_lt_value":1000}}

Query: "сколько видео с лайками меньше 100"
{"intent_type":"AGGREGATE","operation":"COUNT","metric":"*","table":"videos","filters":{"filter_lt_field":"likes_count","filter_lt_value":100}}

Query: "в каком месяце больше всего видео"
{"intent_type":"UNKNOWN"}

Query: "в каком месяце есть видео без просмотров"
{"intent_type":"UNKNOWN"}

Query: "в какой день максимальный прирост"
{"intent_type":"UNKNOWN"}

Query: "какое видео самое просматриваемое"
{"intent_type":"LOOKUP_ID","id_field":"id","metric":"views_count","table":"videos","filters":{}}

Query: "топ видео по лайкам"
{"intent_type":"LOOKUP_ID","id_field":"id","metric":"likes_count","table":"videos","filters":{}}

Query: "какое видео получило больше всего жалоб"
{"intent_type":"LOOKUP_ID","id_field":"id","metric":"reports_count","table":"videos","filters":{}}

Query: "топ видео по комментариям за октябрь"
{"intent_type":"LOOKUP_ID","id_field":"id","metric":"comments_count","table":"videos","filters":{"date_from":"2025-10-01","date_to":"2025-10-31"}}

Query: "диапазон дат видео"
{"intent_type":"VIDEO_DATE_RANGE"}

Query: "за какой период есть видео"
{"intent_type":"VIDEO_DATE_RANGE"}

Query: "суммарный прирост просмотров автора abc с 10:00 до 15:00 28 ноября 2025"
{"intent_type":"AGGREGATE","operation":"SUM","metric":"delta_views_count","table":"video_snapshots","filters":{"creator_id":"abc","date_from":"2025-11-28","date_to":"2025-11-28","hour_from":10,"hour_to":15}}

Query: "прирост лайков с 10:00 до 15:00 28 ноября"
{"intent_type":"AGGREGATE","operation":"SUM","metric":"delta_likes_count","table":"video_snapshots","filters":{"date_from":"2025-11-28","date_to":"2025-11-28","hour_from":10,"hour_to":15}}

Query: "сколько замеров с 0 до 6 часов за ноябрь"
{"intent_type":"AGGREGATE","operation":"COUNT","metric":"*","table":"video_snapshots","filters":{"date_from":"2025-11-01","date_to":"2025-11-30","hour_from":0,"hour_to":6}}

Query: "максимальный прирост просмотров у автора abc за ноябрь"
{"intent_type":"AGGREGATE","operation":"MAX","metric":"delta_views_count","table":"video_snapshots","filters":{"creator_id":"abc","date_from":"2025-11-01","date_to":"2025-11-30"}}

Query: "сколько замеров у создателя abc за 28 ноября"
{"intent_type":"AGGREGATE","operation":"COUNT","metric":"*","table":"video_snapshots","filters":{"creator_id":"abc","date_from":"2025-11-28","date_to":"2025-11-28"}}

Query: "в скольких разных календарных днях ноября 2025 публиковал видео создатель abc"
{"intent_type":"AGGREGATE","operation":"COUNT_DISTINCT","metric":"publish_date","table":"videos","filters":{"creator_id":"abc","date_from":"2025-11-01","date_to":"2025-11-30"}}

Query: "сколько разных дней публикации было у автора xyz за октябрь"
{"intent_type":"AGGREGATE","operation":"COUNT_DISTINCT","metric":"publish_date","table":"videos","filters":{"creator_id":"xyz","date_from":"2025-10-01","date_to":"2025-10-31"}}

Query: "в скольких днях создатель abc123 публиковал хотя бы одно видео"
{"intent_type":"AGGREGATE","operation":"COUNT_DISTINCT","metric":"publish_date","table":"videos","filters":{"creator_id":"abc123"}}

Query: "среднее количество замеров на видео"
{"intent_type":"AGGREGATE","operation":"AVG","metric":"snapshot_count","table":"video_snapshots","filters":{}}

Query: "среднее число замеров за ноябрь на видео"
{"intent_type":"AGGREGATE","operation":"AVG","metric":"snapshot_count","table":"video_snapshots","filters":{"date_from":"2025-11-01","date_to":"2025-11-30"}}

Query: "fde42b07-37f4-4db7-95b4-d850a5e78693 когда вышло"
{"intent_type":"AGGREGATE","operation":"MIN","metric":"video_created_at","table":"videos","filters":{"video_id":"fde42b07-37f4-4db7-95b4-d850a5e78693"}}

Query: "когда было опубликовано видео abc1-2345-6789-abcd-000000000000"
{"intent_type":"AGGREGATE","operation":"MIN","metric":"video_created_at","table":"videos","filters":{"video_id":"abc1-2345-6789-abcd-000000000000"}}

Query: "когда вышло видео ecd8a4e4-1f24-4b0a-9c3d-000000000000"
{"intent_type":"AGGREGATE","operation":"MIN","metric":"video_created_at","table":"videos","filters":{"video_id":"ecd8a4e4-1f24-4b0a-9c3d-000000000000"}}

Query: "покажи статистику видео ecd8a4e4-1f24-4b0a-9c3d-000000000000"
{"intent_type":"VIDEO_DETAIL","video_id":"ecd8a4e4-1f24-4b0a-9c3d-000000000000"}

Query: "расскажи про видео abc-123"
{"intent_type":"VIDEO_DETAIL","video_id":"abc-123"}

Query: "что у видео fde42b07-37f4-4db7-95b4-d850a5e78693"
{"intent_type":"VIDEO_DETAIL","video_id":"fde42b07-37f4-4db7-95b4-d850a5e78693"}

Query: "топ 5 авторов по лайкам"
{"intent_type":"TOP_CREATORS","metric":"likes_count","limit":5,"filters":{}}

Query: "топ 3 автора по просмотрам за ноябрь"
{"intent_type":"TOP_CREATORS","metric":"views_count","limit":3,"filters":{"date_from":"2025-11-01","date_to":"2025-11-30"}}

Query: "у каких авторов больше всего видео"
{"intent_type":"TOP_CREATORS","metric":"count","limit":10,"filters":{}}

Query: "топ 10 авторов по жалобам"
{"intent_type":"TOP_CREATORS","metric":"reports_count","limit":10,"filters":{}}

Query: "топ 7 авторов по комментариям за октябрь"
{"intent_type":"TOP_CREATORS","metric":"comments_count","limit":7,"filters":{"date_from":"2025-10-01","date_to":"2025-10-31"}}

Query: "динамика просмотров по дням за ноябрь"
{"intent_type":"TIME_SERIES","metric":"delta_views_count","filters":{"date_from":"2025-11-01","date_to":"2025-11-30"},"limit":null,"order":"ASC"}

Query: "прирост лайков по дням за октябрь 2025"
{"intent_type":"TIME_SERIES","metric":"delta_likes_count","filters":{"date_from":"2025-10-01","date_to":"2025-10-31"},"limit":null,"order":"ASC"}

Query: "в какой день был максимальный прирост просмотров за ноябрь"
{"intent_type":"TIME_SERIES","metric":"delta_views_count","filters":{"date_from":"2025-11-01","date_to":"2025-11-30"},"limit":1,"order":"DESC"}

Query: "самый активный день по лайкам за октябрь"
{"intent_type":"TIME_SERIES","metric":"delta_likes_count","filters":{"date_from":"2025-10-01","date_to":"2025-10-31"},"limit":1,"order":"DESC"}

Query: "динамика просмотров"
{"intent_type":"UNKNOWN"}

Query: "погода в москве"
{"intent_type":"UNKNOWN"}

Query: "привет"
{"intent_type":"UNKNOWN"}
"""

_UNKNOWN_INTENT = Intent(IntentType.UNKNOWN, {})

_LOOKUP_ID_FIELDS = {"creator_id", "id"}
_LOOKUP_AGGREGATES = {"SUM", "COUNT"}


def _parse_date(date_value: str) -> datetime:
    return datetime.strptime(date_value, "%Y-%m-%d")


def _parse_filters(raw: dict) -> dict | None:
    filters: dict = {}

    creator_id = raw.get("creator_id")
    if creator_id:
        filters["creator_id"] = str(creator_id)

    video_id = raw.get("video_id")
    if video_id:
        filters["video_id"] = str(video_id)

    date_from_raw = raw.get("date_from")
    if date_from_raw:
        try:
            filters["date_from"] = _parse_date(str(date_from_raw))
        except ValueError:
            return None

    date_to_raw = raw.get("date_to")
    if date_to_raw:
        try:
            filters["date_to"] = _parse_date(str(date_to_raw)) + timedelta(days=1)
        except ValueError:
            return None

    hour_from = raw.get("hour_from")
    if hour_from is not None:
        try:
            h = int(hour_from)
            if 0 <= h <= 23:
                filters["hour_from"] = h
        except (TypeError, ValueError):
            return None

    hour_to = raw.get("hour_to")
    if hour_to is not None:
        try:
            h = int(hour_to)
            if 0 <= h <= 23:
                filters["hour_to"] = h
        except (TypeError, ValueError):
            return None

    filter_field = raw.get("filter_field")
    filter_gt = raw.get("filter_gt")
    if filter_field is not None:
        filters["filter_field"] = str(filter_field)
    if filter_gt is not None:
        try:
            filters["filter_gt"] = int(filter_gt)
        except (TypeError, ValueError):
            return None

    filter_eq_field = raw.get("filter_eq_field")
    filter_eq_value = raw.get("filter_eq_value")
    if filter_eq_field is not None:
        filters["filter_eq_field"] = str(filter_eq_field)
    if filter_eq_value is not None:
        try:
            filters["filter_eq_value"] = int(filter_eq_value)
        except (TypeError, ValueError):
            return None

    filter_lt_field = raw.get("filter_lt_field")
    filter_lt_value = raw.get("filter_lt_value")
    if filter_lt_field is not None:
        filters["filter_lt_field"] = str(filter_lt_field)
    if filter_lt_value is not None:
        try:
            filters["filter_lt_value"] = int(filter_lt_value)
        except (TypeError, ValueError):
            return None

    return filters


def _payload_to_intent(payload: dict[str, Any]) -> Intent:
    raw_type = str(payload.get("intent_type", "UNKNOWN")).strip()
    try:
        intent_type = IntentType(raw_type)
    except ValueError:
        return _UNKNOWN_INTENT

    if intent_type == IntentType.UNKNOWN:
        return _UNKNOWN_INTENT

    if intent_type == IntentType.VIDEO_DATE_RANGE:
        return Intent(intent_type, {})

    if intent_type == IntentType.AGGREGATE:
        operation = str(payload.get("operation", "")).strip().upper()
        metric = str(payload.get("metric", "")).strip()
        table = str(payload.get("table", "videos")).strip()
        raw_filters = payload.get("filters") or {}

        if operation not in ALLOWED_OPERATIONS:
            return _UNKNOWN_INTENT
        if table not in ALLOWED_METRICS:
            return _UNKNOWN_INTENT
        if metric not in ALLOWED_METRICS[table]:
            return _UNKNOWN_INTENT
        # AVG(*) — невалидный SQL; для среднего числа замеров на видео нужен metric=snapshot_count
        if operation == "AVG" and metric == "*":
            return _UNKNOWN_INTENT

        filters = _parse_filters(raw_filters)
        if filters is None:
            return _UNKNOWN_INTENT
        return Intent(intent_type, {"operation": operation, "metric": metric, "table": table, "filters": filters})

    if intent_type == IntentType.LOOKUP_ID:
        id_field = str(payload.get("id_field", "")).strip()
        metric = str(payload.get("metric", "")).strip()
        table = str(payload.get("table", "videos")).strip()
        raw_filters = payload.get("filters") or {}

        if id_field not in _LOOKUP_ID_FIELDS:
            return _UNKNOWN_INTENT
        if table not in ALLOWED_METRICS:
            return _UNKNOWN_INTENT

        params: dict[str, Any] = {"id_field": id_field, "metric": metric, "table": table}

        if id_field == "creator_id":
            aggregate = str(payload.get("aggregate", "SUM")).strip().upper()
            if aggregate not in _LOOKUP_AGGREGATES:
                return _UNKNOWN_INTENT
            if aggregate == "SUM" and metric not in ALLOWED_METRICS[table] - {"*", "id", "creator_id"}:
                return _UNKNOWN_INTENT
            params["aggregate"] = aggregate
        else:
            # id_field == "id"
            if metric not in ALLOWED_METRICS[table] - {"*", "creator_id"}:
                return _UNKNOWN_INTENT

        filters = _parse_filters(raw_filters)
        if filters is None:
            return _UNKNOWN_INTENT
        params["filters"] = filters
        return Intent(intent_type, params)

    if intent_type == IntentType.VIDEO_DETAIL:
        video_id = str(payload.get("video_id", "")).strip()
        if not video_id:
            return _UNKNOWN_INTENT
        return Intent(intent_type, {"video_id": video_id})

    if intent_type == IntentType.TOP_CREATORS:
        metric = str(payload.get("metric", "count")).strip()
        if metric not in ALLOWED_TOP_CREATOR_METRICS:
            return _UNKNOWN_INTENT
        limit_raw = payload.get("limit", 10)
        try:
            limit = max(1, min(50, int(limit_raw)))
        except (TypeError, ValueError):
            limit = 10
        raw_filters = payload.get("filters") or {}
        filters = _parse_filters(raw_filters)
        if filters is None:
            return _UNKNOWN_INTENT
        return Intent(intent_type, {"metric": metric, "limit": limit, "filters": filters})

    if intent_type == IntentType.TIME_SERIES:
        metric = str(payload.get("metric", "")).strip()
        if metric not in ALLOWED_TIME_SERIES_METRICS:
            return _UNKNOWN_INTENT
        raw_filters = payload.get("filters") or {}
        filters = _parse_filters(raw_filters)
        if filters is None:
            return _UNKNOWN_INTENT
        # date range is required for TIME_SERIES
        if not filters.get("date_from") or not filters.get("date_to"):
            return _UNKNOWN_INTENT
        limit_raw = payload.get("limit")
        limit: int | None = None
        if limit_raw is not None:
            try:
                limit = max(1, min(30, int(limit_raw)))
            except (TypeError, ValueError):
                limit = None
        order = str(payload.get("order", "ASC")).upper()
        if order not in {"ASC", "DESC"}:
            order = "ASC"
        ts_params: dict[str, Any] = {"metric": metric, "filters": filters, "order": order}
        if limit is not None:
            ts_params["limit"] = limit
        return Intent(intent_type, ts_params)

    return _UNKNOWN_INTENT


async def parse_intent_with_llm(text: str, settings: Settings) -> Intent:
    if not settings.llm_parser_enabled or not settings.openai_api_key:
        if settings.llm_debug_logging:
            logger.warning(
                "LLM fallback skipped: llm_parser_enabled=%s openai_key_present=%s",
                settings.llm_parser_enabled,
                bool(settings.openai_api_key),
            )
        return _UNKNOWN_INTENT

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    prompt_variants = [COMPACT_SYSTEM_PROMPT] if settings.llm_compact_prompt_enabled else [SYSTEM_PROMPT]
    if settings.llm_compact_prompt_enabled and settings.llm_compact_retry_full:
        prompt_variants.append(SYSTEM_PROMPT)

    last_intent = _UNKNOWN_INTENT
    for idx, prompt in enumerate(prompt_variants, start=1):
        if settings.llm_debug_logging:
            logger.info(
                "LLM request text=%r model=%s prompt_variant=%s/%s compact=%s",
                text,
                settings.openai_model,
                idx,
                len(prompt_variants),
                prompt is COMPACT_SYSTEM_PROMPT,
            )
        try:
            response = await client.chat.completions.create(
                model=settings.openai_model,
                temperature=0,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": text},
                ],
            )
        except Exception as exc:
            if settings.llm_debug_logging:
                logger.exception("LLM request failed: %s", exc)
            continue

        content = response.choices[0].message.content or "{}"
        if settings.llm_debug_logging:
            logger.info("LLM raw response content=%s", content[:1200])

        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            if settings.llm_debug_logging:
                logger.warning("LLM response is not valid JSON")
            continue

        if not isinstance(payload, dict):
            if settings.llm_debug_logging:
                logger.warning("LLM JSON payload is not object: type=%s", type(payload).__name__)
            continue

        intent = _payload_to_intent(payload)
        if settings.llm_debug_logging:
            logger.info("LLM parsed intent=%s payload=%s", intent.intent_type.value, payload)
        last_intent = intent
        if intent.intent_type != IntentType.UNKNOWN:
            return intent

    return last_intent
