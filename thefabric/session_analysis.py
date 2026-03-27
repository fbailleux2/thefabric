from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Dict, Iterable, List, Tuple

from .models import DailySession, SessionActivity

STOPWORDS = {
    "a",
    "au",
    "aux",
    "avec",
    "ce",
    "ces",
    "dans",
    "de",
    "des",
    "du",
    "elle",
    "elles",
    "en",
    "et",
    "for",
    "il",
    "ils",
    "je",
    "la",
    "le",
    "les",
    "leur",
    "leurs",
    "mais",
    "mes",
    "mon",
    "nos",
    "notre",
    "ou",
    "par",
    "pas",
    "plus",
    "pour",
    "que",
    "qui",
    "sans",
    "ses",
    "sur",
    "the",
    "this",
    "to",
    "une",
    "user",
    "utilisateur",
    "with",
    "work",
}


def analyze_session(session: DailySession) -> Dict[str, Any]:
    activities = session.activities
    step_rows = [_build_step(index, activity) for index, activity in enumerate(activities, start=1)]
    decisions = _build_decisions(activities)
    irritants = _build_irritants(activities)
    input_artifacts, output_artifacts = _build_artifacts(activities)
    business_rules = _build_business_rules(activities)
    keywords = _extract_keywords(session, activities)
    repeated_apps = Counter(activity.app for activity in activities if activity.app)
    apps_used = sorted(repeated_apps)
    documents_needed = _collect_documents(activities)
    supporting_patterns = _build_patterns(activities)
    recommendations = _build_recommendations(session, step_rows, irritants, decisions, repeated_apps)
    automation_candidates = _build_automation_candidates(step_rows, irritants, decisions)
    coverage_score = _coverage_score(activities)
    divergence_score = _divergence_score(irritants, activities)
    summary = _build_summary(session, apps_used, irritants, decisions, recommendations)
    learning_targets = _build_learning_targets(decisions, irritants, documents_needed)

    return {
        "process_context": session.process_context,
        "session_id": session.session_id,
        "date": session.date,
        "user_profile": session.user_profile,
        "goal": session.goal,
        "declared_procedure": session.declared_procedure,
        "expected_outcomes": list(session.expected_outcomes),
        "apps_used": apps_used,
        "keywords": keywords,
        "observed_steps": step_rows,
        "decisions": decisions,
        "irritants": irritants,
        "input_artifacts": input_artifacts,
        "output_artifacts": output_artifacts,
        "business_rules": business_rules,
        "recommendations": recommendations,
        "automation_candidates": automation_candidates,
        "documents_needed": documents_needed,
        "supporting_patterns": supporting_patterns,
        "coverage_score": coverage_score,
        "divergence_score": divergence_score,
        "summary": summary,
        "learning_targets": learning_targets,
        "process_map_mermaid": _build_mermaid(step_rows),
    }


def _build_step(position: int, activity: SessionActivity) -> Dict[str, Any]:
    duration = _duration_seconds(activity.start, activity.end)
    label = activity.title or "{0} via {1}".format(activity.action or "work", activity.app or "app")
    notes = []
    if activity.details:
        notes.append(activity.details)
    notes.extend(activity.notes)
    if activity.blockers:
        notes.append("Blocages: " + "; ".join(activity.blockers))
    return {
        "id": "step-{0}".format(position),
        "position": position,
        "label": label,
        "app": activity.app,
        "event_types": [_map_event_type(activity.action, activity.tags)],
        "frequency": 1,
        "average_duration_seconds": duration,
        "source_trace_ids": [],
        "notes": notes,
    }


def _build_decisions(activities: List[SessionActivity]) -> List[Dict[str, Any]]:
    rows = []
    for index, activity in enumerate(activities, start=1):
        explicit_decisions = [item for item in activity.decisions if item]
        has_decision_signal = any(
            token in _activity_text(activity)
            for token in ("approve", "approval", "validation", "decider", "choisir", "triage")
        )
        if not explicit_decisions and not has_decision_signal:
            continue

        if not explicit_decisions:
            explicit_decisions = [
                "Determiner l'action correcte a l'issue de l'etape {0}".format(index)
            ]

        rows.append(
            {
                "id": "decision-{0}".format(index),
                "step_label": activity.title,
                "question": explicit_decisions[0],
                "rules": [
                    {
                        "id": "rule-decision-{0}".format(index),
                        "condition": "Contexte de l'etape {0}".format(activity.title),
                        "outcome": explicit_decisions[0],
                        "rationale": "Decision detectee dans la session observee.",
                        "confidence": 0.7,
                        "source": activity.app,
                        "examples": explicit_decisions[1:],
                    }
                ],
                "signals": list(dict.fromkeys(activity.tags + activity.blockers)),
                "frequency": 1,
            }
        )
    return rows


