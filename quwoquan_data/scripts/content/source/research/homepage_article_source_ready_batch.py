"""Freeze homepage/article catalogs from immutable physical evidence capsules."""
from __future__ import annotations

import hashlib
import json
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, NoReturn

from core.io import read_json
from core.schema import assert_valid

from content.source.research.article_source_unit_catalog import (
    build_article_source_unit_catalog,
    write_create_once_article_source_unit_catalog,
)
from content.source.research.homepage_source_unit_catalog import (
    build_homepage_source_unit_catalog,
    write_create_once_homepage_source_unit_catalog,
)
from content.source.research.homepage_article_seed_selection import (
    load_homepage_article_seed_selection,
)
from content.source.research.homepage_article_source_ready_provenance import verify_source_ready_provenance

SOURCE_POOL_SHORTFALL = "DATA.SOURCE.POOL_SHORTFALL"
SOURCE_INVALID_EVIDENCE = "DATA.SOURCE.INVALID_EVIDENCE"
BATCH_SCHEMA = "quwoquan_data.homepage_article_source_ready_batch"
CAPSULE_SCHEMA = "quwoquan_data.homepage_article_source_ready_candidate"


class HomepageArticleSourceReadyBatchError(ValueError):
    """Typed physical-evidence or pool shortfall blocker."""

    def __init__(self, code: str, issues: Sequence[object]) -> None:
        normalized = tuple(str(issue).strip() for issue in issues if str(issue).strip())
        if not normalized:
            raise ValueError("source-ready batch error requires an issue")
        self.code = code
        self.issues = normalized
        super().__init__(f"{code}: " + "; ".join(normalized))


def _digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _safe_file(root: Path, ref: object, *, label: str) -> Path:
    relative = Path(str(ref or "").strip())
    if not str(relative) or relative.is_absolute() or ".." in relative.parts:
        raise HomepageArticleSourceReadyBatchError(
            SOURCE_INVALID_EVIDENCE,
            [f"{label} must be a non-empty relative reference"],
        )
    current = root.expanduser().resolve()
    for index, part in enumerate(relative.parts):
        current = current / part
        try:
            mode = current.lstat().st_mode
        except OSError as exc:
            raise HomepageArticleSourceReadyBatchError(
                SOURCE_INVALID_EVIDENCE,
                [f"{label} is missing: {relative.as_posix()}"],
            ) from exc
        if stat.S_ISLNK(mode):
            raise HomepageArticleSourceReadyBatchError(
                SOURCE_INVALID_EVIDENCE,
                [f"{label} must not traverse a symlink: {relative.as_posix()}"],
            )
        final = index == len(relative.parts) - 1
        if (final and not stat.S_ISREG(mode)) or (
            not final and not stat.S_ISDIR(mode)
        ):
            raise HomepageArticleSourceReadyBatchError(
                SOURCE_INVALID_EVIDENCE,
                [f"{label} must resolve to a regular file: {relative.as_posix()}"],
            )
    return current


def _safe_directory(root: Path, ref: object, *, label: str) -> Path:
    base = root.expanduser().absolute()
    raw = str(ref or "").strip()
    relative = Path(raw)
    if raw != "." and (not raw or relative.is_absolute() or ".." in relative.parts):
        raise HomepageArticleSourceReadyBatchError(
            SOURCE_INVALID_EVIDENCE, [f"{label} must be a safe relative directory"]
        )
    try:
        roots = (base,) if raw == "." else (
            base,
            *(base.joinpath(*relative.parts[:index]) for index in range(1, len(relative.parts) + 1)),
        )
        for current in roots:
            mode = current.lstat().st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                raise OSError("symlink or non-directory")
    except OSError as exc:
        raise HomepageArticleSourceReadyBatchError(
            SOURCE_INVALID_EVIDENCE, [f"{label} is missing or not a real directory"]
        ) from exc
    return roots[-1]


def _load_json_file(
    root: Path,
    binding: Mapping[str, Any],
    *,
    label: str,
    digest_field: str | None = None,
) -> tuple[dict[str, Any], Path]:
    path = _safe_file(root, binding.get("ref"), label=label)
    actual_file_sha = _file_sha256(path)
    if actual_file_sha != binding.get("fileSha256"):
        raise HomepageArticleSourceReadyBatchError(
            SOURCE_INVALID_EVIDENCE,
            [f"{label} fileSha256 drift"],
        )
    try:
        document = read_json(path)
    except (OSError, TypeError, ValueError) as exc:
        raise HomepageArticleSourceReadyBatchError(
            SOURCE_INVALID_EVIDENCE,
            [f"{label} is not readable JSON: {exc}"],
        ) from exc
    if not isinstance(document, dict):
        raise HomepageArticleSourceReadyBatchError(
            SOURCE_INVALID_EVIDENCE,
            [f"{label} must be one JSON object"],
        )
    if digest_field and document.get(digest_field) != binding.get("digest"):
        raise HomepageArticleSourceReadyBatchError(
            SOURCE_INVALID_EVIDENCE,
            [f"{label} {digest_field} drift"],
        )
    return document, path


