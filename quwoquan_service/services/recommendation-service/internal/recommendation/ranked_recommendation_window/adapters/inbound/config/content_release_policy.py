from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from ....domain.experiment_policy import (
    EXPERIMENT_ID,
    ExperimentPolicy,
    PolicyVariant,
    canonical_policy,
)


def load_content_release_policy(path: str) -> ExperimentPolicy:
    source = Path(path)
    if not source.is_file() or source.is_symlink():
        raise ValueError("content-release recommendation policy is unavailable")
    try:
        payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise ValueError("content-release recommendation policy is invalid") from error
    experiments = payload.get("experiments") if isinstance(payload, dict) else None
    if not isinstance(experiments, list):
        raise ValueError("content-release recommendation experiments are invalid")
    selected = next(
        (
            item
            for item in experiments
            if isinstance(item, dict) and item.get("id") == EXPERIMENT_ID
        ),
        None,
    )
    if not isinstance(selected, dict) or selected.get("enabled") is not True:
        raise ValueError("content-release recommendation experiment is unavailable")
    buckets = selected.get("buckets")
    if not isinstance(buckets, list):
        raise ValueError("content-release recommendation buckets are invalid")
    variants = tuple(_variant(item) for item in buckets)
    return canonical_policy(
        ExperimentPolicy(
            experiment_id=EXPERIMENT_ID,
            revision=1,
            status="running",
            variants=variants,
            starts_at=None,
            ends_at=None,
            updated_at=datetime(1970, 1, 1, tzinfo=timezone.utc),
            digest="",
        )
    )


def _variant(value: Any) -> PolicyVariant:
    if not isinstance(value, dict):
        raise ValueError("content-release recommendation bucket is invalid")
    name = str(value.get("name") or "")
    weight = value.get("weightPct")
    if isinstance(weight, bool) or not isinstance(weight, int):
        raise ValueError("content-release recommendation bucket weight is invalid")
    return PolicyVariant(
        key=name,
        allocation_basis_points=weight * 100,
    )
