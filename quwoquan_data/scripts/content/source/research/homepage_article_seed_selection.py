"""Validate governed seed selections against exact fresh coverage evidence."""
from __future__ import annotations

import hashlib
import json
import stat
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from core.io import read_json
from core.schema import assert_valid

SOURCE_INVALID_EVIDENCE = "DATA.SOURCE.INVALID_EVIDENCE"


class HomepageArticleSeedSelectionError(ValueError):
    """Typed selector contract or fresh-coverage intersection blocker."""

    def __init__(self, issues: Sequence[object]) -> None:
        normalized = tuple(str(issue).strip() for issue in issues if str(issue).strip())
        if not normalized:
            raise ValueError("homepage/article seed selection requires an issue")
        self.code = SOURCE_INVALID_EVIDENCE
        self.issues = normalized
        super().__init__(f"{self.code}: " + "; ".join(normalized))


def _digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def seed_id(
    *,
    seed_origin: str,
    coverage_key: Mapping[str, Any],
    article_category: str = "",
) -> str:
    """Return the deterministic identity of one origin-bound exact coverage key."""

    identity: dict[str, Any] = {
        "seedOrigin": str(seed_origin),
        "coverageKey": dict(coverage_key),
    }
    if article_category:
        identity["articleCategory"] = article_category
    return _digest(identity)


def load_homepage_article_seed_selection(path: Path) -> dict[str, Any]:
    """Load one regular create-once hint document and verify its own digest."""

    source = path.expanduser().absolute()
    try:
        mode = source.lstat().st_mode
        if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
            raise OSError("not a regular non-symlink file")
        document = read_json(source)
        if not isinstance(document, dict):
            raise TypeError("seed selection must be one JSON object")
        assert_valid(
            document,
            "source",
            "homepage_article_seed_selection",
            label="homepage/article seed selection",
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise HomepageArticleSeedSelectionError([str(exc)]) from exc
    stable = {key: value for key, value in document.items() if key != "selectionDigest"}
    if document["selectionDigest"] != _digest(stable):
        raise HomepageArticleSeedSelectionError(["selectionDigest mismatch"])
    seeds = [dict(row) for row in document["seeds"] if isinstance(row, Mapping)]
    actual_counts = dict(
        Counter(str(row["coverageKey"]["carrier"]) for row in seeds)
    )
    expected_counts = {
        "homepage": actual_counts.get("homepage", 0),
        "article": actual_counts.get("article", 0),
    }
    if document["counts"] != expected_counts:
        raise HomepageArticleSeedSelectionError(["seed carrier counts drift"])
    keys = [json.dumps(row["coverageKey"], sort_keys=True) for row in seeds]
    seed_ids = [str(row["seedId"]) for row in seeds]
    if len(keys) != len(set(keys)):
        raise HomepageArticleSeedSelectionError(["duplicate exact coverage seed key"])
    if len(seed_ids) != len(set(seed_ids)):
        raise HomepageArticleSeedSelectionError(["duplicate seedId"])
    for index, row in enumerate(seeds):
        expected = seed_id(
            seed_origin=str(row["seedOrigin"]),
            coverage_key=row["coverageKey"],
            article_category=str(row.get("articleCategory") or ""),
        )
        if row["seedId"] != expected:
            raise HomepageArticleSeedSelectionError(
                [f"seeds[{index}].seedId mismatch"]
            )
    return document


def _coverage_entity_ref(row: Mapping[str, Any]) -> str:
    canonical = str(row.get("canonicalEntityRef") or "").strip()
    if canonical:
        return canonical
    entity_type = str(row.get("entityType") or "").strip().split("/", 1)
    name = str(row.get("candidateName") or "").strip()
    if len(entity_type) != 2 or not all(entity_type) or not name or "/" in name:
        return ""
    return f"/entity/{entity_type[0]}/{entity_type[1]}/{name}"


def select_fresh_coverage_candidates(
    selection: Mapping[str, Any],
    planned: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    """Intersect hints with fresh coverage using exact entity/carrier/source keys."""

    fresh: dict[tuple[str, str, str, str], list[Mapping[str, Any]]] = {}
    for row in planned:
        source = row.get("source")
        source = source if isinstance(source, Mapping) else {}
        entity_ref = _coverage_entity_ref(row)
        source_url = str(source.get("sourceUrl") or "")
        coverage_identity = str(row.get("coverageEntityIdentity") or "")
        coverage_digest = str(row.get("coverageRecordDigest") or "")
        exact_key = (coverage_identity, coverage_digest, entity_ref, source_url)
        fresh.setdefault(exact_key, []).append(row)
    ambiguous = [key for key, rows in fresh.items() if len(rows) != 1]
    if ambiguous:
        raise HomepageArticleSeedSelectionError(
            ["fresh coverage contains ambiguous exact coverage keys"]
        )
    selected = {"homepage": [], "article": []}
    excluded: list[dict[str, Any]] = []
    for raw in selection["seeds"]:
        seed = dict(raw)
        coverage_key = seed["coverageKey"]
        carrier = str(coverage_key["carrier"])
        key = (
            str(coverage_key["coverageEntityIdentity"]),
            str(coverage_key["coverageRecordDigest"]),
            str(coverage_key["entityRef"]),
            str(coverage_key["sourceUrl"]),
        )
        matches = fresh.get(key) or []
        row = matches[0] if len(matches) == 1 else None
        source = row.get("source") if isinstance(row, Mapping) else None
        source = source if isinstance(source, Mapping) else {}
        matching_fields = bool(row) and all(
            (
                str(row.get("candidateName") or "") == str(seed["candidateName"]),
                str(row.get("province") or "") == str(seed["province"]),
                str(row.get("city") or "") == str(seed["city"]),
                str(row.get("district") or "") == str(seed["district"]),
                str(row.get("entityType") or "") == str(seed["entityType"]),
                str(source.get("sourceKind") or "") == str(seed["sourceKind"]),
                str(source.get("extractor") or "") == str(seed["extractor"]),
            )
        )
        if not matching_fields:
            excluded.append(
                {
                    "seedOrigin": str(seed["seedOrigin"]),
                    "seedId": str(seed["seedId"]),
                    "coverageKey": dict(coverage_key),
                    "reason": "fresh coverage intersection missing or changed",
                }
            )
            continue
        selected[carrier].append({**dict(row), "seed": seed})
    return selected, excluded


__all__ = [
    "SOURCE_INVALID_EVIDENCE",
    "HomepageArticleSeedSelectionError",
    "load_homepage_article_seed_selection",
    "select_fresh_coverage_candidates",
    "seed_id",
]