def _identity(value: Mapping[str, Any]) -> tuple[str, str, str]:
    return tuple(
        str(value.get(field) or "")
        for field in ("sourceRevision", "sourceDigest", "entityCatalogDigest")
    )


def _verify_bound_file(
    root: Path,
    binding: Mapping[str, Any],
    *,
    label: str,
) -> str:
    path = _safe_file(root, binding.get("ref"), label=label)
    actual = _file_sha256(path)
    if actual != binding.get("fileSha256"):
        raise HomepageArticleSourceReadyBatchError(
            SOURCE_INVALID_EVIDENCE,
            [f"{label} physical bytes drift"],
        )
    expected_content = str(binding.get("contentSha256") or "")
    if expected_content and actual != expected_content:
        raise HomepageArticleSourceReadyBatchError(
            SOURCE_INVALID_EVIDENCE,
            [f"{label} contentSha256 drift"],
        )
    return actual


def _candidate_bindings(
    carrier: str, candidate: Mapping[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if carrier == "homepage":
        primary = candidate.get("primarySource")
        hero = candidate.get("hero")
        if not isinstance(primary, Mapping) or not isinstance(hero, Mapping):
            raise HomepageArticleSourceReadyBatchError(
                SOURCE_INVALID_EVIDENCE,
                ["homepage capsule lacks primarySource/hero"],
            )
        body = {
            "ref": primary.get("bodyEvidenceRef"),
            "contentSha256": primary.get("bodyContentSha256"),
        }
        media = [{
            "assetId": hero.get("assetId"),
            "role": "hero",
            "ref": hero.get("assetRef"),
            "contentSha256": hero.get("contentSha256"),
        }]
        return body, media
    assets = candidate.get("assets")
    rows = assets if isinstance(assets, list) else []
    body = {
        "ref": candidate.get("bodyEvidenceRef"),
        "contentSha256": candidate.get("bodyContentSha256"),
    }
    media = [
        {
            "assetId": row.get("assetId"),
            "role": row.get("role"),
            "ref": row.get("assetRef"),
            "contentSha256": row.get("contentSha256"),
        }
        for row in rows
        if isinstance(row, Mapping)
    ]
    return body, media


def _verify_provenance(root: Path, provenance: Mapping[str, Any], *, label: str) -> None:
    def reject(issue: str) -> NoReturn:
        raise HomepageArticleSourceReadyBatchError(SOURCE_INVALID_EVIDENCE, [issue])

    verify_source_ready_provenance(
        root,
        provenance,
        label=label,
        load_json_file=_load_json_file,
        safe_file=_safe_file,
        file_sha256=_file_sha256,
        reject=reject,
    )


def _verify_raw_source_evidence(
    root: Path, provenance: Mapping[str, Any], *, label: str
) -> None:
    binding = {
        "ref": provenance.get("discoveryEvidenceRef"),
        "fileSha256": provenance.get("discoveryEvidenceFileSha256"),
    }
    evidence, _ = _load_json_file(root, binding, label=f"{label}.acquisition")
    if evidence.get("schema") != (
        "quwoquan_data.homepage_article_source_ready_acquisition_evidence"
    ):
        return
    source_unit = evidence.get("sourceUnit")
    if not isinstance(source_unit, Mapping):
        raise HomepageArticleSourceReadyBatchError(
            SOURCE_INVALID_EVIDENCE, [f"{label}.sourceUnit is missing"]
        )
    _verify_bound_file(
        root,
        {
            "ref": source_unit.get("rawEvidenceRef"),
            "fileSha256": source_unit.get("rawEvidenceFileSha256"),
        },
        label=f"{label}.rawEvidence",
    )


def validate_source_ready_candidate_capsule(
    capsule: Mapping[str, Any], *, evidence_root: Path
) -> dict[str, Any]:
    """Validate one candidate capsule and all physical body/media evidence."""

    try:
        assert_valid(
            dict(capsule),
            "source",
            "homepage_article_source_ready_candidate",
            label="homepage/article source-ready candidate capsule",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise HomepageArticleSourceReadyBatchError(
            SOURCE_INVALID_EVIDENCE, [str(exc)]
        ) from exc
    stable = {key: value for key, value in capsule.items() if key != "capsuleDigest"}
    if capsule.get("capsuleDigest") != _digest(stable):
        raise HomepageArticleSourceReadyBatchError(
            SOURCE_INVALID_EVIDENCE, ["candidate capsuleDigest mismatch"]
        )
    carrier = str(capsule["carrier"])
    candidate = capsule["candidate"]
    if not isinstance(candidate, Mapping) or _identity(candidate) != _identity(capsule):
        raise HomepageArticleSourceReadyBatchError(
            SOURCE_INVALID_EVIDENCE, ["candidate capsule source identity drift"]
        )
    if carrier == "homepage" and "primarySource" not in candidate:
        raise HomepageArticleSourceReadyBatchError(
            SOURCE_INVALID_EVIDENCE, ["homepage capsule contains an article candidate"]
        )
    if carrier == "article" and "sourceUnitId" not in candidate:
        raise HomepageArticleSourceReadyBatchError(
            SOURCE_INVALID_EVIDENCE, ["article capsule contains a homepage candidate"]
        )
    try:
        builder = (
            build_homepage_source_unit_catalog
            if carrier == "homepage"
            else build_article_source_unit_catalog
        )
        builder(
            catalog_id=f"capsule-validation-{candidate.get('candidateId')}",
            catalog_version="capsule",
            created_at="immutable-capsule",
            minimum_candidate_count=1,
            source_revision=_identity(capsule)[0],
            source_digest=_identity(capsule)[1],
            entity_catalog_digest=_identity(capsule)[2],
            candidates=[candidate],
        )
    except ValueError as exc:
        raise HomepageArticleSourceReadyBatchError(
            SOURCE_INVALID_EVIDENCE,
            [f"{carrier} candidate contract is invalid: {exc}"],
        ) from exc
    materialization = capsule["materialization"]
    assert isinstance(materialization, Mapping)
    expected_body, expected_media = _candidate_bindings(carrier, candidate)
    actual_body = materialization["body"]
    actual_media = materialization["media"]
    assert isinstance(actual_body, Mapping) and isinstance(actual_media, list)
    if any(actual_body.get(field) != expected_body.get(field) for field in expected_body):
        raise HomepageArticleSourceReadyBatchError(
            SOURCE_INVALID_EVIDENCE, ["candidate body materialization binding drift"]
        )
    expected_media_rows = sorted(
        tuple(row.get(field) for field in ("assetId", "role", "ref", "contentSha256"))
         for row in expected_media
    )
    actual_media_rows = sorted(
        tuple(row.get(field) for field in ("assetId", "role", "ref", "contentSha256"))
         for row in actual_media if isinstance(row, Mapping)
    )
    if actual_media_rows != expected_media_rows:
        raise HomepageArticleSourceReadyBatchError(
            SOURCE_INVALID_EVIDENCE, ["candidate media materialization binding drift"]
        )
    _verify_bound_file(evidence_root, actual_body, label="candidate.body")
    for index, row in enumerate(actual_media):
        assert isinstance(row, Mapping)
        _verify_bound_file(evidence_root, row, label=f"candidate.media[{index}]")
    provenance = capsule["provenance"]
    assert isinstance(provenance, Mapping)
    _verify_provenance(evidence_root, provenance, label="candidate.provenance")
    _verify_raw_source_evidence(
        evidence_root, provenance, label="candidate.provenance"
    )
    return dict(capsule)


def _load_batch_capsules(
    batch: Mapping[str, Any], *, evidence_root: Path
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, dict[str, Any]],
]:
    homepage: list[dict[str, Any]] = []
    article: list[dict[str, Any]] = []
    candidate_ids: set[str] = set()
    homepage_entities: set[str] = set()
    article_units: set[str] = set()
    physical_content: set[str] = set()
    bindings: dict[str, dict[str, Any]] = {}
    for index, raw_binding in enumerate(batch["candidateCapsules"]):
        assert isinstance(raw_binding, Mapping)
        evidence_root_ref = str(raw_binding.get("evidenceRootRef") or "")
        candidate_root = _safe_directory(
            evidence_root,
            evidence_root_ref,
            label=f"candidateCapsules[{index}].evidenceRootRef",
        )
        capsule, _ = _load_json_file(
            candidate_root,
            raw_binding,
            label=f"candidateCapsules[{index}]",
            digest_field="capsuleDigest",
        )
        validate_source_ready_candidate_capsule(capsule, evidence_root=candidate_root)
        candidate = dict(capsule["candidate"])
        candidate_id = str(candidate["candidateId"])
        carrier = str(capsule["carrier"])
        if raw_binding.get("carrier") != carrier or raw_binding.get("candidateId") != candidate_id:
            raise HomepageArticleSourceReadyBatchError(
                SOURCE_INVALID_EVIDENCE,
                [f"candidateCapsules[{index}] binding drift"],
            )
        if _identity(capsule) != _identity(batch):
            raise HomepageArticleSourceReadyBatchError(
                SOURCE_INVALID_EVIDENCE,
                [f"candidateCapsules[{index}] source identity drift"],
            )
        if candidate_id in candidate_ids:
            raise HomepageArticleSourceReadyBatchError(
                SOURCE_INVALID_EVIDENCE, [f"duplicate candidateId: {candidate_id}"]
            )
        candidate_ids.add(candidate_id)
        normalized_binding = dict(raw_binding)
        if evidence_root_ref != ".":
            normalized_binding["ref"] = (
                f"{evidence_root_ref.rstrip('/')}/{raw_binding['ref']}"
            )
        bindings[candidate_id] = normalized_binding
        materialization = capsule["materialization"]
        assert isinstance(materialization, Mapping)
        content_rows = [materialization["body"], *materialization["media"]]
        for content in content_rows:
            assert isinstance(content, Mapping)
            digest = str(content["contentSha256"])
            if digest in physical_content:
                raise HomepageArticleSourceReadyBatchError(
                    SOURCE_INVALID_EVIDENCE,
                    [f"duplicate physical content across candidates: {digest}"],
                )
            physical_content.add(digest)
        if carrier == "homepage":
            entity = str(candidate["entityRef"])
            if entity in homepage_entities:
                raise HomepageArticleSourceReadyBatchError(
                    SOURCE_INVALID_EVIDENCE, [f"duplicate homepage entityRef: {entity}"]
                )
            homepage_entities.add(entity)
            homepage.append(candidate)
        else:
            source_unit = str(candidate["sourceUnitId"])
            if source_unit in article_units:
                raise HomepageArticleSourceReadyBatchError(
                    SOURCE_INVALID_EVIDENCE,
                    [f"duplicate article sourceUnitId: {source_unit}"],
                )
            article_units.add(source_unit)
            article.append(candidate)
    return homepage, article, bindings


def load_homepage_article_source_ready_batch(
    batch_manifest: Path, *, evidence_root: Path
) -> dict[str, Any]:
    """Load and physically verify a batch without writing aggregate catalogs."""

    try:
        batch = read_json(batch_manifest)
        if not isinstance(batch, dict):
            raise TypeError("batch manifest must be one JSON object")
        assert_valid(
            batch,
            "source",
            "homepage_article_source_ready_batch",
            label="homepage/article source-ready batch",
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise HomepageArticleSourceReadyBatchError(
            SOURCE_INVALID_EVIDENCE, [str(exc)]
        ) from exc
    stable = {key: value for key, value in batch.items() if key != "sourceSetDigest"}
    if batch.get("sourceSetDigest") != _digest(stable):
        raise HomepageArticleSourceReadyBatchError(
            SOURCE_INVALID_EVIDENCE, ["sourceSetDigest mismatch"]
        )
    coverage, _ = _load_json_file(
        evidence_root,
        batch["coverageProjection"],
        label="coverageProjection",
    )
    coverage_digest = batch["coverageProjection"]["digest"]
    if coverage_digest not in {
        coverage.get("projectionDigest"),
        coverage.get("documentDigest"),
        coverage.get("receiptDigest"),
    }:
        raise HomepageArticleSourceReadyBatchError(
            SOURCE_INVALID_EVIDENCE, ["coverageProjection digest drift"]
        )
    seed_selection, seed_path = _load_json_file(
        evidence_root,
        batch["seedSelection"],
        label="seedSelection",
    )
    try:
        validated_seed_selection = load_homepage_article_seed_selection(seed_path)
    except ValueError as exc:
        raise HomepageArticleSourceReadyBatchError(
            SOURCE_INVALID_EVIDENCE, [f"seedSelection is invalid: {exc}"]
        ) from exc
    if (
        seed_selection != validated_seed_selection
        or seed_selection.get("selectionDigest") != batch["seedSelection"]["digest"]
    ):
        raise HomepageArticleSourceReadyBatchError(
            SOURCE_INVALID_EVIDENCE, ["seedSelection digest drift"]
        )
    homepage, article, bindings = _load_batch_capsules(
        batch, evidence_root=evidence_root
    )
    expected_counts = {"homepage": len(homepage), "article": len(article)}
    if batch.get("counts") != expected_counts:
        raise HomepageArticleSourceReadyBatchError(
            SOURCE_INVALID_EVIDENCE, ["batch candidate counts drift"]
        )
    return {
        "batch": batch,
        "homepageCandidates": homepage,
        "articleCandidates": article,
        "capsuleBindings": bindings,
    }


def freeze_homepage_article_source_ready_batch(
    batch_manifest: Path,
    *,
    evidence_root: Path,
    output_root: Path,
    minimum_homepage_candidate_count: int,
    minimum_article_candidate_count: int,
) -> dict[str, Any]:
    """Validate one batch and create the two canonical source-unit catalogs."""

    loaded = load_homepage_article_source_ready_batch(
        batch_manifest, evidence_root=evidence_root
    )
    batch = loaded["batch"]
    homepage = loaded["homepageCandidates"]
    article = loaded["articleCandidates"]
    assert isinstance(batch, dict) and isinstance(homepage, list) and isinstance(article, list)
    if (
        minimum_homepage_candidate_count < 0
        or minimum_article_candidate_count < 0
        or not (minimum_homepage_candidate_count or minimum_article_candidate_count)
    ):
        raise HomepageArticleSourceReadyBatchError(
            SOURCE_INVALID_EVIDENCE,
            ["catalog minimums must activate at least one carrier"],
        )
    if len(homepage) < minimum_homepage_candidate_count or len(article) < minimum_article_candidate_count:
        raise HomepageArticleSourceReadyBatchError(
            SOURCE_POOL_SHORTFALL,
            [
                (
                    "homepage/article source-ready pool shortfall: "
                    f"required={minimum_homepage_candidate_count}/"
                    f"{minimum_article_candidate_count} "
                    f"actual={len(homepage)}/{len(article)}"
                )
            ],
        )
    identity = _identity(batch)
    common = {
        "catalog_version": str(batch["targetScale"]).lower(),
        "created_at": str(batch["createdAt"]),
        "source_revision": identity[0],
        "source_digest": identity[1],
        "entity_catalog_digest": identity[2],
    }
    result: dict[str, Any] = {
        "schema": "quwoquan_data.homepage_article_source_ready_batch_write_result",
        "sourceSetDigest": batch["sourceSetDigest"],
    }
    if minimum_homepage_candidate_count:
        homepage_catalog = build_homepage_source_unit_catalog(
            catalog_id=f"{batch['sourceSetId']}-homepage",
            minimum_candidate_count=minimum_homepage_candidate_count,
            candidates=homepage,
            **common,
        )
        homepage_path = output_root / "source-unit-catalogs" / "homepage" / (
            str(homepage_catalog["catalogDigest"]).removeprefix("sha256:") + ".json"
        )
        homepage_frozen = write_create_once_homepage_source_unit_catalog(
            homepage_path, homepage_catalog
        )
        result["homepage"] = {
            "catalogRef": homepage_path.relative_to(output_root).as_posix(),
            "catalogDigest": homepage_frozen["catalogDigest"],
            "catalogFileSha256": _file_sha256(homepage_path),
            "candidateCount": len(homepage),
        }
    if minimum_article_candidate_count:
        article_catalog = build_article_source_unit_catalog(
            catalog_id=f"{batch['sourceSetId']}-article",
            minimum_candidate_count=minimum_article_candidate_count,
            candidates=article,
            **common,
        )
        article_path = output_root / "source-unit-catalogs" / "article" / (
            str(article_catalog["catalogDigest"]).removeprefix("sha256:") + ".json"
        )
        article_frozen = write_create_once_article_source_unit_catalog(
            article_path, article_catalog
        )
        result["article"] = {
            "catalogRef": article_path.relative_to(output_root).as_posix(),
            "catalogDigest": article_frozen["catalogDigest"],
            "catalogFileSha256": _file_sha256(article_path),
            "candidateCount": len(article),
        }
    return result


__all__ = [
    "BATCH_SCHEMA",
    "CAPSULE_SCHEMA",
    "SOURCE_INVALID_EVIDENCE",
    "SOURCE_POOL_SHORTFALL",
    "HomepageArticleSourceReadyBatchError",
    "freeze_homepage_article_source_ready_batch",
    "load_homepage_article_source_ready_batch",
    "validate_source_ready_candidate_capsule",
]
