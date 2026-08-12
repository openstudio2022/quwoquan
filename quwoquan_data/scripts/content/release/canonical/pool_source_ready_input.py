"""Validate exact physical source-ready inputs for the next rolling wave."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from content.release.canonical.object_transaction_contract import _read_json
from content.source.research.scale_source_pool import (
    validate_scale_source_pool_evidence,
)
from core.schema import assert_valid

_CARRIERS = ("homepage", "article", "image", "video")


def _exact_output_path(
    output_root: Path,
    raw_ref: object,
    *,
    label: str,
) -> tuple[Path, str]:
    ref = Path(str(raw_ref or "").strip())
    if ref.is_absolute() or not ref.parts or ".." in ref.parts:
        raise ValueError(f"{label} must be one exact relative output ref")
    path = (output_root / ref).resolve()
    try:
        normalized = path.relative_to(output_root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"{label} escapes QWQ_OUTPUT_ROOT") from exc
    return path, normalized


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def load_source_ready_input(
    *,
    output_root: Path,
    publish_root: Path,
    milestone: str,
    source_pool_ref: str,
    evidence_root_ref: str,
    consumed_object_refs: frozenset[str] = frozenset(),
) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    """Return validated unconsumed candidates from one exact immutable pool."""

    pool_path, normalized_pool_ref = _exact_output_path(
        output_root,
        source_pool_ref,
        label="sourcePoolRef",
    )
    evidence_root, normalized_evidence_ref = _exact_output_path(
        output_root,
        evidence_root_ref,
        label="sourcePoolEvidenceRootRef",
    )
    plan = _read_json(pool_path)
    if plan.get("targetScale") != milestone:
        raise ValueError(
            "source-ready pool milestone drift: "
            f"expected={milestone} actual={plan.get('targetScale')}"
        )
    validation = validate_scale_source_pool_evidence(
        plan,
        evidence_root=evidence_root,
    )
    candidates = {carrier: [] for carrier in _CARRIERS}
    for raw in plan["candidates"]:
        row = dict(raw)
        carrier = str(row["carrier"])
        object_ref = str(row["objectRef"]).strip("/")
        # Any existing canonical manifest owns this stable object identity.
        # A later wave must not reinterpret it as fresh semantic work.
        if (
            object_ref in consumed_object_refs
            or (publish_root / object_ref / "manifest.json").is_file()
        ):
            continue
        candidates[carrier].append(
            {
                "carrier": carrier,
                "candidateId": str(row["candidateId"]),
                "objectRef": object_ref,
                "entityRef": str(row["entityRef"]),
                "sourceUnitRef": str(row["sourceUnitRef"]),
                "sourceReadyEvidenceRootRef": str(
                    row.get("sourceReadyEvidenceRootRef") or "."
                ),
            }
        )
    for rows in candidates.values():
        rows.sort(key=lambda item: (item["objectRef"], item["candidateId"]))
    return (
        {
            "status": "validated",
            "sourcePoolRef": normalized_pool_ref,
            "sourcePoolFileSha256": _file_sha256(pool_path),
            "sourcePoolDigest": str(plan["planDigest"]),
            "sourcePoolEvidenceRootRef": normalized_evidence_ref,
            "evidenceBindingCount": int(validation["evidenceBindingCount"]),
        },
        candidates,
    )


def load_p10_throughput(
    *,
    output_root: Path,
    promotion_ref: str,
) -> tuple[dict[str, float], dict[str, str]]:
    """Read deterministic p10 samples from one immutable promotion receipt."""

    path, normalized_ref = _exact_output_path(
        output_root,
        promotion_ref,
        label="throughputPromotionRef",
    )
    document = _read_json(path)
    assert_valid(
        document,
        "release",
        "research_scale_promotion",
        label="pool scheduling throughput promotion",
    )
    rows = document.get("capacityThroughputByCarrier")
    if not isinstance(rows, Sequence):
        raise ValueError("throughput promotion has no carrier samples")
    rates: dict[str, float] = {}
    for raw in rows:
        if not isinstance(raw, Mapping):
            raise ValueError("throughput promotion row is invalid")
        carrier = str(raw.get("carrier") or "")
        samples = raw.get("perSlotThroughputSamples")
        if carrier not in _CARRIERS or not isinstance(samples, list) or not samples:
            raise ValueError("throughput promotion carrier samples are incomplete")
        ordered = sorted(float(value) for value in samples)
        if any(value <= 0 for value in ordered):
            raise ValueError("throughput promotion samples must be positive")
        rank = max(0, math.ceil(len(ordered) * 0.1) - 1)
        rates[carrier] = ordered[rank]
    if set(rates) != set(_CARRIERS):
        raise ValueError("throughput promotion lacks four carriers")
    return rates, {
        "throughputPromotionRef": normalized_ref,
        "throughputPromotionFileSha256": _file_sha256(path),
    }


__all__ = ["load_p10_throughput", "load_source_ready_input"]
