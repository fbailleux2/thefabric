"""Jean-Marc integration.

Generates payloads compatible with Jean-Marc's actual Pydantic schema
(fbailleux2/jean-marc, schema_version 2.0).

Jean-Marc field mapping (from src/jean_marc/models.py):
  ProcessAnalysis:
    declared_steps: list[ProcedureStep]      {order, action, application, is_declared}
    observed_steps: list[ObservedStep]       {order, action, application, duration_seconds, irritant_kind}
    irritants:      list[Irritant]           {kind (IrritantKind enum), severity, description, at_step,
                                              estimated_time_loss_seconds}
    artifacts:      list[ArtifactIO]         {name, kind (ArtifactKind), direction, application}
    recommendations: list[ProcessRecommendation]  {rec_type, description, estimated_gain_percent,
                                                    complexity, target_applications}
    procedure_state: ProcedureState enum     (declared|observed|validated|automatable)

  FieldObservation:
    declared_procedure: str
    real_procedure_summary: str
    gap_description: str
    total_irritant_severity: float
    automatable: bool
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List

from ..models import DailySession

# ── IrritantKind enum values (jean-marc) ──────────────────────────────────────
_IRRITANT_KIND_MAP = {
    "double_entry": "double_entry",
    "context_switch": "context_switching",   # TheFabric internal → Jean-Marc
    "context_switching": "context_switching",
    "search": "lookup",                      # TheFabric "search" → Jean-Marc "lookup"
    "lookup": "lookup",
    "waiting": "waiting",
    "manual_transcription": "manual_entry",  # TheFabric internal → Jean-Marc
    "manual_entry": "manual_entry",
    "rework": "rework",
    "approval_delay": "approval_delay",
}

# ── ArtifactKind enum values (jean-marc) ──────────────────────────────────────
_ARTIFACT_KIND_MAP = {
    "email": "email",
    "erp_record": "erp_record",
    "pdf": "pdf",
    "file": "file",
    "message": "email",     # closest jean-marc kind
    "form": "form",
    "generic": "file",
    "spreadsheet": "file",
}

# ── RecType enum values (jean-marc) ───────────────────────────────────────────
_REC_TYPE_KEYWORDS = {
    "automatiser": "automate",
    "confier": "delegate",
    "publier": "simplify",
    "construire": "simplify",
    "eliminer": "eliminate",
}


def build_jean_marc_payload(session: DailySession, analysis: Dict[str, Any]) -> Dict[str, Any]:
    """Build a Jean-Marc schema-compatible payload from TheFabric analysis.

    Returns a dict with two top-level keys:
      - process_analysis  (maps to jean-marc ProcessAnalysis)
      - field_observation (maps to jean-marc FieldObservation)
    """
    generated_at = datetime.utcnow().isoformat() + "Z"
    analysis_id = str(uuid.uuid4())
    observation_id = str(uuid.uuid4())

    process_analysis = {
        # ── Identity ──────────────────────────────────────────────────
        "id": analysis_id,
        "session_id": session.session_id,
        "analysis_date": generated_at,
        "schema_version": "2.0",
        # ── Classification ────────────────────────────────────────────
        "domain": analysis["process_context"],
        "keywords": analysis["keywords"],
        "procedure_state": _procedure_state(analysis),
        # ── Steps ─────────────────────────────────────────────────────
        "declared_steps": _to_declared_steps(session),
        "observed_steps": _to_observed_steps(analysis["observed_steps"], analysis["irritants"]),
        # ── Process intelligence ───────────────────────────────────────
        "patterns": _to_patterns(analysis["supporting_patterns"]),
        "artifacts": _to_artifacts(analysis["input_artifacts"] + analysis["output_artifacts"]),
        "rules": _to_rules(analysis["business_rules"]),
        "decision_points": _to_decision_points(analysis["decisions"]),
        "irritants": _to_irritants(analysis["irritants"]),
        "recommendations": _to_recommendations(analysis["recommendations"]),
        # ── TheFabric extensions (prefixed, ignored by Jean-Marc validator) ──
        "_thefabric_coverage_score": analysis["coverage_score"],
        "_thefabric_divergence_score": analysis["divergence_score"],
        "_thefabric_mermaid": analysis["process_map_mermaid"],
    }

    total_severity = sum(i.get("severity", 0.0) for i in analysis["irritants"])
    automatable = total_severity > 1.0 or any(
        i.get("severity", 0.0) > 0.8 for i in analysis["irritants"]
    )

    field_observation = {
        # ── Identity ──────────────────────────────────────────────────
        "id": observation_id,
        "session_id": session.session_id,
        "analysis_id": analysis_id,
        "observation_date": generated_at,
        "schema_version": "2.0",
        # ── Core observation fields (Jean-Marc FieldObservation) ───────
        "declared_procedure": session.declared_procedure or "Procédure déclarée non fournie.",
        "real_procedure_summary": _build_real_summary(analysis),
        "gap_description": _build_gap_description(analysis),
        "total_irritant_severity": round(total_severity, 3),
        "automatable": automatable,
        # ── TheFabric extensions ───────────────────────────────────────
        "_thefabric_origin": "thefabric",
        "_thefabric_validation_status": "ready_for_validation",
        "_thefabric_analysis_markdown": _analysis_markdown(session, analysis),
    }

    return {
        "process_analysis": process_analysis,
        "field_observation": field_observation,
    }


# ── Translators ───────────────────────────────────────────────────────────────

def _procedure_state(analysis: Dict[str, Any]) -> str:
    """Map TheFabric analysis metrics to Jean-Marc ProcedureState enum value."""
    total_severity = sum(i.get("severity", 0.0) for i in analysis["irritants"])
    if total_severity > 1.5 and analysis["recommendations"]:
        return "automatable"
    if analysis["divergence_score"] > 0.3:
        return "observed"
    return "declared"


def _to_declared_steps(session: DailySession) -> List[Dict[str, Any]]:
    """Build Jean-Marc ProcedureStep list from declared_procedure text."""
    if not session.declared_procedure:
        return []
    lines = [line.strip() for line in session.declared_procedure.splitlines() if line.strip()]
    return [
        {
            "order": i,
            "action": line,
            "application": "",
            "duration_seconds": None,
            "is_declared": True,
        }
        for i, line in enumerate(lines)
    ]


def _to_observed_steps(
    step_rows: List[Dict[str, Any]],
    irritants: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Convert TheFabric step rows to Jean-Marc ObservedStep format (0-based order)."""
    # Map each impacted step label to its first irritant_kind
    irritant_by_label: Dict[str, str] = {}
    for irritant in irritants:
        jean_marc_kind = _IRRITANT_KIND_MAP.get(irritant.get("kind", ""), None)
        for step_label in irritant.get("impacted_steps", []):
            if step_label not in irritant_by_label:
                irritant_by_label[step_label] = jean_marc_kind

    return [
        {
            "order": row["position"] - 1,           # Jean-Marc is 0-based
            "action": row["label"],
            "application": row.get("app") or "",
            "duration_seconds": row.get("average_duration_seconds") or None,
            "irritant_kind": irritant_by_label.get(row["label"]),
            "deviation_from_declared": None,        # requires human annotation
        }
        for row in step_rows
    ]


