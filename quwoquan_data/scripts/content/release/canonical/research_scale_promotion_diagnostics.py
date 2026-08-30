"""Project optional diagnostics into non-blocking research promotion fields."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from content.release.canonical.research_scale_capacity import (
    ResearchScaleCapacityEvidenceError,
    project_capacity_throughput,
)
from content.release.canonical.research_scale_promotion_statistics import (
    automatic_recovery_statistics,
)
from content.release.canonical.research_scale_promotion_timing import (
    ResearchScalePromotionTimingError,
    validate_promotion_timing,
)


def project_promotion_diagnostics(
    *,
    target_scale: str,
    evidence: Mapping[str, Any],
    resource_evidence: Mapping[str, Any] | None,
    fault_evidence: Mapping[str, Any] | None,
    automatic_recovery_rate_target: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return optional document/statistic fields; diagnostic failure never raises."""

    document_fields: dict[str, Any] = {}
    statistic_fields: dict[str, Any] = {}
    diagnostic_issues = [
        str(issue)
        for issue in evidence.get("diagnosticIssues") or []
        if str(issue).strip()
    ]
    timing_issues: list[str] = []
    if isinstance(resource_evidence, Mapping) and all(
        key in evidence
        for key in (
            "scaleStartedAt",
            "scaleCompletedAt",
            "wallClockBudgetSeconds",
            "wallClockSeconds",
        )
    ):
        try:
            timing_fields = validate_promotion_timing(
                target_scale=target_scale,
                evidence=evidence,
                resource_evidence=resource_evidence,
            )
        except ResearchScalePromotionTimingError as exc:
            timing_issues.append(
                f"DATA.DIAGNOSTIC.SCALE_TIMING_UNAVAILABLE: {exc}"
            )
        else:
            document_fields.update(timing_fields)
            budget = timing_fields.get("wallClockBudgetSeconds")
            if (
                isinstance(budget, int)
                and int(timing_fields["wallClockSeconds"]) > budget
            ):
                timing_issues.append(
                    "DATA.DIAGNOSTIC.WALL_CLOCK_BUDGET_EXCEEDED: "
                    f"{target_scale} wall-clock "
                    f"{timing_fields['wallClockSeconds']}s exceeds {budget}s"
                )
    else:
        timing_issues.append(
            "DATA.DIAGNOSTIC.SCALE_TIMING_UNAVAILABLE: "
            "resource/timing evidence not provided"
        )

    capacity_issues: list[str] = []
    capacity_throughput: list[dict[str, Any]] = []
    if isinstance(resource_evidence, Mapping):
        try:
            capacity_throughput = project_capacity_throughput(
                evidence=evidence,
                resource_evidence=resource_evidence,
            )
        except ResearchScaleCapacityEvidenceError as exc:
            capacity_issues.append(str(exc))
        statistic_fields["capacityPlanning"] = {
            "statistical": True,
            "nonBlocking": True,
            "status": "MEASURED" if capacity_throughput else "UNAVAILABLE",
            "evidenceCount": len(capacity_throughput),
            "observationIssues": capacity_issues,
        }
        statistic_fields["resourceSoak"] = {
            "statistical": True,
            "nonBlocking": True,
            "status": str(resource_evidence.get("status") or "failed"),
            "durationSeconds": int(resource_evidence.get("durationSeconds") or 0),
            "fourLaneOverlapDurationSeconds": int(
                resource_evidence.get("fourLaneOverlapDurationSeconds") or 0
            ),
        }
        document_fields.update(
            {
                "capacityThroughputByCarrier": capacity_throughput,
                "resourceIsolationPassed": (
                    resource_evidence.get("status") == "passed"
                ),
                "soakDurationSeconds": int(resource_evidence["durationSeconds"]),
                "semanticJobsByLane": list(resource_evidence["semanticJobsByLane"]),
                "fourLaneOverlapSampleCount": int(
                    resource_evidence["fourLaneOverlapSampleCount"]
                ),
                "fourLaneOverlapDurationSeconds": int(
                    resource_evidence["fourLaneOverlapDurationSeconds"]
                ),
                "fourLaneLongestContinuousOverlapSeconds": int(
                    resource_evidence["fourLaneLongestContinuousOverlapSeconds"]
                ),
                "allSemanticJobsTerminalAt": resource_evidence[
                    "allSemanticJobsTerminalAt"
                ],
                "terminalResidualSampleAt": str(
                    resource_evidence["terminalResidualSampleAt"]
                ),
                "resourceSoakEvidenceRef": str(evidence["resourceSoakEvidenceRef"]),
                "resourceSoakEvidenceDigest": str(
                    evidence["resourceSoakEvidenceDigest"]
                ),
            }
        )
    else:
        capacity_issues.append(
            "DATA.DIAGNOSTIC.CAPACITY_UNAVAILABLE: "
            "resource soak evidence not provided"
        )

    recovery_issues: list[str] = []
    if isinstance(fault_evidence, Mapping):
        try:
            statistic_fields["automaticRecoveryRate"] = (
                automatic_recovery_statistics(
                    fault_evidence,
                    target_rate=automatic_recovery_rate_target,
                )
            )
        except ValueError as exc:
            recovery_issues.append(
                f"DATA.DIAGNOSTIC.AUTOMATIC_RECOVERY_UNAVAILABLE: {exc}"
            )
        document_fields.update(
            {
                "faultInjectionEvidenceRef": str(
                    evidence["faultInjectionEvidenceRef"]
                ),
                "faultInjectionEvidenceDigest": str(
                    evidence["faultInjectionEvidenceDigest"]
                ),
            }
        )
    else:
        recovery_issues.append(
            "DATA.DIAGNOSTIC.AUTOMATIC_RECOVERY_UNAVAILABLE: "
            "fault-injection evidence not provided"
        )

    all_issues = list(
        dict.fromkeys(
            [
                *diagnostic_issues,
                *timing_issues,
                *capacity_issues,
                *recovery_issues,
            ]
        )
    )
    if all_issues:
        document_fields["diagnosticIssues"] = all_issues
    return document_fields, statistic_fields


__all__ = ["project_promotion_diagnostics"]
