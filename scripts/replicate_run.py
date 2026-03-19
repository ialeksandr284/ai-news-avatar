#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import sys
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


def parse_args(argv: list[str]) -> tuple[str | None, dict[str, str | bool]]:
    if not argv:
        return None, {}

    task = argv[0]
    parsed: dict[str, str | bool] = {}
    i = 1
    while i < len(argv):
        current = argv[i]
        if not current.startswith("--"):
            i += 1
            continue
        key = current[2:]
        next_value = argv[i + 1] if i + 1 < len(argv) else None
        if not next_value or next_value.startswith("--"):
            parsed[key] = True
            i += 1
        else:
            parsed[key] = next_value
            i += 2
    return task, parsed


def compact(data: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in data.items() if value not in (None, "", False)}


def print_help() -> None:
    print(
        """Usage:
  python3 scripts/replicate_run.py generate --prompt "Luxury perfume on black glass"
  python3 scripts/replicate_run.py alt --prompt "..."
  python3 scripts/replicate_run.py text-heavy --prompt "..."
  python3 scripts/replicate_run.py edit --prompt "Make it colder and more editorial" --image "https://..."
  python3 scripts/replicate_run.py upscale --image "https://..."
  python3 scripts/replicate_run.py repair-face --image "https://..."
  python3 scripts/replicate_run.py video --prompt "Luxury perfume UGC video" --first-frame-image "https://..."

Options:
  --model   Override the model name
  --prompt  Prompt for generation or edit tasks
  --image   Source image URL for edit/upscale/repair tasks
  --first-frame-image  Reference image URL for video first frame
  --subject-reference  Subject reference image URL for video generation
  --prompt-optimizer   true/false for minimax video prompt optimizer
  --aspect  Aspect ratio, for example 1:1 or 4:5
  --format  Output format, default png
"""
    )


def build_task(task: str, args: dict[str, str | bool]) -> tuple[str, dict[str, object]]:
    model_overrides = {
        "generate": os.environ.get("REPLICATE_DEFAULT_IMAGE_MODEL"),
        "alt": os.environ.get("REPLICATE_ALT_IMAGE_MODEL"),
        "text-heavy": os.environ.get("REPLICATE_TEXT_HEAVY_IMAGE_MODEL"),
        "edit": os.environ.get("REPLICATE_EDIT_MODEL"),
        "upscale": os.environ.get("REPLICATE_UPSCALE_MODEL"),
        "repair-face": os.environ.get("REPLICATE_FACE_REPAIR_MODEL"),
        "video": os.environ.get("REPLICATE_VIDEO_MODEL", "minimax/video-01"),
    }

    model = str(args.get("model") or model_overrides.get(task) or "")
    prompt = args.get("prompt")
    image = args.get("image")
    first_frame_image = args.get("first-frame-image")
    subject_reference = args.get("subject-reference")
    output_format = str(args.get("format") or "png")
    aspect_ratio = args.get("aspect")
    prompt_optimizer_raw = str(args.get("prompt-optimizer") or "true").lower()
    prompt_optimizer = prompt_optimizer_raw in {"1", "true", "yes", "on"}

    tasks = {
        "generate": (
            model,
            compact(
                {
                    "prompt": prompt,
                    "aspect_ratio": aspect_ratio,
                    "output_format": output_format,
                }
            ),
        ),
        "alt": (
            model,
            compact(
                {
                    "prompt": prompt,
                    "aspect_ratio": aspect_ratio,
                    "output_format": output_format,
                }
            ),
        ),
        "text-heavy": (
            model,
            compact(
                {
                    "prompt": prompt,
                    "aspect_ratio": aspect_ratio,
                    "output_format": output_format,
                }
            ),
        ),
        "edit": (
            model,
            compact(
                {
                    "prompt": prompt,
                    "image": image,
                    "output_format": output_format,
                }
            ),
        ),
        "upscale": (
            model,
            compact(
                {
                    "image": image,
                }
            ),
        ),
        "repair-face": (
            model,
            compact(
                {
                    "image": image,
                }
            ),
        ),
        "video": (
            model,
            compact(
                {
                    "prompt": prompt,
                    "prompt_optimizer": prompt_optimizer,
                    "first_frame_image": first_frame_image,
                    "subject_reference": subject_reference,
                }
            ),
        ),
    }

    if task not in tasks:
        raise ValueError(f"Unknown task: {task}")

    return tasks[task]


def main() -> int:
    load_env(ENV_PATH)

    token = os.environ.get("REPLICATE_API_TOKEN")
    if not token:
        print("Missing REPLICATE_API_TOKEN in environment.", file=sys.stderr)
        return 1

    task, args = parse_args(sys.argv[1:])
    if not task or task == "--help":
        print_help()
        return 0

    try:
        model, payload_input = build_task(task, args)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        print_help()
        return 1

    if task in {"generate", "alt", "text-heavy", "edit", "video"} and "prompt" not in payload_input:
        print("Missing required --prompt argument.", file=sys.stderr)
        return 1

    if task in {"edit", "upscale", "repair-face"} and "image" not in payload_input:
        print("Missing required --image argument.", file=sys.stderr)
        return 1

    if not model:
        print("Missing model configuration for this task.", file=sys.stderr)
        return 1

    payload = json.dumps({"input": payload_input}).encode("utf-8")
    api_url = f"https://api.replicate.com/v1/models/{model}/predictions"

    req = request.Request(
        api_url,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Prefer": "wait",
        },
        method="POST",
    )

    try:
        with request.urlopen(req) as response:
            print(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"Replicate API error: {exc.code}\n{body}", file=sys.stderr)
        return 1
    except error.URLError as exc:
        print(f"Network error: {exc.reason}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
