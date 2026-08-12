"""Project coverage source-readiness evidence to the catalog-builder boundary.

Coverage qualification proves only an entity/source match.  It does not prove
that article body bytes, anonymous access, or media were acquired.  This
read-only projection therefore binds the exact coverage files and exposes the
remaining typed gaps without manufacturing homepage/article catalog inputs.
"""
from __future__ import annotations

import hashlib
import json
import re
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from core.baike_source_contract import (
    HOMEPAGE_SOURCE_POLICY_REVISION,
    source_identity_matches_contract,
)
from core.schema import assert_valid
from governance.coverage.source_readiness_candidates import (
    canonical_source_ready_entity_ref,
    canonical_source_ready_name,
)


SOURCE_POOL_SHORTFALL = "DATA.SOURCE.POOL_SHORTFALL"
SOURCE_INVALID_EVIDENCE = "DATA.SOURCE.INVALID_EVIDENCE"
PROJECTION_SCHEMA = (
    "quwoquan_data.coverage_source_ready_catalog_projection"
)
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


class CoverageSourceReadyProjectionError(ValueError):
    """Typed blocker at the coverage-to-catalog boundary."""

    def __init__(self, code: str, issues: Sequence[object]) -> None:
        normalized = tuple(
            str(issue).strip() for issue in issues if str(issue).strip()
        )
        if not normalized:
            raise ValueError("coverage projection error requires an issue")
        self.code = code
        self.issues = normalized
        super().__init__(f"{code}: " + "; ".join(normalized))


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _regular_file(run_dir: Path, name: str) -> Path:
    try:
        run_mode = run_dir.lstat().st_mode
    except OSError as exc:
        raise CoverageSourceReadyProjectionError(
            SOURCE_INVALID_EVIDENCE,
            [f"coverage run directory is missing: {run_dir}"],
        ) from exc
    if stat.S_ISLNK(run_mode) or not stat.S_ISDIR(run_mode):
        raise CoverageSourceReadyProjectionError(
            SOURCE_INVALID_EVIDENCE,
            ["coverage run root must be a real directory"],
        )
    path = run_dir / name
    try:
        mode = path.lstat().st_mode
    except OSError as exc:
        raise CoverageSourceReadyProjectionError(
            SOURCE_INVALID_EVIDENCE,
            [f"coverage evidence file is missing: {name}"],
        ) from exc
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise CoverageSourceReadyProjectionError(
            SOURCE_INVALID_EVIDENCE,
            [f"coverage evidence must be a regular non-symlink file: {name}"],
        )
    return path


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CoverageSourceReadyProjectionError(
            SOURCE_INVALID_EVIDENCE,
            [f"{label} is not readable JSON"],
        ) from exc
    if not isinstance(value, dict):
        raise CoverageSourceReadyProjectionError(
            SOURCE_INVALID_EVIDENCE,
            [f"{label} must be one JSON object"],
        )
    return value


