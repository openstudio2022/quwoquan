"""App content UAT 的输入、套件、Patrol authority 与父回执编排。"""

from __future__ import annotations

import argparse
import hashlib
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.commands.app_preflight_uat_raw_results import (
    AppUatRawResultError,
)
from quwoquan_ops.cli.commands.app_preflight_uat_support import (
    APP_CORE_READBACK_UAT_TEST_TARGET,
    CONTROLLED_EDGE_RECOVERY_UAT_TEST_TARGET,
    MESSAGE_HOME_UAT_TEST_TARGET,
    PROFILE_JOURNEY_UAT_TEST_TARGET,
    RELEASE_SAMPLE_MATRIX_UAT_TEST_TARGET,
)


def prepare_app_content_uat_context(
    *,
    args: argparse.Namespace,
    stackctl: Any,
    resolve_uat_profile: Callable[..., dict[str, Any]],
    initial_issues: Sequence[str],
) -> tuple[
    list[str],
    Path,
    Path,
    list[str],
    list[str],
    str,
    dict[str, Any],
]:
    """Parse target/device inputs once and preserve fail-closed diagnostics."""
    allowed_targets = {"alpha-local", "beta-local", "gamma-local"}
    targets = [
        item.strip()
        for item in str(getattr(args, "targets", "")).split(",")
        if item.strip()
    ]
    report_dir = (
        Path(args.report_dir)
        if getattr(args, "report_dir", "")
        else stackctl.repo_run_dir("app-content-uat", target="nonprod-local")
    )
    canonical_output_root = Path(stackctl.output_root()).expanduser().resolve()
    issues = list(initial_issues)
    if not targets or len(targets) != len(set(targets)):
        issues.append("--targets must contain unique non-empty targets")
    unsupported = sorted(set(targets) - allowed_targets)
    if unsupported:
        issues.append("unsupported App content UAT targets: " + ", ".join(unsupported))
    device_id = str(getattr(args, "device_id", "") or "").strip()
    if not device_id:
        issues.append("--device-id is required")
    uat_profile: dict[str, Any] = {}
    if device_id:
        try:
            uat_profile = resolve_uat_profile(
                platform=str(getattr(args, "platform", "") or ""),
                device_id=device_id,
                device_registration_ref=str(
                    getattr(args, "device_registration_ref", "") or ""
                ),
            )
        except ValueError as exc:
            issues.append(str(exc))
    return (
        targets,
        report_dir,
        canonical_output_root,
        issues,
        unsupported,
        device_id,
        uat_profile,
    )


def app_content_uat_suite_plan(
    *,
    stackctl: Any,
    release_video_work_id: str,
) -> list[tuple[str, str, bool, str]]:
    """Return the canonical ordered page-UAT suite topology."""
    return [
        (
            "release-sample-matrix",
            RELEASE_SAMPLE_MATRIX_UAT_TEST_TARGET,
            False,
            "",
        ),
        (
            "controlled-edge-recovery",
            stackctl.CONTROLLED_EDGE_RECOVERY_UAT_TEST_TARGET,
            False,
            "",
        ),
        ("homepage-feed", stackctl.DISCOVERY_FEED_UAT_TEST_TARGET, False, ""),
        ("profile-journey", PROFILE_JOURNEY_UAT_TEST_TARGET, False, ""),
        ("message-home", MESSAGE_HOME_UAT_TEST_TARGET, False, ""),
        (
            "home-video-playback",
            stackctl.HOME_VIDEO_PLAYBACK_UAT_TEST_TARGET,
            True,
            release_video_work_id,
        ),
        (
            "app-core-readback",
            stackctl.APP_CORE_READBACK_UAT_TEST_TARGET,
            True,
            release_video_work_id,
        ),
    ]


def build_app_uat_patrol_authority(
    *,
    preflight: Mapping[str, Any],
    sample_plan: Mapping[str, Any],
    launch_binding: object,
    target_uat_binding_ref: object,
    runtime_binding: Mapping[str, Any],
    output_root: Path,
) -> tuple[dict[str, str], Path]:
    """Bind Patrol execution to exact release, candidate and graph bytes."""
    sample_plan_selection = sample_plan.get("selectionEvidence")
    if (
        not isinstance(sample_plan_selection, Mapping)
        or not isinstance(launch_binding, Mapping)
        or not isinstance(target_uat_binding_ref, Mapping)
    ):
        raise ValueError("App UAT Patrol authority inputs are incomplete")
    sample_plan_ref = str(preflight.get("releaseUatSamplePlanRef") or "")
    header_ref = Path(str(preflight.get("releaseHeaderRef") or "")).expanduser()
    sample_plan_path = (
        Path(sample_plan_ref).expanduser()
        if Path(sample_plan_ref).expanduser().is_absolute()
        else header_ref.parent / sample_plan_ref
    )
    if not sample_plan_path.is_file():
        sample_plan_path = header_ref.parent / "uat" / "sample_plan.json"
    try:
        sample_plan_authority_ref = (
            sample_plan_path.resolve().relative_to(output_root).as_posix()
        )
        binding_authority_ref = str(target_uat_binding_ref.get("ref") or "")
        candidate_manifest_path = (
            Path(str(runtime_binding["sourceCapsuleManifestRef"])).parent.parent
            / "manifest.json"
        )
        candidate_manifest_sha256 = hashlib.sha256(
            candidate_manifest_path.read_bytes()
        ).hexdigest()
        graph_path = Path(str(launch_binding["contractGraphRef"]))
        contract_graph_source_hash = hashlib.sha256(graph_path.read_bytes()).hexdigest()
        authority = {
            "releaseId": str(preflight.get("releaseId") or ""),
            "samplePlanRef": sample_plan_authority_ref,
            "samplePlanSha256": str(
                preflight.get("releaseUatSamplePlanDigest") or ""
            ),
            "targetUatBindingRef": binding_authority_ref,
            "targetUatBindingSha256": str(
                target_uat_binding_ref.get("digest") or ""
            ),
            "targetUatBindingDigest": str(
                target_uat_binding_ref.get("digest") or ""
            ),
            "releaseDigest": str(sample_plan.get("releaseDigest") or ""),
            "sourceIdentitySetDigest": str(
                sample_plan_selection.get("sourceIdentitySetDigest") or ""
            ),
            "commitSha": str(runtime_binding.get("sourceRevision") or ""),
            "contractGraphSourceHash": contract_graph_source_hash,
            "candidateManifestSha256": candidate_manifest_sha256,
        }
        return authority, sample_plan_path
    except (KeyError, OSError, ValueError) as exc:
        raise ValueError(
            f"App UAT Patrol authority binding failed: {exc}"
        ) from exc


