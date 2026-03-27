from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from ..models import DailySession


def build_hermes_payload(
    session: DailySession,
    analysis: Dict[str, Any],
    bundle_resolution: Dict[str, Any],
    kfabric_plan: Dict[str, Any],
    output_dir: Path,
) -> Dict[str, Any]:
    process_slug = _slug(session.process_context)
    skill_name = "thefabric-{0}".format(process_slug)
    skill_dir = output_dir / "hermes" / "skills" / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)

    memory_path = output_dir / "hermes" / "MEMORY.md"
    user_path = output_dir / "hermes" / "USER.md"
    skill_path = skill_dir / "SKILL.md"

    memory_entries = _memory_entries(analysis, bundle_resolution, kfabric_plan)
    user_entries = _user_entries(session, analysis)
    toolsets = _toolsets_for_session(session)
    selected_bundle = bundle_resolution.get("selected_bundle", {})
    selected_bundle_id = selected_bundle.get("bundle_id") or bundle_resolution.get("created_bundle_id", "")

    memory_text = "# MEMORY\n\n" + "\n".join("- " + item for item in memory_entries) + "\n"
    user_text = "# USER\n\n" + "\n".join("- " + item for item in user_entries) + "\n"
    skill_text = _skill_markdown(
        skill_name=skill_name,
        session=session,
        analysis=analysis,
        toolsets=toolsets,
        selected_bundle_id=selected_bundle_id,
        kfabric_plan=kfabric_plan,
    )

    memory_path.write_text(memory_text, encoding="utf-8")
    user_path.write_text(user_text, encoding="utf-8")
    skill_path.write_text(skill_text, encoding="utf-8")

    return {
        "agent_name": "hermes-{0}".format(process_slug),
        "role": "runtime-and-learning-engine",
        "objective": (
            "Executer le workflow quotidien reconstruit par TheFabric, s'appuyer sur le bundle "
            "retenu et mettre a jour la memoire procedurale a chaque execution."
        ),
        "system_prompt": _system_prompt(session, analysis, selected_bundle_id),
        "suggested_toolsets": toolsets,
        "memory_entries": memory_entries,
        "user_entries": user_entries,
        "skill": {
            "name": skill_name,
            "path": str(skill_path),
        },
        "bundle_binding": selected_bundle_id,
        "kfabric_dependencies": kfabric_plan.get("documents_needed", []),
        "learning_protocol": {
            "record_after_each_run": [
                "decisions prises",
                "documents consultes",
                "ecarts entre resultat attendu et obtenu",
                "nouveaux cas clients et exceptions",
            ],
            "promote_to_memory_when": [
                "une decision revient au moins 3 fois",
                "une reponse ou une synthese fonctionne sur plusieurs cas",
                "une nouvelle source documentaire devient recurrente",
            ],
            "update_skill_when": [
                "la sequence d'actions stable change",
                "un nouveau garde-fou metier apparait",
                "un bundle different devient meilleur sur le meme contexte",
            ],
        },
        "artifacts": {
            "memory_md": str(memory_path),
            "user_md": str(user_path),
            "skill_md": str(skill_path),
        },
    }


def _memory_entries(
    analysis: Dict[str, Any],
    bundle_resolution: Dict[str, Any],
    kfabric_plan: Dict[str, Any],
) -> List[str]:
    entries = [
        "Process context: {0}".format(analysis["process_context"]),
        "Workflow summary: {0}".format(analysis["summary"]),
    ]
    if analysis["decisions"]:
        entries.append(
            "Decision points to remember: {0}".format(
                "; ".join(item["question"] for item in analysis["decisions"][:4])
            )
        )
    if analysis["irritants"]:
        entries.append(
            "Main irritants to reduce: {0}".format(
                "; ".join(item["title"] for item in analysis["irritants"][:4])
            )
        )
    selected_bundle = bundle_resolution.get("selected_bundle")
    if selected_bundle:
        entries.append("Preferred bundle: {0}".format(selected_bundle["bundle_id"]))
    if bundle_resolution.get("created_bundle_id"):
        entries.append("Bundle created by TheFabric: {0}".format(bundle_resolution["created_bundle_id"]))
    if kfabric_plan.get("documents_needed"):
        entries.append(
            "Knowledge gaps to fill via KFabric: {0}".format(
                "; ".join(kfabric_plan["documents_needed"][:6])
            )
        )
    return entries


def _user_entries(session: DailySession, analysis: Dict[str, Any]) -> List[str]:
    entries = [
        "User profile: {0}".format(session.user_profile),
        "Daily objective: {0}".format(session.goal),
    ]
    if session.expected_outcomes:
        entries.append("Expected outcomes: {0}".format("; ".join(session.expected_outcomes)))
    if analysis["apps_used"]:
        entries.append("Main tools used: {0}".format(", ".join(analysis["apps_used"])))
    return entries


