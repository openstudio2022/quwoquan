"""Tests for explore prepare and validate."""
import tempfile
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
import sys
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import os

from core.paths import ensure_execution_layout, execution_catalog
from core.io import write_ndjson
from content.source.discovery.gate import gate_explore


def test_gate_explore_passes_with_valid_catalog():
    execution_id = "20260712--travel-homepage-explore--test-region-a--pilot-001"
    ensure_execution_layout(execution_id)

    rows = [{"topic_id": f"poi_{i}", "canonicalName": f"Place {i}", "entityType": "scenic"} for i in range(15)]
    write_ndjson(execution_catalog(execution_id), rows)

    issues = gate_explore(execution_id, expected_topic_ids=[f"poi_{i}" for i in range(10)])
    assert issues == []


def test_gate_explore_fails_with_too_few():
    execution_id = "20260712--travel-homepage-explore--test-region-a--pilot-002"
    ensure_execution_layout(execution_id)

    rows = [{"topic_id": f"poi_{i}", "canonicalName": f"Place {i}", "entityType": "scenic"} for i in range(3)]
    write_ndjson(execution_catalog(execution_id), rows)

    issues = gate_explore(execution_id, expected_topic_ids=[f"poi_{i}" for i in range(10)])
    assert len(issues) == 1
    assert "missing expected topic_ids" in issues[0]
