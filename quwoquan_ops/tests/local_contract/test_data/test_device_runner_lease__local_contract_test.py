# spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/spec.md#sit-004
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from quwoquan_ops.ci.device_runner_lease import acquire, release


HOST_DIGEST = "sha256:" + "1" * 64


def _acquire(root: Path, platform: str = "android") -> tuple[dict[str, str], Path]:
    output = root / f"{platform}.output"
    evidence = root / f"{platform}.lease.json"
    with patch(
        "quwoquan_ops.ci.device_runner_lease.host_digest",
        return_value=HOST_DIGEST,
    ), patch(
        "quwoquan_ops.ci.device_runner_lease.select_device",
        return_value={
            "id": f"{platform}-device",
            "targetPlatform": "ios" if platform == "ios" else "android-arm64",
            "emulator": False,
            "isSupported": True,
        },
    ):
        values = acquire(
            platform=platform,
            expected_host_digest=HOST_DIGEST,
            runner_label=f"mobile-{platform}",
            run_id="123",
            run_attempt="1",
            preferred_device_id="",
            lease_root=root / "leases",
            evidence_output=evidence,
            github_output=output,
        )
    return values, evidence


def test_device_lease_is_atomic_host_bound_and_releasable() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        values, evidence_path = _acquire(root)
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))

        assert "schema" not in evidence
        assert evidence["status"] == "held"
        assert evidence["hostDigest"] == HOST_DIGEST
        assert evidence["runnerLabel"] == "mobile-android"
        assert evidence["deviceIdDigest"] == values["device_id_digest"]
        assert evidence["deviceClass"] == "physical"
        assert evidence["deviceRegistered"] is True
        assert evidence["targetPlatform"] == "android-arm64"
        assert Path(evidence["leaseOwnerRef"]).is_file()
        assert "android-device" not in evidence_path.read_text(encoding="utf-8")

        release(
            lease_evidence=evidence_path,
            lease_token=values["lease_token"],
            lease_root=root / "leases",
        )
        assert not any((root / "leases").iterdir())


def test_device_lease_rejects_second_owner_and_wrong_release_token() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        values, evidence_path = _acquire(root)

        with pytest.raises(ValueError, match="active lease"):
            _acquire(root)
        with pytest.raises(ValueError, match="ownership token"):
            release(
                lease_evidence=evidence_path,
                lease_token="wrong",
                lease_root=root / "leases",
            )

        release(
            lease_evidence=evidence_path,
            lease_token=values["lease_token"],
            lease_root=root / "leases",
        )


def test_device_lease_rejects_runner_host_and_label_drift() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        with patch(
            "quwoquan_ops.ci.device_runner_lease.host_digest",
            return_value="sha256:" + "2" * 64,
        ), pytest.raises(ValueError, match="not the Beta stack host"):
            acquire(
                platform="ios",
                expected_host_digest=HOST_DIGEST,
                runner_label="mobile-ios",
                run_id="123",
                run_attempt="1",
                preferred_device_id="",
                lease_root=root / "leases",
                evidence_output=root / "lease.json",
                github_output=root / "output",
            )

        with pytest.raises(ValueError, match="runner label"):
            acquire(
                platform="ios",
                expected_host_digest=HOST_DIGEST,
                runner_label="mobile-android",
                run_id="123",
                run_attempt="1",
                preferred_device_id="",
                lease_root=root / "leases",
                evidence_output=root / "lease.json",
                github_output=root / "output",
            )


def test_device_lease_source_has_no_contract_version_identity() -> None:
    source = (
        Path(__file__).resolve().parents[4]
        / "quwoquan_ops/ci/device_runner_lease.py"
    ).read_text(encoding="utf-8")
    for forbidden in ("schemaVersion", "contractVersion", "registryRevision"):
        assert forbidden not in source
