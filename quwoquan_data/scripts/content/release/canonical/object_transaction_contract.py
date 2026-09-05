"""Canonical publish package contract, integrity, and closure validation."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

OBJECT_ASSET_OVER_BUDGET = "DATA.PUBLISH.OBJECT_ASSET_OVER_BUDGET"
OBJECT_CLOSURE_OVER_BUDGET = "DATA.PUBLISH.OBJECT_CLOSURE_OVER_BUDGET"


class TypedPublishExclusion:
    """Typed mechanical publish exclusion without execution orchestration."""

    def __init__(self, issue_code: str, message: str) -> None:
        self.issue_code = issue_code
        super().__init__(message)
from content.release.canonical.object_transaction_bindings import (
    collect_object_keys,
    verify_entity_manifest_asset_binding,
)
from content.release.canonical.object_transaction_environment import (
    iter_forbidden_release_keys,
)
from core.control_types import SourcePolicyRevision
from core.paths import CONTROL_PLANE_TAXONOMY_ROOT
from core.schema import assert_valid

_collect_object_keys = collect_object_keys

PACKAGE_SCHEMA = "quwoquan_data.object_transaction_package"
DRY_RUN_SCHEMA = "quwoquan_data.object_transaction_dry_run"
APPLY_SCHEMA = "quwoquan_data.object_transaction_apply"
ROLLBACK_SCHEMA = "quwoquan_data.object_transaction_rollback"
LAYOUT_SCHEMA = "quwoquan_data.canonical_publish"
RELEASE_SCHEMA = "quwoquan_data.release"
REQUIRED_SOURCE_POLICY = SourcePolicyRevision.ENCYCLOPEDIA_PRIMARY.value
EXECUTION_CONTENT_REVIEW_REF = "5.review/content_review.json"
CANONICAL_CONTENT_REVIEW_REF = "content_review.json"
CANONICAL_TRANSACTION_LAYOUT_REVISION = "content-review-v1"
ALLOWED_OBJECT_KINDS = {"creators", "entities", "posts"}
# Canonical publish holds the documents that describe a work, never the bytes it
# shows: media bodies are owned once by the content library and reached by the
# digests those documents record.
#
# Roots alone cannot express that. A body nested at `posts/<ref>/assets/x.jpg`
# has a canonical root and would pass a root-only check, so the rule that keeps
# the versioned tree free of bodies is stated over the whole path: a canonical
# destination is a document, wherever it sits.
ALLOWED_CANONICAL_ROOTS = {"creators", "entities", "posts", "tags"}
CANONICAL_DOCUMENT_SUFFIXES = frozenset({".json", ".md", ".ndjson", ".vtt"})
EXPECTED_OBJECT_SCHEMAS = {
    "creators": "quwoquan_data.creator_object",
    "entities": "quwoquan_data.entity_object",
    "posts": "quwoquan_data.post_object",
}

EXPECTED_SOURCE_POLICIES = {
    "creators": SourcePolicyRevision.GOVERNANCE_PROJECTION,
    "entities": SourcePolicyRevision.ENCYCLOPEDIA_PRIMARY,
    "posts": SourcePolicyRevision.RIGHTS_CLEARED_CONTENT,
}

def assert_environment_neutral(root: Path) -> None:
    """Reject mutable activation state from an immutable release payload.

    ``targetEnvironment`` is an immutable build policy and is intentionally
    allowed; mutable environment state still belongs only to stackctl runs.
    """
    for path in _files(root):
        if path.suffix != ".json":
            continue
        for key in iter_forbidden_release_keys(_read_json(path)):
            raise ObjectTransactionError(
                f"release 含环境字段：{path.relative_to(root)}:{key}"
            )

class ObjectTransactionError(RuntimeError):
    """对象发布事务的输入、闭包或原子切换失败。"""


class ObjectStorageBudgetExceeded(ObjectTransactionError, TypedPublishExclusion):
    """对象闭包超出单对象存储预算，整对象 blocked。

    发布侧不裁剪资产、不丢弃正文已引用的图、不生成降级衍生体：前两者会在正文里
    留下悬挂引用，后者需要尚未冻结的重编码参数。对象因此整体不出包。
    """

    def __init__(self, issue_code: str, message: str) -> None:
        TypedPublishExclusion.__init__(self, issue_code, message)

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")

def _digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()

def _digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()

def _execution_id(value: str) -> str:
    from content.execution.identity import validate_execution_id

    try:
        return validate_execution_id(value)
    except ValueError as exc:
        raise ObjectTransactionError(f"executionId 非法：{value!r}") from exc

def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ObjectTransactionError(f"JSON 不可读：{path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ObjectTransactionError(f"JSON 顶层必须为 object：{path}")
    return value

def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_bytes(_json_bytes(dict(value)))
    os.replace(tmp, path)

def _safe_id(value: str, *, label: str) -> str:
    text = str(value or "").strip()
    if not text or "/" in text or "\\" in text or text in {".", ".."}:
        raise ObjectTransactionError(f"{label} 非法：{value!r}")
    return text


def canonical_transaction_id(
    *, execution_id: str, object_kind: str, object_ref: str
) -> str:
    """Bind create-once transaction identity to the hard-cut package layout."""

    normalized_execution = _execution_id(execution_id)
    marker = {"entities": "entity", "posts": "post"}.get(object_kind)
    if marker is None:
        raise ObjectTransactionError(f"transaction objectKind 不支持：{object_kind}")
    normalized_ref = _safe_rel(object_ref, label="objectRef").as_posix()
    ref_digest = hashlib.sha256(normalized_ref.encode("utf-8")).hexdigest()[:12]
    return (
        f"{normalized_execution}--{marker}-{ref_digest}--"
        f"{CANONICAL_TRANSACTION_LAYOUT_REVISION}"
    )


def _safe_rel(value: str, *, label: str) -> Path:
    text = str(value or "").strip().strip("/")
    candidate = Path(text)
    if (
        not text
        or candidate.is_absolute()
        or ".." in candidate.parts
        or any(part in {"", "."} for part in candidate.parts)
    ):
        raise ObjectTransactionError(f"{label} 路径逃逸：{value!r}")
    return candidate


def is_canonical_document(relative: Path) -> bool:
    """Whether one relative path names a document canonical publish may hold."""

    return relative.suffix.casefold() in CANONICAL_DOCUMENT_SUFFIXES


def object_lineage(manifest_path: str) -> str:
    """The object a canonical manifest path belongs to, version stripped.

    Canonical objects are versioned in place (``posts/<carrier>/<topic>/<title>/2``)
    and a successor coexists with the version it supersedes, so identity questions
    asked per manifest path would read one object's own next version as a second
    object holding the same content.
    """

    parts = [part for part in manifest_path.split("/") if part]
    if len(parts) >= 3 and parts[-1] == "manifest.json" and parts[-2].isdigit():
        return "/".join(parts[:-2])
    return "/".join(parts[:-1]) if parts[-1:] == ["manifest.json"] else manifest_path


def canonical_destination(value: str, *, label: str) -> Path:
    """Return the canonical publish path ``value`` names, or refuse it.

    Every write into the versioned tree passes here, so this is the one place
    that decides what canonical publish may contain: a document under a known
    root. A media body reaching this point means some producer tried to make the
    tree the owner of bytes the content library already owns, and failing here is
    what keeps that from becoming permanent Git history.
    """

    relative = _safe_rel(value, label=label)
    if relative.parts[0] not in ALLOWED_CANONICAL_ROOTS:
        raise ObjectTransactionError(f"{label} is outside canonical roots: {value}")
    if not is_canonical_document(relative):
        raise ObjectTransactionError(
            f"{label} is a media body, which canonical publish never owns: {value}"
        )
    return relative


def _files(root: Path) -> Iterable[Path]:
    if not root.is_dir():
        return ()
    paths = sorted(root.rglob("*"))
    if any(path.is_symlink() for path in paths):
        raise ObjectTransactionError(f"对象事务禁止 symlink：{root}")
    return (path for path in paths if path.is_file())

def _copy_tree(source: Path, target: Path) -> None:
    if not source.is_dir():
        raise ObjectTransactionError(f"目录不存在：{source}")
    target.mkdir(parents=True, exist_ok=True)
    for path in _files(source):
        destination = target / path.relative_to(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)

def _tree_rows(root: Path) -> list[dict[str, Any]]:
    return [
        {
            "path": path.relative_to(root).as_posix(),
            "sha256": _digest_file(path),
            "bytes": path.stat().st_size,
        }
        for path in _files(root)
    ]


def _tree_digest(root: Path) -> str:
    return _digest_bytes(_json_bytes(_tree_rows(root)))


def _document_tree_digest(root: Path) -> str:
    """Digest only the files canonical publish can hold.

    A transaction package carries both the documents describing an object and the
    bodies those documents point at, and applying it puts the bodies in the
    content library rather than the tree. The two trees are therefore only ever
    equal on their document projection, so a readback that compares whole trees
    would read a correct apply as drift.
    """

    return _digest_bytes(
        _json_bytes(
            [
                row
                for row in _tree_rows(root)
                if is_canonical_document(Path(str(row["path"])))
            ]
        )
    )

def _tag_exists(ref: str) -> bool:
    root = Path(os.environ.get("QWQ_TAGS_ROOT") or CONTROL_PLANE_TAXONOMY_ROOT)
    tag = root / _safe_rel(ref, label="tagRef")
    return (tag / "_definition.json").is_file()


def _collect_tag_refs(value: Any) -> set[str]:
    refs: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "tagRefs" and isinstance(child, list):
                refs.update(item.strip() for item in child if isinstance(item, str) and item.strip())
            refs.update(_collect_tag_refs(child))
    elif isinstance(value, list):
        for child in value:
            refs.update(_collect_tag_refs(child))
    return refs


def collect_canonical_tag_refs(canonical_root: Path) -> list[str]:
    """Return exactly the tag references consumed by canonical objects."""
    refs: set[str] = set()
    for kind in sorted(ALLOWED_OBJECT_KINDS):
        for path in _files(canonical_root / kind):
            if path.suffix == ".json":
                refs.update(_collect_tag_refs(_read_json(path)))
    return sorted(refs)


def refresh_canonical_tag_snapshots(canonical_root: Path) -> list[str]:
    """Materialize only consumer-referenced taxonomy leaves into canonical publish.

    The control-plane taxonomy remains the editable source. Canonical publish holds
    a compact consumer snapshot so every consumer reference closes without copying
    the whole taxonomy tree or retaining stale branches.
    """
    refs = collect_canonical_tag_refs(canonical_root)
    taxonomy_root = Path(os.environ.get("QWQ_TAGS_ROOT") or CONTROL_PLANE_TAXONOMY_ROOT)
    target = canonical_root / "tags"
    target.mkdir(parents=True, exist_ok=True)
    expected: set[Path] = set()
    for ref in refs:
        rel = _safe_rel(ref, label="tagRef")
        source = taxonomy_root / rel / "_definition.json"
        if not source.is_file():
            raise ObjectTransactionError(f"tag closure 不可解析：{ref}")
        definition = _read_json(source)
        try:
            assert_valid(
                definition,
                "governance",
                "_definition",
                label=f"taxonomy tag {ref}",
            )
        except (ValueError, FileNotFoundError) as exc:
            raise ObjectTransactionError(str(exc)) from exc
        destination = target / rel / "_definition.json"
        expected.add(destination)
        if destination.is_file() and _digest_file(destination) == _digest_file(source):
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(
            f".{destination.name}.{os.getpid()}.tag-snapshot.tmp"
        )
        shutil.copy2(source, temporary)
        try:
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
    for snapshot in list(_files(target)):
        if snapshot in expected:
            continue
        snapshot.unlink()
        current = snapshot.parent
        while current != target:
            try:
                current.rmdir()
            except OSError:
                break
            current = current.parent
    return refs

def _object_json_keys(root: Path) -> set[str]:
    result: set[str] = set()
    for path in _files(root):
        if path.suffix == ".json":
            result.update(collect_object_keys(_read_json(path)))
    return result

def _review_binding(object_root: Path, package: Mapping[str, Any]) -> dict[str, Any]:
    review = package.get("review")
    if not isinstance(review, dict):
        raise ObjectTransactionError("对象包缺 review binding")
    content_review_ref = _safe_rel(
        str(review.get("contentReviewRef") or ""),
        label="review.contentReviewRef",
    )
    content_review_path = object_root / content_review_ref
    if (
        content_review_ref.as_posix() != CANONICAL_CONTENT_REVIEW_REF
        or content_review_path.is_symlink()
        or not content_review_path.is_file()
    ):
        raise ObjectTransactionError("对象包 content review exact binding drift")
    content_review = _read_json(content_review_path)
    try:
        assert_valid(
            content_review,
            "content",
            "content_review",
            label=content_review_path.as_posix(),
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise ObjectTransactionError(str(exc)) from exc
    if content_review.get("decision") != "approved":
        raise ObjectTransactionError("对象未 review-approved")
    digest = _digest_file(content_review_path)
    return {
        "contentReviewRef": content_review_ref.as_posix(),
        "contentReviewSha256": digest,
        "rightsAuthorityRef": content_review_ref.as_posix(),
        "rightsAuthoritySha256": digest,
    }

def _rights_binding(
    *,
    package_root: Path,
    object_root: Path,
    rights_ref: Path,
    cas_rows: list[dict[str, Any]],
    publish_media_mode: str,
) -> dict[str, Any]:
    rights_path = object_root / rights_ref
    rights = _read_json(rights_path)
    if rights.get("publishMediaMode") != publish_media_mode:
        raise ObjectTransactionError(
            "asset rights closure publishMediaMode 与 transaction package 漂移"
        )
    try:
        assert_valid(
            rights,
            "release",
            "asset_rights_closure",
            label="object_transaction_asset_rights_closure",
        )
    except (ValueError, FileNotFoundError) as exc:
        raise ObjectTransactionError(str(exc)) from exc
    bindings: list[dict[str, Any]] = []
    bound_sources: set[str] = set()
    for index, item in enumerate(rights["assets"]):
        snapshot = item["snapshot"]
        snapshot_ref = _safe_rel(
            str(snapshot["ref"]),
            label=f"rights.assets[{index}].snapshot.ref",
        )
        snapshot_path = package_root / snapshot_ref
        if not snapshot_path.is_file() or snapshot_path.is_symlink():
            raise ObjectTransactionError(f"图片授权快照不存在或为 symlink：{snapshot_ref}")
        if (
            _digest_file(snapshot_path) != str(snapshot["sha256"])
            or snapshot_path.stat().st_size != int(snapshot["bytes"])
        ):
            raise ObjectTransactionError("图片授权快照 hash/bytes 不匹配")
        asset = item["asset"]
        asset_ref = _safe_rel(
            str(asset["ref"]),
            label=f"rights.assets[{index}].asset.ref",
        )
        matches = [
            row
            for row in cas_rows
            if row["sourceRef"] == asset_ref.as_posix()
            and row["sha256"] == str(asset["sha256"])
            and row["bytes"] == int(asset["bytes"])
        ]
        if len(matches) != 1 or asset_ref.as_posix() in bound_sources:
            raise ObjectTransactionError("图片权利证据未与唯一事务 CAS asset 绑定")
        bound_sources.add(asset_ref.as_posix())
        bindings.append(
            {
                "assetId": str(item["assetId"]),
                "snapshotRef": snapshot_ref.as_posix(),
                "snapshotSha256": str(snapshot["sha256"]),
                "assetRef": asset_ref.as_posix(),
                "assetSha256": str(asset["sha256"]),
                "assetBytes": int(asset["bytes"]),
                "author": str(item["author"]),
                "licenseName": str(item["licenseName"]),
                "licenseUrl": str(item["licenseUrl"]),
                "canonicalFilePage": str(item["canonicalFilePage"]),
                "attribution": str(item["attribution"]),
                "fetchedAt": str(item["fetchedAt"]),
            }
        )
    if bound_sources != {row["sourceRef"] for row in cas_rows}:
        raise ObjectTransactionError("图片权利证据未覆盖全部事务 CAS assets")
    return {
        "rightsRef": rights_ref.as_posix(),
        "rightsSha256": _digest_file(rights_path),
        "assets": bindings,
    }


def _admit_object_storage_budget(object_root: Path, *, object_kind: str, object_ref: str) -> None:
    """Refuse to seal a closure that does not fit the single-object storage budget.

    This is the one boundary both carriers must cross to obtain an
    ``objectClosureDigest``, so binding admission here is what makes "a new
    carrier forgot to call it" structurally impossible rather than a convention.
    The measurement and the per-carrier budget numbers stay owned by the gate
    that also scans canonical publish, so admission and that gate cannot reach
    different conclusions about the same object.
    """

    from verify.verify_object_size_budget import (
        ObjectBudgetVerdict,
        budget_verdict,
        describe_closure,
        object_carrier,
        object_closure,
    )

    closure, issues = object_closure(
        object_root,
        ref=f"{object_kind}/{object_ref}",
        carrier=object_carrier(object_kind, object_ref),
    )
    if issues:
        raise ObjectTransactionError(
            "object closure could not be measured: " + "; ".join(sorted(issues))
        )
    verdict = budget_verdict(closure)
    if verdict is ObjectBudgetVerdict.WITHIN_BUDGET:
        return
    code = (
        OBJECT_ASSET_OVER_BUDGET
        if verdict is ObjectBudgetVerdict.SINGLE_ASSET_OVER_BUDGET
        else OBJECT_CLOSURE_OVER_BUDGET
    )
    raise ObjectStorageBudgetExceeded(
        code,
        f"{code}: object exceeds its storage budget: {describe_closure(closure)}",
    )


def _closure_digest(
    *,
    object_root: Path,
    object_kind: str,
    object_ref: str,
    target_schema: str,
    source_policy_revision: str,
    closure: Mapping[str, Any],
    cas_rows: list[dict[str, Any]],
    review: Mapping[str, Any],
) -> str:
    """Digest everything an object's identity may not silently change."""

    _admit_object_storage_budget(
        object_root,
        object_kind=object_kind,
        object_ref=object_ref,
    )
    return _digest_bytes(
        _json_bytes(
            {
                "object": {
                    "kind": object_kind,
                    "ref": object_ref,
                    "schema": target_schema,
                    "treeDigest": _tree_digest(object_root),
                },
                "sourcePolicyRevision": source_policy_revision,
                "closure": {
                    "creatorRefs": sorted(
                        str(item) for item in closure.get("creatorRefs") or []
                    ),
                    "tagRefs": sorted(
                        str(item) for item in closure.get("tagRefs") or []
                    ),
                    "sourceCatalogRef": str(
                        closure.get("sourceCatalogRef") or ""
                    ),
                    "rightsRef": str(closure.get("rightsRef") or ""),
                    "creatorObjects": sorted(
                        (
                            {
                                "creatorRef": str(item.get("creatorRef") or ""),
                                "packageRef": str(item.get("packageRef") or ""),
                                "treeDigest": str(item.get("treeDigest") or ""),
                            }
                            for item in closure.get("creatorObjects") or []
                            if isinstance(item, Mapping)
                        ),
                        key=lambda item: item["creatorRef"],
                    ),
                },
                "cas": sorted(cas_rows, key=lambda row: row["objectKey"]),
                "review": dict(review),
            }
        )
    )

def _verify_package(
    package_root: Path,
    *,
    canonical_root: Path,
    require_target_absent: bool,
) -> dict[str, Any]:
    from content.release.canonical.object_transaction_package_verification import (
        verify_package,
    )

    return verify_package(
        package_root,
        canonical_root=canonical_root,
        require_target_absent=require_target_absent,
    )
