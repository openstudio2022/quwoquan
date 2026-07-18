"""Canonical publish package contract, integrity, and closure validation."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from core.paths import CONTROL_PLANE_TAXONOMY_ROOT
from core.control_types import SourcePolicyRevision
from core.schema import assert_valid
from core.tree_integrity import tree_integrity_stats

PACKAGE_SCHEMA = "quwoquan_data.object_transaction_package"

DRY_RUN_SCHEMA = "quwoquan_data.object_transaction_dry_run"

APPLY_SCHEMA = "quwoquan_data.object_transaction_apply"

ROLLBACK_SCHEMA = "quwoquan_data.object_transaction_rollback"

LAYOUT_SCHEMA = "quwoquan_data.canonical_publish"

RELEASE_SCHEMA = "quwoquan_data.release"

REQUIRED_SOURCE_POLICY = SourcePolicyRevision.ENCYCLOPEDIA_PRIMARY.value

ALLOWED_OBJECT_KINDS = {"creators", "entities", "posts"}

ALLOWED_CANONICAL_ROOTS = {"creators", "entities", "posts", "tags", "media"}

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

FORBIDDEN_RELEASE_KEYS = {
    "env",
    "environment",
    "sampleRatio",
    "activatedAt",
    "importRun",
}


def assert_environment_neutral(root: Path) -> None:
    """Reject environment state from an immutable, reusable release payload."""
    for path in _files(root):
        if path.suffix != ".json":
            continue
        stack: list[Any] = [_read_json(path)]
        while stack:
            value = stack.pop()
            if isinstance(value, dict):
                for key, child in value.items():
                    if key in FORBIDDEN_RELEASE_KEYS:
                        raise ObjectTransactionError(
                            f"release 含环境字段：{path.relative_to(root)}:{key}"
                        )
                    stack.append(child)
            elif isinstance(value, list):
                stack.extend(value)

class ObjectTransactionError(RuntimeError):
    """对象发布事务的输入、闭包或原子切换失败。"""

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

def _tree_digest(root: Path) -> str:
    rows = [
        {
            "path": path.relative_to(root).as_posix(),
            "sha256": _digest_file(path),
            "bytes": path.stat().st_size,
        }
        for path in _files(root)
    ]
    return _digest_bytes(_json_bytes(rows))

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
    staging = Path(tempfile.mkdtemp(prefix=".tags.", dir=canonical_root))
    try:
        for ref in refs:
            rel = _safe_rel(ref, label="tagRef")
            source = taxonomy_root / rel / "_definition.json"
            if not source.is_file():
                raise ObjectTransactionError(f"tag closure 不可解析：{ref}")
            definition = _read_json(source)
            try:
                assert_valid(definition, "governance", "_definition", label=f"taxonomy tag {ref}")
            except (ValueError, FileNotFoundError) as exc:
                raise ObjectTransactionError(str(exc)) from exc
            _write_json(staging / rel / "_definition.json", definition)
        target = canonical_root / "tags"
        shutil.rmtree(target, ignore_errors=True)
        staging.replace(target)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return refs

def _collect_object_keys(value: Any) -> set[str]:
    result: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "objectKey" and isinstance(child, str) and child:
                result.add(child)
            result.update(_collect_object_keys(child))
    elif isinstance(value, list):
        for child in value:
            result.update(_collect_object_keys(child))
    return result

def _object_json_keys(root: Path) -> set[str]:
    result: set[str] = set()
    for path in _files(root):
        if path.suffix == ".json":
            result.update(_collect_object_keys(_read_json(path)))
    return result

def _review_binding(object_root: Path, package: Mapping[str, Any]) -> dict[str, Any]:
    review = package.get("review")
    if not isinstance(review, dict):
        raise ObjectTransactionError("对象包缺 review binding")
    attestation_ref = _safe_rel(
        str(review.get("attestationRef") or ""),
        label="review.attestationRef",
    )
    evidence_ref = _safe_rel(
        str(review.get("evidenceIndexRef") or ""),
        label="review.evidenceIndexRef",
    )
    attestation_path = object_root / attestation_ref
    evidence_path = object_root / evidence_ref
    if not attestation_path.is_file() or not evidence_path.is_file():
        raise ObjectTransactionError("对象包缺 compact review attestation/evidence index")
    attestation = _read_json(attestation_path)
    if attestation.get("decision") != "approved":
        raise ObjectTransactionError("对象未 review-approved")
    for key in ("deterministicGate", "independentReviewer", "mediaRefReview"):
        value = attestation.get(key)
        if not isinstance(value, dict) or value.get("status") != "passed":
            raise ObjectTransactionError(f"review 前置未通过：{key}")
    return {
        "attestationRef": attestation_ref.as_posix(),
        "attestationSha256": _digest_file(attestation_path),
        "evidenceIndexRef": evidence_ref.as_posix(),
        "evidenceIndexSha256": _digest_file(evidence_path),
    }

def _rights_binding(
    *,
    package_root: Path,
    object_root: Path,
    rights_ref: Path,
    cas_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    rights_path = object_root / rights_ref
    rights = _read_json(rights_path)
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
    package_path = package_root / "object_transaction_package.json"
    package = _read_json(package_path)
    if package.get("schema") != PACKAGE_SCHEMA:
        raise ObjectTransactionError("object transaction package schema 不匹配")
    try:
        assert_valid(
            package,
            "release",
            "object_transaction_package",
            label="object_transaction_package",
        )
    except (ValueError, FileNotFoundError) as exc:
        raise ObjectTransactionError(str(exc)) from exc
    transaction_id = _safe_id(
        str(package.get("transactionId") or ""),
        label="transactionId",
    )
    execution_id = _execution_id(str(package.get("executionId") or ""))
    source_policy_revision = str(package.get("sourcePolicyRevision") or "")
    target = package.get("target")
    if not isinstance(target, dict) or target.get("layoutSchema") != LAYOUT_SCHEMA:
        raise ObjectTransactionError("target layout schema 不匹配")
    object_kind = str(target.get("objectKind") or "")
    if object_kind not in ALLOWED_OBJECT_KINDS:
        raise ObjectTransactionError(f"objectKind 不支持：{object_kind}")
    expected_source_policy = EXPECTED_SOURCE_POLICIES[object_kind].value
    if source_policy_revision != expected_source_policy:
        raise ObjectTransactionError(
            "sourcePolicyRevision 不匹配："
            f"expected={expected_source_policy} actual={source_policy_revision}"
        )
    target_schema = str(target.get("objectSchema") or "")
    if target_schema != EXPECTED_OBJECT_SCHEMAS[object_kind]:
        raise ObjectTransactionError("target object schema 不匹配")
    object_ref = _safe_rel(
        str(target.get("objectRef") or ""),
        label="objectRef",
    ).as_posix()
    target_root = canonical_root / object_kind / object_ref
    if require_target_absent and target_root.exists():
        raise ObjectTransactionError(f"对象事务只能 create-once，目标已存在：{target_root}")
    object_package_ref = _safe_rel(
        str(target.get("packageObjectRef") or "object"),
        label="packageObjectRef",
    )
    object_root = package_root / object_package_ref
    required_anchor = "_creator.json" if object_kind == "creators" else "manifest.json"
    if not (object_root / required_anchor).is_file():
        raise ObjectTransactionError(f"对象缺 {required_anchor}")
    if object_kind == "entities" and not (object_root / "_entity.json").is_file():
        raise ObjectTransactionError("entity 对象缺 _entity.json")
    review = _review_binding(object_root, package)
    closure = package.get("closure")
    if not isinstance(closure, dict):
        raise ObjectTransactionError("对象包缺 closure")
    creator_refs = [str(item) for item in closure.get("creatorRefs") or []]
    tag_refs = [str(item) for item in closure.get("tagRefs") or []]
    creator_objects: dict[str, dict[str, Any]] = {}
    for raw in closure.get("creatorObjects") or []:
        if not isinstance(raw, Mapping):
            raise ObjectTransactionError("creatorObjects item 必须为 object")
        creator_ref = str(raw.get("creatorRef") or "").strip()
        package_ref = _safe_rel(
            str(raw.get("packageRef") or ""),
            label="creatorObjects.packageRef",
        )
        creator_root = package_root / package_ref
        if not creator_ref or creator_ref in creator_objects:
            raise ObjectTransactionError("creatorObjects creatorRef 为空或重复")
        if not (creator_root / "_creator.json").is_file():
            raise ObjectTransactionError(f"creatorObjects 缺 _creator.json：{creator_ref}")
        tree_digest = _tree_digest(creator_root)
        if tree_digest != str(raw.get("treeDigest") or ""):
            raise ObjectTransactionError(f"creatorObjects treeDigest 不匹配：{creator_ref}")
        creator_objects[creator_ref] = {
            "creatorRef": creator_ref,
            "packageRef": package_ref.as_posix(),
            "treeDigest": tree_digest,
            "objectRoot": creator_root,
        }
    for creator_ref in creator_refs:
        creator = canonical_root / "creators" / _safe_rel(
            creator_ref,
            label="creatorRef",
        )
        packaged = creator_objects.get(creator_ref)
        if (creator / "_creator.json").is_file():
            if packaged and _tree_digest(creator) != packaged["treeDigest"]:
                raise ObjectTransactionError(f"creator canonical 与 projection 漂移：{creator_ref}")
        elif packaged is None:
            raise ObjectTransactionError(f"creator closure 不可解析：{creator_ref}")
    if not set(creator_objects).issubset(creator_refs):
        raise ObjectTransactionError("creatorObjects 不得包含 creatorRefs 之外的对象")
    for tag_ref in tag_refs:
        if not _tag_exists(tag_ref):
            raise ObjectTransactionError(f"tag closure 不可解析：{tag_ref}")
    local_refs: dict[str, Path] = {}
    for key in ("sourceCatalogRef", "rightsRef"):
        local_ref = _safe_rel(str(closure.get(key) or ""), label=key)
        if not (object_root / local_ref).is_file():
            raise ObjectTransactionError(f"对象 closure 缺 {key}: {local_ref}")
        local_refs[key] = local_ref
    cas_rows: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for raw in closure.get("casRefs") or []:
        if not isinstance(raw, dict):
            raise ObjectTransactionError("casRefs item 必须为 object")
        source_ref = _safe_rel(str(raw.get("sourceRef") or ""), label="cas.sourceRef")
        source = package_root / source_ref
        object_key = _safe_rel(
            str(raw.get("objectKey") or ""),
            label="cas.objectKey",
        ).as_posix()
        if not source.is_file() or source.is_symlink():
            raise ObjectTransactionError(f"CAS source 不存在或为 symlink：{source_ref}")
        if not object_key.startswith("media/objects/sha256/"):
            raise ObjectTransactionError(f"CAS objectKey 非 canonical：{object_key}")
        digest = _digest_file(source)
        if digest != str(raw.get("sha256") or ""):
            raise ObjectTransactionError(f"CAS digest mismatch：{object_key}")
        if int(raw.get("bytes") or -1) != source.stat().st_size:
            raise ObjectTransactionError(f"CAS bytes mismatch：{object_key}")
        if Path(object_key).stem != digest.removeprefix("sha256:"):
            raise ObjectTransactionError(f"CAS objectKey 未按内容寻址：{object_key}")
        if object_key in seen_keys:
            raise ObjectTransactionError(f"CAS objectKey 重复：{object_key}")
        seen_keys.add(object_key)
        cas_rows.append(
            {
                "sourceRef": source_ref.as_posix(),
                "objectKey": object_key,
                "sha256": digest,
                "bytes": source.stat().st_size,
            }
        )
    rights = _rights_binding(
        package_root=package_root,
        object_root=object_root,
        rights_ref=local_refs["rightsRef"],
        cas_rows=cas_rows,
    )
    referenced_keys = _object_json_keys(object_root)
    if referenced_keys != seen_keys:
        raise ObjectTransactionError(
            "对象 asset closure 与事务包 CAS 不一致："
            f"object={sorted(referenced_keys)} package={sorted(seen_keys)}"
        )
    closure_digest = _closure_digest(
        object_root=object_root,
        object_kind=object_kind,
        object_ref=object_ref,
        target_schema=target_schema,
        source_policy_revision=source_policy_revision,
        closure=closure,
        cas_rows=cas_rows,
        review=review,
    )
    if closure_digest != str(package.get("objectClosureDigest") or ""):
        raise ObjectTransactionError(
            "object closure digest mismatch："
            f"expected={package.get('objectClosureDigest')} actual={closure_digest}"
        )
    return {
        "package": package,
        "packageSha256": _digest_file(package_path),
        "transactionId": transaction_id,
        "executionId": execution_id,
        "sourcePolicyRevision": source_policy_revision,
        "objectKind": object_kind,
        "objectRef": object_ref,
        "objectSchema": target_schema,
        "objectRoot": object_root,
        "objectClosureDigest": closure_digest,
        "creatorRefs": creator_refs,
        "creatorObjects": list(creator_objects.values()),
        "tagRefs": tag_refs,
        "casRows": cas_rows,
        "review": review,
        "rights": rights,
    }
