#!/usr/bin/env python3
"""Plan reference-safe OCI release artifact garbage collection.

The planner is intentionally read-only. A deletion executor may consume its
``eligible`` list only after a separately authorized hosted mutation.
"""
from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

_REF = re.compile(r"^ghcr\.io/[a-z0-9._/-]+@sha256:[0-9a-f]{64}$")


def plan_gc(*, inventory: Sequence[Mapping[str, Any]], references: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    referenced = set()
    for item in references:
        ref = str(item.get("ref") or "")
        reason = str(item.get("reason") or "")
        if _REF.fullmatch(ref) is None or reason not in {"released", "last-known-good", "active-candidate", "audit-window"}:
            raise ValueError("OCI.GC.REFERENCE_INDEX_INVALID")
        referenced.add(ref)
    eligible = []
    protected = []
    seen = set()
    for item in inventory:
        ref = str(item.get("ref") or "")
        if _REF.fullmatch(ref) is None or ref in seen:
            raise ValueError("OCI.GC.INVENTORY_INVALID")
        seen.add(ref)
        descriptor = {"ref": ref, "createdAt": str(item.get("createdAt") or "")}
        (protected if ref in referenced else eligible).append(descriptor)
    return {"schema": "quwoquan.oci_gc_plan.v1", "eligible": sorted(eligible, key=lambda x: x["ref"]),
            "protected": sorted(protected, key=lambda x: x["ref"]), "applyAuthorized": False}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--references", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    references = json.loads(args.references.read_text(encoding="utf-8"))
    if not isinstance(inventory, list) or not isinstance(references, list):
        raise ValueError("OCI.GC.INPUT_INVALID")
    plan = plan_gc(inventory=inventory, references=references)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
