"""Identity, coverage snapshot, and capsule evidence for source acquisition."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from governance.coverage.coverage_source_ready_catalog_projection import (
    project_coverage_source_ready_catalog_inputs,
)
from content.source.research.homepage_article_source_ready_batch import (
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
)

SOURCE_POOL_SHORTFALL = "DATA.SOURCE.POOL_SHORTFALL"
SOURCE_INVALID_EVIDENCE = "DATA.SOURCE.INVALID_EVIDENCE"
SOURCE_ACQUISITION_FAILED = "DATA.SOURCE.ACQUISITION_FAILED"
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
    projector: Callable[..., dict[str, Any]] = project_coverage_source_ready_catalog_inputs,
) -> dict[str, Any]:
    try:
        initial = projector(
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
        observed = projector(
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
        "publishMediaMode": (
            "illustrated"
            if acquired.carrier == "homepage"
            else str(candidate["publishMediaMode"])
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

