"""Strongly typed, execution-owned homepage source qualification.

Coverage lists deliberately contain only stable identity and classification.  A
homepage source becomes eligible only after this execution has materialized an
object-local source catalog and its evidence bundle.  Nothing here mutates a
coverage file or invents a static readiness state.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping

from core.baike_source_contract import (
    HOMEPAGE_SOURCE_POLICY_REVISION,
    source_identity_matches_contract,
)
from core.data_issue import (
    DataIssue,
    DataIssueCode,
    DataIssueLane,
    DataIssueStage,
    DataRecoveryAction,
    data_issue,
)
from core.io import read_json, write_json
from core.paths import now_iso
from core.schema import assert_valid
from content.execution import store

from .identity import validate_execution_id
from .workspace import execution_root


QUALIFICATION_VERSION = "execution-source-qualification-v1"


class QualificationStatus(StrEnum):
    CONFIRMED = "confirmed"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class QualificationTarget:
    name: str
    entity_type: str
    geo_tag_ref: str
    aliases: tuple[str, ...]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "QualificationTarget":
        name = str(value.get("name") or "").strip()
        entity_type = str(value.get("entityType") or "").strip()
        geo_tag_ref = str(value.get("geoTagRef") or "").strip()
        aliases = tuple(
            item
            for item in (str(raw).strip() for raw in (value.get("aliases") or []))
            if item
        )
        if not name or not entity_type or not geo_tag_ref:
            raise ValueError(
                "coverage target requires name, entityType, and geoTagRef for source qualification"
            )
        return cls(name, entity_type, geo_tag_ref, aliases)

    def as_request(self) -> dict[str, object]:
        return {
            "name": self.name,
            "entityType": self.entity_type,
            "geoTagRef": self.geo_tag_ref,
            "aliases": list(self.aliases),
        }


@dataclass(frozen=True, slots=True)
class QualificationReport:
    execution_id: str
    passed: bool
    issues: tuple[DataIssue, ...]
    path: Path


def qualification_root(execution_id: str) -> Path:
    return execution_root(validate_execution_id(execution_id)) / "sources" / "qualification"


def qualification_request_path(execution_id: str) -> Path:
    return qualification_root(execution_id) / "request.json"


def qualification_result_path(execution_id: str) -> Path:
    return qualification_root(execution_id) / "result.json"


def _targets_from_spec(execution_id: str) -> tuple[QualificationTarget, ...]:
    spec = store.load_spec(execution_id)
    scope = spec.get("scope") if isinstance(spec.get("scope"), Mapping) else {}
    raw_targets = scope.get("coverageTargets") if isinstance(scope, Mapping) else []
    if not isinstance(raw_targets, list) or not raw_targets:
        raise ValueError("execution spec requires non-empty scope.coverageTargets")
    targets = tuple(
        QualificationTarget.from_mapping(row)
        for row in raw_targets
        if isinstance(row, Mapping)
    )
    if len(targets) != len(raw_targets):
        raise ValueError("coverageTargets must contain only objects")
    names = [target.name for target in targets]
    if len(set(names)) != len(names):
        raise ValueError("coverageTargets names must be unique")
    return targets


def prepare_execution_qualification(execution_id: str) -> Path:
    """Persist immutable identity-only qualification input for this execution."""
    normalized = validate_execution_id(execution_id)
    payload = {
        "contractVersion": QUALIFICATION_VERSION,
        "executionId": normalized,
        "policyRevision": HOMEPAGE_SOURCE_POLICY_REVISION,
        "createdAt": now_iso(),
        "targets": [target.as_request() for target in _targets_from_spec(normalized)],
    }
    assert_valid(
        payload,
        "execution",
        "source_qualification_request",
        label=f"source_qualification_request:{normalized}",
    )
    path = qualification_request_path(normalized)
    if path.is_file():
        existing = read_json(path)
        immutable = ("contractVersion", "executionId", "policyRevision", "targets")
        if not isinstance(existing, Mapping) or any(existing.get(key) != payload[key] for key in immutable):
            raise ValueError(
                "source qualification request input drift; create a new execution sequence"
            )
        return path
    write_json(path, payload)
    return path


def _source_catalogs_by_name(root: Path) -> dict[str, list[tuple[Path, Mapping[str, Any]]]]:
    catalogs: dict[str, list[tuple[Path, Mapping[str, Any]]]] = {}
    for path in sorted((root / "entities").glob("**/evidence/source_catalog.json")):
        try:
            payload = read_json(path)
        except (OSError, TypeError, ValueError):
            continue
        if not isinstance(payload, Mapping):
            continue
        source = payload.get("primarySource")
        if not isinstance(source, Mapping):
            continue
        name = str(source.get("entityName") or "").strip()
        if name:
            catalogs.setdefault(name, []).append((path, payload))
    return catalogs


def _catalog_issue(
    target: QualificationTarget,
    code: DataIssueCode,
    message: str,
    *,
    recovery: DataRecoveryAction = DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
    attributes: Mapping[str, object] | None = None,
) -> DataIssue:
    return data_issue(
        code,
        stage=DataIssueStage.SOURCE_GATE,
        ref=target.name,
        lane=DataIssueLane.HOMEPAGE,
        recovery=recovery,
        message=message,
        attributes=attributes,
    )


def _primary_source_projection(source: Mapping[str, Any]) -> dict[str, str]:
    return {
        "sourceKind": str(source.get("sourceKind") or ""),
        "canonicalUrl": str(source.get("canonicalUrl") or ""),
        "extractor": str(source.get("extractor") or ""),
        "snapshotHash": str(source.get("snapshotHash") or ""),
        "evidenceRef": str(source.get("evidenceRef") or ""),
    }


def _catalog_issues(
    target: QualificationTarget,
    catalog_path: Path,
    catalog: Mapping[str, Any],
) -> list[DataIssue]:
    primary = catalog.get("primarySource")
    if not isinstance(primary, Mapping):
        return [
            _catalog_issue(
                target,
                DataIssueCode.SOURCE_PRIMARY_AUTHORITY_MISSING,
                "object source catalog does not contain primarySource",
            )
        ]
    issues: list[DataIssue] = []
    if str(catalog.get("policyRevision") or "") != HOMEPAGE_SOURCE_POLICY_REVISION:
        issues.append(
            _catalog_issue(
                target,
                DataIssueCode.CONTRACT_INVALID,
                "object source catalog policy revision does not match homepage contract",
                recovery=DataRecoveryAction.STOP,
            )
        )
    if str(primary.get("entityName") or "") != target.name:
        issues.append(
            _catalog_issue(
                target,
                DataIssueCode.SOURCE_ENTITY_MISMATCH,
                "primary source entityName does not match selected coverage target",
            )
        )
    source_kind = str(primary.get("sourceKind") or "")
    canonical_url = str(primary.get("canonicalUrl") or "")
    extractor = str(primary.get("extractor") or "")
    policy_revision = str(primary.get("policyRevision") or "")
    if not source_identity_matches_contract(
        source_kind=source_kind,
        url=canonical_url,
        extractor=extractor,
        policy_revision=policy_revision,
    ):
        issues.append(
            _catalog_issue(
                target,
                DataIssueCode.SOURCE_PRIMARY_AUTHORITY_MISSING,
                "primary source is not a contract-qualified encyclopedia source",
                attributes={"sourceKind": source_kind, "extractor": extractor},
            )
        )
    evidence_ref = str(primary.get("evidenceRef") or "")
    object_root = catalog_path.parent.parent
    evidence_path = (object_root / evidence_ref).resolve()
    try:
        evidence_path.relative_to(object_root.resolve())
    except ValueError:
        issues.append(
            _catalog_issue(
                target,
                DataIssueCode.CONTRACT_INVALID,
                "primary source evidenceRef escapes the object work package",
                recovery=DataRecoveryAction.STOP,
            )
        )
    else:
        if not evidence_ref or not evidence_path.is_file():
            issues.append(
                _catalog_issue(
                    target,
                    DataIssueCode.SOURCE_MISSING,
                    "primary source evidence file is missing",
                )
            )
    return issues


def finalize_execution_qualification(execution_id: str) -> QualificationReport:
    """Validate object-local source catalogs and persist a typed execution closure."""
    normalized = validate_execution_id(execution_id)
    request_path = qualification_request_path(normalized)
    if not request_path.is_file():
        raise FileNotFoundError(
            f"source qualification request is missing: {request_path}; prepare execution first"
        )
    request = read_json(request_path)
    if not isinstance(request, Mapping):
        raise ValueError(f"source qualification request is not an object: {request_path}")
    assert_valid(
        request,
        "execution",
        "source_qualification_request",
        label=f"source_qualification_request:{normalized}",
    )
    targets = _targets_from_spec(normalized)
    if request.get("executionId") != normalized or request.get("targets") != [
        target.as_request() for target in targets
    ]:
        raise ValueError(
            "source qualification request does not match immutable execution targets"
        )
    root = execution_root(normalized)
    catalogs = _source_catalogs_by_name(root)
    target_rows: list[dict[str, object]] = []
    issues: list[DataIssue] = []
    for target in targets:
        matches = catalogs.get(target.name, [])
        source_catalog_ref = ""
        primary_projection = {
            "sourceKind": "",
            "canonicalUrl": "",
            "extractor": "",
            "snapshotHash": "",
            "evidenceRef": "",
        }
        target_issues: list[DataIssue] = []
        if len(matches) != 1:
            target_issues.append(
                _catalog_issue(
                    target,
                    DataIssueCode.SOURCE_MISSING if not matches else DataIssueCode.CONTRACT_INVALID,
                    "object source catalog is missing" if not matches else "multiple object source catalogs resolve to one target",
                    recovery=(
                        DataRecoveryAction.RETRY_SOURCE_DISCOVERY
                        if not matches
                        else DataRecoveryAction.STOP
                    ),
                )
            )
        else:
            catalog_path, catalog = matches[0]
            source_catalog_ref = catalog_path.relative_to(root).as_posix()
            primary = catalog.get("primarySource")
            if isinstance(primary, Mapping):
                primary_projection = _primary_source_projection(primary)
            target_issues.extend(_catalog_issues(target, catalog_path, catalog))
        issues.extend(target_issues)
        target_rows.append(
            {
                "name": target.name,
                "status": (
                    QualificationStatus.BLOCKED.value
                    if target_issues
                    else QualificationStatus.CONFIRMED.value
                ),
                "sourceCatalogRef": source_catalog_ref,
                "primarySource": primary_projection,
            }
        )
    payload = {
        "contractVersion": QUALIFICATION_VERSION,
        "executionId": normalized,
        "policyRevision": HOMEPAGE_SOURCE_POLICY_REVISION,
        "verifiedAt": now_iso(),
        "passed": not issues,
        "targets": target_rows,
        "issues": [issue.as_dict() for issue in issues],
    }
    assert_valid(
        payload,
        "execution",
        "source_qualification_result",
        label=f"source_qualification_result:{normalized}",
    )
    path = qualification_result_path(normalized)
    write_json(path, payload)
    return QualificationReport(normalized, not issues, tuple(issues), path)


__all__ = [
    "QualificationReport",
    "QualificationStatus",
    "finalize_execution_qualification",
    "prepare_execution_qualification",
    "qualification_request_path",
    "qualification_result_path",
]
