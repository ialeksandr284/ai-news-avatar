#!/usr/bin/env python3

from __future__ import annotations

import email.utils
import json
import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib import parse, request


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent
ENV_PATH = PROJECT_ROOT / ".env"
ITEMS_PATH = ROOT / "inbox" / "news_items.json"
INBOX_PATH = ROOT / "inbox" / "news_inbox.md"
SCOUT_STATE_PATH = ROOT / "inbox" / "news_scout_state.json"

CORE_BRANDS = [
    "openai",
    "anthropic",
    "google",
    "deepmind",
    "xai",
    "meta",
    "mistral",
    "hugging face",
    "runway",
    "midjourney",
]

VIRAL_KEYWORDS = [
    "new model",
    "new models",
    "launch",
    "released",
    "announced",
    "rollout",
    "video",
    "image",
    "images",
    "generator",
    "avatar",
    "voice",
    "reasoning",
    "agent",
    "agents",
    "grok",
    "gemini",
    "chatgpt",
    "sora",
    "veo",
    "seedance",
    "runway",
    "image generation",
    "video generation",
    "multimodal",
    "real-time",
    "creative",
    "consumer",
    "app",
    "search",
]

DEPRIORITIZED_KEYWORDS = [
    "embedding",
    "embeddings",
    "inference stack",
    "benchmark",
    "eval",
    "sdk",
    "python sdk",
    "enterprise",
    "observability",
    "infrastructure",
    "backend",
    "security patch",
    "compliance",
    "documentation",
]

FEEDS = [
    ("OpenAI", "https://openai.com/news/rss.xml"),
    ("Anthropic", "https://www.anthropic.com/news/rss.xml"),
    ("Google Blog AI", "https://blog.google/technology/ai/rss/"),
    ("Google Developers", "https://developers.googleblog.com/feeds/posts/default"),
    ("Hugging Face", "https://huggingface.co/blog/feed.xml"),
    ("Mistral", "https://mistral.ai/news/rss.xml"),
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


def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def telegram_post(method: str, payload: dict) -> dict:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    url = f"https://api.telegram.org/bot{token}/{method}"
    body = parse.urlencode(payload).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def build_keyboard(item_id: int) -> str:
    return json.dumps(
        {
            "inline_keyboard": [
                [
                    {"text": "Оценить", "callback_data": f"assess:{item_id}"},
                    {"text": "Сценарий", "callback_data": f"script:{item_id}"},
                ],
                [
                    {"text": "В рендер", "callback_data": f"render:{item_id}"},
                    {"text": "Стоп", "callback_data": f"stop:{item_id}"},
                ],
            ]
        },
        ensure_ascii=False,
    )


def build_reply_keyboard() -> str:
    return json.dumps(
        {
            "keyboard": [[{"text": "Статистика"}]],
            "resize_keyboard": True,
            "persistent_keyboard": True,
        },
        ensure_ascii=False,
    )


def fetch_feed(url: str) -> bytes:
    req = request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with request.urlopen(req, timeout=30) as response:
        return response.read()


def parse_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def first_text(element: ET.Element | None, names: list[str]) -> str:
    if element is None:
        return ""
    for name in names:
        found = element.find(name)
        if found is not None and found.text:
            return found.text.strip()
    return ""


def parse_entries(xml_bytes: bytes, source_name: str) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    entries: list[dict] = []

    channel_items = root.findall(".//channel/item")
    atom_entries = root.findall(".//{http://www.w3.org/2005/Atom}entry")
    generic_entries = channel_items or atom_entries

    for entry in generic_entries:
        title = first_text(entry, ["title", "{http://www.w3.org/2005/Atom}title"])
        summary = first_text(
            entry,
            [
                "description",
                "summary",
                "{http://www.w3.org/2005/Atom}summary",
                "{http://www.w3.org/2005/Atom}content",
            ],
        )
        link = first_text(entry, ["link"])
        if not link:
            atom_link = entry.find("{http://www.w3.org/2005/Atom}link")
            if atom_link is not None:
                link = atom_link.attrib.get("href", "").strip()

        published = first_text(
            entry,
            [
                "pubDate",
                "published",
                "updated",
                "{http://www.w3.org/2005/Atom}published",
                "{http://www.w3.org/2005/Atom}updated",
            ],
        )

        entries.append(
            {
                "source": source_name,
                "title": title,
                "summary": summary,
                "link": link,
                "published_at": parse_datetime(published),
            }
        )
    return entries


def score_entry(entry: dict) -> int:
    haystack = f"{entry['title']} {entry['summary']}".lower()
    score = 0

    for brand in CORE_BRANDS:
        if brand in haystack:
            score += 2

    for keyword in VIRAL_KEYWORDS:
        if keyword in haystack:
            score += 2

    if any(word in haystack for word in ["model", "models", "launch", "released", "announced"]):
        score += 3

    if any(word in haystack for word in ["video", "image", "avatar", "voice", "generator"]):
        score += 4

    if any(word in haystack for word in ["faster", "better", "cheaper", "real-time", "viral", "popular"]):
        score += 2

    for keyword in DEPRIORITIZED_KEYWORDS:
        if keyword in haystack:
            score -= 3

    if any(word in haystack for word in ["embedding", "embeddings"]) and not any(
        word in haystack for word in ["video", "image", "consumer", "search", "chatgpt", "gemini", "grok"]
    ):
        score -= 4

    return score


def is_fresh(entry: dict) -> bool:
    return entry["published_at"] >= datetime.now(timezone.utc) - timedelta(days=3)


def shortlist(entries: list[dict], existing_links: set[str], limit: int = 3) -> list[dict]:
    deduped = []
    seen = set(existing_links)
    for entry in entries:
        link = entry.get("link", "")
        if not link or link in seen:
            continue
        if not is_fresh(entry):
            continue
        score = score_entry(entry)
        if score < 2:
            continue
        entry["score"] = score
        deduped.append(entry)
        seen.add(link)

    deduped.sort(key=lambda item: (item["score"], item["published_at"]), reverse=True)
    return deduped[:limit]


def append_inbox_entry(item_id: int, entry: dict) -> None:
    INBOX_PATH.parent.mkdir(parents=True, exist_ok=True)
    timestamp = entry["published_at"].strftime("%Y-%m-%d %H:%M UTC")
    text = f"{entry['title']}\n\n{entry['summary']}\n\nИсточник: {entry['link']}"
    block = (
        f"\n### {timestamp}\n"
        f"- Update ID: `{item_id}`\n"
        f"- From: news_scout\n"
        f"- Username: railway_worker\n"
        f"- Text: {text}\n"
        f"- Link: {entry['link']}\n"
        f"- Forwarded from: {entry['source']}\n"
        f"- Status: inbox\n"
    )
    with INBOX_PATH.open("a", encoding="utf-8") as handle:
        handle.write(block)


def send_shortlist_item(item_id: int, entry: dict) -> None:
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    text = (
        f"Найдена охватная AI-новость\n\n"
        f"{entry['title']}\n\n"
        f"Источник: {entry['source']}\n"
        f"Скоринг: {entry['score']}\n"
        f"{entry['link']}"
    )
    telegram_post(
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": "false",
            "reply_markup": build_keyboard(item_id),
        },
    )


