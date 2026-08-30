"""Digest and path-safety primitives for pool delivery intents."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.io import read_json
from core.paths import PUBLISH_ROOT
from core.schema import assert_valid
from core.source_attribution import canonical_source_attribution
from core.tree_integrity import tree_integrity_stats
from governance.creators.assignment import (
    CREATOR_ASSIGNMENT_FIELDS,
    creator_assignment_issues,
    creator_from_payload,
    resolve_registry_creator_assignment,
)

from content.execution.closure.pool_delivery_identity import (
    load_post_identity_reservation as _load_reservation,
)
from content.execution.closure.pool_delivery_identity import (
    load_reserved_post_identity,
)
from content.execution.closure.pool_delivery_identity import (
    reserve_post_identity as _reserve_post_identity,
)
from content.execution.identity import validate_execution_id
from content.execution.queue.model import QueueJob
from content.execution.workspace import execution_root
from content.release.canonical.object_transaction_lock import (
    canonical_publish_serialized,
)
from content.release.canonical.pool_source_attribution import (
    source_attribution_complete,
)

POOL_DELIVERY_INTENT_DIR = "_shared/pool_delivery_intents"
_SCHEMA = "quwoquan_data.pool_delivery_intent"
_CARRIERS = frozenset({"homepage", "article", "image", "video"})
_CREATOR_BINDING_FIELDS = (*CREATOR_ASSIGNMENT_FIELDS, "creatorProfileVersion")


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _safe_object_dir(root: Path, value: object) -> tuple[str, Path]:
    relative = str(value or "").strip().strip("/")
    candidate = root / relative
    path = candidate.resolve()
    try:
        normalized = path.relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError("pool delivery contentObjectDir escapes execution root") from exc
    relative_parts = Path(relative).parts
    has_symlink = any(
        (root / Path(*relative_parts[:index])).is_symlink()
        for index in range(1, len(relative_parts) + 1)
    )
    if has_symlink:
        raise ValueError("pool delivery contentObjectDir cannot traverse symlinks")
    if not normalized or not path.is_dir():
        raise ValueError("pool delivery contentObjectDir is not a physical object directory")
    return normalized, path
