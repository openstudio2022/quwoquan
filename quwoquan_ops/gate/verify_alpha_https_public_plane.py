#!/usr/bin/env python3
from __future__ import annotations

import re
import socket
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LOCAL_ROOT_CA = (
    ROOT
    / ".qwq_output"
    / "local"
    / "alpha-local"
    / "tls"
    / "ca"
    / "root.crt"
)
APP_CHAT_MOCK_DATA_PATH = (
    ROOT
    / "quwoquan_app"
    / "lib"
    / "cloud"
    / "services"
    / "chat"
    / "mock"
    / "chat_mock_data.dart"
)
GROUP_AVATAR_CALL_RE = re.compile(r"groupAvatarFor\('([^']+)'\)")


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
        "/media/avatar/conversation/conv_002/v1/mock.png",
        None,
        "200",
    ),
    (
        "chat-group-avatar-current-contract",
        "alpha-avatar.quwoquan-env.test",
        17100,
        "/media/avatar/s/archived-avatar/conversation/conv_grid_7/v1/mock.png",
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
        "/media/avatar/s/archived-avatar/conversation/conv_grid_7/v1/mock.png",
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


def _collect_app_mock_group_avatar_paths() -> list[str]:
    text = APP_CHAT_MOCK_DATA_PATH.read_text(encoding="utf-8")
    conversation_ids = {
        match.group(1)
        for match in GROUP_AVATAR_CALL_RE.finditer(text)
        if "$" not in match.group(1)
    }
    if "groupAvatarFor('conv_grid_$n')" in text:
        conversation_ids.update(f"conv_grid_{index}" for index in range(1, 17))
    return [
        f"/media/avatar/s/archived-avatar/conversation/{conversation_id}/mock.png"
        for conversation_id in sorted(conversation_ids)
    ]


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
    app_group_avatar_checks = tuple(
        (
            f"app-mock-group-avatar-{path.split('/')[-3]}",
            "alpha-avatar.quwoquan-env.test",
            17100,
            path,
            None,
            "200",
        )
        for path in _collect_app_mock_group_avatar_paths()
    )
    android_group_avatar_checks = tuple(
        (
            f"android-emulator-app-mock-group-avatar-{path.split('/')[-3]}",
            "10.0.2.2",
            17100,
            path,
            None,
            "200",
        )
        for path in _collect_app_mock_group_avatar_paths()
    )
    checks = (*CHECKS, *app_group_avatar_checks)
    android_checks = (*ANDROID_LOOPBACK_CHECKS, *android_group_avatar_checks)

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

    if not LOCAL_ROOT_CA.is_file():
        issues.append(f"local root CA missing: {LOCAL_ROOT_CA}")
    else:
        for name, host, port, path, range_header, expected in android_checks:
            status = _curl_status(
                host,
                port,
                path,
                range_header,
                connect_to="127.0.0.1",
                cacert=LOCAL_ROOT_CA,
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
