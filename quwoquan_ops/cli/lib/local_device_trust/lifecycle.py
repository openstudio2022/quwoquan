"""设备信任 receipt 的安装 / 验证 / 释放公开生命周期（逐字搬移）。

``verify_certificate`` / ``resolve_managed_device`` / ``root_certificate_path`` /
``_receipt_path`` / ``_android_identity`` / ``_install_ios`` / ``_install_android`` /
``_verify_android_system_trust`` / ``_probe_ios_system_trust`` 是测试的
patch 锚点，包内消费一律经 ``_pkg.`` 属性访问。
"""

from __future__ import annotations

from typing import Any

import quwoquan_ops.cli.lib.local_device_trust as _pkg

from .constants import SCHEMA
from .device_commands import _read_receipt, _root_fingerprint, _utc_now, _write_receipt
from .errors import AndroidSystemTrustUnavailable, LocalDeviceTrustError


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
    _pkg.verify_certificate(target)
    selected = _pkg.resolve_managed_device(platform_name, device)
    root = _pkg.root_certificate_path(target)
    fingerprint = _root_fingerprint(root)
    path = _pkg._receipt_path(target, platform_name, selected)
    previous = _read_receipt(path)
    leases = list(previous.get("leases") or []) if previous else []
    # trust 回执必须绑定真实 consumer lease，禁止 fabricated lease 身份。
    normalized_lease = str(lease_id or "").strip()
    if not normalized_lease:
        raise LocalDeviceTrustError(
            "device trust install requires a real consumer lease id"
        )
    if normalized_lease not in leases:
        leases.append(normalized_lease)
    android_identity = (
        _pkg._android_identity(selected) if platform_name == "android-emulator" else {}
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
        proof = _pkg._verify_android_system_trust(selected, root, previous)
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
            proof = _pkg._install_ios(
                target,
                selected,
                root,
                endpoint_probe=endpoint_probe,
            )
        else:
            device_evidence = _pkg._install_android(
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
    selected = _pkg.resolve_managed_device(platform_name, device)
    path = _pkg._receipt_path(target, platform_name, selected)
    receipt = _read_receipt(path)
    if receipt is None:
        raise LocalDeviceTrustError("device system-trust receipt is missing")
    root = _pkg.root_certificate_path(target)
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
        _pkg._probe_ios_system_trust(target, selected)
        if platform_name == "ios-simulator"
        else _pkg._verify_android_system_trust(selected, root, receipt)
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
    selected = _pkg.resolve_managed_device(platform_name, device)
    path = _pkg._receipt_path(target, platform_name, selected)
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
