#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[3]
APP_LIB = ROOT / "quwoquan_app" / "lib"
URL_RE = re.compile(
    r"https?://(?:\[[0-9A-Fa-f:.]+\]|[A-Za-z0-9][A-Za-z0-9.-]*)"
    r"(?::[0-9]+)?[^\s'\"`)>]*"
)
ALLOWED_PUBLIC_HOSTS = {"schema.org", "quwoquan.com"}
ALLOWED_PUBLIC_HOST_SUFFIXES = (".quwoquan.com",)


def _is_comment_only_line(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("//") or stripped.startswith("*")


def _is_allowed_host(host: str) -> bool:
    normalized = host.strip("[]").lower()
    if normalized in ALLOWED_PUBLIC_HOSTS:
        return True
    return any(
        normalized.endswith(suffix)
        and normalized[: -len(suffix)].strip(".")
        for suffix in ALLOWED_PUBLIC_HOST_SUFFIXES
    )


def _self_test() -> None:
    controls = {
        "https://example.com/path": "example.com",
        "http://[::1]:8080/healthz": "::1",
        "https://127.0.0.1:17000/healthz": "127.0.0.1",
    }
    for source, expected_host in controls.items():
        match = URL_RE.search(source)
        if match is None or urlparse(match.group(0)).hostname != expected_host:
            raise AssertionError(f"runtime host detector missed {source}")
    if URL_RE.search(r"RegExp(r'(https://[^\s?#]+)\?[^\s#]*')") is not None:
        raise AssertionError("runtime host detector treated a regex pattern as a URL")


def main() -> int:
    _self_test()
    issues: list[str] = []
    for path in sorted(APP_LIB.rglob("*.dart")):
        rel = path.relative_to(ROOT).as_posix()
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _is_comment_only_line(line):
                continue
            for match in URL_RE.finditer(line):
                url = match.group(0)
                # Raw RegExp fragments such as ``r'(https://[^\\s?#]+)'`` are
                # patterns, not runtime URL literals.  URL_RE intentionally
                # stays small, so exclude escaped pattern fragments before
                # handing the candidate to urllib's IPv6-aware parser.
                if "$" in url or "\\" in url:
                    continue
                try:
                    host = urlparse(url).hostname or ""
                except ValueError:
                    issues.append(f"{rel}:{line_no}: invalid URL literal ({url})")
                    continue
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
