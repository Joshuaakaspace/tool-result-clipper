from .clipper import clip, ClipReport
from .detect import detect_kind
from .strategies import clip_json, clip_logs, clip_list, clip_text
from .tokens import count_tokens

__all__ = [
    "clip",
    "ClipReport",
    "detect_kind",
    "clip_json",
    "clip_logs",
    "clip_list",
    "clip_text",
    "count_tokens",
]

__version__ = "0.1.0"
