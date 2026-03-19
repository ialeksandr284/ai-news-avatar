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
POOL_PATH = ROOT / "inbox" / "news_pool.json"
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


def load_pool() -> dict:
    if not POOL_PATH.exists():
        return {"refreshed_at": "", "candidates": []}
    return json.loads(POOL_PATH.read_text(encoding="utf-8"))


def save_items(items: dict) -> None:
    ITEMS_PATH.parent.mkdir(parents=True, exist_ok=True)
    ITEMS_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def next_item_id(items: dict) -> int:
    numeric_ids = [int(key) for key in items.keys() if str(key).isdigit()]
    base = int(time.time())
    return max(numeric_ids + [base]) + 1


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


def item_from_scout_card(message_text: str, update_id: int) -> dict | None:
    text = clean_html_entities(message_text or "").strip()
    if not text.startswith("Найдена охватная AI-новость"):
        return None

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 4:
        return None

    title = lines[1]
    source = ""
    link = ""
    for line in lines[2:]:
        if line.lower().startswith("источник:"):
            source = line.split(":", 1)[1].strip()
        elif line.startswith("http://") or line.startswith("https://"):
            link = line.strip()

    if not title:
        return None

    rebuilt_text = f"{title}\n\nИсточник: {source}\n\n{link}".strip()
    return {
        "update_id": update_id,
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "from": "news_scout_card",
        "username": "railway_worker",
        "text": rebuilt_text,
        "link": link,
        "forwarded_from": source,
        "source": source,
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


def build_scout_card(entry: dict) -> str:
    synopsis = textwrap.shorten(clean_html_entities(entry.get("summary", "")).strip(), width=220, placeholder="...")
    parts = [
        "Найдена охватная AI-новость",
        "",
        entry.get("title", "").strip(),
    ]
    if synopsis:
        parts.extend(["", f"Синопсис: {synopsis}"])
    parts.extend(
        [
            "",
            f"Источник: {entry.get('source', '').strip()}",
            f"Скоринг: {entry.get('score', 0)}",
            entry.get("link", "").strip(),
        ]
    )
    return "\n".join(part for part in parts if part is not None)


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


def rough_translate_text(text: str) -> str:
    translated = clean_html_entities(text or "")
    replacements = [
        ("task execution", "выполнению задач"),
        ("content planning", "планирование контента"),
        ("small teams", "небольшие команды"),
        ("real working scenarios", "реальные рабочие сценарии"),
        ("working scenarios", "рабочие сценарии"),
        ("repetitive steps", "рутинные шаги"),
        ("move from chat to", "переходить от чата к"),
        ("lets teams", "позволяет командам"),
        ("workflow", "рабочий сценарий"),
        ("workflows", "рабочие сценарии"),
        ("creators", "создатели контента"),
        ("creator", "создатель контента"),
        ("teams", "команды"),
        ("team", "команда"),
        ("faster", "быстрее"),
        ("slower", "медленнее"),
        ("update", "обновление"),
        ("launch", "запуск"),
        ("released", "выпустила"),
        ("release", "релиз"),
        ("new", "новый"),
        ("tool", "инструмент"),
        ("tools", "инструменты"),
        ("content", "контент"),
        ("image", "изображение"),
        ("images", "изображения"),
        ("video", "видео"),
        ("voice", "озвучка"),
        ("chat", "чат"),
    ]
    for src, dst in replacements:
        translated = re.sub(rf"(?i)\b{re.escape(src)}\b", dst, translated)
    translated = re.sub(r"\s+", " ", translated).strip()
    return translated


def fact_is_generic(fact: str) -> bool:
    lower = (fact or "").lower()
    generic_markers = [
        "вышла новая ai-новость",
        "обновление вокруг claude вызвало большой интерес",
        "openai показала очередной заметный апдейт",
        "google выкатила ai-обновление",
        "появился новый заметный ai-апдейт",
    ]
    return any(marker in lower for marker in generic_markers)


def fetch_url_text(url: str) -> str:
    req = request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
        },
    )
    with request.urlopen(req, timeout=30) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="ignore")


