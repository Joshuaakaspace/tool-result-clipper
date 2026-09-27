from __future__ import annotations

import json
import re
from collections import Counter

from .tokens import count_tokens, encode, decode

TIMESTAMP_RE = re.compile(
    r"^(?:\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[\.,]?\d*Z?|\[\d{2}:\d{2}:\d{2}\]|\d{2}:\d{2}:\d{2})\s*"
)
LEVEL_RE = re.compile(r"\b(DEBUG|INFO|WARN|WARNING|ERROR|CRITICAL|TRACE|FATAL)\b")
HEX_RE = re.compile(r"\b[0-9a-f]{8,}\b", re.I)
UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I
)
NUM_RE = re.compile(r"\b\d+\b")

LOG_PRIORITY = {"CRITICAL": 5, "FATAL": 5, "ERROR": 4, "WARN": 3, "WARNING": 3, "INFO": 2, "DEBUG": 1, "TRACE": 0}


def _fit(text: str, budget: int) -> str:
    """Hard cap by tokens using the shared encoder."""
    if count_tokens(text) <= budget:
        return text
    toks = encode(text)
    return decode(toks[:budget])


def clip_text(text: str, budget: int) -> str:
    """Head plus tail truncation with a middle marker.

    Preserves the opening context and the tail (usually the answer or
    the error) that plain tail truncation would keep, but also the
    header that plain head truncation would keep.
    """
    if count_tokens(text) <= budget:
        return text
    # Reserve room for the marker.
    marker = "\n...[{n} tokens omitted]...\n"
    reserve = count_tokens(marker.format(n=999999))
    remaining = max(1, budget - reserve)
    head_budget = remaining * 2 // 3
    tail_budget = remaining - head_budget

    toks = encode(text)
    total = len(toks)
    head_txt = decode(toks[:head_budget])
    tail_txt = decode(toks[-tail_budget:]) if tail_budget else ""
    omitted = total - head_budget - tail_budget
    return head_txt + marker.format(n=omitted) + tail_txt


def _normalize_log_line(line: str) -> str:
    line = TIMESTAMP_RE.sub("", line)
    line = UUID_RE.sub("<uuid>", line)
    line = HEX_RE.sub("<hex>", line)
    line = NUM_RE.sub("<n>", line)
    return line.strip()


def _log_level(line: str) -> int:
    m = LEVEL_RE.search(line)
    if not m:
        return 2
    return LOG_PRIORITY.get(m.group(1).upper(), 2)


def clip_logs(text: str, budget: int) -> str:
    """Deduplicate near-identical log lines and keep highest severity.

    Repeated INFO or DEBUG lines are collapsed to a single line with a
    count. ERROR and WARNING lines are preserved individually so that
    context around failures survives the clip.
    """
    lines = text.splitlines()
    if not lines:
        return text

    # First pass: group consecutive duplicates by normalized form.
    groups: list[tuple[str, list[int], int]] = []  # (representative, [line_idxs], level)
    for i, ln in enumerate(lines):
        norm = _normalize_log_line(ln)
        lvl = _log_level(ln)
        if groups and groups[-1][0] == norm and lvl < 3:
            groups[-1][1].append(i)
        else:
            groups.append((norm, [i], lvl))

    # Rebuild with dup collapse.
    collapsed = []
    for norm, idxs, lvl in groups:
        if len(idxs) == 1:
            collapsed.append((lines[idxs[0]], lvl))
        else:
            rep = lines[idxs[0]]
            collapsed.append((f"{rep}    [x{len(idxs)}]", lvl))

    # If still over budget, drop lowest-severity lines from the middle.
    def render(items):
        return "\n".join(x for x, _ in items)

    if count_tokens(render(collapsed)) <= budget:
        return render(collapsed)

    # Sort candidates for removal by (level ascending, distance from ends).
    n = len(collapsed)
    order = sorted(
        range(n),
        key=lambda i: (collapsed[i][1], -min(i, n - 1 - i)),
    )
    kept = [True] * n
    dropped = 0
    for i in order:
        if count_tokens(render([c for c, k in zip(collapsed, kept) if k])) <= budget - 20:
            break
        kept[i] = False
        dropped += 1

    kept_items = [c for c, k in zip(collapsed, kept) if k]
    if dropped:
        kept_items.append((f"...[{dropped} lower-severity lines dropped]", 0))
    out = render(kept_items)
    return _fit(out, budget)


