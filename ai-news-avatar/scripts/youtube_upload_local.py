#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from youtube_stats import get_credentials


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent
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


def send_telegram_notice(title: str, url: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return

    from urllib import parse, request

    payload = parse.urlencode(
        {
            "chat_id": chat_id,
            "text": f"Ролик загружен в YouTube\n\n{title}\n{url}",
            "disable_web_page_preview": "false",
        }
    ).encode("utf-8")
    req = request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=20):
            pass
    except Exception:
        pass


def main() -> int:
    load_env(ENV_PATH)

    if len(sys.argv) < 5:
        print(
            "Usage: python3 ai-news-avatar/scripts/youtube_upload_local.py <video_path> <title> <description> <tags_json> [privacyStatus]",
            file=sys.stderr,
        )
        return 1

    video_path = Path(sys.argv[1]).expanduser()
    title = sys.argv[2]
    description = sys.argv[3]
    tags = json.loads(sys.argv[4])
    privacy_status = sys.argv[5] if len(sys.argv) > 5 else "public"

    if not video_path.exists():
        print(f"Video not found: {video_path}", file=sys.stderr)
        return 1

    creds = get_credentials()
    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": "28",
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True, mimetype="video/*")
    request_upload = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        _, response = request_upload.next_chunk()

    video_id = response["id"]
    url = f"https://www.youtube.com/watch?v={video_id}"
    send_telegram_notice(title, url)
    print(json.dumps({"video_id": video_id, "url": url}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
