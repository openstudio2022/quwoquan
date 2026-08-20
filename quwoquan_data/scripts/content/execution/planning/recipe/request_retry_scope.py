"""Frozen predecessor and retry-scope derivation for execution requests."""

from __future__ import annotations

import argparse
import subprocess
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

from content.execution.planning.recipe.request_predecessors import (
    submission_only_predecessor_target_names,
    terminal_campaign_predecessor_target_names,
)
from content.execution.planning.retry_unfinished_scope import (
    RetryUnfinishedScope,
    load_retry_unfinished_scope,
)


def resolve_frozen_selection(
    recipe: dict[str, Any],
    request: Any,
    *,
    repo_root: Path,
    vertical: str,
    content_type: str,
    intent: str,
) -> dict[str, Any]:
    """Project runtime-only scope into one execution selection."""
    selection = dict(recipe.get("selection") or {})
    discovery = (
        repo_root
        / "quwoquan_data/reference"
        / vertical
        / "entities"
        / request.region_ref
    )
    name = request.topic or f"{request.region_ref.rsplit('/', 1)[-1]}-{content_type}"
    selection.update(
        {
            "region": request.region_ref,
            "discovery": discovery.relative_to(repo_root).as_posix(),
            "name": name,
            "title": name,
            "intentLabel": intent,
            "limit": request.count,
            "approvedQuota": request.quota,
            "capacityCalibration": dict(request.capacity_calibration),
            "workerHostSetBinding": (
                dict(request.worker_host_set_binding)
                if request.worker_host_set_binding is not None
                else None
            ),
            "scaleSourcePool": (
                dict(request.scale_source_pool)
                if request.scale_source_pool is not None
                else None
            ),
            "sourcePoolEvidenceRootRef": request.source_pool_evidence_root_ref,
            "sourcePoolSelection": (
                dict(request.source_pool_selection)
                if request.source_pool_selection is not None
                else None
            ),
        }
    )
    return selection


EXTERNAL_MEDIA_CARRIERS: tuple[str, ...] = ("image", "video")


def predecessor_target_names_without_target_set(
    retry_of: str | None,
) -> tuple[str, ...] | None:
    return submission_only_predecessor_target_names(
        retry_of
    ) or terminal_campaign_predecessor_target_names(retry_of)


def _external_media_scope_block(retry_of: str, detail: str) -> SystemExit:
    return SystemExit(
        f"[task execute] GATE_BLOCK retryOf={retry_of}: "
        f"EXTERNAL_MEDIA_RETRY_SCOPE_INVALID {detail}"
    )


def frozen_campaign_retry_request(
    retry_of: str,
    *,
    carrier: str,
    campaign_envelope: str | None,
    campaign_root_execution_id: str | None,
) -> dict[str, Any]:
    """Load the exact campaign request this retry lane was frozen against."""
    from content.execution.campaign import request_envelope_io
    from content.execution.campaign import submission as campaign_submission

    envelope_ref = str(campaign_envelope or "").strip()
    if envelope_ref:
        try:
            payload = request_envelope_io.load_campaign_envelope(Path(envelope_ref))
        except (OSError, TypeError, ValueError) as exc:
            raise _external_media_scope_block(retry_of, str(exc)) from exc
    else:
        root_execution_id = str(campaign_root_execution_id or "").strip()
        if not root_execution_id:
            raise _external_media_scope_block(
                retry_of,
                "campaign lane retry requires --campaign-envelope or "
                "--campaign-root-execution-id",
            )
        try:
            submissions = campaign_submission.load_submissions(root_execution_id)
        except (OSError, TypeError, ValueError) as exc:
            raise _external_media_scope_block(retry_of, str(exc)) from exc
        payload = submissions.get(carrier)
    if not isinstance(payload, dict):
        raise _external_media_scope_block(
            retry_of, f"{carrier} campaign request is missing"
        )
    return payload


def _frozen_campaign_target_names(
    request: dict[str, Any],
    retry_of: str,
    *,
    execution_id: str,
    carrier: str,
    block: Callable[[str, str], SystemExit],
) -> tuple[str, ...]:
    if (
        str(request.get("executionId") or "") != execution_id
        or str(request.get("carrier") or "") != carrier
        or str(request.get("retryOf") or "") != retry_of
    ):
        raise block(retry_of, "campaign request lane identity drift")
    names = request.get("targetNames")
    if not isinstance(names, list) or any(
        not isinstance(name, str) or not name.strip() for name in names
    ):
        raise block(retry_of, "campaign request targetNames are invalid")
    resolved = tuple(names)
    if len(set(resolved)) != len(resolved):
        raise block(retry_of, "campaign request targetNames repeat an entity")
    return resolved


