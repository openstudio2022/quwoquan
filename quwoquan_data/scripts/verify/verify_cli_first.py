#!/usr/bin/env python3
"""Enforce one business CLI; only engineering gates may be direct-run."""
from __future__ import annotations

import re
import sys
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
_MAIN_RE = re.compile(r"__name__\s*==\s*[\"']__main__[\"']")


def main() -> None:
    offenders: list[str] = []
    verify_entries = 0
    for path in sorted(SCRIPTS_ROOT.rglob("*.py")):
        rel = path.relative_to(SCRIPTS_ROOT).as_posix()
        try:
            direct_run = bool(_MAIN_RE.search(path.read_text(encoding="utf-8")))
        except OSError:
            continue
        if not direct_run:
            continue
        if rel == "cli.py":
            continue
        if rel.startswith("verify/"):
            verify_entries += 1
            continue
        offenders.append(rel)

    if offenders:
        print("[verify-cli-first] FAILED: direct-run business scripts detected", file=sys.stderr)
        for rel in offenders:
            print(f"  - {rel} (expose through scripts/cli.py)", file=sys.stderr)
        raise SystemExit(1)

    print(
        "[verify-cli-first] PASSED "
        f"(business_entry=cli.py engineering_gates={verify_entries})"
    )


if __name__ == "__main__":
    main()
