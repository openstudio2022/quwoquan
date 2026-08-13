"""Android Emulator 系统 CA 信任的安装与验证（逐字搬移）。

``_require_success`` / ``_android_*`` 系列 / ``verify_runtime_trust_stores`` /
``install_android_host_overlay`` / ``verify_android_host_overlay`` /
``materialize_handoff`` / ``load_handoff`` 是测试的 patch 锚点，包内消费
一律经 ``_pkg.`` 属性访问。
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import quwoquan_ops.cli.lib.local_device_trust as _pkg

from ..local_device_android_trust import AndroidTrustOverlayError
from ..local_device_resolver import LocalDeviceResolverError
from .constants import (
    _ANDROID_CONSCRYPT_CACERTS,
    _ANDROID_SYSTEM_CACERTS,
    _ANDROID_TRUST_STAGE_ROOT,
    _SAFE,
)
from .device_commands import _run
from .errors import (
    AndroidSystemTrustUnavailable,
    AndroidSystemTrustVerificationError,
    LocalDeviceTrustError,
)


def _android_property(device: str, name: str) -> str:
    return _pkg._require_success(
        ["adb", "-s", device, "shell", "getprop", name],
        action=f"Android property {name}",
    ).stdout.strip()


def _android_identity(device: str) -> dict[str, Any]:
    if _pkg._android_property(device, "ro.kernel.qemu") != "1":
        raise LocalDeviceTrustError(
            "physical Android devices are not eligible for local CA trust"
        )
    api_value = _pkg._android_property(device, "ro.build.version.sdk")
    try:
        api = int(api_value)
    except ValueError as exc:
        raise LocalDeviceTrustError("Android Emulator API level is invalid") from exc
    build_type = _pkg._android_property(device, "ro.build.type")
    debuggable_value = _pkg._android_property(device, "ro.debuggable")
    fingerprint = _pkg._android_property(device, "ro.build.fingerprint")
    boot_id = _pkg._require_success(
        [
            "adb",
            "-s",
            device,
            "shell",
            "cat",
            "/proc/sys/kernel/random/boot_id",
        ],
        action="Android Emulator boot identity",
    ).stdout.strip()
    if (
        api <= 0
        or not build_type
        or debuggable_value not in {"0", "1"}
        or not fingerprint
        or re.fullmatch(r"[0-9a-fA-F-]{36}", boot_id) is None
    ):
        raise LocalDeviceTrustError("Android Emulator identity is incomplete")
    return {
        "apiLevel": api,
        "buildType": build_type,
        "debuggable": debuggable_value == "1",
        "buildFingerprint": fingerprint,
        "bootId": boot_id.lower(),
    }


def _android_subject_hash(root: Path) -> str:
    subject_hash = _pkg._require_success(
        ["openssl", "x509", "-in", str(root), "-subject_hash_old", "-noout"],
        action="Android CA subject hash",
    ).stdout.strip()
    if re.fullmatch(r"[0-9a-fA-F]{8}", subject_hash) is None:
        raise LocalDeviceTrustError("Android CA subject hash is invalid")
    return subject_hash.lower()


def _android_root(device: str) -> None:
    adb_root = _run(["adb", "-s", device, "root"])
    if (
        adb_root.returncode != 0
        or "cannot run as root"
        in ((adb_root.stderr or "") + (adb_root.stdout or "")).lower()
    ):
        raise AndroidSystemTrustUnavailable(
            "Android Emulator system CA store is not writable; "
            "use a managed userdebug or eng AVD for endpoint verification"
        )
    _pkg._require_success(
        ["adb", "-s", device, "wait-for-device"],
        action="Android Emulator wait",
    )
    uid = _pkg._require_success(
        ["adb", "-s", device, "shell", "id", "-u"],
        action="Android Emulator root verification",
    ).stdout.strip()
    if uid != "0":
        raise AndroidSystemTrustUnavailable(
            "Android Emulator system CA store is not writable; "
            "use a managed userdebug or eng AVD for endpoint verification"
        )


def _android_remote_sha256(
    device: str,
    remote: str,
    *,
    namespace_pid: int | None = None,
) -> str:
    argv = ["adb", "-s", device, "shell"]
    if namespace_pid is not None:
        argv.extend(["nsenter", "-t", str(namespace_pid), "-m", "--"])
    argv.extend(["sha256sum", remote])
    result = _run(argv)
    if result.returncode != 0:
        return ""
    digest = result.stdout.strip().split(maxsplit=1)[0]
    return digest.upper() if re.fullmatch(r"[0-9a-fA-F]{64}", digest) else ""


def _android_zygote_pids(device: str) -> list[int]:
    result = _run(["adb", "-s", device, "shell", "pidof", "zygote", "zygote64"])
    if result.returncode != 0:
        raise LocalDeviceTrustError("Android zygote discovery failed")
    pids = sorted({int(value) for value in result.stdout.split() if value.isdigit()})
    if not pids:
        raise LocalDeviceTrustError("Android zygote discovery returned no processes")
    return pids


def _android_mount_namespace_evidence(
    device: str,
    pids: list[int],
) -> list[dict[str, Any]]:
    representatives: dict[str, int] = {}
    for pid in [1, *pids]:
        namespace = _pkg._require_success(
            [
                "adb",
                "-s",
                device,
                "shell",
                "readlink",
                f"/proc/{pid}/ns/mnt",
            ],
            action=f"Android mount namespace discovery pid={pid}",
        ).stdout.strip()
        if re.fullmatch(r"mnt:\[[0-9]+\]", namespace) is None:
            raise LocalDeviceTrustError("Android mount namespace identity is invalid")
        representatives.setdefault(namespace, pid)
    return [
        {"namespace": namespace, "representativePid": pid}
        for namespace, pid in representatives.items()
    ]


def _android_conscrypt_source_cacerts(device: str) -> str:
    mounts = _pkg._require_success(
        ["adb", "-s", device, "shell", "mount"],
        action="Android Conscrypt source mount discovery",
    ).stdout
    candidates = sorted(
        set(
            re.findall(
                r" on (/apex/com\.android\.conscrypt@[0-9]+)/? type ",
                mounts,
            )
        )
    )
    if len(candidates) != 1:
        raise LocalDeviceTrustError(
            "Android Conscrypt versioned source mount is not unique"
        )
    return f"{candidates[0]}/cacerts"


def _android_trust_stage_root(
    target: str,
    identity: dict[str, Any],
    certificate_digest: str,
) -> str:
    target_segment = _SAFE.sub("-", target).strip("-") or "target"
    boot_segment = _SAFE.sub("-", str(identity["bootId"])).strip("-")
    return (
        f"{_ANDROID_TRUST_STAGE_ROOT}/{target_segment}/"
        f"{boot_segment}/{certificate_digest[:16].lower()}"
    )


def _install_android_conscrypt(
    target: str,
    device: str,
    root: Path,
    identity: dict[str, Any],
) -> dict[str, Any]:
    if identity["debuggable"] is not True or identity["buildType"] not in {
        "userdebug",
        "eng",
    }:
        raise AndroidSystemTrustUnavailable(
            "Android 14+ system CA installation requires a managed userdebug or eng AVD"
        )
    _pkg._android_root(device)
    subject_hash = _pkg._android_subject_hash(root)
    expected_digest = hashlib.sha256(root.read_bytes()).hexdigest().upper()
    certificate_name = f"{subject_hash}.0"
    stage_root = _android_trust_stage_root(target, identity, expected_digest)
    source_cacerts = _pkg._android_conscrypt_source_cacerts(device)
    namespaces = _pkg._android_mount_namespace_evidence(
        device,
        _pkg._android_zygote_pids(device),
    )
    store_specs = (
        (
            "conscrypt-apex",
            source_cacerts,
            _ANDROID_CONSCRYPT_CACERTS,
            f"{stage_root}/apex-cacerts",
        ),
        (
            "system-partition",
            _ANDROID_SYSTEM_CACERTS,
            _ANDROID_SYSTEM_CACERTS,
            f"{stage_root}/system-cacerts",
        ),
    )
    stores: list[dict[str, Any]] = []
    for kind, source, trust_store, stage in store_specs:
        source_digest = _pkg.remote_tree_sha256(device, source)
        if not source_digest:
            raise AndroidSystemTrustVerificationError(
                f"Android {kind} source trust store digest failed"
            )
        _pkg._require_success(
            ["adb", "-s", device, "shell", "rm", "-rf", stage],
            action=f"Android {kind} stale trust store staging cleanup",
        )
        _pkg._require_success(
            ["adb", "-s", device, "shell", "mkdir", "-p", stage],
            action=f"Android {kind} trust store staging directory",
        )
        _pkg._require_success(
            [
                "adb",
                "-s",
                device,
                "shell",
                "cp",
                "-pR",
                f"{source}/.",
                stage,
            ],
            action=f"Android {kind} trust store staging",
        )
        staged_certificate = f"{stage}/{certificate_name}"
        _pkg._require_success(
            ["adb", "-s", device, "push", str(root), staged_certificate],
            action=f"Android {kind} CA push",
        )
        _pkg._require_success(
            ["adb", "-s", device, "shell", "chown", "root:shell", stage],
            action=f"Android {kind} trust store ownership",
        )
        _pkg._require_success(
            ["adb", "-s", device, "shell", "chmod", "0755", stage],
            action=f"Android {kind} trust store permissions",
        )
        _pkg._require_success(
            [
                "adb",
                "-s",
                device,
                "shell",
                "chown",
                "system:system",
                staged_certificate,
            ],
            action=f"Android {kind} CA ownership",
        )
        _pkg._require_success(
            ["adb", "-s", device, "shell", "chmod", "0644", staged_certificate],
            action=f"Android {kind} CA permissions",
        )
        _pkg._require_success(
            [
                "adb",
                "-s",
                device,
                "shell",
                "chcon",
                "-R",
                "u:object_r:system_security_cacerts_file:s0",
                stage,
            ],
            action=f"Android {kind} CA SELinux context",
        )
        if (
            _pkg.remote_tree_sha256(
                device,
                stage,
                exclude_name=certificate_name,
            )
            != source_digest
        ):
            raise AndroidSystemTrustVerificationError(
                f"Android {kind} source bytes changed during staging"
            )
        incremental_digest = _pkg.remote_tree_sha256(device, stage)
        if not incremental_digest:
            raise AndroidSystemTrustVerificationError(
                f"Android {kind} incremental trust store digest failed"
            )
        stores.append(
            {
                "kind": kind,
                "sourcePath": source,
                "sourceStoreSha256": source_digest,
                "stagedStorePath": stage,
                "incrementalStoreSha256": incremental_digest,
                "trustStorePath": trust_store,
                "certificatePath": f"{trust_store}/{certificate_name}",
                "installedCertificateSha256": expected_digest,
                "mountNamespaces": namespaces,
            }
        )
    for store in stores:
        for namespace in namespaces:
            pid = int(namespace["representativePid"])
            _pkg._require_success(
                [
                    "adb",
                    "-s",
                    device,
                    "shell",
                    "nsenter",
                    "-t",
                    str(pid),
                    "-m",
                    "--",
                    "mount",
                    "--bind",
                    str(store["stagedStorePath"]),
                    str(store["trustStorePath"]),
                ],
                action=f"Android {store['kind']} trust store bind pid={pid}",
            )
    try:
        host_overlay = _pkg.install_android_host_overlay(
            target=target,
            device=device,
            stage_root=stage_root,
            namespaces=namespaces,
            handoff=_pkg.materialize_handoff(target),
        )
    except LocalDeviceResolverError as exc:
        raise AndroidSystemTrustVerificationError(str(exc)) from exc
    try:
        namespace_count = _pkg.verify_runtime_trust_stores(
            device,
            stores,
            namespaces,
            expected_digest,
            remote_sha256=_pkg._android_remote_sha256,
        )
    except AndroidTrustOverlayError as exc:
        raise AndroidSystemTrustVerificationError(str(exc)) from exc
    return {
        **identity,
        "androidTrustStores": stores,
        "androidHostOverlay": host_overlay,
        "verification": (
            "dual-system-root-installed; trust-stores-verified=2; "
            f"mount-namespaces-verified={namespace_count}"
        ),
    }


def _install_android_system_store(
    device: str,
    root: Path,
    identity: dict[str, Any],
) -> dict[str, Any]:
    subject_hash = _pkg._android_subject_hash(root)
    remote = f"{_ANDROID_SYSTEM_CACERTS}/{subject_hash}.0"
    _pkg._android_root(device)
    remount = _run(["adb", "-s", device, "remount"])
    if remount.returncode != 0:
        raise AndroidSystemTrustUnavailable(
            "Android Emulator system CA store is not writable; "
            "use a managed debug AVD for endpoint verification"
        )
    staged = f"/data/local/tmp/{subject_hash}.0"
    _pkg._require_success(
        ["adb", "-s", device, "push", str(root), staged],
        action="Android CA push",
    )
    _pkg._require_success(
        [
            "adb",
            "-s",
            device,
            "shell",
            "cp",
            staged,
            remote,
        ],
        action="Android CA system installation",
    )
    _pkg._require_success(
        ["adb", "-s", device, "shell", "chmod", "0644", remote],
        action="Android CA permissions",
    )
    _pkg._require_success(
        ["adb", "-s", device, "shell", "rm", "-f", staged],
        action="Android CA staging cleanup",
    )
    expected_digest = hashlib.sha256(root.read_bytes()).hexdigest().upper()
    if _android_remote_sha256(device, remote) != expected_digest:
        raise LocalDeviceTrustError("Android system CA verification failed")
    return {
        **identity,
        "trustStorePath": remote,
        "installedCertificateSha256": expected_digest,
        "verification": "system-partition-root-installed",
    }


def _install_android(
    target: str,
    device: str,
    root: Path,
    *,
    identity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_identity = identity or _pkg._android_identity(device)
    if resolved_identity["apiLevel"] >= 34:
        return _install_android_conscrypt(
            target,
            device,
            root,
            resolved_identity,
        )
    return _install_android_system_store(device, root, resolved_identity)


def _verify_android_system_trust(
    device: str,
    root: Path,
    receipt: dict[str, Any],
) -> str:
    identity = _pkg._android_identity(device)
    identity_keys = (
        "apiLevel",
        "buildType",
        "debuggable",
        "buildFingerprint",
        "bootId",
    )
    if any(receipt.get(key) != identity[key] for key in identity_keys):
        raise LocalDeviceTrustError("device system-trust receipt identity mismatch")
    subject_hash = _pkg._android_subject_hash(root)
    expected_digest = hashlib.sha256(root.read_bytes()).hexdigest().upper()
    if identity["apiLevel"] >= 34:
        target = str(receipt.get("target") or "")
        stage_root = _android_trust_stage_root(target, identity, expected_digest)
        source_cacerts = _pkg._android_conscrypt_source_cacerts(device)
        certificate_name = f"{subject_hash}.0"
        expected_layouts = (
            (
                "conscrypt-apex",
                source_cacerts,
                f"{stage_root}/apex-cacerts",
                _ANDROID_CONSCRYPT_CACERTS,
            ),
            (
                "system-partition",
                _ANDROID_SYSTEM_CACERTS,
                f"{stage_root}/system-cacerts",
                _ANDROID_SYSTEM_CACERTS,
            ),
        )
        stores = receipt.get("androidTrustStores")
        store_keys = {
            "kind",
            "sourcePath",
            "sourceStoreSha256",
            "stagedStorePath",
            "incrementalStoreSha256",
            "trustStorePath",
            "certificatePath",
            "installedCertificateSha256",
            "mountNamespaces",
        }
        if (
            not isinstance(stores, list)
            or len(stores) != len(expected_layouts)
            or any(not isinstance(store, dict) or set(store) != store_keys for store in stores)
        ):
            raise LocalDeviceTrustError("Android trust store receipt schema mismatch")
        namespaces = _pkg._android_mount_namespace_evidence(
            device,
            _pkg._android_zygote_pids(device),
        )
        for store, layout in zip(stores, expected_layouts, strict=True):
            kind, source, staged, trust_store = layout
            if (
                store["kind"] != kind
                or store["sourcePath"] != source
                or store["stagedStorePath"] != staged
                or store["trustStorePath"] != trust_store
                or store["certificatePath"]
                != f"{trust_store}/{certificate_name}"
                or store["installedCertificateSha256"] != expected_digest
                or store["mountNamespaces"] != namespaces
                or re.fullmatch(
                    r"[0-9A-F]{64}",
                    str(store["sourceStoreSha256"]),
                )
                is None
                or re.fullmatch(
                    r"[0-9A-F]{64}",
                    str(store["incrementalStoreSha256"]),
                )
                is None
            ):
                raise LocalDeviceTrustError("Android trust store receipt drift")
        try:
            namespace_count = _pkg.verify_runtime_trust_stores(
                device,
                stores,
                namespaces,
                expected_digest,
                remote_sha256=_pkg._android_remote_sha256,
            )
        except AndroidTrustOverlayError as exc:
            raise LocalDeviceTrustError(str(exc)) from exc
        try:
            _pkg.verify_android_host_overlay(
                target=target,
                device=device,
                stage_root=stage_root,
                namespaces=namespaces,
                handoff=_pkg.load_handoff(target),
                receipt=receipt.get("androidHostOverlay"),
            )
        except LocalDeviceResolverError as exc:
            raise LocalDeviceTrustError(str(exc)) from exc
        return (
            "dual-system-trust-ok; trust-stores-verified=2; "
            f"mount-namespaces-verified={namespace_count}; resolver-overlay-verified"
        )
    remote = f"{_ANDROID_SYSTEM_CACERTS}/{subject_hash}.0"
    if (
        receipt.get("trustStorePath") != remote
        or receipt.get("installedCertificateSha256") != expected_digest
    ):
        raise LocalDeviceTrustError("device system-trust receipt certificate mismatch")
    if _android_remote_sha256(device, remote) != expected_digest:
        raise LocalDeviceTrustError("Android system CA verification failed")
    return "system-partition-trust-ok"
