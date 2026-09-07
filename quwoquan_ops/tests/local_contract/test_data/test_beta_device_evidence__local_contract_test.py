# spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/spec.md#sit-004
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from quwoquan_ops.ci.render_beta_device_evidence import (
    merge_platform_bundles,
    render_platform_bundle,
    render_stack_bundle,
)


ROOT = Path(__file__).resolve().parents[4]
CANDIDATE = "sha256:" + "c" * 64
GIT_SHA = "a" * 40
TREE_DIGEST = "sha1:" + "b" * 40
ARTIFACT_DIGEST = "sha256:" + "d" * 64
HOST_DIGEST = "sha256:" + "1" * 64
STACK_DIGEST = "sha256:" + "2" * 64
ANDROID_DIGEST = "sha256:" + "3" * 64
IOS_DIGEST = "sha256:" + "4" * 64
SERVICE_DIGEST = "sha256:" + "e" * 64
CONTRACT_GRAPH_DIGEST = "sha256:" + "9" * 64


def _manifest() -> dict:
    return {
        "status": "qualified",
        "candidateId": CANDIDATE,
        "artifactDigest": ARTIFACT_DIGEST,
        "contractGraphDigest": CONTRACT_GRAPH_DIGEST,
        "source": {
            "gitSha": GIT_SHA,
            "treeDigest": TREE_DIGEST,
            "repository": "owner/repo",
        },
        "environmentArtifacts": {
            "beta": {
                "environment": "beta",
                "images": {
                    "gateway": {
                        "ref": "ghcr.io/owner/repo/gateway@" + SERVICE_DIGEST,
                        "digest": SERVICE_DIGEST,
                    }
                },
            }
        },
    }


def _stack_reports(root: Path) -> dict[str, Path]:
    payloads = {
        "package": {
            "command": "package",
            "env": "beta",
            "target": "beta-local",
            "status": "ok",
            "candidateId": CANDIDATE,
            "artifactDigest": ARTIFACT_DIGEST,
            "sourceGitSha": GIT_SHA,
            "sourceTreeDigest": TREE_DIGEST,
            "releaseInputClassification": "commercial_inputs",
            "contractGraphDigest": CONTRACT_GRAPH_DIGEST,
            "endedAt": "2026-07-28T00:00:10Z",
        },
        "up": {
            "command": "up",
            "target": "beta-local",
            "steps": [{"exitCode": 0}],
            "formalRelease": True,
            "releaseInputClassification": "commercial_inputs",
            "contractGraphDigest": CONTRACT_GRAPH_DIGEST,
            "runtimeMode": "immutable-oci",
            "runtimeCandidateDigest": CANDIDATE,
            "runtimeImages": {
                "gateway": {
                    "ref": "ghcr.io/owner/repo/gateway@" + SERVICE_DIGEST,
                    "digest": SERVICE_DIGEST,
                    "containerId": "container-gateway",
                    "runtimeImageId": "sha256:" + "f" * 64,
                    "status": "running",
                    "health": "healthy",
                }
            },
            "destructiveRepairPerformed": False,
            "destructiveActions": [],
            "endedAt": "2026-07-28T00:00:11Z",
        },
        "health": {
            "command": "health",
            "target": "beta-local",
            "checks": [{"ok": True}],
            "findings": [],
            "endedAt": "2026-07-28T00:00:12Z",
        },
        "verify": {
            "command": "verify",
            "env": "beta",
            "target": "beta-local",
            "status": "passed",
            "endedAt": "2026-07-28T00:00:13Z",
        },
    }
    paths: dict[str, Path] = {}
    for name, payload in payloads.items():
        path = root / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        paths[name] = path
    return paths


def _stack_bundle(root: Path) -> tuple[Path, dict]:
    bundle = root / "bundle-stack"
    with patch("quwoquan_ops.ci.render_beta_device_evidence.validate_historical_release_snapshot"):
        payload = render_stack_bundle(
            manifest=_manifest(),
            host_digest=HOST_DIGEST,
            stack_paths=_stack_reports(root / "source-stack"),
            bundle_dir=bundle,
        )
    return bundle, payload


