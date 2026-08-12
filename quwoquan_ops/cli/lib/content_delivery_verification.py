"""Minimal Research content delivery verification from immutable receipts."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any


_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


def _object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object: {path}")
    return value


def _evidence_path(
    output_root: Path,
    raw_ref: object,
    *,
    label: str,
) -> Path:
    ref = str(raw_ref or "").strip()
    if not ref:
        raise ValueError(f"{label} ref is missing")
    root = output_root.resolve()
    path = (root / ref).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} ref escapes QWQ_OUTPUT_ROOT") from exc
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} evidence is missing: {ref}")
    return path


def _string_set(value: object, *, label: str) -> set[str]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    rows = [str(item or "").strip() for item in value]
    if any(not item for item in rows) or len(rows) != len(set(rows)):
        raise ValueError(f"{label} must contain unique non-empty values")
    return set(rows)


def _count(value: object, *, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def verify_content_delivery(
    *,
    output_root: Path,
    readiness_path: Path,
    environment: str,
    release_id: str,
    manifest_digest: str,
) -> dict[str, Any]:
    """Verify only import, outbox, Search, Recommendation, Homepage and Persona.

    Quality and authorization are upstream pool facts. Provider, chat, share,
    device UAT and commercial rollout evidence are deliberately outside this
    Research delivery check.
    """

    issues: list[str] = []
    counts: dict[str, int] = {}
    try:
        if environment not in {"alpha", "beta", "gamma"}:
            raise ValueError("content-delivery supports alpha, beta or gamma")
        if not release_id:
            raise ValueError("releaseId is required")
        if _DIGEST.fullmatch(manifest_digest) is None:
            raise ValueError("manifestDigest must use sha256:<64 lowercase hex>")

        readiness = _object(readiness_path, label="release readiness")
        if (
            readiness.get("schema")
            != "quwoquan_data.environment_release_readiness"
            or readiness.get("passed") is not True
            or readiness.get("environment") != environment
            or readiness.get("releaseId") != release_id
            or readiness.get("manifestDigest") != manifest_digest
        ):
            raise ValueError("release readiness identity or result is invalid")

        post_ids = _string_set(readiness.get("postIds"), label="readiness postIds")
        entity_refs = _string_set(
            readiness.get("entityRefs"), label="readiness entityRefs"
        )
        creator_ids = _string_set(
            readiness.get("creatorIds"), label="readiness creatorIds"
        )
        if not post_ids:
            raise ValueError("content-delivery requires at least one Post")

        import_report = _object(
            _evidence_path(
                output_root,
                readiness.get("contentImportReportRef"),
                label="content import",
            ),
            label="content import",
        )
        if (
            import_report.get("status") != "active"
            or import_report.get("environment") != environment
            or import_report.get("releaseId") != release_id
            or import_report.get("manifestDigest") != manifest_digest
        ):
            raise ValueError("content import is not the active immutable release")
        import_counts = import_report.get("counts")
        if not isinstance(import_counts, Mapping):
            raise ValueError("content import counts must be an object")
        loaded = _count(import_counts.get("postsLoaded"), label="postsLoaded")
        upserted = _count(
            import_counts.get("postsUpserted"), label="postsUpserted"
        )
        outbox_ready = _count(
            import_counts.get("outboxEventsReady"), label="outboxEventsReady"
        )
        outbox_appended = _count(
            import_counts.get("outboxEventsAppended"),
            label="outboxEventsAppended",
        )
        if loaded != len(post_ids) or upserted != len(post_ids):
            raise ValueError("Manifest/import Post counts differ")
        if outbox_ready < len(post_ids) or outbox_appended not in {
            0,
            outbox_ready,
        }:
            raise ValueError("durable Post outbox closure is incomplete")

        creator_report = _object(
            _evidence_path(
                output_root,
                readiness.get("creatorAttributionRef"),
                label="Persona import",
            ),
            label="Persona import",
        )
        if (
            creator_report.get("status") != "active"
            or creator_report.get("environment") != environment
            or creator_report.get("releaseId") != release_id
            or _string_set(
                creator_report.get("verifiedCreatorIds"),
                label="verifiedCreatorIds",
            )
            != creator_ids
        ):
            raise ValueError("Persona import differs from the Manifest")

        homepage_report = _object(
            _evidence_path(
                output_root,
                readiness.get("homepageApiVerificationRef"),
                label="Homepage API",
            ),
            label="Homepage API",
        )
        homepage_entities = {
            str(row.get("entityRef") or "").strip()
            for row in homepage_report.get("entities") or []
            if isinstance(row, Mapping)
        }
        if (
            homepage_report.get("passed") is not True
            or homepage_report.get("environment") != environment
            or homepage_report.get("releaseId") != release_id
            or homepage_entities != entity_refs
        ):
            raise ValueError("Homepage API differs from the Manifest")

        post_report = _object(
            _evidence_path(
                output_root,
                readiness.get("postApiVerificationRef"),
                label="Post API",
            ),
            label="Post API",
        )
        verified_posts = {
            str(row.get("postId") or "").strip()
            for row in post_report.get("posts") or []
            if isinstance(row, Mapping)
        }
        if (
            post_report.get("passed") is not True
            or post_report.get("environment") != environment
            or post_report.get("releaseId") != release_id
            or verified_posts != post_ids
        ):
            raise ValueError("Post API differs from the Manifest")

        search_rows = post_report.get("searchQueries")
        if not isinstance(search_rows, list):
            raise ValueError("Search verification is missing")
        searchable_posts = {
            str(row.get("targetId") or "").strip()
            for row in search_rows
            if isinstance(row, Mapping) and row.get("targetType") == "post"
        }
        creators = [
            row
            for row in post_report.get("creators") or []
            if isinstance(row, Mapping)
        ]
        persona_ids = {
            str(row.get("personaId") or "").strip() for row in creators
        }
        searchable_personas = {
            str(row.get("targetId") or "").strip()
            for row in search_rows
            if isinstance(row, Mapping) and row.get("targetType") == "author"
        }
        if searchable_posts != post_ids or searchable_personas != persona_ids:
            raise ValueError("Search does not expose every selected Post and Persona")
        if any(row.get("profileStatus") != 200 for row in creators):
            raise ValueError("Persona public profile readback is incomplete")

        feed_rows = post_report.get("feedQueries")
        if not isinstance(feed_rows, list):
            raise ValueError("Recommendation verification is missing")
        by_name = {
            str(row.get("name") or ""): row
            for row in feed_rows
            if isinstance(row, Mapping)
        }
        typed_ids: set[str] = set()
        for name in ("typed_article", "typed_image", "typed_video"):
            row = by_name.get(name)
            if row is not None:
                typed_ids.update(
                    _string_set(row.get("matchedPostIds"), label=f"{name} matches")
                )
        homepage_recommend = by_name.get("homepage_recommend")
        homepage_ids = (
            _string_set(
                homepage_recommend.get("matchedPostIds"),
                label="homepage recommendation matches",
            )
            if isinstance(homepage_recommend, Mapping)
            else set()
        )
        if typed_ids != post_ids or not homepage_ids or not homepage_ids <= post_ids:
            raise ValueError("Recommendation does not expose the selected release")

        counts = {
            "manifestPosts": len(post_ids),
            "importedPosts": loaded,
            "outboxPosts": len(post_ids),
            "searchablePosts": len(searchable_posts),
            "recommendablePosts": len(typed_ids),
            "homepages": len(entity_refs),
            "personas": len(persona_ids),
        }
    except (OSError, TypeError, ValueError) as exc:
        issues.append(str(exc))

    return {
        "schema": "quwoquan_ops.content_delivery_verification",
        "result": "ready" if not issues else "blocked",
        "environment": environment,
        "releaseId": release_id,
        "manifestDigest": manifest_digest,
        "checks": {
            "delivery": "passed" if not issues else "failed",
        },
        "counts": counts,
        "issues": issues,
    }


__all__ = ["verify_content_delivery"]
