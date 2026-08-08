"""Project immutable homepage/article catalogs into scale source-pool rows.

The projection is read-only and deterministic. Every source-unit,
acquisition, rights and quality binding points back to the exact create-once
catalog file so ``validate_scale_source_pool_evidence`` can re-read the
physical bytes before a scale pool is persisted.
"""
from __future__ import annotations

import hashlib
import json
import stat
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from core.io import read_json
from core.schema import load_schema, validate_strict

from content.source.research.article_source_unit_catalog import (
    validate_article_source_unit_catalog,
)
from content.source.research.homepage_source_unit_catalog import (
    validate_homepage_source_unit_catalog,
)
from content.source.research.homepage_article_source_ready_batch import (
    load_homepage_article_source_ready_batch,
)


PROJECTION_INVALID = "DATA.SOURCE.INVALID_EVIDENCE"
PROJECTION_SCHEMA = "quwoquan_data.scale_source_pool_homepage_article_projection"
_SHA256_PREFIX = "sha256:"


class ScaleSourcePoolProjectionError(ValueError):
    """Typed catalog-to-scale projection blocker."""

    def __init__(self, issues: Sequence[object]) -> None:
        normalized = tuple(
            str(issue).strip() for issue in issues if str(issue).strip()
        )
        if not normalized:
            raise ValueError("scale source-pool projection error requires an issue")
        self.code = PROJECTION_INVALID
        self.issues = normalized
        super().__init__(f"{PROJECTION_INVALID}: " + "; ".join(normalized))


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _SHA256_PREFIX + hashlib.sha256(encoded).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return _SHA256_PREFIX + digest.hexdigest()


def _catalog_file(root: Path, ref: str, *, label: str) -> Path:
    relative = Path(str(ref or "").strip())
    if not str(relative) or relative.is_absolute() or ".." in relative.parts:
        raise ScaleSourcePoolProjectionError(
            [f"{label} must be a non-empty relative catalog ref"]
        )
    current = root
    for index, part in enumerate(relative.parts):
        current = current / part
        try:
            mode = current.lstat().st_mode
        except OSError as exc:
            raise ScaleSourcePoolProjectionError(
                [f"{label} is missing or unreadable: {relative.as_posix()}"]
            ) from exc
        if stat.S_ISLNK(mode):
            raise ScaleSourcePoolProjectionError(
                [f"{label} must not traverse a symlink: {relative.as_posix()}"]
            )
        final = index == len(relative.parts) - 1
        if (not final and not stat.S_ISDIR(mode)) or (
            final and not stat.S_ISREG(mode)
        ):
            raise ScaleSourcePoolProjectionError(
                [f"{label} is not a regular catalog file: {relative.as_posix()}"]
            )
    return current


def _load_catalog(
    *,
    root: Path,
    ref: str,
    expected_catalog_digest: str,
    expected_file_sha256: str,
    carrier: str,
) -> tuple[dict[str, Any], str, str]:
    path = _catalog_file(root, ref, label=f"{carrier}CatalogRef")
    actual_file_sha256 = _file_sha256(path)
    if actual_file_sha256 != expected_file_sha256:
        raise ScaleSourcePoolProjectionError(
            [
                f"{carrier} catalog fileSha256 drift: "
                f"expected={expected_file_sha256} actual={actual_file_sha256}"
            ]
        )
    try:
        document = read_json(path)
    except (OSError, TypeError, ValueError) as exc:
        raise ScaleSourcePoolProjectionError(
            [f"{carrier} catalog is unreadable: {exc}"]
        ) from exc
    if not isinstance(document, dict):
        raise ScaleSourcePoolProjectionError(
            [f"{carrier} catalog must be one JSON object"]
        )
    try:
        if carrier == "homepage":
            validate_homepage_source_unit_catalog(document)
        else:
            validate_article_source_unit_catalog(document)
    except ValueError as exc:
        raise ScaleSourcePoolProjectionError(
            [f"{carrier} catalog contract is invalid: {exc}"]
        ) from exc
    stable = {
        key: value for key, value in document.items() if key != "catalogDigest"
    }
    recomputed = _canonical_digest(stable)
    if document.get("catalogDigest") != recomputed:
        raise ScaleSourcePoolProjectionError(
            [f"{carrier} catalogDigest does not match canonical bytes"]
        )
    if recomputed != expected_catalog_digest:
        raise ScaleSourcePoolProjectionError(
            [
                f"{carrier} catalogDigest drift: "
                f"expected={expected_catalog_digest} actual={recomputed}"
            ]
        )
    return document, ref, actual_file_sha256


