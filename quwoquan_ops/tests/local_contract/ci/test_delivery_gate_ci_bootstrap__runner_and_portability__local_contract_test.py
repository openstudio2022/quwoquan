"""Delivery gate runner placement and portability contracts.

Mechanically split from test_delivery_gate_ci_bootstrap__local_contract_test.py
at Engineering pre-merge head ddd8b9366.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
GATE_REPO_PATH = ROOT / "quwoquan_ops/gate/gate_repo.sh"


def _job_body(workflow: str, job_name: str) -> str:
    job_start = workflow.index(f"  {job_name}:\n")
    next_job = re.search(
        r"^  [a-z_]+:\n", workflow[job_start + 1 :], flags=re.MULTILINE
    )
    job_end = job_start + 1 + next_job.start() if next_job else None
    return workflow[job_start:job_end]


def _run_stubbed_app_test_phase(
    tmp_path: Path,
    *,
    phase: str = "tests",
    shard_total: str | None = "4",
    shard_index: str | None = "0",
) -> tuple[subprocess.CompletedProcess[str], Path]:
    source = GATE_REPO_PATH.read_text(encoding="utf-8")
    start = re.search(r"(?m)^run_app\(\)\s+\{", source)
    end = re.search(r"(?m)^run_portal\(\)\s+\(", source)
    assert start is not None and end is not None and start.start() < end.start()
    app = source[start.start() : end.start()]
    total_label = shard_total if shard_total is not None else "unset"
    index_label = shard_index if shard_index is not None else "unset"
    case_dir = tmp_path / f"shard-{total_label}-{index_label}"
    stub_dir = case_dir / "bin"
    stub_dir.mkdir(parents=True)
    log_path = case_dir / "commands.log"
    stub = '#!/usr/bin/env sh\nprintf "%s %s\\n" "$0" "$*" >>"$GATE_STUB_LOG"\n'
    for executable in ("python3", "dart", "flutter", "make"):
        path = stub_dir / executable
        path.write_text(stub, encoding="utf-8")
        path.chmod(0o755)
    harness = case_dir / "run_app_tests.sh"
    harness.write_text(
        "#!/bin/bash\nset -euo pipefail\n"
        f"ROOT={str(ROOT)!r}\ncd \"$ROOT\"\n{app}\nrun_app\n",
        encoding="utf-8",
    )
    harness.chmod(0o755)
    environment = os.environ.copy()
    environment.pop("FLUTTER_TEST_TOTAL_SHARDS", None)
    environment.pop("FLUTTER_TEST_SHARD_INDEX", None)
    environment.update(
        {
            "GATE_APP_PHASE": phase,
            "GATE_STUB_LOG": str(log_path),
            "PATH": f"{stub_dir}:/usr/bin:/bin",
        }
    )
    if shard_total is not None:
        environment["FLUTTER_TEST_TOTAL_SHARDS"] = shard_total
    if shard_index is not None:
        environment["FLUTTER_TEST_SHARD_INDEX"] = shard_index
    completed = subprocess.run(
        ["/bin/bash", str(harness)],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed, log_path


def test_app_test_phase_executes_shared_contracts_only_on_shard_zero(
    tmp_path: Path,
) -> None:
    for shard_index in ("0", "1", "2", "3"):
        completed, log_path = _run_stubbed_app_test_phase(
            tmp_path,
            shard_index=shard_index,
        )
        assert completed.returncode == 0, completed.stderr
        commands = log_path.read_text(encoding="utf-8").splitlines()
        python_contract_commands = [
            command
            for command in commands
            if "test-app-python-local-contract" in command
        ]
        canonical_coverage_commands = [
            command
            for command in commands
            if "verify_canonical_coverage.py --collect --scope app" in command
        ]
        expected_count = 1 if shard_index == "0" else 0
        assert len(python_contract_commands) == expected_count
        assert len(canonical_coverage_commands) == 0


def test_unsharded_app_test_phase_keeps_the_full_shared_suite(
    tmp_path: Path,
) -> None:
    completed, log_path = _run_stubbed_app_test_phase(
        tmp_path,
        shard_total=None,
        shard_index=None,
    )

    assert completed.returncode == 0, completed.stderr
    commands = log_path.read_text(encoding="utf-8").splitlines()
    assert sum("test-app-python-local-contract" in row for row in commands) == 1
    assert not any(
        "verify_canonical_coverage.py --collect --scope app" in row
        for row in commands
    )


def test_app_coverage_phase_executes_canonical_coverage_once(
    tmp_path: Path,
) -> None:
    completed, log_path = _run_stubbed_app_test_phase(
        tmp_path,
        phase="coverage",
        shard_total=None,
        shard_index=None,
    )

    assert completed.returncode == 0, completed.stderr
    commands = log_path.read_text(encoding="utf-8").splitlines()
    assert not any("test-app-python-local-contract" in row for row in commands)
    assert sum(
        "verify_canonical_coverage.py --collect --scope app" in row
        for row in commands
    ) == 1


def test_app_test_phase_rejects_invalid_shards_before_execution(
    tmp_path: Path,
) -> None:
    invalid_shards = (
        (None, "0"),
        ("4", None),
        ("0", "0"),
        ("not-a-number", "0"),
        ("4", "-1"),
        ("4", "not-a-number"),
        ("4", "4"),
    )

    for shard_total, shard_index in invalid_shards:
        completed, log_path = _run_stubbed_app_test_phase(
            tmp_path,
            shard_total=shard_total,
            shard_index=shard_index,
        )

        assert completed.returncode == 2
        assert (
            "app phase=tests sharding requires total>0 and 0<=index<total"
            in completed.stderr
        )
        assert "or unset both for unsharded execution" in completed.stderr
        assert not log_path.exists()


def test_delivery_pr_reuses_push_owned_app_evidence_without_merging_ranges() -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(
        encoding="utf-8"
    )
    local_app_if = (
        "github.event_name != 'pull_request' && (github.event_name == "
        "'workflow_call' || needs.topology_regression.outputs.candidate_app == 'true')"
    )
    assert workflow.count(local_app_if) == 3
    assert "needs.topology_regression.outputs.coverage_app == 'true'" in workflow
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
    # 三格匹配同一台物理 runner，并共享 host-wide App dependency sync lock；
    # matrix 保留三份独立证据，但不得在该主机上互相争锁。
    assert "packaging_env: [alpha, beta, gamma]" in packaging
    assert "max-parallel: 1" in packaging
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
    workflow = (ROOT / ".github/workflows/pre-release-gate.yml").read_text(
        encoding="utf-8"
    )
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


def test_delivery_impact_plan_is_generated_once_and_artifacted() -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(encoding="utf-8")
    topology = _job_body(workflow, "topology_regression")
    assert topology.count("--impact-plan") == 1
    assert "--validate-impact-plan" in topology
    assert "Upload versioned Delivery impact plan" in topology
    assert "impact_plan_digest: ${{ steps.detect.outputs.plan_digest }}" in topology
    for job_name in ("quwoquan_app_tests", "quwoquan_data_tests"):
        assert "detect_ci_impacted_scopes.py" not in _job_body(workflow, job_name)


def test_coverage_jobs_use_business_impact_or_governance_contract_closure() -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(encoding="utf-8")
    assert "outputs.coverage_service == 'true'" in _job_body(workflow, "quwoquan_service_coverage")
    assert "outputs.coverage_app == 'true'" in _job_body(workflow, "quwoquan_app_coverage")
    assert 'expect_typed_pending_or_skipped "quwoquan_service_coverage" "${SERVICE_COVERAGE}" "$SERVICE_COVERAGE_IMPACTED"' in workflow


def test_delivery_timing_provider_failure_is_pr_warn_not_red_on_green() -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(encoding="utf-8")
    assert "telemetry_classification=infra" in workflow
    assert "TIMING_PR_WARN" in workflow
    assert "functional Delivery checks remain authoritative" in workflow
    assert "Delivery Gate timing is historical_incomplete" not in workflow
