"""Physical input resolvers shared by standalone scale-source executions."""

from __future__ import annotations

import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.io import read_json

from content.source.research.homepage_article_source_ready_batch import (
    CAPSULE_SCHEMA as SOURCE_READY_CAPSULE_SCHEMA,
)
from content.source.research.homepage_article_source_ready_batch import (
    validate_source_ready_candidate_capsule,
)


def direct_selected_rows(
    *,
    execution_id: str,
    carrier: str,
    direct_selection: Mapping[str, Any] | None,
    output_root: Path,
) -> tuple[Path, Path, dict[str, Any], list[dict[str, Any]]]:
    """Resolve one lane from its direct frozen binding, never by discovery."""

    if direct_selection is None:
        from content.execution import store

        spec = store.load_spec(execution_id)
        policy = spec.get("executionPolicy")
        if not isinstance(policy, Mapping):
            raise TypeError("executionPolicy is unavailable")
        source = policy
    else:
        source = direct_selection
    binding = source.get("scaleSourcePool")
    evidence_ref = source.get("sourcePoolEvidenceRootRef")
    selection = source.get("sourcePoolSelection")
    if (
        not isinstance(binding, Mapping)
        or not isinstance(selection, Mapping)
        or not str(evidence_ref or "").strip()
    ):
        raise ValueError("standalone source-pool runtime binding is incomplete")
    from content.execution.source_pool.binding import (
        validate_bound_scale_source_pool,
        validate_lane_source_pool_selection,
    )

    frozen_selection = validate_lane_source_pool_selection(
        selection,
        carrier=carrier,
        count=int(selection.get("candidateCount") or 0),
    )
    plan = validate_bound_scale_source_pool(
        binding,
        evidence_root_ref=str(evidence_ref),
        output_root=output_root,
    )
    selected_ids = tuple(str(value) for value in frozen_selection["candidateIds"])
    by_id = {
        str(row["candidateId"]): dict(row)
        for row in plan.get("candidates") or []
        if isinstance(row, Mapping) and row.get("carrier") == carrier
    }
    if any(candidate_id not in by_id for candidate_id in selected_ids):
        raise ValueError("standalone selected candidate is absent from frozen plan")
    evidence_root = (output_root / str(evidence_ref)).resolve()
    evidence_root.relative_to(output_root.resolve())
    return (
        output_root.resolve(),
        evidence_root,
        dict(binding),
        [by_id[value] for value in selected_ids],
    )


def source_ready_capsule(
    row: Mapping[str, Any], *, evidence_root: Path
) -> tuple[dict[str, Any], Path]:
    """Load one member-root-scoped source-ready capsule and reject path drift."""

    root_text = str(row.get("sourceReadyEvidenceRootRef") or "").strip()
    root_ref = Path(root_text)
    if (
        not root_text
        or root_ref.is_absolute()
        or (root_text != "." and ".." in root_ref.parts)
    ):
        raise ValueError("selected source-ready evidence root ref is unsafe")
    candidate_root = evidence_root
    root_parts = () if root_text == "." else root_ref.parts
    for part in root_parts:
        candidate_root = candidate_root / part
        mode = candidate_root.lstat().st_mode
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise ValueError("selected source-ready evidence root is invalid")
    relative = Path(str(row.get("sourceUnitRef") or ""))
    if not str(relative) or relative.is_absolute() or ".." in relative.parts:
        raise ValueError("selected source-ready candidate ref is unsafe")
    value = read_json(candidate_root / relative)
    if not isinstance(value, Mapping) or value.get("schema") != SOURCE_READY_CAPSULE_SCHEMA:
        raise TypeError("selected candidate is not a source-ready capsule")
    capsule = validate_source_ready_candidate_capsule(
        value, evidence_root=candidate_root
    )
    candidate = capsule["candidate"]
    checks = {
        "carrier": (capsule.get("carrier"), row.get("carrier")),
        "candidateId": (candidate.get("candidateId"), row.get("candidateId")),
        "entityRef": (candidate.get("entityRef"), row.get("entityRef")),
        "observedEntityRef": (
            candidate.get("observedEntityRef"),
            row.get("observedEntityRef"),
        ),
        **{
            field: (candidate.get(field), row.get(field))
            for field in ("sourceRevision", "sourceDigest", "entityCatalogDigest")
        },
    }
    drift = sorted(field for field, values in checks.items() if values[0] != values[1])
    if drift:
        raise ValueError(
            "selected candidate row drifts from its source-ready capsule: "
            + ", ".join(drift)
        )
    return capsule, candidate_root


__all__ = ["direct_selected_rows", "source_ready_capsule"]
