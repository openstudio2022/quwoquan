#!/usr/bin/env python3
"""Verify data consistency coverage is traceable."""

from __future__ import annotations

from nonfunctional_coverage_lib import Failures, ROOT


def main() -> int:
    failures = Failures()
    publish_paths = ROOT / "quwoquan_data" / "scripts" / "core" / "paths.py"
    failures.require_path(publish_paths, "data publish path authority")
    if publish_paths.is_file() and (
        'PUBLISH_ROOT = Path(os.environ.get("QWQ_PUBLISH_ROOT", DATA_ROOT / "publish"))'
        not in publish_paths.read_text(encoding="utf-8")
    ):
        failures.add("data publish truth source: canonical PUBLISH_ROOT declaration is missing")
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
