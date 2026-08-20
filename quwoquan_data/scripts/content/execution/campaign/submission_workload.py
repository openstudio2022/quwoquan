"""Freeze the active carrier workload admitted into one submission."""

from __future__ import annotations

import fcntl
import hashlib
import json
import subprocess
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NamedTuple

from core import paths
from core.io import read_json, write_json
from core.schema import assert_valid
from core.source_digest import (
    current_execution_bundle_identity,
    current_source_definition_snapshot,
)

from content.execution.campaign.external_inputs import (
    content_source_revision,
    external_inputs_digest,
    verify_external_input_refs,
)
from content.execution.campaign.carrier_execution_policy import carrier_operation
from content.execution.campaign.lane import (
    CAMPAIGN_CARRIERS,
    normalize_active_carriers,
    normalize_workloads,
)
from content.execution.campaign.scale import execution_campaign_scale
from content.execution.closure.adoption_campaign_contract import (
    ADOPTION_OPERATIONS,
    CAMPAIGN_ADOPTION_FIELD,
)
from content.execution.identity import parse_execution_id, validate_execution_id
from content.execution.model_contract import (
    CURSOR_AUTO_SEMANTIC_SELECTION_ID,
    DEFAULT_SEMANTIC_SELECTION_ID,
    normalize_semantic_selection_id,
)
from content.execution.planning.semantic_preflight_admission import (
    bind_semantic_preflight_receipt,
    validate_semantic_preflight_binding_at,
)
from content.execution.planning.semantic_failover_admission import (
    require_cursor_auto_retry_admission,
)
from content.execution.request import RuntimeExecutionRequest
from content.execution.workspace import entity_catalog_digest

SUBMISSION_SCHEMA = "quwoquan_data.content_execution_submission"


from content.execution.campaign.submission_identity import (
    _assert_no_cross_campaign_collision,
    _git_branch,
    _git_commit,
    _require_stable_source_inputs,
    _sha256,
    _submission_lock,
    _utc_now,
    campaign_root,
    campaigns_root,
    submission_path,
)


class _FrozenWorkload(NamedTuple):
    workload_mode: str
    active_carriers: tuple[str, ...]
    workloads: dict[str, int]


def _frozen_workload(
    campaign_envelope: Mapping[str, Any] | None,
    *,
    carrier: str,
    quota: int,
    active_carriers: Iterable[str] | None,
    workloads: Mapping[str, int] | None,
    workload_mode: str,
) -> _FrozenWorkload:
    """Resolve the one active workload this submission is allowed to join.

    An immutable campaign envelope already froze the workload, so it is the only
    authority once present; a CLI-supplied workload may then only reproduce it
    byte-for-byte.  Without an envelope the caller states the workload directly,
    and an unstated carrier subset means the complete canonical preset, which is
    the same rule ``freeze_campaign_request_envelopes`` applies.
    """

    if campaign_envelope is not None:
        frozen = _FrozenWorkload(
            str(campaign_envelope["workloadMode"]),
            normalize_active_carriers(campaign_envelope["activeCarriers"]),
            normalize_workloads(
                campaign_envelope["workloads"],
                active_carriers=normalize_active_carriers(
                    campaign_envelope["activeCarriers"]
                ),
            ),
        )
        requested = (
            None
            if active_carriers is None
            else normalize_active_carriers(active_carriers)
        )
        if (
            (requested is not None and requested != frozen.active_carriers)
            or (
                workloads is not None
                and normalize_workloads(
                    workloads,
                    active_carriers=frozen.active_carriers,
                )
                != frozen.workloads
            )
            or workload_mode not in {"explicit", frozen.workload_mode}
        ):
            raise ValueError(
                "GATE_BLOCK DATA.CAMPAIGN.EXTERNAL_INPUT_IDENTITY_DRIFT: "
                "CLI active workload differs from the immutable campaign envelope"
            )
    else:
        if workload_mode not in {"explicit", "milestone_preset"}:
            raise ValueError(f"unsupported campaign workload mode: {workload_mode}")
        active = normalize_active_carriers(active_carriers or CAMPAIGN_CARRIERS)
        if workload_mode == "milestone_preset" and active != CAMPAIGN_CARRIERS:
            raise ValueError("milestone preset must expand all campaign carriers")
        frozen = _FrozenWorkload(
            workload_mode,
            active,
            (
                {selected: quota for selected in active}
                if workloads is None
                else normalize_workloads(workloads, active_carriers=active)
            ),
        )
    if carrier not in frozen.active_carriers:
        raise ValueError(f"campaign submission carrier {carrier} is not active")
    return frozen
