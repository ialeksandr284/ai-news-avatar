#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import re
import subprocess
import textwrap
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
                    {"text": "3 сценария", "callback_data": f"script:{update_id}"},
                ],
            ]
        },
        ensure_ascii=False,
    )


def build_render_keyboard(update_id: int, variant: int) -> str:
    return json.dumps(
        {
            "inline_keyboard": [
                [
                    {"text": f"В рендер вариант {variant}", "callback_data": f"render:{update_id}:{variant}"},
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


def best_hook_notes() -> dict:
    try:
        creds = get_credentials()
        youtube = build("youtube", "v3", credentials=creds)
        videos = get_recent_videos(youtube, limit=5)
    except Exception:
        videos = []

    if not videos:
        return {
            "top_title": "",
            "best_views": 0,
            "hook_style": "начинать с явного последствия и громкого нового релиза",
        }

    best = max(videos, key=lambda item: item["views"])
    title = best.get("title", "")
    hook_style = "делать первую фразу более прикладной и заметной"
    if any(word in title.lower() for word in ["google", "nano", "banana", "new", "нов"]):
        hook_style = "лучше заходят новости с ощущением нового релиза и понятной пользы"

    return {
        "top_title": title,
        "best_views": best.get("views", 0),
        "hook_style": hook_style,
    }


def adapt_source_to_russian(item: dict) -> tuple[str, str]:
    title = short_title(item.get("text", ""))
    body = " ".join(line.strip() for line in item.get("text", "").splitlines()[1:] if line.strip())
    body = body or item.get("text", "").strip()

    title_ru = title
    replacements = {
        "OpenAI": "OpenAI",
        "Google": "Google",
        "Anthropic": "Anthropic",
        "launches": "запустила",
        "launch": "запуск",
        "releases": "выпустила",
        "release": "релиз",
        "announces": "анонсировала",
        "announced": "анонсировала",
        "new model": "новую модель",
        "video": "видео",
        "image": "изображения",
        "images": "изображения",
        "voice": "голос",
        "reasoning": "reasoning",
        "agent": "агент",
        "agents": "агенты",
    }
    for src, dst in replacements.items():
        title_ru = title_ru.replace(src, dst)
        body = body.replace(src, dst)

    return title_ru.strip(), body.strip()


def build_script_variants(item: dict) -> list[dict]:
    text = item.get("text", "").strip()
    if not text:
        return []

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

    title_ru, body_ru = adapt_source_to_russian(item)
    title = payload.get("story_title") or title_ru or short_title(text)
    base_hook = payload.get("hook_ru") or title
    base_script = payload.get("script_ru")
    notes = payload.get("notes_ru", "")

    if not base_script:
        base_script = (
            f"{title}. "
            f"Коротко: {body_ru[:170].rstrip()} "
            f"Это может быстро разойтись по AI-комьюнити, если фича реально даёт заметный эффект."
        )

    stats = best_hook_notes()
    style_hint = stats["hook_style"]

    variants = [
        {
            "hook": base_hook,
            "script": base_script,
            "angle": "прямой релиз",
        },
        {
            "hook": f"Похоже, это одна из самых обсуждаемых AI-новостей дня: {title}",
            "script": (
                f"{title}. "
                f"Смысл новости простой: {body_ru[:150].rstrip()}. "
                f"Если это реально даст заметный результат в картинках, видео или контенте, история может быстро разойтись далеко за пределы гиковской аудитории."
            ),
            "angle": "виральный сигнал",
        },
        {
            "hook": f"Вот AI-обновление, которое легко может залететь в охваты: {title}",
            "script": (
                f"{title}. "
                f"По сути, речь про вот что: {body_ru[:145].rstrip()}. "
                f"Я специально подаю это через угол массового эффекта, потому что у нас лучше заходят истории, где новая штука понятна за одну фразу и сразу чувствуется практический результат."
            ),
            "angle": "охватный угол",
        },
    ]

    if notes:
        variants[0]["script"] = f"{variants[0]['script']} Примечание: {notes}"

    for variant in variants:
        variant["script"] = textwrap.shorten(variant["script"], width=430, placeholder="...")
        variant["meta"] = f"Стиль: {style_hint}. Лучший прошлый ролик: {stats['top_title']} ({stats['best_views']} views)."

    return variants


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
        parts = data.split(":")
        action = parts[0]
        update_id = int(parts[1])
        variant_idx = int(parts[2]) if len(parts) > 2 else None
    except ValueError:
        return False

    item = items.get(str(update_id))
    if not item:
        safe_telegram_post("answerCallbackQuery", {"callback_query_id": callback_id, "text": "Новость не найдена"})
        return False

    if action == "script":
        variants = build_script_variants(item)
        item["script_variants"] = variants
        update_item_status(items, update_id, "scripted")
    elif action == "render":
        chosen = None
        variants = item.get("script_variants", [])
        if variant_idx and 1 <= variant_idx <= len(variants):
            chosen = variants[variant_idx - 1]
            item["chosen_variant"] = variant_idx
            item["chosen_script"] = chosen["script"]
            item["chosen_hook"] = chosen["hook"]
        text = "Ок, пометил сценарий как готовый к рендеру."
        if chosen:
            text = (
                f"Ок, отправляем в рендер вариант {variant_idx}.\n\n"
                f"Хук: {chosen['hook']}\n\n"
                f"{chosen['script']}"
            )
        update_item_status(items, update_id, "ready_to_render")
    else:
        text = "Неизвестное действие."

    safe_telegram_post("answerCallbackQuery", {"callback_query_id": callback_id, "text": "Готово"})
    if action == "script":
        if not item.get("script_variants"):
            safe_telegram_post(
                "sendMessage",
                {
                    "chat_id": chat_id,
                    "text": "Не смог собрать 3 сценария: в новости слишком мало сигнала.",
                    "disable_web_page_preview": "true",
                    "reply_markup": build_reply_keyboard(),
                },
            )
        else:
            safe_telegram_post(
                "sendMessage",
                {
                    "chat_id": chat_id,
                    "text": "Собрал 3 русских сценария с более охватными хуками.",
                    "disable_web_page_preview": "true",
                    "reply_markup": build_reply_keyboard(),
                },
            )
            for idx, variant in enumerate(item["script_variants"], start=1):
                safe_telegram_post(
                    "sendMessage",
                    {
                        "chat_id": chat_id,
                        "text": (
                            f"Вариант {idx}\n\n"
                            f"Хук: {variant['hook']}\n\n"
                            f"{variant['script']}\n\n"
                            f"{variant['meta']}"
                        ),
                        "disable_web_page_preview": "true",
                        "reply_markup": build_render_keyboard(update_id, idx),
                    },
                )
    else:
        safe_telegram_post(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": text,
                "disable_web_page_preview": "true",
                "reply_markup": build_reply_keyboard(),
            },
        )
    return action in {"script", "render"}


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
