#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from urllib import error, request


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent
ENV_PATH = PROJECT_ROOT / ".env"
PROMPT_PATH = ROOT / "prompts" / "grok_draft_prompt.md"


def load_env(env_path: Path) -> None:
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def extract_json(text: str) -> dict | None:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def fallback(text: str) -> dict:
    first_line = text.strip().splitlines()[0].strip() if text.strip() else "Новая AI-новость"
    body = " ".join(line.strip() for line in text.splitlines()[1:] if line.strip())
    if not body:
        body = text.strip()
    script = (
        f"{first_line}. "
        f"Коротко: {body[:220].rstrip()} "
        f"Если это подтвердится сильными источниками, новость можно брать в короткий разбор."
    )
    return {
        "decision": "needs_more_research",
        "story_title": first_line[:90],
        "hook_ru": first_line[:120],
        "script_ru": script,
        "notes_ru": "Сработал локальный fallback, потому что Grok draft engine недоступен.",
    }


def main() -> int:
    load_env(ENV_PATH)
    if len(sys.argv) < 2:
        print("Usage: python3 ai-news-avatar/scripts/grok_draft_engine.py <news_text>", file=sys.stderr)
        return 1

    news_text = sys.argv[1]
    api_url = os.environ.get("GROK_DRAFT_API_URL")
    model = os.environ.get("GROK_DRAFT_MODEL", "grok-3-fast")
    proxy = os.environ.get("GROK_DRAFT_PROXY") or None

    if not api_url:
        print(json.dumps(fallback(news_text), ensure_ascii=False, indent=2))
        return 0

    system_prompt = PROMPT_PATH.read_text(encoding="utf-8") if PROMPT_PATH.exists() else ""
    message = (
        f"{system_prompt}\n\n"
        f"Inbound news lead:\n{news_text}\n\n"
        f"Return JSON only."
    )

    payload = json.dumps(
        {
            "proxy": proxy,
            "message": message,
            "model": model,
            "extra_data": None,
        }
    ).encode("utf-8")

    req = request.Request(
        api_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=45) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (error.URLError, error.HTTPError, json.JSONDecodeError):
        print(json.dumps(fallback(news_text), ensure_ascii=False, indent=2))
        return 0

    raw_response = data.get("response", "")
    parsed = extract_json(raw_response)
    if not parsed:
        print(json.dumps(fallback(news_text), ensure_ascii=False, indent=2))
        return 0

    print(json.dumps(parsed, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
