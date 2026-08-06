"""Request normalization for the single-execution recipe facade."""

from __future__ import annotations

import argparse
import subprocess
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any


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
        }
    )
    return selection


def submission_only_predecessor_target_names(
    retry_of: str | None,
) -> tuple[str, ...] | None:
    if not retry_of:
        return None
    from content.execution.campaign_submission_reconciliation import (
        load_reconciled_predecessor_submission,
    )

    row = load_reconciled_predecessor_submission(retry_of)
    if row is None:
        return None
    targets = row.get("targetNames")
    if (
        not isinstance(targets, list)
        or not targets
        or any(not isinstance(name, str) or not name.strip() for name in targets)
        or len(set(targets)) != len(targets)
    ):
        raise SystemExit(
            f"[task execute] GATE_BLOCK retryOf={retry_of}: "
            "reconciled predecessor targetNames are invalid"
        )
    return tuple(targets)


def terminal_campaign_predecessor_target_names(
    retry_of: str | None,
    *,
    output_root: Path | None = None,
) -> tuple[str, ...] | None:
    """Read targets from a fully evidenced blocked campaign terminal."""
    if not retry_of:
        return None
    from core import paths
    from core.io import read_json
    from content.execution.campaign_submission_reconciliation_contract import (
        campaigns_root,
        load_terminal_submission_documents,
        predecessor_campaign_root_execution_id,
    )
    from content.execution.identity import parse_execution_id

    resolved_output = (output_root or paths.OUTPUT_ROOT).resolve()
    root_id = predecessor_campaign_root_execution_id(retry_of)
    campaign = campaigns_root(resolved_output) / root_id
    plan_path = campaign / "campaign_plan.json"
    report_path = campaign / "campaign_report.json"
    snapshot_path = campaign / "runtime/snapshot.json"
    if not report_path.is_file() and not snapshot_path.is_file():
        return None
    if not report_path.is_file() or not snapshot_path.is_file():
        raise SystemExit(
            f"[task execute] GATE_BLOCK retryOf={retry_of}: "
            "predecessor terminal campaign evidence is incomplete"
        )
    report = read_json(report_path)
    snapshot = read_json(snapshot_path)
    if (
        not isinstance(report, dict)
        or report.get("schema") != "quwoquan_data.content_campaign_report"
        or report.get("rootExecutionId") != root_id
        or report.get("status") != "blocked"
        or not isinstance(snapshot, dict)
        or snapshot.get("schema")
        != "quwoquan_data.content_campaign_runtime_snapshot"
        or snapshot.get("rootExecutionId") != root_id
        or snapshot.get("status") != "blocked"
        or not str(snapshot.get("finishedAt") or "").strip()
    ):
        raise SystemExit(
            f"[task execute] GATE_BLOCK retryOf={retry_of}: "
            "predecessor terminal campaign evidence is invalid"
        )
    from content.execution.campaign_plan import sha256_payload
    from content.execution.campaign_process import CAMPAIGN_CARRIERS

    submissions = load_terminal_submission_documents(
        root_id,
        output_root=resolved_output,
    )
    if set(submissions) != set(CAMPAIGN_CARRIERS):
        raise SystemExit(
            f"[task execute] GATE_BLOCK retryOf={retry_of}: "
            "predecessor terminal submissions are incomplete"
        )
    lanes = report.get("lanes")
    snapshot_lanes = snapshot.get("lanes")
    if (
        not isinstance(lanes, dict)
        or set(lanes) != set(CAMPAIGN_CARRIERS)
    ):
        raise SystemExit(
            f"[task execute] GATE_BLOCK retryOf={retry_of}: "
            "predecessor terminal lane evidence is incomplete"
        )

    phases = (report.get("phase"), snapshot.get("phase"))
    if phases == ("freeze", "freeze"):
        if plan_path.exists() or any(
            not isinstance(row, dict)
            or row.get("status") != "pending"
            or row.get("phase") != "submission"
            or row.get("executionRootRef") is not None
            for row in lanes.values()
        ):
            raise SystemExit(
                f"[task execute] GATE_BLOCK retryOf={retry_of}: "
                "predecessor created lane evidence before freeze failure"
            )
    elif phases == ("completed", "completed"):
        if (
            not plan_path.is_file()
            or not isinstance(snapshot_lanes, dict)
            or set(snapshot_lanes) != set(CAMPAIGN_CARRIERS)
        ):
            raise SystemExit(
                f"[task execute] GATE_BLOCK retryOf={retry_of}: "
                "predecessor completed campaign plan is missing"
            )
        plan = read_json(plan_path)
        stable_plan = (
            {key: value for key, value in plan.items() if key != "planDigest"}
            if isinstance(plan, dict)
            else {}
        )
        execution_ids = {
            carrier: str(submissions[carrier].get("executionId") or "")
            for carrier in CAMPAIGN_CARRIERS
        }
        submission_digests = {
            carrier: str(submissions[carrier].get("requestDigest") or "")
            for carrier in CAMPAIGN_CARRIERS
        }
        plan_digest = str(plan.get("planDigest") or "") if isinstance(plan, dict) else ""
        representative = submissions["homepage"]
        source_document = representative.get("sourceDigest")
        if (
            not isinstance(plan, dict)
            or plan.get("schema") != "quwoquan_data.content_campaign_plan"
            or plan.get("rootExecutionId") != root_id
            or plan_digest != sha256_payload(stable_plan)
            or report.get("planDigest") != plan_digest
            or snapshot.get("planDigest") != plan_digest
            or plan.get("executionIds") != execution_ids
            or plan.get("submissionDigests") != submission_digests
            or not isinstance(source_document, dict)
            or plan.get("sourceDigest") != source_document.get("digest")
            or plan.get("sourceRevision") != representative.get("sourceRevision")
            or plan.get("entityCatalogDigest")
            != representative.get("entityCatalogDigest")
        ):
            raise SystemExit(
                f"[task execute] GATE_BLOCK retryOf={retry_of}: "
                "predecessor completed campaign plan evidence is invalid"
            )
        for carrier in CAMPAIGN_CARRIERS:
            execution_id = execution_ids[carrier]
            report_lane = lanes[carrier]
            snapshot_lane = snapshot_lanes[carrier]
            execution_ref = f"data/tasks/{execution_id}"
            execution_root = (resolved_output / execution_ref).resolve()
            if (
                not isinstance(report_lane, dict)
                or report_lane.get("executionId") != execution_id
                or report_lane.get("status") != "blocked"
                or report_lane.get("phase") != "review"
                or not isinstance(report_lane.get("reviewReturnCode"), int)
                or report_lane.get("reviewReturnCode") == 0
                or report_lane.get("publishReturnCode") is not None
                or report_lane.get("executionRootRef") != execution_ref
                or report_lane.get("cleanupStatus") != "cleaned"
                or not str(report_lane.get("error") or "").strip()
                or not isinstance(snapshot_lane, dict)
                or snapshot_lane.get("executionId") != execution_id
                or snapshot_lane.get("status") != "failed"
                or snapshot_lane.get("phase") != "review-only"
                or snapshot_lane.get("returnCode")
                != report_lane.get("reviewReturnCode")
                or resolved_output not in execution_root.parents
                or not execution_root.is_dir()
                or not (
                    execution_root
                    / "0.plan/campaign_external_input_envelope.json"
                ).is_file()
            ):
                raise SystemExit(
                    f"[task execute] GATE_BLOCK retryOf={retry_of}: "
                    f"predecessor completed {carrier} review evidence is invalid"
                )
    else:
        raise SystemExit(
            f"[task execute] GATE_BLOCK retryOf={retry_of}: "
            "predecessor terminal campaign phase is invalid"
        )

    target_sets = {
        tuple(str(name) for name in submissions[carrier].get("targetNames") or [])
        for carrier in CAMPAIGN_CARRIERS
    }
    if len(target_sets) != 1:
        raise SystemExit(
            f"[task execute] GATE_BLOCK retryOf={retry_of}: "
            "predecessor terminal targetNames drift across lanes"
        )
    carrier = parse_execution_id(retry_of).content_type.value
    row = submissions.get(carrier)
    targets = row.get("targetNames") if isinstance(row, dict) else None
    if (
        not isinstance(targets, list)
        or not targets
        or any(not isinstance(name, str) or not name.strip() for name in targets)
        or len(set(targets)) != len(targets)
    ):
        raise SystemExit(
            f"[task execute] GATE_BLOCK retryOf={retry_of}: "
            "predecessor terminal targetNames are invalid"
        )
    return tuple(targets)


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
        from content.execution.reviewed_closure_adoption import (
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
    target_names = owner._retry_target_names(
        retry_of,
        count=count,
        quota=quota,
        requested_target_names=tuple(getattr(args, "target_names", ()) or ()),
    )
    execution_exists = owner.store.spec_exists(execution_id)
    inherited_targets = (
        ()
        if execution_exists
        else retry_target_rows(
            retry_of,
            target_names=target_names,
            load_frozen_target_set=owner.load_frozen_target_set,
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
        ),
        invoke=invoke,
    )
