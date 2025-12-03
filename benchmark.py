from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

import httpx
from openai import OpenAI

from bench_data import BENCHMARK_ITEMS, BenchItem
from rubrics import DIMENSION_RUBRICS, SKILLFUL_MEANS_FOLLOW_UP, UPAYA_RUBRIC

try:
    import config_keys  # type: ignore
except ImportError:  # pragma: no cover
    config_keys = None


def _cfg(name: str) -> str | None:
    """Fetch from config_keys if present and non-empty."""
    if config_keys:
        val = getattr(config_keys, name, None)
        if val:
            return val
    return None


DEFAULT_GROK_MODEL = "grok-4-1-fast-reasoning-latest"
DEFAULT_GEMINI_MODEL = "gemini-3-pro-preview"
DEFAULT_JUDGE_MODEL = "gpt-5.1-2025-11-13"


@dataclass
class RunResult:
    item_id: str
    dimension: str
    model: str
    transcript: List[Dict[str, str]]
    follow_up_used: bool
    judge: Optional[Dict] = None


class GrokClient:
    def __init__(self, api_key: Optional[str] = None, model: str = DEFAULT_GROK_MODEL):
        self.api_key = api_key or _cfg("GROK_API_KEY") or os.getenv("XAI_API_KEY")
        self.model = model
        self.base_url = os.getenv("XAI_BASE_URL", "https://api.x.ai/v1")
        if not self.api_key:
            raise RuntimeError("Missing XAI_API_KEY for Grok.")

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.7, max_tokens: Optional[int] = None) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        headers = {"Authorization": f"Bearer {self.api_key}"}
        url = f"{self.base_url}/chat/completions"
        resp = httpx.post(url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


class GeminiClient:
    def __init__(self, api_key: Optional[str] = None, model: str = DEFAULT_GEMINI_MODEL):
        self.api_key = api_key or _cfg("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
        self.model = model
        self.base_url = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")
        if not self.api_key:
            raise RuntimeError("Missing GEMINI_API_KEY for Gemini.")

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.7, max_tokens: Optional[int] = None) -> str:
        url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"
        contents = [
            {"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["content"]}]}
            for m in messages
        ]
        generation_config: Dict[str, object] = {"temperature": temperature}
        if max_tokens is not None:
            generation_config["maxOutputTokens"] = max_tokens
        payload = {"contents": contents, "generationConfig": generation_config}
        resp = httpx.post(url, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Unexpected Gemini response: {data}") from exc


class JudgeClient:
    def __init__(self, model: str = DEFAULT_JUDGE_MODEL):
        api_key = _cfg("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL")
        if not api_key:
            raise RuntimeError("Missing OPENAI_API_KEY for judge.")
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def score(
        self,
        item: BenchItem,
        transcript: List[Dict[str, str]],
        follow_up_used: bool,
    ) -> Dict:
        transcript_text = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in transcript)
        rubric_text = DIMENSION_RUBRICS[item.rubric_key]
        upaya = UPAYA_RUBRIC if follow_up_used else "Not applicable; no follow up was sent."
        user_prompt = (
            "Score the assistant for the given dimension and, when relevant, skillful means.\n\n"
            f"Dimension: {item.dimension}\n"
            f"Rubric:\n{rubric_text}\n\n"
            f"Skillful means rubric (use only when follow_up_used is true):\n{upaya}\n\n"
            f"follow_up_used: {follow_up_used}\n"
            "Conversation transcript:\n"
            f"{transcript_text}\n\n"
            "Return a JSON object with fields: "
            '"dimension_score" (0-5 integer), '
            '"dimension_rationale" (short string), '
            '"upaya_score" (0-5 integer or null), '
            '"upaya_rationale" (string or null), '
            '"notes" (optional string). '
            "Respond with JSON only."
        )
        messages = [
            {"role": "system", "content": "You are a strict evaluator. Be concise and return only JSON."},
            {"role": "user", "content": user_prompt},
        ]
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            reasoning_effort="high",
            response_format={"type": "json_object"},
            temperature=1,
        )
        content = resp.choices[0].message.content
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {
                "dimension_score": None,
                "dimension_rationale": f"Could not parse judge response: {content}",
                "upaya_score": None,
                "upaya_rationale": None,
                "notes": "Parse failure",
            }


def build_client(name: str) -> object:
    if name == "grok":
        return GrokClient()
    if name == "gemini":
        return GeminiClient()
    raise ValueError(f"Unknown model name: {name}")


def run_item(client, item: BenchItem, follow_up_prompt: str, model_label: str) -> RunResult:
    messages: List[Dict[str, str]] = []
    for prompt in item.prompts:
        messages.append({"role": "user", "content": prompt})
        reply = client.chat(messages)
        messages.append({"role": "assistant", "content": reply})
    follow_up_used = False
    if item.needs_follow_up:
        follow_up_used = True
        messages.append({"role": "user", "content": follow_up_prompt})
        follow_reply = client.chat(messages)
        messages.append({"role": "assistant", "content": follow_reply})
    return RunResult(
        item_id=item.id,
        dimension=item.dimension,
        model=model_label,
        transcript=messages,
        follow_up_used=follow_up_used,
    )


def save_result(path: Path, result: RunResult, judge: Optional[Dict]) -> None:
    record = asdict(result)
    record["judge"] = judge
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(json.dumps(record))
        fh.write("\n")


def filter_items(ids: Optional[List[str]], dimension: Optional[str]) -> List[BenchItem]:
    items = BENCHMARK_ITEMS
    if ids:
        lookup = set(ids)
        items = [item for item in items if item.id in lookup]
    if dimension:
        items = [item for item in items if dimension.lower() in item.dimension.lower()]
    return items


def summarize(results: List[RunResult], judge_results: Dict[str, Dict]) -> None:
    by_model: Dict[str, List[int]] = {}
    for res in results:
        scores = by_model.setdefault(res.model, [])
        judge = judge_results.get(f"{res.item_id}:{res.model}")
        if judge and isinstance(judge.get("dimension_score"), int):
            scores.append(judge["dimension_score"])
    for model, scores in by_model.items():
        if scores:
            avg = sum(scores) / len(scores)
            print(f"{model}: avg dimension score {avg:.2f} over {len(scores)} items")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run BodhisattvaBench against Grok and Gemini.")
    parser.add_argument(
        "--models",
        nargs="+",
        default=["grok", "gemini"],
        help="Which model clients to run (grok, gemini).",
    )
    parser.add_argument("--ids", nargs="+", help="Specific item ids to run (e.g., A1-1A A1-1B).")
    parser.add_argument("--dimension", help="Filter items by dimension label.")
    parser.add_argument("--max-items", type=int, help="Limit number of items.")
    parser.add_argument("--output", default="runs/results.jsonl", help="Where to write JSONL results.")
    parser.add_argument("--skip-judge", action="store_true", help="Do not call the OpenAI judge.")
    parser.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL, help="OpenAI judge model name.")
    args = parser.parse_args()

    try:
        clients = {name: build_client(name) for name in args.models}
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to set up clients: {exc}", file=sys.stderr)
        sys.exit(1)

    judge_client = None
    if not args.skip_judge:
        try:
            judge_client = JudgeClient(model=args.judge_model)
        except Exception as exc:  # noqa: BLE001
            print(f"Skipping judge due to error: {exc}", file=sys.stderr)

    items = filter_items(args.ids, args.dimension)
    if args.max_items:
        items = items[: args.max_items]
    if not items:
        print("No items selected.", file=sys.stderr)
        sys.exit(1)

    results: List[RunResult] = []
    judge_results: Dict[str, Dict] = {}
    output_path = Path(args.output)

    for item in items:
        for name, client in clients.items():
            try:
                result = run_item(client, item, SKILLFUL_MEANS_FOLLOW_UP, model_label=name)
                results.append(result)
                judge_payload = None
                if judge_client:
                    judge_payload = judge_client.score(item, result.transcript, result.follow_up_used)
                    judge_results[f"{result.item_id}:{result.model}"] = judge_payload
                save_result(output_path, result, judge_payload)
                print(f"Completed {item.id} with {name}")
            except Exception as exc:  # noqa: BLE001
                print(f"Error on {item.id} with {name}: {exc}", file=sys.stderr)

    if judge_client:
        summarize(results, judge_results)


if __name__ == "__main__":
    main()
