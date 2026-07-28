#!/usr/bin/env python3
from __future__ import annotations

import socket
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CHECKS = (
    (
        "api-health",
        "api.alpha.quwoquan.com",
        17000,
        "/healthz",
        None,
        "200",
    ),
    (
        "app-config",
        "api.alpha.quwoquan.com",
        17000,
        "/config/app",
        None,
        "200",
    ),
    (
        "legal-document",
        "api.alpha.quwoquan.com",
        17000,
        "/legal/user-agreement",
        None,
        "200",
    ),
    (
        "avatar-media-health",
        "cdn.alpha.quwoquan.com",
        17100,
        "/healthz",
        None,
        "200",
    ),
    (
        "image-media-health",
        "cdn.alpha.quwoquan.com",
        17100,
        "/healthz",
        None,
        "200",
    ),
    (
        "video-media-health",
        "cdn.alpha.quwoquan.com",
        17100,
        "/healthz",
        None,
        "200",
    ),
    (
        "upload-health",
        "upload.alpha.quwoquan.com",
        17100,
        "/healthz",
        None,
        "200",
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
) -> str:
    cmd = [
        "curl",
        "-fsS",
        "-o",
        "/dev/null",
        "-w",
        "%{http_code}",
    ]
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

    if issues:
        print("[verify_alpha_https_public_plane] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        print("Remediation: run `python3 quwoquan_ops/cli/stackctl.py up --target alpha-local --skip-app --workload content-release`.")
        return 1

    print("[verify_alpha_https_public_plane] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
