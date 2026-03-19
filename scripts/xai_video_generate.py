#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from urllib import error, request


PROJECT_ROOT = Path(__file__).resolve().parent.parent
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


def parse_args(argv: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    i = 0
    while i < len(argv):
        current = argv[i]
        if not current.startswith("--"):
            i += 1
            continue
        key = current[2:]
        next_value = argv[i + 1] if i + 1 < len(argv) else None
        if not next_value or next_value.startswith("--"):
            parsed[key] = "true"
            i += 1
        else:
            parsed[key] = next_value
            i += 2
    return parsed


def print_help() -> None:
    print(
        """Usage:
  python3 scripts/xai_video_generate.py --prompt "A moody synth studio reveal" --duration 8 --aspect 16:9 --resolution 720p
  python3 scripts/xai_video_generate.py --prompt "Animate this image" --image-url "https://example.com/input.png"
  python3 scripts/xai_video_generate.py --prompt "Change the lighting to colder" --video-url "https://example.com/input.mp4"

Options:
  --prompt        Required prompt
  --duration      Optional, 1-15 seconds for generation
  --aspect        Optional, e.g. 16:9, 9:16, 1:1, 3:4
  --resolution    Optional, 480p or 720p
  --image-url     Optional source image URL for image-to-video
  --video-url     Optional source video URL for video editing
  --timeout       Optional poll timeout in seconds, default 600
  --interval      Optional poll interval in seconds, default 5
"""
    )


def api_request(url: str, api_key: str, method: str = "GET", payload: dict | None = None) -> dict:
    data = None
    headers = {"Authorization": f"Bearer {api_key}"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = request.Request(url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"xAI API error: {exc.code}\n{body}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Network error: {exc.reason}") from exc


def main() -> int:
    load_env(ENV_PATH)
    args = parse_args(sys.argv[1:])

    if not args or "--help" in sys.argv[1:]:
        print_help()
        return 0

    api_key = os.environ.get("XAI_API_KEY")
    if not api_key:
        print("Missing XAI_API_KEY in environment.", file=sys.stderr)
        return 1

    prompt = args.get("prompt")
    if not prompt:
        print("Missing required --prompt argument.", file=sys.stderr)
        return 1

    model = os.environ.get("XAI_VIDEO_MODEL", "grok-imagine-video")
    timeout_seconds = int(args.get("timeout", "600"))
    interval_seconds = int(args.get("interval", "5"))

    payload: dict[str, object] = {
        "model": model,
        "prompt": prompt,
    }

    if "duration" in args:
        payload["duration"] = int(args["duration"])
    if "aspect" in args:
        payload["aspect_ratio"] = args["aspect"]
    if "resolution" in args:
        payload["resolution"] = args["resolution"]
    if "image-url" in args:
        payload["image_url"] = args["image-url"]
    if "video-url" in args:
        payload["video_url"] = args["video-url"]

    start = api_request(
        "https://api.x.ai/v1/videos/generations",
        api_key=api_key,
        method="POST",
        payload=payload,
    )

    request_id = start.get("request_id")
    if not request_id:
        print(json.dumps(start, indent=2))
        print("xAI did not return request_id.", file=sys.stderr)
        return 1

    deadline = time.time() + timeout_seconds
    status_url = f"https://api.x.ai/v1/videos/{request_id}"

    while time.time() < deadline:
        result = api_request(status_url, api_key=api_key)
        status = result.get("status")

        if status == "done":
            print(json.dumps(result, indent=2))
            return 0
        if status == "expired":
            print(json.dumps(result, indent=2))
            print("xAI request expired before completion.", file=sys.stderr)
            return 1

        time.sleep(interval_seconds)

    print(json.dumps({"request_id": request_id, "status": "timeout"}, indent=2))
    print("Timed out while waiting for xAI video generation.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
