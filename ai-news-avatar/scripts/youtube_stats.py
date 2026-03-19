#!/usr/bin/env python3

from __future__ import annotations

import json
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


ROOT = Path(__file__).resolve().parents[1]
CLIENT_SECRET = ROOT / "client_secret.json"
TOKEN_PATH = ROOT / "youtube_token.json"

SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def get_credentials() -> Credentials:
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    elif not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
        creds = flow.run_local_server(port=0, open_browser=False)
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")

    return creds


def fetch_video_stats(youtube, video_ids: list[str]) -> dict[str, dict]:
    response = (
        youtube.videos()
        .list(part="snippet,statistics", id=",".join(video_ids))
        .execute()
    )
    result = {}
    for item in response.get("items", []):
        result[item["id"]] = {
            "title": item["snippet"]["title"],
            "publishedAt": item["snippet"]["publishedAt"],
            "views": item["statistics"].get("viewCount"),
            "likes": item["statistics"].get("likeCount"),
            "comments": item["statistics"].get("commentCount"),
        }
    return result


def fetch_analytics(youtube_analytics, video_id: str) -> dict:
    windows = [
        ("2026-03-01", "2026-03-18"),
        ("2026-01-01", "2026-03-18"),
        ("2025-01-01", "2026-03-18"),
    ]

    for start_date, end_date in windows:
        response = (
            youtube_analytics.reports()
            .query(
                ids="channel==MINE",
                startDate=start_date,
                endDate=end_date,
                metrics="views,engagedViews,averageViewDuration,averageViewPercentage,likes,comments,shares,subscribersGained,estimatedMinutesWatched",
                dimensions="video",
                filters=f"video=={video_id}",
            )
            .execute()
        )

        if response.get("rows"):
            columns = [col["name"] for col in response["columnHeaders"]]
            values = response["rows"][0]
            data = dict(zip(columns, values))
            data["_window"] = {"startDate": start_date, "endDate": end_date}
            return data

    return {}


def main() -> int:
    if len(sys.argv) < 2:
        print(
            "Usage: python3 ai-news-avatar/scripts/youtube_stats.py <video_id> [<video_id> ...]",
            file=sys.stderr,
        )
        return 1

    if not CLIENT_SECRET.exists():
        print(f"Missing client secret: {CLIENT_SECRET}", file=sys.stderr)
        return 1

    creds = get_credentials()
    youtube = build("youtube", "v3", credentials=creds)
    analytics = build("youtubeAnalytics", "v2", credentials=creds)

    video_ids = sys.argv[1:]
    video_stats = fetch_video_stats(youtube, video_ids)

    report = {}
    for video_id in video_ids:
        report[video_id] = {
            "video": video_stats.get(video_id, {}),
            "analytics": fetch_analytics(analytics, video_id),
        }

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
