from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]


def test_delivery_gate_bootstrap_uses_pinned_verified_toolchains() -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(encoding="utf-8")

    assert "subosito/flutter-action@" not in workflow
    assert "quwoquan_app/.flutter-version" in workflow
    assert "python3 quwoquan_ops/ci/setup_flutter_sdk.py resolve" in workflow
    assert "python3 quwoquan_ops/ci/setup_flutter_sdk.py install" in workflow
    assert "Cache lock-bound Dart dependencies" in workflow
    assert (
        "path: |\n            ${{ steps.flutter.outputs.cache_path }}" not in workflow
    )
    assert "cache-dependency-path: quwoquan_ops/portal/package-lock.json" in workflow
    assert "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065" in workflow
    assert "pip install -r quwoquan_data/requirements.txt" in workflow
    assert "github.com/rhysd/actionlint/cmd/actionlint@v1.7.7" in workflow
    assert 'actionlint\" -version | head -n 1)\" = \"v1.7.7\"' in workflow


def test_ops_portal_build_receives_the_external_deploy_root() -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(encoding="utf-8")
    job_start = workflow.index("  ops_portal:\n")
    job_end = workflow.index("\n  release_evidence:\n", job_start)
    job = workflow[job_start:job_end]

    assert "Configure Ops Portal CI paths" in job
    assert (
        'echo "QWQ_DEPLOY_WORK_ROOT=$RUNNER_TEMP/quwoquan-deploy" '
        '>> "$GITHUB_ENV"'
    ) in job


def test_service_gate_installs_required_native_test_dependencies() -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(encoding="utf-8")
    job_start = workflow.index("  quwoquan_service:\n")
    job_end = workflow.index("\n  search_contract_smoke:\n", job_start)
    job = workflow[job_start:job_end]

    assert "prometheus tesseract-ocr" in job
    assert "--no-install-recommends" in job


def test_delivery_gate_runs_for_integration_and_promotion_pull_requests() -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(encoding="utf-8")
    pre_release = (ROOT / ".github/workflows/pre-release-gate.yml").read_text(encoding="utf-8")

    assert "pull_request:\n    branches:\n      - dev1.0\n      - main" in workflow
    assert "pull_request:\n    branches:\n      - dev1.0\n      - main" in pre_release
    assert "\n  push:\n" not in workflow
    assert "Enforce the reviewed pull-request branch edge" in workflow
    assert "verify_git_branch_policy.py" in workflow


def test_app_pipeline_uses_only_the_repository_pinned_flutter_version() -> None:
    workflow = (ROOT / ".github/workflows/app_pipeline.yml").read_text(encoding="utf-8")

    assert workflow.count("quwoquan_app/.flutter-version") == 4
    assert workflow.count("flutter-version: ${{ steps.flutter_version.outputs.value }}") == 4
    assert "channel: stable" not in workflow
    assert (ROOT / "quwoquan_app/.flutter-version").read_text(encoding="utf-8") == "3.47.0\n"


def test_delivery_gate_has_bounded_jobs() -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(
        encoding="utf-8"
    )

    expected_timeouts = {
        "topology_regression": 10,
        "quwoquan_service": 30,
        "search_contract_smoke": 10,
        "quwoquan_app_static": 20,
        "quwoquan_app_tests": 40,
        "quwoquan_app_serial": 40,
        "quwoquan_app": 10,
        "quwoquan_data": 10,
        "ops_portal": 10,
        "release_evidence": 10,
        "delivery_gate_summary": 5,
    }
    for job, minutes in expected_timeouts.items():
        job_start = workflow.index(f"  {job}:\n")
        next_job = re.search(
            r"^  [a-z_]+:\n", workflow[job_start + 1 :], flags=re.MULTILINE
        )
        job_end = job_start + 1 + next_job.start() if next_job else None
        job_body = workflow[job_start:job_end]
        assert f"    timeout-minutes: {minutes}" in job_body


def test_delivery_gate_shards_app_contract_without_weakening_local_full_gate() -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(encoding="utf-8")
    gate = (ROOT / "quwoquan_ops/gate/gate_repo.sh").read_text(encoding="utf-8")

    assert "quwoquan_app_static:" in workflow
    assert "quwoquan_app_tests:" in workflow
    assert "quwoquan_app_serial:" in workflow
    assert "shard_index: [0, 1, 2, 3]" in workflow
    assert 'FLUTTER_TEST_TOTAL_SHARDS: "4"' in workflow
    assert "FLUTTER_TEST_SHARD_INDEX: ${{ matrix.shard_index }}" in workflow
    assert "GATE_APP_PHASE: static" in workflow
    assert "GATE_APP_PHASE: tests" in workflow
    assert "GATE_APP_PHASE: serial" in workflow
    assert 'local app_phase="${GATE_APP_PHASE:-all}"' in gate
    assert 'run_app_flutter_tests "${FLUTTER_TEST_SERIAL_MODE:-exclude}"' in gate


def test_delivery_gate_keeps_cross_platform_jobs_on_linux_and_visual_serial_on_controlled_macos() -> None:
    delivery = (ROOT / ".github/workflows/delivery-gate.yml").read_text(
        encoding="utf-8"
    )

    hosted_linux_jobs = (
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

    serial_start = delivery.index("  quwoquan_app_serial:\n")
    serial_end = delivery.index("\n  quwoquan_app:\n", serial_start)
    serial_job = delivery[serial_start:serial_end]
    assert "runs-on: [self-hosted, macOS, ARM64]" in serial_job
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
