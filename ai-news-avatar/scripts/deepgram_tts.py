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

    api_key = os.environ.get("DEEPGRAM_API_KEY")
    if not api_key:
        print("Missing DEEPGRAM_API_KEY", file=sys.stderr)
        return 1

    if len(sys.argv) < 2:
        print('Usage: python3 ai-news-avatar/scripts/deepgram_tts.py "Текст для озвучки"', file=sys.stderr)
        return 1

    text = sys.argv[1]
    payload = json.dumps({"text": text}).encode("utf-8")

    req = request.Request(
        "https://api.deepgram.com/v1/speak?model=aura-2-thalia-en",
        data=payload,
        headers={
            "Authorization": f"Token {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with request.urlopen(req) as response:
            audio = response.read()
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"Deepgram API error: {exc.code}\n{body}", file=sys.stderr)
        return 1
    except error.URLError as exc:
        print(f"Network error: {exc.reason}", file=sys.stderr)
        return 1

    out_dir = PROJECT_ROOT / "ai-news-avatar" / "outputs" / "audio"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "latest_tts.mp3"
    out_path.write_bytes(audio)
    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
