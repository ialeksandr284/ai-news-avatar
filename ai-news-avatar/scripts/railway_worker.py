#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent
ENV_PATH = PROJECT_ROOT / ".env"
STATE_PATH = ROOT / "inbox" / "worker_state.json"
MOSCOW = ZoneInfo("Europe/Moscow")


def load_env(env_path: Path) -> None:
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {"last_daily_report_date": ""}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def run_script(script_name: str) -> None:
    script_path = ROOT / "scripts" / script_name
    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    timestamp = datetime.now(MOSCOW).strftime("%Y-%m-%d %H:%M:%S %Z")
    if result.stdout.strip():
        print(f"[{timestamp}] {script_name} stdout:\n{result.stdout.strip()}", flush=True)
    if result.stderr.strip():
        print(f"[{timestamp}] {script_name} stderr:\n{result.stderr.strip()}", flush=True)


def main() -> int:
    load_env(ENV_PATH)
    state = load_state()
    poll_seconds = int(os.environ.get("TG_POLL_INTERVAL_SECONDS", "60"))
    report_hour = int(os.environ.get("DAILY_REPORT_HOUR_MSK", "19"))
    scout_hours = {
        int(hour.strip())
        for hour in os.environ.get("NEWS_SCOUT_HOURS_MSK", "10,14,18").split(",")
        if hour.strip()
    }

    print(
        f"Railway worker started. Poll interval={poll_seconds}s, daily report hour={report_hour}:00 MSK, scout hours={sorted(scout_hours)}",
        flush=True,
    )

    while True:
        now = datetime.now(MOSCOW)
        run_script("telegram_news_inbox.py")

        today = now.strftime("%Y-%m-%d")
        scout_key = f"{today}-{now.hour:02d}"
        seen_scout_runs = set(state.get("scout_runs", []))
        if now.hour in scout_hours and scout_key not in seen_scout_runs:
            run_script("news_scout.py")
            seen_scout_runs.add(scout_key)
            state["scout_runs"] = sorted(seen_scout_runs)[-20:]
            save_state(state)

        if now.hour >= report_hour and state.get("last_daily_report_date") != today:
            run_script("telegram_daily_report.py")
            state["last_daily_report_date"] = today
            save_state(state)

        time.sleep(poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