def extract_article_text(html: str) -> str:
    cleaned = re.sub(r"(?is)<script.*?</script>", " ", html)
    cleaned = re.sub(r"(?is)<style.*?</style>", " ", cleaned)
    cleaned = re.sub(r"(?is)<noscript.*?</noscript>", " ", cleaned)
    paragraphs = re.findall(r"(?is)<p[^>]*>(.*?)</p>", cleaned)
    chunks: list[str] = []
    for paragraph in paragraphs:
        text = re.sub(r"(?is)<[^>]+>", " ", paragraph)
        text = clean_html_entities(text)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text.split()) < 8:
            continue
        if any(
            bad in text.lower()
            for bad in ["subscribe", "sign up", "cookie", "privacy policy", "all rights reserved", "advertisement"]
        ):
            continue
        chunks.append(text)
        if len(" ".join(chunks)) > 5000:
            break

    if not chunks:
        text = re.sub(r"(?is)<[^>]+>", " ", cleaned)
        text = clean_html_entities(text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:5000]
    return " ".join(chunks)[:5000]


def fetch_article_text(link: str) -> str:
    if not link:
        return ""
    try:
        return extract_article_text(fetch_url_text(link))
    except Exception:
        return ""


def pick_article_fact(article_text: str, fallback: str) -> str:
    if not article_text:
        return fallback
    sentences = [
        sentence.strip(" .")
        for sentence in re.split(r"(?<=[.!?])\s+", article_text)
        if sentence.strip()
    ]
    selected = []
    for sentence in sentences:
        lower = sentence.lower()
        if len(sentence) < 55 or len(sentence) > 240:
            continue
        if any(bad in lower for bad in ["cookie", "subscribe", "advertisement", "sign up", "privacy policy"]):
            continue
        if not re.search(r"[A-Za-zА-Яа-яЁё]", sentence):
            continue
        selected.append(sentence)
        if len(selected) == 2:
            break

    if not selected:
        return fallback

    fact = " ".join(selected)
    fact = re.sub(r"\s+", " ", fact).strip(" .")
    return textwrap.shorten(fact, width=220, placeholder="...")


def synthesize_fact_from_article(item: dict, article_text: str, fallback_fact: str) -> str:
    text = clean_html_entities(article_text or "")
    if not text:
        return fallback_fact

    lower = text.lower()
    source_text = clean_html_entities(item.get("text", ""))
    brand = "инструмент"
    if "claude" in lower or "anthropic" in lower or "claude" in source_text.lower():
        brand = "Claude"
    elif "chatgpt" in lower or "openai" in lower or "openai" in source_text.lower():
        brand = "ChatGPT"
    elif "gemini" in lower or "google" in lower or "gemini" in source_text.lower():
        brand = "Gemini"
    elif "grok" in lower:
        brand = "Grok"

    parts = []
    if any(word in lower for word in ["workflow", "workflows"]):
        parts.append(f"в {brand} появился новый рабочий сценарий")
    if any(phrase in lower for phrase in ["task execution", "move from chat to task execution"]):
        parts.append("который помогает быстрее переходить от чата к выполнению задач")
    if "repetitive steps" in lower:
        parts.append("и убирает часть рутинных шагов")
    if "content planning" in lower:
        parts.append("в том числе в планировании контента")
    if any(word in lower for word in ["creators", "creator", "small teams", "teams"]):
        parts.append("поэтому его сразу примеряют к работе создатели контента и небольшие команды")
    if any(word in lower for word in ["video generation", "video model", "video generator"]):
        return "вышел новый AI-видео-инструмент, который обещает ускорить генерацию роликов и сделать качество ближе к коммерческому продакшну"
    if any(word in lower for word in ["image generation", "image model", "photo editing", "image editing"]):
        return "вышло обновление, которое усиливает генерацию изображений и делает AI-картинки полезнее для реальной работы"
    if any(word in lower for word in ["avatar", "voice", "speech"]) and any(word in lower for word in ["creator", "content", "teams"]):
        return "появился инструмент, который может заметно упростить аватары, озвучку и производство короткого контента"

    if parts:
        sentence = " ".join(parts)
        sentence = re.sub(r"\s+", " ", sentence).strip(" .")
        return sentence[0].upper() + sentence[1:] if sentence else fallback_fact

    return fallback_fact


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
    raw = sanitize_for_script(clean_html_entities(item.get("text", "")))
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    title = lines[0] if lines else short_title(raw)
    body = " ".join(
        line
        for line in lines[1:]
        if line and not line.lower().startswith("источник:")
    )
    body = body or raw.strip()

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

    return rough_translate_text(title_ru.strip()), rough_translate_text(body.strip())