def _read_ndjson(path: Path, *, label: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    line_number = 0
    try:
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise TypeError("row must be an object")
                rows.append(value)
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        raise CoverageSourceReadyProjectionError(
            SOURCE_INVALID_EVIDENCE,
            [f"{label} is invalid at row {line_number}"],
        ) from exc
    return rows


def _identity_values(
    *,
    source_revision: str,
    source_digest: str,
    entity_catalog_digest: str,
) -> tuple[str, str, str]:
    values = (source_revision, source_digest, entity_catalog_digest)
    if any(not _SHA256.fullmatch(str(value or "")) for value in values):
        raise CoverageSourceReadyProjectionError(
            SOURCE_INVALID_EVIDENCE,
            ["sourceRevision/sourceDigest/entityCatalogDigest must be sha256"],
        )
    return values


def _verify_output_ref(run_dir: Path, raw: object, expected_name: str) -> None:
    path = Path(str(raw or ""))
    if not path.is_absolute():
        path = run_dir / path
    try:
        matches = path.resolve(strict=True) == (run_dir / expected_name).resolve(
            strict=True
        )
    except OSError as exc:
        raise CoverageSourceReadyProjectionError(
            SOURCE_INVALID_EVIDENCE,
            [f"coverage report output is missing: {expected_name}"],
        ) from exc
    if not matches:
        raise CoverageSourceReadyProjectionError(
            SOURCE_INVALID_EVIDENCE,
            [f"coverage report output escapes this run: {expected_name}"],
        )


def _validate_run_contract(
    *,
    run_dir: Path,
    manifest: Mapping[str, Any],
    report: Mapping[str, Any],
    source_digest: str,
) -> None:
    try:
        assert_valid(
            dict(manifest),
            "governance",
            "source_readiness_manifest",
            label="coverage source-readiness manifest",
        )
        assert_valid(
            dict(report),
            "governance",
            "source_readiness_report",
            label="coverage source-readiness report",
        )
    except ValueError as exc:
        raise CoverageSourceReadyProjectionError(
            SOURCE_INVALID_EVIDENCE,
            [f"coverage manifest/report schema is invalid: {exc}"],
        ) from exc
    if manifest["runId"] != report["runId"]:
        raise CoverageSourceReadyProjectionError(
            SOURCE_INVALID_EVIDENCE,
            ["coverage manifest/report runId drift"],
        )
    for field in ("inputDigest", "sources", "sourceDigest"):
        if manifest[field] != report[field]:
            raise CoverageSourceReadyProjectionError(
                SOURCE_INVALID_EVIDENCE,
                [f"coverage manifest/report {field} drift"],
            )
    observed_digest = str((manifest["sourceDigest"] or {}).get("digest") or "")
    if observed_digest != source_digest:
        raise CoverageSourceReadyProjectionError(
            SOURCE_INVALID_EVIDENCE,
            ["coverage sourceDigest differs from catalog source identity"],
        )
    outputs = report["outputs"]
    _verify_output_ref(run_dir, outputs["ready"], "source_ready.ndjson")
    _verify_output_ref(
        run_dir,
        outputs["inconclusive"],
        "source_inconclusive.ndjson",
    )
    _verify_output_ref(
        run_dir,
        outputs["frozenTargets"],
        "frozen_targets.ndjson",
    )


def _planned_candidate(row: Mapping[str, Any]) -> dict[str, Any]:
    try:
        assert_valid(
            dict(row),
            "governance",
            "source_ready_candidate",
            label="coverage frozen target",
        )
    except ValueError as exc:
        raise CoverageSourceReadyProjectionError(
            SOURCE_INVALID_EVIDENCE,
            [f"coverage frozen target schema is invalid: {exc}"],
        ) from exc
    if row.get("qualified") is not True or not isinstance(row.get("selection"), Mapping):
        raise CoverageSourceReadyProjectionError(
            SOURCE_INVALID_EVIDENCE,
            ["every frozen target must be qualified and selected"],
        )
    candidate = row["candidate"]
    evidence = row["evidence"]
    identity_key = str(row["identityKey"])
    source_kind = str(evidence["sourceKind"])
    extractor = str(evidence["extractor"])
    source_url = str(evidence["canonicalUrl"])
    resolved_title = str(evidence["resolvedTitle"]).strip()
    if not resolved_title:
        raise CoverageSourceReadyProjectionError(
            SOURCE_INVALID_EVIDENCE,
            [f"{identity_key}: resolved source title is empty"],
        )
    entity_type = str(row["selection"]["coverageCell"]["entityType"])
    try:
        canonical_name = canonical_source_ready_name(dict(candidate))
        canonical_entity_ref = canonical_source_ready_entity_ref(
            dict(candidate), entity_type=entity_type
        )
    except ValueError as exc:
        raise CoverageSourceReadyProjectionError(
            SOURCE_INVALID_EVIDENCE,
            [f"{identity_key}: canonical entity ref cannot be derived: {exc}"],
        ) from exc
    if not source_identity_matches_contract(
        source_kind=source_kind,
        url=source_url,
        extractor=extractor,
        policy_revision=HOMEPAGE_SOURCE_POLICY_REVISION,
    ):
        raise CoverageSourceReadyProjectionError(
            SOURCE_INVALID_EVIDENCE,
            [f"{identity_key}: source identity is outside the encyclopedia closed set"],
        )
    common_missing = [
        "anonymousPublicAccessProof",
        "bodyContentDigest",
        "bodyEvidenceRef",
        "canonicalEntityRef",
    ]
    homepage_missing = sorted([*common_missing, "heroAssetEvidence"])
    article_missing = sorted(
        [*common_missing, "articleBodyImageEvidence", "articleCoverEvidence"]
    )
    return {
        "coverageEntityIdentity": identity_key,
        "canonicalEntityRef": canonical_entity_ref,
        "candidateName": canonical_name,
        "province": str(candidate["province"]),
        "city": str(candidate["city"]),
        "district": str(candidate["district"]),
        "entityType": entity_type,
        "source": {
            "sourceKind": source_kind,
            "extractor": extractor,
            "sourceUrl": source_url,
            "resolvedTitle": resolved_title,
            "observedAt": str(row["qualifiedAt"]),
        },
        "coverageRecordDigest": _canonical_digest(row),
        "homepage": {
            "ready": False,
            "blockerCode": SOURCE_POOL_SHORTFALL,
            "missingEvidence": homepage_missing,
        },
        "article": {
            "ready": False,
            "blockerCode": SOURCE_POOL_SHORTFALL,
            "missingEvidence": article_missing,
        },
    }


def project_coverage_source_ready_catalog_inputs(
    *,
    run_dir: Path,
    source_revision: str,
    source_digest: str,
    entity_catalog_digest: str,
) -> dict[str, Any]:
    """Bind a coverage run and expose honest catalog-builder readiness."""

    identity = _identity_values(
        source_revision=source_revision,
        source_digest=source_digest,
        entity_catalog_digest=entity_catalog_digest,
    )
    root = run_dir.absolute()
    manifest_path = _regular_file(root, "manifest.json")
    report_path = _regular_file(root, "report.json")
    ready_path = _regular_file(root, "source_ready.ndjson")
    inconclusive_path = _regular_file(root, "source_inconclusive.ndjson")
    frozen_path = _regular_file(root, "frozen_targets.ndjson")
    manifest = _read_json(manifest_path, label="manifest.json")
    report = _read_json(report_path, label="report.json")
    _validate_run_contract(
        run_dir=root,
        manifest=manifest,
        report=report,
        source_digest=source_digest,
    )
    ready_rows = _read_ndjson(ready_path, label="source_ready.ndjson")
    rows = _read_ndjson(frozen_path, label="frozen_targets.ndjson")
    ready_by_identity: dict[str, dict[str, Any]] = {}
    for ready_row in ready_rows:
        try:
            assert_valid(
                ready_row,
                "governance",
                "source_ready_candidate",
                label="coverage source-ready row",
            )
        except ValueError as exc:
            raise CoverageSourceReadyProjectionError(
                SOURCE_INVALID_EVIDENCE,
                [f"coverage source-ready row schema is invalid: {exc}"],
            ) from exc
        identity_key = str(ready_row.get("identityKey") or "")
        if not identity_key or identity_key in ready_by_identity:
            raise CoverageSourceReadyProjectionError(
                SOURCE_INVALID_EVIDENCE,
                ["coverage source-ready rows contain duplicate entity identity"],
            )
        ready_by_identity[identity_key] = ready_row
    for frozen_row in rows:
        identity_key = str(frozen_row.get("identityKey") or "")
        ready_form = {key: value for key, value in frozen_row.items() if key != "selection"}
        if ready_by_identity.get(identity_key) != ready_form:
            raise CoverageSourceReadyProjectionError(
                SOURCE_INVALID_EVIDENCE,
                [f"{identity_key}: frozen target is not an exact source-ready member"],
            )
    planned = [_planned_candidate(row) for row in rows]
    manifest_required = manifest.get("requiredEntityRefs")
    report_required = report.get("requiredEntityRefs")
    if (manifest_required is None) != (report_required is None):
        raise CoverageSourceReadyProjectionError(
            SOURCE_INVALID_EVIDENCE,
            ["coverage manifest/report requiredEntityRefs mode drift"],
        )
    if manifest_required is not None:
        required_refs = list(manifest_required)
        actual_refs = [row["canonicalEntityRef"] for row in planned]
        if list(report_required) != required_refs:
            raise CoverageSourceReadyProjectionError(
                SOURCE_INVALID_EVIDENCE,
                ["coverage manifest/report requiredEntityRefs drift"],
            )
        if (
            list(report.get("frozenEntityRefs") or []) != required_refs
            or list(report.get("missingRequiredEntityRefs") or [])
            or actual_refs != required_refs
        ):
            raise CoverageSourceReadyProjectionError(
                SOURCE_INVALID_EVIDENCE,
                ["coverage exact frozen canonical refs are incomplete or reordered"],
            )
    else:
        planned.sort(key=lambda item: item["coverageEntityIdentity"])
    identities = [item["coverageEntityIdentity"] for item in planned]
    if len(identities) != len(set(identities)):
        raise CoverageSourceReadyProjectionError(
            SOURCE_INVALID_EVIDENCE,
            ["coverage frozen targets contain duplicate entity identity"],
        )
    frozen_by_province = report["frozenByProvince"]
    if sum(int(value) for value in frozen_by_province.values()) != len(planned):
        raise CoverageSourceReadyProjectionError(
            SOURCE_INVALID_EVIDENCE,
            ["coverage report frozen count differs from frozen target bytes"],
        )
    bindings = {
        "manifest": {
            "ref": "manifest.json",
            "documentDigest": _canonical_digest(manifest),
            "fileSha256": _file_sha256(manifest_path),
        },
        "report": {
            "ref": "report.json",
            "documentDigest": _canonical_digest(report),
            "fileSha256": _file_sha256(report_path),
        },
        "sourceReady": {
            "ref": "source_ready.ndjson",
            "fileSha256": _file_sha256(ready_path),
        },
        "sourceInconclusive": {
            "ref": "source_inconclusive.ndjson",
            "fileSha256": _file_sha256(inconclusive_path),
        },
        "frozenTargets": {
            "ref": "frozen_targets.ndjson",
            "recordSetDigest": _canonical_digest(rows),
            "fileSha256": _file_sha256(frozen_path),
        },
    }
    count = len(planned)
    stable = {
        "schema": PROJECTION_SCHEMA,
        "runId": str(manifest["runId"]),
        "sourceRevision": identity[0],
        "sourceDigest": identity[1],
        "entityCatalogDigest": identity[2],
        "coverageBindings": bindings,
        "coverageReceiptStatus": "missing",
        "counts": {
            "plannedEntityCount": count,
            "homepage": {
                "plannedCount": count,
                "readyCount": 0,
                "mediaMissingCount": count,
            },
            "article": {
                "plannedCount": count,
                "readyCount": 0,
                "mediaMissingCount": count,
            },
        },
        "homepageCatalogBuilderInputs": [],
        "articleCatalogBuilderInputs": [],
        "plannedCandidates": planned,
        "blockers": [
            {
                "code": SOURCE_POOL_SHORTFALL,
                "reason": "coverage qualification has no immutable body, public-access, or media evidence",
                "affectedEntityCount": count,
            }
        ],
    }
    projection = {**stable, "projectionDigest": _canonical_digest(stable)}
    assert_valid(
        projection,
        "governance",
        "coverage_source_ready_catalog_projection",
        label="coverage source-ready catalog projection",
    )
    return projection


def require_catalog_builder_inputs(projection: Mapping[str, Any]) -> None:
    """Fail closed until both carrier builder input sets contain real evidence."""

    if not projection.get("homepageCatalogBuilderInputs") or not projection.get(
        "articleCatalogBuilderInputs"
    ):
        raise CoverageSourceReadyProjectionError(
            SOURCE_POOL_SHORTFALL,
            ["coverage source-ready rows lack catalog-builder body/access/media evidence"],
        )


__all__ = [
    "CoverageSourceReadyProjectionError",
    "project_coverage_source_ready_catalog_inputs",
    "require_catalog_builder_inputs",
]
