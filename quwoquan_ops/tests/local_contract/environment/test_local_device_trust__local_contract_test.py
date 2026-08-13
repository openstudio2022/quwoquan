from __future__ import annotations

import hashlib
from copy import deepcopy
from pathlib import Path
from unittest import mock

import pytest

from quwoquan_ops.cli.lib import local_device_trust as subject
from quwoquan_ops.cli.lib import local_device_android_trust as trust_overlay_subject
from quwoquan_ops.cli.lib import local_device_resolver as resolver_subject


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

    assert (
        installed["rootFingerprintSha256"]
        == hashlib.sha256(b"managed-root").hexdigest().upper()
    )
    assert installed["leases"] == ["launcher-1"]
    assert installed["systemTrustStore"] is True
    assert verified["verification"] == "system-trust-ok status=200"
    assert Path(verified["receipt"]) == receipt


def test_ios_install_can_defer_endpoint_probe_for_app_startup(
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
            return_value="system-root-installed; endpoint-probe-deferred",
        ) as install_ios,
    ):
        installed = subject.install_device_trust(
            target="alpha-local",
            platform_name="ios-simulator",
            device="SIM-1",
            lease_id="direct-debug",
            endpoint_probe=False,
        )

    install_ios.assert_called_once_with(
        "alpha-local",
        "SIM-1",
        root,
        endpoint_probe=False,
    )
    assert installed["endpointProbe"] == "deferred"
    assert installed["systemTrustStore"] is True


def _android_identity(
    *,
    api_level: int = 35,
    build_type: str = "userdebug",
    debuggable: bool = True,
    boot_id: str = "11111111-2222-3333-4444-555555555555",
) -> dict[str, object]:
    return {
        "apiLevel": api_level,
        "buildType": build_type,
        "debuggable": debuggable,
        "buildFingerprint": "quwoquan/sdk_gphone64_arm64/test:userdebug/dev-keys",
        "bootId": boot_id,
    }


def test_android_physical_device_and_android_14_user_image_fail_closed() -> None:
    with (
        mock.patch.object(
            subject,
            "_android_property",
            return_value="0",
        ),
        pytest.raises(subject.LocalDeviceTrustError, match="physical"),
    ):
        subject._install_android(
            "alpha-local",
            "device-1",
            Path("/tmp/root.crt"),
        )
    with (
        mock.patch.object(subject, "_android_root") as android_root,
        pytest.raises(subject.AndroidSystemTrustUnavailable, match="userdebug or eng"),
    ):
        subject._install_android(
            "alpha-local",
            "emulator-5554",
            Path("/tmp/root.crt"),
            identity=_android_identity(build_type="user", debuggable=False),
        )
    android_root.assert_not_called()


def test_android_conscrypt_staging_uses_unique_versioned_apex_source() -> None:
    mount_output = (
        "/dev/block/dm-32 on /apex/com.android.conscrypt@352090000 "
        "type ext4 (ro,seclabel)\n"
        "/dev/block/dm-32 on /apex/com.android.conscrypt "
        "type ext4 (ro,seclabel)"
    )
    with mock.patch.object(
        subject,
        "_require_success",
        return_value=mock.Mock(stdout=mount_output, returncode=0),
    ):
        source_path = subject._android_conscrypt_source_cacerts("emulator-5556")

    assert source_path == "/apex/com.android.conscrypt@352090000/cacerts"