def compress_fact(body_ru: str, title: str = "") -> str:
    fact = re.sub(r"\s+", " ", body_ru).strip(" .")
    fact = re.sub(r"^(Источник:.*)$", "", fact, flags=re.IGNORECASE).strip(" .")
    if title:
        title_norm = re.escape(title.strip())
        fact = re.sub(rf"^{title_norm}[\s\.\:\-–—]*", "", fact, flags=re.IGNORECASE).strip(" .")
    return textwrap.shorten(fact, width=185, placeholder="...")


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
    title_text = short_title(text).strip()
    if title_text and not is_mostly_english(title_text) and len(title_text) > 12:
        return title_text[:90]
    return "Вышла новая AI-функция, которую уже начали примерять к реальной работе"


def infer_russian_fact(item: dict, fallback_fact: str) -> str:
    text = clean_html_entities(item.get("text", ""))
    link = (item.get("link") or "").lower()
    haystack = f"{text} {link}".lower()

    translated_fallback = rough_translate_text(fallback_fact)
    if translated_fallback and not fact_is_generic(translated_fallback):
        return translated_fallback

    if not is_mostly_english(text):
        return translated_fallback or fallback_fact

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
    return translated_fallback or "вышла новая AI-новость, которую сейчас активно обсуждают, потому что у неё есть заметный прикладной эффект"


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


def build_listener_value(item: dict, title: str, fact: str) -> str:
    haystack = f"{clean_html_entities(item.get('text', ''))} {title} {fact}".lower()
    if any(word in haystack for word in ["video", "runway", "seedance", "veo", "sora", "generator", "render"]):
        return "для зрителя это важно, потому что новые AI-видео и генераторы обычно быстро меняют качество и скорость продакшна"
    if any(word in haystack for word in ["image", "images", "midjourney", "photo", "photoshop"]):
        return "для зрителя это важно, потому что такие апдейты быстро доходят до генерации картинок, рекламы и визуального контента"
    if any(word in haystack for word in ["voice", "avatar", "audio", "speech"]):
        return "для зрителя это важно, потому что такие инструменты быстро упрощают озвучку, аватары и вертикальные ролики"
    if any(word in haystack for word in ["claude", "chatgpt", "gpt", "gemini", "grok"]):
        return "для зрителя это важно, потому что такие обновления быстро влияют на повседневные сценарии работы, поиска идей и создания контента"
    return "для зрителя это важно, потому что подобные AI-апдейты очень быстро доходят до обычных продуктов и креаторских инструментов"


def sanitize_generated_script(text: str) -> str:
    cleaned = clean_html_entities(text or "")
    cleaned = re.sub(r"(?im)^\s*(хук|hook|стиль|style|заголовок|title|хештеги|hashtags)\s*:\s*", "", cleaned)
    cleaned = re.sub(r"https?://\S+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .\n")
    return cleaned


def looks_like_publishable_russian_script(text: str) -> bool:
    cleaned = sanitize_generated_script(text)
    if not cleaned:
        return False
    latin = len(re.findall(r"[A-Za-z]", cleaned))
    cyr = len(re.findall(r"[А-Яа-яЁё]", cleaned))
    if cyr < 80:
        return False
    if latin > cyr // 3:
        return False
    return True


