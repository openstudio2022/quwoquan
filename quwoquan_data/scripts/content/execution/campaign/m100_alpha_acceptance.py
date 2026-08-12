"""Bind M1000 semantic waves to the verified M100 Alpha milestone."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.io import read_json
from core.schema import assert_valid


class M100AlphaAcceptanceError(ValueError):
    """The M100 Alpha activation/readback/App UAT boundary is incomplete."""


def _digest(document: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(document), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _load_receipt(
    path: Path, *, output_root: Path, label: str
) -> tuple[dict[str, Any], str]:
    root = output_root.expanduser().resolve()
    if path.expanduser().is_symlink():
        raise M100AlphaAcceptanceError(f"{label} must not be a symlink")
    resolved = path.expanduser().resolve(strict=True)
    try:
        ref = resolved.relative_to(root).as_posix()
    except ValueError as exc:
        raise M100AlphaAcceptanceError(
            f"{label} must be below QWQ_OUTPUT_ROOT"
        ) from exc
    payload = read_json(resolved)
    if not isinstance(payload, Mapping):
        raise M100AlphaAcceptanceError(f"{label} must be an object")
    return dict(payload), ref


def _validate_promotion_receipt(
    promotion: Mapping[str, Any], *, output_root: Path
) -> None:
    ref = str(promotion.get("receiptRef") or "").strip()
    expected_file_digest = str(promotion.get("receiptDigest") or "").strip()
    if not ref or not expected_file_digest:
        raise M100AlphaAcceptanceError("M100 promotion receipt binding is incomplete")
    receipt, observed_ref = _load_receipt(
        output_root / ref,
        output_root=output_root,
        label="M100 promotion receipt",
    )
    if (
        observed_ref != ref
        or _file_digest((output_root / ref).resolve()) != expected_file_digest
    ):
        raise M100AlphaAcceptanceError("M100 promotion receipt digest drift")
    assert_valid(
        receipt,
        "release",
        "research_scale_promotion",
        label="M100 predecessor promotion",
    )
    expected = {
        "promotionId": promotion.get("promotionId"),
        "releaseId": promotion.get("releaseId"),
        "manifestDigest": promotion.get("manifestDigest"),
        "targetScale": "M100",
    }
    if any(receipt.get(field) != value for field, value in expected.items()):
        raise M100AlphaAcceptanceError("M100 promotion receipt identity drift")


def _exact_promotion_counts(promotion: Mapping[str, Any]) -> dict[str, int]:
    rows = promotion.get("carrierCounts")
    if not isinstance(rows, list):
        raise M100AlphaAcceptanceError("M100 promotion carrier counts are missing")
    observed = {
        str(row.get("carrier") or ""): int(row.get("totalUniqueFinalizedCount") or 0)
        for row in rows
        if isinstance(row, Mapping)
    }
    expected = {"homepage": 100, "article": 100, "image": 100, "video": 10}
    if observed != expected:
        raise M100AlphaAcceptanceError(
            "DATA.SCALE.ALPHA_M100_COUNT_MISMATCH: M100 promotion is not exactly "
            "100/100/100/10"
        )
    return observed


def _validate_readiness(
    readiness: Mapping[str, Any], *, promotion: Mapping[str, Any]
) -> None:
    assert_valid(
        dict(readiness),
        "release",
        "environment_release_readiness",
        label="M100 Alpha release readiness",
    )
    expected = {
        "schema": "quwoquan_data.environment_release_readiness",
        "environment": "alpha",
        "releaseId": promotion.get("releaseId"),
        "manifestDigest": promotion.get("manifestDigest"),
        "releaseClass": "research",
        "productLifecycleState": "research",
        "readinessPhase": "research",
        "passed": True,
    }
    if any(readiness.get(field) != value for field, value in expected.items()):
        raise M100AlphaAcceptanceError(
            "DATA.SCALE.ALPHA_M100_READBACK_DRIFT: Alpha readiness does not bind "
            "the promoted M100 research release"
        )
    counts = readiness.get("counts")
    if (
        not isinstance(counts, Mapping)
        or counts.get("entities") != 100
        or counts.get("posts") != 210
        or counts.get("premiumPlayableVideos") != 10
        or len(readiness.get("entityRefs") or []) != 100
        or len(readiness.get("postIds") or []) != 210
    ):
        raise M100AlphaAcceptanceError(
            "DATA.SCALE.ALPHA_M100_COUNT_MISMATCH: Alpha readback is not exactly "
            "100 homepages and 210 posts including 10 playable videos"
        )
    unsigned = dict(readiness)
    declared_checksum = str(unsigned.pop("verificationChecksum", ""))
    if declared_checksum != _digest(unsigned):
        raise M100AlphaAcceptanceError("Alpha readiness verificationChecksum drift")
    activation = readiness.get("activationEnvelope")
    if not isinstance(activation, Mapping):
        raise M100AlphaAcceptanceError("Alpha activation envelope is missing")
    activation_expected = {
        "environment": "alpha",
        "releaseId": promotion.get("releaseId"),
        "manifestDigest": promotion.get("manifestDigest"),
        "releaseClass": "research",
        "productLifecycleState": "research",
        "readinessPhase": "research",
        "appUatEnvelopeDigest": readiness.get("appUatEnvelopeDigest"),
    }
    if any(
        activation.get(field) != value for field, value in activation_expected.items()
    ):
        raise M100AlphaAcceptanceError("Alpha activation envelope identity drift")
    if readiness.get("activationEnvelopeDigest") != _digest(activation):
        raise M100AlphaAcceptanceError("Alpha activation envelope digest drift")
    app_envelope = readiness.get("appUatEnvelope")
    if not isinstance(app_envelope, Mapping) or readiness.get(
        "appUatEnvelopeDigest"
    ) != _digest(app_envelope):
        raise M100AlphaAcceptanceError("Alpha App UAT envelope digest drift")


def _validate_app_uat(
    receipt: Mapping[str, Any],
    *,
    readiness: Mapping[str, Any],
    readiness_digest: str,
) -> None:
    expected = {
        "schema": "quwoquan_ops.app_content_uat_receipt",
        "status": "passed",
        "targets": ["alpha-local"],
        "releaseId": readiness.get("releaseId"),
        "manifestDigest": readiness.get("manifestDigest"),
        "appUatEnvelopeDigest": readiness.get("appUatEnvelopeDigest"),
        "skipped": 0,
    }
    if any(receipt.get(field) != value for field, value in expected.items()):
        raise M100AlphaAcceptanceError(
            "DATA.SCALE.ALPHA_M100_APP_UAT_DRIFT: App UAT does not prove the "
            "same Alpha M100 release"
        )
    if readiness_digest not in set(receipt.get("readinessReceiptDigests") or []):
        raise M100AlphaAcceptanceError("Alpha App UAT readiness receipt digest drift")
    preflights = receipt.get("preflights")
    if not isinstance(preflights, list) or len(preflights) != 1:
        raise M100AlphaAcceptanceError("Alpha App UAT requires one exact preflight")
    preflight = preflights[0]
    if (
        not isinstance(preflight, Mapping)
        or preflight.get("target") != "alpha-local"
        or preflight.get("environment") != "alpha"
        or preflight.get("status") not in {"passed", "warning"}
        or preflight.get("exitCode") != 0
        or preflight.get("launchPolicy") != "test_live"
        or preflight.get("contentBindingState") != "bound"
        or preflight.get("releaseId") != readiness.get("releaseId")
        or preflight.get("manifestDigest") != readiness.get("manifestDigest")
        or preflight.get("readinessReceiptDigest") != readiness_digest
        or preflight.get("appUatEnvelope") != readiness.get("appUatEnvelope")
        or preflight.get("appUatPlan") != receipt.get("appUatPlan")
        or preflight.get("appUatPlanDigest") != receipt.get("appUatPlanDigest")
    ):
        raise M100AlphaAcceptanceError("Alpha App UAT preflight binding drift")
    runtime = receipt.get("runtimeBindings")
    alpha_runtime = runtime.get("alpha-local") if isinstance(runtime, Mapping) else None
    if (
        not isinstance(alpha_runtime, Mapping)
        or alpha_runtime.get("environment") != "alpha"
        or alpha_runtime.get("contentBindingState") != "bound"
        or alpha_runtime.get("releaseId") != readiness.get("releaseId")
        or alpha_runtime.get("manifestDigest") != readiness.get("manifestDigest")
        or alpha_runtime.get("readinessPhase") != "research"
    ):
        raise M100AlphaAcceptanceError("Alpha App UAT runtime binding drift")
    plan = receipt.get("appUatPlan")
    if not isinstance(plan, Mapping) or receipt.get("appUatPlanDigest") != _digest(
        plan
    ):
        raise M100AlphaAcceptanceError("Alpha App UAT plan digest drift")
    sample_plan = plan.get("stratifiedSamples")
    expected_distribution = {
        "homepage": 25,
        "article": 25,
        "image": 40,
        "video": 10,
    }
    if (
        not isinstance(sample_plan, Mapping)
        or sample_plan.get("milestone") != "M100"
        or sample_plan.get("selection") != "lexicographic_prefix_v1"
        or sample_plan.get("sampleCount") != 100
        or sample_plan.get("distribution") != expected_distribution
    ):
        raise M100AlphaAcceptanceError(
            "DATA.SCALE.ALPHA_M100_APP_UAT_SAMPLE_PLAN_INVALID: Alpha App UAT "
            "does not bind the exact M100 25/25/40/10 matrix"
        )
    raw_cases = sample_plan.get("cases")
    if not isinstance(raw_cases, list) or len(raw_cases) != 100:
        raise M100AlphaAcceptanceError("Alpha M100 App UAT sample plan is incomplete")
    planned: dict[str, tuple[str, str]] = {}
    planned_distribution: dict[str, int] = {
        carrier: 0 for carrier in expected_distribution
    }
    planned_object_ids: set[str] = set()
    for case in raw_cases:
        if not isinstance(case, Mapping):
            raise M100AlphaAcceptanceError("Alpha M100 App UAT sample case is invalid")
        sample_id = str(case.get("sampleId") or "").strip()
        carrier = str(case.get("carrier") or "").strip()
        object_id = str(case.get("objectId") or "").strip()
        if (
            not sample_id
            or sample_id in planned
            or carrier not in expected_distribution
            or not object_id
            or object_id in planned_object_ids
        ):
            raise M100AlphaAcceptanceError(
                "Alpha M100 App UAT sample identities are invalid"
            )
        planned[sample_id] = (carrier, object_id)
        planned_object_ids.add(object_id)
        planned_distribution[carrier] += 1
    if planned_distribution != expected_distribution:
        raise M100AlphaAcceptanceError("Alpha M100 App UAT sample distribution drift")
    runs = receipt.get("runs")
    if (
        not isinstance(runs, list)
        or not runs
        or receipt.get("executed") != len(runs)
        or any(not isinstance(run, Mapping) or run.get("exitCode") != 0 for run in runs)
    ):
        raise M100AlphaAcceptanceError("Alpha App UAT execution evidence is incomplete")
    release_runs = [
        run
        for run in runs
        if isinstance(run, Mapping)
        and run.get("suite") == "release-bound-search-and-video-page"
    ]
    if len(release_runs) != 1 or receipt.get("executedSamples") != 100:
        raise M100AlphaAcceptanceError(
            "DATA.SCALE.ALPHA_M100_APP_UAT_SAMPLE_EVIDENCE_MISSING: Alpha App "
            "UAT requires exactly 100 executed release-bound samples"
        )
    release_run = release_runs[0]
    sample_execution = release_run.get("sampleExecution")
    sample_digest = (
        _digest(sample_execution) if isinstance(sample_execution, Mapping) else ""
    )
    if (
        not isinstance(sample_execution, Mapping)
        or sample_execution.get("milestone") != "M100"
        or sample_execution.get("executedSampleCount") != 100
        or sample_execution.get("distribution") != expected_distribution
        or sample_execution.get("appUatPlanDigest")
        != receipt.get("appUatPlanDigest")
        or sample_execution.get("readinessReceiptDigest") != readiness_digest
        or release_run.get("executedSampleCount") != 100
        or release_run.get("sampleExecutionDigest") != sample_digest
        or receipt.get("sampleExecutionDigests") != [sample_digest]
    ):
        raise M100AlphaAcceptanceError(
            "Alpha M100 App UAT sample execution binding drift"
        )
    raw_evidence = sample_execution.get("samples")
    if not isinstance(raw_evidence, list) or len(raw_evidence) != 100:
        raise M100AlphaAcceptanceError("Alpha M100 App UAT sample reads are incomplete")
    observed_ids: set[str] = set()
    for row in raw_evidence:
        if not isinstance(row, Mapping):
            raise M100AlphaAcceptanceError("Alpha M100 App UAT sample read is invalid")
        sample_id = str(row.get("sampleId") or "").strip()
        expected_case = planned.get(sample_id)
        if (
            expected_case is None
            or sample_id in observed_ids
            or row.get("carrier") != expected_case[0]
            or row.get("sourceObjectId") != expected_case[1]
            or row.get("statusCode") != 200
            or row.get("returnedObjectId") != row.get("readObjectId")
            or not str(row.get("responseDigest") or "").startswith("sha256:")
            or not isinstance(row.get("responseBytes"), int)
            or int(row["responseBytes"]) <= 0
        ):
            raise M100AlphaAcceptanceError(
                "Alpha M100 App UAT sample read evidence drift"
            )
        observed_ids.add(sample_id)
    if observed_ids != set(planned):
        raise M100AlphaAcceptanceError("Alpha M100 App UAT sample coverage drift")


def bind_m100_alpha_acceptance(
    readiness_receipt: Path | None,
    app_uat_receipt: Path | None,
    *,
    predecessor_promotion: Mapping[str, Any],
    output_root: Path,
) -> dict[str, Any]:
    if readiness_receipt is None or app_uat_receipt is None:
        raise M100AlphaAcceptanceError(
            "DATA.SCALE.ALPHA_M100_ACCEPTANCE_MISSING: M1000 requires Alpha "
            "activation/readback and passed App UAT receipts"
        )
    _validate_promotion_receipt(predecessor_promotion, output_root=output_root)
    counts = _exact_promotion_counts(predecessor_promotion)
    readiness, readiness_ref = _load_receipt(
        readiness_receipt, output_root=output_root, label="Alpha readiness receipt"
    )
    app_uat, app_uat_ref = _load_receipt(
        app_uat_receipt, output_root=output_root, label="Alpha App UAT receipt"
    )
    _validate_readiness(readiness, promotion=predecessor_promotion)
    readiness_digest = _digest(readiness)
    _validate_app_uat(app_uat, readiness=readiness, readiness_digest=readiness_digest)
    return {
        "schema": "quwoquan_data.m100_alpha_acceptance_binding",
        "promotionId": str(predecessor_promotion["promotionId"]),
        "promotionReceiptRef": str(predecessor_promotion["receiptRef"]),
        "promotionReceiptDigest": str(predecessor_promotion["receiptDigest"]),
        "releaseId": str(predecessor_promotion["releaseId"]),
        "manifestDigest": str(predecessor_promotion["manifestDigest"]),
        "appUatEnvelopeDigest": str(readiness["appUatEnvelopeDigest"]),
        "activationEnvelopeDigest": str(readiness["activationEnvelopeDigest"]),
        "exactCounts": {**counts, "posts": 210},
        "readinessReceiptRef": readiness_ref,
        "readinessReceiptFileSha256": _file_digest(readiness_receipt.resolve()),
        "readinessReceiptDigest": readiness_digest,
        "appUatReceiptRef": app_uat_ref,
        "appUatReceiptFileSha256": _file_digest(app_uat_receipt.resolve()),
        "appUatReceiptDigest": _digest(app_uat),
        "appUatPlanDigest": str(app_uat["appUatPlanDigest"]),
        "executedSampleCount": 100,
        "sampleExecutionDigest": str(app_uat["sampleExecutionDigests"][0]),
    }


def validate_m100_alpha_acceptance_binding(
    binding: Mapping[str, Any], *, output_root: Path
) -> dict[str, Any]:
    assert_valid(
        dict(binding),
        "execution",
        "m100_alpha_acceptance_binding",
        label="M100 Alpha acceptance binding",
    )
    root = output_root.expanduser().resolve()
    readiness_path = root / str(binding["readinessReceiptRef"])
    app_uat_path = root / str(binding["appUatReceiptRef"])
    promotion = {
        "promotionId": binding["promotionId"],
        "receiptRef": binding["promotionReceiptRef"],
        "receiptDigest": binding["promotionReceiptDigest"],
        "releaseId": binding["releaseId"],
        "manifestDigest": binding["manifestDigest"],
        "carrierCounts": [
            {
                "carrier": carrier,
                "totalUniqueFinalizedCount": binding["exactCounts"][carrier],
            }
            for carrier in ("homepage", "article", "image", "video")
        ],
    }
    observed = bind_m100_alpha_acceptance(
        readiness_path,
        app_uat_path,
        predecessor_promotion=promotion,
        output_root=root,
    )
    if observed != dict(binding):
        raise M100AlphaAcceptanceError("M100 Alpha acceptance binding drift")
    return observed


__all__ = [
    "M100AlphaAcceptanceError",
    "bind_m100_alpha_acceptance",
    "validate_m100_alpha_acceptance_binding",
]
