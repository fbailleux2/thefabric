from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from .integrations.bundlefabric import resolve_bundle
from .integrations.hermes import build_hermes_payload
from .integrations.jean_marc import build_jean_marc_payload
from .integrations.kfabric import build_kfabric_plan
from .integrations.pyspur import build_pyspur_workflow
from .models import DailySession
from .session_analysis import analyze_session


def run_thefabric(
    session: DailySession,
    output_dir: Path,
    bundlefabric_bundles_dir: Path,
    kfabric_url: Optional[str] = None,
    kfabric_api_key: Optional[str] = None,
) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    analysis = analyze_session(session)
    jean_marc_payload = build_jean_marc_payload(session, analysis)
    pyspur_workflow = build_pyspur_workflow(session, analysis)
    kfabric_plan = build_kfabric_plan(session, analysis, base_url=kfabric_url, api_key=kfabric_api_key)
    bundle_resolution = resolve_bundle(session, analysis, bundlefabric_bundles_dir, output_dir)
    hermes_payload = build_hermes_payload(session, analysis, bundle_resolution, kfabric_plan, output_dir)

    pyspur_candidates = []
    if bundle_resolution.get("top_matches"):
        pyspur_candidates = [item["bundle_id"] for item in bundle_resolution["top_matches"]]
    if bundle_resolution.get("created_bundle_id"):
        pyspur_candidates.insert(0, bundle_resolution["created_bundle_id"])
    _inject_bundle_candidates(pyspur_workflow, pyspur_candidates)

    session_intelligence = {
        "thefabric": {
            "version": "0.1.0",
            "mission": (
                "Fusion Jean-Marc + PySpur + Hermes Agent + BundleFabric + KFabric "
                "autour d'un JSON pivot de session quotidienne."
            ),
        },
        "input_session": session.to_dict(),
        "analysis": analysis,
        "jean_marc": jean_marc_payload,
        "pyspur": {
            "workflow_template": pyspur_workflow,
        },
        "hermes": hermes_payload,
        "bundlefabric": bundle_resolution,
        "kfabric": kfabric_plan,
    }

    paths = _write_outputs(output_dir, session_intelligence)
    session_intelligence["artifacts"] = paths
    (output_dir / "run_summary.md").write_text(
        _run_summary(session, analysis, hermes_payload, bundle_resolution, kfabric_plan, paths),
        encoding="utf-8",
    )
    return session_intelligence


def _inject_bundle_candidates(pyspur_workflow: Dict[str, Any], candidates: list) -> None:
    definition = pyspur_workflow.get("definition", {})
    test_inputs = definition.get("test_inputs", [])
    if test_inputs:
        test_inputs[0]["bundle_candidates"] = candidates


def _write_outputs(output_dir: Path, payload: Dict[str, Any]) -> Dict[str, str]:
    paths = {
        "session_intelligence": str(output_dir / "session_intelligence.json"),
        "jean_marc_process_analysis": str(output_dir / "jean_marc" / "process_analysis.json"),
        "jean_marc_field_observation": str(output_dir / "jean_marc" / "field_observation.json"),
        "pyspur_workflow": str(output_dir / "pyspur" / "workflow_template.json"),
        "hermes_ingestion": str(output_dir / "hermes" / "ingestion.json"),
        "bundle_resolution": str(output_dir / "bundles" / "resolution.json"),
        "kfabric_query_create": str(output_dir / "kfabric" / "query_create.json"),
        "kfabric_plan": str(output_dir / "kfabric" / "pipeline_plan.json"),
    }

    for key, raw_path in paths.items():
        Path(raw_path).parent.mkdir(parents=True, exist_ok=True)

    _write_json(Path(paths["session_intelligence"]), payload)
    _write_json(Path(paths["jean_marc_process_analysis"]), payload["jean_marc"]["process_analysis"])
    _write_json(Path(paths["jean_marc_field_observation"]), payload["jean_marc"]["field_observation"])
    _write_json(Path(paths["pyspur_workflow"]), payload["pyspur"]["workflow_template"])
    _write_json(Path(paths["hermes_ingestion"]), payload["hermes"])
    _write_json(Path(paths["bundle_resolution"]), payload["bundlefabric"])
    _write_json(Path(paths["kfabric_query_create"]), payload["kfabric"]["query_create"])
    _write_json(Path(paths["kfabric_plan"]), payload["kfabric"])
    return paths


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _run_summary(
    session: DailySession,
    analysis: Dict[str, Any],
    hermes_payload: Dict[str, Any],
    bundle_resolution: Dict[str, Any],
    kfabric_plan: Dict[str, Any],
    paths: Dict[str, str],
) -> str:
    selected_bundle = bundle_resolution.get("selected_bundle", {})
    lines = [
        "# TheFabric Run Summary",
        "",
        "## Processus",
        "",
        "- Session: {0}".format(session.session_id),
        "- Contexte: {0}".format(session.process_context),
        "- Resume: {0}".format(analysis["summary"]),
        "",
        "## Hermes",
        "",
        "- Hermes est traite comme moteur d'execution et d'apprentissage.",
        "- Skill generee: {0}".format(hermes_payload.get("skill", {}).get("path", "")),
        "- Toolsets suggeres: {0}".format(", ".join(hermes_payload.get("suggested_toolsets", []))),
        "",
        "## Bundle",
        "",
        "- Bundle selectionne: {0}".format(selected_bundle.get("bundle_id", "aucun")),
        "- Match score: {0}".format(selected_bundle.get("score", "n/a")),
        "",
        "## KFabric",
        "",
        "- Documents cibles: {0}".format(", ".join(kfabric_plan.get("documents_needed", [])[:8])),
        "",
        "## Fichiers",
        "",
    ]
    for key, value in sorted(paths.items()):
        lines.append("- {0}: {1}".format(key, value))
    return "\n".join(lines) + "\n"