def strip_noise_lines(text: str) -> str:
    lines = []
    for raw in (text or "").splitlines():
        line = clean_html_entities(raw).strip()
        if not line:
            continue
        if line.startswith("http://") or line.startswith("https://"):
            continue
        if line.startswith("@"):
            continue
        if line.lower().startswith("источник:"):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def split_sentences(text: str) -> list[str]:
    chunks = []
    for sentence in re.split(r"(?<=[.!?])\s+", clean_html_entities(text or "")):
        cleaned = re.sub(r"\s+", " ", sentence).strip(" .\n")
        if cleaned:
            chunks.append(cleaned)
    return chunks


def detect_topic(haystack: str) -> str:
    lower = haystack.lower()
    if any(word in lower for word in ["prompt library", "prompts", "github", "library"]) and "seedance" in lower:
        return "prompt_library"
    if any(word in lower for word in ["video", "veo", "sora", "seedance", "runway", "render"]):
        return "video"
    if any(word in lower for word in ["image", "photo", "photoshop", "midjourney"]):
        return "image"
    if any(word in lower for word in ["avatar", "voice", "speech", "audio"]):
        return "avatar_voice"
    if any(word in lower for word in ["chatgpt", "gpt", "claude", "gemini", "grok"]):
        return "assistant"
    return "general"


def detect_product_name(haystack: str) -> str:
    mapping = [
        ("seedance", "Seedance 2.0"),
        ("chatgpt", "ChatGPT"),
        ("gpt-5.4", "GPT-5.4"),
        ("gpt", "GPT"),
        ("claude code", "Claude Code"),
        ("claude", "Claude"),
        ("gemini", "Gemini"),
        ("grok", "Grok"),
        ("runway", "Runway"),
        ("veo", "Veo"),
        ("sora", "Sora"),
        ("midjourney", "Midjourney"),
        ("photoshop", "Photoshop"),
        ("anthropic", "Anthropic"),
        ("openai", "OpenAI"),
        ("google", "Google"),
    ]
    lower = haystack.lower()
    for key, value in mapping:
        if key in lower:
            return value
    return ""


def score_fact_sentence(sentence: str, product: str) -> int:
    lower = sentence.lower()
    score = 0
    if 45 <= len(sentence) <= 220:
        score += 2
    if product and product.lower() in lower:
        score += 4
    for token in [
        "launch",
        "launched",
        "release",
        "released",
        "announced",
        "introduces",
        "introduced",
        "now",
        "can",
        "lets",
        "support",
        "supports",
        "add",
        "added",
        "new",
        "video",
        "image",
        "creator",
        "prompt",
        "github",
        "model",
        "tool",
        "feature",
    ]:
        if token in lower:
            score += 1
    if any(bad in lower for bad in ["cookie", "privacy", "subscribe", "advertisement", "all rights reserved"]):
        score -= 5
    if sentence.count("...") > 0:
        score -= 2
    return score


def pick_concrete_fact(item: dict, article_text: str, fallback_fact: str) -> str:
    source_text = strip_noise_lines(item.get("text", ""))
    title_line = source_text.splitlines()[0].strip() if source_text.splitlines() else ""
    haystack = f"{title_line}\n{source_text}\n{article_text}".strip()
    product = detect_product_name(haystack)

    candidates = split_sentences(article_text) + split_sentences(source_text)
    ranked = sorted(
        {sentence for sentence in candidates if sentence},
        key=lambda sentence: score_fact_sentence(sentence, product),
        reverse=True,
    )
    for sentence in ranked:
        candidate = rough_translate_text(sentence)
        candidate = re.sub(r"\s+", " ", candidate).strip(" .")
        if len(candidate) < 55:
            continue
        if fact_is_generic(candidate):
            continue
        if title_line:
            candidate = re.sub(rf"^{re.escape(title_line)}[\s:.-]*", "", candidate, flags=re.IGNORECASE).strip()
        if candidate:
            return textwrap.shorten(candidate, width=190, placeholder="...")

    return fallback_fact


