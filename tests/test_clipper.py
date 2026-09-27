import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tool_result_clipper import clip, detect_kind, count_tokens


def test_passthrough():
    text = "hello world"
    out, report = clip(text, budget=1000)
    assert out == text
    assert report.strategy == "passthrough"


def test_detect_json():
    assert detect_kind('{"a": 1}') == "json"
    assert detect_kind("[1,2,3]") == "json"


def test_detect_logs():
    text = "\n".join(
        f"2026-01-01T00:00:{i:02d}Z INFO something happened" for i in range(6)
    )
    assert detect_kind(text) == "logs"


def test_detect_list():
    text = "\n".join(f"- item {i}" for i in range(10))
    assert detect_kind(text) == "list"


def test_json_clip_preserves_top_keys():
    payload = {"status": "ok", "request_id": "R1", "items": [{"x": i} for i in range(500)]}
    text = json.dumps(payload)
    out, report = clip(text, budget=200)
    assert '"status"' in out
    assert '"request_id"' in out
    assert report.output_tokens <= 200


def test_logs_dedupes():
    lines = ["2026-01-01T00:00:00Z INFO same thing" for _ in range(200)]
    lines.append("2026-01-01T00:01:00Z ERROR real problem here")
    text = "\n".join(lines)
    out, report = clip(text, budget=100)
    assert "real problem here" in out
    assert report.output_tokens <= 100


def test_budget_hard_cap():
    text = "x " * 10000
    out, report = clip(text, budget=50)
    assert count_tokens(out) <= 50
