from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
sys.path.insert(0, str(DATA_ROOT / "scripts"))

from verify import verify_script_architecture as gate


RETIRED_PATHS = {
    "quwoquan_data/control_plane/_shared/catalogs/review_policy.yaml",
    "quwoquan_data/control_plane/_shared/catalogs/works_classification.yaml",
    "quwoquan_data/schema/content/gate_verdict.schema.json",
    "quwoquan_data/schema/content/works_classification.schema.json",
    "quwoquan_data/schema/release/content_release_stage_receipt.schema.json",
    "quwoquan_data/schema/release/pool_append_batch.schema.json",
    "quwoquan_data/schema/release/release_manifest.schema.json",
    "quwoquan_data/schema/source/article_source_classification.schema.json",
    "quwoquan_data/schema/source/source_candidate.schema.json",
    "quwoquan_data/schema/source/source_plan.schema.json",
    "quwoquan_data/schema/source/source_screen.schema.json",
    "quwoquan_data/schema/source/source_unit_meta.schema.json",

    "quwoquan_data/schema/_common/stage_envelope.schema.json",
    "quwoquan_data/schema/governance/cleanup_report.schema.json",
    "quwoquan_data/schema/governance/review_policy.schema.json",
    "quwoquan_data/schema/release/content_item_version_view.schema.json",
    "quwoquan_data/schema/release/release_identity_incident.schema.json",
    "quwoquan_data/schema/release/release_identity_recovery_provenance.schema.json",
    "quwoquan_data/schema/release/resolve_invalid_canonical_identity_command.schema.json",
    "quwoquan_data/schema/release/supply_chain_drill_receipt.schema.json",
    "quwoquan_data/schema/source/host_source_review_request.schema.json",
    "quwoquan_data/schema/source/host_source_review_result_input.schema.json",
    "quwoquan_data/scripts/content/release/canonical/handler_identity_cli.py",
}

RETIRED_IDENTITIES = {
    "quwoquan_data.stage_envelope",
    "quwoquan_data.coverage_cleanup_audit",
    "quwoquan.gate_verdict",
    "quwoquan_data.works_classification",
    "quwoquan.content_release_stage_receipt",
    "quwoquan_data.pool_append_batch",
    "quwoquan_data.release_manifest",
    "quwoquan_data.article_source_classification",
    "quwoquan_data.source_candidate",
    "quwoquan_data.source_plan",

    "quwoquan_data.content_item_version_view",
    "quwoquan_data.release_identity_incident",
    "quwoquan_data.release_identity_recovery_provenance",
    "quwoquan_data.resolve_invalid_canonical_identity_command",
    "quwoquan_data.supply_chain_drill_receipt",
    "quwoquan_data.host_source_review_request",
    "quwoquan_data.host_source_review_result_input",
}


def test_retired_schema_paths_and_identities_are_guarded_and_absent() -> None:
    assert RETIRED_PATHS <= set(gate.RETIRED_PATHS)
    assert RETIRED_IDENTITIES <= set(gate.FORBIDDEN_TOKENS)
    assert not [path for path in RETIRED_PATHS if (gate.REPO_ROOT / path).exists()]
    assert gate.architecture_issues() == []


def test_entity_page_input_uses_its_own_non_retired_identity() -> None:
    schema = (DATA_ROOT / "schema/content/entity_page_input.schema.json").read_text(encoding="utf-8")
    assert '"const": "quwoquan_data.entity_page_input"' in schema
    assert not any(identity in schema for identity in RETIRED_IDENTITIES)