def _identity(document: Mapping[str, Any]) -> tuple[str, str, str]:
    return tuple(
        str(document.get(field) or "")
        for field in ("sourceRevision", "sourceDigest", "entityCatalogDigest")
    )


def _aggregate_rights(rows: Sequence[Mapping[str, Any]]) -> tuple[str, str]:
    statuses = {str(row.get("rightsStatus") or "") for row in rows}
    if "unknown" in statuses:
        rights_status = "unknown"
    elif "unverified" in statuses:
        rights_status = "unverified"
    else:
        rights_status = "verified"
    decisions = {str(row.get("distributionDecision") or "") for row in rows}
    decision = (
        "research_allowed"
        if "research_allowed" in decisions
        else "commercial_allowed"
    )
    return rights_status, decision


def _bindings(
    *,
    carrier: str,
    candidate_id: str,
    evidence_digest: str,
    evidence_ref: str,
    file_sha256: str,
    source_unit: object,
    acquisition: object,
    rights: object,
    quality: object,
) -> dict[str, Any]:
    values = {
        "sourceUnit": source_unit,
        "acquisition": acquisition,
        "rights": rights,
        "quality": quality,
    }
    result: dict[str, Any] = {}
    for prefix, value in values.items():
        result[f"{prefix}Ref"] = evidence_ref
        result[f"{prefix}Digest"] = _canonical_digest(
            {
                "schema": f"quwoquan_data.{carrier}_{prefix}_composite",
                "evidenceDigest": evidence_digest,
                "candidateId": candidate_id,
                "value": value,
            }
        )
        result[f"{prefix}FileSha256"] = file_sha256
    return result


def _homepage_row(
    candidate: Mapping[str, Any],
    *,
    evidence_digest: str,
    evidence_ref: str,
    file_sha256: str,
) -> dict[str, Any]:
    candidate_id = str(candidate["candidateId"])
    entity_ref = str(candidate["entityRef"])
    primary = candidate["primarySource"]
    hero = candidate["hero"]
    assert isinstance(primary, Mapping) and isinstance(hero, Mapping)
    rights_status, decision = _aggregate_rights([hero])
    bindings = _bindings(
        carrier="homepage",
        candidate_id=candidate_id,
        evidence_digest=evidence_digest,
        evidence_ref=evidence_ref,
        file_sha256=file_sha256,
        source_unit={
            "primarySource": primary,
            "structuredFacts": candidate["structuredFacts"],
            "factEvidence": candidate["factEvidence"],
            "factConflicts": candidate["factConflicts"],
        },
        acquisition={
            key: hero[key]
            for key in (
                "assetId",
                "assetRef",
                "originalAssetUrl",
                "sourcePageUrl",
                "acquisitionStatus",
                "contentSha256",
            )
        },
        rights={
            key: hero[key]
            for key in (
                "creator",
                "license",
                "termsUrl",
                "authorizationProof",
                "authorizationRequired",
                "rightsStatus",
                "rightsIssues",
                "distributionDecision",
            )
        },
        quality={
            key: hero[key]
            for key in ("qualityStatus", "safetyStatus", "generated")
        },
    )
    return {
        "candidateId": candidate_id,
        "carrier": "homepage",
        "objectRef": "entities/" + entity_ref.removeprefix("/entity/").strip("/"),
        "entityRef": entity_ref,
        "observedEntityRef": str(candidate["observedEntityRef"]),
        "sourceRevision": candidate["sourceRevision"],
        "sourceDigest": candidate["sourceDigest"],
        "entityCatalogDigest": candidate["entityCatalogDigest"],
        **bindings,
        "provider": primary["platform"],
        "contentSha256": _canonical_digest(
            {
                "bodyContentSha256": primary["bodyContentSha256"],
                "heroContentSha256": hero["contentSha256"],
            }
        ),
        "acquisitionStatus": "acquired",
        "rightsStatus": rights_status,
        "distributionDecision": decision,
        "qualityStatus": "passed",
        "generated": False,
        "playabilityRef": None,
        "playabilityDigest": None,
        "playabilityFileSha256": None,
        "videoReadiness": None,
    }


