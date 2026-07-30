from __future__ import annotations

import importlib.util
import io
import json
import re
import urllib.error
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[3]
SETUP_PATH = ROOT / "quwoquan_ops/ci/setup_flutter_sdk.py"


def _load_setup_module():
    spec = importlib.util.spec_from_file_location("setup_flutter_sdk", SETUP_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_delivery_gate_bootstrap_uses_pinned_cached_toolchains() -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(encoding="utf-8")

    assert "subosito/flutter-action@1a449444c387b1966244ae4d4f8c696479add0b2" in workflow
    assert "quwoquan_app/.flutter-version" in workflow
    assert "flutter-version: ${{ steps.flutter_version.outputs.value }}" in workflow
    assert "cache: true" in workflow
    assert "cache-dependency-path: quwoquan_ops/portal/package-lock.json" in workflow
    assert "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065" in workflow
    assert "pip install -r quwoquan_data/requirements.txt" in workflow


def test_delivery_gate_has_bounded_jobs() -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(
        encoding="utf-8"
    )

    expected_timeouts = {
        "topology_regression": 10,
        "quwoquan_service": 10,
        "search_contract_smoke": 10,
        "quwoquan_app_static": 10,
        "quwoquan_app_tests": 10,
        "quwoquan_app_serial": 10,
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


def test_delivery_gate_parallelizes_safe_checks_on_hosted_runners() -> None:
    delivery = (ROOT / ".github/workflows/delivery-gate.yml").read_text(
        encoding="utf-8"
    )
    assert "runs-on: ubuntu-latest" in delivery
    assert "timeout-minutes: 10" in delivery
    assert "runs-on: macos-latest" not in delivery


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
        ROOT / "quwoquan_service/scripts/contract/verify_contract_metadata.sh"
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


def test_flutter_release_manifest_download_retries_transient_ssl_eof() -> None:
    setup = _load_setup_module()
    payload = {"current_release": {"stable": "locked"}, "releases": []}
    response = io.BytesIO(json.dumps(payload).encode("utf-8"))
    transient = urllib.error.URLError("SSL: UNEXPECTED_EOF_WHILE_READING")

    with (
        mock.patch.object(
            setup.urllib.request,
            "urlopen",
            side_effect=[transient, transient, response],
        ) as opened,
        mock.patch.object(setup.time, "sleep") as slept,
    ):
        downloaded = setup._download_json(
            "https://storage.googleapis.com/flutter_infra_release/releases/releases_macos.json"
        )

    assert downloaded == payload
    assert opened.call_count == 3
    assert [item.args[0] for item in slept.call_args_list] == [5, 15]


def test_flutter_release_manifest_download_does_not_retry_not_found() -> None:
    setup = _load_setup_module()
    not_found = urllib.error.HTTPError(
        "https://storage.googleapis.com/flutter_infra_release/releases/missing.json",
        404,
        "not found",
        {},
        None,
    )
    with (
        mock.patch.object(setup.urllib.request, "urlopen", side_effect=not_found) as opened,
        mock.patch.object(setup.time, "sleep") as slept,
    ):
        try:
            setup._download_json(not_found.url)
        except urllib.error.HTTPError as error:
            assert error.code == 404
        else:
            raise AssertionError("404 must fail without retry")

    assert opened.call_count == 1
    slept.assert_not_called()
