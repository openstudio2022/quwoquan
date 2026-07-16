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
from content.execution.identity import ExecutionIdentity, parse_execution_id
from core.control_types import RolloutMilestone
from content.execution.workspace import execution_root
from content.release.canonical.rollout_contract import (
    MILESTONE_ORDER,
    MILESTONE_PREDECESSOR,
    RolloutContract,
    RolloutMilestoneError,
    identity_matches,
    load_rollout_contract,
)
from verify.verify_execution_readiness import execution_readiness_issues
from verify.verify_homepage_media_completeness import homepage_media_completeness_report
from verify.verify_release_lifecycle import release_lifecycle_issues


ATTESTATION_FILE = "rollout_milestone_closure.json"


def _release_payload(release_root: Path) -> tuple[dict[str, Any], dict[str, Any], str]:
    try:
        header = read_json(payload_file(release_root, "release.json"))
        desired = read_json(payload_file(release_root, "desired_state.json"))
    except (OSError, TypeError, ValueError) as exc:
        raise RolloutMilestoneError(f"release payload unreadable: {release_root}: {exc}") from exc
    if not isinstance(header, dict) or not isinstance(desired, dict):
        raise RolloutMilestoneError("release payload documents must be objects")
    if str(header.get("releaseId") or "") != release_root.name:
        raise RolloutMilestoneError("release header releaseId does not match directory")
    if str(desired.get("releaseId") or "") != release_root.name:
        raise RolloutMilestoneError("release desired state releaseId does not match directory")
    return header, desired, payload_digest(release_root)


def _release_execution_identities(header: Mapping[str, Any], contract: RolloutContract) -> tuple[ExecutionIdentity, ...]:
    raw_ids = header.get("executionIds")
    if not isinstance(raw_ids, list) or not raw_ids:
        raise RolloutMilestoneError("release header has no executionIds")
    try:
        identities = tuple(parse_execution_id(str(value)) for value in raw_ids)
    except ValueError as exc:
        raise RolloutMilestoneError(f"release has invalid executionId: {exc}") from exc
    if len({item.execution_id for item in identities}) != len(identities):
        raise RolloutMilestoneError("release executionIds are duplicated")
    if any(not identity_matches(item, contract) for item in identities):
        raise RolloutMilestoneError("release executionIds do not belong to the configured rollout")
    milestone = str(header.get("rolloutMilestone") or "").strip()
    if milestone not in MILESTONE_PREDECESSOR:
        raise RolloutMilestoneError("release header rolloutMilestone is invalid")
    current_index = MILESTONE_ORDER.index(milestone)
    if any(MILESTONE_ORDER.index(item.milestone) > current_index for item in identities):
        raise RolloutMilestoneError("release contains an execution from a future milestone")
    if {item.scope for item in identities} != {item.scope for item in identities if item.scope in {row.scope for row in contract.provinces}}:
        raise RolloutMilestoneError("release execution scopes are not configured rollout scopes")
    if {item.scope for item in identities} != {row.scope for row in contract.provinces}:
        raise RolloutMilestoneError("release must include both Zhejiang and Sichuan executions")
    current_scopes = {item.scope for item in identities if item.milestone == milestone}
    if current_scopes != {row.scope for row in contract.provinces}:
        raise RolloutMilestoneError(
            "release must include both province executions for rolloutMilestone"
        )
    return identities


def _desired_entity_refs(desired: Mapping[str, Any]) -> set[str]:
    refs = desired.get("desiredRefs")
    values = refs.get("entities") if isinstance(refs, Mapping) else None
    if not isinstance(values, list) or not values:
        raise RolloutMilestoneError("release desired state has no entity refs")
    result = {str(item).strip() for item in values if str(item).strip()}
    if len(result) != len(values):
        raise RolloutMilestoneError("release desired entity refs are empty or duplicated")
    return result