def _article_row(
    candidate: Mapping[str, Any],
    *,
    evidence_digest: str,
    evidence_ref: str,
    file_sha256: str,
) -> dict[str, Any]:
    candidate_id = str(candidate["candidateId"])
    assets = [row for row in candidate["assets"] if isinstance(row, Mapping)]
    rights_status, decision = _aggregate_rights(assets)
    bindings = _bindings(
        carrier="article",
        candidate_id=candidate_id,
        evidence_digest=evidence_digest,
        evidence_ref=evidence_ref,
        file_sha256=file_sha256,
        source_unit={
            key: candidate[key]
            for key in (
                "sourceUnitId",
                "sourceUnitRef",
                "sourceUnitDigest",
                "sourceKind",
                "extractor",
                "sourceUrl",
                "bodyEvidenceRef",
                "bodyContentSha256",
            )
        },
        acquisition=[
            {
                key: row[key]
                for key in (
                    "assetId",
                    "role",
                    "assetRef",
                    "originalAssetUrl",
                    "sourcePageUrl",
                    "acquisitionStatus",
                    "contentSha256",
                )
            }
            for row in assets
        ],
        rights=[
            {
                key: row[key]
                for key in (
                    "assetId",
                    "creator",
                    "license",
                    "termsUrl",
                    "authorizationProof",
                    "authorizationRequired",
                    "rightsStatus",
                    "rightsIssues",
                    "distributionDecision",
                )
            }
            for row in assets
        ],
        quality=[
            {
                key: row[key]
                for key in (
                    "assetId",
                    "role",
                    "qualityStatus",
                    "safetyStatus",
                    "generated",
                )
            }
            for row in assets
        ],
    )
    return {
        "candidateId": candidate_id,
        "carrier": "article",
        "objectRef": f"posts/article/{candidate_id}",
        "entityRef": candidate["entityRef"],
        "observedEntityRef": candidate["observedEntityRef"],
        "sourceRevision": candidate["sourceRevision"],
        "sourceDigest": candidate["sourceDigest"],
        "entityCatalogDigest": candidate["entityCatalogDigest"],
        **bindings,
        "provider": candidate["platform"],
        "contentSha256": _canonical_digest(
            {
                "bodyContentSha256": candidate["bodyContentSha256"],
                "mediaContentSha256": sorted(
                    str(row["contentSha256"]) for row in assets
                ),
            }
        ),
        "acquisitionStatus": "acquired",
        "rightsStatus": rights_status,
        "distributionDecision": decision,
        "qualityStatus": "passed",
        "generated": False,
        "playabilityRef": None,
        "playabilityDigest": None,
        "playabilityFileSha256": None,
        "videoReadiness": None,
    }


def _validate_rows(rows: Sequence[Mapping[str, Any]]) -> None:
    schema = load_schema("source", "scale_source_pool")
    candidate_schema = schema["$defs"]["candidate"]
    issues: list[str] = []
    for index, row in enumerate(rows):
        issues.extend(
            validate_strict(
                dict(row),
                candidate_schema,
                path=f"$.rows[{index}]",
                _root_schema=schema,
            )
        )
    candidate_ids = [str(row["candidateId"]) for row in rows]
    object_refs = [str(row["objectRef"]) for row in rows]
    content_digests = [str(row["contentSha256"]) for row in rows]
    for label, values in (
        ("candidateId", candidate_ids),
        ("objectRef", object_refs),
        ("contentSha256", content_digests),
    ):
        duplicates = sorted(
            value for value, count in Counter(values).items() if count > 1
        )
        if duplicates:
            issues.append(f"duplicate projected {label}: {duplicates}")
    for row in rows:
        if row["entityRef"] != row["observedEntityRef"]:
            issues.append(f"{row['candidateId']}: entity mismatch")
    if issues:
        raise ScaleSourcePoolProjectionError(issues)


