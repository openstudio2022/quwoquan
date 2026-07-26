from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SETUP_PATH = ROOT / "quwoquan_ops/ci/setup_flutter_sdk.py"


def _load_setup_module():
    spec = importlib.util.spec_from_file_location("setup_flutter_sdk", SETUP_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_delivery_gate_bootstrap_uses_pinned_cache_and_portal_lockfile() -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(encoding="utf-8")

    assert "subosito/flutter-action@" not in workflow
    assert "actions/cache@0057852bfaa89a56745cba8c7296529d2fc39830" in workflow
    assert "python3 quwoquan_ops/ci/setup_flutter_sdk.py resolve" in workflow
    assert "quwoquan_app/.flutter-version" in workflow
    assert "flutter pub get --enforce-lockfile" in workflow
    assert "PUB_HOSTED_URL: https://pub.flutter-io.cn" in workflow
    assert "cache-dependency-path: quwoquan_ops/portal/package-lock.json" in workflow
    assert "QWQ_DEPLOY_WORK_ROOT: ${{ runner.temp }}/quwoquan-deploy" in workflow


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