def _execution_published_refs(identity: ExecutionIdentity) -> set[str]:
    root = execution_root(identity.execution_id)
    try:
        payload = read_json(root / "publish_ref.json")
    except (OSError, TypeError, ValueError) as exc:
        raise RolloutMilestoneError(f"{identity.execution_id}: publish_ref unreadable: {exc}") from exc
    if not isinstance(payload, Mapping) or payload.get("executionId") != identity.execution_id:
        raise RolloutMilestoneError(f"{identity.execution_id}: publish_ref identity drift")
    published = payload.get("publishedRefs")
    entities = published.get("entities") if isinstance(published, Mapping) else None
    if not isinstance(entities, list) or not entities:
        raise RolloutMilestoneError(f"{identity.execution_id}: publish_ref has no entities")
    return {str(item).strip() for item in entities if str(item).strip()}


def _execution_refs_by_scope(
    identities: tuple[ExecutionIdentity, ...], *, milestone: str
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    refs_by_scope: dict[str, set[str]] = {}
    batch_refs_by_scope: dict[str, set[str]] = {}
    for identity in identities:
        issues = execution_readiness_issues(identity.execution_id, require_reviewed=True)
        if issues:
            raise RolloutMilestoneError(f"{identity.execution_id}: execution readiness failed: {issues[0]}")
        media = homepage_media_completeness_report(identity.execution_id)
        if not bool(media.get("passed")):
            raise RolloutMilestoneError(f"{identity.execution_id}: homepage media completeness failed")
        refs = _execution_published_refs(identity)
        refs_by_scope.setdefault(identity.scope, set()).update(refs)
        if identity.milestone == milestone:
            batch_refs_by_scope.setdefault(identity.scope, set()).update(refs)
    return refs_by_scope, batch_refs_by_scope


def _assert_execution_closure(
    refs_by_scope: Mapping[str, set[str]], expected: set[str]
) -> None:
    published = set().union(*refs_by_scope.values()) if refs_by_scope else set()
    if published != expected:
        raise RolloutMilestoneError(
            f"release desired entities do not equal execution publish refs: expected={len(expected)} actual={len(published)}"
        )


def _output_ref(path: Path) -> str:
    try:
        return path.resolve().relative_to(OUTPUT_ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise RolloutMilestoneError(f"evidence must be below QWQ_OUTPUT_ROOT: {path}") from exc


def _read_object(path: Path, *, label: str) -> Mapping[str, Any]:
    try:
        payload = read_json(path)
    except (OSError, TypeError, ValueError) as exc:
        raise RolloutMilestoneError(f"{label} unreadable: {path}: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise RolloutMilestoneError(f"{label} must be an object: {path}")
    return payload


def _run_root(release_id: str, run_id: str) -> Path:
    return OUTPUT_ROOT / "env/gamma/runs/data-release" / release_id / run_id


def _completed_run(path: Path, *, release_id: str, kind: str) -> Mapping[str, Any]:
    run = _read_object(path / "run.json", label="Gamma run")
    result = _read_object(path / "result.json", label="Gamma run result")
    if (
        run.get("environment") != "gamma"
        or run.get("releaseId") != release_id
        or run.get("kind") != kind
        or result.get("environment") != "gamma"
        or result.get("releaseId") != release_id
        or result.get("status") != "completed"
    ):
        raise RolloutMilestoneError(f"Gamma run contract mismatch: {path}")
    return result


def _assert_full_sync_import_receipts(
    root: Path,
    *,
    release_id: str,
    expected_refs: set[str] | None = None,
) -> Mapping[str, Any]:
    content_path = root / "import.json"
    content = _read_object(content_path, label="content importer receipt")
    homepage_path = root / "homepage-import.json"
    homepage = _read_object(homepage_path, label="homepage importer receipt")
    try:
        assert_valid(dict(content), "release", "import_report", label=content_path.as_posix())
        assert_valid(
            dict(homepage),
            "release",
            "homepage_import_report",
            label=homepage_path.as_posix(),
        )
    except (TypeError, ValueError) as exc:
        raise RolloutMilestoneError(str(exc)) from exc
    if (
        content.get("releaseId") != release_id
        or content.get("environment") != "gamma"
        or content.get("status") != "active"
        or content.get("sourceOwner") != "qwq_data"
        or content.get("mode") != "sync"
        or content.get("deletePolicy") != "tombstone"
        or homepage.get("releaseId") != release_id
        or homepage.get("env") != "gamma"
        or homepage.get("dryRun") is not False
        or homepage.get("sourceOwner") != "qwq_data"
        or homepage.get("mode") != "sync"
        or homepage.get("issues")
        or homepage.get("skipped")
    ):
        raise RolloutMilestoneError(
            "Gamma importer receipts do not prove full-sync source-owned application"
        )
    mapping = homepage.get("entityRefToHomepageId")
    if not isinstance(mapping, Mapping):
        raise RolloutMilestoneError("Gamma homepage importer mapping is invalid")
    if expected_refs is not None and set(str(item) for item in mapping) != expected_refs:
        raise RolloutMilestoneError(
            "Gamma homepage importer mapping does not equal release desired entities"
        )
    return homepage


def _assert_gamma_evidence(
    *,
    release_root: Path,
    expected_refs: set[str],
    import_run_id: str,
    api_run_id: str,
    app_uat_report: Path,
    rollback_target_release_id: str,
    rollback_run_id: str,
    replay_run_id: str,
) -> list[str]:
    release_id = release_root.name
    import_root = _run_root(release_id, import_run_id)
    import_result = _completed_run(import_root, release_id=release_id, kind="apply")
    importer_path = import_root / "homepage-import.json"
    importer = _assert_full_sync_import_receipts(
        import_root,
        release_id=release_id,
        expected_refs=expected_refs,
    )
    mapping = importer.get("entityRefToHomepageId")
    if (
        importer.get("releaseId") != release_id
        or not isinstance(mapping, Mapping)
    ):
        raise RolloutMilestoneError("Gamma importer receipt does not exactly close release entities")
    cases_path = import_root / "app_uat_cases.json"
    if import_result.get("appUatCasesRef") != _output_ref(cases_path):
        raise RolloutMilestoneError("Gamma import result does not bind app_uat_cases.json")
    cases = _read_object(cases_path, label="Gamma App UAT cases")
    try:
        assert_valid(dict(cases), "release", "gamma_app_uat_case_manifest", label=cases_path.as_posix())
    except (TypeError, ValueError) as exc:
        raise RolloutMilestoneError(str(exc)) from exc
    case_mapping = {
        str(row.get("entityRef") or "").strip(): str(row.get("homepageId") or "").strip()
        for row in cases.get("cases", []) if isinstance(row, Mapping)
    }
    if cases.get("releaseId") != release_id or set(case_mapping) != expected_refs or any(not value for value in case_mapping.values()):
        raise RolloutMilestoneError("Gamma App UAT case manifest drifts from importer receipt")

    api_root = _run_root(release_id, api_run_id)
    api_result = _completed_run(api_root, release_id=release_id, kind="homepage_api_verification")
    api_path = api_root / "homepage-api-verification.json"
    if api_result.get("homepageApiVerificationRef") != _output_ref(api_path):
        raise RolloutMilestoneError("Gamma API run does not bind homepage verification report")
    api = _read_object(api_path, label="Gamma homepage API verification")
    try:
        assert_valid(dict(api), "release", "gamma_homepage_api_verification", label=api_path.as_posix())
    except (TypeError, ValueError) as exc:
        raise RolloutMilestoneError(str(exc)) from exc
    api_mapping = {
        str(row.get("entityRef") or "").strip(): str(row.get("homepageId") or "").strip()
        for row in api.get("entities", []) if isinstance(row, Mapping)
    }
    if (
        api.get("releaseId") != release_id
        or api.get("passed") is not True
        or api.get("sourceUatCasesRef") != _output_ref(cases_path)
        or api_mapping != case_mapping
    ):
        raise RolloutMilestoneError("Gamma API verification drifts from importer/App UAT identities")

    app_ref = _output_ref(app_uat_report)
    if not app_ref.startswith("env/gamma/runs/"):
        raise RolloutMilestoneError("Gamma App UAT report must be stored in env/gamma/runs")
    app = _read_object(app_uat_report, label="Gamma App UAT report")
    runs = app.get("runs")
    if (
        app.get("status") != "passed"
        or app.get("runtimeEnv") != "gamma"
        or app.get("apiContractEnv") != "gamma"
        or app.get("dataSource") != "remote"
        or app.get("releaseUatCasesPath") != _output_ref(cases_path)
        or not isinstance(runs, list)
        or not runs
        or any(not isinstance(row, Mapping) or row.get("exitCode") != 0 for row in runs)
    ):
        raise RolloutMilestoneError("Gamma App UAT report is not a passed remote release journey")

    if not rollback_target_release_id or rollback_target_release_id == release_id:
        raise RolloutMilestoneError("rollback target release must be a distinct immutable release")
    baseline_issues = release_lifecycle_issues(
        rollback_target_release_id,
        release_root=RELEASE_ROOT,
    )
    if baseline_issues:
        raise RolloutMilestoneError("rollback target immutable release is invalid: " + baseline_issues[0])
    rollback_root = _run_root(rollback_target_release_id, rollback_run_id)
    _completed_run(rollback_root, release_id=rollback_target_release_id, kind="rollback")
    _assert_full_sync_import_receipts(
        rollback_root,
        release_id=rollback_target_release_id,
    )
    rollback_path = rollback_root / "rollback_ref.json"
    rollback = _read_object(rollback_path, label="rollback reference")
    if rollback.get("rollbackTo") != rollback_target_release_id or rollback.get("rollbackFromReleaseId") != release_id:
        raise RolloutMilestoneError("rollback reference does not bind source and target releases")
    replay_root = _run_root(release_id, replay_run_id)
    _completed_run(replay_root, release_id=release_id, kind="apply")
    _assert_full_sync_import_receipts(
        replay_root,
        release_id=release_id,
        expected_refs=expected_refs,
    )
    return [
        _output_ref(import_root / "import.json"), _output_ref(importer_path),
        _output_ref(cases_path), _output_ref(api_path), app_ref,
        _output_ref(rollback_path), _output_ref(replay_root / "result.json"),
    ]


def _assert_milestone_scope(
    *,
    milestone: str,
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
        if milestone == "canary":
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
    header, desired, digest = _release_payload(release_root)
    identities = _release_execution_identities(header, contract)
    milestone = str(header.get("rolloutMilestone") or "")
    expected_refs = _desired_entity_refs(desired)
    refs_by_scope, batch_refs_by_scope = _execution_refs_by_scope(
        identities,
        milestone=milestone,
    )
    _assert_execution_closure(refs_by_scope, expected_refs)
    _assert_milestone_scope(
        milestone=milestone,
        refs_by_scope=refs_by_scope,
        batch_refs_by_scope=batch_refs_by_scope,
        contract=contract,
        expected_refs=expected_refs,
    )
    evidence_refs = _assert_gamma_evidence(
        release_root=release_root,
        expected_refs=expected_refs,
        import_run_id=import_run_id,
        api_run_id=api_run_id,
        app_uat_report=app_uat_report,
        rollback_target_release_id=rollback_target_release_id,
        rollback_run_id=rollback_run_id,
        replay_run_id=replay_run_id,
    )
    payload = {
        "schemaVersion": "quwoquan_data.rollout_milestone_closure/2",
        "releaseId": release_root.name,
        "payloadSha256": digest,
        "rolloutId": contract.rollout_id,
        "milestone": milestone,
        "environment": "gamma",
        "executionIds": sorted(item.execution_id for item in identities),
        "batchExecutionIds": sorted(
            item.execution_id for item in identities if item.milestone == milestone
        ),
        "approvedEntityRefs": sorted(expected_refs),
        "approvedEntityRefsByScope": {
            scope: sorted(refs_by_scope[scope]) for scope in sorted(refs_by_scope)
        },
        "batchApprovedEntityRefsByScope": {
            scope: sorted(batch_refs_by_scope[scope])
            for scope in sorted(batch_refs_by_scope)
        },
        "evidenceRefs": evidence_refs,
        "rollbackTargetReleaseId": rollback_target_release_id,
        "passed": True,
        "recordedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    try:
        assert_valid(payload, "release", "rollout_milestone_closure", label="rollout milestone closure")
    except (TypeError, ValueError) as exc:
        raise RolloutMilestoneError(str(exc)) from exc
    path = attestation_root(release_root) / ATTESTATION_FILE
    if path.exists():
        existing = _read_object(path, label="existing rollout milestone closure")
        comparable_existing = dict(existing)
        comparable_new = dict(payload)
        comparable_existing.pop("recordedAt", None)
        comparable_new.pop("recordedAt", None)
        if comparable_existing != comparable_new:
            raise RolloutMilestoneError(f"rollout milestone attestation is immutable and conflicts: {path}")
    else:
        write_json(path, payload)
    return {"releaseId": release_root.name, "milestone": milestone, "attestation": path.name}


def _milestone_attestation_issues(path: Path, *, contract: RolloutContract, expected: str) -> list[str]:
    try:
        payload = _read_object(path, label="rollout milestone closure")
        assert_valid(dict(payload), "release", "rollout_milestone_closure", label=path.as_posix())
        release_root = path.parent.parent
        header, desired, digest = _release_payload(release_root)
        identities = _release_execution_identities(header, contract)
        milestone = str(header.get("rolloutMilestone") or "")
        refs = _desired_entity_refs(desired)
    except (RolloutMilestoneError, TypeError, ValueError) as exc:
        return [str(exc)]
    if payload.get("releaseId") != release_root.name or payload.get("payloadSha256") != digest:
        return ["rollout milestone closure is detached from immutable release payload"]
    if (
        payload.get("rolloutId") != contract.rollout_id
        or payload.get("milestone") != expected
        or milestone != expected
    ):
        return ["rollout milestone closure identity does not match required predecessor"]
    if sorted(payload.get("executionIds") or []) != sorted(item.execution_id for item in identities):
        return ["rollout milestone closure executionIds drift from release"]
    if set(payload.get("approvedEntityRefs") or []) != refs:
        return ["rollout milestone closure approved entity refs drift from release"]
    by_scope = payload.get("approvedEntityRefsByScope")
    if not isinstance(by_scope, Mapping):
        return ["rollout milestone closure has no per-scope approved entity refs"]
    refs_by_scope = {
        str(scope): {str(item).strip() for item in rows if str(item).strip()}
        for scope, rows in by_scope.items()
        if isinstance(rows, list)
    }
    scoped_refs = set().union(*refs_by_scope.values()) if refs_by_scope else set()
    if scoped_refs != refs:
        return ["rollout milestone closure per-scope entity refs drift from release"]
    batch_by_scope_raw = payload.get("batchApprovedEntityRefsByScope")
    if not isinstance(batch_by_scope_raw, Mapping):
        return ["rollout milestone closure has no per-scope batch refs"]
    batch_refs_by_scope = {
        str(scope): {str(item).strip() for item in rows if str(item).strip()}
        for scope, rows in batch_by_scope_raw.items()
        if isinstance(rows, list)
    }
    try:
        _assert_milestone_scope(
            milestone=expected,
            refs_by_scope=refs_by_scope,
            batch_refs_by_scope=batch_refs_by_scope,
            contract=contract,
            expected_refs=refs,
        )
    except RolloutMilestoneError as exc:
        return [str(exc)]
    evidence = payload.get("evidenceRefs")
    if not isinstance(evidence, list) or len(evidence) != 7:
        return ["rollout milestone closure Gamma evidence is incomplete"]
    evidence_paths: list[Path] = []
    for raw in evidence:
        relative = Path(str(raw or ""))
        if relative.is_absolute() or ".." in relative.parts or not str(raw).startswith("env/gamma/runs/"):
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
        "app_uat_cases.json",
        "homepage-api-verification.json",
        "report.json",
        "rollback_ref.json",
        "result.json",
    }
    if set(by_name) != required_names or any(len(paths) != 1 for paths in by_name.values()):
        return ["rollout milestone closure Gamma evidence types are incomplete or duplicated"]
    importer_path = by_name["homepage-import.json"][0]
    content_importer_path = by_name["import.json"][0]
    cases_path = by_name["app_uat_cases.json"][0]
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
        rollback_target_release_id = str(payload.get("rollbackTargetReleaseId") or "").strip()
        rollback_run_id = _release_run_id(
            rollback_path,
            release_id=rollback_target_release_id,
            filename="rollback_ref.json",
        )
        replay_run_id = _release_run_id(replay_result_path, release_id=release_id, filename="result.json")
        rebuilt_evidence = _assert_gamma_evidence(
            release_root=release_root,
            expected_refs=refs,
            import_run_id=import_run_id,
            api_run_id=api_run_id,
            app_uat_report=app_uat_report,
            rollback_target_release_id=rollback_target_release_id,
            rollback_run_id=rollback_run_id,
            replay_run_id=replay_run_id,
        )
    except RolloutMilestoneError as exc:
        return [str(exc)]
    if list(evidence) != rebuilt_evidence:
        return ["rollout milestone closure Gamma evidence order or binding drifted"]
    return []


def _release_run_id(path: Path, *, release_id: str, filename: str) -> str:
    """Return a run id only for the canonical Gamma data-release evidence path."""
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


def _closed_milestone_releases(
    *, contract: RolloutContract, milestone: str
) -> list[Path]:
    if not RELEASE_ROOT.is_dir():
        return []
    releases: list[Path] = []
    for release_root in sorted(path for path in RELEASE_ROOT.iterdir() if path.is_dir()):
        path = attestation_root(release_root) / ATTESTATION_FILE
        if path.is_file() and not _milestone_attestation_issues(
            path,
            contract=contract,
            expected=milestone,
        ):
            releases.append(release_root)
    return releases


def _single_closed_milestone_release(
    *, contract: RolloutContract, milestone: str
) -> Path:
    releases = _closed_milestone_releases(contract=contract, milestone=milestone)
    if not releases:
        raise RolloutMilestoneError(
            f"no immutable Gamma-closed {milestone} release exists for {contract.rollout_id}"
        )
    if len(releases) != 1:
        raise RolloutMilestoneError(
            f"multiple Gamma-closed {milestone} releases exist; delete superseded runtime evidence"
        )
    return releases[0]


def _predecessor_target_names(
    *, identity: ExecutionIdentity, contract: RolloutContract
) -> tuple[str, ...]:
    predecessor = MILESTONE_PREDECESSOR[identity.milestone]
    if predecessor is None:
        return ()
    release = _single_closed_milestone_release(
        contract=contract,
        milestone=predecessor,
    )
    payload = _read_object(
        attestation_root(release) / ATTESTATION_FILE,
        label=f"{predecessor} rollout milestone closure",
    )
    by_scope = payload.get("approvedEntityRefsByScope")
    rows = by_scope.get(identity.scope) if isinstance(by_scope, Mapping) else None
    if not isinstance(rows, list):
        raise RolloutMilestoneError(
            f"{predecessor} release has no approved refs for {identity.scope}"
        )
    names = tuple(sorted({str(ref).rsplit("/", 1)[-1].strip() for ref in rows if str(ref).strip()}))
    province = contract.province_for_scope(identity.scope)
    if len(names) != contract.cumulative_count(predecessor, province):
        raise RolloutMilestoneError(
            f"{predecessor} approved refs for {identity.scope} are incomplete"
        )
    return names


def _retry_target_names(
    *, identity: ExecutionIdentity, retry_of: str
) -> tuple[str, ...]:
    previous = parse_execution_id(retry_of)
    if (
        previous.vertical,
        previous.content_type,
        previous.intent,
        previous.scope,
        previous.milestone,
    ) != (
        identity.vertical,
        identity.content_type,
        identity.intent,
        identity.scope,
        identity.milestone,
    ):
        raise RolloutMilestoneError("retryOf must identify the same rollout batch")
    if identity.sequence <= previous.sequence:
        raise RolloutMilestoneError("retry execution sequence must increase")
    selection = _read_object(
        execution_root(retry_of) / "_shared/target_selection.json",
        label="retryOf target selection",
    )
    rows = selection.get("targets")
    if not isinstance(rows, list) or not rows:
        raise RolloutMilestoneError("retryOf target selection has no frozen targets")
    names = tuple(
        str(row.get("name") or "").strip()
        for row in rows
        if isinstance(row, Mapping) and str(row.get("name") or "").strip()
    )
    if len(names) != len(rows) or len(set(names)) != len(names):
        raise RolloutMilestoneError("retryOf frozen targets are empty or duplicated")
    return names


def rollout_start_issues(execution_id: str) -> list[str]:
    """Return the exact immutable predecessor failure before an execution exists."""
    try:
        identity = parse_execution_id(execution_id)
        contract = load_rollout_contract()
    except (ValueError, RolloutMilestoneError) as exc:
        return [str(exc)]
    if not identity_matches(identity, contract):
        return []
    try:
        contract.province_for_scope(identity.scope)
    except RolloutMilestoneError as exc:
        return [str(exc)]
    predecessor = MILESTONE_PREDECESSOR[identity.milestone]
    if predecessor is None:
        return []
    if not RELEASE_ROOT.is_dir():
        return [f"{identity.milestone} requires a Gamma-closed {predecessor} release, but no releases exist"]
    candidates = _closed_milestone_releases(contract=contract, milestone=predecessor)
    if not candidates:
        return [
            f"{identity.milestone} requires an immutable Gamma-closed {predecessor} release "
            f"for rollout {contract.rollout_id}"
        ]
    if len(candidates) != 1:
        return [
            f"{identity.milestone} requires exactly one Gamma-closed {predecessor} release; "
            f"found {len(candidates)}"
        ]
    return []


def assert_rollout_start(execution_id: str) -> None:
    issues = rollout_start_issues(execution_id)
    if issues:
        raise RolloutMilestoneError("; ".join(issues))


def geo_rollout_parameters(
    *,
    execution_id: str,
    retry_of: str | None = None,
) -> tuple[str, int, str | None, tuple[str, ...]]:
    """Resolve fixed two-province canary/M1/M2 parameters before manifest creation."""
    identity = parse_execution_id(execution_id)
    contract = load_rollout_contract()
    if not identity_matches(identity, contract):
        raise RolloutMilestoneError(
            f"execution {execution_id} does not belong to rollout {contract.rollout_id}"
        )
    province_contract = contract.province_for_scope(identity.scope)
    expected_limit = contract.batch_count(identity.milestone, province_contract)
    excluded = _predecessor_target_names(identity=identity, contract=contract)
    mandatory: str | None = None
    if retry_of:
        retry_names = _retry_target_names(identity=identity, retry_of=retry_of)
        if len(retry_names) != expected_limit:
            raise RolloutMilestoneError(
                f"retryOf target count {len(retry_names)} != {expected_limit}"
            )
        mandatory = ",".join(retry_names)
    elif identity.milestone == RolloutMilestone.CANARY:
        mandatory = ",".join(province_contract.canary_targets)
    return province_contract.province, expected_limit, mandatory, excluded


__all__ = [
    "ATTESTATION_FILE",
    "RolloutMilestoneError",
    "assert_rollout_start",
    "build_rollout_milestone_attestation",
    "geo_rollout_parameters",
    "load_rollout_contract",
    "rollout_start_issues",
]