def test_android_14_managed_avd_installs_dual_trust_stores_and_resolver_overlay(
    tmp_path: Path,
) -> None:
    root = _root_certificate(tmp_path)
    identity = _android_identity()
    namespaces = [
        {"namespace": "mnt:[1001]", "representativePid": 1},
        {"namespace": "mnt:[1002]", "representativePid": 100},
    ]
    source_apex_digest = "A" * 64
    incremental_apex_digest = "B" * 64
    source_legacy_digest = "C" * 64
    incremental_legacy_digest = "D" * 64
    handoff = {
        "target": "alpha-local",
        "address": "127.0.0.1",
        "hosts": ["api.alpha.quwoquan.com"],
        "handoffDigest": f"sha256:{'a' * 64}",
    }
    overlay = {"handoffDigest": handoff["handoffDigest"]}
    with (
        mock.patch.object(subject, "_android_root"),
        mock.patch.object(subject, "_android_subject_hash", return_value="b7744e41"),
        mock.patch.object(
            subject,
            "_android_conscrypt_source_cacerts",
            return_value="/apex/com.android.conscrypt@352090000/cacerts",
        ),
        mock.patch.object(
            subject,
            "remote_tree_sha256",
            side_effect=(
                source_apex_digest,
                source_apex_digest,
                incremental_apex_digest,
                source_legacy_digest,
                source_legacy_digest,
                incremental_legacy_digest,
            ),
        ),
        mock.patch.object(subject, "_android_zygote_pids", return_value=[100, 200]),
        mock.patch.object(
            subject,
            "_android_mount_namespace_evidence",
            return_value=namespaces,
        ),
        mock.patch.object(subject, "materialize_handoff", return_value=handoff),
        mock.patch.object(
            subject,
            "install_android_host_overlay",
            return_value=overlay,
        ) as install_overlay,
        mock.patch.object(
            subject,
            "verify_runtime_trust_stores",
            return_value=2,
        ) as verify_stores,
        mock.patch.object(
            subject,
            "_require_success",
            return_value=mock.Mock(stdout="", returncode=0),
        ) as require_success,
    ):
        installed = subject._install_android(
            "alpha-local",
            "emulator-5556",
            root,
            identity=identity,
        )

    expected_digest = hashlib.sha256(root.read_bytes()).hexdigest().upper()
    stores = installed["androidTrustStores"]
    assert [store["kind"] for store in stores] == [
        "conscrypt-apex",
        "legacy-system",
    ]
    assert [store["sourcePath"] for store in stores] == [
        "/apex/com.android.conscrypt@352090000/cacerts",
        "/system/etc/security/cacerts",
    ]
    assert [store["trustStorePath"] for store in stores] == [
        "/apex/com.android.conscrypt/cacerts",
        "/system/etc/security/cacerts",
    ]
    assert [store["sourceStoreSha256"] for store in stores] == [
        source_apex_digest,
        source_legacy_digest,
    ]
    assert [store["incrementalStoreSha256"] for store in stores] == [
        incremental_apex_digest,
        incremental_legacy_digest,
    ]
    assert all(store["installedCertificateSha256"] == expected_digest for store in stores)
    assert all(store["mountNamespaces"] == namespaces for store in stores)
    assert installed["androidHostOverlay"] == overlay
    assert installed["bootId"] == identity["bootId"]
    assert "mount-namespaces-verified=2" in str(installed["verification"])
    verify_stores.assert_called_once()
    install_overlay.assert_called_once()
    mount_commands = [
        call.args[0]
        for call in require_success.call_args_list
        if "mount" in call.args[0]
    ]
    assert [command[6] for command in mount_commands] == ["1", "100", "1", "100"]
    assert [command[-1] for command in mount_commands] == [
        "/apex/com.android.conscrypt/cacerts",
        "/apex/com.android.conscrypt/cacerts",
        "/system/etc/security/cacerts",
        "/system/etc/security/cacerts",
    ]
    copy_commands = [
        call.args[0]
        for call in require_success.call_args_list
        if "cp" in call.args[0]
    ]
    assert [command[-2] for command in copy_commands] == [
        "/apex/com.android.conscrypt@352090000/cacerts/.",
        "/system/etc/security/cacerts/.",
    ]


