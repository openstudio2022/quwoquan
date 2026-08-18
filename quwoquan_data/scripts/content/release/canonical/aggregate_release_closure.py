"""Resolve exact canonical object closures for immutable aggregation."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from content.execution.identity import parse_execution_id
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _execution_id,
    _read_json,
    _safe_rel,
)
from core.control_types import ContentType
from core.release_layout import payload_file
from core.source_digest import SourceDefinitionSnapshot, SourceDigestError

OBJECT_KINDS = ("creators", "entities", "posts", "tags")


@dataclass(frozen=True, slots=True)
class ExecutionPublishClosure:
    execution_id: str
    entity_refs: tuple[str, ...]
    post_refs: tuple[str, ...]
    source_digest: SourceDefinitionSnapshot


def normalized_refs(value: object, *, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ObjectTransactionError(f"{label} must be an array")
    refs = tuple(
        sorted({_safe_rel(str(item), label=label).as_posix() for item in value})
    )
    if len(refs) != len(value):
        raise ObjectTransactionError(f"{label} contains duplicate refs")
    return refs


def object_root(publish_root: Path, kind: str, ref: str) -> Path:
    return publish_root / kind / _safe_rel(ref, label=f"{kind}Ref")


def execution_publish_closure(
    execution_id: str,
    *,
    publish_root: Path,
) -> ExecutionPublishClosure:
    execution_id = _execution_id(execution_id)
    identity = parse_execution_id(execution_id)
    matched_refs: dict[str, list[str]] = {"entities": [], "posts": []}
    matched_digests: list[SourceDefinitionSnapshot] = []
    for kind in ("entities", "posts"):
        objects_root = publish_root / kind
        if not objects_root.is_dir():
            continue
        for manifest_path in sorted(objects_root.rglob("manifest.json")):
            manifest = _read_json(manifest_path)
            if str(manifest.get("executionId") or "") != execution_id:
                continue
            ref = _safe_rel(
                manifest_path.parent.relative_to(objects_root).as_posix(),
                label=f"{kind}Ref",
            ).as_posix()
            try:
                source_digest = SourceDefinitionSnapshot.from_document(
                    manifest.get("sourceDigest")
                )
            except SourceDigestError as exc:
                raise ObjectTransactionError(
                    f"{execution_id}: canonical {kind}/{ref} lacks a valid frozen sourceDigest"
                ) from exc
            matched_refs[kind].append(ref)
            matched_digests.append(source_digest)
    entity_refs = tuple(sorted(matched_refs["entities"]))
    post_refs = tuple(sorted(matched_refs["posts"]))
    if identity.content_type is ContentType.HOMEPAGE and post_refs:
        raise ObjectTransactionError(
            f"{execution_id}: homepage execution has canonical posts"
        )
    if identity.content_type is not ContentType.HOMEPAGE and entity_refs:
        raise ObjectTransactionError(
            f"{execution_id}: post execution has canonical entities"
        )
    if identity.content_type is not ContentType.HOMEPAGE:
        for ref in post_refs:
            manifest = _read_json(
                object_root(publish_root, "posts", ref) / "manifest.json"
            )
            if str(manifest.get("contentType") or "") != identity.content_type.value:
                raise ObjectTransactionError(
                    f"{execution_id}: canonical post contentType does not match execution identity"
                )
    if not entity_refs and not post_refs:
        raise ObjectTransactionError(
            f"{execution_id}: canonical publish has no objects bound to this execution"
        )
    source_digests = {item.digest for item in matched_digests}
    if len(source_digests) != 1:
        raise ObjectTransactionError(
            f"{execution_id}: canonical object source digests drift"
        )
    return ExecutionPublishClosure(
        execution_id,
        entity_refs,
        post_refs,
        matched_digests[0],
    )


def copy_tag_snapshot(source: Path, target: Path) -> None:
    """Copy one exact taxonomy leaf without smuggling descendants."""

    if not source.is_dir():
        raise ObjectTransactionError(f"目录不存在：{source}")
    if not (source / "_definition.json").is_file():
        raise ObjectTransactionError(
            f"canonical tag snapshot missing definition: {source}"
        )
    target.mkdir(parents=True, exist_ok=True)
    for path in source.iterdir():
        if path.is_file():
            shutil.copy2(path, target / path.name)


def resolve_tag_snapshot(
    publish_root: Path,
    *,
    tag_ref: str,
    control_plane_taxonomy_root: Path | None = None,
) -> Path:
    """Resolve one exact Tag leaf, preferring canonical publish truth."""

    relative = _safe_rel(tag_ref, label="tagRef")
    candidates = [publish_root / "tags" / relative]
    if control_plane_taxonomy_root is not None:
        candidates.append(control_plane_taxonomy_root / relative)
    for candidate in candidates:
        if candidate.is_dir() and (candidate / "_definition.json").is_file():
            return candidate
    raise ObjectTransactionError(f"DATA.RELEASE.TAG_SNAPSHOT_MISSING: {tag_ref}")


def copy_release_tag_snapshot(
    publish_root: Path,
    *,
    tag_ref: str,
    target: Path,
    control_plane_taxonomy_root: Path | None = None,
) -> None:
    """Copy one resolved Tag leaf into an immutable release staging root."""

    copy_tag_snapshot(
        resolve_tag_snapshot(
            publish_root,
            tag_ref=tag_ref,
            control_plane_taxonomy_root=control_plane_taxonomy_root,
        ),
        target,
    )


def _object_refs_document(
    publish_root: Path,
    *,
    kind: str,
    ref: str,
    filename: str,
    field: str,
) -> tuple[str, ...]:
    path = object_root(publish_root, kind, ref) / filename
    if not path.is_file():
        raise ObjectTransactionError(f"canonical {kind}/{ref} missing {filename}")
    return normalized_refs(
        _read_json(path).get(field),
        label=f"{kind}/{ref}/{filename}.{field}",
    )


def reference_closure(
    publish_root: Path,
    *,
    entity_refs: set[str],
    post_refs: set[str],
    control_plane_taxonomy_root: Path | None = None,
) -> tuple[list[str], list[str]]:
    creator_refs: set[str] = set()
    tag_refs: set[str] = set()
    for kind, refs in (("entities", entity_refs), ("posts", post_refs)):
        for ref in sorted(refs):
            root = object_root(publish_root, kind, ref)
            if not (root / "manifest.json").is_file():
                raise ObjectTransactionError(f"canonical {kind} object missing: {ref}")
            creator_refs.update(
                _object_refs_document(
                    publish_root,
                    kind=kind,
                    ref=ref,
                    filename="creator.refs.json",
                    field="creatorRefs",
                )
            )
            tag_refs.update(
                _object_refs_document(
                    publish_root,
                    kind=kind,
                    ref=ref,
                    filename="tag.refs.json",
                    field="tagRefs",
                )
            )
    tag_refs.update(
        creator_tag_refs(
            publish_root,
            creator_refs=creator_refs,
            control_plane_taxonomy_root=control_plane_taxonomy_root,
        )
    )
    for ref in sorted(tag_refs):
        resolve_tag_snapshot(
            publish_root,
            tag_ref=ref,
            control_plane_taxonomy_root=control_plane_taxonomy_root,
        )
    return sorted(creator_refs), sorted(tag_refs)


def creator_tag_refs(
    publish_root: Path,
    *,
    creator_refs: set[str] | list[str],
    control_plane_taxonomy_root: Path | None = None,
) -> list[str]:
    """Resolve Tag closure for creators selected independently of Posts."""

    tag_refs: set[str] = set()
    for ref in sorted(creator_refs):
        header = _read_json(object_root(publish_root, "creators", ref) / "_creator.json")
        if str(header.get("creatorId") or "") != ref:
            raise ObjectTransactionError(f"canonical creator identity mismatch: {ref}")
        tag_refs.update(
            normalized_refs(
                header.get("tagRefs"),
                label=f"creators/{ref}/_creator.json.tagRefs",
            )
        )
    for ref in sorted(tag_refs):
        resolve_tag_snapshot(
            publish_root,
            tag_ref=ref,
            control_plane_taxonomy_root=control_plane_taxonomy_root,
        )
    return sorted(tag_refs)


def existing_refs(release_root: Path) -> dict[str, list[str]]:
    desired = _read_json(payload_file(release_root, "desired_state.json"))
    refs = desired.get("desiredRefs")
    if not isinstance(refs, dict):
        raise ObjectTransactionError("existing release desiredRefs must be an object")
    return {
        kind: list(normalized_refs(refs.get(kind), label=kind))
        for kind in OBJECT_KINDS
    }


__all__ = [
    "OBJECT_KINDS",
    "copy_release_tag_snapshot",
    "copy_tag_snapshot",
    "creator_tag_refs",
    "execution_publish_closure",
    "existing_refs",
    "object_root",
    "reference_closure",
    "resolve_tag_snapshot",
]
