"""Install and prove target-scoped local CA trust on managed simulators."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import ssl
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from quwoquan_ops.cli.lib.environment_topology import (
    get_target,
    load_environment_topology,
)
from quwoquan_ops.cli.lib.local_device_android_trust import (
    AndroidTrustOverlayError,
    remote_tree_sha256,
    verify_runtime_trust_stores,
)
from quwoquan_ops.cli.lib.local_device_resolver import (
    LocalDeviceResolverError,
    install_android_host_overlay,
    verify_android_host_overlay,
)
from quwoquan_ops.cli.lib.local_target_handoff import (
    load_handoff,
    materialize_handoff,
)
from quwoquan_ops.cli.lib.output_paths import target_cache_dir, target_process_dir
from quwoquan_ops.cli.lib.public_domain_tls import (
    root_certificate_path,
    verify_certificate,
)

SCHEMA = "stackctl-local-device-system-trust"
PLATFORMS = ("ios-simulator", "android-emulator")
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")
_ROOT = Path(__file__).resolve().parents[3]
_ANDROID_CONSCRYPT_CACERTS = "/apex/com.android.conscrypt/cacerts"
_ANDROID_LEGACY_CACERTS = "/system/etc/security/cacerts"
_ANDROID_TRUST_STAGE_ROOT = "/data/local/tmp/quwoquan-device-trust"


class LocalDeviceTrustError(RuntimeError):
    pass


class AndroidSystemTrustUnavailable(LocalDeviceTrustError):
    """The selected Emulator cannot modify its system CA store."""


class AndroidSystemTrustVerificationError(LocalDeviceTrustError):
    """The expected CA is not visible from an Android runtime namespace."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _run(argv: list[str], *, timeout: int = 90) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            argv,
            cwd=_ROOT,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LocalDeviceTrustError(f"device trust command failed: {argv[0]}") from exc


def _require_success(
    argv: list[str],
    *,
    action: str,
    timeout: int = 90,
) -> subprocess.CompletedProcess[str]:
    result = _run(argv, timeout=timeout)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise LocalDeviceTrustError(
            f"{action} failed"
            + (f": {detail[:500]}" if detail else f" (exit={result.returncode})")
        )
    return result


def _root_fingerprint(path: Path) -> str:
    try:
        pem = path.read_text(encoding="ascii")
        der = ssl.PEM_cert_to_DER_cert(pem)
    except (OSError, UnicodeError, ValueError) as exc:
        raise LocalDeviceTrustError(
            "local-managed root certificate is invalid"
        ) from exc
    return hashlib.sha256(der).hexdigest().upper()


def _receipt_path(target: str, platform_name: str, device: str) -> Path:
    segment = _SAFE.sub("-", device).strip("-") or "device"
    return (
        target_process_dir(target) / "device-trust" / platform_name / f"{segment}.json"
    )


