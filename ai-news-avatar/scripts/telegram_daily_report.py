#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib import parse, request

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent
ENV_PATH = PROJECT_ROOT / ".env"
TOKEN_PATH = ROOT / "youtube_token.json"

SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def load_env(env_path: Path) -> None:
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def get_credentials() -> Credentials:
    token_json = os.environ.get("YOUTUBE_TOKEN_JSON")
    if token_json:
        return Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)
    return Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)


def get_recent_videos(youtube, limit: int = 5) -> list[dict]:
    channel = youtube.channels().list(part="contentDetails,snippet", mine=True).execute()["items"][0]
    uploads_id = channel["contentDetails"]["relatedPlaylists"]["uploads"]
    channel_title = channel["snippet"]["title"]

    playlist = (
        youtube.playlistItems()
        .list(part="snippet,contentDetails", playlistId=uploads_id, maxResults=limit)
        .execute()
    )

    video_ids = [item["contentDetails"]["videoId"] for item in playlist.get("items", [])]
    if not video_ids:
        return []

    details = (
        youtube.videos()
        .list(part="snippet,statistics", id=",".join(video_ids))
        .execute()
    )

    by_id = {item["id"]: item for item in details.get("items", [])}
    result = []
    for item in playlist.get("items", []):
        video_id = item["contentDetails"]["videoId"]
        meta = by_id.get(video_id, {})
        stats = meta.get("statistics", {})
        snippet = meta.get("snippet", {})
        result.append(
            {
                "channel_title": channel_title,
                "video_id": video_id,
                "title": snippet.get("title", item["snippet"].get("title", "")),
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats.get("likeCount", 0)),
                "comments": int(stats.get("commentCount", 0)),
                "url": f"https://www.youtube.com/watch?v={video_id}",
            }
        )
    return result


def format_report(videos: list[dict]) -> str:
    if not videos:
        return "Ежедневный отчет Smol\n\nПока нет роликов для анализа."

    channel_title = videos[0]["channel_title"]
    total_views = sum(video["views"] for video in videos)
    best = max(videos, key=lambda video: video["views"])
    worst = min(videos, key=lambda video: video["views"])

    lines = [
        f"Ежедневный отчет YouTube: {channel_title}",
        "",
        f"Всего просмотров по последним {len(videos)} роликам: {total_views}",
        f"Лучший ролик: {best['title']} — {best['views']}",
        f"Слабейший ролик: {worst['title']} — {worst['views']}",
        "",
        "Последние ролики:",
    ]

    for video in videos:
        lines.append(
            f"- {video['title']}\n  просмотры: {video['views']}, лайки: {video['likes']}, комменты: {video['comments']}\n  {video['url']}"
        )

    lines.extend(
        [
            "",
            "Быстрый вывод:",
            "- смотри на тему, заголовок и первую фразу",
            "- если ролик проседает, усиливаем упаковку и хук",
            "- если тема выигрывает, масштабируем похожие сюжеты",
        ]
    )
    return "\n".join(lines)


def build_reply_keyboard() -> str:
    return json.dumps(
        {
            "keyboard": [
                [{"text": "Статистика"}],
            ],
            "resize_keyboard": True,
            "persistent_keyboard": True,
        },
        ensure_ascii=False,
    )


def send_telegram_message(text: str) -> dict:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")

    payload = parse.urlencode(
        {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": "true",
            "reply_markup": build_reply_keyboard(),
        }
    ).encode("utf-8")

    req = request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    load_env(ENV_PATH)
    creds = get_credentials()
    youtube = build("youtube", "v3", credentials=creds)
    videos = get_recent_videos(youtube, limit=5)
    report = format_report(videos)

    if "--print" in sys.argv:
        print(report)
        return 0

    result = send_telegram_message(report)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
