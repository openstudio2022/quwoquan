#!/usr/bin/env python3
"""Verify data consistency coverage is traceable."""

from __future__ import annotations

from nonfunctional_coverage_lib import Failures, ROOT


def main() -> int:
    failures = Failures()
    # `publish/**` is the approved object set and may legitimately be empty before
    # the first reviewed promotion. Git cannot preserve an empty directory, and a
    # marker file would violate publish purity. Gate the versioned contract and
    # canonical producer instead; release/UAT gates own proof of non-empty hosted
    # content for a production candidate.
    failures.require_path(
        ROOT / "quwoquan_data" / "schema" / "publish",
        "canonical publish schema truth source",
    )
    failures.require_path(
        ROOT
        / "quwoquan_data"
        / "scripts"
        / "content"
        / "release"
        / "canonical",
        "canonical publish producer",
    )
    failures.require_any_canonical_test(
        label="data consistency coverage",
        patterns=(
            r"consistency",
            r"idempot",
            r"projection",
            r"outbox",
            r"publish",
            r"import",
            r"release",
            r"stable[_-]?id",
            r"data[_-]?consistency",
        ),
        minimum=3,
    )
    failures.require_any_text(
        label="data consistency governance",
        roots=(ROOT / "specs" / "feature-tree", ROOT / "quwoquan_data" / "sop"),
        patterns=(r"data_consistency", r"publish", r"import", r"release", r"idempot"),
    )
    return failures.exit_code("[verify] OK: data consistency coverage checked")


if __name__ == "__main__":
    raise SystemExit(main())