def clip_list(text: str, budget: int) -> str:
    """Keep the head and tail of a long list with a count marker."""
    lines = text.splitlines()
    if count_tokens(text) <= budget:
        return text

    # Estimate how many items we can fit.
    non_empty = [ln for ln in lines if ln.strip()]
    n = len(non_empty)
    if n == 0:
        return _fit(text, budget)

    avg = max(1, count_tokens(text) // n)
    keep = max(4, (budget - 8) // avg)
    if keep >= n:
        return _fit(text, budget)

    head_k = keep * 2 // 3
    tail_k = keep - head_k
    omitted = n - head_k - tail_k
    marker = f"    ...[{omitted} items omitted]..."
    out = "\n".join(non_empty[:head_k] + [marker] + non_empty[-tail_k:])
    return _fit(out, budget)


def _walk_json(obj, path=""):
    """Yield (path, size_est, is_container) for every node."""
    if isinstance(obj, dict):
        yield path or "$", len(json.dumps(obj)), True
        for k, v in obj.items():
            yield from _walk_json(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        yield path or "$", len(json.dumps(obj)), True
        for i, v in enumerate(obj):
            yield from _walk_json(v, f"{path}[{i}]")
    else:
        yield path, len(json.dumps(obj)), False


def _shrink_json(obj, budget_chars: int):
    """Recursively shrink until serialized length is under budget."""
    def size(o):
        return len(json.dumps(o, separators=(",", ":")))

    if size(obj) <= budget_chars:
        return obj

    if isinstance(obj, list):
        if not obj:
            return obj
        n = len(obj)
        # Try progressively smaller keep counts.
        for keep in (16, 8, 4, 2, 1):
            if keep >= n:
                continue
            head = [_shrink_json(x, budget_chars // max(1, keep)) for x in obj[: keep // 2 or 1]]
            tail = [_shrink_json(x, budget_chars // max(1, keep)) for x in obj[-(keep // 2 or 1):]]
            trimmed = head + [f"...[{n - len(head) - len(tail)} items omitted]"] + tail
            if size(trimmed) <= budget_chars:
                return trimmed
        # Last resort: single-item summary.
        return [f"...[{n} items omitted]"]

    if isinstance(obj, dict):
        # Recurse into biggest child first, replacing with summary if oversized.
        items = sorted(
            obj.items(),
            key=lambda kv: size(kv[1]) if not isinstance(kv[1], (int, float, bool, type(None))) else 0,
            reverse=True,
        )
        out = {k: v for k, v in obj.items()}
        for k, v in items:
            if size(out) <= budget_chars:
                break
            sub_budget = max(40, budget_chars // max(2, len(out)))
            out[k] = _shrink_json(v, sub_budget)
        if size(out) > budget_chars:
            # Drop least important keys (heuristic: keep short scalar keys).
            for k, _ in items:
                if size(out) <= budget_chars:
                    break
                if isinstance(out[k], (dict, list, str)) and len(json.dumps(out[k])) > 20:
                    out[k] = f"...[omitted, ~{len(json.dumps(out[k]))} chars]"
        return out

    if isinstance(obj, str) and len(obj) > 40:
        keep = max(20, budget_chars - 20)
        if keep < len(obj):
            return obj[: keep // 2] + f"...[{len(obj) - keep} chars]..." + obj[-keep // 2 :]
    return obj


def clip_json(text: str, budget: int) -> str:
    """Structure-aware JSON clipping.

    Parses the JSON, recursively drops interior array items and
    truncates long string leaves until the serialization fits the token
    budget. Preserves top-level keys so downstream code can still see
    which fields were present.
    """
    try:
        obj = json.loads(text)
    except Exception:
        return clip_text(text, budget)

    # Convert token budget to a rough char budget for JSON.
    char_budget = max(80, budget * 3)
    shrunk = _shrink_json(obj, char_budget)
    out = json.dumps(shrunk, indent=2)
    return _fit(out, budget)
