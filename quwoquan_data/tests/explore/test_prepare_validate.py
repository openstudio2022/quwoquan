"""Tests for explore prepare and validate."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import os
os.environ["QWQ_RUNTIME_ROOT"] = tempfile.mkdtemp()

from _common.paths import ensure_task_layout, task_catalog
from _common.io import write_ndjson
from explore.gate import gate_explore


def test_gate_explore_passes_with_valid_catalog():
    task_id = "test_explore_001"
    ensure_task_layout(task_id)

    rows = [{"topic_id": f"poi_{i}", "canonicalName": f"Place {i}", "entityType": "scenic"} for i in range(15)]
    write_ndjson(task_catalog(task_id), rows)

    issues = gate_explore(task_id, min_pois=10)
    assert issues == []


def test_gate_explore_fails_with_too_few():
    task_id = "test_explore_002"
    ensure_task_layout(task_id)

    rows = [{"topic_id": f"poi_{i}", "canonicalName": f"Place {i}", "entityType": "scenic"} for i in range(3)]
    write_ndjson(task_catalog(task_id), rows)

    issues = gate_explore(task_id, min_pois=10)
    assert len(issues) == 1
    assert "POI count" in issues[0]
