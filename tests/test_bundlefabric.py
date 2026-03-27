"""Tests for bundlefabric.py — bundle scoring and TPS key compatibility."""

import json
import tempfile
from pathlib import Path

import pytest
from thefabric.integrations.bundlefabric import (
    _tps_score,
    _recency_score,
    _score_bundle,
    resolve_bundle,
    _load_manifests,
    _dump_simple_yaml,
    _parse_simple_yaml,
)


def _write_manifest(bundle_dir: Path, manifest: dict) -> None:
    bundle_dir.mkdir(parents=True, exist_ok=True)
    yaml_text = _dump_simple_yaml(manifest)
    (bundle_dir / "manifest.yaml").write_text(yaml_text, encoding="utf-8")


class TestTpsScore:
    def test_reads_freshness_key(self):
        """Real BundleFabric manifests use 'freshness', not 'freshness_score'."""
        manifest = {"temporal": {"freshness": 0.8, "usage_frequency": 0.6, "ecosystem_alignment": 0.7}}
        score = _tps_score(manifest)
        expected = round(0.8 * 0.4 + 0.6 * 0.3 + 0.7 * 0.3, 4)
        assert score == expected

    def test_reads_freshness_score_key_as_fallback(self):
        """TheFabric-created bundles may use 'freshness_score'."""
        manifest = {"temporal": {"freshness_score": 0.85, "usage_frequency": 0.5, "ecosystem_alignment": 0.82}}
        score = _tps_score(manifest)
        expected = round(0.85 * 0.4 + 0.5 * 0.3 + 0.82 * 0.3, 4)
        assert score == expected

    def test_defaults_to_0_5_when_missing(self):
        score = _tps_score({})
        expected = round(0.5 * 0.4 + 0.5 * 0.3 + 0.5 * 0.3, 4)
        assert score == expected

    def test_score_bounded_0_to_1(self):
        for freshness in (0.0, 0.5, 1.0):
            manifest = {"temporal": {"freshness": freshness, "usage_frequency": freshness, "ecosystem_alignment": freshness}}
            score = _tps_score(manifest)
            assert 0.0 <= score <= 1.0


class TestRecencyScore:
    def test_reads_updated_at_key(self):
        """Real BundleFabric manifests use 'updated_at' at root level."""
        manifest = {"updated_at": "2026-03-01", "temporal": {}}
        score = _recency_score(manifest)
        assert 0.1 <= score <= 1.0

    def test_reads_last_updated_key(self):
        """TheFabric-created bundles use temporal.last_updated."""
        manifest = {"temporal": {"last_updated": "2026-03-01"}}
        score = _recency_score(manifest)
        assert 0.1 <= score <= 1.0

    def test_defaults_to_0_5_when_missing(self):
        assert _recency_score({}) == 0.5

    def test_recent_bundle_scores_near_1(self):
        from datetime import datetime, timedelta
        recent = (datetime.utcnow() - timedelta(days=10)).strftime("%Y-%m-%d")
        manifest = {"temporal": {"last_updated": recent}}
        score = _recency_score(manifest)
        assert score > 0.9


class TestYamlRoundtrip:
    def test_simple_scalars(self):
        data = {"id": "test-bundle", "version": "1.0.0", "active": True, "count": 42}
        assert _parse_simple_yaml(_dump_simple_yaml(data)) == data

    def test_list_values(self):
        data = {"keywords": ["crm", "salesforce", "automation"]}
        parsed = _parse_simple_yaml(_dump_simple_yaml(data))
        assert parsed["keywords"] == ["crm", "salesforce", "automation"]

    def test_nested_dict(self):
        data = {"temporal": {"freshness": 0.85, "usage_frequency": 0.5}}
        yaml_text = _dump_simple_yaml(data)
        parsed = _parse_simple_yaml(yaml_text)
        assert parsed["temporal"]["freshness"] == 0.85
        assert parsed["temporal"]["usage_frequency"] == 0.5


class TestBundleScoring:
    def test_high_overlap_scores_higher(self):
        analysis_high = {
            "keywords": ["crm", "salesforce", "automation"],
            "apps_used": ["Salesforce"],
            "recommendations": [],
        }
        analysis_low = {
            "keywords": ["finance", "invoice", "erp"],
            "apps_used": ["SAP"],
            "recommendations": [],
        }
        manifest = {
            "id": "bundle-crm",
            "name": "CRM Automation",
            "keywords": ["crm", "salesforce"],
            "domains": ["crm"],
            "capabilities": ["automation"],
            "temporal": {"freshness": 0.85, "usage_frequency": 0.75, "ecosystem_alignment": 0.88},
            "updated_at": "2026-03-17",
        }
        score_high, _, _, _ = _score_bundle(analysis_high, manifest)
        score_low, _, _, _ = _score_bundle(analysis_low, manifest)
        assert score_high > score_low

    def test_matched_keywords_returned(self):
        analysis = {
            "keywords": ["crm", "salesforce"],
            "apps_used": [],
            "recommendations": [],
        }
        manifest = {
            "id": "bundle-crm",
            "name": "CRM Expert",
            "keywords": ["crm", "salesforce", "hubspot"],
            "domains": [],
            "capabilities": [],
            "temporal": {},
        }
        _, _, matched, _ = _score_bundle(analysis, manifest)
        assert "crm" in matched
        assert "salesforce" in matched


class TestResolveBundle:
    def test_creates_bundle_when_dir_empty(self):
        from thefabric.models import DailySession
        session = DailySession.from_dict({
            "session_id": "test-001",
            "date": "2026-03-27",
            "user_profile": "user",
            "goal": "Test",
            "process_context": "test-process",
            "activities": [],
        })
        analysis = {
            "keywords": ["test"],
            "apps_used": [],
            "recommendations": [{"title": "Automatiser", "description": "desc", "automation_potential": 0.8}],
            "irritants": [],
            "process_context": "test-process",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            bundles_dir = Path(tmpdir) / "bundles"
            bundles_dir.mkdir()
            output_dir = Path(tmpdir) / "output"
            result = resolve_bundle(session, analysis, bundles_dir, output_dir)
            assert result["created_bundle_id"] is not None
            assert result["selected_bundle"]["score"] == 1.0

    def test_finds_existing_bundle_above_threshold(self):
        from thefabric.models import DailySession
        session = DailySession.from_dict({
            "session_id": "test-002",
            "date": "2026-03-27",
            "user_profile": "user",
            "goal": "GTM debugging",
            "process_context": "gtm-debug",
            "activities": [],
        })
        analysis = {
            "keywords": ["gtm", "analytics", "debug", "ga4"],
            "apps_used": ["Chrome DevTools"],
            "recommendations": [],
            "irritants": [],
            "process_context": "gtm-debug",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            bundles_dir = Path(tmpdir) / "bundles"
            # Write a matching bundle
            _write_manifest(
                bundles_dir / "bundle-gtm-debug",
                {
                    "id": "bundle-gtm-debug",
                    "name": "GTM Analytics Debug Expert",
                    "keywords": ["gtm", "analytics", "ga4", "debug"],
                    "domains": ["analytics"],
                    "capabilities": ["gtm-audit", "ga4-debug"],
                    "temporal": {
                        "freshness": 0.85,
                        "usage_frequency": 0.75,
                        "ecosystem_alignment": 0.88,
                        "last_updated": "2026-03-17",
                    },
                },
            )
            output_dir = Path(tmpdir) / "output"
            result = resolve_bundle(session, analysis, bundles_dir, output_dir, create_threshold=0.3)
            assert result["selected_bundle"]["bundle_id"] == "bundle-gtm-debug"
            assert result["created_bundle_id"] is None
