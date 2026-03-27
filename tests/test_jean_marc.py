"""Tests for jean_marc.py — Jean-Marc schema compatibility."""

import pytest
from thefabric.models import DailySession
from thefabric.session_analysis import analyze_session
from thefabric.integrations.jean_marc import (
    build_jean_marc_payload,
    _to_irritants,
    _to_observed_steps,
    _IRRITANT_KIND_MAP,
)


def _make_session_with_activities():
    return DailySession.from_dict({
        "session_id": "jean-marc-test-001",
        "date": "2026-03-27",
        "user_profile": "back-office",
        "goal": "Process invoices",
        "process_context": "finance-invoicing",
        "declared_procedure": "1. Open SAP\n2. Enter invoice\n3. Submit for approval",
        "activities": [
            {
                "title": "Open SAP",
                "app": "SAP",
                "action": "open",
                "start": "2026-03-27T08:00:00",
                "end": "2026-03-27T08:05:00",
                "tags": [],
                "blockers": [],
            },
            {
                "title": "Enter invoice data",
                "app": "SAP",
                "action": "form_fill",
                "start": "2026-03-27T08:05:00",
                "end": "2026-03-27T08:25:00",
                "tags": ["double_entry"],
                "blockers": ["Must also update Excel sheet manually"],
                "inputs": ["Supplier email"],
                "outputs": ["SAP invoice record"],
            },
            {
                "title": "Update tracking sheet",
                "app": "Excel",
                "action": "edit",
                "start": "2026-03-27T08:25:00",
                "end": "2026-03-27T08:40:00",
                "tags": ["double"],
                "inputs": ["SAP invoice record"],
                "outputs": ["Excel tracking entry"],
            },
        ],
    })


class TestBuildJeanMarcPayload:
    def setup_method(self):
        self.session = _make_session_with_activities()
        self.analysis = analyze_session(self.session)
        self.payload = build_jean_marc_payload(self.session, self.analysis)

    def test_has_required_top_level_keys(self):
        assert "process_analysis" in self.payload
        assert "field_observation" in self.payload

    def test_process_analysis_has_uuid_id(self):
        pa = self.payload["process_analysis"]
        import uuid
        # Should be a valid UUID string
        uuid.UUID(pa["id"])  # raises ValueError if not valid

    def test_schema_version_is_2_0(self):
        assert self.payload["process_analysis"]["schema_version"] == "2.0"
        assert self.payload["field_observation"]["schema_version"] == "2.0"

    def test_observed_steps_are_0_based(self):
        steps = self.payload["process_analysis"]["observed_steps"]
        assert len(steps) > 0
        assert steps[0]["order"] == 0   # Jean-Marc is 0-based

    def test_observed_steps_have_jean_marc_fields(self):
        step = self.payload["process_analysis"]["observed_steps"][0]
        required = {"order", "action", "application", "duration_seconds", "irritant_kind"}
        assert required.issubset(step.keys())

    def test_declared_steps_from_declared_procedure(self):
        steps = self.payload["process_analysis"]["declared_steps"]
        # 3 lines in declared_procedure
        assert len(steps) == 3
        assert steps[0]["is_declared"] is True
        assert steps[0]["order"] == 0

    def test_irritants_use_jean_marc_enum_values(self):
        irritants = self.payload["process_analysis"]["irritants"]
        valid_kinds = set(_IRRITANT_KIND_MAP.values())
        for irr in irritants:
            assert irr["kind"] in valid_kinds, (
                f"Irritant kind '{irr['kind']}' not in Jean-Marc IrritantKind enum"
            )

    def test_irritants_have_jean_marc_fields(self):
        irritants = self.payload["process_analysis"]["irritants"]
        if irritants:
            irr = irritants[0]
            required = {"kind", "severity", "description", "estimated_time_loss_seconds"}
            assert required.issubset(irr.keys())

    def test_artifacts_have_jean_marc_format(self):
        artifacts = self.payload["process_analysis"]["artifacts"]
        valid_kinds = {"email", "erp_record", "pdf", "file", "form", "spreadsheet"}
        for art in artifacts:
            assert "name" in art
            assert "kind" in art
            assert "direction" in art
            assert art["direction"] in ("input", "output")

    def test_field_observation_has_jean_marc_fields(self):
        fo = self.payload["field_observation"]
        required = {
            "declared_procedure", "real_procedure_summary",
            "gap_description", "total_irritant_severity", "automatable",
        }
        assert required.issubset(fo.keys())

    def test_total_irritant_severity_is_float(self):
        severity = self.payload["field_observation"]["total_irritant_severity"]
        assert isinstance(severity, float)
        assert severity >= 0.0

    def test_automatable_is_bool(self):
        assert isinstance(self.payload["field_observation"]["automatable"], bool)

    def test_procedure_state_valid_enum_value(self):
        valid = {"declared", "observed", "validated", "automatable"}
        state = self.payload["process_analysis"]["procedure_state"]
        assert state in valid

    def test_gap_description_mentions_divergence(self):
        gap = self.payload["field_observation"]["gap_description"]
        assert "Divergence score" in gap

    def test_recommendations_have_rec_type(self):
        recs = self.payload["process_analysis"]["recommendations"]
        valid_types = {"automate", "simplify", "eliminate", "delegate"}
        for rec in recs:
            assert rec["rec_type"] in valid_types


class TestIrritantTranslation:
    def test_thefabric_context_switch_maps_to_jean_marc(self):
        irritants = [{"kind": "context_switch", "severity": 0.6, "frequency": 2, "impacted_steps": []}]
        result = _to_irritants(irritants)
        assert result[0]["kind"] == "context_switching"

    def test_thefabric_manual_transcription_maps_to_jean_marc(self):
        irritants = [{"kind": "manual_transcription", "severity": 0.78, "frequency": 1, "impacted_steps": []}]
        result = _to_irritants(irritants)
        assert result[0]["kind"] == "manual_entry"

    def test_thefabric_search_maps_to_lookup(self):
        irritants = [{"kind": "search", "severity": 0.5, "frequency": 3, "impacted_steps": []}]
        result = _to_irritants(irritants)
        assert result[0]["kind"] == "lookup"

    def test_estimated_time_loss_scales_with_frequency(self):
        irritants_freq1 = [{"kind": "double_entry", "severity": 0.8, "frequency": 1, "impacted_steps": []}]
        irritants_freq3 = [{"kind": "double_entry", "severity": 0.8, "frequency": 3, "impacted_steps": []}]
        result1 = _to_irritants(irritants_freq1)
        result3 = _to_irritants(irritants_freq3)
        assert result3[0]["estimated_time_loss_seconds"] == result1[0]["estimated_time_loss_seconds"] * 3
