"""Delivery gate runner placement and portability contracts.

Mechanically split from test_delivery_gate_ci_bootstrap__local_contract_test.py.
"""
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]


def _job_body(workflow: str, job_name: str) -> str:
    job_start = workflow.index(f"  {job_name}:\n")
    next_job = re.search(
        r"^  [a-z_]+:\n", workflow[job_start + 1 :], flags=re.MULTILINE
    )
    job_end = job_start + 1 + next_job.start() if next_job else None
    return workflow[job_start:job_end]


def test_delivery_pr_reuses_push_owned_app_evidence_without_merging_ranges() -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(
        encoding="utf-8"
    )
    local_app_if = (
        "github.event_name != 'pull_request' && (github.event_name == "
        "'workflow_call' || needs.topology_regression.outputs.candidate_app == 'true')"
    )
    assert workflow.count(local_app_if) == 4
    assert "name: Detect candidate-level App scope" in workflow
    assert "git merge-base origin/main \"$HEAD_SHA\"" in workflow
    assert "--scope-receipt" in workflow
    assert "SCOPE_ARGS+=(--required-scope app)" in workflow
    assert '${SCOPE_ARGS[@]+"${SCOPE_ARGS[@]}"}' in workflow
    assert "name: Verify push-owned App evidence" in workflow
    assert "make verify-delivery-app-evidence" in workflow
    assert "job_closure_digest: ${{ steps.external.outputs.job_closure_digest }}" in workflow
    assert "if: ${{ github.event_name == 'pull_request' }}" in workflow
    assert 'if [[ "${{ github.event_name }}" != "pull_request" ]]; then' in workflow
    assert "if: ${{ github.event_name != 'pull_request' }}" in workflow
    assert "--external-phase \"app_static=$APP_STATIC_EXTERNAL\"" in workflow
    assert "--external-phase \"app_coverage=$APP_COVERAGE_EXTERNAL\"" in workflow
    assert '--candidate-job "Delivery Gate — App (L1)"' not in workflow
    concurrency = workflow[workflow.index("concurrency:") : workflow.index("\non:")]
    assert "github.event_name" in concurrency
    assert "github.ref" in concurrency
    assert "head.sha" not in concurrency


def test_delivery_gate_keeps_cross_platform_jobs_on_linux_and_visual_phases_on_controlled_macos() -> None:
    delivery = (ROOT / ".github/workflows/delivery-gate.yml").read_text(
        encoding="utf-8"
    )

    hosted_linux_jobs = (
        "common_governance",
        "topology_regression",
        "quwoquan_service",
        "search_contract_smoke",
        "quwoquan_app_static",
        "quwoquan_app_tests",
        "quwoquan_app",
        "quwoquan_data",
        "ops_portal",
        "release_evidence",
        "delivery_gate_summary",
    )
    for job_name in hosted_linux_jobs:
        job_start = delivery.index(f"  {job_name}:\n")
        next_job = re.search(
            r"^  [a-z_]+:\n", delivery[job_start + 1 :], flags=re.MULTILINE
        )
        job_end = job_start + 1 + next_job.start() if next_job else None
        job_body = delivery[job_start:job_end]
        assert "runs-on: ubuntu-latest" in job_body

    for job_name, next_job_name in (
        ("quwoquan_app_serial", "quwoquan_app_coverage"),
        ("quwoquan_app_coverage", "quwoquan_app"),
    ):
        job_start = delivery.index(f"  {job_name}:\n")
        job_end = delivery.index(f"\n  {next_job_name}:\n", job_start)
        job_body = delivery[job_start:job_end]
        assert "runs-on: [self-hosted, macOS, ARM64]" in job_body
    packaging = _job_body(delivery, "quwoquan_service_packaging")
    assert "runs-on: [self-hosted, macOS, ARM64]" in packaging
    assert "runs-on: macos-latest" not in delivery


def test_search_smoke_builds_the_pinned_cjk_provider_before_api_tests() -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(
        encoding="utf-8"
    )
    job_start = workflow.index("  search_contract_smoke:\n")
    job_end = workflow.index("\n  quwoquan_app_static:\n", job_start)
    job = workflow[job_start:job_end]

    build = (
        "docker build \\\n"
        "            --tag quwoquan/elasticsearch-cjk:8.13.4"
    )
    test = "go test ./services/search-service/tests/api_integration/search/search_index_view"
    assert build in job
    assert job.index(build) < job.index(test)


def test_environment_writing_jobs_stay_on_controlled_runners() -> None:
    for workflow_path in (
        ROOT / ".github/workflows/pre-release-gate.yml",
        ROOT / ".github/workflows/artifact-lifecycle.yml",
    ):
        workflow = workflow_path.read_text(encoding="utf-8")
        assert "runs-on: macos-latest" not in workflow
        assert "runs-on: [self-hosted, macOS, ARM64]" in workflow


def test_contract_metadata_bootstrap_creates_cache_parent_before_mktemp() -> None:
    script = (
        ROOT / "quwoquan_service/scripts/verify/contract_graph/verify_contract_metadata.sh"
    ).read_text(encoding="utf-8")

    mkdir_index = script.index('mkdir -p "$CONTRACT_VIEW_CACHE"')
    mktemp_index = script.index('mktemp -d "${CONTRACT_VIEW_CACHE}/verify.XXXXXX"')
    assert mkdir_index < mktemp_index


def test_ff_config_contract_uses_portable_grep() -> None:
    script = (
        ROOT / "quwoquan_ops/environments/verify/verify_ff_config_contract.sh"
    ).read_text(encoding="utf-8")

    assert 'grep -nF -- "$token" "$spec"' in script
    assert "rg -n" not in script
