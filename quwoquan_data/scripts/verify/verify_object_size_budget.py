#!/usr/bin/env python3
"""Verify every canonical content object stays inside its storage budget.

The budget is measured on the object's logical byte closure: the object's own
documents plus each distinct media entry it references, counted once. Physical
duplicates of the same content inside one object are a separate reference-
semantics defect and must not be able to buy an object extra budget here.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_ROOT))

from core.content_library import MediaHoldingError, resolve_media_holding
from core.media_asset_url import is_cas_media_object_key
from core.paths import PUBLISH_ROOT

MEBIBYTE = 1024 * 1024
# One object is one unit of consumer value, so its cost is capped per carrier.
# Video carries an encoded track and gets the larger cap; every text/image
# carrier shares the smaller one.
VIDEO_OBJECT_BUDGET_BYTES = 50 * MEBIBYTE
DEFAULT_OBJECT_BUDGET_BYTES = 10 * MEBIBYTE
_ASSET_REFS_FILENAMES = ("asset.refs.json", "assets.refs.json")


@dataclass(frozen=True, slots=True)
class ObjectClosure:
    ref: str
    carrier: str
    budget_bytes: int
    document_bytes: int
    media_bytes: int
    largest_asset_bytes: int = 0

    @property
    def closure_bytes(self) -> int:
        return self.document_bytes + self.media_bytes

    @property
    def over_budget_bytes(self) -> int:
        return max(self.closure_bytes - self.budget_bytes, 0)


class ObjectBudgetVerdict(StrEnum):
    """Why one object is refused, kept separable because the remedies differ."""

    WITHIN_BUDGET = "within_budget"
    CLOSURE_OVER_BUDGET = "closure_over_budget"
    SINGLE_ASSET_OVER_BUDGET = "single_asset_over_budget"


def _object_budget_bytes(carrier: str) -> int:
    if carrier == "video":
        return VIDEO_OBJECT_BUDGET_BYTES
    return DEFAULT_OBJECT_BUDGET_BYTES


def object_carrier(object_kind: str, object_ref: str) -> str:
    """Name the carrier that owns the budget for one object reference."""
    if object_kind == "entities":
        return "entity"
    head = str(object_ref or "").strip("/").split("/")[0]
    return head


def _asset_refs_path(object_root: Path) -> Path | None:
    """Return the object's single asset refs document, or None when it owns no media."""
    present = [
        object_root / name
        for name in _ASSET_REFS_FILENAMES
        if (object_root / name).is_file()
    ]
    if not present:
        return None
    if len(present) != 1:
        raise ValueError(f"object must own exactly one asset refs document: {object_root}")
    return present[0]


def _referenced_media_bytes(object_root: Path) -> tuple[int, int, list[str]]:
    """Sum the distinct media bodies one object references, resolved in the library.

    Publish carries the reference, the library carries the body, so the cost of
    an object is measured where the bytes actually are. A reference the library
    cannot honour is an unresolved closure, not zero bytes. The largest single
    body travels with the total because one oversized asset and too many assets
    hand the operator two different next steps.
    """
    refs_path = _asset_refs_path(object_root)
    if refs_path is None:
        return 0, 0, []
    document = json.loads(refs_path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise TypeError(f"asset refs document must be an object: {refs_path}")
    issues: list[str] = []
    distinct: dict[str, int] = {}
    for row in document.get("assets") or []:
        if not isinstance(row, dict):
            issues.append(f"asset refs row is not an object: {refs_path}")
            continue
        object_key = str(row.get("objectKey") or "")
        sha256 = str(row.get("sha256") or "")
        if not is_cas_media_object_key(object_key) or not sha256:
            issues.append(f"asset refs row has no content-addressed identity: {object_key}")
            continue
        try:
            entry = resolve_media_holding(sha256)
        except (MediaHoldingError, ValueError):
            issues.append(f"referenced media entry is missing: {object_key}")
            continue
        distinct[sha256] = entry.stat().st_size
    return sum(distinct.values()), max(distinct.values(), default=0), issues


def _document_bytes(object_root: Path) -> int:
    total = 0
    for path in object_root.rglob("*"):
        if path.is_file():
            total += path.stat().st_size
    return total


def object_closure(
    object_root: Path,
    *,
    ref: str,
    carrier: str,
) -> tuple[ObjectClosure, list[str]]:
    """Measure the logical byte closure of one object before it is sealed."""
    media_bytes, largest_asset_bytes, issues = _referenced_media_bytes(object_root)
    closure = ObjectClosure(
        ref=ref,
        carrier=carrier,
        budget_bytes=_object_budget_bytes(carrier),
        document_bytes=_document_bytes(object_root),
        media_bytes=media_bytes,
        largest_asset_bytes=largest_asset_bytes,
    )
    return closure, issues


def budget_verdict(closure: ObjectClosure) -> ObjectBudgetVerdict:
    """Decide whether one object may be sealed, and if not, on which cause."""
    if closure.largest_asset_bytes > closure.budget_bytes:
        return ObjectBudgetVerdict.SINGLE_ASSET_OVER_BUDGET
    if closure.over_budget_bytes > 0:
        return ObjectBudgetVerdict.CLOSURE_OVER_BUDGET
    return ObjectBudgetVerdict.WITHIN_BUDGET


def describe_closure(closure: ObjectClosure) -> str:
    """Render one closure measurement for an operator-facing refusal."""
    return (
        f"{closure.ref} carrier={closure.carrier} "
        f"closure={closure.closure_bytes / MEBIBYTE:.2f}MiB "
        f"largestAsset={closure.largest_asset_bytes / MEBIBYTE:.2f}MiB "
        f"budget={closure.budget_bytes // MEBIBYTE}MiB "
        f"over={closure.over_budget_bytes / MEBIBYTE:.2f}MiB"
    )


def object_closures(
    *,
    publish_root: Path | None = None,
) -> tuple[list[ObjectClosure], list[str]]:
    """Return the closure of every canonical post and entity object."""
    root = publish_root or PUBLISH_ROOT
    closures: list[ObjectClosure] = []
    issues: list[str] = []
    for kind, depth in (("posts", 4), ("entities", 3)):
        kind_root = root / kind
        if not kind_root.is_dir():
            continue
        for object_root in sorted(kind_root.glob("/".join(["*"] * depth))):
            if not object_root.is_dir():
                continue
            relative = object_root.relative_to(kind_root)
            closure, media_issues = object_closure(
                object_root,
                ref=f"{kind}/{relative.as_posix()}",
                carrier=object_carrier(kind, relative.as_posix()),
            )
            issues.extend(media_issues)
            closures.append(closure)
    return closures, issues


def budget_violations(closures: list[ObjectClosure]) -> list[ObjectClosure]:
    return [row for row in closures if row.over_budget_bytes > 0]


def main() -> int:
    closures, issues = object_closures()
    violations = budget_violations(closures)
    if issues or violations:
        print("[verify_object_size_budget] FAIL")
        for issue in issues:
            print(f"  - closure_unresolved: {issue}")
        for row in violations:
            print(
                f"  - GATE_BLOCK DATA.OBJECT.SIZE_BUDGET_EXCEEDED: "
                f"cause={budget_verdict(row)} {describe_closure(row)}"
            )
        return 1
    largest = max((row.closure_bytes for row in closures), default=0)
    print(
        f"[verify_object_size_budget] OK objects={len(closures)} "
        f"largestClosure={largest / MEBIBYTE:.2f}MiB"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
