"""Report integration for the actual Patrol test-host artifact binding."""

from __future__ import annotations

from typing import Any

from .artifact_binding import (
    APP_PAGE_ARTIFACT_BINDING_BLOCKER,
    CANONICAL_COMPARISON_KEYS,
    TESTED_APP_ARTIFACT_BINDING_PROVENANCE,
    TESTED_APP_ARTIFACT_BINDING_SCHEMA,
    TESTED_APP_ARTIFACT_BINDING_SET_SCHEMA,
    TestedAppArtifactBindingError,
    _platform_for_device,
    _typed_missing,
    collect_tested_app_artifact_binding,
    tested_app_artifact_comparison,
)


def unavailable_tested_app_artifact_binding(
    *,
    device: dict[str, Any] | None,
    reason: str,
    status: str = "gate_block",
) -> dict[str, object]:
    """Preserve an explicit typed absence; absence is never a passed binding."""

    target = device or {}
    try:
        platform = _platform_for_device(target)
    except TestedAppArtifactBindingError:
        platform = ""
    comparison = {key: "" for key in CANONICAL_COMPARISON_KEYS}
    comparison["typedMissing"] = _typed_missing(CANONICAL_COMPARISON_KEYS)
    binding: dict[str, object] = {
        "schema": TESTED_APP_ARTIFACT_BINDING_SCHEMA,
        "status": status,
        "provenance": TESTED_APP_ARTIFACT_BINDING_PROVENANCE,
        "nonPromotable": True,
        "platform": platform,
        "deviceId": str(target.get("id") or "").strip(),
        "applicationIdentity": {"status": "missing"},
        "buildArtifact": {"status": "missing"},
        "installedArtifactReadback": {"status": "missing"},
        "hostSource": {"status": "missing"},
        "canonicalComparison": comparison,
        "reason": " ".join(str(reason).split()).strip(),
    }
    if status == "gate_block":
        binding["errorCode"] = APP_PAGE_ARTIFACT_BINDING_BLOCKER
    return binding


def new_tested_app_artifact_binding_set() -> dict[str, object]:
    return {
        "schema": TESTED_APP_ARTIFACT_BINDING_SET_SCHEMA,
        "status": "pending",
        "provenance": TESTED_APP_ARTIFACT_BINDING_PROVENANCE,
        "bindings": [],
        "comparisonProjections": [],
    }


def attach_tested_app_artifact_binding(
    report: dict[str, Any],
    result: dict[str, Any],
    device: dict[str, Any],
    patrol_command: list[str],
    command_env: dict[str, str],
    dry_run: bool,
) -> tuple[dict[str, object], dict[str, object]]:
    """Collect one binding, mutate result fail-closed, and attach it to report."""

    result.setdefault("patrolExitCode", result.get("exitCode"))
    if dry_run:
        binding = unavailable_tested_app_artifact_binding(
            device=device,
            reason="dry-run did not build or install an App",
            status="not_executed",
        )
    else:
        try:
            binding = collect_tested_app_artifact_binding(
                device=device,
                patrol_command=patrol_command,
                command_env=command_env,
            )
        except Exception as error:  # noqa: BLE001 - evidence absence must not skip cleanup
            detail = (
                error.detail
                if isinstance(error, TestedAppArtifactBindingError)
                else f"App artifact readback failed: {error}"
            )
            binding = unavailable_tested_app_artifact_binding(
                device=device,
                reason=detail,
            )
            result["exitCode"] = 2
            result["outputSummary"] = (
                str(result.get("outputSummary") or "")
                + "\n"
                + APP_PAGE_ARTIFACT_BINDING_BLOCKER
                + ": "
                + detail
            ).strip()
    collection = report.get("testedAppArtifactBinding")
    if not isinstance(collection, dict):
        collection = new_tested_app_artifact_binding_set()
        report["testedAppArtifactBinding"] = collection
    bindings = collection.get("bindings")
    if not isinstance(bindings, list):
        raise TypeError("testedAppArtifactBinding bindings are invalid")
    bindings.append(binding)
    result["testedAppArtifactBinding"] = binding
    blocker: dict[str, object] = {}
    if binding.get("status") == "gate_block":
        blocker = {"errorCode": APP_PAGE_ARTIFACT_BINDING_BLOCKER}
    return binding, blocker


def settle_tested_app_artifact_binding_report(report: dict[str, Any]) -> None:
    """Make every report explicit about collected or missing device bindings."""

    collection = report.get("testedAppArtifactBinding")
    if not isinstance(collection, dict) or collection.get("schema") != (
        TESTED_APP_ARTIFACT_BINDING_SET_SCHEMA
    ):
        collection = new_tested_app_artifact_binding_set()
        report["testedAppArtifactBinding"] = collection
    bindings = collection.get("bindings")
    if not isinstance(bindings, list):
        bindings = []
        collection["bindings"] = bindings
    known_device_ids = {
        str(binding.get("deviceId") or "")
        for binding in bindings
        if isinstance(binding, dict)
    }
    report_is_dry_run = report.get("status") == "dry_run"
    for device in report.get("devices") or []:
        if not isinstance(device, dict):
            continue
        device_id = str(device.get("id") or "").strip()
        if not device_id or device_id in known_device_ids:
            continue
        bindings.append(
            unavailable_tested_app_artifact_binding(
                device=device,
                reason=(
                    "dry-run did not build or install an App"
                    if report_is_dry_run
                    else "page smoke ended before App artifact binding readback"
                ),
                status="not_executed" if report_is_dry_run else "gate_block",
            )
        )
    collection["comparisonProjections"] = [
        tested_app_artifact_comparison(binding)
        for binding in bindings
        if isinstance(binding, dict) and binding.get("status") == "passed"
    ]
    statuses = {
        str(binding.get("status") or "")
        for binding in bindings
        if isinstance(binding, dict)
    }
    if "gate_block" in statuses or (not bindings and not report_is_dry_run):
        collection["status"] = "gate_block"
        collection["errorCode"] = APP_PAGE_ARTIFACT_BINDING_BLOCKER
        if report.get("status") == "passed":
            report["status"] = "gate_block"
            report["failureReason"] = (
                "tested App artifact binding is missing or unreadable"
            )
    elif statuses == {"passed"}:
        collection["status"] = "passed"
        collection.pop("errorCode", None)
    else:
        collection["status"] = "not_executed"
        collection.pop("errorCode", None)
