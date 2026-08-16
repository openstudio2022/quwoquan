"""Canonical coverage-to-capsule acquisition for homepage/article source pools."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from core.runtime_policy import active_runtime_policy
from core.schema import assert_valid
from governance.coverage.coverage_source_ready_catalog_projection import (
    project_coverage_source_ready_catalog_inputs,
)

from content.source.research.homepage_article_seed_selection import (
    load_homepage_article_seed_selection,
    select_fresh_coverage_candidates,
)
from content.source.research.homepage_article_source_ready_article_site import (
    acquire_article_site_source_ready_candidate,
)
from content.source.research.homepage_article_source_ready_baike import (
    acquire_baike_homepage_source_ready_candidate,
)
from content.source.research.homepage_article_source_ready_batch import (
    HomepageArticleSourceReadyBatchError,
    load_homepage_article_source_ready_batch,
    validate_source_ready_candidate_capsule,
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

_EXTRACTED_DEPENDENCIES = (
    HomepageArticleSourceReadyBatchError,
    MediaWikiSourceReadyRejected,
    assert_source_ready_evidence_matches_capsule,
    validate_source_ready_acquisition_evidence,
    validate_source_ready_candidate_capsule,
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
        normalized = tuple(str(issue).strip() for issue in issues if str(issue).strip())
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
    if any(
        not re.fullmatch(r"sha256:[0-9a-f]{64}", value) for value in values.values()
    ):
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
    from content.source.research.homepage_article_source_ready_execution import (
        write_acquired_candidate,
    )

    return write_acquired_candidate(
        acquired,
        evidence_root=evidence_root,
        identity=identity,
        captured_at=captured_at,
        coverage_binding=coverage_binding,
        seed_selection_binding=seed_selection_binding,
        seed=seed,
    )


def _acquire_carrier(
    planned: list[dict[str, Any]],
    *,
    carrier: str,
    required: int,
    acquisition_concurrency: int,
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
    from content.source.research.homepage_article_source_ready_execution import (
        acquire_carrier,
    )

    return acquire_carrier(
        planned,
        carrier=carrier,
        required=required,
        acquisition_concurrency=acquisition_concurrency,
        identity=identity,
        captured_at=captured_at,
        evidence_root=evidence_root,
        coverage_binding=coverage_binding,
        seed_selection_binding=seed_selection_binding,
        excluded_coverage_ids=excluded_coverage_ids,
        used_content=used_content,
        rejection_counts=rejection_counts,
        rejections=rejections,
        acquire_article_site_source_ready_candidate=(
            acquire_article_site_source_ready_candidate
        ),
        acquire_baike_homepage_source_ready_candidate=(
            acquire_baike_homepage_source_ready_candidate
        ),
        acquire_mediawiki_source_ready_candidate=(
            acquire_mediawiki_source_ready_candidate
        ),
        physical_content=_physical_content,
    )


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
    acquisition_concurrency: int | None = None,
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
                (
                    "homepage/article candidate counts must be non-negative "
                    "and at least one carrier must be active"
                )
            ],
        )
    effective_acquisition_concurrency = (
        active_runtime_policy().download_concurrency
        if acquisition_concurrency is None
        else acquisition_concurrency
    )
    if not 1 <= effective_acquisition_concurrency <= 32:
        raise HomepageArticleSourceReadyAcquisitionError(
            SOURCE_INVALID_EVIDENCE,
            ["acquisition concurrency must be between 1 and 32"],
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
        dict(row) for row in projection["plannedCandidates"] if isinstance(row, Mapping)
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
    if (
        matched_counts["homepage"] < homepage_count
        or matched_counts["article"] < article_count
    ):
        raise HomepageArticleSourceReadyAcquisitionError(
            SOURCE_INVALID_EVIDENCE,
            [
                (
                    "exact seed coverage is below requested acquisition counts: "
                    f"required={homepage_count}/{article_count} "
                    f"matched={matched_counts['homepage']}/{matched_counts['article']}"
                )
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
    homepage, _homepage_coverage, homepage_attempted = _acquire_carrier(
        active_selected["homepage"],
        carrier="homepage",
        required=homepage_count,
        acquisition_concurrency=effective_acquisition_concurrency,
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
        acquisition_concurrency=effective_acquisition_concurrency,
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
        (homepage_count > 0 and not homepage) or (article_count > 0 and not article)
    ):
        reason_summary = ", ".join(
            f"{reason}={count}" for reason, count in rejection_counts.most_common(8)
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
                row["carrier"],
                row["coverageEntityIdentity"],
                row["reason"],
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
            f"{reason}={count}" for reason, count in rejection_counts.most_common(8)
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
