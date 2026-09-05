#!/usr/bin/env python3
"""Require retired Data orchestration paths and production tokens to stay absent."""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_ROOT = REPO_ROOT / "quwoquan_data"
_SELF = Path(__file__).resolve()

RETIRED_PATHS = (
    "quwoquan_data/control_plane/_shared/catalogs/bounded_execution_authority_policy.json",
    "quwoquan_data/schema/_common/zero_qualified_reason.schema.json",
    "quwoquan_data/schema/governance/canonical_gc_apply.schema.json",
    "quwoquan_data/schema/governance/canonical_gc_execution_tombstone.schema.json",
    "quwoquan_data/schema/governance/canonical_gc_plan.schema.json",
    "quwoquan_data/schema/governance/canonical_gc_reference_graph.schema.json",
    "quwoquan_data/schema/governance/canonical_gc_tombstone_backfill.schema.json",
    "quwoquan_data/schema/governance/coverage_source_ready_catalog_projection.schema.json",
    "quwoquan_data/schema/governance/data_output_layout_migration.schema.json",
    "quwoquan_data/schema/governance/data_workstream_baseline.schema.json",
    "quwoquan_data/schema/governance/discovery_checkpoint.schema.json",
    "quwoquan_data/schema/governance/source_readiness_manifest.schema.json",
    "quwoquan_data/schema/governance/source_readiness_report.schema.json",
    "quwoquan_data/schema/governance/source_ready_candidate.schema.json",
    "quwoquan_data/schema/release/fault_injection_cases.schema.json",
    "quwoquan_data/schema/release/fault_injection_event.schema.json",
    "quwoquan_data/schema/release/fault_injection_evidence.schema.json",
    "quwoquan_data/schema/release/pool_inspection.schema.json",
    "quwoquan_data/schema/release/pool_object_retirement_receipt.schema.json",
    "quwoquan_data/schema/release/post_metadata_adoption.schema.json",
    "quwoquan_data/schema/release/resource_soak_evidence.schema.json",
    "quwoquan_data/schema/release/resource_soak_samples.schema.json",
    "quwoquan_data/schema/source/homepage_article_source_ready_acquisition_evidence.schema.json",
    "quwoquan_data/schema/source/homepage_article_source_ready_acquisition_report.schema.json",
    "quwoquan_data/schema/source/homepage_article_source_ready_aggregate.schema.json",
    "quwoquan_data/schema/source/homepage_article_source_ready_batch.schema.json",
    "quwoquan_data/schema/source/homepage_article_source_ready_candidate.schema.json",
    "quwoquan_data/schema/source/source_discovery_stage_progress.schema.json",
    "quwoquan_data/scripts/content/homepage",
    "quwoquan_data/scripts/content/post",
    "quwoquan_data/scripts/content/review",
    "quwoquan_data/scripts/content/source/research/scale_source_pool.py",
    "quwoquan_data/scripts/content/source/research/handler_cli.py",
    "quwoquan_data/scripts/content/release/canonical/handler_object_transaction_cli.py",
    "quwoquan_data/scripts/content/release/canonical/publish_execution.py",
    "quwoquan_data/scripts/content/release/canonical/pool_precheck.py",
    "quwoquan_data/scripts/content/release/canonical/pool_inspection.py",
    "quwoquan_data/scripts/content/release/canonical/post_metadata_adoption.py",
    "quwoquan_data/scripts/content/release/canonical/post_metadata_adoption_contract.py",
    "quwoquan_data/scripts/content/release/canonical/post_metadata_adoption_source.py",
    "quwoquan_data/scripts/content/release/canonical/semantic_wave_dispatch.py",
    "quwoquan_data/scripts/content/release/canonical/supply_chain_drill.py",
    "quwoquan_data/scripts/content/release/environment/activation_recovery.py",
    "quwoquan_data/scripts/core/throughput_plan.py",
    "quwoquan_data/scripts/governance/output_layout_migration.py",
    "quwoquan_data/scripts/governance/workstream_baseline.py",
    "quwoquan_data/tests/api_integration/release/test_pool_object_retirement__historical_object__contract__api_integration_test.py",
    "quwoquan_data/tests/support/pool_object_retirement_fixture.py",
    "quwoquan_data/tests/user_acceptance/journeys/content_execution/test_execution_work_package_operator_journey__behavior__functional__user_acceptance_test.py",
)

