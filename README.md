# PROJECT_12_VOICE_BOT_VIDEO_SQL

Telegram bot for video analytics from natural language queries.

## Stack
- Python
- PostgreSQL
- aiogram
- Fully async flow (bot, DB I/O)

## Quick Start
```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
docker compose up -d
```

```bash
copy .env.example .env
.venv\Scripts\python scripts\init_db.py
.venv\Scripts\python scripts\load_json.py --file videos.json
```

```bash
.venv\Scripts\python -m src.bot.app
```

## Guarantees
- One request -> one numeric answer.
- No dialogue context storage.
- Deterministic parser in MVP (no LLM required).

## Bot UX
- `/start` -> friendly intro with examples.
- `/help` -> short usage guide.
- Any regular text query -> numeric result only.

## Checker-like local smoke
```bash
.venv\Scripts\python scripts\smoke_bot.py
```

## Precheck before /check
```bash
.venv\Scripts\python scripts\precheck.py --skip-telegram
```

For full validation (with Telegram token check):
```bash
.venv\Scripts\python scripts\precheck.py
```
