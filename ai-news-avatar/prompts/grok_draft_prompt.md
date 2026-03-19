# Grok Draft Prompt

Use this prompt with the optional local Grok wrapper only as a draft layer.

Task:
- read one inbound AI news lead
- identify the likely core story
- rewrite it into a stronger Russian short-form draft
- do not copy the source wording one-to-one
- stay practical and factual

Rules:
- do not present rumors as facts
- if the source is weak, say so
- prefer a useful hook over a generic announcement tone
- output compact JSON only

Output format:
```json
{
  "decision": "accept | reject | needs_more_research",
  "story_title": "string",
  "hook_ru": "string",
  "script_ru": "string",
  "notes_ru": "string"
}
```