def _build_irritants(activities: List[SessionActivity]) -> List[Dict[str, Any]]:
    grouped = defaultdict(list)
    definitions = [
        (
            "double_entry",
            "Double saisie",
            ("double", "copier-coller", "copy", "double_entry"),
            0.82,
        ),
        (
            "context_switch",
            "Changements de contexte",
            ("switch", "plusieurs outils", "threads", "context"),
            0.63,
        ),
        (
            "search",
            "Recherche de contexte",
            ("search", "rechercher", "historique", "glossaire", "look up"),
            0.66,
        ),
        (
            "waiting",
            "Attente de validation",
            ("waiting", "attente", "validation", "approval"),
            0.7,
        ),
        (
            "manual_transcription",
            "Transcription manuelle",
            ("retapees", "manual", "transcription", "saisie"),
            0.78,
        ),
        (
            "rework",
            "Reprise et corrections",
            ("corriger", "correction", "retry", "rework"),
            0.55,
        ),
    ]

    for activity in activities:
        haystack = _activity_text(activity)
        for kind, title, needles, severity in definitions:
            if any(needle in haystack for needle in needles):
                grouped[kind].append((activity, title, severity))

    irritants = []
    for index, (kind, items) in enumerate(sorted(grouped.items()), start=1):
        impacted_steps = [item[0].title for item in items]
        evidence = []
        for activity, _title, _severity in items:
            evidence.extend(activity.blockers or activity.notes or [activity.details])
        irritants.append(
            {
                "id": "irritant-{0}".format(index),
                "kind": kind,
                "title": items[0][1],
                "description": "Irritant reconstruit a partir des activites observees.",
                "frequency": len(items),
                "severity": items[0][2],
                "evidence": [item for item in evidence if item],
                "impacted_steps": list(dict.fromkeys(impacted_steps)),
            }
        )
    return irritants


