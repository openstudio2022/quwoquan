"""Digest and verify Android trust-store overlays across mount namespaces."""

from __future__ import annotations

import re
import shlex
import subprocess
from pathlib import Path
from typing import Any

_CERTIFICATE_NAME_RE = re.compile(r"[0-9a-f]{8}\.0")
_DIGEST_RE = re.compile(r"[0-9a-fA-F]{64}")


class AndroidTrustOverlayError(RuntimeError):
    pass


def _run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            argv,
            text=True,
            capture_output=True,
            timeout=90,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AndroidTrustOverlayError("Android trust-store command failed") from exc


def remote_tree_sha256(
    device: str,
    remote: str,
    *,
    exclude_name: str = "",
    namespace_pid: int | None = None,
) -> str:
    if exclude_name and _CERTIFICATE_NAME_RE.fullmatch(exclude_name) is None:
        raise AndroidTrustOverlayError("Android trust-store exclusion is invalid")
    command = (
        "set -eu; "
        f"root={shlex.quote(remote)}; exclude={shlex.quote(exclude_name)}; "
        'test -d "$root"; cd "$root"; '
        'test -z "$(find . -mindepth 1 ! -type f -print -quit)"; '
        "if test -n \"$exclude\"; then "
        "find . -type f ! -name \"$exclude\" -exec sha256sum '{}' ';'; "
        "else find . -type f -exec sha256sum '{}' ';'; fi | "
        "LC_ALL=C sort | sha256sum"
    )
    argv = ["adb", "-s", device, "shell"]
    if namespace_pid is not None:
        argv.extend(["nsenter", "-t", str(namespace_pid), "-m", "--"])
    argv.extend(["sh", "-c", shlex.quote(command)])
    result = _run(argv)
    if result.returncode != 0:
        return ""
    digest = result.stdout.strip().split(maxsplit=1)[0]
    return digest.upper() if _DIGEST_RE.fullmatch(digest) else ""


def verify_runtime_trust_stores(
    device: str,
    stores: list[dict[str, Any]],
    namespaces: list[dict[str, Any]],
    expected_certificate_digest: str,
    *,
    remote_sha256: Any,
) -> int:
    for store in stores:
        staged = str(store["stagedStorePath"])
        certificate_name = Path(str(store["certificatePath"])).name
        expected_base = str(store["sourceStoreSha256"])
        expected_incremental = str(store["incrementalStoreSha256"])
        if (
            remote_sha256(device, f"{staged}/{certificate_name}")
            != expected_certificate_digest
            or remote_tree_sha256(device, staged, exclude_name=certificate_name)
            != expected_base
            or remote_tree_sha256(device, staged) != expected_incremental
        ):
            raise AndroidTrustOverlayError(
                f"Android {store['kind']} staged trust store verification failed"
            )
        for namespace in namespaces:
            pid = int(namespace["representativePid"])
            target = str(store["trustStorePath"])
            certificate = str(store["certificatePath"])
            if (
                remote_sha256(device, certificate, namespace_pid=pid)
                != expected_certificate_digest
                or remote_tree_sha256(
                    device,
                    target,
                    exclude_name=certificate_name,
                    namespace_pid=pid,
                )
                != expected_base
                or remote_tree_sha256(device, target, namespace_pid=pid)
                != expected_incremental
            ):
                raise AndroidTrustOverlayError(
                    f"Android {store['kind']} trust store verification failed in "
                    f"mount namespace pid={pid}"
                )
    return len(namespaces)
