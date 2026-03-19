# Metadata Prompt

Based on the approved Russian script, generate:
- short YouTube title in Russian
- short description in Russian
- 3-5 hashtags
- one thumbnail concept

Rules:
- title must be short and specific
- description must mention the key update
- no clickbait beyond the actual news
- keep the tone clear and modern

Output format:
```json
{
  "title_ru": "string",
  "description_ru": "string",
  "hashtags": ["string"],
  "thumbnail_concept": "string"
}
```