def send_no_news_message() -> None:
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    telegram_post(
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": "News scout: сильных новых AI-новостей в этот прогон не нашёл.",
            "disable_web_page_preview": "true",
            "reply_markup": build_reply_keyboard(),
        },
    )


def next_item_id(items: dict) -> int:
    numeric_ids = [int(key) for key in items.keys() if str(key).isdigit()]
    base = int(time.time())
    return max(numeric_ids + [base]) + 1


def main() -> int:
    load_env(ENV_PATH)
    items = load_json(ITEMS_PATH, {})
    state = load_json(SCOUT_STATE_PATH, {"seen_links": []})
    existing_links = {item.get("link", "") for item in items.values() if item.get("link")}
    existing_links.update(state.get("seen_links", []))

    all_entries: list[dict] = []
    for source_name, url in FEEDS:
        try:
            xml_bytes = fetch_feed(url)
            all_entries.extend(parse_entries(xml_bytes, source_name))
        except Exception as exc:
            print(json.dumps({"source": source_name, "url": url, "error": str(exc)}, ensure_ascii=False))

    picks = shortlist(all_entries, existing_links, limit=3)
    if not picks:
        send_no_news_message()
        return 0

    item_id = next_item_id(items)
    for entry in picks:
        current_id = item_id
        item_id += 1
        text = f"{entry['title']}\n\n{entry['summary']}\n\nИсточник: {entry['link']}"
        items[str(current_id)] = {
            "update_id": current_id,
            "timestamp": entry["published_at"].strftime("%Y-%m-%d %H:%M UTC"),
            "from": "news_scout",
            "username": "railway_worker",
            "text": text,
            "link": entry["link"],
            "forwarded_from": entry["source"],
            "status": "inbox",
            "source": entry["source"],
            "score": entry["score"],
        }
        append_inbox_entry(current_id, entry)
        send_shortlist_item(current_id, entry)
        state.setdefault("seen_links", []).append(entry["link"])

    save_json(ITEMS_PATH, items)
    save_json(SCOUT_STATE_PATH, state)
    print(json.dumps({"picked": len(picks)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