def _platform_bundle(
    root: Path,
    platform: str,
    *,
    host_digest: str = HOST_DIGEST,
    started_at: str | None = None,
    ended_at: str | None = None,
    report_ended_at: str = "2026-07-28T00:00:20Z",
) -> tuple[Path, dict]:
    index = 0 if platform == "android" else 1
    source = root / f"source-{platform}"
    report_root = source / "device-matrix"
    report_root.mkdir(parents=True)
    (report_root / f"assistant-{platform}.json").write_text(
        json.dumps(
            {
                "status": "passed",
                "endedAt": report_ended_at,
                "devices": [{"platform": platform}],
                "runs": [{"status": "passed"}],
            }
        ),
        encoding="utf-8",
    )
    (report_root / f"assistant-{platform}.log").write_text(
        "passed\n", encoding="utf-8"
    )
    lease = source / "device-lease.json"
    lease.write_text(
        json.dumps(
            {
                "status": "held",
                "platform": platform,
                "hostDigest": host_digest,
                "deviceIdDigest": "sha256:" + str(5 + index) * 64,
                "leaseId": "sha256:" + str(7 + index) * 64,
                "runnerLabel": f"mobile-{platform}",
                "acquiredAt": f"2026-07-28T00:00:{14 + index:02d}Z",
            }
        ),
        encoding="utf-8",
    )
    execution_start = started_at or f"2026-07-28T00:00:{16 + index:02d}Z"
    execution_end = ended_at or f"2026-07-28T00:00:{25 + index:02d}Z"
    bundle = root / f"bundle-{platform}"
    with patch("quwoquan_ops.ci.render_beta_device_evidence.validate_historical_release_snapshot"):
        payload = render_platform_bundle(
            manifest=_manifest(),
            platform=platform,
            lease_evidence_path=lease,
            execution_started_at=execution_start,
            execution_ended_at=execution_end,
            device_report_root=report_root,
            bundle_dir=bundle,
        )
    return bundle, payload


def _merge(
    root: Path,
    *,
    ios_host_digest: str = HOST_DIGEST,
    ios_started_at: str | None = None,
    ios_ended_at: str | None = None,
) -> dict:
    stack, _ = _stack_bundle(root)
    android, _ = _platform_bundle(root, "android")
    ios, _ = _platform_bundle(
        root,
        "ios",
        host_digest=ios_host_digest,
        started_at=ios_started_at,
        ended_at=ios_ended_at,
        report_ended_at=(
            "2026-07-28T00:00:28Z"
            if ios_started_at == "2026-07-28T00:00:26Z"
            else "2026-07-28T00:00:20Z"
        ),
    )
    with patch("quwoquan_ops.ci.render_beta_device_evidence.validate_historical_release_snapshot"):
        return merge_platform_bundles(
            manifest=_manifest(),
            expected_host_digest=HOST_DIGEST,
            stack_bundle=stack,
            stack_ref="ghcr.io/owner/repo/beta-stack@" + STACK_DIGEST,
            stack_digest=STACK_DIGEST,
            bundles={"android": android, "ios": ios},
            refs={
                "android": "ghcr.io/owner/repo/beta-android@" + ANDROID_DIGEST,
                "ios": "ghcr.io/owner/repo/beta-ios@" + IOS_DIGEST,
            },
            digests={"android": ANDROID_DIGEST, "ios": IOS_DIGEST},
        )


def test_stack_and_platform_bundles_have_distinct_responsibilities() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        stack_bundle, stack = _stack_bundle(root)
        platform_bundle, platform = _platform_bundle(root, "android")

        assert set(stack["stackEvidence"]) == {"package", "up", "health", "verify"}
        assert "reports" not in stack
        assert "schema" not in platform
        assert "stackEvidence" not in platform
        assert platform["deviceLease"]["runnerLabel"] == "mobile-android"
        assert platform["reports"]
        assert (stack_bundle / "stack.json").is_file()
        assert (platform_bundle / "platform.json").is_file()


def test_stack_bundle_rejects_source_built_or_destructively_repaired_runtime() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        reports = _stack_reports(root / "source-stack")
        up = json.loads(reports["up"].read_text(encoding="utf-8"))
        up["runtimeMode"] = "source-build"
        up["destructiveRepairPerformed"] = True
        up["destructiveActions"] = ["wipe"]
        reports["up"].write_text(json.dumps(up), encoding="utf-8")
        with patch(
            "quwoquan_ops.ci.render_beta_device_evidence.validate_historical_release_snapshot"
        ), pytest.raises(ValueError, match="immutable candidate runtime"):
            render_stack_bundle(
                manifest=_manifest(),
                host_digest=HOST_DIGEST,
                stack_paths=reports,
                bundle_dir=root / "bundle-stack",
            )


@pytest.mark.parametrize(
    "classification",
    ["research_inputs", "mixed_inputs"],
)
def test_stack_bundle_rejects_noncommercial_release_inputs(
    classification: str,
) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        reports = _stack_reports(root / "source-stack")
        up = json.loads(reports["up"].read_text(encoding="utf-8"))
        up["releaseInputClassification"] = classification
        reports["up"].write_text(json.dumps(up), encoding="utf-8")
        with patch(
            "quwoquan_ops.ci.render_beta_device_evidence.validate_historical_release_snapshot"
        ), pytest.raises(ValueError, match="commercial release inputs"):
            render_stack_bundle(
                manifest=_manifest(),
                host_digest=HOST_DIGEST,
                stack_paths=reports,
                bundle_dir=root / "bundle-stack",
            )


