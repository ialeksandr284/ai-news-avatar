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


def main() -> int:
    load_env(ENV_PATH)
    api_key = os.environ.get("HEYGEN_API_KEY")
    if not api_key:
        print("Missing HEYGEN_API_KEY", file=sys.stderr)
        return 1

    if len(sys.argv) < 2:
        print("Usage: python3 ai-news-avatar/scripts/heygen_status.py <video_id>", file=sys.stderr)
        return 1

    video_id = sys.argv[1]
    req = request.Request(
        f"https://api.heygen.com/v1/video_status.get?video_id={video_id}",
        headers={
            "X-API-KEY": api_key,
            "Accept": "application/json",
        },
        method="GET",
    )

    try:
        with request.urlopen(req, timeout=120) as response:
            data = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"HeyGen API error: {exc.code}\n{body}", file=sys.stderr)
        return 1
    except error.URLError as exc:
        print(f"Network error: {exc.reason}", file=sys.stderr)
        return 1

    print(json.dumps(data, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