def build_specific_title(item: dict, fact: str) -> str:
    source_text = strip_noise_lines(item.get("text", ""))
    title_line = source_text.splitlines()[0].strip() if source_text.splitlines() else ""
    haystack = f"{title_line} {fact} {source_text}"
    topic = detect_topic(haystack)
    product = detect_product_name(haystack)

    if topic == "prompt_library" and product:
        return f"Для {product} собрали большую библиотеку промптов"
    if topic == "video" and product:
        return f"У {product} появилось важное обновление для AI-видео"
    if topic == "image" and product:
        return f"{product} получил заметное обновление для картинок"
    if topic == "avatar_voice" and product:
        return f"У {product} появился новый инструмент для аватаров и озвучки"
    if topic == "assistant" and product:
        return f"{product} получил заметное обновление"
    if title_line and not is_mostly_english(title_line) and len(title_line) > 16:
        return textwrap.shorten(title_line, width=90, placeholder="...")
    if product:
        return f"У {product} вышло новое AI-обновление"
    return build_russian_title(item, fact)


def build_editor_fact(item: dict, article_text: str, fallback_fact: str) -> str:
    source_text = strip_noise_lines(item.get("text", ""))
    title_line = source_text.splitlines()[0].strip() if source_text.splitlines() else ""
    haystack = f"{title_line}\n{source_text}\n{article_text}"
    topic = detect_topic(haystack)
    product = detect_product_name(haystack)

    if topic == "prompt_library" and product:
        return f"на GitHub уже собрали большую библиотеку промптов и референсов для {product}, чтобы не тестировать всё с нуля"

    if topic == "video" and product:
        if any(word in haystack.lower() for word in ["real-time", "realtime", "live"]):
            return f"у {product} показали обновление для AI-видео с акцентом на более быстрый и живой результат"
        return f"у {product} появилось обновление для AI-видео, которое пытаются быстро примерить к реальной работе"

    if topic == "image" and product:
        return f"{product} получил обновление для картинок, которое может упростить редактирование и ускорить визуальный продакшн"

    if topic == "avatar_voice" and product:
        return f"у {product} появился инструмент, который упрощает аватары, озвучку и сборку коротких роликов"

    if topic == "assistant" and product:
        if "github" in haystack.lower():
            return f"вокруг {product} снова разошлась практическая находка с GitHub, которую сразу начали примерять к реальным сценариям"
        return f"{product} получил обновление, которое быстро начинают примерять к обычной работе и созданию контента"

    return fallback_fact


def build_viewer_value_from_topic(item: dict, fact: str) -> str:
    haystack = f"{item.get('text', '')} {fact}"
    topic = detect_topic(haystack)
    if topic == "prompt_library":
        return "это экономит часы тестов и помогает быстрее находить рабочие структуры промптов"
    if topic == "video":
        return "такие релизы быстро меняют качество, скорость и цену AI-видео для реальной работы"
    if topic == "image":
        return "такие обновления быстро доходят до рекламы, дизайна и генерации картинок под коммерческие задачи"
    if topic == "avatar_voice":
        return "это напрямую влияет на аватары, озвучку и производство коротких вертикальных роликов"
    if topic == "assistant":
        return "такие функции быстро доходят до реальных рабочих сценариев и ежедневного использования"
    return "это быстро начинает влиять на рабочие сценарии и создание контента"


