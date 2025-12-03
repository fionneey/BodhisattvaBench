from __future__ import annotations

import json

from bench_data import BENCHMARK_ITEMS
from benchmark import GeminiClient, GrokClient, run_item, SKILLFUL_MEANS_FOLLOW_UP


def main() -> None:
    # First benchmark item (A1-1A: unconditionality, friend case)
    item = next(i for i in BENCHMARK_ITEMS if i.id == "A1-1A")

    clients = {
        "grok": GrokClient(),
        "gemini": GeminiClient(),
    }

    for name, client in clients.items():
        print(f"\n=== Running {item.id} with {name} ===")
        try:
            result = run_item(client, item, SKILLFUL_MEANS_FOLLOW_UP, model_label=name)
        except Exception as exc:  # noqa: BLE001
            print(f"{name} error: {exc}")
            continue

        # Pretty print the transcript including the skillful-means follow-up
        print(json.dumps(result.transcript, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
