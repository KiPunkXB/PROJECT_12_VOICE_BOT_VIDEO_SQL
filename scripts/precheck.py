from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import asyncpg


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from src.core.env_loader import load_dotenv_if_exists


@dataclass
class CheckResult:
    name: str
    ok: bool
    details: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local precheck before /check")
    parser.add_argument("--skip-telegram", action="store_true", help="Skip Telegram token/network validation")
    parser.add_argument("--skip-smoke", action="store_true", help="Skip smoke_bot.py execution")
    return parser.parse_args()


async def check_database(database_url: str) -> list[CheckResult]:
    results: list[CheckResult] = []
    try:
        connection = await asyncpg.connect(database_url, ssl=False)
    except Exception as exc:
        return [CheckResult("database_connection", False, f"Cannot connect: {type(exc).__name__}: {exc}")]

    try:
        videos_count = await connection.fetchval("SELECT COUNT(*) FROM videos;")
        snapshots_count = await connection.fetchval("SELECT COUNT(*) FROM video_snapshots;")
        results.append(CheckResult("database_connection", True, "Connected successfully"))
        results.append(CheckResult("videos_table_count", bool(videos_count and videos_count > 0), f"videos={videos_count}"))
        results.append(
            CheckResult(
                "video_snapshots_table_count",
                bool(snapshots_count and snapshots_count > 0),
                f"video_snapshots={snapshots_count}",
            )
        )
    except Exception as exc:
        results.append(CheckResult("database_queries", False, f"Query failed: {type(exc).__name__}: {exc}"))
    finally:
        await connection.close()
    return results


def check_env(database_url: str, token: str, skip_telegram: bool) -> list[CheckResult]:
    results: list[CheckResult] = []
    results.append(CheckResult("database_url_present", bool(database_url), "DATABASE_URL is set" if database_url else "DATABASE_URL is missing"))
    token_ok = bool(token) or skip_telegram
    token_details = "TELEGRAM_BOT_TOKEN is set" if token else ("Skipped by --skip-telegram" if skip_telegram else "TELEGRAM_BOT_TOKEN is missing")
    results.append(CheckResult("telegram_token_present", token_ok, token_details))
    return results


def check_telegram_token(token: str) -> CheckResult:
    if not token:
        return CheckResult("telegram_getMe", False, "Token missing")
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        with urlopen(url, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if payload.get("ok"):
            return CheckResult("telegram_getMe", True, "Bot token is valid")
        return CheckResult("telegram_getMe", False, f"Telegram API returned ok=false: {payload}")
    except (HTTPError, URLError, TimeoutError) as exc:
        return CheckResult("telegram_getMe", False, f"Network/API error: {type(exc).__name__}: {exc}")


def run_smoke_script() -> CheckResult:
    command = [sys.executable, str(ROOT / "scripts" / "smoke_bot.py")]
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True, cwd=ROOT)
    except Exception as exc:
        return CheckResult("smoke_bot", False, f"Failed to execute smoke script: {type(exc).__name__}: {exc}")

    if result.returncode != 0:
        tail = (result.stdout + "\n" + result.stderr).strip()[-1200:]
        return CheckResult("smoke_bot", False, f"smoke_bot.py exit={result.returncode}\n{tail}")

    output = result.stdout.strip()
    ok = "Passed 20/20" in output
    return CheckResult("smoke_bot", ok, output[-1200:])


def write_report(results: list[CheckResult]) -> Path:
    report_path = ROOT / "docs" / "precheck_report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [
        "# Precheck Report",
        "",
        f"Generated at: {ts}",
        "",
    ]
    for item in results:
        status = "✅" if item.ok else "❌"
        lines.append(f"- {status} `{item.name}`: {item.details}")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


async def main() -> int:
    args = parse_args()
    load_dotenv_if_exists(ROOT)
    database_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:15432/video_analytics")
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

    results: list[CheckResult] = []
    results.extend(check_env(database_url, token, args.skip_telegram))
    results.extend(await check_database(database_url))

    if not args.skip_telegram:
        results.append(check_telegram_token(token))
    else:
        results.append(CheckResult("telegram_getMe", True, "Skipped by --skip-telegram"))

    if not args.skip_smoke:
        results.append(run_smoke_script())
    else:
        results.append(CheckResult("smoke_bot", True, "Skipped by --skip-smoke"))

    report = write_report(results)
    print(f"Report: {report}")
    for r in results:
        print(f"{'OK' if r.ok else 'FAIL'} | {r.name} | {r.details}")

    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