def _to_patterns(supporting_patterns: List[str]) -> List[Dict[str, Any]]:
    """Convert TheFabric supporting_patterns strings to Jean-Marc PatternHypothesis format.

    Input format: "App1 -> App2 (x3)"
    """
    patterns = []
    for raw in supporting_patterns:
        parts = raw.split(" (x")
        sequence_part = parts[0].strip()
        try:
            freq = int(parts[1].rstrip(")")) if len(parts) > 1 else 1
        except (ValueError, IndexError):
            freq = 1
        apps = [s.strip() for s in sequence_part.split("->")]
        patterns.append({
            "sequence": apps,
            "frequency": freq,
            "applications": list(dict.fromkeys(apps)),
            "confidence": round(min(0.95, 0.5 + freq * 0.1), 3),
            "irritant_kind": None,
        })
    return patterns


def _to_artifacts(artifacts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert TheFabric artifacts to Jean-Marc ArtifactIO format."""
    return [
        {
            "name": a["name"],
            "kind": _ARTIFACT_KIND_MAP.get(a.get("kind", "generic"), "file"),
            "direction": a["direction"],            # "input" | "output"
            "application": a.get("source", ""),
        }
        for a in artifacts
    ]


def _to_rules(business_rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert TheFabric business_rules to Jean-Marc BusinessRule format."""
    return [
        {
            "condition": r["condition"],
            "action": r["outcome"],
            "applications": [r["source"]] if r.get("source") else [],
        }
        for r in business_rules
    ]


def _to_decision_points(decisions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert TheFabric decisions to Jean-Marc DecisionPoint format."""
    result = []
    for d in decisions:
        # Extract step index from id like "decision-3"
        try:
            at_step = int(d["id"].split("-")[-1]) - 1
        except (ValueError, IndexError):
            at_step = 0
        result.append({
            "at_step": at_step,
            "question": d["question"],
            "options": [r["outcome"] for r in d.get("rules", [])],
        })
    return result


def _to_irritants(irritants: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert TheFabric irritants to Jean-Marc Irritant format.

    Jean-Marc Irritant fields:
      kind (IrritantKind), severity, at_step, description, estimated_time_loss_seconds
    """
    time_loss_defaults = {
        "double_entry": 120,
        "context_switching": 30,
        "rework": 300,
        "waiting": 600,
        "lookup": 60,
        "approval_delay": 900,
        "manual_entry": 90,
    }
    result = []
    for irr in irritants:
        jean_marc_kind = _IRRITANT_KIND_MAP.get(irr.get("kind", ""), "manual_entry")
        freq = irr.get("frequency", 1)
        time_loss = time_loss_defaults.get(jean_marc_kind, 60) * freq
        result.append({
            "kind": jean_marc_kind,
            "severity": irr.get("severity", 0.5),
            "at_step": None,        # step-level correlation requires further work
            "description": irr.get("description", irr.get("title", "")),
            "estimated_time_loss_seconds": float(time_loss),
        })
    return result


def _to_recommendations(recommendations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert TheFabric recommendations to Jean-Marc ProcessRecommendation format."""
    result = []
    for rec in recommendations:
        title_lower = rec["title"].lower()
        rec_type = "simplify"
        for keyword, mapped in _REC_TYPE_KEYWORDS.items():
            if keyword in title_lower:
                rec_type = mapped
                break
        result.append({
            "rec_type": rec_type,
            "description": rec["description"],
            "estimated_gain_percent": round(rec.get("automation_potential", 0.5) * 100, 1),
            "complexity": "medium",
            "target_applications": [],
        })
    return result


# ── Text helpers ──────────────────────────────────────────────────────────────

def _build_real_summary(analysis: Dict[str, Any]) -> str:
    apps = analysis.get("apps_used", [])
    steps = analysis.get("observed_steps", [])
    return (
        "Observed {steps} steps across {n_apps} application(s): {app_list}. "
        "Domain: {context}."
    ).format(
        steps=len(steps),
        n_apps=len(apps),
        app_list=", ".join(apps[:5]) + ("..." if len(apps) > 5 else ""),
        context=analysis.get("process_context", "unknown"),
    )


def _build_gap_description(analysis: Dict[str, Any]) -> str:
    declared_lines = analysis.get("declared_procedure", "") or ""
    declared = len([l for l in declared_lines.splitlines() if l.strip()])
    observed = len(analysis.get("observed_steps", []))
    extra = max(0, observed - declared)
    irritant_names = ", ".join(
        i.get("title", i.get("kind", "?")) for i in analysis.get("irritants", [])[:3]
    )
    return (
        "{extra} undeclared step(s) detected vs formal procedure. "
        "Main friction: {irritants}. "
        "Divergence score: {score:.2f}."
    ).format(
        extra=extra,
        irritants=irritant_names or "none",
        score=analysis.get("divergence_score", 0.0),
    )


def _analysis_markdown(session: DailySession, analysis: Dict[str, Any]) -> str:
    lines = [
        "# TheFabric → Jean-Marc",
        "",
        "## Processus",
        analysis["process_context"],
        "",
        "## Résumé",
        analysis["summary"],
        "",
        "## Étapes observées",
    ]
    for step in analysis["observed_steps"]:
        lines.append("- {pos}. {label} [{app}]".format(
            pos=step["position"], label=step["label"], app=step.get("app") or "?"
        ))

    lines.extend(["", "## Décisions"])
    if analysis["decisions"]:
        for d in analysis["decisions"]:
            lines.append("- {label}: {question}".format(
                label=d["step_label"], question=d["question"]
            ))
    else:
        lines.append("- Aucune décision explicite")

    lines.extend(["", "## Irritants"])
    for irr in analysis["irritants"]:
        lines.append("- [{kind}] {title} (sévérité {severity:.2f})".format(**irr))

    lines.extend(["", "## Recommandations"])
    for rec in analysis["recommendations"]:
        lines.append("- {title}: {description}".format(**rec))

    lines.extend(["", "## Contexte complémentaire", session.additional_context or "_Aucun._"])
    return "\n".join(lines)
