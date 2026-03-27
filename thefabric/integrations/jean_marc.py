from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from ..models import DailySession


def build_jean_marc_payload(session: DailySession, analysis: Dict[str, Any]) -> Dict[str, Any]:
    generated_at = datetime.utcnow().isoformat() + "Z"
    process_analysis = {
        "id": "analysis-{0}".format(session.session_id),
        "process_context": analysis["process_context"],
        "procedure_id": "declared-{0}".format(session.process_context),
        "procedure_name": session.process_context.replace("-", " ").title(),
        "declared_steps": [],
        "observed_steps": analysis["observed_steps"],
        "decisions": analysis["decisions"],
        "irritants": analysis["irritants"],
        "input_artifacts": analysis["input_artifacts"],
        "output_artifacts": analysis["output_artifacts"],
        "business_rules": analysis["business_rules"],
        "recommendations": analysis["recommendations"],
        "supporting_patterns": analysis["supporting_patterns"],
        "coverage_score": analysis["coverage_score"],
        "divergence_score": analysis["divergence_score"],
        "summary": analysis["summary"],
        "process_map_mermaid": analysis["process_map_mermaid"],
        "generated_at": generated_at,
        "schema_version": "2.0",
    }

    field_observation = {
        "id": "observation-{0}".format(session.session_id),
        "process_context": analysis["process_context"],
        "declared_procedure": session.declared_procedure or "Procedure declaree non fournie.",
        "observed_behavior": analysis["summary"],
        "gap_score": analysis["divergence_score"],
        "supporting_patterns": analysis["supporting_patterns"],
        "observed_steps": analysis["observed_steps"],
        "decisions": analysis["decisions"],
        "irritants": analysis["irritants"],
        "input_artifacts": analysis["input_artifacts"],
        "output_artifacts": analysis["output_artifacts"],
        "business_rules": analysis["business_rules"],
        "recommendations": analysis["recommendations"],
        "examples": [activity.title for activity in session.activities],
        "state": "observed",
        "metadata": {
            "status": "ready_for_validation",
            "origin": "thefabric",
            "process_map_mermaid": analysis["process_map_mermaid"],
            "analysis_report_markdown": _analysis_markdown(session, analysis),
        },
        "created_at": generated_at,
        "validated_at": None,
        "validated_by": None,
        "schema_version": "2.0",
    }

    return {
        "process_analysis": process_analysis,
        "field_observation": field_observation,
    }


def _analysis_markdown(session: DailySession, analysis: Dict[str, Any]) -> str:
    lines = [
        "# TheFabric -> Jean-Marc",
        "",
        "## Processus",
        analysis["process_context"],
        "",
        "## Resume",
        analysis["summary"],
        "",
        "## Etapes observees",
    ]
    for step in analysis["observed_steps"]:
        lines.append("- {0}. {1} [{2}]".format(step["position"], step["label"], step["app"]))

    lines.extend(["", "## Decisions"])
    if analysis["decisions"]:
        for decision in analysis["decisions"]:
            lines.append("- {0}: {1}".format(decision["step_label"], decision["question"]))
    else:
        lines.append("- Aucune decision explicite")

    lines.extend(["", "## Recommandations"])
    for recommendation in analysis["recommendations"]:
        lines.append("- {0}: {1}".format(recommendation["title"], recommendation["description"]))

    lines.extend(["", "## Contexte complementaire", session.additional_context or "_Aucun._"])
    return "\n".join(lines)
