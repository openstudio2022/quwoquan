"""Request normalization for the single-execution recipe facade."""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from types import ModuleType
from typing import Any, Callable


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
    if not quota <= len(inherited_names) <= count:
        raise SystemExit(
            f"[task execute] GATE_BLOCK retryOf={retry_of}: "
            f"inherited candidate pool {len(inherited_names)} must stay inside "
            f"[--quota {quota}, --count {count}]"
        )
    if requested_target_names and requested_target_names != inherited_names:
        raise SystemExit(
            f"[task execute] GATE_BLOCK retryOf={retry_of}: "
            "--target must match the previous frozen target order exactly"
        )
    return inherited_names


def handle_execute(
    args: argparse.Namespace,
    invoke: Callable[[list[str]], int] | None,
    *,
    owner: ModuleType,
) -> None:
    """Normalize one CLI request before handing it to the recipe runner."""

    execution_id = str(getattr(args, "execution_id", "") or "").strip()
    from content.execution.identity import parse_execution_id

    identity = parse_execution_id(execution_id)
    stage = str(getattr(args, "stage", "run") or "run")
    if stage == "campaign-run":
        root_execution_id = str(
            getattr(args, "campaign_root_execution_id", "") or execution_id
        ).strip()
        if identity.content_type.value != "homepage":
            raise SystemExit(
                "[task execute] GATE_BLOCK campaign-run requires a homepage "
                "root executionId"
            )
        if root_execution_id != execution_id:
            raise SystemExit(
                "[task execute] GATE_BLOCK campaign-run executionId must equal "
                "--campaign-root-execution-id"
            )
        from content.execution.campaign_controller import run_campaign

        try:
            report_path = run_campaign(
                root_execution_id,
                submission_timeout_seconds=getattr(
                    args, "submission_timeout_seconds", None
                ),
                lane_timeout_seconds=getattr(
                    args, "campaign_lane_timeout_seconds", None
                ),
            )
        except (
            OSError,
            RuntimeError,
            TimeoutError,
            ValueError,
            subprocess.SubprocessError,
        ) as exc:
            raise SystemExit(f"[task execute] GATE_BLOCK campaign: {exc}") from exc
        print(f"[task execute] CAMPAIGN DONE report={report_path}")
        return
    region_ref = str(getattr(args, "region_ref", "") or "").strip().strip("/")
    if not region_ref:
        raise SystemExit("[task execute] GATE_BLOCK --region-ref is required")
    discovery_path = (
        owner.REPO_ROOT
        / "quwoquan_data/reference"
        / identity.vertical
        / "entities"
        / region_ref
    )
    if not discovery_path.is_dir():
        raise SystemExit(
            f"[task execute] GATE_BLOCK region reference does not exist: {region_ref}"
        )
    quota, count = owner.resolve_candidate_pool(
        quota=getattr(args, "quota", None),
        count=getattr(args, "count", None),
    )
    selector = str(getattr(args, "selector", "") or "").strip()
    try:
        target_selector = owner.TargetSelector(selector)
    except ValueError as exc:
        choices = ", ".join(item.value for item in owner.TargetSelector)
        raise SystemExit(
            f"[task execute] GATE_BLOCK --selector must be one of: {choices}"
        ) from exc
    if (
        identity.content_type.value == "homepage"
        and target_selector is not owner.TargetSelector.SOURCE_READY_PRIORITY
    ):
        raise SystemExit(
            "[task execute] GATE_BLOCK homepage carrier requires "
            "--selector source-ready-priority"
        )
    target_names = owner._retry_target_names(
        str(getattr(args, "retry_of", "") or "").strip() or None,
        count=count,
        quota=quota,
        requested_target_names=tuple(getattr(args, "target_names", ()) or ()),
    )
    owner._run_execution(
        argparse.Namespace(
            execution_id=execution_id,
            retry_of=getattr(args, "retry_of", None),
            video_scale_promotion=getattr(args, "video_scale_promotion", None),
            image_scale_promotion=getattr(args, "image_scale_promotion", None),
            campaign_envelope=getattr(args, "campaign_envelope", None),
            stage=getattr(args, "stage", "run"),
            campaign_root_execution_id=getattr(
                args, "campaign_root_execution_id", None
            ),
            recover_stage=getattr(args, "recover_stage", None),
            recovery_reason=getattr(args, "recovery_reason", None),
            family=getattr(args, "family", None),
            region_ref=region_ref,
            selector=target_selector.value,
            target_names=target_names,
            topic=getattr(args, "topic", None),
            source_providers=tuple(getattr(args, "source_providers", ()) or ()),
            vertical=identity.vertical,
            content_type=identity.content_type.value,
            intent=identity.intent,
            count=count,
            quota=quota,
        ),
        invoke=invoke,
    )
