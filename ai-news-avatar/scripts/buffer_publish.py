#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib import error, parse, request


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


def build_reply_keyboard() -> str:
    return json.dumps(
        {
            "keyboard": [[{"text": "Статистика"}, {"text": "Скаут"}]],
            "resize_keyboard": True,
            "persistent_keyboard": True,
        },
        ensure_ascii=False,
    )


def send_telegram_publish_notice(title: str, youtube_url: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return

    text = f"Ролик опубликован\n\n{title}\n{youtube_url}"
    payload = parse.urlencode(
        {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": "false",
            "reply_markup": build_reply_keyboard(),
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
    token = os.environ.get("BUFFER_ACCESS_TOKEN")
    if not token:
        print("Missing BUFFER_ACCESS_TOKEN", file=sys.stderr)
        return 1

    if len(sys.argv) < 5:
        print(
            "Usage: python3 ai-news-avatar/scripts/buffer_publish.py <channel_id> <title> <text> <video_url>",
            file=sys.stderr,
        )
        return 1

    channel_id = sys.argv[1]
    title = sys.argv[2]
    text = sys.argv[3]
    video_url = sys.argv[4]

    query = """
    mutation CreatePost($input: CreatePostInput!) {
      createPost(input: $input) {
        __typename
        ... on PostActionSuccess {
          post {
            id
            status
            shareMode
            text
            externalLink
            channelId
          }
        }
        ... on InvalidInputError { message }
        ... on RestProxyError { message code link }
        ... on UnauthorizedError { message }
        ... on UnexpectedError { message }
        ... on LimitReachedError { message }
        ... on NotFoundError { message }
      }
    }
    """

    payload = json.dumps(
        {
            "query": query,
            "variables": {
                "input": {
                    "channelId": channel_id,
                    "schedulingType": "automatic",
                    "mode": "shareNow",
                    "text": text,
                    "metadata": {
                        "youtube": {
                            "title": title,
                            "categoryId": "28",
                            "madeForKids": False,
                            "embeddable": True,
                            "notifySubscribers": False,
                        }
                    },
                    "assets": {
                        "videos": [
                            {
                                "url": video_url,
                                "metadata": {
                                    "title": title,
                                },
                            }
                        ]
                    },
                }
            },
        }
    ).encode("utf-8")

    req = request.Request(
        "https://api.buffer.com",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
            "Origin": "https://developers.buffer.com",
            "Referer": "https://developers.buffer.com/",
        },
        method="POST",
    )

    try:
        with request.urlopen(req) as response:
            result = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"Buffer API error: {exc.code}\n{body}", file=sys.stderr)
        return 1
    except error.URLError as exc:
        print(f"Network error: {exc.reason}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, ensure_ascii=False))

    payload = result.get("data", {}).get("createPost", {})
    if payload.get("__typename") == "PostActionSuccess":
        post = payload.get("post", {})
        external_link = post.get("externalLink")
        if external_link:
            send_telegram_publish_notice(title, external_link)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
