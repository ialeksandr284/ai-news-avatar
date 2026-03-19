#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import textwrap
from datetime import datetime
from pathlib import Path
from urllib import error, parse, request

from telegram_daily_report import format_report, get_credentials, get_recent_videos
from googleapiclient.discovery import build


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent
ENV_PATH = PROJECT_ROOT / ".env"
INBOX_PATH = ROOT / "inbox" / "news_inbox.md"
STATE_PATH = ROOT / "inbox" / "telegram_state.json"
ITEMS_PATH = ROOT / "inbox" / "news_items.json"
GROK_DRAFT_SCRIPT = ROOT / "scripts" / "grok_draft_engine.py"
BUFFER_CHANNEL_ID = os.environ.get("BUFFER_CHANNEL_ID", "69ba7fe47be9f8b1716ad1c3")
SCRIPT_MAX_CHARS = 330


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


def build_publish_keyboard(update_id: int) -> str:
    return json.dumps(
        {
            "inline_keyboard": [
                [
                    {"text": "Окей -> YouTube", "callback_data": f"publish:{update_id}"},
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


def sanitize_for_script(text: str) -> str:
    cleaned = re.sub(r"https?://\S+", "", text or "")
    cleaned = re.sub(r"@\w+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def is_mostly_english(text: str) -> bool:
    latin = len(re.findall(r"[A-Za-z]", text or ""))
    cyrillic = len(re.findall(r"[А-Яа-яЁё]", text or ""))
    return latin > cyrillic * 2 and latin > 20


def clean_html_entities(text: str) -> str:
    replacements = {
        "&#8217;": "'",
        "&amp;": "&",
        "&quot;": '"',
        "&#8230;": "...",
    }
    cleaned = text or ""
    for src, dst in replacements.items():
        cleaned = cleaned.replace(src, dst)
    return cleaned


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
    title = short_title(sanitize_for_script(clean_html_entities(item.get("text", ""))))
    body = " ".join(
        line.strip()
        for line in sanitize_for_script(clean_html_entities(item.get("text", ""))).splitlines()[1:]
        if line.strip()
    )
    body = body or sanitize_for_script(clean_html_entities(item.get("text", ""))).strip()

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


def compress_fact(body_ru: str, title: str = "") -> str:
    fact = re.sub(r"\s+", " ", body_ru).strip(" .")
    fact = re.sub(r"^(Источник:.*)$", "", fact, flags=re.IGNORECASE).strip(" .")
    if title:
        title_norm = re.escape(title.strip())
        fact = re.sub(rf"^{title_norm}[\s\.\:\-–—]*", "", fact, flags=re.IGNORECASE).strip(" .")
    return textwrap.shorten(fact, width=135, placeholder="...")


def build_russian_title(item: dict, fact: str) -> str:
    source = (item.get("source") or item.get("forwarded_from") or "").lower()
    text = clean_html_entities(item.get("text", ""))
    title = short_title(text)
    haystack = f"{title} {fact}".lower()

    if "gpt-5.4" in haystack:
        return "OpenAI показала GPT-5.4 mini и nano"
    if "gemini" in haystack and "personal" in haystack:
        return "Google расширяет персональный Gemini"
    if "claude code" in haystack and any(word in haystack for word in ["love", "hate", "hate.", "hate "]):
        return "Сетап Claude Code неожиданно разделил AI-сообщество"
    if "seedance" in haystack:
        return "Для Seedance собрали большую библиотеку промптов"
    if any(word in haystack for word in ["video", "image", "avatar", "generator", "render"]):
        return "В AI-контенте появилась новая заметная фишка"
    if "openai" in source or "openai" in haystack:
        return "OpenAI выкатила новый заметный апдейт"
    if "google" in source or "gemini" in haystack:
        return "Google выкатила новый AI-апдейт"
    if "anthropic" in source or "claude" in haystack:
        return "Anthropic выкатила заметное обновление Claude"
    return "Появилась новая заметная AI-новость"


def infer_russian_fact(item: dict, fallback_fact: str) -> str:
    text = clean_html_entities(item.get("text", ""))
    link = (item.get("link") or "").lower()
    haystack = f"{text} {link}".lower()

    if not is_mostly_english(text):
        return fallback_fact

    if "claude code" in haystack and any(word in haystack for word in ["love", "hate"]):
        return "тысячи людей повторяют популярный сетап Claude Code от Гарри Тана, и AI-сообщество резко спорит, помогает ли он в реальной работе"
    if "gpt-5.4" in haystack and "mini" in haystack and "nano" in haystack:
        return "OpenAI показала облегчённые версии GPT-5.4, чтобы модель можно было запускать дешевле и шире в реальных продуктах"
    if "gemini" in haystack and "personal" in haystack:
        return "Google расширяет персонализированный Gemini и делает его заметно ближе к массовому пользователю"
    if "seedance" in haystack and any(word in haystack for word in ["prompt", "library", "github"]):
        return "для Seedance уже собрали большую библиотеку готовых промптов и удачных примеров, чтобы не писать всё с нуля"
    if any(word in haystack for word in ["video", "image", "generator", "render", "avatar"]):
        return "появился новый заметный AI-апдейт, который может повлиять на создание видео, изображений или другого контента"
    if "claude" in haystack:
        return "обновление вокруг Claude вызвало большой интерес, потому что его сразу примеряют к реальным рабочим сценариям"
    if "openai" in haystack:
        return "OpenAI показала очередной заметный апдейт, который быстро разойдётся по рынку и по креаторскому AI-сегменту"
    if "google" in haystack or "gemini" in haystack:
        return "Google выкатила AI-обновление, которое пытается стать более массовым и понятным обычному пользователю"
    return "вышла новая AI-новость, которую сейчас активно обсуждают, потому что у неё есть заметный прикладной эффект"


def build_hashtags(item: dict) -> str:
    base = ["#ai", "#shorts"]
    haystack = clean_html_entities(item.get("text", "")).lower()
    if "video" in haystack or "seedance" in haystack or "runway" in haystack:
        base.append("#aivideo")
    elif "image" in haystack or "midjourney" in haystack:
        base.append("#aiimages")
    elif "gpt" in haystack or "chatgpt" in haystack:
        base.append("#chatgpt")
    elif "gemini" in haystack:
        base.append("#gemini")
    elif "claude" in haystack:
        base.append("#claude")
    else:
        base.append("#ainews")
    return " ".join(base[:4])


def build_video_copy_variants(title: str, fact: str) -> list[dict]:
    variants = [
        {
            "video_title": title,
            "script": (
                f"Если ты следишь за AI-инструментами для контента, вот коротко что произошло. "
                f"{title}. "
                f"По сути, {fact}. "
                f"И это как раз тот случай, когда новость можно быстро перевести в практику, а не просто обсудить и забыть."
            ),
            "angle": "практическая подача",
        },
        {
            "video_title": f"{title}: почему об этом все говорят",
            "script": (
                f"Похоже, это одна из тех AI-новостей, которые быстро расходятся не только у гиков. "
                f"{title}. "
                f"Если совсем коротко, {fact}. "
                f"История цепляет потому, что эффект понятен почти сразу, особенно если ты делаешь видео, картинки или любой контент."
            ),
            "angle": "охватный заход",
        },
        {
            "video_title": f"{title}: что это меняет на практике",
            "script": (
                f"Вот новость, которую сегодня точно будут пересказывать все, кто работает с AI-контентом. "
                f"{title}. "
                f"Смысл новости такой: {fact}. "
                f"Именно такие сюжеты обычно набирают лучше, потому что за 20 секунд уже понятно, зачем человеку вообще это знать."
            ),
            "angle": "виральный пересказ",
        },
    ]
    for variant in variants:
        variant["script"] = textwrap.shorten(variant["script"], width=SCRIPT_MAX_CHARS, placeholder="...")
    return variants


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
    fact = compress_fact(body_ru, title_ru)
    fact = infer_russian_fact(item, fact)
    title = build_russian_title(item, fact)
    base_script = payload.get("script_ru")
    notes = payload.get("notes_ru", "")
    using_local_fallback = "локальный fallback" in notes.lower()

    stats = best_hook_notes()
    variants = build_video_copy_variants(title, fact)

    if base_script and not using_local_fallback:
        variants[0]["script"] = textwrap.shorten(base_script, width=SCRIPT_MAX_CHARS, placeholder="...")

    for variant in variants:
        if stats["top_title"] and stats["best_views"]:
            if "релиза" in stats["hook_style"] or "релиз" in stats["hook_style"]:
                variant["script"] = variant["script"].replace(
                    "Именно такие сюжеты обычно набирают лучше, потому что за 20 секунд уже понятно, зачем человеку вообще это знать.",
                    "Такие сюжеты заходят лучше, когда с первых секунд чувствуешь, что это реальный новый релиз или заметный апдейт.",
                )
        variant["hashtags"] = build_hashtags(item)
    return variants


def create_did_talk(script_text: str) -> dict:
    api_key = os.environ.get("DID_API_KEY")
    source_url = os.environ.get("DID_SOURCE_IMAGE_URL")
    if not api_key:
        raise RuntimeError("Не задан DID_API_KEY")
    if not source_url:
        raise RuntimeError("Не задан DID_SOURCE_IMAGE_URL")

    payload = {
        "source_url": source_url,
        "script": {
            "type": "text",
            "provider": {
                "type": "microsoft",
                "voice_id": "ru-RU-SvetlanaNeural",
            },
            "input": script_text,
        },
        "config": {"stitch": True},
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
    with request.urlopen(req, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def get_did_talk(talk_id: str) -> dict:
    api_key = os.environ.get("DID_API_KEY")
    req = request.Request(
        f"https://api.d-id.com/talks/{talk_id}",
        headers={
            "Authorization": f"Basic {api_key}",
            "Accept": "application/json",
        },
        method="GET",
    )
    with request.urlopen(req, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_for_did_result(talk_id: str, timeout_seconds: int = 240) -> dict:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        data = get_did_talk(talk_id)
        status = data.get("status")
        if status == "done":
            return data
        if status in {"error", "rejected", "failed"}:
            raise RuntimeError(f"D-ID завершился со статусом {status}")
        time.sleep(8)
    raise RuntimeError("D-ID рендер не успел завершиться вовремя")


def send_preview(chat_id: int, title: str, preview_url: str) -> None:
    result = safe_telegram_post(
        "sendVideo",
        {
            "chat_id": chat_id,
            "video": preview_url,
            "caption": f"Превью готово\n\n{title}",
            "reply_markup": build_reply_keyboard(),
        },
    )
    if result.get("ok"):
        return
    safe_telegram_post(
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": f"Превью готово\n\n{title}\n{preview_url}",
            "disable_web_page_preview": "false",
            "reply_markup": build_reply_keyboard(),
        },
    )


def send_preview_with_approval(chat_id: int, title: str, preview_url: str, update_id: int) -> None:
    result = safe_telegram_post(
        "sendVideo",
        {
            "chat_id": chat_id,
            "video": preview_url,
            "caption": f"Превью готово\n\n{title}",
            "reply_markup": build_publish_keyboard(update_id),
        },
    )
    if result.get("ok"):
        return
    safe_telegram_post(
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": f"Превью готово\n\n{title}\n{preview_url}",
            "disable_web_page_preview": "false",
            "reply_markup": build_publish_keyboard(update_id),
        },
    )


def publish_to_buffer(title: str, text: str, video_url: str) -> tuple[bool, str]:
    if not BUFFER_CHANNEL_ID:
        return False, "Не задан BUFFER_CHANNEL_ID"
    script_path = ROOT / "scripts" / "buffer_publish.py"
    result = subprocess.run(
        [sys.executable, str(script_path), BUFFER_CHANNEL_ID, title, text, video_url],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if result.returncode != 0:
        return False, (result.stderr or result.stdout or "Buffer publish failed").strip()
    return True, result.stdout.strip()


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
        safe_telegram_post(
            "answerCallbackQuery",
            {"callback_query_id": callback_id, "text": "Карточка устарела, нажми Скаут ещё раз"},
        )
        safe_telegram_post(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": "Эта карточка уже устарела или ещё не успела сохраниться. Нажми `Скаут` и используй свежую карточку.",
                "parse_mode": "Markdown",
                "disable_web_page_preview": "true",
                "reply_markup": build_reply_keyboard(),
            },
        )
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
            item["chosen_title"] = chosen["video_title"]
            item["chosen_hashtags"] = chosen["hashtags"]
        if not chosen:
            text = "Сначала выбери один из трёх сценариев."
        else:
            text = (
                f"Запускаю рендер варианта {variant_idx}.\n\n"
                f"Заголовок: {chosen['video_title']}\n\n"
                f"{chosen['script']}"
            )
        update_item_status(items, update_id, "ready_to_render")
    elif action == "publish":
        preview_url = item.get("preview_url")
        chosen_title = item.get("chosen_title")
        chosen_script = item.get("chosen_script")
        chosen_hashtags = item.get("chosen_hashtags", "")
        source_link = item.get("link", "")
        if not preview_url or not chosen_title or not chosen_script:
            text = "Сначала нужно получить превью через кнопку `В рендер`."
        else:
            publish_text = f"{chosen_script}\n\nИсточник: {source_link}\n{chosen_hashtags}".strip()
            ok, details = publish_to_buffer(chosen_title, publish_text, preview_url)
            if ok:
                update_item_status(items, update_id, "published")
                text = "Ок, отправил ролик в YouTube через Buffer."
            else:
                update_item_status(items, update_id, "publish_failed")
                text = f"Не смог отправить ролик в Buffer: {details}"
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
                            f"Заголовок: {variant['video_title']}\n\n"
                            f"Текст:\n{variant['script']}\n\n"
                            f"Хештеги: {variant['hashtags']}"
                        ),
                        "disable_web_page_preview": "true",
                        "reply_markup": build_render_keyboard(update_id, idx),
                    },
                )
    elif action == "render":
        safe_telegram_post(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": text,
                "disable_web_page_preview": "true",
                "reply_markup": build_reply_keyboard(),
            },
        )
        chosen_script = item.get("chosen_script")
        try:
            if not chosen_script:
                raise RuntimeError("Сценарий для рендера не найден")
            talk = create_did_talk(chosen_script)
            talk_id = talk.get("id", "")
            item["did_talk_id"] = talk_id
            if not talk_id:
                raise RuntimeError("D-ID не вернул id рендера")
            result = wait_for_did_result(talk_id)
            preview_url = result.get("result_url", "")
            item["preview_url"] = preview_url
            item["did_status"] = result.get("status", "")
            update_item_status(items, update_id, "preview_ready")
            if preview_url:
                send_preview_with_approval(chat_id, item.get("chosen_title") or short_title(item.get("text", "")), preview_url, update_id)
            else:
                safe_telegram_post(
                    "sendMessage",
                    {
                        "chat_id": chat_id,
                        "text": "Рендер завершился, но D-ID не вернул ссылку на превью.",
                        "disable_web_page_preview": "true",
                        "reply_markup": build_reply_keyboard(),
                    },
                )
        except Exception as exc:
            item["render_error"] = str(exc)
            update_item_status(items, update_id, "render_failed")
            safe_telegram_post(
                "sendMessage",
                {
                    "chat_id": chat_id,
                    "text": f"Не смог отрендерить превью: {exc}",
                    "disable_web_page_preview": "true",
                    "reply_markup": build_reply_keyboard(),
                },
            )
    elif action == "publish":
        safe_telegram_post(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": text,
                "disable_web_page_preview": "true",
                "reply_markup": build_reply_keyboard(),
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
    return action in {"script", "render", "publish"}


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
