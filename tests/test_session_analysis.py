"""Tests for session_analysis.py — core analysis engine."""

import pytest
from thefabric.models import DailySession, SessionActivity
from thefabric.session_analysis import (
    analyze_session,
    _build_irritants,
    _extract_keywords,
    _coverage_score,
    _divergence_score,
)


def _make_session(**kwargs) -> DailySession:
    defaults = {
        "session_id": "test-session-001",
        "date": "2026-03-27",
        "user_profile": "back-office commercial",
        "goal": "Process daily client requests",
        "process_context": "back-office-commercial",
        "declared_procedure": "1. Check emails\n2. Update CRM\n3. Send responses",
        "activities": [],
    }
    defaults.update(kwargs)
    return DailySession.from_dict(defaults)


def _make_activity(**kwargs) -> dict:
    defaults = {
        "title": "Check emails",
        "app": "Gmail",
        "action": "read",
        "start": "2026-03-27T08:55:00",
        "end": "2026-03-27T09:20:00",
    }
    defaults.update(kwargs)
    return defaults


class TestAnalyzeSession:
    def test_empty_session_runs_without_error(self):
        session = _make_session()
        result = analyze_session(session)
        assert result["process_context"] == "back-office-commercial"
        assert result["observed_steps"] == []
        assert result["irritants"] == []
        assert result["keywords"]  # should have some from goal/process_context

    def test_single_activity_produces_one_step(self):
        session = _make_session(activities=[_make_activity()])
        result = analyze_session(session)
        assert len(result["observed_steps"]) == 1
        assert result["observed_steps"][0]["app"] == "Gmail"
        assert result["observed_steps"][0]["position"] == 1

    def test_double_entry_irritant_detected(self):
        activities = [
            _make_activity(
                title="Enter data in CRM",
                app="Salesforce",
                details="copy-paste from email",
                tags=["double_entry"],
            ),
            _make_activity(
                title="Enter same data in spreadsheet",
                app="Google Sheets",
                tags=["double"],
            ),
        ]
        session = _make_session(activities=activities)
        result = analyze_session(session)
        kinds = {irr["kind"] for irr in result["irritants"]}
        assert "double_entry" in kinds

    def test_context_switch_irritant_detected(self):
        activities = [
            _make_activity(app="Gmail", tags=["switch"]),
            _make_activity(app="Salesforce", tags=["switch"]),
            _make_activity(app="Google Sheets", tags=["switch"]),
        ]
        session = _make_session(activities=activities)
        result = analyze_session(session)
        kinds = {irr["kind"] for irr in result["irritants"]}
        assert "context_switch" in kinds

    def test_apps_used_sorted(self):
        activities = [
            _make_activity(app="Salesforce"),
            _make_activity(app="Gmail"),
            _make_activity(app="Gmail"),
        ]
        session = _make_session(activities=activities)
        result = analyze_session(session)
        assert sorted(result["apps_used"]) == result["apps_used"]

    def test_mermaid_generated(self):
        activities = [_make_activity(), _make_activity(title="Update CRM", app="Salesforce")]
        session = _make_session(activities=activities)
        result = analyze_session(session)
        assert result["process_map_mermaid"].startswith("flowchart TD")
        assert "s1 --> s2" in result["process_map_mermaid"]

    def test_summary_is_non_empty_string(self):
        session = _make_session(activities=[_make_activity()])
        result = analyze_session(session)
        assert isinstance(result["summary"], str)
        assert len(result["summary"]) > 10

    def test_decision_detected_from_explicit_list(self):
        activities = [
            _make_activity(
                title="Apply discount",
                app="Salesforce",
                decisions=["Grant 10% discount for orders > 500€"],
            )
        ]
        session = _make_session(activities=activities)
        result = analyze_session(session)
        assert len(result["decisions"]) >= 1
        assert "Grant 10%" in result["decisions"][0]["question"]

    def test_documents_collected(self):
        activities = [
            _make_activity(
                title="Look up pricing",
                app="SharePoint",
                documents_needed=["Pricing policy 2026", "Discount approval form"],
            )
        ]
        session = _make_session(activities=activities)
        result = analyze_session(session)
        assert "Pricing policy 2026" in result["documents_needed"]

    def test_coverage_score_increases_with_artifacts(self):
        base = _make_session(activities=[_make_activity()])
        with_artifacts = _make_session(
            activities=[_make_activity(inputs=["email"], outputs=["crm_record"])]
        )
        base_result = analyze_session(base)
        artifact_result = analyze_session(with_artifacts)
        assert artifact_result["coverage_score"] >= base_result["coverage_score"]

    def test_divergence_score_increases_with_irritants(self):
        low_session = _make_session(activities=[_make_activity()])
        high_session = _make_session(
            activities=[
                _make_activity(
                    blockers=["Manual copy", "Context lost"],
                    tags=["double_entry", "switch"],
                )
            ]
        )
        low_result = analyze_session(low_session)
        high_result = analyze_session(high_session)
        assert high_result["divergence_score"] >= low_result["divergence_score"]


class TestKeywordExtraction:
    def test_stopwords_excluded(self):
        session = _make_session(goal="traiter les demandes des clients")
        result = analyze_session(session)
        assert "les" not in result["keywords"]
        assert "des" not in result["keywords"]

    def test_domain_terms_included(self):
        session = _make_session(
            goal="process invoices and update ERP",
            process_context="finance-invoicing",
        )
        result = analyze_session(session)
        # At least one of the domain terms should appear
        assert any(kw in result["keywords"] for kw in ["invoices", "invoice", "finance", "erp", "update"])


class TestCoverageScore:
    def test_empty_activities(self):
        assert _coverage_score([]) == 0.0

    def test_score_bounded(self):
        from thefabric.models import SessionActivity
        from dataclasses import fields
        acts = [
            SessionActivity(
                title="step",
                app="App",
                action="read",
                start="2026-01-01T08:00:00",
                end="2026-01-01T09:00:00",
                inputs=["doc"],
                outputs=["record"],
            )
        ]
        score = _coverage_score(acts)
        assert 0.0 <= score <= 1.0
