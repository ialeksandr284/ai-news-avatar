# System

## Purpose
This project is the permanent operating system for the `Smol` AI news Shorts channel.
The chat is only the execution surface.
The files in this project are the memory, rules, and decision log.

## Core Goal
Publish Russian AI news Shorts that:
- look credible and premium
- explain one real update clearly
- grow organically
- improve over time based on metrics

## Channel Identity
- Format: vertical YouTube Shorts
- Language: Russian
- Topic: AI model launches, engines, developer tools, inference, multimodal systems, APIs, major product updates
- Tone: concise, sharp, factual, modern
- Audience: people who track AI products and want quick signal, not hype sludge

## Non-Negotiable Standards
- Prefer primary sources
- One story per short
- The first line must explain why the update matters
- No vague hype words without factual support
- Do not write scripts by simply paraphrasing a forwarded Telegram post
- No recycled filler intros
- No repetitive template spam across consecutive uploads
- Do not publish if the video looks broken, cheap, or obviously synthetic in a bad way

## Anti-Slop Rules
- Never publish nearly identical scripts back-to-back
- Do not reuse the same opening phrase more than twice in a short time window
- Do not keep the same title pattern for every video
- Do not mass-produce weak shorts just to fill volume
- If a story is not explainable in 20-30 seconds, skip it

## Content Decision Rules
- Choose stories with clear user-facing impact
- Prefer launches and updates with obvious practical implications
- Prefer stories that can be summarized as:
  - what launched
  - what changed
  - why it matters
- Avoid stories that need too much context or legal caveats for a short

## Production Loop
1. Select a strong story
2. Gather the source link and original post
3. Verify the story with primary sources or reliable corroboration
4. Build a short factual brief
5. Write a compact spoken script with a stronger hook than the source post
6. Check title, hook, and pacing
7. Render the avatar video
8. Review before publish
9. Publish
10. Pull metrics
11. Log findings
12. Adjust prompts and rules in small controlled steps

## Research Requirement
Every inbound Telegram news item should go through a research pass before it becomes a script.

Minimum standard:
- identify the original source link if available
- search for the primary announcement or official release
- confirm the main fact with at least one strong source
- extract the user-facing implication
- only then write the hook and spoken script

If there is not enough evidence, the news item should stay in `inbox` or be rejected.

## Memory Policy
Always update these files after meaningful work:
- `logs/content_log.md`
- `logs/experiments_log.md`
- `logs/prompt_changes.md`

If strategy changes, update:
- `SYSTEM.md`
- `config/creative_rules.md`
- `config/metrics_rules.md`

## Daily Improvement Policy
The system should not reinvent itself every day.
It should improve through small logged changes.

Allowed daily changes:
- one stronger hook style
- one title formula adjustment
- one pacing adjustment
- one visual quality rule change

Avoid changing everything at once.

## Publish Safety Policy
Do not optimize only for output volume.
The healthy operating range is:
- 1-3 videos per day at most during early testing
- publish only after script and visual quality checks
- review metrics at 2h, 24h, 72h, and 7d when possible
