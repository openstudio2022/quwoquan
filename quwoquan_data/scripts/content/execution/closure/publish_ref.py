"""Canonical publish-ref document construction and validation."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from core.io import write_json
from core.paths import CANONICAL_PUBLISH_ROOT_REF
from core.schema import assert_valid

from content.execution.closure.publish_outcome import normalize_publish_discards
from content.execution.identity import validate_execution_id


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


def write_publish_ref_document(
    target: Path,
    execution_id: str,
    *,
    entity_refs: Iterable[str] = (),
    post_refs: Iterable[str] = (),
    publish_discards: Iterable[Mapping[str, Any]] = (),
) -> Path:
    payload = {
        "schema": "quwoquan_data.execution_publish_ref",
        "executionId": validate_execution_id(execution_id),
        "canonicalPublishRoot": CANONICAL_PUBLISH_ROOT_REF,
        "publishedRefs": {
            "entities": _canonical_object_refs(entity_refs, kind="entities"),
            "posts": _canonical_object_refs(post_refs, kind="posts"),
        },
        "publishDiscards": normalize_publish_discards(publish_discards),
    }
    assert_valid(payload, "execution", "publish_ref", label=f"publish_ref:{execution_id}")
    write_json(target, payload)
    return target


__all__ = ["write_publish_ref_document"]
