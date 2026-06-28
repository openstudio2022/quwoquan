#!/usr/bin/env python3
"""Verify content-service application layer dependency boundaries."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APPLICATION_ROOT = ROOT / "services/content-service/internal/application"
INFRA_IMPORT_PREFIX = "quwoquan_service/services/content-service/internal/infrastructure"


def go_imports(source: str) -> list[str]:
    imports: list[str] = []
    for match in re.finditer(r'^\s*import\s+(?:"([^"]+)"|\((.*?)\))', source, re.M | re.S):
        single = match.group(1)
        if single is not None:
            imports.append(single)
            continue
        block = match.group(2) or ""
        imports.extend(re.findall(r'"([^"]+)"', block))
    return imports


def main() -> int:
    failures: list[str] = []

    direct_go_files = sorted(APPLICATION_ROOT.glob("*.go"))
    if direct_go_files:
        failures.append(
            "content-service internal/application root must not contain Go implementation files:\n"
            + "\n".join(f"  - {path.relative_to(ROOT)}" for path in direct_go_files)
        )

    for path in sorted(APPLICATION_ROOT.rglob("*.go")):
        if path.name.endswith("_test.go"):
            continue
        imports = go_imports(path.read_text(encoding="utf-8", errors="ignore"))
        bad = [imp for imp in imports if imp.startswith(INFRA_IMPORT_PREFIX)]
        if bad:
            failures.append(
                f"{path.relative_to(ROOT)} imports infrastructure from application layer:\n"
                + "\n".join(f"  - {imp}" for imp in bad)
            )

    if failures:
        print("[verify-content-application-boundaries] FAIL", file=sys.stderr)
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1

    print("[verify-content-application-boundaries] OK", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
