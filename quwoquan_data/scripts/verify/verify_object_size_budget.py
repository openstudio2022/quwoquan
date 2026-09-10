#!/usr/bin/env python3
"""Verify every canonical content object stays inside its storage budget.

The budget is measured on the object's logical byte closure: the object's own
documents plus each distinct media entry it references, counted once. Physical
duplicates of the same content inside one object are a separate reference-
semantics defect and must not be able to buy an object extra budget here.

This module owns the measurement, not the numbers. The per-carrier budget table
is declared once in ``control_plane/_shared/media_processing.policy.yaml`` and
the ``1.download`` cross-section refuses over-budget candidates against that same
table, so a candidate that passes download can no longer be rejected here for a
single-asset budget it was never measured against.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


sys.dont_write_bytecode = True

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_ROOT))

from core.object_storage_budget import object_storage_budget_bytes
from core.paths import PUBLISH_ROOT
from core.publish_layout import _coordinates, entity_namespace, logical_object_ref, post_namespace
from core.publish_repository import canonical_files

MEBIBYTE = 1024 * 1024

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
    """一个对象是一份消费者价值，其成本按载体封顶。

    数值不在本文件：逐载体预算表的唯一声明位是
    `control_plane/_shared/media_processing.policy.yaml`，下载截面读的是同一张表。
    在这里另立常量会让下载放行的上限与本门禁判否的上限各自漂移。
    """

    return object_storage_budget_bytes(carrier)


def object_carrier(object_kind: str, object_ref: str) -> str:
    """Name the carrier that owns the budget for one object reference."""
    if object_kind == "entities":
        return "entity"
    head = str(object_ref or "").strip("/").split("/")[0]
    return head


def _asset_refs_path(object_root: Path) -> Path:
    """预算枚举仅含 post/entity；直接度量 creator 时仍只读 profile。"""
    name = "profile.json" if (object_root / "profile.json").exists() and not (object_root / "manifest.json").exists() else "manifest.json"
    return object_root / name


def _referenced_media_bytes(object_root: Path) -> tuple[int, int, list[str]]:
    """度量随体媒体的去重字节；缺失或损坏是未解析闭包，不是免费媒体。

    最大单体与总量分别保留，以区分单素材过大和对象素材总量超限。
    验证只读实际包，不要求内容库在场或触发任何恢复。
    """
    refs_path = _asset_refs_path(object_root)
    if refs_path.is_symlink() or not refs_path.is_file():
        return 0, 0, [f"asset contract is missing or unsafe: {refs_path}"]
    try:
        document = json.loads(refs_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return 0, 0, [f"asset contract is unreadable: {refs_path}"]
    if not isinstance(document, dict):
        return 0, 0, [f"asset contract must be an object: {refs_path}"]
    rows = document.get("assets")
    if not isinstance(rows, list):
        return 0, 0, [f"asset contract assets must be an array: {refs_path}"]
    issues: list[str] = []
    distinct: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, dict):
            issues.append(f"asset refs row is not an object: {refs_path}")
            continue
        object_key = str(row.get("objectKey") or "")
        sha256 = str(row.get("sha256") or "")
        if not sha256:
            issues.append(f"asset refs row has no content-addressed identity: {object_key}")
            continue
        from content.release.canonical.object_transaction_contract import _safe_rel, _digest_file
        try:
            relative = _safe_rel(str(row.get("path") or ""), label="asset.path")
            entry = object_root / relative
            if relative.parts[0] != "media" or entry.is_symlink() or not entry.is_file() or _digest_file(entry) != sha256 or entry.stat().st_size != row.get("bytes"):
                raise ValueError("carried bytes mismatch")
        except (OSError, ValueError, RuntimeError):
            issues.append(f"referenced carried media entry is missing or corrupt: {object_key}")
            continue
        distinct[sha256] = entry.stat().st_size
    return sum(distinct.values()), max(distinct.values(), default=0), issues


def _document_bytes(object_root: Path) -> int:
    total = 0
    for path in object_root.rglob("*"):
        # media/ 的随体字节仅按 manifest 摘要去重计量，不能再次算入文档。
        if path.is_file() and path.relative_to(object_root).parts[0] != "media":
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
    try:
        files = canonical_files(root)
    except (OSError, ValueError) as exc:
        return [], [f"DATA.PUBLISH.REPOSITORY_INVALID: {exc}"]
    object_files = [path for path in files if path.relative_to(root).parts[0] in {"posts", "entities"}]
    manifests = [path for path in object_files if path.name == "manifest.json"
                 and not {"sources", "records", "media"} & set(path.relative_to(root).parts[1:-1])]
    for manifest_path in manifests:
        object_root = manifest_path.parent
        relative = object_root.relative_to(root)
        kind = relative.parts[0]
        try:
            document = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(document, dict) or type(document.get("version")) is not int or document["version"] < 1:
                raise ValueError("DATA.LAYOUT.IDENTITY_REQUIRED: positive version")
            logical = logical_object_ref(document, kind)
            namespace = entity_namespace(document) if kind == "entities" else post_namespace(document)
            if _coordinates(relative.as_posix(), namespace) is None:
                raise ValueError("DATA.LAYOUT.COORDINATES_INVALID")
            closure, media_issues = object_closure(
                object_root, ref=f"{kind}/{logical}", carrier=object_carrier(kind, logical),
            )
        except (OSError, ValueError) as exc:
            issues.append(f"DATA.OBJECT.MANIFEST_INVALID: {manifest_path}: {exc}")
            continue
        issues.extend(media_issues)
        closures.append(closure)
    # 只扫 manifest 会把丢失清单的已有包当成空池；随体文件必须有唯一清单祖先。
    manifest_roots = {path.parent for path in manifests}
    missing = {path.parent for path in object_files if not manifest_roots.intersection(path.parents)}
    issues.extend(f"DATA.OBJECT.MANIFEST_MISSING: {path}" for path in sorted(missing))
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
