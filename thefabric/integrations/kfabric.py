from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from ..models import DailySession


def build_kfabric_plan(
    session: DailySession,
    analysis: Dict[str, Any],
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    documents_needed = analysis["documents_needed"]
    question = (
        "Quels documents, procedures, modeles, glossaires et politiques faut-il reunir "
        "pour automatiser de facon fiable le processus '{0}' observe dans cette session quotidienne ?"
    ).format(session.process_context)
    query_create = {
        "theme": session.process_context.replace("-", " "),
        "question": question,
        "keywords": analysis["keywords"][:16],
        "language": "fr",
        "period": "24 derniers mois",
        "document_types": [
            "procedure",
            "policy",
            "template",
            "faq",
            "glossary",
            "manual",
        ],
        "preferred_domains": _preferred_domains(session),
        "excluded_domains": [],
        "quality_target": "high_precision",
    }

    plan = {
        "documents_needed": documents_needed,
        "query_create": query_create,
        "api_sequence": [
            "POST /api/v1/queries",
            "POST /api/v1/queries/{query_id}:discover",
            "POST /api/v1/candidates/{candidate_id}:collect",
            "POST /api/v1/documents/{document_id}:analyze",
            "POST /api/v1/fragments:consolidate",
            "POST /api/v1/syntheses",
            "POST /api/v1/queries/{query_id}:build-corpus",
            "POST /api/v1/corpora/{corpus_id}:prepare-index",
        ],
        "notes": [
            "Le corpus doit servir a la qualification, aux validations et aux reponses standard.",
            "Les sources les plus importantes sont celles qui decrivent les statuts CRM, les regles tarifaires, les SLA et les modeles de reponse.",
        ],
    }

    if base_url:
        submission = _submit_query(base_url, query_create, api_key)
        plan["submission"] = submission
    return plan


def _submit_query(base_url: str, payload: Dict[str, Any], api_key: Optional[str]) -> Dict[str, Any]:
    url = base_url.rstrip("/") + "/api/v1/queries"
    request = urllib.request.Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            **({"Authorization": "Bearer {0}".format(api_key)} if api_key else {}),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8")
            return {
                "status": "submitted",
                "url": url,
                "response": json.loads(body) if body else {},
            }
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8")
        return {
            "status": "http_error",
            "url": url,
            "status_code": exc.code,
            "response": payload,
        }
    except Exception as exc:
        return {
            "status": "error",
            "url": url,
            "error": str(exc),
        }


def _preferred_domains(session: DailySession) -> list:
    apps = []
    for activity in session.activities:
        app = activity.app.lower().strip()
        if app == "salesforce":
            apps.append("salesforce.com")
        elif app == "gmail":
            apps.append("support.google.com")
        elif app == "google sheets":
            apps.append("support.google.com")
        elif app == "slack":
            apps.append("slack.com")
    return list(dict.fromkeys(apps))