def _toolsets_for_session(session: DailySession) -> List[str]:
    toolsets = ["memory", "session_search", "file", "process", "code_execution", "delegate", "cronjob"]
    app_names = " ".join(activity.app.lower() for activity in session.activities)
    if "gmail" in app_names or "outlook" in app_names:
        toolsets.append("send_message")
    if "slack" in app_names or "teams" in app_names:
        toolsets.append("send_message")
    toolsets.append("web")
    return list(dict.fromkeys(toolsets))


def _skill_markdown(
    skill_name: str,
    session: DailySession,
    analysis: Dict[str, Any],
    toolsets: List[str],
    selected_bundle_id: str,
    kfabric_plan: Dict[str, Any],
) -> str:
    tags = ", ".join(
        "'{0}'".format(tag)
        for tag in list(dict.fromkeys(["TheFabric", "automation"] + analysis["apps_used"][:4]))
    )
    lines = [
        "---",
        "name: {0}".format(skill_name),
        "description: Executer et faire apprendre Hermes sur le processus {0}.".format(session.process_context),
        "version: 1.0.0",
        "author: TheFabric",
        "license: MIT",
        "metadata:",
        "  hermes:",
        "    tags: [{0}]".format(tags),
        "---",
        "",
        "# TheFabric Hermes Operator",
        "",
        "## Mission",
        "",
        "Utiliser Hermes comme moteur d'execution et d'apprentissage pour le processus observe.",
        "Hermes doit reprendre le workflow logique defini par TheFabric, exploiter le bundle courant,",
        "consulter le corpus KFabric et transformer chaque execution reussie en memoire reutilisable.",
        "",
        "## Quand l'utiliser",
        "",
        "- Quand une session ressemble au processus `{0}`.".format(session.process_context),
        "- Quand il faut rejouer une sequence quotidienne avec decisions recurrentes.",
        "- Quand il faut capitaliser les validations, reponses et exceptions observees.",
        "",
        "## Workflow cible",
        "",
    ]
    for step in analysis["observed_steps"]:
        lines.append(
            "- {0}. {1} [{2}]".format(step["position"], step["label"], step["app"] or "tool")
        )

    lines.extend(
        [
            "",
            "## Regles d'execution",
            "",
            "1. Charger la memoire TheFabric avant de repondre.",
            "2. Consulter les documents KFabric quand une decision depend d'une regle metier.",
            "3. Utiliser le bundle `{0}` en priorite.".format(selected_bundle_id or "a determiner"),
            "4. Journaliser les decisions prises, les cas rejectes et les exceptions.",
            "5. Promouvoir en memoire uniquement les faits repetes ou valides.",
            "",
            "## Toolsets suggeres",
            "",
            "- {0}".format(", ".join(toolsets)),
            "",
            "## Cibles d'apprentissage",
            "",
        ]
    )
    for target in analysis["learning_targets"]:
        lines.append("- {0}: {1}".format(target["type"], target["label"]))

    lines.extend(
        [
            "",
            "## Corpus et connaissances",
            "",
            "- Documents a rechercher: {0}".format(
                ", ".join(kfabric_plan.get("documents_needed", [])[:8]) or "a completer"
            ),
            "- Question KFabric: {0}".format(kfabric_plan.get("query_create", {}).get("question", "")),
            "",
            "## Garde-fous",
            "",
            "- Ne jamais inventer une regle commerciale absente du corpus ou de la memoire validee.",
            "- Escalader les cas hors politique tarifaire ou hors procedure.",
            "- Si plusieurs sources se contredisent, preferer la plus recente et garder une trace du doute.",
        ]
    )
    return "\n".join(lines) + "\n"


def _system_prompt(session: DailySession, analysis: Dict[str, Any], selected_bundle_id: str) -> str:
    return (
        "You are Hermes inside TheFabric. Your job is to execute the daily process "
        "'{0}' for {1}. Use bundle '{2}' when relevant, consult the KFabric corpus "
        "before making business decisions, and update memory only with repeated or "
        "validated facts. Main irritants to reduce: {3}."
    ).format(
        session.process_context,
        session.user_profile or "a generic office user",
        selected_bundle_id or "pending-bundle-selection",
        ", ".join(item["title"] for item in analysis["irritants"][:3]) or "none provided",
    )


def _slug(value: str) -> str:
    return "-".join(part for part in "".join(ch.lower() if ch.isalnum() else "-" for ch in value).split("-") if part)
