from __future__ import annotations

import json
import re

TIMESTAMP_RE = re.compile(
    r"^(?:\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}|\[\d{2}:\d{2}:\d{2}\]|\d{2}:\d{2}:\d{2})"
)
LEVEL_RE = re.compile(r"\b(DEBUG|INFO|WARN|WARNING|ERROR|CRITICAL|TRACE)\b")


def detect_kind(text: str) -> str:
    """Classify a tool result as one of: json, logs, list, text."""
    stripped = text.strip()
    if not stripped:
        return "text"

    # JSON: parse-safe check on the first plausible fragment.
    if stripped[0] in "{[":
        try:
            json.loads(stripped)
            return "json"
        except Exception:
            pass

    lines = [ln for ln in stripped.splitlines() if ln.strip()]
    if len(lines) >= 4:
        ts_hits = sum(1 for ln in lines if TIMESTAMP_RE.match(ln))
        lvl_hits = sum(1 for ln in lines if LEVEL_RE.search(ln))
        if ts_hits >= max(2, len(lines) // 3) or lvl_hits >= max(2, len(lines) // 3):
            return "logs"

        # List detection: bullet or numbered markers on most lines.
        bullet_hits = sum(
            1 for ln in lines if re.match(r"^\s*(?:[-*+]|\d+[.)])\s+", ln)
        )
        if bullet_hits >= max(3, int(len(lines) * 0.6)):
            return "list"

    return "text"
