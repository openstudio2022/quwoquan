from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import ssl
import urllib.error
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[4]
SETUP_PATH = ROOT / "quwoquan_ops/ci/setup_flutter_sdk.py"


def _load_setup_module():
    spec = importlib.util.spec_from_file_location("setup_flutter_sdk", SETUP_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_delivery_gate_bootstrap_uses_pinned_cache_and_portal_lockfile() -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(
        encoding="utf-8"
    )

    assert "subosito/flutter-action@" not in workflow
    assert "actions/cache@0057852bfaa89a56745cba8c7296529d2fc39830" in workflow
    assert "python3 quwoquan_ops/ci/setup_flutter_sdk.py resolve" in workflow
    assert "quwoquan_app/.flutter-version" in workflow
    assert "PUB_HOSTED_URL: https://pub.flutter-io.cn" in workflow
    assert "FLUTTER_STORAGE_BASE_URL: https://storage.flutter-io.cn" in workflow
    assert "flutter pub get --enforce-lockfile" in workflow
    assert "cache-dependency-path: quwoquan_ops/portal/package-lock.json" in workflow
    assert 'echo "QWQ_DEPLOY_WORK_ROOT=$RUNNER_TEMP/quwoquan-deploy"' in workflow


def test_contract_metadata_bootstrap_creates_cache_parent_before_mktemp() -> None:
    script = (
        ROOT
        / "quwoquan_service/scripts/verify/contract_graph/verify_contract_metadata.sh"
    ).read_text(encoding="utf-8")

    mkdir_index = script.index('mkdir -p "$CONTRACT_VIEW_CACHE"')
    mktemp_index = script.index('mktemp -d "${CONTRACT_VIEW_CACHE}/verify.XXXXXX"')
    assert mkdir_index < mktemp_index


def test_service_codegen_keeps_contract_view_process_scoped() -> None:
    expected_view = (
        "CONTRACT_VIEW ?= $(QWQ_OUTPUT_ROOT)/env/repo/local/"
        'service-contract-view/cache/$(shell printf %s "$$PPID")'
    )
    expected_builder = (
        "$(MAKE) -C $(SERVICE_ROOT) "
        'CONTRACT_VIEW="$(CONTRACT_VIEW)" service-contract-view'
    )
    for service in ("entity-service", "integration-service"):
        makefile = (
            ROOT / "quwoquan_service/services" / service / "Makefile"
        ).read_text(encoding="utf-8")
        assert expected_view in makefile
        assert expected_builder in makefile


def test_ff_config_contract_uses_portable_grep() -> None:
    script = (
        ROOT / "quwoquan_ops/environments/verify/verify_ff_config_contract.sh"
    ).read_text(encoding="utf-8")

    assert 'grep -nF -- "$token" "$spec"' in script
    assert "rg -n" not in script


def test_flutter_release_resolution_requires_official_checksum_and_architecture() -> (
    None
):
    setup = _load_setup_module()
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

    release = setup.select_current_release(
        manifest, channel="stable", architecture="x64"
    )

    assert release == {
        "archive": "stable/linux/flutter_linux_1.2.3-stable.tar.xz",
        "hash": "abc123",
        "sha256": "a" * 64,
        "version": "1.2.3",
    }


def test_manifest_download_retries_transient_transport_failures() -> None:
    setup = _load_setup_module()
    manifest = {"current_release": {"stable": "abc123"}, "releases": []}
    attempts: list[str] = []

    def flaky_urlopen(request, timeout):  # noqa: ANN001, ARG001
        attempts.append(request.full_url)
        if len(attempts) < 3:
            raise ssl.SSLEOFError("EOF occurred in violation of protocol")
        return contextlib.closing(io.BytesIO(json.dumps(manifest).encode("utf-8")))

    with (
        mock.patch.object(setup.urllib.request, "urlopen", flaky_urlopen),
        mock.patch.object(setup.time, "sleep") as sleep,
    ):
        assert setup._download_json("https://example.invalid/releases.json") == manifest

    assert len(attempts) == 3
    assert [call.args[0] for call in sleep.call_args_list] == [2, 4]


def test_manifest_download_does_not_retry_deterministic_http_failures() -> None:
    setup = _load_setup_module()
    attempts: list[str] = []

    def failing_urlopen(request, timeout):  # noqa: ANN001, ARG001
        attempts.append(request.full_url)
        raise urllib.error.HTTPError(
            request.full_url, 404, "Not Found", hdrs=None, fp=None
        )

    with (
        mock.patch.object(setup.urllib.request, "urlopen", failing_urlopen),
        mock.patch.object(setup.time, "sleep") as sleep,
        pytest.raises(urllib.error.HTTPError),
    ):
        setup._download_json("https://example.invalid/releases.json")

    assert len(attempts) == 1
    sleep.assert_not_called()


def test_manifest_download_fails_closed_after_exhausting_retries() -> None:
    setup = _load_setup_module()

    def always_failing(request, timeout):  # noqa: ANN001, ARG001
        raise ssl.SSLEOFError("EOF occurred in violation of protocol")

    with (
        mock.patch.object(setup.urllib.request, "urlopen", always_failing),
        mock.patch.object(setup.time, "sleep"),
        pytest.raises(RuntimeError, match="unreachable after 4 attempts"),
    ):
        setup._download_json("https://example.invalid/releases.json")


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


def test_app_test_shards_materialize_sealed_wrappers_after_sdk_install() -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(
        encoding="utf-8"
    )
    start = workflow.index("  quwoquan_app_tests:\n")
    end = workflow.index("\n  quwoquan_app_serial:\n", start)
    app_tests = workflow[start:end]
    materialize = (
        "python3 quwoquan_ops/ci/setup_flutter_sdk.py "
        "materialize-gradle-wrappers"
    )

    assert app_tests.count(materialize) == 1
    assert (
        app_tests.index("Install verified Flutter SDK")
        < app_tests.index(materialize)
    )
    assert app_tests.index(materialize) < app_tests.index(
        "Resolve locked App dependencies"
    )
    resolve_android = "Materialize App shared contract Android dependencies"
    assert app_tests.count(resolve_android) == 1
    android_step = app_tests[
        app_tests.index(resolve_android) : app_tests.index(
            "Install repository test native dependencies"
        )
    ]
    assert "if: ${{ matrix.shard_index == 0 }}" in android_step
    assert "working-directory: quwoquan_app/android" in android_step
    assert ":app:testNonprodDebugUnitTest" in android_step
    assert "--tests com.quwoquan.quwoquan_app.RuntimeConfigPackageStoreTest" in android_step
    assert ":app:dependencies" not in android_step
    assert app_tests.index(materialize) < app_tests.index(resolve_android)
    assert app_tests.index(resolve_android) < app_tests.index(
        "Gate (quwoquan_app tests shard)"
    )


def test_gradle_wrapper_bootstrap_delegates_to_pinned_sealed_materializer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup = _load_setup_module()
    project = tmp_path / "repo"
    for relative in (
        "quwoquan_app/android",
        "quwoquan_app/test_host/patrol/android",
    ):
        (project / relative).mkdir(parents=True)
    flutter_identity = {
        "executable": "/pinned/flutter/bin/flutter",
        "flutterVersion": "3.47.0",
        "commandResolutionDigest": "sha256:" + "a" * 64,
    }
    calls: list[tuple[Path, list[Path], object]] = []

    class FacadeError(Exception):
        pass

    monkeypatch.setattr(
        setup,
        "_gradle_wrapper_tools",
        lambda: (
            FacadeError,
            lambda environment: flutter_identity,
            lambda root: (
                setup.argparse.Namespace(
                    gradle_root=root / "quwoquan_app/android"
                ),
                setup.argparse.Namespace(
                    gradle_root=(
                        root / "quwoquan_app/test_host/patrol/android"
                    )
                ),
            ),
            lambda root, roots, identity: calls.append((root, roots, identity))
            or ({}, {}),
        ),
    )

    result = setup.materialize_gradle_wrappers(
        setup.argparse.Namespace(project_root=str(project))
    )

    assert result == 0
    assert calls == [
        (
            project,
            [
                project / "quwoquan_app/android",
                project / "quwoquan_app/test_host/patrol/android",
            ],
            flutter_identity,
        )
    ]


def test_gradle_wrapper_subcommand_does_not_require_tool_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = _load_setup_module()
    monkeypatch.delenv("RUNNER_TOOL_CACHE", raising=False)
    monkeypatch.setattr(setup, "materialize_gradle_wrappers", lambda _args: 0)
    monkeypatch.setattr(
        setup.sys,
        "argv",
        [
            "setup_flutter_sdk.py",
            "materialize-gradle-wrappers",
            "--project-root",
            str(ROOT),
        ],
    )

    assert setup.main() == 0
