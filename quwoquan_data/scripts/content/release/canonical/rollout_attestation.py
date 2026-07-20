"""Gamma-backed rollout milestones for the Zhejiang/Sichuan homepage program.

An execution may be created only after the preceding milestone has an immutable
release whose real Gamma import, API, App UAT, rollback, and replay evidence all
close.  This module deliberately derives that decision from release evidence;
it never maintains a campaign state directory or a mutable progress index.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from core.io import read_json, write_json
from core.paths import OUTPUT_ROOT, RELEASE_ROOT
from core.release_layout import attestation_root, payload_digest, payload_file
from core.schema import assert_valid
from core.control_types import ReleaseRunKind, RolloutMilestone
from content.execution.workspace import execution_root
from content.release.canonical.rollout_contract import (
    MILESTONE_ORDER,
    MILESTONE_PREDECESSOR,
    RolloutContract,
    RolloutMilestoneError,
    load_rollout_contract,
)
from content.release.canonical.rollout_execution_closure import (
    execution_refs_by_scope as _execution_refs_by_scope_impl,
    release_execution_identities as _release_execution_identities,
)
from content.release.canonical.rollout_evidence import (
    ContentImportReceipt,
    GammaAppUatReport,
    GammaRunReceipt,
    HomepageApiVerification,
    HomepageImportReceipt,
    HomepageVerificationCases,
    ReleasePayload,
    RollbackReference,
    RolloutEvidenceError,
    RolloutMilestoneClosure,
)
from verify.verify_execution_readiness import execution_readiness_issues
from verify.verify_homepage_media_completeness import homepage_media_completeness_report
from verify.verify_release_lifecycle import release_lifecycle_issues


ATTESTATION_FILE = "rollout_milestone_closure.json"


def _release_run_id(path: Path, *, release_id: str, filename: str) -> str:
    if not release_id:
        raise RolloutMilestoneError("Gamma evidence releaseId is empty")
    expected_root = OUTPUT_ROOT / "env/gamma/runs/data-release" / release_id
    if path.name != filename or path.parent.parent != expected_root:
        raise RolloutMilestoneError(
            f"Gamma evidence is outside canonical release run path: {path}"
        )
    run_id = path.parent.name
    if not run_id:
        raise RolloutMilestoneError("Gamma evidence runId is empty")
    return run_id


def _release_payload(release_root: Path) -> ReleasePayload:
    try:
        return ReleasePayload.load(
            release_root,
            payload_sha256=payload_digest(release_root),
        )
    except RolloutEvidenceError as exc:
        raise RolloutMilestoneError(f"release payload unreadable: {release_root}: {exc}") from exc


def _execution_refs_by_scope(
    identities: tuple[Any, ...],
    *,
    milestone: RolloutMilestone,
    contract: RolloutContract,
) -> tuple[dict[str, set[str]], dict[str, set[str]], set[str]]:
    return _execution_refs_by_scope_impl(
        identities,
        milestone=milestone,
        contract=contract,
        execution_root_resolver=execution_root,
        readiness_checker=execution_readiness_issues,
        homepage_media_reporter=homepage_media_completeness_report,
    )


def _assert_execution_closure(
    refs_by_scope: Mapping[str, set[str]], expected: set[str]
) -> None:
    published = set().union(*refs_by_scope.values()) if refs_by_scope else set()
    if published != expected:
        raise RolloutMilestoneError(
            f"release desired entities do not equal execution publish refs: expected={len(expected)} actual={len(published)}"
        )

def _assert_post_execution_closure(
    published: set[str],
    expected: set[str],
) -> None:
    if published != expected:
        raise RolloutMilestoneError(
            "release desired posts do not equal execution publish refs: "
            f"expected={len(expected)} actual={len(published)}"
        )

def _output_ref(path: Path) -> str:
    try:
        return path.resolve().relative_to(OUTPUT_ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise RolloutMilestoneError(f"evidence must be below QWQ_OUTPUT_ROOT: {path}") from exc

def _run_root(release_id: str, run_id: str) -> Path:
    return OUTPUT_ROOT / "env/gamma/runs/data-release" / release_id / run_id

def _completed_run(
    path: Path,
    *,
    release_id: str,
    kind: "ReleaseRunKind",
) -> GammaRunReceipt:
    try:
        receipt = GammaRunReceipt.load(path)
        receipt.assert_completed(release_id=release_id, kind=kind)
        return receipt
    except RolloutEvidenceError as exc:
        raise RolloutMilestoneError(f"Gamma run contract mismatch: {path}: {exc}") from exc

def _assert_full_sync_import_receipts(
    root: Path,
    *,
    release_id: str,
    expected_entity_refs: set[str],
    expected_post_refs: set[str],
) -> HomepageImportReceipt:
    content_path = root / "import.json"
    homepage_path = root / "homepage-import.json"
    try:
        content = ContentImportReceipt.load(content_path)
        homepage = HomepageImportReceipt.load(homepage_path)
        content.assert_full_sync(
            release_id=release_id,
            expected_post_count=len(expected_post_refs),
            expected_entity_count=len(expected_entity_refs),
        )
        homepage.assert_full_sync(
            release_id=release_id,
            expected_refs=expected_entity_refs,
        )
    except RolloutEvidenceError as exc:
        raise RolloutMilestoneError(
            "Gamma importer receipts do not prove full-sync source-owned application: "
            f"{exc}"
        ) from exc
    return homepage

def _assert_gamma_evidence(
    *,
    release_root: Path,
    expected_entity_refs: set[str],
    expected_post_refs: set[str],
    import_run_id: str,
    api_run_id: str,
    app_uat_report: Path,
    rollback_target_release_id: str,
    rollback_run_id: str,
    replay_run_id: str,
) -> list[str]:
    release_id = release_root.name
    import_root = _run_root(release_id, import_run_id)
    import_result = _completed_run(
        import_root,
        release_id=release_id,
        kind=ReleaseRunKind.APPLY,
    )
    importer_path = import_root / "homepage-import.json"
    importer = _assert_full_sync_import_receipts(
        import_root,
        release_id=release_id,
        expected_entity_refs=expected_entity_refs,
        expected_post_refs=expected_post_refs,
    )
    cases_path = import_root / "homepage_verification_cases.json"
    if import_result.homepage_verification_cases_ref != _output_ref(cases_path):
        raise RolloutMilestoneError("Gamma import result does not bind homepage verification cases")
    try:
        cases = HomepageVerificationCases.load(cases_path)
        cases.assert_matches(
            release_id=release_id,
            expected_refs=expected_entity_refs,
        )
    except RolloutEvidenceError as exc:
        raise RolloutMilestoneError(str(exc)) from exc
    case_mapping = cases.mapping
    if case_mapping != importer.mapping:
        raise RolloutMilestoneError("Gamma homepage verification cases drift from importer receipt")

    api_root = _run_root(release_id, api_run_id)
    api_result = _completed_run(
        api_root,
        release_id=release_id,
        kind=ReleaseRunKind.VERIFY,
    )
    api_path = api_root / "homepage-api-verification.json"
    if api_result.homepage_api_verification_ref != _output_ref(api_path):
        raise RolloutMilestoneError("Gamma API run does not bind homepage verification report")
    try:
        api = HomepageApiVerification.load(api_path)
        api.assert_matches(
            release_id=release_id,
            source_cases_ref=_output_ref(cases_path),
            mapping=case_mapping,
        )
    except RolloutEvidenceError as exc:
        raise RolloutMilestoneError(str(exc)) from exc

    if app_uat_report.name != "report.json":
        raise RolloutMilestoneError(
            "Gamma App UAT evidence must use the canonical report.json filename"
        )
    app_ref = _output_ref(app_uat_report)
    if not app_ref.startswith("env/gamma/runs/"):
        raise RolloutMilestoneError("Gamma App UAT report must be stored in env/gamma/runs")
    try:
        GammaAppUatReport.load(app_uat_report).assert_passed(
            cases_ref=_output_ref(cases_path)
        )
    except RolloutEvidenceError as exc:
        raise RolloutMilestoneError(str(exc)) from exc

    if not rollback_target_release_id or rollback_target_release_id == release_id:
        raise RolloutMilestoneError("rollback target release must be a distinct immutable release")
    baseline_issues = release_lifecycle_issues(
        rollback_target_release_id,
        release_root=RELEASE_ROOT,
    )
    if baseline_issues:
        raise RolloutMilestoneError("rollback target immutable release is invalid: " + baseline_issues[0])
    rollback_release = _release_payload(RELEASE_ROOT / rollback_target_release_id)
    rollback_root = _run_root(rollback_target_release_id, rollback_run_id)
    _completed_run(
        rollback_root,
        release_id=rollback_target_release_id,
        kind=ReleaseRunKind.ROLLBACK,
    )
    _assert_full_sync_import_receipts(
        rollback_root,
        release_id=rollback_target_release_id,
        expected_entity_refs=set(rollback_release.desired_entity_refs),
        expected_post_refs=set(rollback_release.desired_post_refs),
    )
    rollback_path = rollback_root / "rollback_ref.json"
    try:
        RollbackReference.load(rollback_path).assert_matches(
            rollback_to=rollback_target_release_id,
            rollback_from=release_id,
        )
    except RolloutEvidenceError as exc:
        raise RolloutMilestoneError(str(exc)) from exc
    replay_root = _run_root(release_id, replay_run_id)
    _completed_run(
        replay_root,
        release_id=release_id,
        kind=ReleaseRunKind.APPLY,
    )
    _assert_full_sync_import_receipts(
        replay_root,
        release_id=release_id,
        expected_entity_refs=expected_entity_refs,
        expected_post_refs=expected_post_refs,
    )
    return [
        _output_ref(import_root / "import.json"), _output_ref(importer_path),
        _output_ref(cases_path), _output_ref(api_path), app_ref,
        _output_ref(rollback_path), _output_ref(replay_root / "result.json"),
    ]

def _assert_milestone_scope(
    *,
    milestone: RolloutMilestone,
    refs_by_scope: Mapping[str, set[str]],
    batch_refs_by_scope: Mapping[str, set[str]],
    contract: RolloutContract,
    expected_refs: set[str],
) -> None:
    for province in contract.provinces:
        rows = refs_by_scope.get(province.scope, set())
        batch_rows = batch_refs_by_scope.get(province.scope, set())
        expected_cumulative = contract.cumulative_count(milestone, province)
        expected_batch = contract.batch_count(milestone, province)
        if len(rows) != expected_cumulative:
            raise RolloutMilestoneError(
                f"{milestone} {province.province} cumulative approved entity count "
                f"{len(rows)} != {expected_cumulative}"
            )
        if len(batch_rows) != expected_batch:
            raise RolloutMilestoneError(
                f"{milestone} {province.province} batch approved entity count "
                f"{len(batch_rows)} != {expected_batch}"
            )
        if milestone is RolloutMilestone.CANARY:
            expected_canary = set(province.canary_entity_refs)
            if rows != expected_canary or batch_rows != expected_canary:
                raise RolloutMilestoneError(
                    f"canary {province.province} entities must equal the fixed canary set"
                )
    if not expected_refs:
        raise RolloutMilestoneError("release contains no approved entity refs")

def build_rollout_milestone_attestation(
    *,
    release_root: Path,
    import_run_id: str,
    api_run_id: str,
    app_uat_report: Path,
    rollback_target_release_id: str,
    rollback_run_id: str,
    replay_run_id: str,
) -> dict[str, Any]:
    """Freeze one Gamma-closed rollout milestone without a mutable campaign state."""
    contract = load_rollout_contract()
    release = _release_payload(release_root)
    identities = _release_execution_identities(release, contract)
    milestone = release.milestone
    expected_refs = set(release.desired_entity_refs)
    expected_post_refs = set(release.desired_post_refs)
    refs_by_scope, batch_refs_by_scope, published_post_refs = _execution_refs_by_scope(
        identities,
        milestone=milestone,
        contract=contract,
    )
    _assert_execution_closure(refs_by_scope, expected_refs)
    _assert_post_execution_closure(published_post_refs, expected_post_refs)
    _assert_milestone_scope(
        milestone=milestone,
        refs_by_scope=refs_by_scope,
        batch_refs_by_scope=batch_refs_by_scope,
        contract=contract,
        expected_refs=expected_refs,
    )
    evidence_refs = _assert_gamma_evidence(
        release_root=release_root,
        expected_entity_refs=expected_refs,
        expected_post_refs=expected_post_refs,
        import_run_id=import_run_id,
        api_run_id=api_run_id,
        app_uat_report=app_uat_report,
        rollback_target_release_id=rollback_target_release_id,
        rollback_run_id=rollback_run_id,
        replay_run_id=replay_run_id,
    )
    closure = RolloutMilestoneClosure(
        release_id=release.release_id,
        payload_sha256=release.payload_sha256,
        rollout_id=contract.rollout_id,
        milestone=milestone,
        execution_ids=tuple(sorted(item.execution_id for item in identities)),
        batch_execution_ids=tuple(
            sorted(item.execution_id for item in identities if item.milestone == milestone)
        ),
        approved_entity_refs=tuple(sorted(expected_refs)),
        approved_entity_refs_by_scope=tuple(
            (scope, tuple(sorted(refs_by_scope[scope])))
            for scope in sorted(refs_by_scope)
        ),
        batch_approved_entity_refs_by_scope=tuple(
            (scope, tuple(sorted(batch_refs_by_scope[scope])))
            for scope in sorted(batch_refs_by_scope)
        ),
        evidence_refs=tuple(evidence_refs),
        rollback_target_release_id=rollback_target_release_id,
        recorded_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    )
    payload = closure.to_document()
    try:
        assert_valid(payload, "release", "rollout_milestone_closure", label="rollout milestone closure")
    except (TypeError, ValueError) as exc:
        raise RolloutMilestoneError(str(exc)) from exc
    path = attestation_root(release_root) / ATTESTATION_FILE
    if path.exists():
        try:
            existing = RolloutMilestoneClosure.from_document(
                read_json(path), label=path.as_posix()
            )
        except RolloutEvidenceError as exc:
            raise RolloutMilestoneError(str(exc)) from exc
        if existing.immutable_fields() != closure.immutable_fields():
            raise RolloutMilestoneError(f"rollout milestone attestation is immutable and conflicts: {path}")
    else:
        write_json(path, payload)
    return {
        "releaseId": release_root.name,
        "milestone": milestone.value,
        "attestation": path.name,
    }

def _milestone_attestation_issues(path: Path, *, contract: RolloutContract, expected: str) -> list[str]:
    try:
        closure = RolloutMilestoneClosure.from_document(
            read_json(path), label=path.as_posix()
        )
        release_root = path.parent.parent
        release = _release_payload(release_root)
        identities = _release_execution_identities(release, contract)
        refs = set(release.desired_entity_refs)
        post_refs = set(release.desired_post_refs)
        execution_refs_by_scope, execution_batch_refs_by_scope, execution_post_refs = (
            _execution_refs_by_scope(
                identities,
                milestone=release.milestone,
                contract=contract,
            )
        )
        _assert_execution_closure(execution_refs_by_scope, refs)
        _assert_post_execution_closure(execution_post_refs, post_refs)
    except (RolloutEvidenceError, RolloutMilestoneError, TypeError, ValueError) as exc:
        return [str(exc)]
    if (
        closure.release_id != release.release_id
        or closure.payload_sha256 != release.payload_sha256
    ):
        return ["rollout milestone closure is detached from immutable release payload"]
    if (
        closure.rollout_id != contract.rollout_id
        or closure.milestone.value != expected
        or release.milestone.value != expected
    ):
        return ["rollout milestone closure identity does not match required predecessor"]
    if list(closure.execution_ids) != sorted(item.execution_id for item in identities):
        return ["rollout milestone closure executionIds drift from release"]
    expected_batch_execution_ids = sorted(
        item.execution_id
        for item in identities
        if item.milestone is release.milestone
    )
    if list(closure.batch_execution_ids) != expected_batch_execution_ids:
        return ["rollout milestone closure batchExecutionIds drift from release"]
    if set(closure.approved_entity_refs) != refs:
        return ["rollout milestone closure approved entity refs drift from release"]
    refs_by_scope = closure.refs_by_scope
    scoped_refs = set().union(*refs_by_scope.values()) if refs_by_scope else set()
    if scoped_refs != refs:
        return ["rollout milestone closure per-scope entity refs drift from release"]
    if refs_by_scope != execution_refs_by_scope:
        return ["rollout milestone closure per-scope entity refs drift from executions"]
    batch_refs_by_scope = closure.batch_refs_by_scope
    if batch_refs_by_scope != execution_batch_refs_by_scope:
        return ["rollout milestone closure batch entity refs drift from executions"]
    try:
        _assert_milestone_scope(
            milestone=closure.milestone,
            refs_by_scope=refs_by_scope,
            batch_refs_by_scope=batch_refs_by_scope,
            contract=contract,
            expected_refs=refs,
        )
    except RolloutMilestoneError as exc:
        return [str(exc)]
    if len(closure.evidence_refs) != 7:
        return ["rollout milestone closure Gamma evidence is incomplete"]
    evidence_paths: list[Path] = []
    for ref in closure.evidence_refs:
        relative = Path(ref)
        if relative.is_absolute() or ".." in relative.parts or not ref.startswith("env/gamma/runs/"):
            return ["rollout milestone closure has unsafe Gamma evidence reference"]
        absolute = OUTPUT_ROOT / relative
        if not absolute.is_file():
            return ["rollout milestone closure evidence is missing"]
        evidence_paths.append(absolute)
    by_name: dict[str, list[Path]] = {}
    for evidence_path in evidence_paths:
        by_name.setdefault(evidence_path.name, []).append(evidence_path)
    required_names = {
        "import.json",
        "homepage-import.json",
        "homepage_verification_cases.json",
        "homepage-api-verification.json",
        "report.json",
        "rollback_ref.json",
        "result.json",
    }
    if set(by_name) != required_names or any(len(paths) != 1 for paths in by_name.values()):
        return ["rollout milestone closure Gamma evidence types are incomplete or duplicated"]
    importer_path = by_name["homepage-import.json"][0]
    content_importer_path = by_name["import.json"][0]
    cases_path = by_name["homepage_verification_cases.json"][0]
    api_path = by_name["homepage-api-verification.json"][0]
    app_uat_report = by_name["report.json"][0]
    rollback_path = by_name["rollback_ref.json"][0]
    replay_result_path = by_name["result.json"][0]
    release_id = release_root.name
    try:
        import_run_id = _release_run_id(importer_path, release_id=release_id, filename="homepage-import.json")
        if cases_path.parent != importer_path.parent or content_importer_path.parent != importer_path.parent:
            raise RolloutMilestoneError("Gamma importer evidence is split across different runs")
        api_run_id = _release_run_id(api_path, release_id=release_id, filename="homepage-api-verification.json")
        rollback_target_release_id = closure.rollback_target_release_id
        rollback_run_id = _release_run_id(
            rollback_path,
            release_id=rollback_target_release_id,
            filename="rollback_ref.json",
        )
        replay_run_id = _release_run_id(replay_result_path, release_id=release_id, filename="result.json")
        rebuilt_evidence = _assert_gamma_evidence(
            release_root=release_root,
            expected_entity_refs=refs,
            expected_post_refs=post_refs,
            import_run_id=import_run_id,
            api_run_id=api_run_id,
            app_uat_report=app_uat_report,
            rollback_target_release_id=rollback_target_release_id,
            rollback_run_id=rollback_run_id,
            replay_run_id=replay_run_id,
        )
    except RolloutMilestoneError as exc:
        return [str(exc)]
    if list(closure.evidence_refs) != rebuilt_evidence:
        return ["rollout milestone closure Gamma evidence order or binding drifted"]
    return []
