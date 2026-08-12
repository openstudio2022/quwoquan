"""Bind a target-scoped canonical host overlay into a managed Android AVD."""

from __future__ import annotations

import hashlib
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.lib.local_target_handoff import (
    LOCAL_TARGETS,
    LOOPBACK_ADDRESS,
    canonical_hosts,
)

_ANDROID_HOSTS = "/system/etc/hosts"
_HOST_RE = re.compile(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?")
_DIGEST_RE = re.compile(r"[0-9A-F]{64}")


class LocalDeviceResolverError(RuntimeError):
    pass


def _adb(
    device: str,
    arguments: list[str],
    *,
    action: str,
    timeout: int = 90,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            ["adb", "-s", device, *arguments],
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LocalDeviceResolverError(f"{action} failed") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise LocalDeviceResolverError(
            f"{action} failed" + (f": {detail[:500]}" if detail else "")
        )
    return result


def _namespace_arguments(namespace_pid: int | None) -> list[str]:
    return (
        ["shell", "nsenter", "-t", str(namespace_pid), "-m", "--"]
        if namespace_pid is not None
        else ["shell"]
    )


def _require_regular_file(
    device: str,
    path: str,
    *,
    namespace_pid: int | None = None,
) -> None:
    result = _adb(
        device,
        [*_namespace_arguments(namespace_pid), "stat", "-c", "%F", path],
        action=f"Android resolver regular-file verification {path}",
    )
    if result.stdout.strip() != "regular file":
        raise LocalDeviceResolverError(
            f"Android resolver path is not a contained regular file: {path}"
        )


def _remote_sha256(
    device: str,
    path: str,
    *,
    namespace_pid: int | None = None,
) -> str:
    result = _adb(
        device,
        [*_namespace_arguments(namespace_pid), "sha256sum", path],
        action=f"Android resolver digest {path}",
    )
    digest = result.stdout.strip().split(maxsplit=1)[0].upper()
    if _DIGEST_RE.fullmatch(digest) is None:
        raise LocalDeviceResolverError("Android resolver digest is invalid")
    return digest


def _pull_regular_file(device: str, remote: str, local: Path) -> bytes:
    _require_regular_file(device, remote)
    before = _remote_sha256(device, remote)
    _adb(device, ["pull", remote, str(local)], action="Android resolver source pull")
    after = _remote_sha256(device, remote)
    payload = local.read_bytes()
    local_digest = hashlib.sha256(payload).hexdigest().upper()
    if before != after or before != local_digest:
        raise LocalDeviceResolverError("Android resolver source changed during read")
    return payload


def _overlay_bytes(target: str, hosts: list[str], source: bytes) -> bytes:
    try:
        source_text = source.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LocalDeviceResolverError("Android hosts source is not UTF-8") from exc
    all_local_hosts = {
        host for local_target in LOCAL_TARGETS for host in canonical_hosts(local_target)
    }
    tokens = {
        token.lower().rstrip(".")
        for line in source_text.splitlines()
        for token in line.split()[1:]
        if line.strip() and not line.lstrip().startswith("#")
    }
    if tokens.intersection(all_local_hosts):
        raise LocalDeviceResolverError(
            "Android hosts source already contains a local target overlay"
        )
    if not hosts or any(_HOST_RE.fullmatch(host) is None for host in hosts):
        raise LocalDeviceResolverError("Android resolver canonical host is invalid")
    separator = b"" if source.endswith(b"\n") else b"\n"
    mappings = "".join(f"{LOOPBACK_ADDRESS} {host}\n" for host in hosts)
    return (
        source
        + separator
        + f"# quwoquan managed resolver target={target}\n{mappings}".encode("ascii")
    )


def _validate_handoff(target: str, handoff: dict[str, Any]) -> list[str]:
    hosts = list(canonical_hosts(target))
    if (
        handoff.get("target") != target
        or handoff.get("address") != LOOPBACK_ADDRESS
        or handoff.get("hosts") != hosts
        or re.fullmatch(r"sha256:[0-9a-f]{64}", str(handoff.get("handoffDigest")))
        is None
    ):
        raise LocalDeviceResolverError("Android resolver handoff is invalid")
    return hosts


def install_android_host_overlay(
    *,
    target: str,
    device: str,
    stage_root: str,
    namespaces: list[dict[str, Any]],
    handoff: dict[str, Any],
) -> dict[str, Any]:
    hosts = _validate_handoff(target, handoff)
    source_stage = f"{stage_root}/hosts-source"
    overlay_stage = f"{stage_root}/hosts"
    with tempfile.TemporaryDirectory(prefix="quwoquan-android-hosts-") as temp:
        source_local = Path(temp) / "hosts-source"
        overlay_local = Path(temp) / "hosts"
        source = _pull_regular_file(device, _ANDROID_HOSTS, source_local)
        overlay = _overlay_bytes(target, hosts, source)
        overlay_local.write_bytes(overlay)
        source_digest = hashlib.sha256(source).hexdigest().upper()
        overlay_digest = hashlib.sha256(overlay).hexdigest().upper()
        for local, remote in (
            (source_local, source_stage),
            (overlay_local, overlay_stage),
        ):
            _adb(device, ["push", str(local), remote], action="Android hosts push")
            _adb(
                device,
                ["shell", "chown", "root:root", remote],
                action="Android hosts ownership",
            )
            _adb(
                device,
                ["shell", "chmod", "0644", remote],
                action="Android hosts permissions",
            )
            _adb(
                device,
                ["shell", "chcon", "u:object_r:system_file:s0", remote],
                action="Android hosts SELinux context",
            )
    if (
        _remote_sha256(device, source_stage) != source_digest
        or _remote_sha256(device, overlay_stage) != overlay_digest
    ):
        raise LocalDeviceResolverError("Android resolver staging digest mismatch")
    for namespace in namespaces:
        pid = int(namespace["representativePid"])
        _require_regular_file(device, _ANDROID_HOSTS, namespace_pid=pid)
        _adb(
            device,
            [
                "shell",
                "nsenter",
                "-t",
                str(pid),
                "-m",
                "--",
                "mount",
                "--bind",
                overlay_stage,
                _ANDROID_HOSTS,
            ],
            action=f"Android resolver bind pid={pid}",
        )
        if _remote_sha256(device, _ANDROID_HOSTS, namespace_pid=pid) != overlay_digest:
            raise LocalDeviceResolverError(
                f"Android resolver mount verification failed pid={pid}"
            )
    return {
        "sourcePath": _ANDROID_HOSTS,
        "sourceStagePath": source_stage,
        "sourceSha256": source_digest,
        "overlayPath": overlay_stage,
        "overlaySha256": overlay_digest,
        "mountedPath": _ANDROID_HOSTS,
        "address": LOOPBACK_ADDRESS,
        "hosts": hosts,
        "handoffDigest": handoff["handoffDigest"],
        "mountNamespaces": namespaces,
    }


def verify_android_host_overlay(
    *,
    target: str,
    device: str,
    stage_root: str,
    namespaces: list[dict[str, Any]],
    handoff: dict[str, Any],
    receipt: Any,
) -> None:
    hosts = _validate_handoff(target, handoff)
    expected_keys = {
        "sourcePath",
        "sourceStagePath",
        "sourceSha256",
        "overlayPath",
        "overlaySha256",
        "mountedPath",
        "address",
        "hosts",
        "handoffDigest",
        "mountNamespaces",
    }
    if not isinstance(receipt, dict) or set(receipt) != expected_keys:
        raise LocalDeviceResolverError("Android resolver receipt schema mismatch")
    source_stage = f"{stage_root}/hosts-source"
    overlay_stage = f"{stage_root}/hosts"
    if (
        receipt["sourcePath"] != _ANDROID_HOSTS
        or receipt["sourceStagePath"] != source_stage
        or receipt["overlayPath"] != overlay_stage
        or receipt["mountedPath"] != _ANDROID_HOSTS
        or receipt["address"] != LOOPBACK_ADDRESS
        or receipt["hosts"] != hosts
        or receipt["handoffDigest"] != handoff["handoffDigest"]
        or receipt["mountNamespaces"] != namespaces
        or _DIGEST_RE.fullmatch(str(receipt["sourceSha256"])) is None
        or _DIGEST_RE.fullmatch(str(receipt["overlaySha256"])) is None
    ):
        raise LocalDeviceResolverError("Android resolver receipt drift")
    with tempfile.TemporaryDirectory(prefix="quwoquan-android-hosts-verify-") as temp:
        local = Path(temp) / "hosts-source"
        source = _pull_regular_file(device, source_stage, local)
    expected_overlay = _overlay_bytes(target, hosts, source)
    if (
        hashlib.sha256(source).hexdigest().upper() != receipt["sourceSha256"]
        or hashlib.sha256(expected_overlay).hexdigest().upper()
        != receipt["overlaySha256"]
        or _remote_sha256(device, overlay_stage) != receipt["overlaySha256"]
    ):
        raise LocalDeviceResolverError("Android resolver overlay digest drift")
    for namespace in namespaces:
        pid = int(namespace["representativePid"])
        _require_regular_file(device, _ANDROID_HOSTS, namespace_pid=pid)
        if (
            _remote_sha256(device, _ANDROID_HOSTS, namespace_pid=pid)
            != receipt["overlaySha256"]
        ):
            raise LocalDeviceResolverError(
                f"Android resolver namespace drift pid={pid}"
            )