def external_media_retry_target_names(
    retry_of: str,
    *,
    execution_id: str,
    carrier: str,
    requested_target_names: tuple[str, ...],
    campaign_envelope: str | None,
    campaign_root_execution_id: str | None,
) -> tuple[str, ...]:
    """Scope an image/video retry to its own frozen campaign request.

    An external-media lane carries its work in `externalInputRefs`, so its
    `targetNames` is legitimately empty and the predecessor frozen target set
    holds no entity rows to inherit.  Reading the predecessor here would invent
    targets the lane never requested.
    """
    request = frozen_campaign_retry_request(
        retry_of,
        carrier=carrier,
        campaign_envelope=campaign_envelope,
        campaign_root_execution_id=campaign_root_execution_id,
    )
    return external_media_retry_scope_names(
        request,
        retry_of,
        execution_id=execution_id,
        carrier=carrier,
        requested_target_names=requested_target_names,
    )


def external_media_retry_scope_names(
    request: dict[str, Any],
    retry_of: str,
    *,
    execution_id: str,
    carrier: str,
    requested_target_names: tuple[str, ...],
) -> tuple[str, ...]:
    if carrier not in EXTERNAL_MEDIA_CARRIERS:
        raise _external_media_scope_block(
            retry_of, f"{carrier} is not an external-media carrier"
        )
    names = _frozen_campaign_target_names(
        request,
        retry_of,
        execution_id=execution_id,
        carrier=carrier,
        block=_external_media_scope_block,
    )
    refs = request.get("externalInputRefs")
    if not isinstance(refs, list) or not refs:
        raise _external_media_scope_block(
            retry_of, "campaign request externalInputRefs are missing"
        )
    if requested_target_names and requested_target_names != names:
        raise _external_media_scope_block(
            retry_of, "--target must match the frozen campaign targetNames exactly"
        )
    return names


def _reconciled_scope_block(retry_of: str, detail: str) -> SystemExit:
    return SystemExit(
        f"[task execute] GATE_BLOCK retryOf={retry_of}: "
        f"RECONCILED_CAMPAIGN_RETRY_SCOPE_INVALID {detail}"
    )


def reconciled_campaign_retry_target_names(
    retry_of: str,
    *,
    execution_id: str,
    carrier: str,
    count: int,
    quota: int,
    requested_target_names: tuple[str, ...],
    campaign_envelope: str | None,
    campaign_root_execution_id: str | None = None,
) -> tuple[str, ...]:
    """Scope a reconciled-campaign retry to the exact frozen envelope subset."""
    request = frozen_campaign_retry_request(
        retry_of,
        carrier=carrier,
        campaign_envelope=campaign_envelope,
        campaign_root_execution_id=campaign_root_execution_id,
    )
    return reconciled_campaign_retry_scope_names(
        request,
        retry_of,
        execution_id=execution_id,
        carrier=carrier,
        count=count,
        quota=quota,
        requested_target_names=requested_target_names,
    )


def reconciled_campaign_retry_scope_names(
    request: dict[str, Any],
    retry_of: str,
    *,
    execution_id: str,
    carrier: str,
    count: int,
    quota: int,
    requested_target_names: tuple[str, ...],
) -> tuple[str, ...]:
    reconciliation = request.get("predecessorReconciliation")
    if not isinstance(reconciliation, dict):
        raise _reconciled_scope_block(
            retry_of, "campaign request declares no predecessorReconciliation"
        )
    if not str(
        reconciliation.get("predecessorRootExecutionId") or ""
    ).strip() or not str(reconciliation.get("receiptDigest") or "").strip():
        raise _reconciled_scope_block(
            retry_of, "predecessorReconciliation reference is incomplete"
        )
    names = _frozen_campaign_target_names(
        request,
        retry_of,
        execution_id=execution_id,
        carrier=carrier,
        block=_reconciled_scope_block,
    )
    if not names:
        raise _reconciled_scope_block(
            retry_of, "reconciled campaign retry requires an exact entity subset"
        )
    if request.get("count") != count or request.get("quota") != quota:
        raise _reconciled_scope_block(
            retry_of, "--count/--quota must match the frozen campaign request"
        )
    if len(names) > count:
        raise _reconciled_scope_block(
            retry_of, f"reconciled entity pool {len(names)} exceeds --count {count}"
        )
    if requested_target_names and requested_target_names != names:
        raise _reconciled_scope_block(
            retry_of, "--target must match the frozen campaign targetNames exactly"
        )
    return names