def finalize_app_content_uat(
    *,
    args: argparse.Namespace,
    stackctl: Any,
    report_dir: Path,
    output_root: Path,
    targets: list[str],
    uat_profile: Mapping[str, Any],
    runtime_bindings: list[dict[str, Any]],
    launch_bindings: dict[str, dict[str, str]],
    target_uat_binding_refs: dict[str, dict[str, str]],
    raw_results: dict[str, list[dict[str, Any]]],
    expected_raw_coverage: dict[str, int],
    preflights: list[dict[str, Any]],
    runs: list[dict[str, Any]],
    experience_screenshot_digests: dict[str, dict[str, str]],
    issues: list[str],
    expected_raw_coverage_for_plan: Callable[[Mapping[str, Any]], int],
    project_raw_authority: Callable[..., tuple[dict[str, Any], list[str]]],
    build_receipt: Callable[..., dict[str, Any]],
    select_first_blocker: Callable[..., tuple[str, dict[str, Any]]],
) -> dict[str, Any]:
    """Project raw authority and write the canonical parent receipt."""
    dry_run = bool(getattr(args, "dry_run", False))
    if not issues and not dry_run and set(launch_bindings) != set(targets):
        issues.append("canonical launch bindings are incomplete for requested targets")
    if dry_run:
        for preflight in preflights:
            target = str(preflight.get("target") or "")
            sample_plan = preflight.get("releaseUatSamplePlan")
            if target and isinstance(sample_plan, Mapping):
                try:
                    expected_raw_coverage[target] = expected_raw_coverage_for_plan(
                        sample_plan
                    )
                except AppUatRawResultError as exc:
                    issues.append(f"{target}: {exc}")
    try:
        raw_authority_projection, raw_projection_issues = project_raw_authority(
            evidence_root=output_root,
            targets=targets,
            raw_results=raw_results,
            expected_raw_coverage=expected_raw_coverage,
            dry_run=dry_run,
        )
    except (OSError, TypeError, ValueError) as exc:
        raw_authority_projection = {
            "rawResultRefs": {target: [] for target in targets},
            "rawResultDigests": {target: [] for target in targets},
            "rawCoverage": {
                target: {
                    "expected": int(expected_raw_coverage.get(target) or 0),
                    "present": 0,
                    "missing": int(expected_raw_coverage.get(target) or 0),
                }
                for target in targets
            },
            "rawGaps": {target: [str(exc)] for target in targets},
        }
        raw_projection_issues = [str(exc)]
    issues.extend(item for item in raw_projection_issues if item not in issues)
    status = "gate_block" if issues else ("planned" if dry_run else "complete")
    payload = build_receipt(
        status=status,
        targets=targets,
        platform=str(args.platform),
        device_id=str(args.device_id),
        uat_profile=uat_profile,
        runtime_bindings=runtime_bindings,
        launch_bindings=launch_bindings,
        target_uat_binding_refs=target_uat_binding_refs,
        raw_authority_projection=raw_authority_projection,
        preflights=preflights,
        runs=runs,
        experience_screenshot_digests=experience_screenshot_digests,
        issues=issues,
        dry_run=dry_run,
        canonical_checksum=stackctl._canonical_document_checksum,
    )
    first_blocker, first_blocker_audit = select_first_blocker(
        status=status,
        preflights=preflights,
        runs=runs,
    )
    payload["firstBlocker"] = first_blocker
    if first_blocker_audit.get("fallback") is True and not payload["details"]:
        payload["details"].append(
            "APP.LAUNCH.receipt_invalid: parent gate_block lacked a canonical "
            "child blocker; inspect retained preflights/runs evidence for the "
            "original cause"
        )
    stackctl.write_json(report_dir / "report.json", payload)
    stackctl.write_json(report_dir / "findings.json", {"issues": issues})
    return {
        **payload,
        "exitCode": 0 if not issues else 2,
        "summary": (
            "App content UAT dry-run planned"
            if not issues and dry_run
            else "App content UAT raw authority projection complete"
            if not issues
            else "App content UAT is GATE_BLOCK"
        ),
        "reportDir": stackctl.relpath(report_dir),
    }
