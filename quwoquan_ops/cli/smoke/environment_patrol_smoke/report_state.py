"""Build and settle the canonical environment Patrol smoke report."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import artifact_binding_report, external_aut_driver
from .constants import utc_now
from .session import (
    _account_enforcement_subject_digest,
    _evidence_class_for_runtime,
    _requires_account_closure,
    _resolved_media_base_urls,
    _resolved_owner_id,
    _resolved_persona_id,
    _uses_persisted_device_session,
)


def new_report(
    *,
    args: Any,
    runtime_env: str,
    api_contract_env: str,
    external_aut_required: bool,
) -> dict[str, Any]:
    return {
        "suiteId": "environment_page_smoke",
        "status": "failed",
        "startedAt": utc_now(),
        "endedAt": "",
        "environmentAlias": args.env_name,
        "rolloutStage": getattr(args, "rollout_stage", ""),
        "runtimeEnv": runtime_env,
        "apiContractEnv": api_contract_env,
        "composition": "production_remote",
        "evidenceClass": _evidence_class_for_runtime(runtime_env),
        "target": args.target,
        "platform": args.platform,
        "gatewayBaseUrl": args.gateway_base_url,
        "productOpsBaseUrl": args.product_ops_base_url,
        "rtcMediaConnectionUrl": args.rtc_media_connection_url,
        **_resolved_media_base_urls(args),
        "videoPlaybackCanaryWorkId": str(
            getattr(args, "video_playback_canary_work_id", "") or ""
        ).strip(),
        "accountClosureDisposableAck": (
            bool(getattr(args, "account_closure_disposable_ack", False))
            if _requires_account_closure(args)
            else False
        ),
        "persistedDeviceSession": _uses_persisted_device_session(args),
        "candidateDigest": str(
            getattr(args, "candidate_digest", "") or ""
        ).strip(),
        "controlledEdgeFault": {
            "requested": bool(
                getattr(args, "stackctl_controlled_edge_fault", False)
            ),
            "receipt": {},
        },
        "controlledSubjectDigest": _account_enforcement_subject_digest(args),
        "hasCurrentOwnerIdentity": bool(_resolved_owner_id(args)),
        "hasCurrentPersonaIdentity": bool(_resolved_persona_id(args)),
        "sessionSource": "",
        "releaseUatCasesPath": "",
        "remoteApiEvidence": {},
        "devices": [],
        "runs": [],
        "caseResults": [],
        "failureReason": "",
        "deviceInventoryPath": "",
        "evidenceRoot": "",
        "externalProductionAutJourneys": (
            external_aut_driver.new_external_aut_journey_set(
                required=external_aut_required
            )
        ),
        "externalProductionAutDriverArtifact": {},
    }


def write_report(path: Path, report: dict[str, Any]) -> None:
    artifact_binding_report.settle_tested_app_artifact_binding_report(report)
    external_aut_driver.settle_external_aut_journey_report(report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def finish_report(
    path: Path,
    report: dict[str, Any],
    *,
    status: str,
    reason: object,
    exit_code: int,
    devices: list[dict[str, Any]] | None = None,
) -> int:
    report["status"] = status
    report["failureReason"] = str(reason)
    if devices is not None:
        report["devices"] = devices
    report["endedAt"] = utc_now()
    write_report(path, report)
    return exit_code