def test_android_verify_rejects_boot_drift_before_reusing_receipt(
    tmp_path: Path,
) -> None:
    root = _root_certificate(tmp_path)
    receipt = {
        **_android_identity(),
        "trustStorePath": "/apex/com.android.conscrypt/cacerts/b7744e41.0",
        "installedCertificateSha256": hashlib.sha256(root.read_bytes())
        .hexdigest()
        .upper(),
    }
    current = _android_identity(boot_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    with (
        mock.patch.object(subject, "_android_identity", return_value=current),
        pytest.raises(subject.LocalDeviceTrustError, match="identity mismatch"),
    ):
        subject._verify_android_system_trust(
            "emulator-5556",
            root,
            receipt,
        )


def test_android_verify_proves_dual_stores_resolver_and_current_namespaces(
    tmp_path: Path,
) -> None:
    root = _root_certificate(tmp_path)
    identity = _android_identity()
    expected_digest = hashlib.sha256(root.read_bytes()).hexdigest().upper()
    namespaces = [
        {"namespace": "mnt:[1001]", "representativePid": 1},
        {"namespace": "mnt:[1002]", "representativePid": 100},
    ]
    stage_root = subject._android_trust_stage_root(
        "alpha-local",
        identity,
        expected_digest,
    )
    layouts = (
        (
            "conscrypt-apex",
            "/apex/com.android.conscrypt@352090000/cacerts",
            f"{stage_root}/apex-cacerts",
            "/apex/com.android.conscrypt/cacerts",
        ),
        (
            "legacy-system",
            "/system/etc/security/cacerts",
            f"{stage_root}/legacy-cacerts",
            "/system/etc/security/cacerts",
        ),
    )
    stores = [
        {
            "kind": kind,
            "sourcePath": source,
            "sourceStoreSha256": "A" * 64,
            "stagedStorePath": staged,
            "incrementalStoreSha256": "B" * 64,
            "trustStorePath": trust_store,
            "certificatePath": f"{trust_store}/b7744e41.0",
            "installedCertificateSha256": expected_digest,
            "mountNamespaces": namespaces,
        }
        for kind, source, staged, trust_store in layouts
    ]
    receipt = {
        **identity,
        "target": "alpha-local",
        "androidTrustStores": stores,
        "androidHostOverlay": {"schema": "test-overlay"},
    }
    with (
        mock.patch.object(subject, "_android_identity", return_value=identity),
        mock.patch.object(subject, "_android_subject_hash", return_value="b7744e41"),
        mock.patch.object(
            subject,
            "_android_conscrypt_source_cacerts",
            return_value="/apex/com.android.conscrypt@352090000/cacerts",
        ),
        mock.patch.object(subject, "_android_zygote_pids", return_value=[100]),
        mock.patch.object(
            subject,
            "_android_mount_namespace_evidence",
            return_value=namespaces,
        ),
        mock.patch.object(
            subject,
            "verify_runtime_trust_stores",
            return_value=2,
        ) as verify_stores,
        mock.patch.object(
            subject,
            "load_handoff",
            return_value={"handoffDigest": f"sha256:{'a' * 64}"},
        ),
        mock.patch.object(subject, "verify_android_host_overlay") as verify_overlay,
    ):
        proof = subject._verify_android_system_trust(
            "emulator-5556",
            root,
            receipt,
        )

    assert proof == (
        "dual-system-trust-ok; trust-stores-verified=2; "
        "mount-namespaces-verified=2; resolver-overlay-verified"
    )
    verify_stores.assert_called_once_with(
        "emulator-5556",
        stores,
        namespaces,
        expected_digest,
        remote_sha256=subject._android_remote_sha256,
    )
    verify_overlay.assert_called_once()


def test_android_install_reuses_exact_verified_receipt_without_device_mutation(
    tmp_path: Path,
) -> None:
    root = _root_certificate(tmp_path)
    receipt_path = tmp_path / "device-trust.json"
    identity = _android_identity()
    fingerprint = hashlib.sha256(b"managed-root").hexdigest().upper()
    receipt_path.write_text(
        subject.json.dumps(
            {
                "schema": subject.SCHEMA,
                "target": "alpha-local",
                "platform": "android-emulator",
                "device": "emulator-5556",
                "rootFingerprintSha256": fingerprint,
                "systemTrustStore": True,
                "status": "installed",
                "leases": ["existing-lease"],
                **identity,
            }
        ),
        encoding="utf-8",
    )
    with (
        mock.patch.object(subject, "verify_certificate"),
        mock.patch.object(
            subject,
            "resolve_managed_device",
            return_value="emulator-5556",
        ),
        mock.patch.object(subject, "root_certificate_path", return_value=root),
        mock.patch.object(
            subject.ssl,
            "PEM_cert_to_DER_cert",
            return_value=b"managed-root",
        ),
        mock.patch.object(subject, "_receipt_path", return_value=receipt_path),
        mock.patch.object(subject, "_android_identity", return_value=identity),
        mock.patch.object(
            subject,
            "_verify_android_system_trust",
            return_value="dual-system-trust-ok",
        ) as verify_existing,
        mock.patch.object(subject, "_install_android") as install_android,
    ):
        installed = subject.install_device_trust(
            target="alpha-local",
            platform_name="android-emulator",
            device="emulator-5556",
            lease_id="new-lease",
        )

    verify_existing.assert_called_once_with("emulator-5556", root, mock.ANY)
    install_android.assert_not_called()
    assert installed["verification"] == "dual-system-trust-ok"
    assert installed["leases"] == ["existing-lease", "new-lease"]


def test_android_install_fails_before_mutation_when_exact_receipt_is_invalid(
    tmp_path: Path,
) -> None:
    root = _root_certificate(tmp_path)
    receipt_path = tmp_path / "device-trust.json"
    identity = _android_identity()
    receipt_path.write_text(
        subject.json.dumps(
            {
                "schema": subject.SCHEMA,
                "target": "alpha-local",
                "platform": "android-emulator",
                "device": "emulator-5556",
                "rootFingerprintSha256": hashlib.sha256(b"managed-root")
                .hexdigest()
                .upper(),
                "systemTrustStore": True,
                "status": "installed",
                "leases": [],
                **identity,
            }
        ),
        encoding="utf-8",
    )
    with (
        mock.patch.object(subject, "verify_certificate"),
        mock.patch.object(
            subject,
            "resolve_managed_device",
            return_value="emulator-5556",
        ),
        mock.patch.object(subject, "root_certificate_path", return_value=root),
        mock.patch.object(
            subject.ssl,
            "PEM_cert_to_DER_cert",
            return_value=b"managed-root",
        ),
        mock.patch.object(subject, "_receipt_path", return_value=receipt_path),
        mock.patch.object(subject, "_android_identity", return_value=identity),
        mock.patch.object(
            subject,
            "_verify_android_system_trust",
            side_effect=subject.LocalDeviceTrustError("mounted store drift"),
        ),
        mock.patch.object(subject, "_install_android") as install_android,
        pytest.raises(subject.LocalDeviceTrustError, match="mounted store drift"),
    ):
        subject.install_device_trust(
            target="alpha-local",
            platform_name="android-emulator",
            device="emulator-5556",
            lease_id="new-lease",
        )

    install_android.assert_not_called()


def test_android_dual_store_verifier_rejects_any_namespace_digest_drift() -> None:
    expected_certificate = "E" * 64
    base_digest = "A" * 64
    incremental_digest = "B" * 64
    stores = [
        {
            "kind": "legacy-system",
            "sourceStoreSha256": base_digest,
            "incrementalStoreSha256": incremental_digest,
            "stagedStorePath": "/stage/legacy-cacerts",
            "trustStorePath": "/system/etc/security/cacerts",
            "certificatePath": "/system/etc/security/cacerts/b7744e41.0",
        }
    ]
    namespaces = [{"namespace": "mnt:[1001]", "representativePid": 1}]
    with (
        mock.patch.object(
            trust_overlay_subject,
            "remote_tree_sha256",
            side_effect=(
                base_digest,
                incremental_digest,
                "F" * 64,
            ),
        ),
        pytest.raises(
            trust_overlay_subject.AndroidTrustOverlayError,
            match="namespace pid=1",
        ),
    ):
        trust_overlay_subject.verify_runtime_trust_stores(
            "emulator-5556",
            stores,
            namespaces,
            expected_certificate,
            remote_sha256=lambda *_args, **_kwargs: expected_certificate,
        )


def test_android_resolver_overlay_preserves_source_and_binds_each_namespace() -> None:
    target = "alpha-local"
    hosts = list(resolver_subject.canonical_hosts(target))
    handoff = {
        "target": target,
        "address": "127.0.0.1",
        "hosts": hosts,
        "handoffDigest": f"sha256:{'a' * 64}",
    }
    namespaces = [
        {"namespace": "mnt:[1001]", "representativePid": 1},
        {"namespace": "mnt:[1002]", "representativePid": 100},
    ]
    source = b"127.0.0.1 localhost\n::1 localhost\n"
    overlay = resolver_subject._overlay_bytes(target, hosts, source)
    source_digest = hashlib.sha256(source).hexdigest().upper()
    overlay_digest = hashlib.sha256(overlay).hexdigest().upper()
    pushed: dict[str, bytes] = {}
    commands: list[list[str]] = []

    def fake_adb(
        _device: str,
        arguments: list[str],
        *,
        action: str,
        timeout: int = 90,
    ) -> mock.Mock:
        del action, timeout
        commands.append(arguments)
        if arguments[0] == "push":
            pushed[arguments[2]] = Path(arguments[1]).read_bytes()
        return mock.Mock(stdout="", returncode=0)

    def fake_digest(
        _device: str,
        path: str,
        *,
        namespace_pid: int | None = None,
    ) -> str:
        del namespace_pid
        return source_digest if path.endswith("hosts-source") else overlay_digest

    def fake_pull(_device: str, _remote: str, local: Path) -> bytes:
        local.write_bytes(source)
        return source

    with (
        mock.patch.object(resolver_subject, "_pull_regular_file", side_effect=fake_pull),
        mock.patch.object(resolver_subject, "_adb", side_effect=fake_adb),
        mock.patch.object(resolver_subject, "_remote_sha256", side_effect=fake_digest),
        mock.patch.object(resolver_subject, "_require_regular_file"),
    ):
        receipt = resolver_subject.install_android_host_overlay(
            target=target,
            device="emulator-5556",
            stage_root="/data/local/tmp/quwoquan-device-trust/alpha",
            namespaces=namespaces,
            handoff=handoff,
        )

    assert pushed[receipt["sourceStagePath"]] == source
    assert pushed[receipt["overlayPath"]] == overlay
    assert overlay.startswith(source)
    assert all(f"127.0.0.1 {host}\n".encode() in overlay for host in hosts)
    mount_commands = [arguments for arguments in commands if "mount" in arguments]
    assert [command[3] for command in mount_commands] == ["1", "100"]
    assert all(command[-1] == "/system/etc/hosts" for command in mount_commands)
    assert receipt["handoffDigest"] == handoff["handoffDigest"]
    assert receipt["mountNamespaces"] == namespaces


def test_android_resolver_rejects_symlink_and_namespace_receipt_drift() -> None:
    with (
        mock.patch.object(
            resolver_subject,
            "_adb",
            return_value=mock.Mock(stdout="symbolic link\n", returncode=0),
        ),
        pytest.raises(resolver_subject.LocalDeviceResolverError, match="regular file"),
    ):
        resolver_subject._require_regular_file(
            "emulator-5556",
            "/system/etc/hosts",
        )

    target = "alpha-local"
    hosts = list(resolver_subject.canonical_hosts(target))
    handoff = {
        "target": target,
        "address": "127.0.0.1",
        "hosts": hosts,
        "handoffDigest": f"sha256:{'a' * 64}",
    }
    namespaces = [{"namespace": "mnt:[1001]", "representativePid": 1}]
    receipt = {
        "sourcePath": "/system/etc/hosts",
        "sourceStagePath": "/stage/hosts-source",
        "sourceSha256": "A" * 64,
        "overlayPath": "/stage/hosts",
        "overlaySha256": "B" * 64,
        "mountedPath": "/system/etc/hosts",
        "address": "127.0.0.1",
        "hosts": hosts,
        "handoffDigest": handoff["handoffDigest"],
        "mountNamespaces": [
            {"namespace": "mnt:[different]", "representativePid": 1}
        ],
    }
    with pytest.raises(resolver_subject.LocalDeviceResolverError, match="receipt drift"):
        resolver_subject.verify_android_host_overlay(
            target=target,
            device="emulator-5556",
            stage_root="/stage",
            namespaces=namespaces,
            handoff=handoff,
            receipt=deepcopy(receipt),
        )


def test_android_startup_can_record_unprovisioned_system_store(
    tmp_path: Path,
) -> None:
    root = _root_certificate(tmp_path)
    receipt = tmp_path / "device-trust.json"
    with (
        mock.patch.object(subject, "verify_certificate"),
        mock.patch.object(
            subject,
            "resolve_managed_device",
            return_value="emulator-5554",
        ),
        mock.patch.object(subject, "root_certificate_path", return_value=root),
        mock.patch.object(
            subject.ssl,
            "PEM_cert_to_DER_cert",
            return_value=b"managed-root",
        ),
        mock.patch.object(subject, "_receipt_path", return_value=receipt),
        mock.patch.object(
            subject,
            "_android_identity",
            return_value=_android_identity(build_type="user", debuggable=False),
        ),
        mock.patch.object(
            subject,
            "_install_android",
            side_effect=subject.AndroidSystemTrustUnavailable("system store is locked"),
        ),
    ):
        installed = subject.install_device_trust(
            target="alpha-local",
            platform_name="android-emulator",
            device="emulator-5554",
            lease_id="direct-debug",
            allow_unprovisioned_system_trust=True,
        )
        with pytest.raises(subject.LocalDeviceTrustError, match="identity mismatch"):
            subject.verify_device_trust(
                target="alpha-local",
                platform_name="android-emulator",
                device="emulator-5554",
            )

    assert installed["status"] == "launch-degraded"
    assert installed["systemTrustStore"] is False
    assert installed["apiLevel"] == 35
    assert installed["buildType"] == "user"
    assert installed["debuggable"] is False
    assert installed["bootId"] == "11111111-2222-3333-4444-555555555555"
    assert installed["trustStorePath"] == ""
    assert installed["installedCertificateSha256"] == ""
    assert "unprovisioned" in installed["verification"]


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
