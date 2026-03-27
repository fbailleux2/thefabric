from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..models import DailySession


def resolve_bundle(
    session: DailySession,
    analysis: Dict[str, Any],
    bundlefabric_bundles_dir: Path,
    output_dir: Path,
    create_threshold: float = 0.48,
) -> Dict[str, Any]:
    manifests = _load_manifests(bundlefabric_bundles_dir)
    matches = []
    for manifest in manifests:
        score, overlap, matched_keywords, recency = _score_bundle(analysis, manifest)
        matches.append(
            {
                "bundle_id": manifest.get("id", ""),
                "bundle_name": manifest.get("name", ""),
                "score": score,
                "tps_score": _tps_score(manifest),
                "keyword_overlap": overlap,
                "recency_score": recency,
                "matched_keywords": matched_keywords,
                "explanation": "Matched: {0}".format(", ".join(matched_keywords[:5]) or "general"),
                "manifest_path": str(manifest.get("_path", "")),
            }
        )
    matches.sort(key=lambda item: item["score"], reverse=True)

    selected_bundle = matches[0] if matches else None
    created_bundle = None
    created_bundle_id = None
    if not selected_bundle or selected_bundle["score"] < create_threshold:
        created_bundle = _create_bundle(session, analysis, output_dir / "bundles")
        created_bundle_id = created_bundle["id"]
        selected_bundle = {
            "bundle_id": created_bundle["id"],
            "bundle_name": created_bundle["name"],
            "score": 1.0,
            "tps_score": _tps_score(created_bundle),
            "keyword_overlap": 1.0,
            "recency_score": 1.0,
            "matched_keywords": created_bundle.get("keywords", [])[:8],
            "explanation": "Bundle cree par TheFabric faute de match suffisant",
            "manifest_path": str((output_dir / "bundles" / created_bundle["id"] / "manifest.yaml")),
        }

    return {
        "searched_dir": str(bundlefabric_bundles_dir),
        "threshold": create_threshold,
        "top_matches": matches[:5],
        "selected_bundle": selected_bundle,
        "created_bundle_id": created_bundle_id,
        "created_bundle_manifest": created_bundle,
    }


def _load_manifests(bundles_dir: Path) -> List[Dict[str, Any]]:
    manifests = []
    if not bundles_dir.exists():
        return manifests
    for manifest_path in sorted(bundles_dir.glob("*/manifest.yaml")):
        parsed = _parse_simple_yaml(manifest_path.read_text(encoding="utf-8"))
        parsed["_path"] = str(manifest_path)
        manifests.append(parsed)
    return manifests


def _score_bundle(analysis: Dict[str, Any], manifest: Dict[str, Any]) -> tuple:
    intent_terms = set(item.lower() for item in analysis["keywords"])
    intent_terms.update(item.lower() for item in analysis["apps_used"])
    intent_terms.update(
        token.lower()
        for recommendation in analysis["recommendations"]
        for token in recommendation["title"].lower().split()
        if len(token) > 3
    )
    bundle_terms = set(item.lower() for item in manifest.get("keywords", []))
    bundle_terms.update(item.lower() for item in manifest.get("domains", []))
    bundle_terms.update(item.lower() for item in manifest.get("capabilities", []))
    bundle_terms.update(str(manifest.get("id", "")).replace("-", " ").lower().split())
    bundle_terms.update(str(manifest.get("name", "")).lower().split())

    matched = sorted(intent_terms & bundle_terms)
    overlap = round(len(matched) / float(max(len(intent_terms), 1)), 4)
    tps = _tps_score(manifest)
    recency = _recency_score(manifest)
    score = round(overlap * 0.5 + tps * 0.3 + recency * 0.2, 4)
    return score, overlap, matched, recency


def _tps_score(manifest: Dict[str, Any]) -> float:
    temporal = manifest.get("temporal", {})
    # Real BundleFabric manifests use "freshness" (not "freshness_score") — support both.
    freshness = _as_float(
        temporal.get("freshness") if temporal.get("freshness") is not None else temporal.get("freshness_score"),
        0.5,
    )
    usage_frequency = _as_float(temporal.get("usage_frequency"), 0.5)
    ecosystem_alignment = _as_float(temporal.get("ecosystem_alignment"), 0.5)
    return round(freshness * 0.4 + usage_frequency * 0.3 + ecosystem_alignment * 0.3, 4)


def _recency_score(manifest: Dict[str, Any]) -> float:
    temporal = manifest.get("temporal", {})
    # Support both "last_updated" (TheFabric bundles) and "updated_at" (real BundleFabric manifests)
    raw = temporal.get("last_updated") or manifest.get("updated_at")
    if not raw:
        return 0.5
    try:
        updated = datetime.fromisoformat(str(raw).strip("'").strip('"'))
        days_old = (datetime.utcnow() - updated).days
        return round(max(0.1, 1.0 - (days_old / 365.0)), 4)
    except Exception:
        return 0.5


