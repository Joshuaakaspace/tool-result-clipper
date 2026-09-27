"""Minimal end-to-end usage."""
from __future__ import annotations

import json

from tool_result_clipper import clip


LOG_SAMPLE = "\n".join(
    [f"2026-01-01T00:00:{i:02d}Z INFO handled request id={i}" for i in range(50)]
    + ["2026-01-01T00:01:00Z ERROR upstream timeout at gateway id=99"]
)

JSON_SAMPLE = json.dumps(
    {
        "status": "ok",
        "request_id": "REQ-42",
        "results": [{"id": i, "score": i * 0.01} for i in range(500)],
        "summary": {"matched": 3, "note": "top hits: 12, 44, 191"},
    }
)


def show(label: str, text: str, budget: int):
    clipped, report = clip(text, budget=budget)
    print(f"--- {label} ---")
    print(f"kind={report.kind} in={report.input_tokens} out={report.output_tokens} budget={report.budget}")
    print(clipped[:600] + ("\n..." if len(clipped) > 600 else ""))
    print()


if __name__ == "__main__":
    show("logs (budget 80)", LOG_SAMPLE, 80)
    show("json (budget 120)", JSON_SAMPLE, 120)