@pytest.mark.parametrize("label", ["package", "up"])
def test_stack_bundle_rejects_contract_graph_drift(label: str) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        reports = _stack_reports(root / "source-stack")
        payload = json.loads(reports[label].read_text(encoding="utf-8"))
        payload["contractGraphDigest"] = "sha256:" + "8" * 64
        reports[label].write_text(json.dumps(payload), encoding="utf-8")
        with patch(
            "quwoquan_ops.ci.render_beta_device_evidence.validate_historical_release_snapshot"
        ), pytest.raises(ValueError, match="ContractGraph"):
            render_stack_bundle(
                manifest=_manifest(),
                host_digest=HOST_DIGEST,
                stack_paths=reports,
                bundle_dir=root / "bundle-stack",
            )


def test_merge_requires_exact_oci_refs_one_host_and_parallel_device_leases() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        payload = _merge(Path(temporary))

    assert payload["schema"] == "release-device-matrix-evidence"
    assert payload["candidateId"] == CANDIDATE
    assert set(payload["platforms"]) == {"android", "ios"}
    assert payload["stackEvidence"]["evidenceRef"].endswith("@" + STACK_DIGEST)
    assert all(
        entry["evidenceRef"].endswith("@" + entry["evidenceDigest"])
        for entry in payload["platformEvidence"].values()
    )
    executions = [entry["execution"] for entry in payload["platformEvidence"].values()]
    assert executions[0]["startedAt"] < executions[1]["endedAt"]
    assert executions[1]["startedAt"] < executions[0]["endedAt"]


def test_merge_rejects_tampered_platform_payload() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        stack, _ = _stack_bundle(root)
        android, _ = _platform_bundle(root, "android")
        ios, _ = _platform_bundle(root, "ios")
        (ios / "raw" / "device-lease.json").write_text("{}", encoding="utf-8")

        with patch(
            "quwoquan_ops.ci.render_beta_device_evidence.validate_historical_release_snapshot"
        ), pytest.raises(ValueError, match="digest mismatch"):
            merge_platform_bundles(
                manifest=_manifest(),
                expected_host_digest=HOST_DIGEST,
                stack_bundle=stack,
                stack_ref="ghcr.io/owner/repo/beta-stack@" + STACK_DIGEST,
                stack_digest=STACK_DIGEST,
                bundles={"android": android, "ios": ios},
                refs={
                    "android": "ghcr.io/owner/repo/beta-android@" + ANDROID_DIGEST,
                    "ios": "ghcr.io/owner/repo/beta-ios@" + IOS_DIGEST,
                },
                digests={"android": ANDROID_DIGEST, "ios": IOS_DIGEST},
            )


def test_merge_rejects_different_hosts_and_serial_execution() -> None:
    with tempfile.TemporaryDirectory() as temporary, pytest.raises(
        ValueError, match="one host"
    ):
        _merge(Path(temporary), ios_host_digest="sha256:" + "9" * 64)
    with tempfile.TemporaryDirectory() as temporary, pytest.raises(
        ValueError, match="did not overlap"
    ):
        _merge(
            Path(temporary),
            ios_started_at="2026-07-28T00:00:26Z",
            ios_ended_at="2026-07-28T00:00:30Z",
        )


def test_merge_rejects_a_second_platform_schema_identity() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        stack, _ = _stack_bundle(root)
        android, _ = _platform_bundle(root, "android")
        ios, payload = _platform_bundle(root, "ios")
        payload["schema"] = "release-device-platform-evidence"
        (ios / "platform.json").write_text(json.dumps(payload), encoding="utf-8")

        with patch(
            "quwoquan_ops.ci.render_beta_device_evidence.validate_historical_release_snapshot"
        ), pytest.raises(ValueError, match="second schema identity"):
            merge_platform_bundles(
                manifest=_manifest(),
                expected_host_digest=HOST_DIGEST,
                stack_bundle=stack,
                stack_ref="ghcr.io/owner/repo/beta-stack@" + STACK_DIGEST,
                stack_digest=STACK_DIGEST,
                bundles={"android": android, "ios": ios},
                refs={
                    "android": "ghcr.io/owner/repo/beta-android@" + ANDROID_DIGEST,
                    "ios": "ghcr.io/owner/repo/beta-ios@" + IOS_DIGEST,
                },
                digests={"android": ANDROID_DIGEST, "ios": IOS_DIGEST},
            )


def test_platform_evidence_has_no_contract_version_identity() -> None:
    source = (ROOT / "quwoquan_ops/ci/render_beta_device_evidence.py").read_text(
        encoding="utf-8"
    )
    for forbidden in (
        "schemaVersion",
        "contractVersion",
        "registryRevision",
        "release-device-matrix-evidence-v",
    ):
        assert forbidden not in source