RETIRED_COVERAGE_PATHS = (
    "benchmark.py",
    "coverage_corroboration.py",
    "coverage_finalize.py",
    "coverage_matrix.py",
    "coverage_merge.py",
    "coverage_runtime.py",
    "coverage_semantics.py",
    "coverage_source_ready_catalog_projection.py",
    "coverage_status.py",
    "discovery.py",
    "discovery_shared.py",
    "discovery_wiki.py",
    "discovery_wikidata.py",
    "maturity.py",
    "source_readiness.py",
    "source_readiness_candidates.py",
)

PRODUCTION_ROOTS = (
    DATA_ROOT / "scripts",
    DATA_ROOT / "schema",
    DATA_ROOT / "control_plane",
    DATA_ROOT / "tests",
    REPO_ROOT / "specs/feature-tree/discovery-content/object-homepage-coverage-scaling",
    REPO_ROOT / "specs/feature-tree/runtime/runtime-data-engineering",
)

FORBIDDEN_TOKENS = (
    "content.execution.planning",
    "content.execution.campaign",
    "content.execution.source_pool",
    "content.execution.runtime_state",
    "content.execution.stage_reports",
    "content.execution.model_contract",
    "reviewedClosureAdoption",
    "reviewed_closure_adoption",
    "automaticRecovery",
    "recoveryStage",
    "execution_command_root",
    "execution_inputs_dir",
    "execution_results_dir",
    "execution_assistant_task",
    "ensure_execution_command_layout",
    "WORKSPACE_ROOT_BY_COMMAND",
    "post_metadata_adoption",
    "activation_recovery",
    "throughput_plan",
    "_shared/execution_state.json",
    "_shared/semantic_tasks",
    "pool-inspect",
    "pool-precheck",
)

_ALLOWED_NEGATIVE_TESTS = {
    DATA_ROOT / "tests/local_contract/execution/test_execution_kernel__minimal__contract__local_contract_test.py",
}
def _production_files() -> list[Path]:
    files: list[Path] = []
    for root in PRODUCTION_ROOTS:
        if not root.is_dir():
            continue
        files.extend(
            path
            for path in root.rglob("*")
            if path.is_file() and path.suffix in {".py", ".json", ".yaml", ".yml", ".md"}
        )
    return sorted(set(files))


def _token_allowed(path: Path, token: str) -> bool:
    if path == _SELF or path.name == "verify_public_cli_live_import_zero.py":
        return True
    if token in {"_shared/execution_state.json", "_shared/semantic_tasks"}:
        return path in _ALLOWED_NEGATIVE_TESTS
    if token in {"pool-inspect", "pool-precheck"}:
        return path.name == "verify_public_cli_live_import_zero.py"
    return False


def architecture_issues() -> list[str]:
    issues = [
        f"retired path still exists: {relative}"
        for relative in RETIRED_PATHS
        if (REPO_ROOT / relative).exists()
    ]
    coverage_root = DATA_ROOT / "scripts/governance/coverage"
    issues.extend(
        f"retired path still exists: quwoquan_data/scripts/governance/coverage/{name}"
        for name in RETIRED_COVERAGE_PATHS
        if (coverage_root / name).exists()
    )
    for path in _production_files():
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_TOKENS:
            if token in text and not _token_allowed(path, token):
                issues.append(f"{path.relative_to(REPO_ROOT)}: retired token {token}")
    return issues


def main() -> int:
    issues = architecture_issues()
    if issues:
        print("[verify script-architecture] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify script-architecture] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
