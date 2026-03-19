# AI News Avatar

Russian-speaking talking-avatar pipeline for 30-second AI news shorts.

## Goal
Automatically collect fresh AI engine/model news, draft a short Russian script, generate a talking-avatar video, send it for review, and publish it to YouTube Shorts after approval.

## MVP Flow
1. Fetch AI news from selected web sources.
2. Filter for relevant items about models, engines, APIs, and launches.
3. Summarize the top story in Russian.
4. Generate a 30-second short-form script.
5. Generate title, description, and thumbnail brief.
6. Produce voiceover and talking-avatar video.
7. Send preview to review channel.
8. Publish to YouTube Shorts after approval.

## Initial Review Mode
For now, review can happen manually in this workspace instead of Telegram.
Later, replace the manual review step with Telegram delivery and approval buttons.

## Suggested Stack
- News fetch: RSS, official blogs, API feeds, selected web sources
- LLM reasoning/scripting: OpenAI, Gemini, or another approved text model
- Optional cheap draft layer: local Grok wrapper API
- TTS: ElevenLabs, OpenAI TTS, or a local TTS provider
- Avatar video: HeyGen, Tavus, Omnihuman, Kling, or another avatar/video provider
- Workflow orchestration: n8n or custom Python jobs
- Publish: YouTube Data API

## Project Files
- `ARCHITECTURE.md` - system design and data flow
- `SYSTEM.md` - permanent operating system for the channel
- `DAILY_WORKFLOW.md` - daily operating runbook
- `MVP_WORKFLOW.md` - practical step-by-step pipeline
- `config/source_list.md` - initial source strategy
- `config/review_contract.md` - how review works before publish
- `config/creative_rules.md` - creative and anti-slop rules
- `config/metrics_rules.md` - how metrics are interpreted
- `prompts/script_prompt.md` - prompt for 30-second Russian script generation
- `prompts/rewrite_prompt.md` - prompt for title/description/metadata generation
- `logs/content_log.md` - release journal
- `logs/experiments_log.md` - experiment journal
- `logs/prompt_changes.md` - prompt evolution log
- `templates/daily_review_template.md` - daily review output template

## Output Contract
Each run should produce:
- one selected news item
- one Russian 30-second script
- one short title
- one YouTube description draft
- one avatar video draft
- one review package with source links

## Constraints
- Russian language output
- 30 seconds target runtime
- Focus only on AI product/model/engine news
- Prefer primary sources where possible
- Avoid hype without factual grounding

## Operating Principle
Do not rely on chat history as the source of truth.
This project keeps permanent memory in markdown files so new sessions can pick up the channel strategy, prompt rules, experiments, and performance history without losing context.
