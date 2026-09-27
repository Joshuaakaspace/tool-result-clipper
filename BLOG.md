---
title: Stop truncating LLM tool results from the tail
subtitle: A 300-line clipper that keeps the parts of a tool call the model actually needs
tags:
  - python
  - llm
  - agents
  - developer-tools
  - inference
---

If you have ever wired a tool-calling loop around a large language model, you know the shape of this problem. The model calls a tool, the tool returns 20 KB of JSON, and your agent scaffolding has to decide what to feed back into the context. The easy answer is to cap the string at N characters or N tokens and hope for the best. In practice, what you actually cap with is the tail of `str(result)`, which throws away exactly the piece the model needs: the top-level `status` and `request_id`, the ERROR line hiding in 400 lines of INFO, the summary block at the top of the response.

We hit this often enough that we built a small library specifically for it. It is called `tool-result-clipper`. The code is at `https://github.com/Joshuaakaspace/tool-result-clipper`. It is deliberately small: one detection function, four strategies, a shared token counter.

## The problem in one sentence

Naive truncation is a silent context-quality regression. The output stays under budget, so nothing errors, but the model quietly loses the tokens it needed to answer.

## What the library does

`clip(text, budget)` first classifies the input as JSON, logs, list, or free text, then routes to a strategy that knows the shape.

- JSON is parsed. Interior array items are dropped with an omitted-count marker, long string leaves are trimmed, top-level keys survive so the model can still tell which fields were present in the response.
- Logs are normalized (timestamps, hex, uuids stripped) and consecutive near-duplicates are collapsed to one line with `[xN]`. Low-severity lines are the first to go when we still overshoot the budget; ERROR and CRITICAL are preserved.
- Lists keep the head and the tail with a count of what was omitted in the middle.
- Free text uses two-thirds head and one-third tail so the answer at the end and the framing at the start both survive.

Every strategy ends with the same hard cap using tiktoken so downstream code can rely on the number.

A minimal usage looks like this:

```python
from tool_result_clipper import clip

clipped, report = clip(huge_tool_output, budget=400)
# report.input_tokens, report.output_tokens, report.strategy
```

## The before and after numbers

To measure whether this is a real improvement or a nicer-looking one, we generated four synthetic tool results with planted high-signal tokens (request ids, error reasons, header and footer answers), clipped each to a 400-token budget with both naive tail truncation and the router, and counted how many planted facts survived.

Key-fact retention at the same 400-token budget:

- JSON (15,287 input tokens): 25 percent with naive tail truncation, 100 percent with the clipper.
- Logs (12,402 input tokens): 0 percent naive, 100 percent clipper. The buried ERROR, WARNING, and CRITICAL lines all survive.
- List (3,531 input tokens): 50 percent both. Both strategies happen to keep the tail, where one planted fact lives, and both drop the middle. We report the tie honestly.
- Text (4,230 input tokens): 50 percent naive, 100 percent clipper. Naive keeps the footer answer but loses the header summary.

Average retention rises from 31 percent to 88 percent at the same output token budget. The chart with the numbers is in the repo README so you can see it in context: `https://github.com/Joshuaakaspace/tool-result-clipper#results`.

## What was surprising

Two things. First, the biggest gap was not in JSON, where we expected structure-aware handling to pay off, but in logs. Tail truncation on a 12 KB log file at a 400-token budget kept literally none of the planted facts, because they were seeded early and in the middle. Dedupe plus severity-first eviction recovered all of them.

Second, the list case tying was a useful reminder to measure honestly. If your data is mostly homogeneous with signal at the ends, naive truncation is fine. The tool should not oversell itself on cases where the naive answer is already correct.

## How to try it

```
git clone https://github.com/Joshuaakaspace/tool-result-clipper
cd tool-result-clipper
pip install -r requirements.txt
pip install -e .
python benchmarks/run_benchmark.py
pytest -q
```

The benchmark script regenerates the chart in `docs/before_after.png` and writes the raw numbers to `docs/results.json`, so you can rerun with your own budgets and see the effect.

## What is next

The obvious extensions are more content kinds (tables and HTML fragments), model-specific token counters, and a streaming version that can clip a tool result as it arrives rather than buffering it. The strategy interface is small enough that plugging in a new kind is about 30 lines. If you have tool outputs that these four strategies still botch, that is the thing we want to hear about.
