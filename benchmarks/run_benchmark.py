"""Compare naive tail truncation vs. semantic clipping.

Generates synthetic but realistic tool results in four categories
(JSON, logs, list, mixed text), plants a set of "key facts" in each,
clips them to a fixed token budget with the two strategies, and
measures how many key facts survive.

Writes results to docs/before_after.png and prints a table.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from tool_result_clipper import clip, count_tokens  # noqa: E402
from tool_result_clipper.tokens import encode, decode  # noqa: E402


def naive_tail(text: str, budget: int) -> str:
    if count_tokens(text) <= budget:
        return text
    toks = encode(text)
    return decode(toks[-budget:])


# ---------- Sample generators ----------

def gen_json_sample(seed: int):
    rnd = random.Random(seed)
    items = []
    for i in range(200):
        items.append(
            {
                "id": f"item_{i:04d}",
                "name": rnd.choice(["alpha", "beta", "gamma", "delta", "epsilon"]) + f"_{i}",
                "value": rnd.randint(0, 1000),
                "meta": {"created_at": "2026-01-01T00:00:00Z", "tags": ["a", "b", "c"]},
            }
        )
    # Plant key facts: the response envelope keys and the summary block.
    payload = {
        "status": "ok",
        "request_id": "REQ-KEY-9F31D2",
        "summary": {
            "total": 200,
            "matched": 3,
            "critical_note": "MATCHED_ITEMS_INCLUDE_ALPHA_7_AND_DELTA_142",
        },
        "results": items,
        "trace_id": "TRACE-KEY-B7C2A4",
    }
    text = json.dumps(payload, indent=2)
    facts = ["REQ-KEY-9F31D2", "TRACE-KEY-B7C2A4", "MATCHED_ITEMS_INCLUDE_ALPHA_7_AND_DELTA_142", '"status": "ok"']
    return text, facts


def gen_logs_sample(seed: int):
    rnd = random.Random(seed)
    lines = []
    for i in range(400):
        ts = f"2026-01-01T00:{i//60:02d}:{i%60:02d}Z"
        if i == 37:
            lines.append(f"{ts} ERROR request handler failed reason=KEY_ERROR_TIMEOUT_UPSTREAM req=REQ-KEY-77 status=500")
        elif i == 210:
            lines.append(f"{ts} WARNING cache miss ratio elevated ratio=0.83 shard=KEY_SHARD_NORTH_3")
        elif i == 380:
            lines.append(f"{ts} CRITICAL out of memory KEY_OOM_WORKER_PID_4421")
        else:
            lines.append(f"{ts} INFO handled request path=/api/v1/thing status=200 latency_ms={rnd.randint(1,20)}")
    text = "\n".join(lines)
    facts = ["KEY_ERROR_TIMEOUT_UPSTREAM", "KEY_SHARD_NORTH_3", "KEY_OOM_WORKER_PID_4421", "REQ-KEY-77"]
    return text, facts


def gen_list_sample(seed: int):
    rnd = random.Random(seed)
    lines = []
    for i in range(300):
        lines.append(f"- file_{i:04d}.py    {rnd.randint(10, 5000)} bytes")
    # Plant facts at head, tail, and one buried in the middle.
    lines[0] = "- README.md    KEY_FACT_README_1024 bytes"
    lines[-1] = "- LICENSE    KEY_FACT_LICENSE_2048 bytes"
    lines[150] = "- CONFIG.yaml    KEY_FACT_CONFIG_512 bytes"
    text = "\n".join(lines)
    facts = ["KEY_FACT_README_1024", "KEY_FACT_LICENSE_2048"]
    # CONFIG is expected to be dropped by both; do not count it.
    return text, facts


def gen_text_sample(seed: int):
    rnd = random.Random(seed)
    body = []
    body.append("SUMMARY: KEY_HEADER_SUMMARY_TAG describes the scan output below.")
    for i in range(120):
        body.append(
            f"Paragraph {i}: " + " ".join(rnd.choice(["lorem", "ipsum", "dolor", "sit", "amet"]) for _ in range(30))
        )
    body.append("FINAL_NOTE: KEY_FOOTER_ANSWER_42 is the requested value.")
    text = "\n\n".join(body)
    facts = ["KEY_HEADER_SUMMARY_TAG", "KEY_FOOTER_ANSWER_42"]
    return text, facts


SAMPLES = {
    "json": gen_json_sample,
    "logs": gen_logs_sample,
    "list": gen_list_sample,
    "text": gen_text_sample,
}


def score(clipped: str, facts: list[str]) -> float:
    if not facts:
        return 1.0
    hits = sum(1 for f in facts if f in clipped)
    return hits / len(facts)


def run(budget: int = 400):
    rows = []
    for kind, gen in SAMPLES.items():
        text, facts = gen(seed=42)
        in_tok = count_tokens(text)

        naive_out = naive_tail(text, budget)
        naive_score = score(naive_out, facts) * 100

        smart_out, report = clip(text, budget=budget)
        smart_score = score(smart_out, facts) * 100

        rows.append(
            {
                "kind": kind,
                "input_tokens": in_tok,
                "budget": budget,
                "naive_retention_pct": round(naive_score, 1),
                "smart_retention_pct": round(smart_score, 1),
                "smart_output_tokens": report.output_tokens,
            }
        )
    return rows


def make_chart(rows, out_path: Path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    kinds = [r["kind"] for r in rows]
    naive = [r["naive_retention_pct"] for r in rows]
    smart = [r["smart_retention_pct"] for r in rows]

    x = range(len(kinds))
    width = 0.38

    fig, ax = plt.subplots(figsize=(8.5, 5.0), dpi=140)
    b1 = ax.bar([i - width / 2 for i in x], naive, width, label="Naive tail truncation", color="#8a8a8a")
    b2 = ax.bar([i + width / 2 for i in x], smart, width, label="tool-result-clipper", color="#2b7bd6")

    ax.set_xticks(list(x))
    ax.set_xticklabels(kinds)
    ax.set_ylabel("Key facts preserved (%)")
    ax.set_ylim(0, 110)
    ax.set_title(f"Key-fact retention at {rows[0]['budget']}-token budget")
    ax.legend(loc="upper left")
    ax.grid(axis="y", linestyle=":", alpha=0.5)

    for bars in (b1, b2):
        for b in bars:
            h = b.get_height()
            ax.text(b.get_x() + b.get_width() / 2, h + 2, f"{h:.0f}", ha="center", fontsize=9)

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)
    print(f"Wrote {out_path}")


def main():
    budget = 400
    rows = run(budget=budget)
    print(f"{'kind':<6} {'input_tok':>10} {'budget':>7} {'naive%':>8} {'smart%':>8}")
    for r in rows:
        print(
            f"{r['kind']:<6} {r['input_tokens']:>10} {r['budget']:>7} "
            f"{r['naive_retention_pct']:>8} {r['smart_retention_pct']:>8}"
        )
    out = ROOT / "docs" / "before_after.png"
    make_chart(rows, out)

    # Also emit machine-readable results next to the chart.
    results_path = ROOT / "docs" / "results.json"
    results_path.write_text(json.dumps({"budget": budget, "rows": rows}, indent=2))
    print(f"Wrote {results_path}")


if __name__ == "__main__":
    main()
