"""Optional runtime diagnostics for campaign scale evidence and promotion audits."""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.release.canonical import runtime_scale_evidence_binding as runtime_binding
from content.release.canonical.campaign_scale_contract import (
    CampaignScaleEvidenceError,
    _file_sha256,
    _load_plan,
    _resolve_ref,
    _safe_ref,
    _validated,
    _verify_evidence_digest,
)
from content.release.canonical.campaign_scale_cumulative import scale_timing_fields
from content.release.canonical.fault_injection_evidence import (
    write_fault_injection_evidence,
)
from content.release.canonical.resource_soak_evidence import (
    _derive_resource_soak_stable,
    write_resource_soak_evidence,
)


def derive_runtime_diagnostic_fields(
    *,
    evidence_id: str,
    runtime_session_path: Path | None,
    campaign_plan_path: Path,
    tasks_root: Path,
    release: Path,
    output_root: Path,
    evidence_root: Path,
    target_scale: str,
    predecessor_promotion_path: Path | None,
) -> dict[str, Any]:
    """Best-effort runtime observations; never decide scale promotion."""

    issues: list[str] = []
    fields: dict[str, Any] = {}
    if runtime_session_path is None:
        return {
            "diagnosticIssues": [
                (
                    "DATA.DIAGNOSTIC.RUNTIME_EVIDENCE_UNAVAILABLE: "
                    "runtime session not provided"
                )
            ]
        }
    try:
        session, raw_samples_path, raw_fault_cases_path = (
            runtime_binding.materialize_bound_runtime_inputs(
                runtime_session_path=runtime_session_path,
                campaign_plan_path=campaign_plan_path,
                evidence_root=evidence_root,
                output_root=output_root,
            )
        )
        fields.update(
            runtime_binding.runtime_binding_fields(
                session,
                session_path=runtime_session_path,
                output_root=output_root,
            )
        )
    except (CampaignScaleEvidenceError, OSError, TypeError, ValueError) as exc:
        return {
            "diagnosticIssues": [
                f"DATA.DIAGNOSTIC.RUNTIME_EVIDENCE_UNAVAILABLE: {exc}"
            ]
        }

    try:
        resource, resource_path = write_resource_soak_evidence(
            evidence_id=evidence_id,
            campaign_plan_path=campaign_plan_path,
            raw_samples_path=raw_samples_path,
            tasks_root=tasks_root,
            release_root=release,
            output_root=output_root,
            evidence_root=evidence_root,
        )
    except (CampaignScaleEvidenceError, OSError, TypeError, ValueError) as exc:
        resource = None
        issues.append(f"DATA.DIAGNOSTIC.RESOURCE_SOAK_UNAVAILABLE: {exc}")
    if resource is not None:
        fields.update(
            {
                "fourLaneOverlapDurationSeconds": int(
                    resource["fourLaneOverlapDurationSeconds"]
                ),
                "fourLaneLongestContinuousOverlapSeconds": int(
                    resource["fourLaneLongestContinuousOverlapSeconds"]
                ),
                "allSemanticJobsTerminalAt": resource[
                    "allSemanticJobsTerminalAt"
                ],
                "terminalResidualSampleAt": resource["terminalResidualSampleAt"],
                "resourceSoakEvidenceRef": _safe_ref(
                    resource_path,
                    output_root=output_root,
                    label="resource soak evidence",
                ),
                "resourceSoakEvidenceDigest": resource["evidenceDigest"],
            }
        )
        try:
            fields.update(
                scale_timing_fields(
                    target_scale=target_scale,
                    plan=_load_plan(campaign_plan_path),
                    predecessor_promotion_path=predecessor_promotion_path,
                    resource=resource,
                )
            )
        except (CampaignScaleEvidenceError, OSError, TypeError, ValueError) as exc:
            issues.append(f"DATA.DIAGNOSTIC.SCALE_TIMING_UNAVAILABLE: {exc}")

    try:
        fault, fault_path = write_fault_injection_evidence(
            evidence_id=evidence_id,
            campaign_plan_path=campaign_plan_path,
            raw_cases_path=raw_fault_cases_path,
            tasks_root=tasks_root,
            output_root=output_root,
            evidence_root=evidence_root,
        )
    except (CampaignScaleEvidenceError, OSError, TypeError, ValueError) as exc:
        fault = None
        issues.append(f"DATA.DIAGNOSTIC.FAULT_INJECTION_UNAVAILABLE: {exc}")
    if fault is not None:
        fields.update(
            {
                "faultInjectionEvidenceRef": _safe_ref(
                    fault_path,
                    output_root=output_root,
                    label="fault injection evidence",
                ),
                "faultInjectionEvidenceDigest": fault["evidenceDigest"],
            }
        )
    fields["diagnosticIssues"] = list(dict.fromkeys(issues))
    return fields


