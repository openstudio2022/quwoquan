#!/usr/bin/env python3
"""Rewrite acceptance recorded refs to canonical test paths and .qwq_output/env/repo/runs/tests reports."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from test_directory_inventory_lib import ROOT, recorded_file_is_canonical


FEATURE_TREE = ROOT / "specs" / "feature-tree"
ACCEPTANCE_GROUPS = (
    "uat_acceptance",
    "domain_acceptance",
    "sit_acceptance",
    "gwt_acceptance",
    "contract_acceptance",
)
DONE_STATUSES = {"implemented", "completed"}
TEST_FILE_SUFFIXES = (".dart", ".go", ".py")


def normalize_record(record: Any) -> tuple[dict[str, str] | None, str | None]:
    kind: str | None = None
    value: str | None = None
    if isinstance(record, dict):
        if record.get("file"):
            kind, value = "file", str(record["file"]).strip()
        elif record.get("artifact"):
            kind, value = "artifact", str(record["artifact"]).strip()
        elif record.get("command"):
            kind, value = "command", str(record["command"]).strip()
    else:
        text = str(record).strip()
        if text.startswith("file:"):
            kind, value = "file", text.split(":", 1)[1].strip()
        elif text.startswith("artifact:"):
            kind, value = "artifact", text.split(":", 1)[1].strip()
        elif text.startswith("command:"):
            kind, value = "command", text.split(":", 1)[1].strip()
        elif text:
            kind, value = "file", text
    if not kind or not value:
        return None, None
    if kind == "file":
        if recorded_file_is_canonical(value):
            return {"file": value}, None
        if value.endswith(TEST_FILE_SUFFIXES):
            return None, f"[removed_recorded_noncanonical] {value}"
        return None, f"[removed_recorded_reference] {value}"
    if kind == "artifact":
        if value.startswith(".qwq_output/env/repo/runs/tests/") and value.endswith("report.json"):
            return {"artifact": value}, None
        return None, f"[migrated_from_recorded_artifact] {value}"
    return None, f"[migrated_from_recorded_command] {value}"


def migrate_file(path: Path) -> bool:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    changed = False
    for group_name in ACCEPTANCE_GROUPS:
        group = data.get(group_name) or {}
        if not isinstance(group, dict):
            continue
        for item in group.values():
            if not isinstance(item, dict):
                continue
            tests = item.setdefault("tests", {})
            recorded = tests.get("recorded") or []
            if not isinstance(recorded, list):
                continue
            notes = item.setdefault("notes", [])
            if not isinstance(notes, list):
                notes = [str(notes)]
                item["notes"] = notes
            normalized: list[dict[str, str]] = []
            for record in recorded:
                mapped, note = normalize_record(record)
                if mapped is not None:
                    normalized.append(mapped)
                if note and note not in notes:
                    notes.append(note)
            if normalized != recorded:
                tests["recorded"] = normalized
                changed = True
            status = str(item.get("status") or "").strip()
            if status in DONE_STATUSES and not normalized:
                item["status"] = "pending_evidence"
                changed = True
    if changed:
        path.write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False),
            encoding="utf-8",
        )
    return changed


def main() -> int:
    changed = 0
    for path in sorted(FEATURE_TREE.rglob("acceptance.yaml")):
        if migrate_file(path):
            changed += 1
            print(f"[normalize] {path.relative_to(ROOT)}")
    print(f"[normalize] changed_files={changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
