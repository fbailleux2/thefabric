from __future__ import annotations

import argparse
import json
from pathlib import Path

from .engine import run_thefabric
from .models import DailySession


def main() -> int:
    parser = argparse.ArgumentParser(description="TheFabric CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Analyze a daily session and generate all TheFabric artifacts")
    run_parser.add_argument("--input", required=True, help="Path to the JSON session file")
    run_parser.add_argument("--output", required=True, help="Output directory for generated artifacts")
    run_parser.add_argument(
        "--bundlefabric-dir",
        default=str(_default_bundlefabric_dir()),
        help="Path to the BundleFabric bundles directory",
    )
    run_parser.add_argument("--kfabric-url", default=None, help="Optional base URL for a running KFabric API")
    run_parser.add_argument("--kfabric-api-key", default=None, help="Optional API key for KFabric")

    args = parser.parse_args()

    if args.command == "run":
        session = _load_session(Path(args.input))
        payload = run_thefabric(
            session=session,
            output_dir=Path(args.output),
            bundlefabric_bundles_dir=Path(args.bundlefabric_dir),
            kfabric_url=args.kfabric_url,
            kfabric_api_key=args.kfabric_api_key,
        )
        print(
            json.dumps(
                {
                    "status": "ok",
                    "session_id": session.session_id,
                    "output_dir": str(Path(args.output).resolve()),
                    "selected_bundle": payload["bundlefabric"]["selected_bundle"]["bundle_id"],
                },
                indent=2,
            )
        )
        return 0

    return 1


def _load_session(path: Path) -> DailySession:
    return DailySession.from_dict(json.loads(path.read_text(encoding="utf-8")))


def _default_bundlefabric_dir() -> Path:
    repo_root = Path(__file__).resolve().parents[1]
    return repo_root.parent / "bundlefabric" / "bundles"
