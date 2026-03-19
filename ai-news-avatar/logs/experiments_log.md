# Experiments Log

Track only meaningful experiments and outcomes.

## Template
```md
### YYYY-MM-DD
- Hypothesis:
- Change made:
- Videos affected:
- Result:
- Keep / revert / retest:
```

## Entries

### 2026-03-18
- Hypothesis: a fully automated chain from news to published YouTube Short is feasible with current tooling
- Change made: used D-ID for avatar rendering and Buffer GraphQL for publishing
- Videos affected: `ryquS6e3rDA`, `ANw-PYcHnzw`
- Result: pipeline worked end-to-end
- Keep / revert / retest: keep

### 2026-03-18
- Hypothesis: launch-style story framing performs better than abstract infrastructure framing
- Change made: compared `Nano Banana 2` vs `Gemini Embedding 2`
- Videos affected: `ryquS6e3rDA`, `ANw-PYcHnzw`
- Result: early view count favored Nano Banana 2
- Keep / revert / retest: retest with more samples
