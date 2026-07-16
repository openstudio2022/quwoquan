"""Bind final Zhejiang/Sichuan environment proofs to one immutable release."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from core.io import read_json
from core.paths import OUTPUT_ROOT, RELEASE_ROOT
from core.release_layout import attestation_root, payload_digest, payload_file
from core.schema import assert_valid
from content.release.canonical.two_province_closure import (
    ATTESTATION_FILES,
    TwoProvinceClosureError,
    expected_entity_refs,
    write_two_province_attestation,
)
from verify.verify_release_lifecycle import release_lifecycle_issues


_UAT_TARGET = "test/user_acceptance/patrol/entity/two_province_homepage__rollout_render__functional__user_acceptance_test.dart"


class TwoProvinceEnvironmentClosureError(ValueError):
    """Gamma evidence is absent, malformed, or detached from the immutable release."""


def _read_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = read_json(path)
    except (OSError, TypeError, ValueError) as exc:
        raise TwoProvinceEnvironmentClosureError(f"{label} unreadable: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise TwoProvinceEnvironmentClosureError(f"{label} must be an object: {path}")
    return payload


def _output_ref(path: Path) -> str:
    try:
        return path.resolve().relative_to(OUTPUT_ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise TwoProvinceEnvironmentClosureError(f"runtime evidence must be below QWQ_OUTPUT_ROOT: {path}") from exc


def _path_from_output_ref(reference: object, *, label: str) -> Path:
    """Resolve one evidence reference without permitting path escape."""
    raw = str(reference or "").strip()
    relative = Path(raw)
    if not raw or relative.is_absolute() or ".." in relative.parts:
        raise TwoProvinceEnvironmentClosureError(f"{label} must be a relative QWQ_OUTPUT_ROOT reference")
    path = OUTPUT_ROOT / relative
    if not path.is_file():
        raise TwoProvinceEnvironmentClosureError(f"{label} is missing: {raw}")
    return path


def _data_release_run_id(path: Path, *, release_id: str, filename: str) -> str:
    """Return the run identity only for canonical Gamma data-release evidence."""
    try:
        relative = path.resolve().relative_to(OUTPUT_ROOT.resolve())
    except ValueError as exc:
        raise TwoProvinceEnvironmentClosureError(f"runtime evidence must be below QWQ_OUTPUT_ROOT: {path}") from exc
    parts = relative.parts
    prefix = ("env", "gamma", "runs", "data-release", release_id)
    if len(parts) != len(prefix) + 2 or parts[: len(prefix)] != prefix or parts[-1] != filename:
        raise TwoProvinceEnvironmentClosureError(
            f"{filename} must be stored in Gamma data-release run evidence for {release_id}"
        )
    run_id = parts[-2].strip()
    if not run_id:
        raise TwoProvinceEnvironmentClosureError(f"{filename} has no run identity")
    return run_id


def _single_evidence_ref(payload: Mapping[str, Any], *, kind: str, count: int) -> list[Path]:
    refs = payload.get("evidenceRefs")
    if not isinstance(refs, list) or len(refs) != count or len({str(item) for item in refs}) != count:
        raise TwoProvinceEnvironmentClosureError(f"{kind} attestation must contain exactly {count} distinct evidence refs")
    return [_path_from_output_ref(reference, label=f"{kind} evidence ref") for reference in refs]


def _assert_schema(payload: Mapping[str, Any], command: str, schema: str, *, label: str) -> None:
    try:
        assert_valid(dict(payload), command, schema, label=label)
    except (TypeError, ValueError) as exc:
        raise TwoProvinceEnvironmentClosureError(str(exc)) from exc


def _expected_refs(release_root: Path) -> set[str]:
    desired = _read_object(payload_file(release_root, "desired_state.json"), label="release desired state")
    refs = desired.get("desiredRefs") if isinstance(desired.get("desiredRefs"), Mapping) else {}
    actual = {str(value).strip() for value in (refs.get("entities") or []) if str(value).strip()}
    expected_by_province = expected_entity_refs()
    expected = set().union(*expected_by_province.values())
    if not all(expected_by_province.values()) or actual != expected:
        raise TwoProvinceEnvironmentClosureError("release desired entity refs do not exactly close the two-province master list")
    return expected


def _run_root(release_id: str, run_id: str) -> Path:
    return OUTPUT_ROOT / "env/gamma/runs/data-release" / release_id / run_id


def _assert_completed_run(path: Path, *, release_id: str, kind: str) -> dict[str, Any]:
    run = _read_object(path / "run.json", label="environment run")
    result = _read_object(path / "result.json", label="environment run result")
    if (
        run.get("environment") != "gamma"
        or run.get("releaseId") != release_id
        or run.get("kind") != kind
        or result.get("environment") != "gamma"
        or result.get("releaseId") != release_id
        or result.get("status") != "completed"
    ):
        raise TwoProvinceEnvironmentClosureError(f"environment run contract mismatch: {path}")
    return result


def _assert_import_and_api(
    *,
    release_root: Path,
    import_run_id: str,
    api_run_id: str,
    expected_refs: set[str],
) -> tuple[Path, Path, Path]:
    release_id = release_root.name
    import_root = _run_root(release_id, import_run_id)
    import_result = _assert_completed_run(import_root, release_id=release_id, kind="apply")
    importer = _read_object(import_root / "homepage-import.json", label="homepage importer receipt")
    _assert_schema(importer, "release", "homepage_import_report", label="homepage importer receipt")
    mapping = importer.get("entityRefToHomepageId")
    if (
        importer.get("env") != "gamma"
        or importer.get("dryRun") is not False
        or importer.get("issues")
        or importer.get("skipped")
        or not isinstance(mapping, Mapping)
        or set(mapping) != expected_refs
        or any(not isinstance(value, str) or not value.strip() for value in mapping.values())
    ):
        raise TwoProvinceEnvironmentClosureError("homepage importer receipt does not exactly close the two-province release")
    cases_path = import_root / "app_uat_cases.json"
    if import_result.get("appUatCasesRef") != _output_ref(cases_path):
        raise TwoProvinceEnvironmentClosureError("Gamma import result does not bind app_uat_cases.json")
    cases = _read_object(cases_path, label="Gamma App UAT cases")
    _assert_schema(cases, "release", "gamma_app_uat_case_manifest", label="Gamma App UAT cases")
    case_rows = cases.get("cases")
    if not isinstance(case_rows, list):
        raise TwoProvinceEnvironmentClosureError("Gamma App UAT cases must contain a cases array")
    case_mapping = {
        str(row.get("entityRef") or "").strip(): str(row.get("homepageId") or "").strip()
        for row in case_rows if isinstance(row, Mapping)
    }
    if cases.get("releaseId") != release_id or case_mapping != {str(key): str(value) for key, value in mapping.items()}:
        raise TwoProvinceEnvironmentClosureError("Gamma App UAT cases drift from homepage importer identity mapping")

    api_root = _run_root(release_id, api_run_id)
    api_result = _assert_completed_run(api_root, release_id=release_id, kind="homepage_api_verification")
    api_path = api_root / "homepage-api-verification.json"
    if api_result.get("homepageApiVerificationRef") != _output_ref(api_path):
        raise TwoProvinceEnvironmentClosureError("Gamma API verification run does not bind its report")
    api = _read_object(api_path, label="Gamma homepage API verification")
    _assert_schema(api, "release", "gamma_homepage_api_verification", label="Gamma homepage API verification")
    api_mapping = {
        str(row.get("entityRef") or "").strip(): str(row.get("homepageId") or "").strip()
        for row in api.get("entities", []) if isinstance(row, Mapping)
    }
    if api.get("releaseId") != release_id or api.get("sourceUatCasesRef") != _output_ref(cases_path) or api_mapping != case_mapping:
        raise TwoProvinceEnvironmentClosureError("Gamma API verification drift from importer/App UAT identities")
    return import_root / "homepage-import.json", cases_path, api_path


def _assert_app_uat(app_report: Path, *, case_manifest: Path, release_id: str) -> Path:
    try:
        relative = app_report.resolve().relative_to(OUTPUT_ROOT.resolve())
    except ValueError as exc:
        raise TwoProvinceEnvironmentClosureError("Gamma App UAT report must be below QWQ_OUTPUT_ROOT") from exc
    if relative.parts[:3] != ("env", "gamma", "runs"):
        raise TwoProvinceEnvironmentClosureError("Gamma App UAT report must be stored in env/gamma/runs")
    payload = _read_object(app_report, label="Gamma App UAT report")
    expected_ref = _output_ref(case_manifest)
    if (
        payload.get("status") != "passed"
        or payload.get("runtimeEnv") != "gamma"
        or payload.get("apiContractEnv") != "gamma"
        or payload.get("dataSource") != "remote"
        or payload.get("target") != _UAT_TARGET
        or payload.get("releaseUatCasesPath") != expected_ref
    ):
        raise TwoProvinceEnvironmentClosureError("Gamma App UAT report is not bound to the imported two-province case manifest")
    if not isinstance(payload.get("runs"), list) or not payload["runs"]:
        raise TwoProvinceEnvironmentClosureError("Gamma App UAT report has no device run evidence")
    return app_report


def _assert_rollback_replay(
    *,
    release_id: str,
    rollback_target_release_id: str,
    rollback_run_id: str,
    replay_run_id: str,
) -> tuple[Path, Path]:
    if not rollback_target_release_id or rollback_target_release_id == release_id:
        raise TwoProvinceEnvironmentClosureError("rollback target release must be a distinct immutable release")
    baseline_issues = release_lifecycle_issues(
        rollback_target_release_id,
        release_root=RELEASE_ROOT,
    )
    if baseline_issues:
        raise TwoProvinceEnvironmentClosureError(
            "rollback target immutable release is invalid: " + baseline_issues[0]
        )
    rollback_root = _run_root(rollback_target_release_id, rollback_run_id)
    rollback_result = _assert_completed_run(
        rollback_root,
        release_id=rollback_target_release_id,
        kind="rollback",
    )
    rollback_ref = _read_object(rollback_root / "rollback_ref.json", label="rollback reference")
    if (
        rollback_ref.get("rollbackTo") != rollback_target_release_id
        or rollback_ref.get("rollbackFromReleaseId") != release_id
        or rollback_result.get("status") != "completed"
    ):
        raise TwoProvinceEnvironmentClosureError("rollback evidence does not identify both source and target releases")
    replay_root = _run_root(release_id, replay_run_id)
    _assert_completed_run(replay_root, release_id=release_id, kind="apply")
    return rollback_root / "rollback_ref.json", replay_root / "result.json"


def environment_attestation_issues(
    *,
    release_root: Path,
    kind: str,
    payload: Mapping[str, Any],
) -> list[str]:
    """Re-validate an already-written Gamma attestation from its evidence.

    This is deliberately separate from the writer.  The final release gate must
    reconstruct the evidence binding instead of trusting a prior writer run or
    merely checking that evidence files still exist.
    """
    try:
        release_id = release_root.name
        expected_refs = _expected_refs(release_root)
        if kind == "importer_api":
            refs = _single_evidence_ref(payload, kind=kind, count=3)
            importer_path = next((path for path in refs if path.name == "homepage-import.json"), None)
            cases_path = next((path for path in refs if path.name == "app_uat_cases.json"), None)
            api_path = next((path for path in refs if path.name == "homepage-api-verification.json"), None)
            if importer_path is None or cases_path is None or api_path is None:
                raise TwoProvinceEnvironmentClosureError("importer_api attestation has invalid evidence roles")
            import_run_id = _data_release_run_id(importer_path, release_id=release_id, filename="homepage-import.json")
            if _data_release_run_id(cases_path, release_id=release_id, filename="app_uat_cases.json") != import_run_id:
                raise TwoProvinceEnvironmentClosureError("Gamma App UAT cases are not in the importer run")
            api_run_id = _data_release_run_id(api_path, release_id=release_id, filename="homepage-api-verification.json")
            resolved = _assert_import_and_api(
                release_root=release_root,
                import_run_id=import_run_id,
                api_run_id=api_run_id,
                expected_refs=expected_refs,
            )
            if set(resolved) != {importer_path, cases_path, api_path}:
                raise TwoProvinceEnvironmentClosureError("importer_api evidence paths do not match canonical run outputs")
        elif kind == "gamma_app_uat":
            (app_report,) = _single_evidence_ref(payload, kind=kind, count=1)
            cases_ref = _read_object(app_report, label="Gamma App UAT report").get("releaseUatCasesPath")
            cases_path = _path_from_output_ref(cases_ref, label="Gamma App UAT cases reference")
            _data_release_run_id(cases_path, release_id=release_id, filename="app_uat_cases.json")
            _assert_app_uat(app_report, case_manifest=cases_path, release_id=release_id)
        elif kind == "rollback_replay":
            rollback_target = str(payload.get("rollbackTargetReleaseId") or "").strip()
            refs = _single_evidence_ref(payload, kind=kind, count=2)
            rollback_path = next((path for path in refs if path.name == "rollback_ref.json"), None)
            replay_path = next((path for path in refs if path.name == "result.json"), None)
            if rollback_path is None or replay_path is None:
                raise TwoProvinceEnvironmentClosureError("rollback_replay attestation has invalid evidence roles")
            rollback_run_id = _data_release_run_id(
                rollback_path,
                release_id=rollback_target,
                filename="rollback_ref.json",
            )
            replay_run_id = _data_release_run_id(replay_path, release_id=release_id, filename="result.json")
            resolved = _assert_rollback_replay(
                release_id=release_id,
                rollback_target_release_id=rollback_target,
                rollback_run_id=rollback_run_id,
                replay_run_id=replay_run_id,
            )
            if set(resolved) != {rollback_path, replay_path}:
                raise TwoProvinceEnvironmentClosureError("rollback_replay evidence paths do not match canonical run outputs")
        else:
            raise TwoProvinceEnvironmentClosureError(f"unsupported environment attestation kind: {kind}")
    except TwoProvinceEnvironmentClosureError as exc:
        return [str(exc)]
    return []


def build_environment_attestations(
    *,
    release_root: Path,
    import_run_id: str,
    api_run_id: str,
    app_uat_report: Path,
    rollback_target_release_id: str,
    rollback_run_id: str,
    replay_run_id: str,
) -> dict[str, Any]:
    """Create final Gamma closure attestations from concrete runtime evidence only."""
    release_id = release_root.name
    expected_refs = _expected_refs(release_root)
    importer_path, cases_path, api_path = _assert_import_and_api(
        release_root=release_root,
        import_run_id=import_run_id,
        api_run_id=api_run_id,
        expected_refs=expected_refs,
    )
    app_path = _assert_app_uat(app_uat_report, case_manifest=cases_path, release_id=release_id)
    rollback_path, replay_path = _assert_rollback_replay(
        release_id=release_id,
        rollback_target_release_id=rollback_target_release_id,
        rollback_run_id=rollback_run_id,
        replay_run_id=replay_run_id,
    )
    common = {
        "schemaVersion": "quwoquan_data.two_province_release_attestation/1",
        "releaseId": release_id,
        "payloadSha256": payload_digest(release_root),
        "passed": True,
        "recordedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "environment": "gamma",
    }
    attestations = attestation_root(release_root)
    importer_refs = [_output_ref(importer_path), _output_ref(cases_path), _output_ref(api_path)]
    app_refs = [_output_ref(app_path)]
    rollback_refs = [_output_ref(rollback_path), _output_ref(replay_path)]
    write_two_province_attestation(
        attestations / ATTESTATION_FILES["importer_api"],
        {**common, "kind": "importer_api", "evidenceRefs": importer_refs},
    )
    write_two_province_attestation(
        attestations / ATTESTATION_FILES["gamma_app_uat"],
        {**common, "kind": "gamma_app_uat", "evidenceRefs": app_refs},
    )
    write_two_province_attestation(
        attestations / ATTESTATION_FILES["rollback_replay"],
        {
            **common,
            "kind": "rollback_replay",
            "rollbackTargetReleaseId": rollback_target_release_id,
            "evidenceRefs": rollback_refs,
        },
    )
    return {
        "releaseId": release_id,
        "entityCount": len(expected_refs),
        "attestations": [
            ATTESTATION_FILES["importer_api"],
            ATTESTATION_FILES["gamma_app_uat"],
            ATTESTATION_FILES["rollback_replay"],
        ],
    }


__all__ = [
    "TwoProvinceEnvironmentClosureError",
    "build_environment_attestations",
    "environment_attestation_issues",
]
