"""Data-owned pool-delivery preflight, independent from semantic providers."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.schema import assert_valid
from core.paths import OUTPUT_ROOT

from content.execution.campaign.external_input_runtime import (
    execution_external_input_envelope_path,
    load_execution_external_input_envelope,
)
from content.execution.campaign.fleet_transport import (
    resolve_campaign_fleet_transport,
)
from content.execution.campaign.observer_binary import (
    resolve_campaign_observer_binary,
)
from content.execution.campaign.plan import sha256_payload
from content.execution.campaign.runtime import read_runtime_snapshot
from content.execution.campaign.workspace import CampaignRuntimePaths
from content.execution.identity import validate_execution_id
from content.execution.queue.backend import load_execution_queue_backend
from content.execution.queue.reliabletask.transport import (
    ReliableTaskFleetTransport,
    pool_delivery_fleet_preflight,
    require_pool_delivery_fleet_transport,
    resolve_reliabletask_fleet_transport,
)
from content.execution.runtime_evidence.reliabletask_observer_build import (
    prepare_controller_observer_binary,
)
from content.execution.workspace import (
    execution_root,
    load_frozen_execution_manifest,
    load_frozen_target_set,
)

POOL_DELIVERY_UNAVAILABLE = "DATA.POOL.DELIVERY_UNAVAILABLE"


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _delivery_runtime_binding(
    execution_id: str,
    envelope: Mapping[str, Any],
) -> tuple[
    dict[str, str],
    int,
    str,
    dict[str, object] | None,
    ReliableTaskFleetTransport | None,
]:
    """Recover delivery authority from frozen files, never transient lane env."""

    execution_dir = execution_root(execution_id)
    external_envelope_path = execution_external_input_envelope_path(execution_dir)
    if external_envelope_path.is_file():
        external = load_execution_external_input_envelope(external_envelope_path)
        runtime = CampaignRuntimePaths.defaults()
        root_execution_id = validate_execution_id(str(external["rootExecutionId"]))
        plan_path = runtime.campaigns_root / root_execution_id / "campaign_plan.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        if not isinstance(plan, dict):
            raise TypeError("pool delivery campaign plan must be an object")
        assert_valid(
            plan,
            "execution",
            "content_campaign_plan",
            label=f"pool delivery campaign plan:{root_execution_id}",
        )
        stable_plan = {key: value for key, value in plan.items() if key != "planDigest"}
        if plan.get("planDigest") != sha256_payload(stable_plan):
            raise ValueError("pool delivery campaign plan digest drift")
        carrier = str(external.get("carrier") or "").strip()
        execution_ids = plan.get("executionIds")
        snapshot = read_runtime_snapshot(runtime, root_execution_id)
        manifest = load_frozen_execution_manifest(execution_id)
        source_digest = manifest.get("sourceDigest")
        target_set = load_frozen_target_set(execution_id)
        if (
            external.get("executionId") != execution_id
            or not isinstance(execution_ids, Mapping)
            or execution_ids.get(carrier) != execution_id
            or external.get("planDigest") != plan.get("planDigest")
            or external.get("sourceRevision") != plan.get("sourceRevision")
            or external.get("sourceDigest") != plan.get("sourceDigest")
            or external.get("entityCatalogDigest")
            != plan.get("entityCatalogDigest")
            or not isinstance(source_digest, Mapping)
            or source_digest.get("digest") != plan.get("sourceDigest")
            or target_set.get("entityCatalogDigest")
            != plan.get("entityCatalogDigest")
            or not isinstance(snapshot, Mapping)
            or snapshot.get("rootExecutionId") != root_execution_id
            or snapshot.get("planDigest") != plan.get("planDigest")
        ):
            raise ValueError("pool delivery campaign source/fence identity drift")
        generation = snapshot.get("generation")
        run_id = str(snapshot.get("runId") or "").strip()
        fencing_token = str(snapshot.get("fencingToken") or "").strip()
        if (
            isinstance(generation, bool)
            or not isinstance(generation, int)
            or generation < 1
            or not run_id
            or not fencing_token.startswith("sha256:")
        ):
            raise ValueError("pool delivery campaign runtime fence is invalid")
        distributed = plan.get("distributedRun")
        if isinstance(distributed, Mapping) and (
            distributed.get("campaignRunId") != run_id
            or distributed.get("campaignGeneration") != generation
            or distributed.get("campaignFencingToken") != fencing_token
        ):
            raise ValueError("pool delivery distributed campaign fence drift")
        plan_digest = str(plan["planDigest"])
        worker = resolve_campaign_observer_binary(
            runtime,
            root_execution_id,
            plan_digest=plan_digest,
        )
        fleet = resolve_campaign_fleet_transport(
            runtime,
            root_execution_id,
            plan_digest=plan_digest,
            preparer=require_pool_delivery_fleet_transport,
        )
        campaign_binding = {
            "rootExecutionId": root_execution_id,
            "campaignRunId": run_id,
            "campaignGeneration": generation,
            "campaignFencingToken": fencing_token,
            "campaignPlanDigest": plan_digest,
            "campaignSourceRevision": str(plan["sourceRevision"]),
            "campaignSourceDigest": str(plan["sourceDigest"]),
            "campaignEntityCatalogDigest": str(plan["entityCatalogDigest"]),
        }
        return (
            worker.as_document(),
            generation,
            fencing_token,
            campaign_binding,
            fleet.transport,
        )
    if envelope.get("scaleClass") in {"M100_PLUS", "M10000_PLUS"}:
        # A carrier-selective semantic-wave dispatch is deliberately not a
        # four-lane campaign root.  Its standalone delivery authority is still
        # fully frozen: v2 source/executor identity, exact physical pool plan,
        # exact candidate selection, target catalog and the immutable queue
        # envelope form one delivery fence.  Requiring a synthetic campaign
        # root here coupled otherwise independent carrier waves and made a
        # healthy Data fleet unusable after review.
        manifest = load_frozen_execution_manifest(execution_id)
        source_digest = manifest.get("sourceDigest")
        execution_bundle = manifest.get("executionBundle")
        target_set = load_frozen_target_set(execution_id)
        request_path = execution_dir / "0.plan/request.json"
        request = json.loads(request_path.read_text(encoding="utf-8"))
        pool = request.get("scaleSourcePool") if isinstance(request, Mapping) else None
        selection = (
            request.get("sourcePoolSelection")
            if isinstance(request, Mapping)
            else None
        )
        evidence_root_ref = (
            request.get("sourcePoolEvidenceRootRef")
            if isinstance(request, Mapping)
            else None
        )
        if (
            not isinstance(source_digest, Mapping)
            or not str(source_digest.get("digest") or "").startswith("sha256:")
            or not isinstance(execution_bundle, Mapping)
            or not str(execution_bundle.get("digest") or "").startswith("sha256:")
            or not isinstance(pool, Mapping)
            or pool.get("entityCatalogDigest")
            != target_set.get("entityCatalogDigest")
            or not str(evidence_root_ref or "").strip()
            or not str(pool.get("planRef") or "").strip()
            or not str(pool.get("planDigest") or "").startswith("sha256:")
            or not str(pool.get("planFileSha256") or "").startswith("sha256:")
            or not isinstance(selection, Mapping)
            or selection.get("carrier")
            not in {"homepage", "article", "image", "video"}
            or not isinstance(selection.get("candidateIds"), list)
            or len(selection["candidateIds"]) < 1
            or selection.get("candidateCount") != len(selection["candidateIds"])
            or not str(selection.get("selectionDigest") or "").startswith("sha256:")
        ):
            raise ValueError(
                "standalone M100+ pool delivery source/selection fence is invalid"
            )
        # The semantic execution snapshot and the physical source-pool plan are
        # deliberately separate identities.  Revalidate both exact frozen
        # documents, then prove that this lane selection is a member of the
        # byte-verified plan; never require their source digests to be equal.
        from content.execution.campaign.source_pool_binding import (
            validate_bound_scale_source_pool,
            validate_lane_source_pool_selection,
        )

        frozen_selection = validate_lane_source_pool_selection(
            selection,
            carrier=str(selection["carrier"]),
            count=int(selection["candidateCount"]),
        )
        plan = validate_bound_scale_source_pool(
            pool,
            evidence_root_ref=str(evidence_root_ref),
            output_root=OUTPUT_ROOT,
        )
        selected_ids = tuple(str(value) for value in frozen_selection["candidateIds"])
        plan_ids = {
            str(row.get("candidateId") or "")
            for row in plan.get("candidates") or []
            if isinstance(row, Mapping)
            and row.get("carrier") == frozen_selection["carrier"]
        }
        if any(candidate_id not in plan_ids for candidate_id in selected_ids):
            raise ValueError(
                "standalone M100+ pool delivery selection is absent from frozen plan"
            )
    binding = prepare_controller_observer_binary().binding
    token = str(envelope.get("envelopeDigest") or "").strip()
    if not token.startswith("sha256:"):
        raise ValueError("pool delivery queue envelope digest is invalid")
    return binding.as_document(), 1, token, None, None


def build_pool_delivery_preflight_report(
    execution_id: str,
    *,
    fleet_probe: Callable[[], Mapping[str, object]] | None = None,
    transport_resolver: Callable[[], ReliableTaskFleetTransport] | None = None,
) -> dict[str, Any]:
    """Probe only the durable delivery plane and its frozen worker identity."""

    normalized = validate_execution_id(execution_id)
    envelope = load_execution_queue_backend(normalized)
    if envelope.get("poolDeliveryBackend") != "reliabletask":
        raise ValueError("pool delivery backend must be reliabletask")
    base = {
        "schema": "quwoquan_data.pool_delivery_preflight",
        "preflightProfile": "pool-delivery",
        "executionId": normalized,
        "target": "data-local",
        "queueBackendEnvelopeDigest": envelope["envelopeDigest"],
    }
    try:
        worker, generation, fencing_token, campaign_binding, frozen_transport = (
            _delivery_runtime_binding(normalized, envelope)
        )
        worker_ref = str(worker.get("observerBinaryRef") or "").strip()
        worker_sha = str(worker.get("observerBinarySha256") or "").strip()
        if not worker_ref or not worker_sha.startswith("sha256:"):
            raise ValueError("pool delivery worker binding is incomplete")
        transport = frozen_transport or (
            transport_resolver or resolve_reliabletask_fleet_transport
        )()
        fleet = dict(
            fleet_probe()
            if fleet_probe is not None
            else pool_delivery_fleet_preflight(transport)
        )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        return {
            **base,
            "mongo": False,
            "redis": False,
            "owned": False,
            "poolDeliveryReady": False,
            "ready": False,
            "issueCode": POOL_DELIVERY_UNAVAILABLE,
            "issues": [
                "Data pool delivery transport unavailable: "
                f"{type(exc).__name__}"
            ],
        }
    transport_digest = _digest(
        {
            "target": transport.target,
            "mongoUri": transport.mongo_uri,
            "redisAddr": transport.redis_addr,
        }
    )
    target = str(fleet.get("target") or transport.target).strip()
    mongo = fleet.get("mongo") is True
    redis = fleet.get("redis") is True
    owned = fleet.get("owned") is True
    ready = bool(
        target == "data-local"
        and fleet.get("ready") is True
        and mongo
        and redis
        and owned
    )
    return {
        "schema": "quwoquan_data.pool_delivery_preflight",
        **base,
        "target": target,
        "transportDigest": transport_digest,
        "queueBackendEnvelopeDigest": envelope["envelopeDigest"],
        "deliveryGeneration": generation,
        "deliveryFencingToken": fencing_token,
        "workerRef": worker_ref,
        "workerSha256": worker_sha,
        "campaignBinding": campaign_binding,
        "mongo": mongo,
        "redis": redis,
        "owned": owned,
        "poolDeliveryReady": ready,
        "ready": ready,
        "issueCode": None if ready else POOL_DELIVERY_UNAVAILABLE,
        "issues": [] if ready else ["dedicated Data pool delivery fleet is not writable"],
    }


def build_pool_delivery_preflight_receipt(
    report: Mapping[str, Any],
) -> dict[str, Any]:
    if report.get("preflightProfile") != "pool-delivery":
        raise ValueError("pool delivery preflight profile mismatch")
    ready = report.get("poolDeliveryReady") is True
    if not ready:
        raise ValueError("pool delivery preflight receipt requires ready evidence")
    evidence = {
        key: report[key]
        for key in (
            "preflightProfile",
            "executionId",
            "target",
            "transportDigest",
            "queueBackendEnvelopeDigest",
            "deliveryGeneration",
            "deliveryFencingToken",
            "workerRef",
            "workerSha256",
            "campaignBinding",
            "mongo",
            "redis",
            "owned",
            "poolDeliveryReady",
            "issueCode",
        )
    }
    stable = {
        "schema": "quwoquan_data.pool_delivery_preflight_receipt",
        "recordedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        **evidence,
        "evidenceDigest": _digest(evidence),
    }
    receipt = {"receiptId": _digest(stable), **stable}
    validate_pool_delivery_preflight_receipt(receipt)
    return receipt


def validate_pool_delivery_preflight_receipt(
    receipt: Mapping[str, Any],
    *,
    expected_execution_id: str | None = None,
    minimum_generation: int | None = None,
    expected_fencing_token: str | None = None,
) -> None:
    payload = dict(receipt)
    assert_valid(
        payload,
        "execution",
        "pool_delivery_preflight_receipt",
        label="pool delivery preflight receipt",
    )
    stable = {key: value for key, value in payload.items() if key != "receiptId"}
    if _digest(stable) != payload["receiptId"]:
        raise ValueError("pool delivery preflight receiptId mismatch")
    evidence = {
        key: payload[key]
        for key in (
            "preflightProfile",
            "executionId",
            "target",
            "transportDigest",
            "queueBackendEnvelopeDigest",
            "deliveryGeneration",
            "deliveryFencingToken",
            "workerRef",
            "workerSha256",
            "campaignBinding",
            "mongo",
            "redis",
            "owned",
            "poolDeliveryReady",
            "issueCode",
        )
    }
    if _digest(evidence) != payload["evidenceDigest"]:
        raise ValueError("pool delivery preflight evidenceDigest mismatch")
    if not all(payload[field] is True for field in ("mongo", "redis", "owned", "poolDeliveryReady")):
        raise ValueError("pool delivery preflight readiness is inconsistent")
    if payload["issueCode"] is not None:
        raise ValueError("ready pool delivery preflight cannot carry an issue code")
    campaign = payload["campaignBinding"]
    if campaign is not None and (
        campaign["campaignGeneration"] != payload["deliveryGeneration"]
        or campaign["campaignFencingToken"]
        != payload["deliveryFencingToken"]
    ):
        raise ValueError("pool delivery campaign fence binding is inconsistent")
    if expected_execution_id is not None and payload["executionId"] != expected_execution_id:
        raise ValueError("pool delivery preflight executionId mismatch")
    if minimum_generation is not None and payload["deliveryGeneration"] < minimum_generation:
        raise ValueError("pool delivery preflight generation is stale")
    if (
        expected_fencing_token is not None
        and payload["deliveryFencingToken"] != expected_fencing_token
    ):
        raise ValueError("pool delivery preflight fencing token is stale")


def write_pool_delivery_preflight_receipt(
    path: Path,
    receipt: Mapping[str, Any],
) -> Path:
    validate_pool_delivery_preflight_receipt(receipt)
    encoded = (json.dumps(dict(receipt), ensure_ascii=False, indent=2) + "\n").encode()
    destination = path.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError as exc:
        if destination.read_bytes() != encoded:
            raise ValueError("pool delivery preflight receipt create-once collision") from exc
        return destination
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    return destination


def record_pool_delivery_preflight(
    execution_id: str,
    *,
    fleet_probe: Callable[[], Mapping[str, object]] | None = None,
    transport_resolver: Callable[[], ReliableTaskFleetTransport] | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None, Path | None]:
    report = build_pool_delivery_preflight_report(
        execution_id,
        fleet_probe=fleet_probe,
        transport_resolver=transport_resolver,
    )
    if not report["poolDeliveryReady"]:
        return report, None, None
    receipt = build_pool_delivery_preflight_receipt(report)
    path = (
        execution_root(execution_id)
        / "evidence/pool-delivery/preflight"
        / f"{str(receipt['receiptId'])[7:]}.json"
    )
    write_pool_delivery_preflight_receipt(path, receipt)
    return report, receipt, path


def load_current_pool_delivery_preflight_receipt(
    execution_id: str,
) -> tuple[dict[str, Any], Path]:
    normalized = validate_execution_id(execution_id)
    report = build_pool_delivery_preflight_report(normalized)
    if report.get("poolDeliveryReady") is not True:
        raise RuntimeError(POOL_DELIVERY_UNAVAILABLE)
    expected_evidence = build_pool_delivery_preflight_receipt(report)[
        "evidenceDigest"
    ]
    root = execution_root(normalized) / "evidence/pool-delivery/preflight"
    matches: list[tuple[dict[str, Any], Path]] = []
    for path in sorted(root.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                continue
            validate_pool_delivery_preflight_receipt(
                payload,
                expected_execution_id=normalized,
            )
        except (OSError, TypeError, ValueError):
            continue
        if payload.get("evidenceDigest") == expected_evidence:
            matches.append((payload, path))
    if not matches:
        raise ValueError("current pool delivery preflight receipt is missing")
    matches.sort(key=lambda item: (str(item[0]["recordedAt"]), item[1].name))
    return matches[-1]


def run_pool_delivery_preflight(args: argparse.Namespace) -> dict[str, Any]:
    """CLI profile hook; parser/printing remain owned by the task preflight facade."""

    execution_id = validate_execution_id(str(getattr(args, "execution_id", "") or ""))
    report = build_pool_delivery_preflight_report(execution_id)
    receipt_out = getattr(args, "receipt_out", None)
    if receipt_out and report["poolDeliveryReady"]:
        destination = Path(str(receipt_out)).expanduser().resolve()
        root = execution_root(execution_id).resolve()
        try:
            destination.relative_to(root)
        except ValueError as exc:
            raise ValueError(
                "pool delivery receipt must be inside its execution work package"
            ) from exc
        receipt = build_pool_delivery_preflight_receipt(report)
        write_pool_delivery_preflight_receipt(destination, receipt)
        report["receiptRef"] = destination.relative_to(root).as_posix()
        report["receiptId"] = receipt["receiptId"]
    return report


__all__ = [
    "POOL_DELIVERY_UNAVAILABLE",
    "build_pool_delivery_preflight_receipt",
    "build_pool_delivery_preflight_report",
    "load_current_pool_delivery_preflight_receipt",
    "record_pool_delivery_preflight",
    "run_pool_delivery_preflight",
    "validate_pool_delivery_preflight_receipt",
    "write_pool_delivery_preflight_receipt",
]
