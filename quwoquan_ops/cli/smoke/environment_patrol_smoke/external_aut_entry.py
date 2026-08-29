"""Execute a native driver against an already-running production AUT."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from quwoquan_ops.ci.device_matrix.android import resolve_android_debug_bridge
from quwoquan_ops.ci.device_matrix.evidence import (
    capture_device_screenshot,
    repo_relative,
)

from . import external_aut_driver
from .constants import PATROL_HOST_DIR
from .execution import run_command
from .session import _local_target_for_environment_alias


def decode_external_aut_request(
    args: Any,
) -> tuple[
    bool,
    dict[str, Any],
    external_aut_driver.ExternalAutDriverEvidenceError | None,
]:
    handoff = str(
        getattr(args, "external_aut_canonical_binding_b64", "") or ""
    ).strip()
    if not handoff:
        return False, {}, None
    try:
        return (
            True,
            external_aut_driver.decode_external_aut_canonical_binding(handoff),
            None,
        )
    except external_aut_driver.ExternalAutDriverEvidenceError as exc:
        return True, {}, exc


def validate_external_aut_device_count(
    *, required: bool, devices: list[dict[str, Any]]
) -> None:
    if required and len(devices) != 1:
        raise external_aut_driver.ExternalAutDriverEvidenceError(
            "external production AUT journey requires exactly one device"
        )


def run_external_production_aut_homepage(
    *,
    args: Any,
    device: dict[str, Any],
    run_dir: Path,
    patrol_output: str,
    canonical_binding: dict[str, Any],
    runtime_env: str,
    command_env: dict[str, str],
) -> tuple[dict[str, object], dict[str, Any], dict[str, Any]]:
    """Run the native driver against the already-running canonical production AUT."""

    target_platform = str(device.get("targetPlatform") or "").strip().lower()
    platform = "android" if target_platform.startswith("android") else "ios"
    device_id = str(device.get("id") or "").strip()
    deployment_target = _local_target_for_environment_alias(args.env_name)
    projection = external_aut_driver.external_aut_canonical_binding_projection(
        canonical_binding,
        platform=platform,
        device_id=device_id,
        target=deployment_target,
        environment=runtime_env,
    )
    production_application_id = projection["applicationId"]
    log_path = run_dir / "external-production-aut-homepage.log"
    temporary_xctestrun: Path | None = None
    driver_result: dict[str, Any] = {}
    native_driver_artifact_binding: dict[str, object] = {}
    xctestrun_evidence: dict[str, object] = {"status": "not_required"}
    try:
        if platform == "android":
            adb = resolve_android_debug_bridge()
            if not adb:
                raise external_aut_driver.ExternalAutDriverEvidenceError(
                    "Android external AUT driver cannot resolve adb"
                )
            native_driver_artifact_binding = (
                external_aut_driver.collect_android_external_aut_driver_artifact_binding(
                    patrol_host_dir=PATROL_HOST_DIR,
                    device=device,
                    command_env=command_env,
                    adb=adb,
                )
            )
            command = external_aut_driver.android_external_aut_instrumentation_command(
                adb=adb,
                device_id=device_id,
                production_application_id=production_application_id,
            )
        else:
            source_xctestrun = (
                external_aut_driver.resolve_ios_external_aut_xctestrun(
                    patrol_host_dir=PATROL_HOST_DIR,
                    patrol_output=patrol_output,
                )
            )
            native_driver_artifact_binding = (
                external_aut_driver.build_ios_external_aut_driver_artifact_binding(
                    source=source_xctestrun,
                    patrol_host_dir=PATROL_HOST_DIR,
                    device_id=device_id,
                )
            )
            source_xctestrun_digest = str(
                (
                    native_driver_artifact_binding.get("evidence")
                    if isinstance(
                        native_driver_artifact_binding.get("evidence"), dict
                    )
                    else {}
                ).get("xctestrunDigest")
                or ""
            )
            temporary_xctestrun, xctestrun_digest = (
                external_aut_driver.materialize_ios_external_aut_xctestrun(
                    source=source_xctestrun,
                    production_application_id=production_application_id,
                    expected_source_digest=source_xctestrun_digest,
                )
            )
            command = external_aut_driver.ios_external_aut_xcodebuild_command(
                xctestrun=temporary_xctestrun,
                device_id=device_id,
            )
            xctestrun_evidence = {
                "status": "materialized",
                "sourcePath": repo_relative(source_xctestrun),
                "driverInputDigest": xctestrun_digest,
                "temporaryCopyRemoved": True,
            }
        driver_result = run_command(
            command,
            cwd=PATROL_HOST_DIR,
            timeout_seconds=args.timeout_seconds,
            log_path=log_path,
        )
        if driver_result.get("exitCode") != 0:
            raise external_aut_driver.ExternalAutDriverEvidenceError(
                "external AUT native driver failed: "
                + str(driver_result.get("outputSummary") or "unknown failure")
            )
        native_output = log_path.read_text(encoding="utf-8")
        native_evidence = external_aut_driver.parse_external_aut_homepage_evidence(
            native_output
        )
        journey = external_aut_driver.build_external_aut_homepage_journey(
            native_evidence=native_evidence,
            native_driver_artifact_binding=native_driver_artifact_binding,
            canonical_binding=canonical_binding,
            patrol_target=args.target,
            environment_alias=args.env_name,
            platform=platform,
            device_id=device_id,
            target=deployment_target,
            environment=runtime_env,
        )
        screenshot = capture_device_screenshot(
            device,
            run_dir / "external-production-aut-homepage.png",
        )
        driver_result["xctestrun"] = xctestrun_evidence
        driver_result["nativeDriverArtifactBinding"] = (
            native_driver_artifact_binding
        )
        return journey, driver_result, screenshot
    except Exception as exc:  # noqa: BLE001 - typed evidence must survive cleanup
        detail = (
            exc.detail
            if isinstance(
                exc, external_aut_driver.ExternalAutDriverEvidenceError
            )
            else f"external AUT native driver failed: {exc}"
        )
        if not driver_result:
            driver_result = {
                "command": [],
                "cwd": str(PATROL_HOST_DIR),
                "exitCode": 2,
                "timedOut": False,
                "durationMs": 0,
                "outputSummary": detail,
                "logPath": repo_relative(log_path),
            }
        else:
            driver_result["exitCode"] = 2
            driver_result["outputSummary"] = (
                str(driver_result.get("outputSummary") or "")
                + "\n"
                + external_aut_driver.APP_PAGE_ARTIFACT_BINDING_BLOCKER
                + ": "
                + detail
            ).strip()
        driver_result["xctestrun"] = xctestrun_evidence
        if native_driver_artifact_binding:
            driver_result["nativeDriverArtifactBinding"] = (
                native_driver_artifact_binding
            )
        return (
            external_aut_driver.unavailable_external_aut_journey(
                reason=detail,
                platform=platform,
                device_id=device_id,
            ),
            driver_result,
            {"status": "skipped", "reason": "external AUT journey failed"},
        )
    finally:
        if temporary_xctestrun is not None:
            temporary_xctestrun.unlink(missing_ok=True)


def record_external_aut_journey(
    *,
    required: bool,
    args: Any,
    device: dict[str, Any],
    run_dir: Path,
    patrol_output: str,
    canonical_binding: dict[str, Any],
    runtime_env: str,
    command_env: dict[str, str],
    tested_app_artifact_binding: dict[str, Any],
    report: dict[str, Any],
    result: dict[str, Any],
) -> tuple[
    dict[str, object],
    dict[str, Any],
    dict[str, Any],
    dict[str, object],
    bool,
]:
    """Attach the optional external journey and return its typed blocker."""

    journey: dict[str, object] = {}
    driver_result: dict[str, Any] = {"status": "not_required"}
    screenshot: dict[str, Any] = {
        "status": "skipped",
        "reason": "external AUT journey not required",
    }
    blocker: dict[str, object] = {}
    if not required:
        return journey, driver_result, screenshot, blocker, False

    platform = (
        "android"
        if str(device.get("targetPlatform") or "")
        .strip()
        .lower()
        .startswith("android")
        else "ios"
    )
    if args.dry_run:
        journey = external_aut_driver.unavailable_external_aut_journey(
            reason="dry-run did not execute a production AUT",
            platform=platform,
            device_id=str(device.get("id") or ""),
            status="not_executed",
        )
        driver_result = {"status": "not_executed"}
    elif tested_app_artifact_binding.get("status") != "passed":
        journey = external_aut_driver.unavailable_external_aut_journey(
            reason="native driver artifact was not installed and read back",
            platform=platform,
            device_id=str(device.get("id") or ""),
        )
    else:
        journey, driver_result, screenshot = run_external_production_aut_homepage(
            args=args,
            device=device,
            run_dir=run_dir,
            patrol_output=patrol_output,
            canonical_binding=canonical_binding,
            runtime_env=runtime_env,
            command_env=command_env,
        )
        native_driver_artifact = driver_result.get("nativeDriverArtifactBinding")
        if isinstance(native_driver_artifact, dict):
            report["externalProductionAutDriverArtifact"] = native_driver_artifact

    external_aut_driver.attach_external_aut_journey(report, journey)
    gate_blocked = journey.get("status") == "gate_block"
    if gate_blocked:
        blocker = external_aut_driver.external_aut_journey_blocker()
        result["exitCode"] = 2
        result["outputSummary"] = (
            str(result.get("outputSummary") or "")
            + "\n"
            + external_aut_driver.APP_PAGE_ARTIFACT_BINDING_BLOCKER
            + ": external production AUT startup/homepage journey failed"
        ).strip()
    result["externalProductionAutJourney"] = journey
    result["externalProductionAutDriver"] = driver_result
    return journey, driver_result, screenshot, blocker, gate_blocked


def external_aut_case_result(
    *,
    required: bool,
    dry_run: bool,
    device_id: str,
    journey: dict[str, object],
    driver_result: dict[str, Any],
    screenshot: dict[str, Any],
    blocker: dict[str, object],
) -> dict[str, object] | None:
    if not required:
        return None
    return {
        "caseId": "external-aut:production-startup-homepage:" + device_id,
        "journeyId": external_aut_driver.EXTERNAL_AUT_JOURNEY_ID,
        "status": (
            "not_executed"
            if dry_run
            else ("passed" if journey.get("status") == "passed" else "gate_block")
        ),
        "deviceId": device_id,
        **blocker,
        "evidence": {
            "journey": journey,
            "driver": driver_result,
            "screenshot": screenshot,
        },
    }
