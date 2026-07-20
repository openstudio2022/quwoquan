"""Typed boundary models for immutable Gamma rollout evidence.

All JSON decoding for rollout closure lives here.  The attestation coordinator
only receives value objects, so release approval cannot accidentally depend on
wire-format ``dict.get`` calls or free-form status text.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TypeVar

from core.codec import JsonObject, JsonObjectDecodeError
from core.control_types import (
    AppUatDataSource,
    AppUatStatus,
    ContentImportStatus,
    DeploymentEnvironment,
    ReleaseDeletePolicy,
    ReleaseRunKind,
    ReleaseRunStatus,
    ReleaseSourceOwner,
    ReleaseSyncMode,
    RolloutMilestone,
)
from core.io import read_json
from core.schema import assert_valid


class RolloutEvidenceError(ValueError):
    """A persisted environment receipt does not meet the closed contract."""


EnumValue = TypeVar("EnumValue", bound=StrEnum)


def _read_document(path: Path, *, label: str, schema_name: str | None = None) -> JsonObject:
    try:
        payload = read_json(path)
        document = JsonObject.from_value(payload, label=label)
        if schema_name is not None:
            assert_valid(document.to_document(), "release", schema_name, label=path.as_posix())
        return document
    except (OSError, TypeError, ValueError, JsonObjectDecodeError) as exc:
        raise RolloutEvidenceError(f"{label} unreadable or invalid: {path}: {exc}") from exc


def _enum(
    enum_type: type[EnumValue], value: str, *, field_name: str
) -> EnumValue:
    try:
        return enum_type(value)
    except ValueError as exc:
        raise RolloutEvidenceError(f"{field_name} is invalid: {value!r}") from exc


def _gamma_environment(value: str, *, field_name: str) -> DeploymentEnvironment:
    environment = _enum(DeploymentEnvironment, value, field_name=field_name)
    if environment is not DeploymentEnvironment.GAMMA:
        raise RolloutEvidenceError(f"{field_name} must be gamma")
    return environment


@dataclass(frozen=True, slots=True)
class GammaRunReceipt:
    release_id: str
    kind: ReleaseRunKind
    status: ReleaseRunStatus
    homepage_verification_cases_ref: str | None
    homepage_api_verification_ref: str | None

    @classmethod
    def load(cls, root: Path) -> "GammaRunReceipt":
        run = _read_document(root / "run.json", label="Gamma run")
        result = _read_document(root / "result.json", label="Gamma run result")
        run_environment = _gamma_environment(run.string("environment"), field_name="run.environment")
        result_environment = _gamma_environment(result.string("environment"), field_name="result.environment")
        if run_environment is not result_environment:
            raise RolloutEvidenceError("Gamma run environment mismatch")
        release_id = run.string("releaseId")
        if result.string("releaseId") != release_id:
            raise RolloutEvidenceError("Gamma run releaseId mismatch")
        return cls(
            release_id=release_id,
            kind=_enum(ReleaseRunKind, run.string("kind"), field_name="run.kind"),
            status=_enum(ReleaseRunStatus, result.string("status"), field_name="result.status"),
            homepage_verification_cases_ref=result.optional_string("homepageVerificationCasesRef"),
            homepage_api_verification_ref=result.optional_string("homepageApiVerificationRef"),
        )

    def assert_completed(self, *, release_id: str, kind: ReleaseRunKind) -> None:
        if (
            self.release_id != release_id
            or self.kind is not kind
            or self.status is not ReleaseRunStatus.COMPLETED
        ):
            raise RolloutEvidenceError("Gamma run contract mismatch")


@dataclass(frozen=True, slots=True)
class ContentImportReceipt:
    release_id: str
    environment: DeploymentEnvironment
    status: ContentImportStatus
    source_owner: ReleaseSourceOwner
    mode: ReleaseSyncMode
    delete_policy: ReleaseDeletePolicy
    posts_loaded: int
    entities_loaded: int

    @classmethod
    def load(cls, path: Path) -> "ContentImportReceipt":
        document = _read_document(path, label="content importer receipt", schema_name="import_report")
        counts = document.object("counts")
        return cls(
            release_id=document.string("releaseId"),
            environment=_gamma_environment(document.string("environment"), field_name="content.environment"),
            status=_enum(ContentImportStatus, document.string("status"), field_name="content.status"),
            source_owner=_enum(ReleaseSourceOwner, document.string("sourceOwner"), field_name="content.sourceOwner"),
            mode=_enum(ReleaseSyncMode, document.string("mode"), field_name="content.mode"),
            delete_policy=_enum(ReleaseDeletePolicy, document.string("deletePolicy"), field_name="content.deletePolicy"),
            posts_loaded=counts.integer("postsLoaded"),
            entities_loaded=counts.integer("entitiesLoaded"),
        )

    def assert_full_sync(
        self,
        *,
        release_id: str,
        expected_post_count: int,
        expected_entity_count: int,
    ) -> None:
        if (
            self.release_id != release_id
            or self.environment is not DeploymentEnvironment.GAMMA
            or self.status is not ContentImportStatus.ACTIVE
            or self.source_owner is not ReleaseSourceOwner.QWQ_DATA
            or self.mode is not ReleaseSyncMode.SYNC
            or self.delete_policy is not ReleaseDeletePolicy.TOMBSTONE
            or self.posts_loaded != expected_post_count
            or self.entities_loaded != expected_entity_count
        ):
            raise RolloutEvidenceError("content importer receipt does not prove Gamma full sync")


@dataclass(frozen=True, slots=True)
class HomepageImportReceipt:
    release_id: str
    environment: DeploymentEnvironment
    dry_run: bool
    source_owner: ReleaseSourceOwner
    mode: ReleaseSyncMode
    issues: tuple[JsonObject, ...]
    skipped: tuple[object, ...]
    entity_homepage_ids: tuple[tuple[str, str], ...]

    @classmethod
    def load(cls, path: Path) -> "HomepageImportReceipt":
        document = _read_document(path, label="homepage importer receipt", schema_name="homepage_import_report")
        skipped = document.value("skipped")
        if not isinstance(skipped, list):
            raise RolloutEvidenceError("homepage importer skipped must be an array")
        return cls(
            release_id=document.string("releaseId"),
            environment=_gamma_environment(document.string("env"), field_name="homepage.env"),
            dry_run=document.boolean("dryRun"),
            source_owner=_enum(ReleaseSourceOwner, document.string("sourceOwner"), field_name="homepage.sourceOwner"),
            mode=_enum(ReleaseSyncMode, document.string("mode"), field_name="homepage.mode"),
            issues=document.object_sequence("issues"),
            skipped=tuple(skipped),
            entity_homepage_ids=document.string_mapping("entityRefToHomepageId"),
        )

    @property
    def mapping(self) -> dict[str, str]:
        return dict(self.entity_homepage_ids)

    def assert_full_sync(self, *, release_id: str, expected_refs: set[str] | None = None) -> None:
        if (
            self.release_id != release_id
            or self.environment is not DeploymentEnvironment.GAMMA
            or self.dry_run
            or self.source_owner is not ReleaseSourceOwner.QWQ_DATA
            or self.mode is not ReleaseSyncMode.SYNC
            or self.issues
            or self.skipped
        ):
            raise RolloutEvidenceError("homepage importer receipt does not prove Gamma full sync")
        if expected_refs is not None and set(self.mapping) != expected_refs:
            raise RolloutEvidenceError("homepage importer mapping does not equal release desired entities")


@dataclass(frozen=True, slots=True)
class HomepageVerificationCases:
    release_id: str
    environment: DeploymentEnvironment
    entity_homepage_ids: tuple[tuple[str, str], ...]

    @classmethod
    def load(cls, path: Path) -> "HomepageVerificationCases":
        document = _read_document(path, label="homepage verification cases", schema_name="homepage_verification_case_manifest")
        rows: list[tuple[str, str]] = []
        for row in document.object_sequence("cases"):
            rows.append((row.string("entityRef"), row.string("homepageId")))
        return cls(
            release_id=document.string("releaseId"),
            environment=_gamma_environment(document.string("environment"), field_name="cases.environment"),
            entity_homepage_ids=tuple(rows),
        )

    @property
    def mapping(self) -> dict[str, str]:
        return dict(self.entity_homepage_ids)

    def assert_matches(self, *, release_id: str, expected_refs: set[str]) -> None:
        if (
            self.release_id != release_id
            or self.environment is not DeploymentEnvironment.GAMMA
            or set(self.mapping) != expected_refs
            or any(not homepage_id for homepage_id in self.mapping.values())
        ):
            raise RolloutEvidenceError("homepage verification cases drift from importer receipt")


@dataclass(frozen=True, slots=True)
class HomepageApiVerification:
    release_id: str
    environment: DeploymentEnvironment
    passed: bool
    source_cases_ref: str
    entity_homepage_ids: tuple[tuple[str, str], ...]

    @classmethod
    def load(cls, path: Path) -> "HomepageApiVerification":
        document = _read_document(path, label="homepage API verification", schema_name="homepage_api_verification")
        rows: list[tuple[str, str]] = []
        for row in document.object_sequence("entities"):
            rows.append((row.string("entityRef"), row.string("homepageId")))
        return cls(
            release_id=document.string("releaseId"),
            environment=_gamma_environment(document.string("environment"), field_name="api.environment"),
            passed=document.boolean("passed"),
            source_cases_ref=document.string("sourceCasesRef"),
            entity_homepage_ids=tuple(rows),
        )

    @property
    def mapping(self) -> dict[str, str]:
        return dict(self.entity_homepage_ids)

    def assert_matches(self, *, release_id: str, source_cases_ref: str, mapping: dict[str, str]) -> None:
        if (
            self.release_id != release_id
            or self.environment is not DeploymentEnvironment.GAMMA
            or not self.passed
            or self.source_cases_ref != source_cases_ref
            or self.mapping != mapping
        ):
            raise RolloutEvidenceError("homepage API verification drifts from importer identities")


@dataclass(frozen=True, slots=True)
class GammaAppUatReport:
    status: AppUatStatus
    runtime_environment: DeploymentEnvironment
    api_contract_environment: DeploymentEnvironment
    data_source: AppUatDataSource
    release_uat_cases_path: str
    exit_codes: tuple[int, ...]

    @classmethod
    def load(cls, path: Path) -> "GammaAppUatReport":
        document = _read_document(path, label="Gamma App UAT report")
        return cls(
            status=_enum(AppUatStatus, document.string("status"), field_name="app.status"),
            runtime_environment=_gamma_environment(document.string("runtimeEnv"), field_name="app.runtimeEnv"),
            api_contract_environment=_gamma_environment(document.string("apiContractEnv"), field_name="app.apiContractEnv"),
            data_source=_enum(AppUatDataSource, document.string("dataSource"), field_name="app.dataSource"),
            release_uat_cases_path=document.string("releaseUatCasesPath"),
            exit_codes=tuple(row.integer("exitCode") for row in document.object_sequence("runs")),
        )

    def assert_passed(self, *, cases_ref: str) -> None:
        if (
            self.status is not AppUatStatus.PASSED
            or self.runtime_environment is not DeploymentEnvironment.GAMMA
            or self.api_contract_environment is not DeploymentEnvironment.GAMMA
            or self.data_source is not AppUatDataSource.REMOTE
            or self.release_uat_cases_path != cases_ref
            or not self.exit_codes
            or any(code != 0 for code in self.exit_codes)
        ):
            raise RolloutEvidenceError("Gamma App UAT report is not a passed remote release journey")


@dataclass(frozen=True, slots=True)
class RollbackReference:
    rollback_to: str
    rollback_from_release_id: str

    @classmethod
    def load(cls, path: Path) -> "RollbackReference":
        document = _read_document(path, label="rollback reference")
        return cls(
            rollback_to=document.string("rollbackTo"),
            rollback_from_release_id=document.string("rollbackFromReleaseId"),
        )

    def assert_matches(self, *, rollback_to: str, rollback_from: str) -> None:
        if self.rollback_to != rollback_to or self.rollback_from_release_id != rollback_from:
            raise RolloutEvidenceError("rollback reference does not bind source and target releases")


@dataclass(frozen=True, slots=True)
class ReleasePayload:
    """The two immutable release documents decoded as one release identity."""

    release_id: str
    milestone: RolloutMilestone
    execution_ids: tuple[str, ...]
    desired_entity_refs: tuple[str, ...]
    desired_post_refs: tuple[str, ...]
    payload_sha256: str

    @classmethod
    def load(cls, release_root: Path, *, payload_sha256: str) -> "ReleasePayload":
        header = _read_document(
            release_root / "payload" / "release.json", label="release header"
        )
        desired = _read_document(
            release_root / "payload" / "desired_state.json", label="release desired state"
        )
        release_id = header.string("releaseId")
        if release_id != release_root.name or desired.string("releaseId") != release_id:
            raise RolloutEvidenceError("release payload releaseId does not match directory")
        try:
            milestone = RolloutMilestone(header.string("rolloutMilestone"))
        except ValueError as exc:
            raise RolloutEvidenceError("release header rolloutMilestone is invalid") from exc
        execution_ids = header.string_sequence("executionIds")
        desired_refs = desired.object("desiredRefs")
        desired_entity_refs = desired_refs.string_sequence("entities")
        desired_post_refs = desired_refs.string_sequence("posts")
        if len(set(desired_entity_refs)) != len(desired_entity_refs):
            raise RolloutEvidenceError("release desired entity refs are duplicated")
        if len(set(desired_post_refs)) != len(desired_post_refs):
            raise RolloutEvidenceError("release desired post refs are duplicated")
        return cls(
            release_id=release_id,
            milestone=milestone,
            execution_ids=execution_ids,
            desired_entity_refs=desired_entity_refs,
            desired_post_refs=desired_post_refs,
            payload_sha256=payload_sha256,
        )


@dataclass(frozen=True, slots=True)
class ExecutionPublishReference:
    execution_id: str
    entity_refs: tuple[str, ...]
    post_refs: tuple[str, ...]

    @classmethod
    def load(cls, path: Path) -> "ExecutionPublishReference":
        document = _read_document(path, label="execution publish reference")
        refs = document.object("publishedRefs")
        return cls(
            execution_id=document.string("executionId"),
            entity_refs=refs.string_sequence("entities"),
            post_refs=refs.string_sequence("posts"),
        )

    def assert_matches_execution(self, execution_id: str) -> None:
        if self.execution_id != execution_id:
            raise RolloutEvidenceError("execution publish reference identity drift")


@dataclass(frozen=True, slots=True)
class HomepageMediaCompleteness:
    passed: bool

    @classmethod
    def from_document(cls, value: object) -> "HomepageMediaCompleteness":
        document = JsonObject.from_value(value, label="homepage media completeness")
        return cls(passed=document.boolean("passed"))


@dataclass(frozen=True, slots=True)
class RolloutMilestoneClosure:
    release_id: str
    payload_sha256: str
    rollout_id: str
    milestone: RolloutMilestone
    execution_ids: tuple[str, ...]
    batch_execution_ids: tuple[str, ...]
    approved_entity_refs: tuple[str, ...]
    approved_entity_refs_by_scope: tuple[tuple[str, tuple[str, ...]], ...]
    batch_approved_entity_refs_by_scope: tuple[tuple[str, tuple[str, ...]], ...]
    evidence_refs: tuple[str, ...]
    rollback_target_release_id: str
    recorded_at: str

    @staticmethod
    def _scope_rows(document: JsonObject, key: str) -> tuple[tuple[str, tuple[str, ...]], ...]:
        raw = document.value(key)
        if not isinstance(raw, dict):
            raise RolloutEvidenceError(f"{key} must be an object")
        rows: list[tuple[str, tuple[str, ...]]] = []
        for scope, values in raw.items():
            if not isinstance(scope, str) or not scope.strip():
                raise RolloutEvidenceError(f"{key} scope is invalid")
            if not isinstance(values, list) or any(
                not isinstance(value, str) or not value.strip() for value in values
            ):
                raise RolloutEvidenceError(f"{key}.{scope} must be a string array")
            rows.append((scope, tuple(values)))
        return tuple(rows)

    @classmethod
    def from_document(cls, value: object, *, label: str) -> "RolloutMilestoneClosure":
        document = JsonObject.from_value(value, label=label)
        try:
            assert_valid(document.to_document(), "release", "rollout_milestone_closure", label=label)
            milestone = RolloutMilestone(document.string("milestone"))
        except (TypeError, ValueError, JsonObjectDecodeError) as exc:
            raise RolloutEvidenceError(f"{label} is invalid: {exc}") from exc
        if document.string("environment") != DeploymentEnvironment.GAMMA.value:
            raise RolloutEvidenceError("rollout milestone closure environment must be gamma")
        if not document.boolean("passed"):
            raise RolloutEvidenceError("rollout milestone closure must be passed")
        return cls(
            release_id=document.string("releaseId"),
            payload_sha256=document.string("payloadSha256"),
            rollout_id=document.string("rolloutId"),
            milestone=milestone,
            execution_ids=document.string_sequence("executionIds"),
            batch_execution_ids=document.string_sequence("batchExecutionIds"),
            approved_entity_refs=document.string_sequence("approvedEntityRefs"),
            approved_entity_refs_by_scope=cls._scope_rows(document, "approvedEntityRefsByScope"),
            batch_approved_entity_refs_by_scope=cls._scope_rows(document, "batchApprovedEntityRefsByScope"),
            evidence_refs=document.string_sequence("evidenceRefs"),
            rollback_target_release_id=document.string("rollbackTargetReleaseId"),
            recorded_at=document.string("recordedAt"),
        )

    def to_document(self) -> dict[str, object]:
        return {
            "schema": "quwoquan_data.rollout_milestone_closure",
            "releaseId": self.release_id,
            "payloadSha256": self.payload_sha256,
            "rolloutId": self.rollout_id,
            "milestone": self.milestone.value,
            "environment": DeploymentEnvironment.GAMMA.value,
            "executionIds": list(self.execution_ids),
            "batchExecutionIds": list(self.batch_execution_ids),
            "approvedEntityRefs": list(self.approved_entity_refs),
            "approvedEntityRefsByScope": {
                scope: list(refs) for scope, refs in self.approved_entity_refs_by_scope
            },
            "batchApprovedEntityRefsByScope": {
                scope: list(refs)
                for scope, refs in self.batch_approved_entity_refs_by_scope
            },
            "evidenceRefs": list(self.evidence_refs),
            "rollbackTargetReleaseId": self.rollback_target_release_id,
            "passed": True,
            "recordedAt": self.recorded_at,
        }

    @property
    def refs_by_scope(self) -> dict[str, set[str]]:
        return {scope: set(refs) for scope, refs in self.approved_entity_refs_by_scope}

    @property
    def batch_refs_by_scope(self) -> dict[str, set[str]]:
        return {
            scope: set(refs) for scope, refs in self.batch_approved_entity_refs_by_scope
        }

    def immutable_fields(self) -> tuple[object, ...]:
        return (
            self.release_id,
            self.payload_sha256,
            self.rollout_id,
            self.milestone,
            self.execution_ids,
            self.batch_execution_ids,
            self.approved_entity_refs,
            self.approved_entity_refs_by_scope,
            self.batch_approved_entity_refs_by_scope,
            self.evidence_refs,
            self.rollback_target_release_id,
        )


__all__ = [
    "ContentImportReceipt",
    "GammaAppUatReport",
    "GammaRunReceipt",
    "HomepageApiVerification",
    "HomepageMediaCompleteness",
    "HomepageImportReceipt",
    "HomepageVerificationCases",
    "ExecutionPublishReference",
    "ReleasePayload",
    "RollbackReference",
    "RolloutMilestoneClosure",
    "RolloutEvidenceError",
]