def _read_receipt(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LocalDeviceTrustError(
            f"device trust receipt is unreadable: {exc}"
        ) from exc
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        raise LocalDeviceTrustError("device trust receipt schema mismatch")
    return value


def _write_receipt(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def _booted_ios_simulators() -> dict[str, dict[str, Any]]:
    result = _require_success(
        ["xcrun", "simctl", "list", "devices", "booted", "--json"],
        action="iOS Simulator discovery",
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise LocalDeviceTrustError(
            "iOS Simulator discovery returned invalid JSON"
        ) from exc
    discovered: dict[str, dict[str, Any]] = {}
    for devices in (payload.get("devices") or {}).values():
        if not isinstance(devices, list):
            continue
        for device in devices:
            if (
                isinstance(device, dict)
                and device.get("state") == "Booted"
                and device.get("isAvailable") is not False
            ):
                discovered[str(device.get("udid") or "")] = device
    return {key: value for key, value in discovered.items() if key}


def resolve_managed_device(platform_name: str, device: str = "") -> str:
    requested = str(device or "").strip()
    if platform_name == "ios-simulator":
        devices = _booted_ios_simulators()
        if requested:
            if requested not in devices:
                raise LocalDeviceTrustError(
                    f"selected device is not a booted iOS Simulator: {requested}"
                )
            return requested
        if len(devices) != 1:
            raise LocalDeviceTrustError(
                "select exactly one booted iOS Simulator with an explicit device id"
            )
        return next(iter(devices))
    if platform_name == "android-emulator":
        result = _require_success(
            ["adb", "devices"],
            action="Android Emulator discovery",
        )
        devices = [
            line.split("\t", 1)[0]
            for line in result.stdout.splitlines()
            if "\tdevice" in line and line.split("\t", 1)[0].startswith("emulator-")
        ]
        if requested:
            if requested not in devices:
                raise LocalDeviceTrustError(
                    f"selected device is not a connected Android Emulator: {requested}"
                )
            return requested
        if len(devices) != 1:
            raise LocalDeviceTrustError(
                "select exactly one Android Emulator with an explicit device id"
            )
        return devices[0]
    raise LocalDeviceTrustError(f"unsupported managed device platform: {platform_name}")


def _target_probe_url(target: str) -> str:
    topology = load_environment_topology()
    row = get_target(topology, target)
    api = str((row.get("publicBases") or {}).get("api") or "").rstrip("/")
    if not api.startswith("https://"):
        raise LocalDeviceTrustError("local target has no canonical HTTPS API URL")
    return api + "/healthz"


def _ios_probe_binary(target: str) -> Path:
    source = _ROOT / "quwoquan_ops/cli/tools/ios_simulator_system_trust_probe.swift"
    source_digest = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
    binary = target_cache_dir(target) / "device-trust" / f"ios-probe-{source_digest}"
    if binary.is_file():
        return binary
    binary.parent.mkdir(parents=True, exist_ok=True)
    sdk = _require_success(
        ["xcrun", "--sdk", "iphonesimulator", "--show-sdk-path"],
        action="iOS Simulator SDK resolution",
    ).stdout.strip()
    architecture = "arm64" if platform.machine() == "arm64" else "x86_64"
    _require_success(
        [
            "xcrun",
            "--sdk",
            "iphonesimulator",
            "swiftc",
            "-sdk",
            sdk,
            "-target",
            f"{architecture}-apple-ios17.0-simulator",
            str(source),
            "-o",
            str(binary),
        ],
        action="iOS system-trust probe build",
        timeout=180,
    )
    return binary


def _probe_ios_system_trust(target: str, device: str) -> str:
    probe = _ios_probe_binary(target)
    result = _require_success(
        [
            "xcrun",
            "simctl",
            "spawn",
            device,
            str(probe),
            _target_probe_url(target),
        ],
        action="iOS Simulator default system-trust HTTPS probe",
        timeout=40,
    )
    if "system-trust-ok" not in result.stdout:
        raise LocalDeviceTrustError("iOS system-trust probe emitted no success receipt")
    return result.stdout.strip()


def _install_ios(
    target: str,
    device: str,
    root: Path,
    *,
    endpoint_probe: bool,
) -> str:
    _require_success(
        ["xcrun", "simctl", "keychain", device, "add-root-cert", str(root)],
        action="iOS Simulator root certificate installation",
    )
    if endpoint_probe:
        return _probe_ios_system_trust(target, device)
    return "system-root-installed; endpoint-probe-deferred"


def _android_property(device: str, name: str) -> str:
    return _require_success(
        ["adb", "-s", device, "shell", "getprop", name],
        action=f"Android property {name}",
    ).stdout.strip()


def _android_identity(device: str) -> dict[str, Any]:
    if _android_property(device, "ro.kernel.qemu") != "1":
        raise LocalDeviceTrustError(
            "physical Android devices are not eligible for local CA trust"
        )
    api_value = _android_property(device, "ro.build.version.sdk")
    try:
        api = int(api_value)
    except ValueError as exc:
        raise LocalDeviceTrustError("Android Emulator API level is invalid") from exc
    build_type = _android_property(device, "ro.build.type")
    debuggable_value = _android_property(device, "ro.debuggable")
    fingerprint = _android_property(device, "ro.build.fingerprint")
    boot_id = _require_success(
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
    subject_hash = _require_success(
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
    _require_success(
        ["adb", "-s", device, "wait-for-device"],
        action="Android Emulator wait",
    )
    uid = _require_success(
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
        namespace = _require_success(
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
    mounts = _require_success(
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
    _android_root(device)
    subject_hash = _android_subject_hash(root)
    expected_digest = hashlib.sha256(root.read_bytes()).hexdigest().upper()
    certificate_name = f"{subject_hash}.0"
    stage_root = _android_trust_stage_root(target, identity, expected_digest)
    source_cacerts = _android_conscrypt_source_cacerts(device)
    namespaces = _android_mount_namespace_evidence(
        device,
        _android_zygote_pids(device),
    )
    store_specs = (
        (
            "conscrypt-apex",
            source_cacerts,
            _ANDROID_CONSCRYPT_CACERTS,
            f"{stage_root}/apex-cacerts",
        ),
        (
            "legacy-system",
            _ANDROID_LEGACY_CACERTS,
            _ANDROID_LEGACY_CACERTS,
            f"{stage_root}/legacy-cacerts",
        ),
    )
    stores: list[dict[str, Any]] = []
    for kind, source, trust_store, stage in store_specs:
        source_digest = remote_tree_sha256(device, source)
        if not source_digest:
            raise AndroidSystemTrustVerificationError(
                f"Android {kind} source trust store digest failed"
            )
        _require_success(
            ["adb", "-s", device, "shell", "rm", "-rf", stage],
            action=f"Android {kind} stale trust store staging cleanup",
        )
        _require_success(
            ["adb", "-s", device, "shell", "mkdir", "-p", stage],
            action=f"Android {kind} trust store staging directory",
        )
        _require_success(
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
        _require_success(
            ["adb", "-s", device, "push", str(root), staged_certificate],
            action=f"Android {kind} CA push",
        )
        _require_success(
            ["adb", "-s", device, "shell", "chown", "root:shell", stage],
            action=f"Android {kind} trust store ownership",
        )
        _require_success(
            ["adb", "-s", device, "shell", "chmod", "0755", stage],
            action=f"Android {kind} trust store permissions",
        )
        _require_success(
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
        _require_success(
            ["adb", "-s", device, "shell", "chmod", "0644", staged_certificate],
            action=f"Android {kind} CA permissions",
        )
        _require_success(
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
            remote_tree_sha256(
                device,
                stage,
                exclude_name=certificate_name,
            )
            != source_digest
        ):
            raise AndroidSystemTrustVerificationError(
                f"Android {kind} source bytes changed during staging"
            )
        incremental_digest = remote_tree_sha256(device, stage)
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
            _require_success(
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
        host_overlay = install_android_host_overlay(
            target=target,
            device=device,
            stage_root=stage_root,
            namespaces=namespaces,
            handoff=materialize_handoff(target),
        )
    except LocalDeviceResolverError as exc:
        raise AndroidSystemTrustVerificationError(str(exc)) from exc
    try:
        namespace_count = verify_runtime_trust_stores(
            device,
            stores,
            namespaces,
            expected_digest,
            remote_sha256=_android_remote_sha256,
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


def _install_android_legacy(
    device: str,
    root: Path,
    identity: dict[str, Any],
) -> dict[str, Any]:
    subject_hash = _android_subject_hash(root)
    remote = f"{_ANDROID_LEGACY_CACERTS}/{subject_hash}.0"
    _android_root(device)
    remount = _run(["adb", "-s", device, "remount"])
    if remount.returncode != 0:
        raise AndroidSystemTrustUnavailable(
            "Android Emulator system CA store is not writable; "
            "use a managed debug AVD for endpoint verification"
        )
    staged = f"/data/local/tmp/{subject_hash}.0"
    _require_success(
        ["adb", "-s", device, "push", str(root), staged],
        action="Android CA push",
    )
    _require_success(
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
    _require_success(
        ["adb", "-s", device, "shell", "chmod", "0644", remote],
        action="Android CA permissions",
    )
    _require_success(
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
        "verification": "legacy-system-root-installed",
    }


def _install_android(
    target: str,
    device: str,
    root: Path,
    *,
    identity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_identity = identity or _android_identity(device)
    if resolved_identity["apiLevel"] >= 34:
        return _install_android_conscrypt(
            target,
            device,
            root,
            resolved_identity,
        )
    return _install_android_legacy(device, root, resolved_identity)


def _verify_android_system_trust(
    device: str,
    root: Path,
    receipt: dict[str, Any],
) -> str:
    identity = _android_identity(device)
    identity_keys = (
        "apiLevel",
        "buildType",
        "debuggable",
        "buildFingerprint",
        "bootId",
    )
    if any(receipt.get(key) != identity[key] for key in identity_keys):
        raise LocalDeviceTrustError("device system-trust receipt identity mismatch")
    subject_hash = _android_subject_hash(root)
    expected_digest = hashlib.sha256(root.read_bytes()).hexdigest().upper()
    if identity["apiLevel"] >= 34:
        target = str(receipt.get("target") or "")
        stage_root = _android_trust_stage_root(target, identity, expected_digest)
        source_cacerts = _android_conscrypt_source_cacerts(device)
        certificate_name = f"{subject_hash}.0"
        expected_layouts = (
            (
                "conscrypt-apex",
                source_cacerts,
                f"{stage_root}/apex-cacerts",
                _ANDROID_CONSCRYPT_CACERTS,
            ),
            (
                "legacy-system",
                _ANDROID_LEGACY_CACERTS,
                f"{stage_root}/legacy-cacerts",
                _ANDROID_LEGACY_CACERTS,
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
        namespaces = _android_mount_namespace_evidence(
            device,
            _android_zygote_pids(device),
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
            namespace_count = verify_runtime_trust_stores(
                device,
                stores,
                namespaces,
                expected_digest,
                remote_sha256=_android_remote_sha256,
            )
        except AndroidTrustOverlayError as exc:
            raise LocalDeviceTrustError(str(exc)) from exc
        try:
            verify_android_host_overlay(
                target=target,
                device=device,
                stage_root=stage_root,
                namespaces=namespaces,
                handoff=load_handoff(target),
                receipt=receipt.get("androidHostOverlay"),
            )
        except LocalDeviceResolverError as exc:
            raise LocalDeviceTrustError(str(exc)) from exc
        return (
            "dual-system-trust-ok; trust-stores-verified=2; "
            f"mount-namespaces-verified={namespace_count}; resolver-overlay-verified"
        )
    remote = f"{_ANDROID_LEGACY_CACERTS}/{subject_hash}.0"
    if (
        receipt.get("trustStorePath") != remote
        or receipt.get("installedCertificateSha256") != expected_digest
    ):
        raise LocalDeviceTrustError("device system-trust receipt certificate mismatch")
    if _android_remote_sha256(device, remote) != expected_digest:
        raise LocalDeviceTrustError("Android system CA verification failed")
    return "legacy-system-trust-ok"


def install_device_trust(
    *,
    target: str,
    platform_name: str,
    device: str = "",
    lease_id: str = "",
    endpoint_probe: bool = True,
    allow_unprovisioned_system_trust: bool = False,
) -> dict[str, Any]:
    if allow_unprovisioned_system_trust and platform_name != "android-emulator":
        raise LocalDeviceTrustError(
            "unprovisioned system trust is supported only for "
            "Android Emulator app startup"
        )
    verify_certificate(target)
    selected = resolve_managed_device(platform_name, device)
    root = root_certificate_path(target)
    fingerprint = _root_fingerprint(root)
    path = _receipt_path(target, platform_name, selected)
    previous = _read_receipt(path)
    leases = list(previous.get("leases") or []) if previous else []
    normalized_lease = str(lease_id or "").strip() or uuid4().hex
    if normalized_lease not in leases:
        leases.append(normalized_lease)
    android_identity = (
        _android_identity(selected) if platform_name == "android-emulator" else {}
    )
    if (
        platform_name == "android-emulator"
        and previous is not None
        and previous.get("target") == target
        and previous.get("platform") == platform_name
        and previous.get("device") == selected
        and previous.get("rootFingerprintSha256") == fingerprint
        and previous.get("status") == "installed"
        and previous.get("systemTrustStore") is True
        and all(
            previous.get(key) == android_identity[key]
            for key in (
                "apiLevel",
                "buildType",
                "debuggable",
                "buildFingerprint",
                "bootId",
            )
        )
    ):
        # The Android 14+ trust stores are bind-mounted from the receipt's
        # staging tree. Re-staging from those live mounts would make the
        # incremental store its own source and can delete the backing tree
        # before verification. Prove the complete existing receipt first and
        # reuse it without any device mutation. Any drift fails before the
        # installer can clean, copy, or bind a path.
        proof = _verify_android_system_trust(selected, root, previous)
        payload = {
            **previous,
            "verification": proof,
            "leases": sorted(leases),
            "updatedAt": _utc_now(),
        }
        _write_receipt(path, payload)
        return {**payload, "receipt": str(path), "leaseId": normalized_lease}
    device_evidence: dict[str, Any] = {}
    try:
        if platform_name == "ios-simulator":
            proof = _install_ios(
                target,
                selected,
                root,
                endpoint_probe=endpoint_probe,
            )
        else:
            device_evidence = _install_android(
                target,
                selected,
                root,
                identity=android_identity,
            )
            proof = str(device_evidence.pop("verification"))
        system_trust_store = True
    except AndroidSystemTrustUnavailable:
        if not allow_unprovisioned_system_trust:
            raise
        proof = (
            "system-root-unprovisioned; "
            "managed userdebug or eng AVD required for endpoint verification"
        )
        device_evidence = {
            **android_identity,
            "trustStorePath": "",
            "installedCertificateSha256": "",
        }
        system_trust_store = False
    payload = {
        "schema": SCHEMA,
        "target": target,
        "platform": platform_name,
        "device": selected,
        "rootFingerprintSha256": fingerprint,
        "systemTrustStore": system_trust_store,
        "endpointProbe": (
            "verified"
            if platform_name == "ios-simulator" and endpoint_probe
            else "deferred"
            if platform_name == "ios-simulator"
            else "not_applicable"
        ),
        **device_evidence,
        "verification": proof,
        "leases": sorted(leases),
        "status": "installed" if system_trust_store else "launch-degraded",
        "updatedAt": _utc_now(),
    }
    _write_receipt(path, payload)
    return {**payload, "receipt": str(path), "leaseId": normalized_lease}


def verify_device_trust(
    *,
    target: str,
    platform_name: str,
    device: str,
) -> dict[str, Any]:
    selected = resolve_managed_device(platform_name, device)
    path = _receipt_path(target, platform_name, selected)
    receipt = _read_receipt(path)
    if receipt is None:
        raise LocalDeviceTrustError("device system-trust receipt is missing")
    root = root_certificate_path(target)
    fingerprint = _root_fingerprint(root)
    if (
        receipt.get("target") != target
        or receipt.get("platform") != platform_name
        or receipt.get("device") != selected
        or receipt.get("rootFingerprintSha256") != fingerprint
        or receipt.get("status") != "installed"
        or receipt.get("systemTrustStore") is not True
    ):
        raise LocalDeviceTrustError("device system-trust receipt identity mismatch")
    proof = (
        _probe_ios_system_trust(target, selected)
        if platform_name == "ios-simulator"
        else _verify_android_system_trust(selected, root, receipt)
    )
    payload = {**receipt, "verification": proof, "verifiedAt": _utc_now()}
    _write_receipt(path, payload)
    return {**payload, "receipt": str(path)}


def release_device_trust(
    *,
    target: str,
    platform_name: str,
    device: str,
    lease_id: str,
) -> dict[str, Any]:
    selected = resolve_managed_device(platform_name, device)
    path = _receipt_path(target, platform_name, selected)
    receipt = _read_receipt(path)
    if receipt is None:
        raise LocalDeviceTrustError("device system-trust receipt is missing")
    leases = [value for value in receipt.get("leases") or [] if value != lease_id]
    payload = {
        **receipt,
        "leases": leases,
        "status": (
            "installed"
            if leases and receipt.get("systemTrustStore") is True
            else "launch-degraded"
            if leases
            else "managed-root-retained"
            if receipt.get("systemTrustStore") is True
            else "unprovisioned"
        ),
        "updatedAt": _utc_now(),
    }
    _write_receipt(path, payload)
    return {
        **payload,
        "receipt": str(path),
        "revocation": (
            "lease-released"
            if leases
            else "root retained; simctl has no certificate-scoped removal API"
        ),
    }
