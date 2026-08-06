"""Re-derive one resource sample from its frozen session observations."""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any

from content.release.canonical.campaign_scale_contract import (
    CARRIERS,
    CampaignScaleEvidenceError,
    _timestamp,
)


def _validate_process_registration(
    receipt: Mapping[str, Any], session: Mapping[str, Any]
) -> None:
    registrations = [session["controller"], *session["workers"]]
    expected = {int(row["pid"]): row for row in registrations}
    measurements = receipt["processMeasurements"]
    observed_pids = [int(row["pid"]) for row in measurements]
    if len(observed_pids) != len(set(observed_pids)):
        raise CampaignScaleEvidenceError("resource sample process PID is duplicated")
    by_registration: dict[int, list[Mapping[str, Any]]] = {}
    for row in measurements:
        by_registration.setdefault(int(row["registrationPid"]), []).append(row)
    if set(by_registration) != set(expected):
        raise CampaignScaleEvidenceError("resource sample process registration drift")
    for registration_pid, rows in by_registration.items():
        registration = expected[registration_pid]
        registered = [row for row in rows if row["isRegisteredProcess"] is True]
        if len(registered) != 1 or int(registered[0]["pid"]) != registration_pid:
            raise CampaignScaleEvidenceError(
                "resource sample registered process identity is not unique"
            )
        for row in rows:
            if (
                row["role"] != registration["role"]
                or row["carrier"] != registration["carrier"]
                or row["executionId"] != registration["executionId"]
                or int(row["pgid"]) != int(registration["pgid"])
            ):
                raise CampaignScaleEvidenceError(
                    "resource sample process-group scope drift"
                )
        root = registered[0]
        if root["processIdentityDigest"] != registration["processIdentityDigest"]:
            raise CampaignScaleEvidenceError(
                "resource sample registered process digest drift"
            )


def _validate_raw_projection(receipt: Mapping[str, Any]) -> None:
    raw = receipt["rawSample"]
    processes = receipt["processMeasurements"]
    queues = receipt["queueMeasurements"]
    workspaces = receipt["workspaceMeasurements"]
    controller = sum(
        int(row["rssBytes"]) for row in processes if row["role"] == "controller"
    )
    by_carrier = Counter()
    for row in processes:
        if row["role"] == "worker":
            by_carrier[str(row["carrier"])] += int(row["rssBytes"])
    captured_at = _timestamp(raw["capturedAt"], label="resource sample capturedAt")
    oldest_ready = [
        _timestamp(row["oldestReadyAt"], label="queue oldestReadyAt")
        for row in queues
        if row.get("oldestReadyAt") is not None
    ]
    expected = {
        "capturedAt": receipt["capturedAt"],
        "controllerRssBytes": controller,
        "nonVideoWorkerMaxRssBytes": max(
            by_carrier[carrier] for carrier in CARRIERS if carrier != "video"
        ),
        "videoWorkerMaxRssBytes": by_carrier["video"],
        "totalRssBytes": sum(int(row["rssBytes"]) for row in processes),
        "temporaryWorkspaceBytes": sum(int(row["bytes"]) for row in workspaces),
        "terminalResidualBytes": sum(
            int(row["bytes"])
            for row in workspaces
            if row["kind"] == "transaction_staging"
        ),
        "openFdCount": sum(int(row["openFdCount"]) for row in processes),
        "queueDepth": sum(int(row["queueDepth"]) for row in queues),
        "oldestReadyAgeSeconds": max(
            (max(0, int((captured_at - value).total_seconds())) for value in oldest_ready),
            default=0,
        ),
    }
    if any(raw.get(key) != value for key, value in expected.items()):
        raise CampaignScaleEvidenceError(
            f"resource sample raw projection drift: {receipt['sampleId']}"
        )


def validate_resource_receipt(
    receipt: Mapping[str, Any],
    *,
    session: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> None:
    _validate_process_registration(receipt, session)
    queue_lanes = {
        str(row.get("carrier")): str(row.get("executionId"))
        for row in receipt.get("queueMeasurements") or []
        if isinstance(row, Mapping)
    }
    if queue_lanes != plan.get("executionIds"):
        raise CampaignScaleEvidenceError("resource sample queue lane drift")
    _validate_raw_projection(receipt)


__all__ = ["validate_resource_receipt"]