def project_scale_source_pool_homepage_article(
    *,
    evidence_root: Path,
    homepage_catalog_ref: str,
    homepage_catalog_digest: str,
    homepage_catalog_file_sha256: str,
    article_catalog_ref: str,
    article_catalog_digest: str,
    article_catalog_file_sha256: str,
    source_ready_set_ref: str,
    source_ready_set_digest: str,
    source_ready_set_file_sha256: str,
) -> dict[str, Any]:
    """Return deterministic scale candidates without writing any output."""

    root = evidence_root.expanduser().absolute()
    try:
        mode = root.lstat().st_mode
    except OSError as exc:
        raise ScaleSourcePoolProjectionError(
            [f"evidence root is missing or unreadable: {root}"]
        ) from exc
    if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
        raise ScaleSourcePoolProjectionError(
            [f"evidence root must be a real directory: {root}"]
        )
    homepage, homepage_ref, homepage_file_sha = _load_catalog(
        root=root,
        ref=homepage_catalog_ref,
        expected_catalog_digest=homepage_catalog_digest,
        expected_file_sha256=homepage_catalog_file_sha256,
        carrier="homepage",
    )
    article, article_ref, article_file_sha = _load_catalog(
        root=root,
        ref=article_catalog_ref,
        expected_catalog_digest=article_catalog_digest,
        expected_file_sha256=article_catalog_file_sha256,
        carrier="article",
    )
    source_set_path = _catalog_file(
        root, source_ready_set_ref, label="sourceReadySetRef"
    )
    if _file_sha256(source_set_path) != source_ready_set_file_sha256:
        raise ScaleSourcePoolProjectionError(
            ["source-ready set fileSha256 drift"]
        )
    try:
        loaded_batch = load_homepage_article_source_ready_batch(
            source_set_path, evidence_root=root
        )
    except ValueError as exc:
        raise ScaleSourcePoolProjectionError(
            [f"source-ready set is invalid: {exc}"]
        ) from exc
    batch = loaded_batch["batch"]
    if not isinstance(batch, Mapping) or batch.get("sourceSetDigest") != source_ready_set_digest:
        raise ScaleSourcePoolProjectionError(["source-ready sourceSetDigest drift"])
    homepage_batch = loaded_batch["homepageCandidates"]
    article_batch = loaded_batch["articleCandidates"]
    bindings = loaded_batch["capsuleBindings"]
    if homepage.get("candidates") != homepage_batch or article.get("candidates") != article_batch:
        raise ScaleSourcePoolProjectionError(
            ["aggregate catalogs drift from immutable candidate capsules"]
        )
    if not isinstance(bindings, Mapping):
        raise ScaleSourcePoolProjectionError(["source-ready capsule bindings are missing"])
    homepage_identity = _identity(homepage)
    article_identity = _identity(article)
    if homepage_identity != article_identity:
        raise ScaleSourcePoolProjectionError(
            ["homepage/article catalog source identity drift"]
        )
    rows = [
        *(
            _homepage_row(
                candidate,
                evidence_digest=str(bindings[str(candidate["candidateId"])]["digest"]),
                evidence_ref=str(bindings[str(candidate["candidateId"])]["ref"]),
                file_sha256=str(bindings[str(candidate["candidateId"])]["fileSha256"]),
            )
            for candidate in homepage["candidates"]
        ),
        *(
            _article_row(
                candidate,
                evidence_digest=str(bindings[str(candidate["candidateId"])]["digest"]),
                evidence_ref=str(bindings[str(candidate["candidateId"])]["ref"]),
                file_sha256=str(bindings[str(candidate["candidateId"])]["fileSha256"]),
            )
            for candidate in article["candidates"]
        ),
    ]
    rows = sorted(
        rows,
        key=lambda row: (str(row["carrier"]), str(row["objectRef"])),
    )
    _validate_rows(rows)
    stable: dict[str, Any] = {
        "schema": PROJECTION_SCHEMA,
        "sourceRevision": homepage_identity[0],
        "sourceDigest": homepage_identity[1],
        "entityCatalogDigest": homepage_identity[2],
        "catalogBindings": [
            {
                "carrier": "homepage",
                "catalogRef": homepage_ref,
                "catalogDigest": homepage_catalog_digest,
                "catalogFileSha256": homepage_file_sha,
            },
            {
                "carrier": "article",
                "catalogRef": article_ref,
                "catalogDigest": article_catalog_digest,
                "catalogFileSha256": article_file_sha,
            },
            {
                "carrier": "homepage_article_source_set",
                "catalogRef": source_ready_set_ref,
                "catalogDigest": source_ready_set_digest,
                "catalogFileSha256": source_ready_set_file_sha256,
            },
        ],
        "rowCounts": [
            {
                "carrier": carrier,
                "candidateCount": sum(row["carrier"] == carrier for row in rows),
            }
            for carrier in ("homepage", "article")
        ],
        "rows": rows,
    }
    return {**stable, "projectionDigest": _canonical_digest(stable)}


__all__ = [
    "PROJECTION_INVALID",
    "PROJECTION_SCHEMA",
    "ScaleSourcePoolProjectionError",
    "project_scale_source_pool_homepage_article",
]
