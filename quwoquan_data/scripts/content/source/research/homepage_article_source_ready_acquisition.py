"""Canonical coverage-to-capsule acquisition for homepage/article source pools."""
from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from core.schema import assert_valid
from governance.coverage.coverage_source_ready_catalog_projection import (
    project_coverage_source_ready_catalog_inputs,
)

from content.source.research.homepage_article_source_ready_baike import (
    acquire_baike_homepage_source_ready_candidate,
)
from content.source.research.homepage_article_source_ready_batch import (
    HomepageArticleSourceReadyBatchError,
    load_homepage_article_source_ready_batch,
    validate_source_ready_candidate_capsule,
)
from content.source.research.homepage_article_source_ready_article_site import (
    acquire_article_site_source_ready_candidate,
)
from content.source.research.homepage_article_source_ready_evidence import (
    assert_source_ready_evidence_matches_capsule,
    canonical_digest,
    file_sha256,
    validate_source_ready_acquisition_evidence,
    write_create_once_bytes,
    write_create_once_json,
)
from content.source.research.homepage_article_source_ready_mediawiki import (
    AcquiredSourceReadyCandidate,
    MediaWikiSourceReadyRejected,
    acquire_mediawiki_source_ready_candidate,
)
from content.source.research.homepage_article_seed_selection import (
    load_homepage_article_seed_selection,
    select_fresh_coverage_candidates,
)

SOURCE_POOL_SHORTFALL = "DATA.SOURCE.POOL_SHORTFALL"
SOURCE_INVALID_EVIDENCE = "DATA.SOURCE.INVALID_EVIDENCE"
_SOURCE_SET_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")
_COVERAGE_FILES = (
    "manifest.json",
    "report.json",
    "source_ready.ndjson",
    "source_inconclusive.ndjson",
    "frozen_targets.ndjson",
)


class HomepageArticleSourceReadyAcquisitionError(ValueError):
    """Typed acquisition shortfall or immutable evidence blocker."""

    def __init__(
        self,
        code: str,
        issues: Sequence[object],
        *,
        checkpoint: Mapping[str, Any] | None = None,
    ) -> None:
        normalized = tuple(
            str(issue).strip() for issue in issues if str(issue).strip()
        )
        if not normalized:
            raise ValueError("homepage/article acquisition requires an issue")
        self.code = code
        self.issues = normalized
        self.checkpoint = dict(checkpoint) if checkpoint is not None else None
        super().__init__(f"{code}: " + "; ".join(normalized))


def _identity(
    *,
    source_revision: str,
    source_digest: str,
    entity_catalog_digest: str,
) -> dict[str, str]:
    values = {
        "sourceRevision": str(source_revision).strip(),
        "sourceDigest": str(source_digest).strip(),
        "entityCatalogDigest": str(entity_catalog_digest).strip(),
    }
    if any(not re.fullmatch(r"sha256:[0-9a-f]{64}", value) for value in values.values()):
        raise HomepageArticleSourceReadyAcquisitionError(
            SOURCE_INVALID_EVIDENCE,
            ["sourceRevision/sourceDigest/entityCatalogDigest must be sha256"],
        )
    return values


