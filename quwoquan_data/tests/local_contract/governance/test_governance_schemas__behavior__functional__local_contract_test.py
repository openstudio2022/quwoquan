from __future__ import annotations

import json
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCHEMA_ROOT = DATA_ROOT / "schema" / "governance"


def test_governance_schemas_are_valid_json_and_freeze_status_vocabulary() -> None:
    expected = {
        "_definition.schema.json",
        "_dimension.schema.json",
        "_group.schema.json",
        "_taxonomy.schema.json",
        "audit_event.schema.json",
        "backfill_event.schema.json",
        "candidate.schema.json",
        "cleanup_report.schema.json",
        "cold_start_supply_policy.schema.json",
        "discovery_checkpoint.schema.json",
        "master_list.schema.json",
        "review.schema.json",
        "semantic_mention.schema.json",
        "tag_ref.schema.json",
    }
    assert {path.name for path in SCHEMA_ROOT.glob("*.json")} == expected
    documents = {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in SCHEMA_ROOT.glob("*.json")
    }
    statuses = {"published", "pending_review", "rejected", "offline"}
    assert set(documents["candidate.schema.json"]["properties"]["status"]["enum"]) == statuses
    assert set(documents["semantic_mention.schema.json"]["properties"]["status"]["enum"]) == statuses
