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
    api_key = os.environ.get("DID_API_KEY")
    if not api_key:
        print("Missing DID_API_KEY", file=sys.stderr)
        return 1

    if len(sys.argv) < 3:
        print("Usage: python3 ai-news-avatar/scripts/did_create_talk.py <image_url> <text>", file=sys.stderr)
        return 1

    image_url = sys.argv[1]
    text = sys.argv[2]

    payload = {
        "source_url": image_url,
        "script": {
            "type": "text",
            "provider": {
                "type": "microsoft",
                "voice_id": "ru-RU-SvetlanaNeural",
            },
            "input": text,
        },
        "config": {
            "stitch": True,
        },
    }

    req = request.Request(
        "https://api.d-id.com/talks",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Basic {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=120) as response:
            data = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"D-ID API error: {exc.code}\n{body}", file=sys.stderr)
        return 1
    except error.URLError as exc:
        print(f"Network error: {exc.reason}", file=sys.stderr)
        return 1

    print(json.dumps(data, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