def _create_bundle(session: DailySession, analysis: Dict[str, Any], bundles_output_dir: Path) -> Dict[str, Any]:
    bundle_id = "bundle-{0}-automation".format(_slug(session.process_context))
    bundle_dir = bundles_output_dir / bundle_id
    bundle_dir.mkdir(parents=True, exist_ok=True)

    capabilities = list(
        dict.fromkeys(
            ["session-analysis", "workflow-design", "knowledge-grounding", "hermes-learning"]
            + [app.lower().replace(" ", "-") for app in analysis["apps_used"]]
        )
    )
    domains = list(dict.fromkeys([_slug(session.process_context)] + analysis["apps_used"][:4]))
    keywords = analysis["keywords"][:16]

    manifest = {
        "id": bundle_id,
        "version": "1.0.0",
        "name": "TheFabric {0}".format(session.process_context.replace("-", " ").title()),
        "description": "Bundle specialise cree automatiquement par TheFabric pour un processus quotidien observe.",
        "capabilities": capabilities,
        "domains": domains,
        "keywords": keywords,
        "temporal": {
            "status": "active",
            "freshness_score": 0.85,
            "usage_frequency": 0.5,
            "ecosystem_alignment": 0.82,
            "last_updated": datetime.utcnow().strftime("%Y-%m-%d"),
            "usage_count": 0,
        },
        "author": "thefabric",
        "license": "MIT",
        "deerflow_workflow": "thefabric-{0}".format(_slug(session.process_context)),
        "rag_collection": "kfabric-{0}".format(_slug(session.process_context)),
    }

    (bundle_dir / "manifest.yaml").write_text(_dump_simple_yaml(manifest), encoding="utf-8")
    (bundle_dir / "README.md").write_text(_bundle_readme(session, analysis, manifest), encoding="utf-8")
    (bundle_dir / "tools.yaml").write_text("tools:\n  - hermes\n  - pyspur\n  - kfabric\n", encoding="utf-8")
    prompts_dir = bundle_dir / "prompts"
    prompts_dir.mkdir(exist_ok=True)
    (prompts_dir / "system.md").write_text(
        (
            "# {0}\n\n"
            "Bundle genere par TheFabric.\n\n"
            "Objectif : automatiser le processus `{1}` en s'appuyant sur Hermes pour la memoire,\n"
            "PySpur pour le workflow et KFabric pour le corpus documentaire.\n"
        ).format(manifest["name"], session.process_context),
        encoding="utf-8",
    )
    return manifest


def _bundle_readme(session: DailySession, analysis: Dict[str, Any], manifest: Dict[str, Any]) -> str:
    lines = [
        "# {0}".format(manifest["name"]),
        "",
        manifest["description"],
        "",
        "## Process context",
        "",
        "- {0}".format(session.process_context),
        "",
        "## Observed apps",
        "",
    ]
    for app in analysis["apps_used"]:
        lines.append("- {0}".format(app))
    lines.extend(["", "## Recommended steps", ""])
    for recommendation in analysis["recommendations"]:
        lines.append("- {0}: {1}".format(recommendation["title"], recommendation["description"]))
    return "\n".join(lines) + "\n"


def _parse_simple_yaml(text: str) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    current_key: Optional[str] = None
    last_scalar_key: Optional[str] = None
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()
        if line.startswith("- "):
            if current_key is not None:
                if data[current_key] is None:
                    data[current_key] = []
                if isinstance(data[current_key], list):
                    data[current_key].append(_parse_scalar(line[2:].strip()))
            continue
        if indent == 0:
            if line.endswith(":") and ":" not in line[:-1]:
                current_key = line[:-1]
                data[current_key] = None
                last_scalar_key = None
                continue
            if ":" not in line:
                if last_scalar_key and isinstance(data.get(last_scalar_key), str):
                    data[last_scalar_key] = "{0} {1}".format(data[last_scalar_key], line).strip()
                continue
            key, value = line.split(":", 1)
            data[key.strip()] = _parse_scalar(value.strip())
            current_key = None
            last_scalar_key = key.strip()
        else:
            if current_key is None:
                continue
            if ":" in line:
                if data[current_key] is None:
                    data[current_key] = {}
                key, value = line.split(":", 1)
                data[current_key][key.strip()] = _parse_scalar(value.strip())
            elif last_scalar_key and isinstance(data.get(last_scalar_key), str):
                data[last_scalar_key] = "{0} {1}".format(data[last_scalar_key], line).strip()
    return data


def _dump_simple_yaml(data: Dict[str, Any]) -> str:
    lines: List[str] = []
    for key, value in data.items():
        if isinstance(value, list):
            lines.append("{0}:".format(key))
            for item in value:
                lines.append("- {0}".format(_scalar_to_yaml(item)))
        elif isinstance(value, dict):
            lines.append("{0}:".format(key))
            for nested_key, nested_value in value.items():
                lines.append("  {0}: {1}".format(nested_key, _scalar_to_yaml(nested_value)))
        else:
            lines.append("{0}: {1}".format(key, _scalar_to_yaml(value)))
    return "\n".join(lines) + "\n"


def _parse_scalar(value: str) -> Any:
    if value in ("true", "false"):
        return value == "true"
    if value == "null":
        return None
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _scalar_to_yaml(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if not text:
        return "''"
    if any(char in text for char in [":", "#", "[", "]", "{", "}", ","]) or text != text.strip():
        return "'" + text.replace("'", "''") + "'"
    return text


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _slug(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in value)
    return "-".join(part for part in cleaned.split("-") if part)
