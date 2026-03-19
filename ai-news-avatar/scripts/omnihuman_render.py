#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import sys
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


def api_request(url: str, api_key: str, payload: dict | None = None, method: str = "POST") -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "X-API-Key": api_key,
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        with request.urlopen(req) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OmniHuman API error: {exc.code}\n{body}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Network error: {exc.reason}") from exc


def main() -> int:
    load_env(ENV_PATH)
    api_key = os.environ.get("OMNIHUMAN_API_KEY")
    if not api_key:
        print("Missing OMNIHUMAN_API_KEY", file=sys.stderr)
        return 1

    if len(sys.argv) < 3:
        print("Usage: python3 ai-news-avatar/scripts/omnihuman_render.py <image_url> <audio_url>", file=sys.stderr)
        return 1

    image_url = sys.argv[1]
    audio_url = sys.argv[2]

    payload = {
        "model": "omni-human",
        "task_type": "omni-human-1.5",
        "input": {
            "image_url": image_url,
            "audio_url": audio_url,
            "prompt": "A professional female AI news host in business casual calmly delivers a short tech update to camera with natural lip sync, subtle head movement, and clean studio presentation.",
            "fast_mode": True,
        },
    }

    try:
        result = api_request("https://api.piapi.ai/api/v1/task", api_key, payload)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