def retry_target_names(
    retry_of: str | None,
    *,
    count: int,
    quota: int,
    requested_target_names: tuple[str, ...],
    load_frozen_target_set: Callable[[str], dict[str, Any]],
) -> tuple[str, ...]:
    """Keep a retry on the exact immutable target set of its predecessor."""

    if not retry_of:
        return requested_target_names
    try:
        target_set = load_frozen_target_set(retry_of)
    except FileNotFoundError as exc:
        reconciled_names = predecessor_target_names_without_target_set(retry_of)
        if reconciled_names is not None:
            if len(reconciled_names) > count:
                raise SystemExit(
                    f"[task execute] GATE_BLOCK retryOf={retry_of}: "
                    f"reconciled entity pool {len(reconciled_names)} exceeds "
                    f"--count {count}"
                ) from exc
            if requested_target_names and requested_target_names != reconciled_names:
                raise SystemExit(
                    f"[task execute] GATE_BLOCK retryOf={retry_of}: "
                    "--target must match reconciled predecessor targetNames exactly"
                ) from exc
            return reconciled_names
        if requested_target_names:
            return requested_target_names
        raise SystemExit(
            f"[task execute] GATE_BLOCK retryOf={retry_of}: "
            "previous frozen target set is unavailable; provide every exact --target"
        ) from exc
    except ValueError as exc:
        raise SystemExit(
            f"[task execute] GATE_BLOCK retryOf={retry_of}: "
            "previous frozen target set is invalid"
        ) from exc
    targets = target_set.get("targets")
    if not isinstance(targets, list):
        raise SystemExit(
            f"[task execute] GATE_BLOCK retryOf={retry_of}: "
            "previous frozen target set is invalid"
        )
    inherited_names = tuple(
        str(target.get("name") or "").strip()
        for target in targets
        if isinstance(target, dict)
    )
    if (
        len(inherited_names) != len(targets)
        or any(not name for name in inherited_names)
        or len(set(inherited_names)) != len(inherited_names)
    ):
        raise SystemExit(
            f"[task execute] GATE_BLOCK retryOf={retry_of}: "
            "previous frozen target names are invalid"
        )
    # --count bounds the entity pool while --quota counts approved objects, so a
    # multi-object carrier legitimately runs quota > entities.
    if len(inherited_names) > count:
        raise SystemExit(
            f"[task execute] GATE_BLOCK retryOf={retry_of}: "
            f"inherited entity pool {len(inherited_names)} exceeds --count {count}"
        )
    if requested_target_names and requested_target_names != inherited_names:
        raise SystemExit(
            f"[task execute] GATE_BLOCK retryOf={retry_of}: "
            "--target must match the previous frozen target order exactly"
        )
    return inherited_names


def retry_target_rows(
    retry_of: str | None,
    *,
    target_names: tuple[str, ...],
    load_frozen_target_set: Callable[[str], dict[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Load predecessor rows so retries retain source-qualification evidence."""
    if not retry_of:
        return ()
    try:
        target_set = load_frozen_target_set(retry_of)
    except FileNotFoundError:
        return ()
    targets = target_set.get("targets")
    if not isinstance(targets, list) or any(
        not isinstance(row, dict) for row in targets
    ):
        raise SystemExit(
            f"[task execute] GATE_BLOCK retryOf={retry_of}: "
            "previous frozen target rows are invalid"
        )
    rows = tuple(dict(row) for row in targets)
    inherited_names = tuple(str(row.get("name") or "").strip() for row in rows)
    if inherited_names != target_names:
        raise SystemExit(
            f"[task execute] GATE_BLOCK retryOf={retry_of}: "
            "previous frozen target rows must match the requested target order exactly"
        )
    return rows
