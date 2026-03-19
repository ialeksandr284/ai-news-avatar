# News Processing Rules

## Goal
Telegram news leads are only inputs, not final source material.

## Required Pipeline
1. Receive inbound post
2. Extract link if present
3. Search for the original source or official release
4. Confirm the main claim
5. Build a factual brief
6. Rewrite into a stronger hook and script

## Never Do This
- do not turn the forwarded text into a script one-to-one
- do not copy the source wording into the hook
- do not use a Telegram post as the only evidence when a stronger source exists

## Desired Output Quality
- stronger than the source post
- cleaner than the source post
- more factual than the source post
- more useful than the source post

## Decision Outcomes
- `accept` if the story is real and strong
- `needs_more_research` if signal exists but confirmation is weak
- `reject` if the story is hype, thin, duplicate, or unusable for Shorts
