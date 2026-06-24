#!/usr/bin/env python3
from __future__ import annotations

import ipaddress
import re
import sys
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[3]
APP_LIB = ROOT / "quwoquan_app" / "lib"
URL_RE = re.compile(r"https?://[^\s'\"`)>]+")
ALLOWED_PUBLIC_HOSTS = {"schema.org"}
ALLOWED_PRIVATE_HOSTS = {"localhost", "127.0.0.1", "::1", "10.0.2.2"}
ALLOWED_PUBLIC_HOST_SUFFIXES = (".quwoquan-env.test",)


def _is_comment_only_line(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("//") or stripped.startswith("*")


def _is_allowed_host(host: str) -> bool:
    normalized = host.strip("[]").lower()
    if normalized in ALLOWED_PUBLIC_HOSTS or normalized in ALLOWED_PRIVATE_HOSTS:
        return True
    if any(
        normalized.endswith(suffix)
        and normalized[: -len(suffix)].strip(".")
        for suffix in ALLOWED_PUBLIC_HOST_SUFFIXES
    ):
        return True
    try:
        ipaddress.ip_address(normalized)
        return True
    except ValueError:
        return False


def main() -> int:
    issues: list[str] = []
    for path in sorted(APP_LIB.rglob("*.dart")):
        rel = path.relative_to(ROOT).as_posix()
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _is_comment_only_line(line):
                continue
            for match in URL_RE.finditer(line):
                url = match.group(0)
                if "$" in url:
                    continue
                host = urlparse(url).hostname or ""
                if not host or _is_allowed_host(host):
                    continue
                issues.append(f"{rel}:{line_no}: {host} ({url})")

    if issues:
        print("[verify_runtime_host_literals] FAIL")
        print("lib/ runtime code must not embed third-party hosts.")
        print("Use CloudRuntimeConfig IP bases plus media object keys, or a dart-define override.")
        for issue in issues:
            print(f"  - {issue}")
        return 1

    print("[verify_runtime_host_literals] OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
