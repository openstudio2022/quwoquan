"""Pure aggregation of immutable lane source-pool bindings into a campaign plan."""
from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from content.execution.campaign.lane import CAMPAIGN_CARRIERS


def aggregate_plan_source_pool(
    submissions: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any] | None, str | None, dict[str, dict[str, Any]] | None]:
    bindings = {
        json.dumps(row.get("scaleSourcePool"), sort_keys=True, separators=(",", ":"))
        for row in submissions.values()
    }
    evidence_refs = {
        str(row.get("sourcePoolEvidenceRootRef") or "")
        for row in submissions.values()
    }
    if bindings == {"null"}:
        if evidence_refs != {""} or any(
            row.get("sourcePoolSelection") is not None
            for row in submissions.values()
        ):
            raise ValueError("DATA.SOURCE.POOL_SHORTFALL: incomplete campaign pool binding")
        return None, None, None
    if len(bindings) != 1 or len(evidence_refs) != 1:
        raise ValueError("DATA.SOURCE.POOL_SHORTFALL: campaign pool binding drift")
    binding = submissions["homepage"].get("scaleSourcePool")
    if not isinstance(binding, Mapping):
        raise TypeError("DATA.SOURCE.POOL_SHORTFALL: campaign pool binding invalid")
    selections: dict[str, dict[str, Any]] = {}
    for carrier in CAMPAIGN_CARRIERS:
        selection = submissions[carrier].get("sourcePoolSelection")
        if not isinstance(selection, Mapping) or selection.get("carrier") != carrier:
            raise ValueError(f"DATA.SOURCE.POOL_SHORTFALL: {carrier} pool selection drift")
        selections[carrier] = dict(selection)
    return dict(binding), next(iter(evidence_refs)), selections


__all__ = ["aggregate_plan_source_pool"]