def _copy_coverage_run(
    source_run: Path,
    *,
    evidence_root: Path,
    identity: Mapping[str, str],
    expected_projection: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        initial = project_coverage_source_ready_catalog_inputs(
            run_dir=source_run,
            source_revision=identity["sourceRevision"],
            source_digest=identity["sourceDigest"],
            entity_catalog_digest=identity["entityCatalogDigest"],
        )
        if expected_projection is not None and initial != expected_projection:
            raise ValueError("coverage evidence changed after write preflight")
        for name in _COVERAGE_FILES:
            write_create_once_bytes(
                evidence_root / name,
                (source_run / name).read_bytes(),
                allow_empty=name.endswith(".ndjson"),
            )
        observed = project_coverage_source_ready_catalog_inputs(
            run_dir=source_run,
            source_revision=identity["sourceRevision"],
            source_digest=identity["sourceDigest"],
            entity_catalog_digest=identity["entityCatalogDigest"],
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise HomepageArticleSourceReadyAcquisitionError(
            SOURCE_INVALID_EVIDENCE,
            [f"coverage source-readiness evidence is invalid: {exc}"],
        ) from exc
    if observed != initial:
        raise HomepageArticleSourceReadyAcquisitionError(
            SOURCE_INVALID_EVIDENCE,
            ["coverage evidence changed while creating immutable snapshot"],
        )
    projection_path = evidence_root / "coverage-projection.json"
    write_create_once_json(projection_path, initial)
    return initial


def _project_coverage_run(
    source_run: Path, *, identity: Mapping[str, str]
) -> dict[str, Any]:
    try:
        return project_coverage_source_ready_catalog_inputs(
            run_dir=source_run,
            source_revision=identity["sourceRevision"],
            source_digest=identity["sourceDigest"],
            entity_catalog_digest=identity["entityCatalogDigest"],
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise HomepageArticleSourceReadyAcquisitionError(
            SOURCE_INVALID_EVIDENCE,
            [f"coverage source-readiness evidence is invalid: {exc}"],
        ) from exc


def _physical_content(acquired: AcquiredSourceReadyCandidate) -> set[str]:
    return {
        str(acquired.source_unit["bodyContentSha256"]),
        *(str(asset.document["contentSha256"]) for asset in acquired.assets),
    }


def _write_acquired_candidate(
    acquired: AcquiredSourceReadyCandidate,
    *,
    evidence_root: Path,
    identity: Mapping[str, str],
    captured_at: str,
    coverage_binding: Mapping[str, str],
    seed_selection_binding: Mapping[str, str],
    seed: Mapping[str, Any],
) -> dict[str, Any]:
    candidate = acquired.candidate
    candidate_id = str(candidate["candidateId"])
    body_ref = str(acquired.source_unit["bodyEvidenceRef"])
    body_path = evidence_root / body_ref
    write_create_once_bytes(body_path, acquired.body)
    raw_ref = f"raw/{acquired.carrier}/{candidate_id}.json"
    raw_path = evidence_root / raw_ref
    write_create_once_bytes(raw_path, acquired.raw_evidence)
    for asset in acquired.assets:
        write_create_once_bytes(
            evidence_root / str(asset.document["assetRef"]),
            asset.body,
        )
    source_unit = {
        **acquired.source_unit,
        "bodyFileSha256": file_sha256(body_path),
        "rawEvidenceRef": raw_ref,
        "rawEvidenceFileSha256": file_sha256(raw_path),
    }
    seed_binding = {
        "seedOrigin": seed["seedOrigin"],
        "seedId": seed["seedId"],
        "coverageKey": dict(seed["coverageKey"]),
    }
    for field in ("articleCategory", "writingIntent", "topicTagRefs"):
        if field in seed:
            seed_binding[field] = seed[field]
    historical_baseline = seed.get("historicalBaseline")
    historical_comparison: dict[str, Any] | None = None
    if isinstance(historical_baseline, Mapping):
        historical_comparison = {
            "candidateId": historical_baseline["candidateId"],
            "bodyContentSha256": historical_baseline["bodyContentSha256"],
            "bodyComparison": (
                "same"
                if historical_baseline["bodyContentSha256"]
                == source_unit["bodyContentSha256"]
                else "changed"
            ),
        }
    stable_evidence: dict[str, Any] = {
        "schema": "quwoquan_data.homepage_article_source_ready_acquisition_evidence",
        "carrier": acquired.carrier,
        "candidateId": candidate_id,
        "entityRef": candidate["entityRef"],
        **identity,
        "capturedAt": captured_at,
        "sourceAttribution": dict(candidate["sourceAttribution"]),
        "publishMediaMode": str(
            candidate.get("publishMediaMode") or "illustrated"
        ),
        "seedSelection": dict(seed_selection_binding),
        "seed": seed_binding,
        "sourceUnit": source_unit,
        "assets": [dict(asset.document) for asset in acquired.assets],
    }
    if acquired.source_selection_origin != "coverage_source":
        stable_evidence["sourceSelectionOrigin"] = acquired.source_selection_origin
    if historical_comparison is not None:
        stable_evidence["historicalComparison"] = historical_comparison
    evidence = {
        **stable_evidence,
        "evidenceDigest": canonical_digest(stable_evidence),
    }
    validate_source_ready_acquisition_evidence(evidence)
    evidence_ref = (
        f"acquisition-evidence/{acquired.carrier}/"
        f"{evidence['evidenceDigest'].removeprefix('sha256:')}.json"
    )
    evidence_path = evidence_root / evidence_ref
    write_create_once_json(evidence_path, evidence)
    materialization = {
        "body": {
            "ref": body_ref,
            "contentSha256": source_unit["bodyContentSha256"],
            "fileSha256": source_unit["bodyFileSha256"],
        },
        "media": [
            {
                "assetId": asset.document["assetId"],
                "role": asset.document["role"],
                "ref": asset.document["assetRef"],
                "contentSha256": asset.document["contentSha256"],
                "fileSha256": file_sha256(
                    evidence_root / str(asset.document["assetRef"])
                ),
            }
            for asset in acquired.assets
        ],
    }
    evidence_file_binding = {
        "ref": evidence_ref,
        "fileSha256": file_sha256(evidence_path),
    }
    stable_capsule: dict[str, Any] = {
        "schema": "quwoquan_data.homepage_article_source_ready_candidate",
        "carrier": acquired.carrier,
        **identity,
        "candidate": candidate,
        "materialization": materialization,
        "provenance": {
            "coverageProjectionRef": coverage_binding["ref"],
            "coverageProjectionDigest": coverage_binding["digest"],
            "coverageProjectionFileSha256": coverage_binding["fileSha256"],
            "seedSelectionRef": seed_selection_binding["ref"],
            "seedSelectionDigest": seed_selection_binding["digest"],
            "seedSelectionFileSha256": seed_selection_binding["fileSha256"],
            **seed_binding,
            "discoveryEvidenceRef": evidence_ref,
            "discoveryEvidenceFileSha256": evidence_file_binding["fileSha256"],
            "acquisitionEvidenceRefs": [evidence_file_binding],
            "rightsEvidenceRefs": [evidence_file_binding],
            "qualityEvidenceRefs": [evidence_file_binding],
        },
    }
    if acquired.source_selection_origin != "coverage_source":
        stable_capsule["provenance"]["sourceSelectionOrigin"] = (
            acquired.source_selection_origin
        )
    if historical_comparison is not None:
        stable_capsule["provenance"]["historicalComparison"] = historical_comparison
    capsule = {
        **stable_capsule,
        "capsuleDigest": canonical_digest(stable_capsule),
    }
    assert_source_ready_evidence_matches_capsule(evidence, capsule)
    capsule_ref = (
        f"capsules/{acquired.carrier}/"
        f"{capsule['capsuleDigest'].removeprefix('sha256:')}.json"
    )
    capsule_path = evidence_root / capsule_ref
    write_create_once_json(capsule_path, capsule)
    validate_source_ready_candidate_capsule(
        capsule,
        evidence_root=evidence_root,
    )
    return {
        "carrier": acquired.carrier,
        "candidateId": candidate_id,
        "evidenceRootRef": ".",
        "ref": capsule_ref,
        "digest": capsule["capsuleDigest"],
        "fileSha256": file_sha256(capsule_path),
    }


def _acquire_carrier(
    planned: list[dict[str, Any]],
    *,
    carrier: str,
    required: int,
    identity: Mapping[str, str],
    captured_at: str,
    evidence_root: Path,
    coverage_binding: Mapping[str, str],
    seed_selection_binding: Mapping[str, str],
    excluded_coverage_ids: set[str],
    used_content: set[str],
    rejection_counts: Counter[str],
    rejections: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], set[str], int]:
    bindings: list[dict[str, Any]] = []
    accepted_coverage_ids: set[str] = set()
    attempted = 0
    for row in planned:
        if len(bindings) >= required:
            break
        coverage_id = str(row.get("coverageEntityIdentity") or "")
        if coverage_id in excluded_coverage_ids:
            continue
        attempted += 1
        try:
            source = row.get("source")
            source = source if isinstance(source, Mapping) else {}
            if carrier == "homepage" and source.get("sourceKind") in {
                "baidu_baike",
                "toutiao_baike",
            }:
                acquired = acquire_baike_homepage_source_ready_candidate(
                    row,
                    source_revision=identity["sourceRevision"],
                    source_digest=identity["sourceDigest"],
                    entity_catalog_digest=identity["entityCatalogDigest"],
                    captured_at=captured_at,
                )
            elif carrier == "article":
                acquired = acquire_article_site_source_ready_candidate(
                    row,
                    source_revision=identity["sourceRevision"],
                    source_digest=identity["sourceDigest"],
                    entity_catalog_digest=identity["entityCatalogDigest"],
                    captured_at=captured_at,
                )
            else:
                acquired = acquire_mediawiki_source_ready_candidate(
                    row,
                    carrier=carrier,
                    source_revision=identity["sourceRevision"],
                    source_digest=identity["sourceDigest"],
                    entity_catalog_digest=identity["entityCatalogDigest"],
                    captured_at=captured_at,
                )
            physical = _physical_content(acquired)
            if physical & used_content:
                raise MediaWikiSourceReadyRejected(
                    "body or media duplicates another accepted source-ready candidate"
                )
            binding = _write_acquired_candidate(
                acquired,
                evidence_root=evidence_root,
                identity=identity,
                captured_at=captured_at,
                coverage_binding=coverage_binding,
                seed_selection_binding=seed_selection_binding,
                seed=row["seed"],
            )
        except (MediaWikiSourceReadyRejected, HomepageArticleSourceReadyBatchError) as exc:
            reason = str(exc)
            rejection_counts[reason] += 1
            rejections.append(
                {
                    "carrier": carrier,
                    "coverageEntityIdentity": coverage_id,
                    "candidateName": str(row.get("candidateName") or ""),
                    "entityType": str(row.get("entityType") or ""),
                    "sourceKind": str(source.get("sourceKind") or ""),
                    "sourceUrl": str(source.get("sourceUrl") or ""),
                    "reason": reason,
                }
            )
            continue
        bindings.append(binding)
        accepted_coverage_ids.add(coverage_id)
        used_content.update(physical)
    return bindings, accepted_coverage_ids, attempted


def acquire_homepage_article_source_ready_batch(
    *,
    coverage_run_dir: Path,
    output_root: Path,
    source_set_id: str,
    target_scale: str,
    source_revision: str,
    source_digest: str,
    entity_catalog_digest: str,
    captured_at: str,
    homepage_count: int,
    article_count: int,
    seed_selection: Path,
) -> dict[str, Any]:
    """Acquire exact source-ready counts and freeze a physical batch manifest."""

    if not _SOURCE_SET_ID.fullmatch(source_set_id):
        raise HomepageArticleSourceReadyAcquisitionError(
            SOURCE_INVALID_EVIDENCE, ["sourceSetId is invalid"]
        )
    if target_scale not in {"M100", "M1000", "M10000"}:
        raise HomepageArticleSourceReadyAcquisitionError(
            SOURCE_INVALID_EVIDENCE, ["targetScale is invalid"]
        )
    if homepage_count < 0 or article_count < 0 or not (homepage_count or article_count):
        raise HomepageArticleSourceReadyAcquisitionError(
            SOURCE_INVALID_EVIDENCE,
            [
                "homepage/article candidate counts must be non-negative "
                "and at least one carrier must be active"
            ],
        )
    identity = _identity(
        source_revision=source_revision,
        source_digest=source_digest,
        entity_catalog_digest=entity_catalog_digest,
    )
    evidence_root = (
        output_root.expanduser().resolve()
        / "homepage-article-source-ready"
        / target_scale.lower()
        / source_set_id
    )
    source_run = coverage_run_dir.expanduser().resolve()
    projection = _project_coverage_run(source_run, identity=identity)
    planned = [
        dict(row)
        for row in projection["plannedCandidates"]
        if isinstance(row, Mapping)
    ]
    seed_source = seed_selection.expanduser().absolute()
    selection = load_homepage_article_seed_selection(seed_source)
    initial_seed_file_sha256 = file_sha256(seed_source)
    selected_by_carrier, seed_exclusions = select_fresh_coverage_candidates(
        selection, planned
    )
    if seed_exclusions:
        raise HomepageArticleSourceReadyAcquisitionError(
            SOURCE_INVALID_EVIDENCE,
            [
                "seed selection is not an exact member of current ready+frozen coverage: "
                + ", ".join(str(row["seedId"]) for row in seed_exclusions)
            ],
        )
    matched_counts = {
        "homepage": len(selected_by_carrier["homepage"]),
        "article": len(selected_by_carrier["article"]),
    }
    if matched_counts["homepage"] < homepage_count or matched_counts["article"] < article_count:
        raise HomepageArticleSourceReadyAcquisitionError(
            SOURCE_INVALID_EVIDENCE,
            [
                "exact seed coverage is below requested acquisition counts: "
                f"required={homepage_count}/{article_count} "
                f"matched={matched_counts['homepage']}/{matched_counts['article']}"
            ],
        )
    observed_projection = _project_coverage_run(source_run, identity=identity)
    observed_selection = load_homepage_article_seed_selection(seed_source)
    if (
        observed_projection != projection
        or observed_selection != selection
        or file_sha256(seed_source) != initial_seed_file_sha256
    ):
        raise HomepageArticleSourceReadyAcquisitionError(
            SOURCE_INVALID_EVIDENCE,
            ["coverage or seed bytes changed during write preflight"],
        )
    projection = _copy_coverage_run(
        source_run,
        evidence_root=evidence_root,
        identity=identity,
        expected_projection=projection,
    )
    projection_path = evidence_root / "coverage-projection.json"
    coverage_binding = {
        "ref": "coverage-projection.json",
        "digest": str(projection["projectionDigest"]),
        "fileSha256": file_sha256(projection_path),
    }
    seed_ref = "seed-selection.json"
    seed_path = evidence_root / seed_ref
    write_create_once_bytes(seed_path, seed_source.read_bytes())
    seed_binding = {
        "ref": seed_ref,
        "digest": str(selection["selectionDigest"]),
        "fileSha256": file_sha256(seed_path),
    }
    active_selected = {
        "homepage": selected_by_carrier["homepage"] if homepage_count else [],
        "article": selected_by_carrier["article"] if article_count else [],
    }
    planned = [*active_selected["homepage"], *active_selected["article"]]
    used_content: set[str] = set()
    rejection_counts: Counter[str] = Counter()
    rejections: list[dict[str, str]] = []
    homepage, homepage_coverage, homepage_attempted = _acquire_carrier(
        active_selected["homepage"],
        carrier="homepage",
        required=homepage_count,
        identity=identity,
        captured_at=captured_at,
        evidence_root=evidence_root,
        coverage_binding=coverage_binding,
        seed_selection_binding=seed_binding,
        excluded_coverage_ids=set(),
        used_content=used_content,
        rejection_counts=rejection_counts,
        rejections=rejections,
    )
    article, _, article_attempted = _acquire_carrier(
        active_selected["article"],
        carrier="article",
        required=article_count,
        identity=identity,
        captured_at=captured_at,
        evidence_root=evidence_root,
        coverage_binding=coverage_binding,
        seed_selection_binding=seed_binding,
        excluded_coverage_ids=set(),
        used_content=used_content,
        rejection_counts=rejection_counts,
        rejections=rejections,
    )
    shortfall = len(homepage) != homepage_count or len(article) != article_count
    if shortfall and (
        (homepage_count > 0 and not homepage)
        or (article_count > 0 and not article)
    ):
        reason_summary = ", ".join(
            f"{reason}={count}"
            for reason, count in rejection_counts.most_common(8)
        )
        raise HomepageArticleSourceReadyAcquisitionError(
            SOURCE_POOL_SHORTFALL,
            [
                (
                    "homepage/article source-ready acquisition shortfall: "
                    f"required={homepage_count}/{article_count} "
                    f"actual={len(homepage)}/{len(article)}; {reason_summary}"
                )
            ],
        )
    capsule_bindings = sorted(
        [*homepage, *article],
        key=lambda row: (str(row["carrier"]), str(row["candidateId"])),
    )
    stable_batch: dict[str, Any] = {
        "schema": "quwoquan_data.homepage_article_source_ready_batch",
        "sourceSetId": source_set_id,
        "targetScale": target_scale,
        **identity,
        "createdAt": captured_at,
        "coverageProjection": coverage_binding,
        "seedSelection": seed_binding,
        "candidateCapsules": capsule_bindings,
        "counts": {"homepage": len(homepage), "article": len(article)},
    }
    batch = {**stable_batch, "sourceSetDigest": canonical_digest(stable_batch)}
    batch_ref = f"batches/{batch['sourceSetDigest'].removeprefix('sha256:')}.json"
    batch_path = evidence_root / batch_ref
    write_create_once_json(batch_path, batch)
    load_homepage_article_source_ready_batch(
        batch_path,
        evidence_root=evidence_root,
    )
    stable_report: dict[str, Any] = {
        "schema": "quwoquan_data.homepage_article_source_ready_acquisition_report",
        "sourceSetId": source_set_id,
        "targetScale": target_scale,
        **identity,
        "startedAt": captured_at,
        "completedAt": captured_at,
        "coverageProjection": coverage_binding,
        "seedSelection": seed_binding,
        "seedIntersection": {
            "homepageMatched": len(selected_by_carrier["homepage"]),
            "articleMatched": len(selected_by_carrier["article"]),
            "excluded": len(seed_exclusions),
        },
        "seedExclusions": seed_exclusions,
        "status": "source_pool_shortfall" if shortfall else "copy_ready",
        "counts": {
            "planned": len(planned),
            "attempted": homepage_attempted + article_attempted,
            "homepageRequired": homepage_count,
            "articleRequired": article_count,
            "homepageAccepted": len(homepage),
            "articleAccepted": len(article),
            "homepageShortfall": max(0, homepage_count - len(homepage)),
            "articleShortfall": max(0, article_count - len(article)),
            "rejected": sum(rejection_counts.values()),
        },
        "rejectionReasonCounts": dict(sorted(rejection_counts.items())),
        "rejections": sorted(
            rejections,
            key=lambda row: (
                row["carrier"], row["coverageEntityIdentity"], row["reason"]
            ),
        ),
        "batchRef": batch_ref,
        "sourceSetDigest": batch["sourceSetDigest"],
    }
    report = {
        **stable_report,
        "reportDigest": canonical_digest(stable_report),
    }
    assert_valid(
        report,
        "source",
        "homepage_article_source_ready_acquisition_report",
        label="homepage/article source-ready acquisition report",
    )
    report_ref = f"reports/{report['reportDigest'].removeprefix('sha256:')}.json"
    report_path = evidence_root / report_ref
    write_create_once_json(report_path, report)
    result = {
        "schema": "quwoquan_data.homepage_article_source_ready_acquisition_result",
        "status": report["status"],
        "evidenceRoot": str(evidence_root),
        "sourceReadyManifest": str(batch_path),
        "sourceSetDigest": batch["sourceSetDigest"],
        "reportRef": report_ref,
        "reportDigest": report["reportDigest"],
        "counts": batch["counts"],
    }
    if shortfall:
        reason_summary = ", ".join(
            f"{reason}={count}"
            for reason, count in rejection_counts.most_common(8)
        )
        raise HomepageArticleSourceReadyAcquisitionError(
            SOURCE_POOL_SHORTFALL,
            [
                (
                    "homepage/article source-ready acquisition shortfall: "
                    f"required={homepage_count}/{article_count} "
                    f"actual={len(homepage)}/{len(article)}; {reason_summary}"
                )
            ],
            checkpoint=result,
        )
    return result


__all__ = [
    "SOURCE_INVALID_EVIDENCE",
    "SOURCE_POOL_SHORTFALL",
    "HomepageArticleSourceReadyAcquisitionError",
    "acquire_homepage_article_source_ready_batch",
]
