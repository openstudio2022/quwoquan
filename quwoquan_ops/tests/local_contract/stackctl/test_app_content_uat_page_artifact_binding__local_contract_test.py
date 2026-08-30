"""App content UAT page evidence must bind the exact launched AppArtifact.

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
"""

from __future__ import annotations

import pytest

from quwoquan_ops.cli.commands.app_preflight_uat_binding import (
    _app_content_page_artifact_binding,
)
from quwoquan_ops.cli.smoke.environment_patrol_smoke.artifact_binding import (
    build_tested_app_artifact_binding,
)
from quwoquan_ops.cli.smoke.environment_patrol_smoke.artifact_binding import (
    tested_app_artifact_comparison as _tested_app_artifact_comparison,
)


def _digest(marker: str) -> str:
    return "sha256:" + marker * 64


def _valid_test_host_binding() -> dict[str, object]:
    return build_tested_app_artifact_binding(
        platform="android",
        device_id="emulator-5556",
        command_application_id="com.quwoquan.testhost.patrol",
        build_application_id="com.quwoquan.testhost.patrol",
        build_artifact_path="build/app/outputs/apk/debug/app-debug.apk",
        build_artifact_digest=_digest("2"),
        installed_application_id="com.quwoquan.testhost.patrol",
        installed_artifact_digest=_digest("2"),
        installed_readback_method="adb-pull-base-apk",
        installed_locator_digest=_digest("6"),
        host_source={
            "root": "quwoquan_app/test_host/patrol",
            "rootIdentityDigest": _digest("7"),
            "sourceDigest": _digest("8"),
            "sourceFileCount": 1,
        },
    )


def _canonical_page_comparison() -> dict[str, str]:
    return {
        "applicationId": "com.leadwise.quwoquan.nonprod.debug",
        "artifactDigest": _digest("2"),
        "sourceProjectionDigest": _digest("f"),
        "runtimeConfigPackageDigest": _digest("4"),
        "trustDigest": _digest("3"),
        "launchAttemptId": "launch-attempt-1",
    }


def _canonical_page_launch_binding() -> dict[str, str]:
    comparison = _canonical_page_comparison()
    return {
        **comparison,
        "runtimeConfigTrustEnvelopeDigest": comparison["trustDigest"],
    }


def _page_artifact_evidence(binding: dict[str, object]) -> dict[str, object]:
    comparison = _tested_app_artifact_comparison(binding)
    return {
        "patrolTarget": "test/example.dart",
        "environmentAlias": "alpha-local",
        "platform": "android",
        "deviceId": "emulator-5556",
        "testedAppArtifactBinding": {
            "status": "passed",
            "bindings": [binding],
            "comparisonProjections": [dict(comparison)],
        },
    }


def test_page_artifact_binding_rejects_spoofed_six_key_projection() -> None:
    comparison = _canonical_page_comparison()
    evidence = {
        "testedAppArtifactBinding": {
            "status": "passed",
            "bindings": [{"canonicalComparison": dict(comparison)}],
            "comparisonProjections": [dict(comparison)],
        }
    }
    with pytest.raises(ValueError, match="binding schema is invalid"):
        _app_content_page_artifact_binding(
            page_evidence={
                **evidence,
                "patrolTarget": "test/example.dart",
                "environmentAlias": "alpha-local",
                "platform": "android",
                "deviceId": "emulator-5556",
            },
            launch_binding=_canonical_page_launch_binding(),
            expected_patrol_target="test/example.dart",
            expected_environment_alias="alpha-local",
            expected_platform="android",
            expected_device_id="emulator-5556",
        )


def test_test_host_missing_canonical_keys_blocks_strict_page_uat() -> None:
    with pytest.raises(
        ValueError,
        match="missing sourceProjectionDigest,runtimeConfigPackageDigest,trustDigest,launchAttemptId",
    ):
        _app_content_page_artifact_binding(
            page_evidence=_page_artifact_evidence(_valid_test_host_binding()),
            launch_binding=_canonical_page_launch_binding(),
            expected_patrol_target="test/example.dart",
            expected_environment_alias="alpha-local",
            expected_platform="android",
            expected_device_id="emulator-5556",
        )


def test_page_artifact_binding_rejects_cross_artifact_comparison() -> None:
    binding = _valid_test_host_binding()
    comparison = binding["canonicalComparison"]
    assert isinstance(comparison, dict)
    comparison["artifactDigest"] = _digest("9")
    with pytest.raises(ValueError, match="artifactDigest is not a readback"):
        _app_content_page_artifact_binding(
            page_evidence={
                "testedAppArtifactBinding": {
                    "status": "passed",
                    "bindings": [binding],
                    "comparisonProjections": [_tested_app_artifact_comparison(binding)],
                }
            },
            launch_binding=_canonical_page_launch_binding(),
            expected_patrol_target="test/example.dart",
            expected_environment_alias="alpha-local",
            expected_platform="android",
            expected_device_id="emulator-5556",
        )


@pytest.mark.parametrize(
    ("target", "environment", "platform", "device", "detail"),
    (
        ("test/wrong.dart", "alpha-local", "android", "emulator-5556", "patrolTarget"),
        (
            "test/example.dart",
            "beta-local",
            "android",
            "emulator-5556",
            "environmentAlias",
        ),
        ("test/example.dart", "alpha-local", "ios", "emulator-5556", "platform"),
        ("test/example.dart", "alpha-local", "android", "emulator-9999", "deviceId"),
    ),
)
def test_page_artifact_binding_rejects_wrong_page_or_device_identity(
    target: str,
    environment: str,
    platform: str,
    device: str,
    detail: str,
) -> None:
    with pytest.raises(ValueError, match=detail):
        _app_content_page_artifact_binding(
            page_evidence=_page_artifact_evidence(_valid_test_host_binding()),
            launch_binding=_canonical_page_launch_binding(),
            expected_patrol_target=target,
            expected_environment_alias=environment,
            expected_platform=platform,
            expected_device_id=device,
        )
