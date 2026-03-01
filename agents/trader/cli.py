"""CLI entrypoint for independent Trader agent workflows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(REPO / "pce-core" / "src"))
sys.path.insert(0, str(REPO / "agents" / "llm-assistant" / "src"))

from trader_plugins.runtime import TraderRuntime


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PCE Trader agent CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    replay = sub.add_parser("replay", help="Replay candles from CSV and emit decisions")
    replay.add_argument("--csv", required=True, help="CSV with candles: symbol,timeframe,timestamp,open,high,low,close,volume")

    train = sub.add_parser("train", help="Train model from feature CSV")
    train.add_argument("--csv", required=True, help="CSV with timeframe=1h and feature columns")

    live = sub.add_parser("live-demo", help="Fetch latest real market data and run one cycle")
    live.add_argument("--output", default="agents/trader/artifacts/live_demo.json", help="Output JSON path")

    return parser


def main() -> int:
    args = build_parser().parse_args()
    runtime = TraderRuntime()

    if args.command == "replay":
        decisions = runtime.replay_csv(Path(args.csv))
        print(json.dumps({"decisions": decisions}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "train":
        result = runtime.train_from_csv(Path(args.csv))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "live-demo":
        result = runtime.live_demo_once()
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"output": str(out), "decisions": len(result)}, ensure_ascii=False))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
