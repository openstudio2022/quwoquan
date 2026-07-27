from __future__ import annotations

import importlib.util
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SETUP_PATH = ROOT / "quwoquan_ops/ci/setup_flutter_sdk.py"


def _load_setup_module():
    spec = importlib.util.spec_from_file_location("setup_flutter_sdk", SETUP_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_delivery_gate_bootstrap_uses_verified_sdk_without_actions_toolchain_cache() -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(encoding="utf-8")

    assert "subosito/flutter-action@" not in workflow
    assert "Cache Flutter SDK" not in workflow
    assert "steps.flutter.outputs.cache_path }}\n            ~/.pub-cache" not in workflow
    assert "python3 quwoquan_ops/ci/setup_flutter_sdk.py resolve" in workflow
    assert "quwoquan_app/.flutter-version" in workflow
    assert "PUB_HOSTED_URL: https://pub.flutter-io.cn" in workflow
    assert "FLUTTER_STORAGE_BASE_URL: https://storage.flutter-io.cn" in workflow
    assert "flutter pub get --enforce-lockfile" in workflow
    assert "cache-dependency-path: quwoquan_ops/portal/package-lock.json" in workflow
    assert "QWQ_DEPLOY_WORK_ROOT: ${{ runner.temp }}/quwoquan-deploy" in workflow
    assert "actions/setup-python@" not in workflow
    assert 'venv_root="${RUNNER_TEMP}/quwoquan-delivery-gate/${GITHUB_RUN_ID}/service-python"' in workflow
    assert 'venv_root="${RUNNER_TEMP}/quwoquan-delivery-gate/${GITHUB_RUN_ID}/data-python"' in workflow
    assert 'echo "$venv_root/bin" >> "$GITHUB_PATH"' in workflow
    service_job = workflow.split("  quwoquan_service:", 1)[1].split(
        "  search_contract_smoke:", 1
    )[0]
    assert 'python_bin="$(command -v python3)"' in service_job
    assert "(3, 12) <= sys.version_info[:2] < (3, 14)" in service_job
    assert "python3 -m pip install -r quwoquan_service/services/recommendation-service" in workflow


def test_delivery_gate_has_bounded_jobs() -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(
        encoding="utf-8"
    )

    expected_timeouts = {
        "topology_regression": 15,
        "quwoquan_service": 45,
        "search_contract_smoke": 20,
        "quwoquan_app": 45,
        "quwoquan_app_tests_ui": 45,
        "quwoquan_app_tests_runtime": 45,
        "quwoquan_data": 45,
        "ops_portal": 25,
        "delivery_gate_summary": 15,
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

    assert "quwoquan_app_tests_ui:" in workflow
    assert "quwoquan_app_tests_runtime:" in workflow
    ui_job = workflow.split("  quwoquan_app_tests_ui:", 1)[1].split(
        "  quwoquan_app_tests_runtime:", 1
    )[0]
    assert "runs-on: [self-hosted, macOS, ARM64]" in ui_job
    assert "runs-on: ubuntu-latest" not in workflow
    assert "QWQ_APP_GATE_PHASE: static" in workflow
    assert "QWQ_APP_TEST_SHARD: ui" in workflow
    assert "QWQ_APP_TEST_SHARD: runtime" in workflow
    assert 'local app_gate_phase="${QWQ_APP_GATE_PHASE:-all}"' in gate
    assert 'local app_test_shard="${QWQ_APP_TEST_SHARD:-all}"' in gate
    assert 'if [[ "$scope" != "app" || "${QWQ_APP_GATE_PHASE:-all}" != "tests" ]]' in gate
    assert "run_global" in gate
    assert 'flutter_test_targets=("test/local_contract/")' in gate
    assert "test/local_contract/ui/" in gate
    for runtime_root in ("app", "cloud", "core", "quality"):
        assert f'"test/local_contract/{runtime_root}/"' in gate


def test_pr_control_jobs_do_not_consume_github_hosted_actions_minutes() -> None:
    for workflow_path in (
        ROOT / ".github/workflows/delivery-gate.yml",
        ROOT / ".github/workflows/pre-release-gate.yml",
        ROOT / ".github/workflows/app-env-device-matrix-self-hosted.yml",
        ROOT / ".github/workflows/artifact-lifecycle.yml",
    ):
        workflow = workflow_path.read_text(encoding="utf-8")
        assert "runs-on: ubuntu-latest" not in workflow
        assert "runs-on: macos-latest" not in workflow
        assert "runs-on: [self-hosted, macOS, ARM64]" in workflow


def test_contract_metadata_bootstrap_creates_cache_parent_before_mktemp() -> None:
    script = (
        ROOT / "quwoquan_service/scripts/contract/verify_contract_metadata.sh"
    ).read_text(encoding="utf-8")

    mkdir_index = script.index('mkdir -p "$CONTRACT_VIEW_PARENT"')
    mktemp_index = script.index('mktemp -d "${CONTRACT_VIEW_PARENT}/cache-verify.XXXXXX"')
    assert mkdir_index < mktemp_index


def test_ff_config_contract_uses_portable_grep() -> None:
    script = (
        ROOT / "quwoquan_ops/environments/verify/verify_ff_config_contract.sh"
    ).read_text(encoding="utf-8")

    assert 'grep -nF -- "$token" "$spec"' in script
    assert "rg -n" not in script


def test_flutter_release_resolution_requires_official_checksum_and_architecture() -> None:
    setup = _load_setup_module()
    assert setup.OS_NAMES["macOS"] == "macos"
    assert setup.OS_NAMES["darwin"] == "macos"
    assert setup.ARCH_NAMES["ARM64"] == "arm64"
    assert setup.ARCH_NAMES["aarch64"] == "arm64"
    manifest = {
        "current_release": {"stable": "abc123"},
        "releases": [
            {
                "archive": "stable/linux/flutter_linux_1.2.3-stable.tar.xz",
                "dart_sdk_arch": "x64",
                "hash": "abc123",
                "sha256": "a" * 64,
                "version": "1.2.3",
            },
            {
                "archive": "stable/linux/flutter_linux_arm64_1.2.3-stable.tar.xz",
                "dart_sdk_arch": "arm64",
                "hash": "abc123",
                "sha256": "b" * 64,
                "version": "1.2.3",
            },
        ],
    }

    release = setup.select_current_release(manifest, channel="stable", architecture="x64")

    assert release == {
        "archive": "stable/linux/flutter_linux_1.2.3-stable.tar.xz",
        "hash": "abc123",
        "sha256": "a" * 64,
        "version": "1.2.3",
    }


def test_flutter_release_resolution_honors_repository_pinned_version() -> None:
    setup = _load_setup_module()
    manifest = {
        "current_release": {"stable": "new-current"},
        "releases": [
            {
                "archive": "stable/linux/flutter_linux_3.44.8-stable.tar.xz",
                "channel": "stable",
                "dart_sdk_arch": "x64",
                "hash": "new-current",
                "sha256": "a" * 64,
                "version": "3.44.8",
            },
            {
                "archive": "stable/linux/flutter_linux_3.44.3-stable.tar.xz",
                "channel": "stable",
                "dart_sdk_arch": "x64",
                "hash": "locked-release",
                "sha256": "b" * 64,
                "version": "3.44.3",
            },
        ],
    }

    release = setup.select_current_release(
        manifest, channel="stable", architecture="x64", version="3.44.3"
    )

    assert release == {
        "archive": "stable/linux/flutter_linux_3.44.3-stable.tar.xz",
        "hash": "locked-release",
        "sha256": "b" * 64,
        "version": "3.44.3",
    }
