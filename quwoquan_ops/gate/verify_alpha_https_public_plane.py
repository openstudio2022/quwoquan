#!/usr/bin/env python3
from __future__ import annotations

import socket
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.local_target_tls import (
    LocalTargetTlsError,
    resolve_local_target_root_ca,
)
CHECKS = (
    (
        "api-health",
        "alpha-api.quwoquan-env.test",
        17000,
        "/healthz",
        None,
        "200",
    ),
    (
        "app-config",
        "alpha-api.quwoquan-env.test",
        17000,
        "/config/app",
        None,
        "200",
    ),
    (
        "product-ops-health",
        "alpha-product-ops.quwoquan-env.test",
        17010,
        "/healthz",
        None,
        "200",
    ),
    (
        "avatar",
        "alpha-avatar.quwoquan-env.test",
        17100,
        "/media/avatar/s/archived-avatar/user/fixture_user_friend/avatar.png",
        None,
        "200",
    ),
    (
        "chat-group-avatar-current-contract",
        "alpha-avatar.quwoquan-env.test",
        17100,
        "/media/avatar/s/archived-avatar/group/fixture_conv_group/composite.png",
        None,
        "200",
    ),
    (
        "home-post-author-avatar",
        "alpha-avatar.quwoquan-env.test",
        17100,
        "/media/avatar/s/archived-avatar/user/fixture_user_article/v1/avatar.png",
        None,
        "200",
    ),
    (
        "image",
        "alpha-image.quwoquan-env.test",
        17100,
        "/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png",
        None,
        "200",
    ),
    (
        "video-range",
        "alpha-video.quwoquan-env.test",
        17100,
        "/media/video/s/video-primary-0001/post/video-content-0001/source.mp4",
        "bytes=0-1",
        "206",
    ),
    (
        "upload-health",
        "alpha-upload.quwoquan-env.test",
        17100,
        "/healthz",
        None,
        "200",
    ),
)

ANDROID_LOOPBACK_CHECKS = (
    (
        "android-emulator-chat-group-avatar-current-contract",
        "10.0.2.2",
        17100,
        "/media/avatar/s/archived-avatar/group/fixture_conv_group/composite.png",
        None,
        "200",
    ),
    (
        "android-emulator-home-post-author-avatar",
        "10.0.2.2",
        17100,
        "/media/avatar/s/archived-avatar/user/fixture_user_article/v1/avatar.png",
        None,
        "200",
    ),
    (
        "android-emulator-image",
        "10.0.2.2",
        17100,
        "/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png",
        None,
        "200",
    ),
    (
        "android-emulator-video-range",
        "10.0.2.2",
        17100,
        "/media/video/s/video-primary-0001/post/video-content-0001/source.mp4",
        "bytes=0-1",
        "206",
    ),
)


def _loopback_addresses(host: str) -> set[str]:
    try:
        return {item[4][0] for item in socket.getaddrinfo(host, None)}
    except socket.gaierror:
        return set()


def _curl_status(
    host: str,
    port: int,
    path: str,
    range_header: str | None,
    *,
    connect_to: str | None = None,
    cacert: Path | None = None,
) -> str:
    cmd = [
        "curl",
        "-fsS",
        "-o",
        "/dev/null",
        "-w",
        "%{http_code}",
    ]
    if cacert is not None:
        cmd.extend(["--cacert", str(cacert)])
    if connect_to is not None:
        cmd.extend(["--connect-to", f"{host}:{port}:{connect_to}:{port}"])
    if range_header:
        cmd.extend(["-H", f"Range: {range_header}"])
    cmd.append(f"https://{host}:{port}{path}")
    result = subprocess.run(cmd, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        return f"curl-failed:{detail[-1] if detail else result.returncode}"
    return result.stdout.strip()


def main() -> int:
    issues: list[str] = []
    checks = CHECKS
    android_checks = ANDROID_LOOPBACK_CHECKS

    hosts = sorted({host for _, host, _, _, _, _ in checks})
    for host in hosts:
        addresses = _loopback_addresses(host)
        if not addresses:
            issues.append(f"{host} does not resolve")
            continue
        if not any(address.startswith("127.") or address == "::1" for address in addresses):
            issues.append(f"{host} resolves outside loopback: {', '.join(sorted(addresses))}")

    for name, host, port, path, range_header, expected in checks:
        status = _curl_status(host, port, path, range_header)
        if status != expected:
            issues.append(
                f"{name} expected HTTP {expected}, got {status}: https://{host}:{port}{path}"
            )

    try:
        local_root_ca = resolve_local_target_root_ca("alpha-local")
    except LocalTargetTlsError as exc:
        local_root_ca = None
        issues.append(str(exc))
    if local_root_ca is not None:
        for name, host, port, path, range_header, expected in android_checks:
            status = _curl_status(
                host,
                port,
                path,
                range_header,
                connect_to="127.0.0.1",
                cacert=local_root_ca,
            )
            if status != expected:
                issues.append(
                    f"{name} expected HTTP {expected}, got {status}: https://{host}:{port}{path}"
                )

    if issues:
        print("[verify_alpha_https_public_plane] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        print("Remediation: run `bash quwoquan_ops/cli/alpha/start_alpha_mock_stack.sh up` and allow local DNS/CA trust setup.")
        return 1

    print("[verify_alpha_https_public_plane] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
