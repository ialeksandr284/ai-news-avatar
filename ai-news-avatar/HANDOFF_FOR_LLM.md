# Handoff For Another LLM

## What This Project Is
This is a semi-automated Russian YouTube Shorts pipeline for AI news.

The system currently:
- accepts news leads from Telegram
- stores them in a project inbox
- lets the operator review or draft content
- generates talking-avatar videos
- publishes to YouTube Shorts through Buffer
- pulls YouTube metrics
- sends daily reports to Telegram

The current project path is:
- `/Users/aleksandrivanov/Documents/New project/ai-news-avatar`

## Core Objective
Turn recent AI product/model/tool news into:
- short Russian scripts
- talking-avatar videos
- published YouTube Shorts
- feedback loops based on YouTube metrics

## Current Working Stack
- Telegram Bot API
  - inbox for news
  - daily reports
  - basic action buttons
- D-ID
  - talking-avatar video generation from one face image + text
  - current limitation: watermark on trial
- Buffer GraphQL API
  - publishes Shorts to YouTube
- YouTube Data API + YouTube Analytics API
  - reads video stats and analytics
- Local markdown files
  - permanent memory for prompts, rules, logs, and workflow

## Important Architectural Principle
Chat history is not the source of truth.
Project files are the source of truth.

This project stores:
- system rules
- creative rules
- metrics interpretation rules
- content logs
- experiment logs
- prompt changes
- scripts and automation helpers

## What Already Works
1. D-ID video generation
2. Buffer publish to YouTube Shorts
3. YouTube metrics reading
4. Telegram daily reporting
5. Telegram inbox for forwarded news

## What Is Still Semi-Manual
The research and rewriting layer.

Right now, the highest-quality workflow is:
1. User forwards a Telegram news post
2. Inbox captures it
3. The assistant manually researches the story
4. The assistant rewrites it into:
   - factual brief
   - stronger hook
   - cleaner Russian short script
5. Then the video is rendered and published

This is intentional because the user currently wants to avoid paying for another live LLM API layer.

## Current Weaknesses
- Trial watermark on D-ID
- Telegram buttons are not true realtime; they require the inbox processor to run
- The automatic `Scenario` reply is still too simple and should eventually become:
  - inbound post
  - source lookup
  - factual verification
  - rewrite
  - stronger short script
- Visual quality gate is not fully implemented yet

## Key Files To Read First

### System and Workflow
- `README.md`
- `ARCHITECTURE.md`
- `SYSTEM.md`
- `DAILY_WORKFLOW.md`

### Rules
- `config/creative_rules.md`
- `config/metrics_rules.md`
- `config/news_processing_rules.md`
- `config/source_list.md`
- `config/avatar_identity.md`
- `config/video_presentation_rules.md`
- `config/episode_contract.md`

### Prompts
- `prompts/script_prompt.md`
- `prompts/rewrite_prompt.md`
- `prompts/research_rewrite_prompt.md`
- `prompts/avatar_video_prompt.md`

### Logs
- `logs/content_log.md`
- `logs/experiments_log.md`
- `logs/prompt_changes.md`

### Inbox
- `inbox/news_inbox.md`

### Scripts
- `scripts/did_create_talk.py`
- `scripts/did_get_talk.py`
- `scripts/buffer_publish.py`
- `scripts/youtube_stats.py`
- `scripts/telegram_daily_report.py`
- `scripts/telegram_news_inbox.py`

## Telegram UX
The Telegram bot currently serves three roles:

1. News inbox
- user forwards posts or sends links

2. Daily report
- daily YouTube summary can be sent to Telegram

3. Light control panel
- current button set:
  - `Оценить`
  - `Сценарий`
  - `В рендер`
  - `Стоп`
- there is also a persistent `Статистика` keyboard button

Important:
- button handling is not fully live unless the Telegram inbox processor runs regularly

## Publishing Logic
Publishing uses Buffer GraphQL, not the old Buffer REST API.

Working flow:
1. Render video through D-ID
2. Use `buffer_publish.py`
3. Publish to the YouTube channel through Buffer
4. Telegram can receive the resulting YouTube URL

## Metrics Logic
Metrics are pulled from YouTube APIs.

Primary interpretation direction:
- strong views + weak retention => packaging worked, body weak
- low views + decent retention => topic or title packaging weak
- strong performance on certain topic shapes => scale carefully

Current early observation:
- stronger practical or signal-heavy hooks seem to outperform drier infra framing

## How The User Wants This To Evolve
Near-term:
- keep costs low
- use the assistant as the main research + rewrite layer
- keep Telegram as inbox and reporting surface

Later:
- remove watermark by switching to a paid or better renderer
- improve visual realism
- add stronger automatic research and rewriting
- make Telegram flow more autonomous

## What Another LLM Should Respect
- do not treat forwarded Telegram text as final source material
- do not optimize for quantity over quality
- do not make repetitive AI-slop Shorts
- keep the first sentence strong and useful
- prefer primary sources
- keep the project memory in files, not only in chat

## Best Next Improvements
1. Add a proper research-and-rewrite backend for Telegram news leads
2. Add a visual quality gate before publish
3. Improve topic bucketing and metrics-based iteration
4. Separate project Shorts metrics from unrelated channel videos in Telegram reports
5. Make Telegram button actions autonomous with a lightweight worker
