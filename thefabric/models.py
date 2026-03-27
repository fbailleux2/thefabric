from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass
class SessionActivity:
    title: str
    app: str
    action: str
    start: str
    end: str
    details: str = ""
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    decisions: List[str] = field(default_factory=list)
    documents_needed: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "SessionActivity":
        return cls(
            title=str(payload.get("title", "")).strip(),
            app=str(payload.get("app", "")).strip(),
            action=str(payload.get("action", "")).strip(),
            start=str(payload.get("start", "")).strip(),
            end=str(payload.get("end", "")).strip(),
            details=str(payload.get("details", "")).strip(),
            inputs=[str(item) for item in payload.get("inputs", [])],
            outputs=[str(item) for item in payload.get("outputs", [])],
            tags=[str(item) for item in payload.get("tags", [])],
            blockers=[str(item) for item in payload.get("blockers", [])],
            notes=[str(item) for item in payload.get("notes", [])],
            decisions=[str(item) for item in payload.get("decisions", [])],
            documents_needed=[str(item) for item in payload.get("documents_needed", [])],
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DailySession:
    session_id: str
    date: str
    user_profile: str
    goal: str
    process_context: str
    declared_procedure: str = ""
    expected_outcomes: List[str] = field(default_factory=list)
    additional_context: str = ""
    activities: List[SessionActivity] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "DailySession":
        activities = [SessionActivity.from_dict(item) for item in payload.get("activities", [])]
        return cls(
            session_id=str(payload.get("session_id", "")).strip(),
            date=str(payload.get("date", "")).strip(),
            user_profile=str(payload.get("user_profile", "")).strip(),
            goal=str(payload.get("goal", "")).strip(),
            process_context=str(payload.get("process_context", "")).strip(),
            declared_procedure=str(payload.get("declared_procedure", "")).strip(),
            expected_outcomes=[str(item) for item in payload.get("expected_outcomes", [])],
            additional_context=str(payload.get("additional_context", "")).strip(),
            activities=activities,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "date": self.date,
            "user_profile": self.user_profile,
            "goal": self.goal,
            "process_context": self.process_context,
            "declared_procedure": self.declared_procedure,
            "expected_outcomes": list(self.expected_outcomes),
            "additional_context": self.additional_context,
            "activities": [activity.to_dict() for activity in self.activities],
        }
