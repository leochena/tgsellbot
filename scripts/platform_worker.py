from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.model_lab import ModelLabWorker, ModelLabWorkerConfig  # noqa: E402


def _read_task(path: str | None) -> dict[str, Any]:
    if path:
        text = Path(path).read_text(encoding="utf-8")
    else:
        text = sys.stdin.read()
    if not text.strip():
        raise SystemExit("task JSON is required on stdin or through --input")
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise SystemExit("task JSON must be an object")
    return payload


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    task = _read_task(args.input)
    config = ModelLabWorkerConfig(
        timeout_seconds=args.timeout,
        max_response_bytes=args.max_response_bytes,
        max_redirects=args.max_redirects,
        max_concurrency=args.max_concurrency,
        max_tokens=args.max_tokens,
    )
    worker = ModelLabWorker(config=config)
    return await worker.run_task(task)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run an isolated TGSellBot Model Lab P0 compatibility check. "
            "Task JSON is read from stdin by default and API keys are never persisted by this script."
        )
    )
    parser.add_argument("--input", help="Read task JSON from this file instead of stdin.")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--max-response-bytes", type=int, default=256 * 1024)
    parser.add_argument("--max-redirects", type=int, default=2)
    parser.add_argument("--max-concurrency", type=int, default=2)
    parser.add_argument("--max-tokens", type=int, default=64)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = asyncio.run(_run(args))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
