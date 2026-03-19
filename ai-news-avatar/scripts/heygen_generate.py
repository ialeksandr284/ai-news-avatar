#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from urllib import error, request


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"


def load_env(env_path: Path) -> None:
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def api_request(url: str, api_key: str, payload: dict | None = None, method: str = "GET") -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = request.Request(
        url,
        data=data,
        headers={
            "X-API-KEY": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method=method,
    )
    try:
        with request.urlopen(req, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HeyGen API error: {exc.code}\n{body}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Network error: {exc.reason}") from exc


def main() -> int:
    load_env(ENV_PATH)
    api_key = os.environ.get("HEYGEN_API_KEY")
    avatar_id = os.environ.get("HEYGEN_AVATAR_ID")
    voice_id = os.environ.get("HEYGEN_VOICE_ID")

    if not api_key or not avatar_id or not voice_id:
        print("Missing HEYGEN_API_KEY, HEYGEN_AVATAR_ID, or HEYGEN_VOICE_ID", file=sys.stderr)
        return 1

    if len(sys.argv) < 2:
        print('Usage: python3 ai-news-avatar/scripts/heygen_generate.py "Текст ролика"', file=sys.stderr)
        return 1

    text = sys.argv[1]

    payload = {
        "video_inputs": [
            {
                "character": {
                    "type": "avatar",
                    "avatar_id": avatar_id,
                    "avatar_style": "normal",
                },
                "voice": {
                    "type": "text",
                    "input_text": text,
                    "voice_id": voice_id,
                    "speed": 1.0,
                },
            }
        ],
        "dimension": {
            "width": 1080,
            "height": 1920,
        },
    }

    try:
        created = api_request(
            "https://api.heygen.com/v2/video/generate",
            api_key=api_key,
            payload=payload,
            method="POST",
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(created, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
