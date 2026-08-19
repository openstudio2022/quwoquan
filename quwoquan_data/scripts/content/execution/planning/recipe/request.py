"""Request normalization for the single-execution recipe facade."""

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


def predecessor_target_names_without_target_set(
    retry_of: str | None,
) -> tuple[str, ...] | None:
    return submission_only_predecessor_target_names(
        retry_of
    ) or terminal_campaign_predecessor_target_names(retry_of)


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
            if not quota <= len(reconciled_names) <= count:
                raise SystemExit(
                    f"[task execute] GATE_BLOCK retryOf={retry_of}: "
                    f"reconciled candidate pool {len(reconciled_names)} must stay "
                    f"inside [--quota {quota}, --count {count}]"
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


def retry_unfinished_scope(
    retry_of: str | None,
    *,
    requested_object_refs: tuple[str, ...],
    output_root: Path,
) -> RetryUnfinishedScope | None:
    if not requested_object_refs:
        return None
    if not retry_of:
        raise SystemExit(
            "[task execute] GATE_BLOCK --retry-unfinished-ref requires --retry-of"
        )
    try:
        return load_retry_unfinished_scope(
            output_root / "data/tasks" / retry_of,
            predecessor_execution_id=retry_of,
            required_object_refs=requested_object_refs,
        )
    except (OSError, TypeError, ValueError) as exc:
        raise SystemExit(
            f"[task execute] GATE_BLOCK retryOf={retry_of}: "
            f"invalid unfinished retry scope: {exc}"
        ) from exc


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
    from content.execution.campaign.distributed_request import (
        handle_distributed_campaign_stage,
    )

    if handle_distributed_campaign_stage(args, identity):
        return
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
        from content.execution.campaign.controller import run_campaign

        try:
            report_path = run_campaign(
                root_execution_id,
                submission_timeout_seconds=getattr(
                    args, "submission_timeout_seconds", None
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
    if stage == "adopt-reviewed-closure":
        required = {
            "--adoption-id": getattr(args, "adoption_id", None),
            "--source-release-id": getattr(args, "source_release_id", None),
            "--identity-incident": getattr(args, "identity_incident", None),
            "--region-ref": getattr(args, "region_ref", None),
            "--article-execution-id": getattr(args, "article_execution_id", None),
            "--image-execution-id": getattr(args, "image_execution_id", None),
            "--video-execution-id": getattr(args, "video_execution_id", None),
        }
        missing = [
            flag for flag, value in required.items() if not str(value or "").strip()
        ]
        if missing:
            raise SystemExit(
                "[task execute] GATE_BLOCK adopt-reviewed-closure requires "
                + ", ".join(missing)
            )
        if identity.content_type.value != "homepage":
            raise SystemExit(
                "[task execute] GATE_BLOCK adopt-reviewed-closure requires a "
                "homepage --execution-id"
            )
        from content.execution.closure.adoption import (
            handle_adopt_reviewed_closure,
        )

        handle_adopt_reviewed_closure(args)
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
    retry_of = str(getattr(args, "retry_of", "") or "").strip() or None
    execution_exists = owner.store.spec_exists(execution_id)
    requested_unfinished_refs = tuple(
        str(value).strip()
        for value in (getattr(args, "retry_unfinished_refs", ()) or ())
        if str(value).strip()
    )
    unfinished_scope = (
        None
        if execution_exists
        else retry_unfinished_scope(
            retry_of,
            requested_object_refs=requested_unfinished_refs,
            output_root=owner.OUTPUT_ROOT,
        )
    )
    from content.execution.planning.rewrite import (
        RewriteBinding,
        resolve_rewrite_from_args,
        rewrite_target_rows,
    )

    rewrite_values = dict(vars(args))
    rewrite_values["content_type"] = identity.content_type.value
    rewrite_args = argparse.Namespace(**rewrite_values)
    rewrite_binding = None
    request_path = owner.execution_request_path(execution_id)
    if execution_exists and request_path.is_file():
        frozen_request = owner.RuntimeExecutionRequest.from_document(
            owner.store.read_json(request_path)
        )
        if frozen_request.rewrite is not None:
            rewrite_binding = RewriteBinding.from_document(frozen_request.rewrite)
            supplied = (
                str(getattr(args, "rewrite_content_id", "") or "").strip(),
                getattr(args, "expected_version", None),
                str(getattr(args, "rewrite_reason", "") or "").strip(),
            )
            if supplied != (
                rewrite_binding.content_id,
                rewrite_binding.expected_version,
                rewrite_binding.reason,
            ):
                raise SystemExit(
                    "[task execute] GATE_BLOCK resume may not change the frozen rewrite"
                )
    else:
        from core.paths import PUBLISH_ROOT

        rewrite_binding = resolve_rewrite_from_args(
            rewrite_args,
            publish_root=PUBLISH_ROOT,
        )
    requested_target_names = tuple(getattr(args, "target_names", ()) or ())
    if rewrite_binding is not None:
        if identity.content_type.value == "homepage":
            raise SystemExit(
                "[task execute] GATE_BLOCK homepage is not a content rewrite carrier"
            )
        if count != 1 or quota != 1:
            raise SystemExit(
                "[task execute] GATE_BLOCK targeted rewrite requires --count 1 --quota 1"
            )
        if requested_target_names and requested_target_names != (
            rewrite_binding.target_name,
        ):
            raise SystemExit(
                "[task execute] GATE_BLOCK --target must equal the rewrite source target"
            )
        target_names = (rewrite_binding.target_name,)
        inherited_targets = (
            ()
            if execution_exists
            else rewrite_target_rows(
                rewrite_binding,
                retry_of=retry_of or "",
                load_frozen_target_set=owner.load_frozen_target_set,
            )
        )
    else:
        if unfinished_scope is not None:
            if count != len(unfinished_scope.target_names) or quota != count:
                raise SystemExit(
                    "[task execute] GATE_BLOCK unfinished retry count/quota must "
                    "equal the exact predecessor failed-object count"
                )
            if requested_target_names != unfinished_scope.target_names:
                raise SystemExit(
                    "[task execute] GATE_BLOCK --target must match the exact "
                    "unfinished predecessor target order"
                )
            target_names = unfinished_scope.target_names
        else:
            target_names = owner._retry_target_names(
                retry_of,
                count=count,
                quota=quota,
                requested_target_names=requested_target_names,
            )
        inherited_targets = (
            unfinished_scope.target_rows
            if unfinished_scope is not None
            else (
                ()
                if execution_exists
                else retry_target_rows(
                    retry_of,
                    target_names=target_names,
                    load_frozen_target_set=owner.load_frozen_target_set,
                )
            )
        )
    submission_only_predecessor = bool(
        retry_of
        and not execution_exists
        and not inherited_targets
        and predecessor_target_names_without_target_set(retry_of) is not None
    )
    if (
        retry_of
        and identity.content_type.value == "homepage"
        and not execution_exists
        and not inherited_targets
        and not submission_only_predecessor
    ):
        raise SystemExit(
            f"[task execute] GATE_BLOCK retryOf={retry_of}: homepage retry requires "
            "the predecessor frozen target-set evidence"
        )
    owner._run_execution(
        argparse.Namespace(
            execution_id=execution_id,
            retry_of=getattr(args, "retry_of", None),
            retry_unfinished_refs=requested_unfinished_refs,
            semantic_selection_id=getattr(args, "semantic_selection_id", None),
            semantic_preflight_receipt=getattr(
                args, "semantic_preflight_receipt", None
            ),
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
            inherited_targets=inherited_targets,
            retry_submission_only_predecessor=submission_only_predecessor,
            topic=getattr(args, "topic", None),
            source_providers=tuple(getattr(args, "source_providers", ()) or ()),
            vertical=identity.vertical,
            content_type=identity.content_type.value,
            intent=identity.intent,
            count=count,
            quota=quota,
            capacity_calibration_receipt=getattr(
                args, "capacity_calibration_receipt", None
            ),
            scale_source_pool_id=getattr(args, "scale_source_pool_id", None),
            scale_source_pool_target_scale=getattr(
                args, "scale_source_pool_target_scale", None
            ),
            scale_source_pool_plan_ref=getattr(
                args, "scale_source_pool_plan_ref", None
            ),
            scale_source_pool_plan_digest=getattr(
                args, "scale_source_pool_plan_digest", None
            ),
            scale_source_pool_plan_file_sha256=getattr(
                args, "scale_source_pool_plan_file_sha256", None
            ),
            source_pool_source_revision=getattr(
                args, "source_pool_source_revision", None
            ),
            source_pool_source_digest=getattr(
                args, "source_pool_source_digest", None
            ),
            source_pool_entity_catalog_digest=getattr(
                args, "source_pool_entity_catalog_digest", None
            ),
            source_pool_evidence_root_ref=getattr(
                args, "source_pool_evidence_root_ref", None
            ),
            source_pool_carrier=getattr(args, "source_pool_carrier", None),
            source_pool_candidate_ids=tuple(
                getattr(args, "source_pool_candidate_ids", ()) or ()
            ),
            source_pool_selection_digest=getattr(
                args, "source_pool_selection_digest", None
            ),
            rewrite_binding=(
                rewrite_binding.to_document()
                if rewrite_binding is not None
                else None
            ),
        ),
        invoke=invoke,
    )
