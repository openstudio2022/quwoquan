"""Deterministic semantic mention records for content-side entity/tag grounding."""
from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable, Mapping, Sequence
import hashlib
import json
import unicodedata
from typing import Any, TypeVar

STATUS_PUBLISHED = "published"
STATUS_PENDING_REVIEW = "pending_review"
STATUS_REJECTED = "rejected"
STATUS_OFFLINE = "offline"
MENTION_STATUSES = frozenset(
    {
        STATUS_PUBLISHED,
        STATUS_PENDING_REVIEW,
        STATUS_REJECTED,
        STATUS_OFFLINE,
    }
)

DEFAULT_MAX_DEPTH = 2
DEFAULT_MAX_CANDIDATES = 200

T = TypeVar("T")


def utf16_offset(text: str, codepoint_offset: int) -> int:
    """Convert a Python code-point offset to a UTF-16 code-unit offset."""
    if codepoint_offset < 0 or codepoint_offset > len(text):
        raise ValueError(f"codepoint offset out of range: {codepoint_offset}")
    return len(text[:codepoint_offset].encode("utf-16-le")) // 2


def _normalized_surface(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip()


def stable_mention_id(
    source_ref: str,
    target_ref: str,
    surface: str,
    occurrence: int,
) -> str:
    """Build an ID stable across reruns, status changes, and offset-only shifts."""
    if occurrence < 0:
        raise ValueError("occurrence must be non-negative")
    identity = "\x1f".join(
        (
            str(source_ref).strip(),
            str(target_ref or "").strip(),
            _normalized_surface(surface),
            str(occurrence),
        )
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    return f"mention_{digest}"


def _infer_kind(target_ref: str, explicit: str = "") -> str:
    kind = str(explicit or "").strip().lower()
    if kind in {"entity", "tag"}:
        return kind
    ref = str(target_ref or "").strip()
    if ref.startswith(("Topic/", "Format/", "Geo/", "tag:", "/tag/", "tag/")):
        return "tag"
    return "entity"


def semantic_mentions_for_target(
    text: str,
    *,
    source_ref: str,
    target_ref: str | None,
    surface: str,
    status: str,
    candidate_id: str | None = None,
    kind: str = "",
    location: str = "body",
) -> list[dict[str, Any]]:
    """Return every exact occurrence using UTF-16 half-open offsets."""
    if status not in MENTION_STATUSES:
        raise ValueError(f"unsupported semantic mention status: {status!r}")
    if not source_ref:
        raise ValueError("source_ref is required")
    resolved_kind = _infer_kind(str(target_ref or ""), kind)
    if not surface:
        return []

    mentions: list[dict[str, Any]] = []
    cursor = 0
    occurrence = 0
    while True:
        start = text.find(surface, cursor)
        if start < 0:
            break
        end = start + len(surface)
        start_utf16 = utf16_offset(text, start)
        end_utf16 = utf16_offset(text, end)
        row: dict[str, Any] = {
            "mentionId": stable_mention_id(str(source_ref), str(target_ref or ""), surface, occurrence),
            "sourceRef": source_ref,
            "targetRef": target_ref,
            "kind": resolved_kind,
            "surface": surface,
            "location": location,
            "occurrence": occurrence,
            "rangeStart": start_utf16,
            "rangeEnd": end_utf16,
            "startUtf16": start_utf16,
            "endUtf16": end_utf16,
            "status": status,
        }
        if candidate_id:
            row["candidateId"] = candidate_id
        mentions.append(row)
        occurrence += 1
        cursor = end
    return mentions


def build_semantic_mentions(
    text: str,
    *,
    source_ref: str,
    targets: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Build deterministic mentions for ordered, de-duplicated targets."""
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for target in targets:
        target_ref = str(target.get("targetRef") or "").strip()
        surface = str(target.get("surface") or "").strip()
        candidate_id = str(target.get("candidateId") or "").strip()
        key = (target_ref or candidate_id, surface)
        if (not target_ref and not candidate_id) or not surface or key in seen:
            continue
        seen.add(key)
        rows.extend(
            semantic_mentions_for_target(
                text,
                source_ref=source_ref,
                target_ref=target_ref,
                surface=surface,
                status=str(target.get("status") or STATUS_PENDING_REVIEW),
                candidate_id=candidate_id or None,
                kind=str(target.get("kind") or ""),
                location=str(target.get("location") or "body"),
            )
        )
    return rows


def _default_walk_identity(item: Any) -> str:
    if isinstance(item, Mapping):
        for key in ("candidateId", "naturalKey", "targetRef", "ref", "id"):
            value = str(item.get(key) or "").strip()
            if value:
                return f"{key}:{value}"
    encoded = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def bounded_candidate_walk(
    seeds: Iterable[T],
    expand: Callable[[T], Iterable[T]],
    *,
    identity: Callable[[T], str] | None = None,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
) -> list[tuple[T, int]]:
    """Breadth-first walk with depth=2, cap=200, and cycle-safe visited defaults."""
    if max_depth < 0:
        raise ValueError("max_depth must be non-negative")
    if max_candidates < 1 or max_candidates > DEFAULT_MAX_CANDIDATES:
        raise ValueError(f"max_candidates must be between 1 and {DEFAULT_MAX_CANDIDATES}")

    identity_fn = identity or _default_walk_identity
    queue: deque[tuple[T, int]] = deque((seed, 0) for seed in seeds)
    visited: set[str] = set()
    output: list[tuple[T, int]] = []

    while queue and len(output) < max_candidates:
        item, depth = queue.popleft()
        key = identity_fn(item)
        if key in visited:
            continue
        visited.add(key)
        output.append((item, depth))
        if depth >= max_depth:
            continue
        for child in expand(item):
            child_key = identity_fn(child)
            if child_key not in visited:
                queue.append((child, depth + 1))
    return output


__all__ = [
    "STATUS_PUBLISHED",
    "STATUS_PENDING_REVIEW",
    "STATUS_REJECTED",
    "STATUS_OFFLINE",
    "MENTION_STATUSES",
    "DEFAULT_MAX_DEPTH",
    "DEFAULT_MAX_CANDIDATES",
    "utf16_offset",
    "stable_mention_id",
    "semantic_mentions_for_target",
    "build_semantic_mentions",
    "bounded_candidate_walk",
]
