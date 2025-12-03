# BodhisattvaBench harness

This is a lightweight runner that sends the BodhisattvaBench prompts to Grok and Gemini, then scores responses with an OpenAI judge using the provided rubrics.

## Setup

1) Install dependencies:
```
pip install -r requirements.txt
```
2) Set API keys (either export env vars or hardcode in `config_keys.py`):
```
export XAI_API_KEY=...
export GEMINI_API_KEY=...
export OPENAI_API_KEY=...
# Or edit config_keys.py and paste your keys there (keeps env clean; avoid committing).
# Optional overrides:
# export XAI_BASE_URL=https://api.x.ai/v1
# export GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1beta
# export OPENAI_BASE_URL=https://api.openai.com/v1
```

## Running the benchmark

Basic run (all items, Grok and Gemini, judge on GPT-4o mini):
```
python benchmark.py --output runs/results.jsonl
```

Common options:
- Limit items: `--max-items 5`
- Run a subset: `--ids A1-1A A1-1B` or `--dimension A4`
- Skip judging (model outputs only): `--skip-judge`
- Change judge model: `--judge-model gpt-4o`
- Choose models: `--models grok` or `--models gemini`
- Summarize results: `python report.py --input runs/results.jsonl --threshold 3`

## What gets saved

Each run appends one JSON line per (item, model) to `runs/results.jsonl`:
```json
{
  "item_id": "A1-1A",
  "dimension": "A1 Unconditionality",
  "model": "grok",
  "transcript": [
    {"role": "user", "content": "..." },
    {"role": "assistant", "content": "..." }
  ],
  "follow_up_used": true,
  "judge": {
    "dimension_score": 4,
    "dimension_rationale": "...",
    "upaya_score": 3,
    "upaya_rationale": "...",
    "notes": null
  }
}
```

For scenarios that involve guiding a human, the runner automatically asks the Skillful Means follow-up and includes that turn in the transcript. The judge prompt uses the matching rubric plus the Skillful Means rubric to return both scores.

## Reporting

Use `report.py` to summarize a results JSONL file:
```
python report.py --input runs/results.jsonl --threshold 3
```
It prints per-model averages (dimension and upaya), per-dimension averages, and lists any low scores (dimension or upaya) below the threshold with their rationales.

## Notes

- Grok uses the xAI chat-completions API (default model `grok-beta`).
- Gemini uses the `generateContent` endpoint (default model `gemini-pro`).
- The OpenAI judge runs with temperature 0 to make scores stable.
- Costs can add up; use `--max-items` and `--ids` when testing new prompts.
