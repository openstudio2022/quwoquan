"""Canonical publish-reference projection for execution workspaces."""

from __future__ import annotations

from content.execution.workspace import (
    Iterable,
    Path,
    execution_root,
    validate_execution_id,
    write_json,
)


def _canonical_object_refs(refs: Iterable[str], *, kind: str) -> list[str]:
    singular = {"entities": "entity", "posts": "post"}.get(kind)
    if singular is None:
        raise ValueError(f"unsupported canonical object kind: {kind}")
    prefix = f"/{singular}/"
    normalized: set[str] = set()
    for raw in refs:
        ref = str(raw or "").strip().strip("/")
        if raw and str(raw).startswith(prefix):
            ref = str(raw)[len(prefix) :].strip("/")
        candidate = Path(ref)
        if not ref or candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError(f"unsafe canonical {kind} ref: {raw}")
        normalized.add(ref)
    return sorted(normalized)


def write_publish_ref(
    execution_id: str,
    *,
    entity_refs: Iterable[str] = (),
    post_refs: Iterable[str] = (),
) -> Path:
    """Record this execution's canonical object closure, never a release alias."""
    target = execution_root(execution_id) / "publish_ref.json"
    payload = {
        "schema": "quwoquan_data.execution_publish_ref",
        "executionId": validate_execution_id(execution_id),
        "canonicalPublishRoot": "quwoquan_data/publish",
        "publishedRefs": {
            "entities": _canonical_object_refs(entity_refs, kind="entities"),
            "posts": _canonical_object_refs(post_refs, kind="posts"),
        },
    }
    from core.schema import assert_valid

    assert_valid(
        payload, "execution", "publish_ref", label=f"publish_ref:{execution_id}"
    )
    write_json(target, payload)
    return target