def load_campaign_diagnostics(
    *,
    campaign: Mapping[str, Any],
    campaign_path: Path,
    plan: Mapping[str, Any],
    plan_path: Path,
    predecessor_path: Path | None,
    release: Path,
    output_root: Path,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Strictly audit optional diagnostics without making them promotion inputs."""

    resource_ref = campaign.get("resourceSoakEvidenceRef")
    fault_ref = campaign.get("faultInjectionEvidenceRef")
    if resource_ref is None and fault_ref is None:
        return None, None
    runtime_session_path = _resolve_ref(
        str(campaign.get("runtimeSessionRef") or ""),
        output_root=output_root,
        label="runtime session ref",
    )
    session, bound_samples_path, bound_faults_path = (
        runtime_binding.materialize_bound_runtime_inputs(
            runtime_session_path=runtime_session_path,
            campaign_plan_path=plan_path,
            evidence_root=campaign_path.parent,
            output_root=output_root,
        )
    )
    resource: dict[str, Any] | None = None
    fault: dict[str, Any] | None = None
    diagnostic_documents: list[Mapping[str, Any]] = [campaign]
    identity_keys = (
        "rootExecutionId",
        "sourceRevision",
        "sourceDigest",
        "entityCatalogDigest",
    )
    if resource_ref is not None:
        resource_path = _resolve_ref(
            str(resource_ref),
            output_root=output_root,
            label="resource soak evidence ref",
        )
        resource = _validated(
            resource_path,
            "release",
            "resource_soak_evidence",
            label="canonical resource soak evidence",
        )
        resource_digest = _verify_evidence_digest(resource, label="resource soak")
        raw_samples_path = _resolve_ref(
            str(resource["rawSamplesRef"]),
            output_root=output_root,
            label="resource raw samples ref",
        )
        expected_resource = _derive_resource_soak_stable(
            evidence_id=str(resource["evidenceId"]),
            campaign_plan_path=plan_path,
            raw_samples_path=raw_samples_path,
            tasks_root=output_root / "data/tasks",
            release_root=release,
            output_root=output_root,
        )
        resource_stable = {
            key: value
            for key, value in resource.items()
            if key not in {"recordedAt", "evidenceDigest"}
        }
        if resource_stable != expected_resource:
            raise CampaignScaleEvidenceError("resource soak derived evidence drift")
        timing_fields = scale_timing_fields(
            target_scale=str(campaign.get("targetScale") or ""),
            plan=plan,
            predecessor_promotion_path=predecessor_path,
            resource=resource,
        )
        expected_campaign_resource = {
            "fourLaneOverlapDurationSeconds": resource[
                "fourLaneOverlapDurationSeconds"
            ],
            "fourLaneLongestContinuousOverlapSeconds": resource[
                "fourLaneLongestContinuousOverlapSeconds"
            ],
            "allSemanticJobsTerminalAt": resource["allSemanticJobsTerminalAt"],
            "terminalResidualSampleAt": resource["terminalResidualSampleAt"],
            **timing_fields,
        }
        if (
            campaign.get("resourceSoakEvidenceDigest") != resource_digest
            or resource.get("evidenceId") != campaign.get("evidenceId")
            or raw_samples_path.resolve() != bound_samples_path.resolve()
            or _file_sha256(raw_samples_path) != resource.get("rawSamplesSha256")
            or any(
                campaign.get(key) != value
                for key, value in expected_campaign_resource.items()
            )
            or any(resource.get(key) != campaign.get(key) for key in identity_keys)
        ):
            raise CampaignScaleEvidenceError(
                "resource soak diagnostic binding drift"
            )
        diagnostic_documents.append(resource)
    if fault_ref is not None:
        fault_path = _resolve_ref(
            str(fault_ref),
            output_root=output_root,
            label="fault injection evidence ref",
        )
        fault = _validated(
            fault_path,
            "release",
            "fault_injection_evidence",
            label="canonical fault injection evidence",
        )
        fault_digest = _verify_evidence_digest(fault, label="fault injection")
        raw_faults_path = _resolve_ref(
            str(fault["rawCasesRef"]),
            output_root=output_root,
            label="fault raw cases ref",
        )
        if fault_path.name != "fault-injection.json":
            raise CampaignScaleEvidenceError(
                "fault injection evidence path is non-canonical"
            )
        write_fault_injection_evidence(
            evidence_id=str(fault["evidenceId"]),
            campaign_plan_path=plan_path,
            raw_cases_path=raw_faults_path,
            tasks_root=output_root / "data/tasks",
            output_root=output_root,
            evidence_root=fault_path.parent,
        )
        if (
            campaign.get("faultInjectionEvidenceDigest") != fault_digest
            or fault.get("evidenceId") != campaign.get("evidenceId")
            or raw_faults_path.resolve() != bound_faults_path.resolve()
            or _file_sha256(raw_faults_path) != fault.get("rawCasesSha256")
            or any(fault.get(key) != campaign.get(key) for key in identity_keys)
        ):
            raise CampaignScaleEvidenceError("fault diagnostic binding drift")
        diagnostic_documents.append(fault)
    if not runtime_binding.documents_match_runtime_binding(
        tuple(diagnostic_documents),
        session,
        session_path=runtime_session_path,
        output_root=output_root,
    ):
        raise CampaignScaleEvidenceError(
            "campaign runtime diagnostic binding drift"
        )
    return resource, fault


__all__ = ["derive_runtime_diagnostic_fields", "load_campaign_diagnostics"]
