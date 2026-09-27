from __future__ import annotations

import argparse
import sys

from .clipper import clip


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="clip",
        description="Clip a tool result to fit a token budget while preserving high-signal content.",
    )
    parser.add_argument("path", nargs="?", help="Input file. Reads stdin when omitted.")
    parser.add_argument("--budget", "-b", type=int, required=True, help="Maximum output tokens.")
    parser.add_argument(
        "--kind",
        "-k",
        choices=("auto", "json", "logs", "list", "text"),
        default="auto",
        help="Force a strategy. Default auto detects.",
    )
    parser.add_argument("--report", action="store_true", help="Print a summary to stderr.")
    args = parser.parse_args(argv)

    if args.path:
        with open(args.path, "r", encoding="utf-8") as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    kind = None if args.kind == "auto" else args.kind
    out, report = clip(text, budget=args.budget, kind=kind)
    sys.stdout.write(out)
    if args.report:
        sys.stderr.write(
            f"kind={report.kind} strategy={report.strategy} "
            f"in={report.input_tokens} out={report.output_tokens} "
            f"budget={report.budget} ratio={report.ratio:.2f}\n"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
