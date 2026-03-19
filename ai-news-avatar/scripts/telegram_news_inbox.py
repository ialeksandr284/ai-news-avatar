#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from urllib import parse, request

from telegram_daily_report import format_report, get_credentials, get_recent_videos
from googleapiclient.discovery import build


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent
ENV_PATH = PROJECT_ROOT / ".env"
INBOX_PATH = ROOT / "inbox" / "news_inbox.md"
STATE_PATH = ROOT / "inbox" / "telegram_state.json"
ITEMS_PATH = ROOT / "inbox" / "news_items.json"
GROK_DRAFT_SCRIPT = ROOT / "scripts" / "grok_draft_engine.py"


def load_env(env_path: Path) -> None:
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def telegram_get(method: str) -> dict:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    url = f"https://api.telegram.org/bot{token}/{method}"
    with request.urlopen(url, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


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
    with request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def safe_telegram_post(method: str, payload: dict) -> dict:
    try:
        return telegram_post(method, payload)
    except Exception as exc:
        return {"ok": False, "error": str(exc), "method": method}


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {"last_update_id": 0}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def load_items() -> dict:
    if not ITEMS_PATH.exists():
        return {}
    return json.loads(ITEMS_PATH.read_text(encoding="utf-8"))


def save_items(items: dict) -> None:
    ITEMS_PATH.parent.mkdir(parents=True, exist_ok=True)
    ITEMS_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def extract_link(text: str) -> str:
    match = re.search(r"https?://\S+", text or "")
    return match.group(0) if match else ""


def append_inbox_entry(message: dict, update_id: int) -> dict:
    INBOX_PATH.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcfromtimestamp(message["date"]).strftime("%Y-%m-%d %H:%M UTC")
    sender = message.get("from", {})
    text = message.get("text", "") or message.get("caption", "")
    forward_from = ""
    if "forward_origin" in message:
        origin = message["forward_origin"]
        forward_from = origin.get("type", "")

    entry = (
        f"\n### {timestamp}\n"
        f"- Update ID: `{update_id}`\n"
        f"- From: {sender.get('first_name', '')}\n"
        f"- Username: {sender.get('username', '')}\n"
        f"- Text: {text}\n"
        f"- Link: {extract_link(text)}\n"
        f"- Forwarded from: {forward_from}\n"
        f"- Status: inbox\n"
    )
    with INBOX_PATH.open("a", encoding="utf-8") as handle:
        handle.write(entry)

    return {
        "update_id": update_id,
        "timestamp": timestamp,
        "from": sender.get("first_name", ""),
        "username": sender.get("username", ""),
        "text": text,
        "link": extract_link(text),
        "forwarded_from": forward_from,
        "status": "inbox",
    }


def build_keyboard(update_id: int) -> str:
    return json.dumps(
        {
            "inline_keyboard": [
                [
                    {"text": "Оценить", "callback_data": f"assess:{update_id}"},
                    {"text": "Сценарий", "callback_data": f"script:{update_id}"},
                ],
                [
                    {"text": "В рендер", "callback_data": f"render:{update_id}"},
                    {"text": "Стоп", "callback_data": f"stop:{update_id}"},
                ],
            ]
        },
        ensure_ascii=False,
    )


def build_reply_keyboard() -> str:
    return json.dumps(
        {
            "keyboard": [
                [{"text": "Статистика"}, {"text": "Скаут"}],
            ],
            "resize_keyboard": True,
            "persistent_keyboard": True,
        },
        ensure_ascii=False,
    )


def short_title(text: str) -> str:
    first_line = (text or "").strip().splitlines()[0].strip()
    return first_line[:90] if first_line else "Новая новость"


def assess_item(item: dict) -> str:
    text = item.get("text", "")
    link = item.get("link", "")
    score = 0
    reasons = []

    if link:
        score += 1
        reasons.append("есть ссылка на источник")
    if any(word in text.lower() for word in ["launch", "released", "выпуст", "анонс", "model", "api", "prompt", "seedance", "gemini", "openai", "anthropic"]):
        score += 1
        reasons.append("похоже на продуктовую или AI-новость")
    if len(text) > 120:
        score += 1
        reasons.append("хватает контекста для короткого пересказа")

    verdict = "годится" if score >= 2 else "сомнительно"
    return (
        f"Оценка: {verdict}\n"
        f"Причины: {', '.join(reasons) if reasons else 'мало данных'}\n"
        f"Тема: {short_title(text)}"
    )


def build_script(item: dict) -> str:
    text = item.get("text", "").strip()
    if not text:
        return "Черновик пока не собрался: в новости слишком мало текста."

    try:
        result = subprocess.run(
            ["python3", str(GROK_DRAFT_SCRIPT), text],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        payload = json.loads(result.stdout) if result.stdout.strip() else {}
    except Exception:
        payload = {}

    title = payload.get("story_title") or short_title(text)
    hook = payload.get("hook_ru") or title
    script = payload.get("script_ru")
    notes = payload.get("notes_ru", "")

    if not script:
        body = " ".join(line.strip() for line in text.splitlines()[1:] if line.strip())
        if not body:
            body = text
        script = (
            f"{title}. "
            f"Коротко: {body[:210].rstrip()} "
            f"Если тема взлетит, это стоит смотреть как сигнал для рынка и разработчиков."
        )

    output = [f"Черновик сценария:\n\nХук: {hook}\n\n{script}"]
    if notes:
        output.append(f"\nПримечание: {notes}")
    return "".join(output)


def update_item_status(items: dict, update_id: int, status: str) -> None:
    key = str(update_id)
    if key in items:
        items[key]["status"] = status


def handle_callback(callback_query: dict, items: dict) -> bool:
    data = callback_query.get("data", "")
    callback_id = callback_query.get("id")
    message = callback_query.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    if not data or not callback_id or not chat_id:
        return False

    try:
        action, raw_update_id = data.split(":", 1)
        update_id = int(raw_update_id)
    except ValueError:
        return False

    item = items.get(str(update_id))
    if not item:
        safe_telegram_post("answerCallbackQuery", {"callback_query_id": callback_id, "text": "Новость не найдена"})
        return False

    if action == "assess":
        text = assess_item(item)
    elif action == "script":
        text = build_script(item)
        update_item_status(items, update_id, "scripted")
    elif action == "render":
        text = "Ок, пометил новость как готовую к рендеру."
        update_item_status(items, update_id, "ready_to_render")
    elif action == "stop":
        text = "Ок, остановил эту новость. В работу не беру."
        update_item_status(items, update_id, "stopped")
    else:
        text = "Неизвестное действие."

    safe_telegram_post("answerCallbackQuery", {"callback_query_id": callback_id, "text": "Готово"})
    safe_telegram_post(
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": "true",
            "reply_markup": build_reply_keyboard(),
        },
    )
    return action in {"script", "render", "stop"}


def handle_text_command(text: str, expected_chat_id: int) -> bool:
    normalized = text.strip().lower()
    if normalized == "статистика":
        creds = get_credentials()
        youtube = build("youtube", "v3", credentials=creds)
        videos = get_recent_videos(youtube, limit=5)
        report = format_report(videos)
        safe_telegram_post(
            "sendMessage",
            {
                "chat_id": expected_chat_id,
                "text": report,
                "disable_web_page_preview": "true",
                "reply_markup": build_reply_keyboard(),
            },
        )
        return True

    if normalized == "скаут":
        news_scout_script = ROOT / "scripts" / "news_scout.py"
        result = subprocess.run(
            [os.environ.get("PYTHON_BIN", "python3"), str(news_scout_script)],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        message = "Запустил news scout."
        if result.returncode != 0:
            message = "Не смог запустить news scout."
        safe_telegram_post(
            "sendMessage",
            {
                "chat_id": expected_chat_id,
                "text": message,
                "disable_web_page_preview": "true",
                "reply_markup": build_reply_keyboard(),
            },
        )
        return True

    return False


def main() -> int:
    load_env(ENV_PATH)
    expected_chat_id = int(os.environ["TELEGRAM_CHAT_ID"])
    state = load_state()
    items = load_items()
    updates = telegram_get("getUpdates").get("result", [])

    latest_seen = state.get("last_update_id", 0)
    processed = 0

    for update in updates:
        update_id = update["update_id"]
        latest_seen = max(latest_seen, update_id)
        if update_id <= state.get("last_update_id", 0):
            continue

        callback_query = update.get("callback_query")
        if callback_query:
            if handle_callback(callback_query, items):
                processed += 1
            continue

        message = update.get("message")
        if not message:
            continue

        if message.get("chat", {}).get("id") != expected_chat_id:
            continue

        if message.get("from", {}).get("is_bot"):
            continue

        text = message.get("text", "") or message.get("caption", "")
        if not text or text.startswith("/"):
            continue

        if handle_text_command(text, expected_chat_id):
            processed += 1
            continue

        item = append_inbox_entry(message, update_id)
        items[str(update_id)] = item
        telegram_post(
            "sendMessage",
            {
                "chat_id": expected_chat_id,
                "text": f"Принял новость: {short_title(text)}",
                "disable_web_page_preview": "true",
                "reply_markup": build_keyboard(update_id),
            },
        )
        processed += 1

    save_state({"last_update_id": latest_seen})
    save_items(items)
    print(json.dumps({"processed": processed, "last_update_id": latest_seen}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
