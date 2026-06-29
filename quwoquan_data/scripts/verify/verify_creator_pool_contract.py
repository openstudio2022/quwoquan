#!/usr/bin/env python3
"""Verify system-creator-pool contract paths exist (D0 gate)."""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SCRIPTS_ROOT.parent.parent
DATA_ROOT = REPO_ROOT / "quwoquan_data"
SERVICE_ROOT = REPO_ROOT / "quwoquan_service"

REQUIRED_PATHS = [
    DATA_ROOT / "docs/creator_pool_pipeline_spec.md",
    DATA_ROOT / "schema/creator/creator_bundle.schema.json",
    DATA_ROOT / "schema/creator/creator_pool_plan.schema.json",
    DATA_ROOT / "schema/creator/diversity_matrix.schema.json",
    DATA_ROOT / "schema/creator/creator_rollup_report.schema.json",
    DATA_ROOT / "schema/creator/creator_readiness_report.schema.json",
    DATA_ROOT / "scripts/governance/creator_pool/handler.py",
    DATA_ROOT / "scripts/governance/creator_pool/workflow.py",
    DATA_ROOT / "schema/creator/creator_persona_quality.schema.json",
    DATA_ROOT / "schema/creator/creator_persona_rubric.json",
    DATA_ROOT / "scripts/_common/creator_pool/persona_rubric.py",
    DATA_ROOT / "scripts/_common/creator_pool/persona_dedup.py",
    DATA_ROOT / "scripts/governance/creator_pool/diversify.py",
    DATA_ROOT / "scripts/governance/creator_pool/readiness.py",
    DATA_ROOT / "scripts/verify/verify_creator_pool_seed_consistency.py",
    DATA_ROOT / "tests/local_contract/creator_pool/test_creator_commercial_readiness__local_contract_test.py",
    DATA_ROOT / "tests/local_contract/creator_pool/test_creator_content_workflow_smoke__local_contract_test.py",
    SERVICE_ROOT / "services/user-service/tests/local_contract/creator_pool_seed_contract__local_contract_test.go",
    DATA_ROOT / "scripts/verify/verify_creator_pool_contract.py",
    DATA_ROOT / "tests/local_contract/creator_pool/test_creator_bundle_schema__local_contract_test.py",
    DATA_ROOT / "tests/local_contract/creator_pool/test_creator_pool_workflow_contract__local_contract_test.py",
    DATA_ROOT / "tests/local_contract/creator_pool/test_creator_scale10_fixtures__local_contract_test.py",
    DATA_ROOT / "tests/local_contract/creator_pool/test_creator_readiness_gate__local_contract_test.py",
    DATA_ROOT / "tests/local_contract/creator_pool/test_creator_content_bind_smoke__local_contract_test.py",
    DATA_ROOT / "tests/local_contract/creator_pool/test_creator_registry_bridge__local_contract_test.py",
    DATA_ROOT / "tests/local_contract/creator_pool/test_creator_persona_content_match__local_contract_test.py",
    DATA_ROOT / "tests/local_contract/creator_pool/test_creator_relations_consumer__local_contract_test.py",
    DATA_ROOT / "tests/local_contract/creator_pool/test_creator_content_bind__local_contract_test.py",
    DATA_ROOT / "scripts/governance/creator_pool/relations.py",
    DATA_ROOT / "scripts/governance/creator_pool/content_bind.py",
    DATA_ROOT / "scripts/governance/creator_pool/content_rollout.py",
    SERVICE_ROOT / "contracts/metadata/_shared/test_fixtures/creator_pool/creator_content.seed.json",
    REPO_ROOT / "artifacts/creator_content_prod_rollout_dryrun.json",
    DATA_ROOT / "scripts/_common/creator_assignment.py",
    DATA_ROOT / "scripts/_common/creator_pool/registry_bridge.py",
    DATA_ROOT / "tests/fixtures/creator_pool/travel_scale10_verify/golden_creator_bundle.json",
    REPO_ROOT / "specs/feature-tree/runtime/runtime-data-engineering/system-creator-pool/spec.md",
    REPO_ROOT / "specs/feature-tree/runtime/runtime-data-engineering/system-creator-pool/acceptance.yaml",
    REPO_ROOT / "specs/feature-tree/runtime/runtime-data-engineering/system-creator-pool/next-round-plan.md",
    SERVICE_ROOT / "contracts/metadata/_shared/test_fixtures/creator_pool",
]


def main() -> int:
    missing = [str(p.relative_to(REPO_ROOT)) for p in REQUIRED_PATHS if not p.exists()]
    if missing:
        print("[verify-creator-pool-contract] FAILED missing paths:", file=sys.stderr)
        for item in missing:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print(f"[verify-creator-pool-contract] PASSED ({len(REQUIRED_PATHS)} paths)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
