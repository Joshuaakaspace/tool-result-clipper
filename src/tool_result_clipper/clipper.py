from __future__ import annotations

from dataclasses import dataclass

from .detect import detect_kind
from .strategies import clip_json, clip_logs, clip_list, clip_text
from .tokens import count_tokens


@dataclass
class ClipReport:
    kind: str
    input_tokens: int
    output_tokens: int
    budget: int
    strategy: str

    @property
    def savings(self) -> int:
        return self.input_tokens - self.output_tokens

    @property
    def ratio(self) -> float:
        if self.input_tokens == 0:
            return 1.0
        return self.output_tokens / self.input_tokens


def clip(text: str, budget: int, kind: str | None = None) -> tuple[str, ClipReport]:
    """Clip a tool result to fit a token budget.

    Picks a strategy based on the content kind (json, logs, list,
    text). Pass an explicit kind to override detection.
    """
    if budget <= 0:
        raise ValueError("budget must be positive")

    in_tokens = count_tokens(text)
    if in_tokens <= budget:
        detected = kind or detect_kind(text)
        return text, ClipReport(
            kind=detected,
            input_tokens=in_tokens,
            output_tokens=in_tokens,
            budget=budget,
            strategy="passthrough",
        )

    detected = kind or detect_kind(text)
    if detected == "json":
        out = clip_json(text, budget)
    elif detected == "logs":
        out = clip_logs(text, budget)
    elif detected == "list":
        out = clip_list(text, budget)
    else:
        out = clip_text(text, budget)

    report = ClipReport(
        kind=detected,
        input_tokens=in_tokens,
        output_tokens=count_tokens(out),
        budget=budget,
        strategy=detected,
    )
    return out, report
