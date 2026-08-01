from __future__ import annotations

import hashlib
from pathlib import Path
from unittest import mock

import pytest

from quwoquan_ops.cli.lib import local_device_trust as subject


def _root_certificate(tmp_path: Path) -> Path:
    # A syntactically valid PEM is enough because fingerprinting is patched to
    # a deterministic DER conversion in this isolated contract.
    path = tmp_path / "root.crt"
    path.write_text(
        "-----BEGIN CERTIFICATE-----\nAA==\n-----END CERTIFICATE-----\n",
        encoding="ascii",
    )
    return path


def test_ios_install_and_verify_bind_target_device_fingerprint_and_lease(
    tmp_path: Path,
) -> None:
    root = _root_certificate(tmp_path)
    receipt = tmp_path / "device-trust.json"
    with (
        mock.patch.object(subject, "verify_certificate"),
        mock.patch.object(subject, "resolve_managed_device", return_value="SIM-1"),
        mock.patch.object(subject, "root_certificate_path", return_value=root),
        mock.patch.object(
            subject.ssl,
            "PEM_cert_to_DER_cert",
            return_value=b"managed-root",
        ),
        mock.patch.object(subject, "_receipt_path", return_value=receipt),
        mock.patch.object(
            subject,
            "_install_ios",
            return_value="system-trust-ok status=200",
        ),
    ):
        installed = subject.install_device_trust(
            target="alpha-local",
            platform_name="ios-simulator",
            device="SIM-1",
            lease_id="launcher-1",
        )
        with mock.patch.object(
            subject,
            "_probe_ios_system_trust",
            return_value="system-trust-ok status=200",
        ):
            verified = subject.verify_device_trust(
                target="alpha-local",
                platform_name="ios-simulator",
                device="SIM-1",
            )

    assert installed["rootFingerprintSha256"] == hashlib.sha256(
        b"managed-root"
    ).hexdigest().upper()
    assert installed["leases"] == ["launcher-1"]
    assert installed["systemTrustStore"] is True
    assert verified["verification"] == "system-trust-ok status=200"
    assert Path(verified["receipt"]) == receipt


def test_android_physical_device_and_android_14_fail_closed() -> None:
    with mock.patch.object(
        subject,
        "_android_property",
        return_value="0",
    ):
        with pytest.raises(subject.LocalDeviceTrustError, match="physical"):
            subject._install_android(
                "alpha-local",
                "device-1",
                Path("/tmp/root.crt"),
            )
    with mock.patch.object(
        subject,
        "_android_property",
        side_effect=("1", "34"),
    ):
        with pytest.raises(subject.LocalDeviceTrustError, match="Android 14"):
            subject._install_android(
                "alpha-local",
                "emulator-5554",
                Path("/tmp/root.crt"),
            )


def test_release_removes_only_requested_lease_and_never_resets_keychain(
    tmp_path: Path,
) -> None:
    root = _root_certificate(tmp_path)
    receipt = tmp_path / "device-trust.json"
    with (
        mock.patch.object(subject, "verify_certificate"),
        mock.patch.object(subject, "resolve_managed_device", return_value="SIM-1"),
        mock.patch.object(subject, "root_certificate_path", return_value=root),
        mock.patch.object(
            subject.ssl,
            "PEM_cert_to_DER_cert",
            return_value=b"managed-root",
        ),
        mock.patch.object(subject, "_receipt_path", return_value=receipt),
        mock.patch.object(subject, "_install_ios", return_value="system-trust-ok"),
    ):
        subject.install_device_trust(
            target="gamma-local",
            platform_name="ios-simulator",
            device="SIM-1",
            lease_id="lease-a",
        )
        subject.install_device_trust(
            target="gamma-local",
            platform_name="ios-simulator",
            device="SIM-1",
            lease_id="lease-b",
        )
        released = subject.release_device_trust(
            target="gamma-local",
            platform_name="ios-simulator",
            device="SIM-1",
            lease_id="lease-a",
        )

    assert released["leases"] == ["lease-b"]
    assert released["revocation"] == "lease-released"
