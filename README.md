# PROJECT_12_VOICE_BOT_VIDEO_SQL

Telegram-бот аналитики видео на Python + PostgreSQL (асинхронный стек).  
Принимает вопрос на русском, распознает intent и возвращает ответ по базе `videos`/`video_snapshots`.  
Сделан под формат тестового задания: быстро поднять, проверить, прогнать smoke/precheck.

## Возможности
- Асинхронный бот на `aiogram` + асинхронные запросы в PostgreSQL (`asyncpg`).
- Детерминированный rule-based парсер (быстро и предсказуемо).
- GPT fallback для свободных формулировок (`rule -> LLM -> intent`).
- Белый список SQL-шаблонов (без генерации SQL моделью).
- Загрузка `videos.json` в БД через idempotent upsert-скрипт.
- Smoke-набор запросов (`scripts/smoke_bot.py`) и precheck перед проверкой (`scripts/precheck.py`).
- Ответы в формате автопроверки: одно число для метрик.

## Быстрый старт (локально)
### 1) Поднять PostgreSQL
```bash
docker compose up -d
```

### 2) Установить зависимости
```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

### 3) Настроить окружение
```bash
copy .env.example .env
```

### 4) Инициализировать БД и загрузить данные
```bash
.venv\Scripts\python scripts\init_db.py
.venv\Scripts\python scripts\load_json.py --file videos.json
```

### 5) Запустить бота
```bash
.venv\Scripts\python -m src.bot.app
```

## Проверка, что всё работает
### Тесты
```bash
python -m pytest -q
```

### Precheck перед `/check`
```bash
.venv\Scripts\python scripts\precheck.py --skip-telegram
```

### Smoke-набор фраз
```bash
.venv\Scripts\python scripts\smoke_bot.py
```

## Что на выходе
- Для метрик бот возвращает одно число (например, `358`).
- Для meta-запроса про период данных бот возвращает диапазон дат (например, `2025-05-28 — 2025-11-30`).
- Отчёт precheck сохраняется в `docs/precheck_report.md`.

## Архитектура (кратко)
- `src/bot` - Telegram handlers и форматирование ответа.
- `src/parser` - intents, rule parser, hybrid parser, LLM parser.
- `src/sql` - SQL-шаблоны и исполнение intent.
- `src/db` - создание пула подключений к PostgreSQL.
- `scripts` - init/load/smoke/precheck.
- `migrations` - SQL-схема таблиц и индексов.

## Поддерживаемые типы запросов (MVP)
- `Сколько всего видео есть в системе?`
- `Сколько видео набрало больше 100 000 просмотров за всё время?`
- `На сколько просмотров в сумме выросли все видео 28 ноября 2025?`
- `Сколько разных видео получали новые просмотры 27 ноября 2025?`
- `Сколько видео у креатора id ... вышло с ... по ...?`
- `Покажи диапазон дат видео` / `в какие дни видео`
- `Сколько всего просмотров`

## Как работает NLP в проекте
1. Rule parser пытается распознать запрос по шаблонам/триггерам.
2. Если intent `UNKNOWN`, включается GPT fallback (если разрешен в env).
3. Fallback возвращает строгий JSON intent (SQL модель не генерирует).
4. Intent исполняется через фиксированные SQL-шаблоны.

## Переменные окружения
Пример в `.env.example`:

```env
TELEGRAM_BOT_TOKEN=replace_with_token
DATABASE_URL=postgresql://postgres:postgres@localhost:15432/video_analytics
SQL_TIMEOUT_SECONDS=2
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
LLM_PARSER_ENABLED=1
LLM_DEBUG_LOGGING=0
LOG_LEVEL=INFO
```

Ключевые:
- `TELEGRAM_BOT_TOKEN` - токен бота.
- `DATABASE_URL` - строка подключения к PostgreSQL.
- `LLM_PARSER_ENABLED` - `1/0`, включить или выключить GPT fallback.
- `OPENAI_API_KEY` - нужен только если включен fallback.
- `LLM_DEBUG_LOGGING` - `1/0`, печать диагностических логов rule/LLM-парсера.
- `LOG_LEVEL` - уровень логов (`INFO`, `DEBUG`, ...).

## Railway (деплой)
В `Variables` сервиса укажи минимум:
- `TELEGRAM_BOT_TOKEN`
- `DATABASE_URL`
- `LLM_PARSER_ENABLED=1`
- `OPENAI_API_KEY` (если нужен fallback)

После изменения переменных сделай `Redeploy`/`Restart`.

### Как отловить, что происходит с GPT
1. В `Variables` выстави:
   - `LLM_DEBUG_LOGGING=1`
   - `LOG_LEVEL=INFO` (или `DEBUG`)
2. Сделай `Redeploy`.
3. В `Deploy Logs` смотри строки:
   - `Rule parser result: ...`
   - `Rule parser returned UNKNOWN, fallback to LLM`
   - `LLM request text=...`
   - `LLM raw response content=...`
   - `LLM parsed intent=...`

## Требования
- Python 3.12+
- Docker (для локального PostgreSQL)
- Доступ к Telegram Bot API
- PostgreSQL 16 (локально через `docker-compose` или Railway Postgres)

## Безопасность
`.env` и реальные ключи не коммитятся; используй `.env.example` как шаблон.
