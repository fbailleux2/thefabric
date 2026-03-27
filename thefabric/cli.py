from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
from pathlib import Path

from .engine import run_thefabric
from .models import DailySession

# Default LLM model for PySpur nodes — override via --pyspur-model or PYSPUR_MODEL env var.
_DEFAULT_PYSPUR_MODEL = "openai/chatgpt-4o-latest"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "TheFabric — Daily session orchestrator "
            "(Jean-Marc + PySpur + Hermes + BundleFabric + KFabric)"
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ── run command ───────────────────────────────────────────────────────────
    run_parser = subparsers.add_parser(
        "run",
        help="Analyse a daily session JSON and generate all TheFabric artifacts",
    )
    run_parser.add_argument(
        "--input", "-i",
        required=True,
        help="Path to the JSON session file (DailySession format)",
    )
    run_parser.add_argument(
        "--output", "-o",
        default="./artifacts",
        help="Output directory for generated artifacts (default: ./artifacts)",
    )
    run_parser.add_argument(
        "--bundlefabric-dir",
        default=None,
        help=(
            "Path to the BundleFabric bundles directory. "
            "Default: ../bundlefabric/bundles relative to this repo root. "
            "If not found, bundle search is skipped and a new bundle is always created."
        ),
    )
    run_parser.add_argument(
        "--kfabric-url",
        default=os.environ.get("KFABRIC_URL"),
        help="Base URL for a running KFabric API (e.g. http://localhost:8000). "
             "If omitted, only the query plan is generated without submitting.",
    )
    run_parser.add_argument(
        "--kfabric-api-key",
        default=os.environ.get("KFABRIC_API_KEY"),
        help="Optional API key for KFabric (Bearer token).",
    )
    run_parser.add_argument(
        "--pyspur-model",
        default=os.environ.get("PYSPUR_MODEL", _DEFAULT_PYSPUR_MODEL),
        help=(
            "LLM model for PySpur nodes. Use PySpur provider/model format. "
            "Examples: openai/chatgpt-4o-latest, anthropic/claude-sonnet-4-6, ollama/mistral. "
            "Default: openai/chatgpt-4o-latest (override via PYSPUR_MODEL env var)."
        ),
    )
    run_parser.add_argument(
        "--pyspur-url",
        default=os.environ.get("PYSPUR_URL"),
        help="Base URL of a running PySpur instance (e.g. http://localhost:6080). "
             "If set, the generated workflow definition will be submitted via POST /api/v1/workflows.",
    )

    args = parser.parse_args()

    if args.command == "run":
        return _cmd_run(args)

    return 1


def _cmd_run(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    if not input_path.exists():
        print("ERROR: input file not found: {0}".format(input_path), file=sys.stderr)
        return 1

    session = _load_session(input_path)

    # Resolve bundlefabric dir
    bundlefabric_dir = _resolve_bundlefabric_dir(args.bundlefabric_dir)

    payload = run_thefabric(
        session=session,
        output_dir=Path(args.output),
        bundlefabric_bundles_dir=bundlefabric_dir,
        kfabric_url=args.kfabric_url,
        kfabric_api_key=args.kfabric_api_key,
        pyspur_model=args.pyspur_model,
    )

    # Optionally submit workflow to running PySpur instance
    if args.pyspur_url:
        _submit_pyspur_workflow(args.pyspur_url, payload["pyspur"]["workflow_template"])

    selected = payload["bundlefabric"].get("selected_bundle", {})
    print(json.dumps(
        {
            "status": "ok",
            "session_id": session.session_id,
            "output_dir": str(Path(args.output).resolve()),
            "domain": payload["analysis"]["process_context"],
            "selected_bundle": selected.get("bundle_id", "none"),
            "bundle_score": selected.get("score", 0.0),
            "created_bundle": payload["bundlefabric"].get("created_bundle_id"),
            "pyspur_model": args.pyspur_model,
        },
        indent=2,
    ))
    return 0


def _load_session(path: Path) -> DailySession:
    return DailySession.from_dict(json.loads(path.read_text(encoding="utf-8")))


def _resolve_bundlefabric_dir(cli_value: str | None) -> Path:
    """Return the BundleFabric bundles directory, with a warning if it doesn't exist."""
    if cli_value:
        path = Path(cli_value)
    else:
        # Default: ../bundlefabric/bundles relative to repo root
        repo_root = Path(__file__).resolve().parents[1]
        path = repo_root.parent / "bundlefabric" / "bundles"

    if not path.exists():
        print(
            "WARNING: BundleFabric bundles dir not found at '{dir}'. "
            "Bundle search will be skipped — a new bundle will always be created. "
            "Clone fbailleux2/bundlefabric alongside this repo, or pass --bundlefabric-dir.".format(
                dir=path
            ),
            file=sys.stderr,
        )
    return path


def _submit_pyspur_workflow(pyspur_url: str, workflow: dict) -> None:
    """POST the workflow definition to a running PySpur instance."""
    import json as _json
    import urllib.error
    import urllib.request

    url = pyspur_url.rstrip("/") + "/api/v1/workflows"
    data = _json.dumps(workflow).encode("utf-8")
    req = urllib.request.Request(
        url=url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            result = _json.loads(body) if body else {}
            print("PySpur workflow submitted: id={0}".format(result.get("id", "?")))
    except urllib.error.HTTPError as exc:
        print(
            "WARNING: PySpur submission failed (HTTP {code}): {body}".format(
                code=exc.code, body=exc.read().decode("utf-8", errors="replace")
            ),
            file=sys.stderr,
        )
    except Exception as exc:
        print("WARNING: PySpur submission error: {0}".format(exc), file=sys.stderr)
