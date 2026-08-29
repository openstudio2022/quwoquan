#!/usr/bin/env python3
"""Verify security and privacy coverage is traceable."""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

from nonfunctional_coverage_lib import Failures, ROOT


def main() -> int:
    failures = Failures()
    failures.require_path(
        ROOT / "quwoquan_service" / "contracts" / "metadata" / "log_kv_policy.yaml",
        "log key/value redaction policy",
    )
    failures.require_any_canonical_test(
        label="security/privacy coverage",
        patterns=(
            r"auth",
            r"permission",
            r"privacy",
            r"redact",
            r"token",
            r"secret",
            r"security",
            r"audit",
        ),
        minimum=3,
    )
    failures.require_any_text(
        label="security/privacy governance",
        roots=(ROOT / "specs" / "feature-tree",),
        patterns=(r"privacy", r"auth", r"permission", r"security", r"audit"),
    )
    return failures.exit_code("[verify] OK: security coverage checked")


if __name__ == "__main__":
    raise SystemExit(main())