def build_video_copy_variants(title: str, fact: str, listener_value: str) -> list[dict]:
    variants = [
        {
            "video_title": title,
            "script": (
                f"{fact[0].upper() + fact[1:] if fact else title}. "
                f"Для зрителя и создателей контента это важно, потому что {listener_value}. "
                f"Если коротко, это не просто ещё одна AI-новость, а штука, которую реально можно примерить к работе уже сейчас."
            ),
            "angle": "прикладная польза",
        },
        {
            "video_title": f"{title}: что в этом реально нового",
            "script": (
                f"Вот новость, которую стоит разбирать не ради хайпа, а ради практики. "
                f"{fact[0].upper() + fact[1:] if fact else title}. "
                f"Самое интересное тут в том, что {listener_value}, а значит это быстро дойдёт до обычных creator-сценариев."
            ),
            "angle": "редакторский разбор",
        },
        {
            "video_title": f"{title}: почему это быстро разлетится",
            "script": (
                f"Такие AI-новости обычно быстро расходятся, когда у выгоды есть понятный человеческий смысл. "
                f"{fact[0].upper() + fact[1:] if fact else title}. "
                f"Здесь цепляет то, что {listener_value}, без долгих объяснений и техношума."
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

    article_text = fetch_article_text(item.get("link", ""))
    title_ru, body_ru = adapt_source_to_russian(item)
    fact = compress_fact(body_ru, title_ru)
    fact = pick_article_fact(article_text, fact)
    fact = synthesize_fact_from_article(item, article_text, fact)
    fact = infer_russian_fact(item, fact)
    fact = pick_concrete_fact(item, article_text, fact)
    fact = build_editor_fact(item, article_text, fact)
    title = build_specific_title(item, fact)
    listener_value = build_viewer_value_from_topic(item, fact)
    base_script = payload.get("script_ru")
    notes = payload.get("notes_ru", "")
    using_local_fallback = "локальный fallback" in notes.lower()

    stats = best_hook_notes()
    variants = build_video_copy_variants(title, fact, listener_value)

    if base_script and not using_local_fallback and looks_like_publishable_russian_script(base_script):
        variants[0]["script"] = textwrap.shorten(
            sanitize_generated_script(base_script), width=SCRIPT_MAX_CHARS, placeholder="..."
        )

    for variant in variants:
        if stats["top_title"] and stats["best_views"] and ("релиза" in stats["hook_style"] or "релиз" in stats["hook_style"]):
            variant["video_title"] = variant["video_title"].replace("что в этом реально нового", "что здесь реально нового")
        variant["hashtags"] = build_hashtags(item)
    return variants


def send_pool_top_news(chat_id: int, items: dict, limit: int = 3) -> int:
    pool = load_pool()
    candidates = pool.get("candidates", [])[:limit]
    if not candidates:
        safe_telegram_post(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": "Сильных новостей в пуле пока нет. Попробуй ещё раз чуть позже.",
                "disable_web_page_preview": "true",
                "reply_markup": build_reply_keyboard(),
            },
        )
        return 0

    safe_telegram_post(
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": f"Собрал пул новостей и отобрал 3 лучшие темы из {len(pool.get('candidates', []))}.",
            "disable_web_page_preview": "true",
            "reply_markup": build_reply_keyboard(),
        },
    )

    item_id = next_item_id(items)
    sent = 0
    for entry in candidates:
        current_id = item_id
        item_id += 1
        text = f"{entry['title']}\n\n{entry.get('summary', '')}\n\nИсточник: {entry['link']}"
        items[str(current_id)] = {
            "update_id": current_id,
            "timestamp": entry.get("published_at", datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")),
            "from": "news_scout",
            "username": "railway_worker",
            "text": text,
            "link": entry["link"],
            "forwarded_from": entry.get("source", ""),
            "status": "inbox",
            "source": entry.get("source", ""),
            "score": entry.get("score", 0),
            "pool_id": entry.get("pool_id", ""),
        }
        safe_telegram_post(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": build_scout_card(entry),
                "disable_web_page_preview": "false",
                "reply_markup": build_keyboard(current_id),
            },
        )
        sent += 1
    return sent


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
        rebuilt = item_from_scout_card(message.get("text", ""), update_id)
        if rebuilt:
            items[str(update_id)] = rebuilt
            item = rebuilt

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

    print(
        json.dumps(
            {
                "callback_action": action,
                "update_id": update_id,
                "variant_idx": variant_idx,
                "item_found": True,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

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


def handle_text_command(text: str, expected_chat_id: int, items: dict) -> bool:
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
        if result.returncode != 0:
            safe_telegram_post(
                "sendMessage",
                {
                    "chat_id": expected_chat_id,
                    "text": "Не смог обновить пул новостей.",
                    "disable_web_page_preview": "true",
                    "reply_markup": build_reply_keyboard(),
                },
            )
            return True
        send_pool_top_news(expected_chat_id, items, limit=3)
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

        if handle_text_command(text, expected_chat_id, items):
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
