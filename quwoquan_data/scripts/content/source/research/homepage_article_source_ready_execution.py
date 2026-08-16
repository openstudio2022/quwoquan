"""Execution implementation for homepage/article source-ready acquisition."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

from content.source.research.homepage_article_source_ready_acquisition import (
    SOURCE_INVALID_EVIDENCE,
    AcquiredSourceReadyCandidate,
    HomepageArticleSourceReadyAcquisitionError,
    HomepageArticleSourceReadyBatchError,
    MediaWikiSourceReadyRejected,
    assert_source_ready_evidence_matches_capsule,
    canonical_digest,
    file_sha256,
    validate_source_ready_acquisition_evidence,
    validate_source_ready_candidate_capsule,
    write_create_once_bytes,
    write_create_once_json,
)


def write_acquired_candidate(
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
        "publishMediaMode": str(candidate.get("publishMediaMode") or "illustrated"),
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


def acquire_carrier(
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
    acquire_article_site_source_ready_candidate: Any,
    acquire_baike_homepage_source_ready_candidate: Any,
    acquire_mediawiki_source_ready_candidate: Any,
    physical_content: Any,
) -> tuple[list[dict[str, Any]], set[str], int]:
    bindings: list[dict[str, Any]] = []
    accepted_coverage_ids: set[str] = set()
    attempted = 0

    eligible = [
        row
        for row in planned
        if str(row.get("coverageEntityIdentity") or "") not in excluded_coverage_ids
    ]

    existing_by_seed: dict[str, tuple[dict[str, Any], set[str], str]] = {}
    capsule_root = evidence_root / "capsules" / carrier
    if capsule_root.is_dir():
        for capsule_path in sorted(capsule_root.iterdir()):
            if capsule_path.is_symlink() or not capsule_path.is_file():
                raise HomepageArticleSourceReadyAcquisitionError(
                    SOURCE_INVALID_EVIDENCE,
                    [f"existing {carrier} capsule must be a regular file"],
                )
            try:
                raw_capsule = json.loads(capsule_path.read_text(encoding="utf-8"))
                capsule = validate_source_ready_candidate_capsule(
                    raw_capsule,
                    evidence_root=evidence_root,
                )
                provenance = capsule["provenance"]
                materialization = capsule["materialization"]
                seed_id = str(provenance["seedId"])
                coverage_id = str(provenance["coverageKey"]["coverageEntityIdentity"])
                if (
                    capsule["carrier"] != carrier
                    or any(capsule[key] != value for key, value in identity.items())
                    or provenance["seedSelectionDigest"]
                    != seed_selection_binding["digest"]
                ):
                    raise ValueError("existing capsule identity binding drift")
                physical = {
                    str(materialization["body"]["contentSha256"]),
                    *(str(row["contentSha256"]) for row in materialization["media"]),
                }
                binding = {
                    "carrier": carrier,
                    "candidateId": str(capsule["candidate"]["candidateId"]),
                    "evidenceRootRef": ".",
                    "ref": capsule_path.relative_to(evidence_root).as_posix(),
                    "digest": str(capsule["capsuleDigest"]),
                    "fileSha256": file_sha256(capsule_path),
                }
            except (
                HomepageArticleSourceReadyBatchError,
                KeyError,
                OSError,
                TypeError,
                ValueError,
                json.JSONDecodeError,
            ) as exc:
                raise HomepageArticleSourceReadyAcquisitionError(
                    SOURCE_INVALID_EVIDENCE,
                    [f"existing {carrier} capsule is invalid: {exc}"],
                ) from exc
            if seed_id in existing_by_seed:
                # Historical waves may have frozen more than one valid capsule
                # for the same seed (for example when the source page changed
                # between interrupted runs).  An idempotent same-parameter
                # resume keeps the deterministic first capsule (sorted by
                # digest file name) and skips the extras instead of rejecting
                # the whole batch; each duplicate has already passed full
                # capsule validation above.
                continue
            existing_by_seed[seed_id] = (binding, physical, coverage_id)

    def _seed_id(row: Mapping[str, Any]) -> str:
        seed = row.get("seed")
        return str(seed.get("seedId") or "") if isinstance(seed, Mapping) else ""

    for row in eligible:
        if len(bindings) >= required:
            break
        existing = existing_by_seed.get(_seed_id(row))
        if existing is None:
            continue
        binding, physical, coverage_id = existing
        if physical & used_content:
            raise HomepageArticleSourceReadyAcquisitionError(
                SOURCE_INVALID_EVIDENCE,
                [f"existing {carrier} capsule duplicates accepted physical content"],
            )
        bindings.append(binding)
        accepted_coverage_ids.add(coverage_id)
        used_content.update(physical)
        attempted += 1

    remaining = required - len(bindings)
    if remaining <= 0:
        return bindings, accepted_coverage_ids, attempted

    def acquire(row: dict[str, Any]) -> AcquiredSourceReadyCandidate:
        source = row.get("source")
        source = source if isinstance(source, Mapping) else {}
        if carrier == "homepage" and source.get("sourceKind") in {
            "baidu_baike",
            "toutiao_baike",
        }:
            return acquire_baike_homepage_source_ready_candidate(
                row,
                source_revision=identity["sourceRevision"],
                source_digest=identity["sourceDigest"],
                entity_catalog_digest=identity["entityCatalogDigest"],
                captured_at=captured_at,
            )
        if carrier == "article":
            try:
                return acquire_article_site_source_ready_candidate(
                    row,
                    source_revision=identity["sourceRevision"],
                    source_digest=identity["sourceDigest"],
                    entity_catalog_digest=identity["entityCatalogDigest"],
                    captured_at=captured_at,
                )
            except MediaWikiSourceReadyRejected as frontier_rejection:
                # The governed site frontier stays first choice.  When every
                # frontier site produced nothing, a coverage-qualified public
                # Wikipedia detail page is itself an admitted article source
                # profile (`wikipedia_zh`), so the exact seed source falls
                # back to the MediaWiki producer instead of losing the seed.
                if source.get("sourceKind") != "wikipedia":
                    raise
                try:
                    return acquire_mediawiki_source_ready_candidate(
                        row,
                        carrier="article",
                        source_revision=identity["sourceRevision"],
                        source_digest=identity["sourceDigest"],
                        entity_catalog_digest=identity["entityCatalogDigest"],
                        captured_at=captured_at,
                    )
                except MediaWikiSourceReadyRejected as wikipedia_rejection:
                    raise MediaWikiSourceReadyRejected(
                        f"{frontier_rejection}; wikipedia fallback: "
                        f"{wikipedia_rejection}"
                    ) from wikipedia_rejection
        return acquire_mediawiki_source_ready_candidate(
            row,
            carrier=carrier,
            source_revision=identity["sourceRevision"],
            source_digest=identity["sourceDigest"],
            entity_catalog_digest=identity["entityCatalogDigest"],
            captured_at=captured_at,
        )

    # An idempotent resume must retry every seed that has no frozen capsule
    # yet, including seeds rejected by earlier runs: producer fixes between
    # resumes are exactly what makes a previously rejected source acquirable.
    # Skipping is therefore keyed on capsule existence, never on list position.
    pending_rows = [row for row in eligible if _seed_id(row) not in existing_by_seed]
    executor = ThreadPoolExecutor(max_workers=acquisition_concurrency)
    futures: list[tuple[dict[str, Any], Future[AcquiredSourceReadyCandidate]]] = [
        (row, executor.submit(acquire, row)) for row in pending_rows[:remaining]
    ]
    next_candidate = len(futures)
    future_index = 0
    try:
        while future_index < len(futures) and len(bindings) < required:
            row, future = futures[future_index]
            future_index += 1
            attempted += 1
            rejected = False
            coverage_id = str(row.get("coverageEntityIdentity") or "")
            source = row.get("source")
            source = source if isinstance(source, Mapping) else {}
            try:
                acquired = future.result()
                physical = physical_content(acquired)
                if physical & used_content:
                    raise MediaWikiSourceReadyRejected(
                        "body or media duplicates another accepted source-ready candidate"
                    )
                binding = write_acquired_candidate(
                    acquired,
                    evidence_root=evidence_root,
                    identity=identity,
                    captured_at=captured_at,
                    coverage_binding=coverage_binding,
                    seed_selection_binding=seed_selection_binding,
                    seed=row["seed"],
                )
            except (
                MediaWikiSourceReadyRejected,
                HomepageArticleSourceReadyBatchError,
            ) as exc:
                rejected = True
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
            if rejected:
                if next_candidate < len(pending_rows):
                    replacement = pending_rows[next_candidate]
                    next_candidate += 1
                    futures.append((replacement, executor.submit(acquire, replacement)))
                continue
            bindings.append(binding)
            accepted_coverage_ids.add(coverage_id)
            used_content.update(physical)
    finally:
        executor.shutdown(wait=True, cancel_futures=True)
    return bindings, accepted_coverage_ids, attempted