def _build_artifacts(activities: List[SessionActivity]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    input_artifacts = []
    output_artifacts = []
    seen_inputs = set()
    seen_outputs = set()

    for activity in activities:
        for name in activity.inputs:
            key = (name.lower(), "input")
            if key in seen_inputs:
                continue
            seen_inputs.add(key)
            input_artifacts.append(
                {
                    "id": "input-{0}".format(len(input_artifacts) + 1),
                    "name": name,
                    "kind": _artifact_kind(name),
                    "direction": "input",
                    "source": activity.app,
                    "description": "Artefact consomme pendant l'etape '{0}'.".format(activity.title),
                    "examples": [],
                }
            )

        for name in activity.outputs:
            key = (name.lower(), "output")
            if key in seen_outputs:
                continue
            seen_outputs.add(key)
            output_artifacts.append(
                {
                    "id": "output-{0}".format(len(output_artifacts) + 1),
                    "name": name,
                    "kind": _artifact_kind(name),
                    "direction": "output",
                    "source": activity.app,
                    "description": "Artefact produit pendant l'etape '{0}'.".format(activity.title),
                    "examples": [],
                }
            )
    return input_artifacts, output_artifacts


def _build_business_rules(activities: List[SessionActivity]) -> List[Dict[str, Any]]:
    rows = []
    for index, activity in enumerate(activities, start=1):
        for decision in activity.decisions:
            rows.append(
                {
                    "id": "business-rule-{0}".format(len(rows) + 1),
                    "condition": "Si l'etape '{0}' rencontre un cas particulier".format(activity.title),
                    "outcome": decision,
                    "rationale": "Regle inferee depuis une decision utilisateur explicite.",
                    "confidence": 0.6,
                    "source": activity.app,
                    "examples": activity.notes[:2],
                }
            )

        if any(tag in activity.tags for tag in ("approval", "validation")):
            rows.append(
                {
                    "id": "business-rule-{0}".format(len(rows) + 1),
                    "condition": "Si la demande sort du cadre standard",
                    "outcome": "Soumettre une demande de validation avant l'envoi.",
                    "rationale": "Signal d'approbation detecte.",
                    "confidence": 0.72,
                    "source": activity.app,
                    "examples": activity.blockers[:2],
                }
            )
    return rows


def _build_recommendations(
    session: DailySession,
    step_rows: List[Dict[str, Any]],
    irritants: List[Dict[str, Any]],
    decisions: List[Dict[str, Any]],
    repeated_apps: Counter,
) -> List[Dict[str, Any]]:
    recommendations = []
    high_repeat_apps = [app for app, count in repeated_apps.items() if count >= 2]
    if high_repeat_apps:
        recommendations.append(
            {
                "id": "recommendation-1",
                "title": "Automatiser le noyau repetitif du parcours",
                "description": "Cibler d'abord les etapes qui reviennent sur {0}.".format(", ".join(high_repeat_apps)),
                "rationale": "Les applications les plus frequentes offrent le meilleur levier d'automatisation.",
                "automation_potential": 0.84,
                "impacted_steps": [row["label"] for row in step_rows if row["app"] in high_repeat_apps],
                "related_irritants": [item["id"] for item in irritants],
            }
        )

    if decisions:
        recommendations.append(
            {
                "id": "recommendation-{0}".format(len(recommendations) + 1),
                "title": "Confier les syntheses et validations a Hermes",
                "description": "Hermes doit preparer les messages, appliquer la memoisation des cas, puis apprendre des validations recues.",
                "rationale": "Les decisions repetitives sont un bon point d'ancrage pour la memoire procedurale Hermes.",
                "automation_potential": 0.79,
                "impacted_steps": [item["step_label"] for item in decisions],
                "related_irritants": [],
            }
        )

    recommendations.append(
        {
            "id": "recommendation-{0}".format(len(recommendations) + 1),
            "title": "Publier un bundle specialise pour ce processus",
            "description": "Associer le workflow PySpur, la skill Hermes et les besoins documentaires dans un bundle reutilisable.",
            "rationale": "Un bundle permet de capitaliser et de reemployer l'automatisation sur des sessions similaires.",
            "automation_potential": 0.75,
            "impacted_steps": [row["label"] for row in step_rows],
            "related_irritants": [item["id"] for item in irritants[:2]],
        }
    )

    recommendations.append(
        {
            "id": "recommendation-{0}".format(len(recommendations) + 1),
            "title": "Construire un corpus KFabric avant execution",
            "description": "Rechercher les procedures, modeles, politiques et glossaires qui reduisent les erreurs de qualification et d'envoi.",
            "rationale": "La qualite du corpus conditionne la fiabilite des agents et du bundle.",
            "automation_potential": 0.71,
            "impacted_steps": [row["label"] for row in step_rows],
            "related_irritants": [item["id"] for item in irritants if item["kind"] in ("search", "manual_transcription")],
        }
    )

    return recommendations


def _build_automation_candidates(
    step_rows: List[Dict[str, Any]],
    irritants: List[Dict[str, Any]],
    decisions: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    decision_steps = {item["step_label"] for item in decisions}
    impacted_steps = set()
    for irritant in irritants:
        impacted_steps.update(irritant["impacted_steps"])

    candidates = []
    for row in step_rows:
        duration = row.get("average_duration_seconds") or 0
        score = 0.4
        if row["label"] in impacted_steps:
            score += 0.25
        if row["label"] in decision_steps:
            score += 0.2
        if duration >= 1200:
            score += 0.15
        candidates.append(
            {
                "step_id": row["id"],
                "step_label": row["label"],
                "app": row["app"],
                "automation_score": round(min(score, 0.95), 2),
                "why": "Etape analysee pour son repetition, sa duree et les irritants associes.",
            }
        )
    candidates.sort(key=lambda item: item["automation_score"], reverse=True)
    return candidates


def _build_patterns(activities: List[SessionActivity]) -> List[str]:
    if len(activities) < 2:
        return []
    sequence_counts = Counter()
    for left, right in zip(activities, activities[1:]):
        sequence_counts["{0} -> {1}".format(left.app or left.title, right.app or right.title)] += 1
    return [
        "{0} (x{1})".format(pattern, count)
        for pattern, count in sequence_counts.most_common(5)
    ]


def _build_learning_targets(
    decisions: List[Dict[str, Any]],
    irritants: List[Dict[str, Any]],
    documents_needed: List[str],
) -> List[Dict[str, Any]]:
    rows = []
    for item in decisions:
        rows.append(
            {
                "type": "decision_memory",
                "label": item["step_label"],
                "capture": item["question"],
            }
        )
    for item in irritants:
        rows.append(
            {
                "type": "friction_signal",
                "label": item["title"],
                "capture": ", ".join(item["impacted_steps"]),
            }
        )
    for document in documents_needed[:5]:
        rows.append(
            {
                "type": "knowledge_gap",
                "label": document,
                "capture": "Document a rechercher ou consolider dans KFabric.",
            }
        )
    return rows


def _collect_documents(activities: List[SessionActivity]) -> List[str]:
    rows = []
    for activity in activities:
        rows.extend(activity.documents_needed)
    return list(dict.fromkeys(item for item in rows if item))


def _extract_keywords(session: DailySession, activities: Iterable[SessionActivity]) -> List[str]:
    tokens = []
    tokens.extend(_tokenize(session.goal))
    tokens.extend(_tokenize(session.process_context))
    tokens.extend(_tokenize(session.user_profile))
    for activity in activities:
        tokens.extend(_tokenize(activity.title))
        tokens.extend(_tokenize(activity.app))
        tokens.extend(_tokenize(activity.action))
        for tag in activity.tags:
            tokens.extend(_tokenize(tag))
        for document in activity.documents_needed:
            tokens.extend(_tokenize(document))
    counts = Counter(token for token in tokens if token not in STOPWORDS and len(token) > 2)
    return [token for token, _count in counts.most_common(16)]


def _coverage_score(activities: List[SessionActivity]) -> float:
    if not activities:
        return 0.0
    with_outputs = sum(1 for activity in activities if activity.outputs)
    with_inputs = sum(1 for activity in activities if activity.inputs)
    raw = 0.45 + (with_outputs / float(len(activities))) * 0.3 + (with_inputs / float(len(activities))) * 0.2
    return round(min(raw, 0.97), 2)


def _divergence_score(irritants: List[Dict[str, Any]], activities: List[SessionActivity]) -> float:
    if not activities:
        return 0.0
    blocker_count = sum(len(activity.blockers) for activity in activities)
    raw = (len(irritants) * 0.12) + (blocker_count * 0.04)
    return round(min(max(raw, 0.12), 0.95), 2)


def _build_summary(
    session: DailySession,
    apps_used: List[str],
    irritants: List[Dict[str, Any]],
    decisions: List[Dict[str, Any]],
    recommendations: List[Dict[str, Any]],
) -> str:
    return (
        "Session quotidienne '{0}' pour {1}. "
        "Le processus observe traverse {2}. "
        "Les principaux points de friction sont {3}. "
        "{4} decision(s) recurrente(s) ont ete detectee(s). "
        "Les prochaines actions recommandees sont : {5}."
    ).format(
        session.process_context,
        session.user_profile or "un utilisateur",
        ", ".join(apps_used) if apps_used else "des outils non renseignes",
        ", ".join(item["title"] for item in irritants[:3]) if irritants else "peu d'irritants explicites",
        len(decisions),
        ", ".join(item["title"] for item in recommendations[:3]),
    )


def _build_mermaid(step_rows: List[Dict[str, Any]]) -> str:
    if not step_rows:
        return "flowchart TD\n  start([Aucune etape observee])"
    lines = ["flowchart TD"]
    for index, row in enumerate(step_rows, start=1):
        label = "{0}. {1}".format(index, row["label"]).replace('"', "'")
        lines.append('  s{0}["{1}"]'.format(index, label))
        if index > 1:
            lines.append("  s{0} --> s{1}".format(index - 1, index))
    return "\n".join(lines)


def _activity_text(activity: SessionActivity) -> str:
    parts = [activity.title, activity.details, activity.app, activity.action]
    parts.extend(activity.tags)
    parts.extend(activity.blockers)
    parts.extend(activity.notes)
    parts.extend(activity.decisions)
    return " ".join(part.lower() for part in parts if part)


def _artifact_kind(name: str) -> str:
    lower = name.lower()
    if "email" in lower or "mail" in lower:
        return "email"
    if "crm" in lower or "record" in lower or "fiche" in lower:
        return "erp_record"
    if "pdf" in lower:
        return "pdf"
    if "tableau" in lower or "sheet" in lower or "excel" in lower:
        return "file"
    if "message" in lower or "slack" in lower:
        return "message"
    if "form" in lower:
        return "form"
    return "generic"


def _map_event_type(action: str, tags: List[str]) -> str:
    lower = (action or "").lower()
    tagset = {tag.lower() for tag in tags}
    if lower in ("save", "edit", "update"):
        return "save"
    if lower in ("submit", "send"):
        return "submit"
    if lower in ("export", "download"):
        return "export"
    if "annotation" in tagset:
        return "annotation"
    return "custom"


def _duration_seconds(start: str, end: str) -> float:
    try:
        started_at = datetime.fromisoformat(start)
        ended_at = datetime.fromisoformat(end)
        return round(max((ended_at - started_at).total_seconds(), 0), 1)
    except Exception:
        return 0.0


def _tokenize(value: str) -> List[str]:
    return re.findall(r"[a-zA-Z0-9][a-zA-Z0-9_-]{1,}", value.lower())
