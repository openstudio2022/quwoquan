"""Exact predecessor evidence for a semantic retry of unfinished objects only."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from content.execution.identity import validate_execution_id
from core.entity_object import parse_entity_ref
from core.io import read_json


@dataclass(frozen=True, slots=True)
class RetryUnfinishedScope:
    object_refs: tuple[str, ...]
    entity_refs: tuple[str, ...]
    target_names: tuple[str, ...]
    target_rows: tuple[dict[str, Any], ...]
    candidate_ids: tuple[str, ...]
    review_feedback_source: Any | None = None


def _has_review_retry_evidence(
    root: Path,
    *,
    root_execution_id: str,
    required_object_refs: Sequence[str],
) -> bool:
    if (root / "_shared/post_review_closure.json").is_file():
        return True
    from content.execution.campaign.review_interruption_reconciliation import (
        review_interruption_receipt_path,
    )

    output_root = root.parents[2]
    return any(
        review_interruption_receipt_path(
            root_execution_id,
            str(ref),
            output_root=output_root,
        ).is_file()
        for ref in required_object_refs
    )


def _review_retry_scope(
    root: Path,
    *,
    predecessor_execution_id: str,
    successor_execution_id: str,
    root_execution_id: str,
    required_object_refs: Sequence[str],
) -> RetryUnfinishedScope:
    from content.execution.planning.retry_review_feedback import (
        load_retry_review_feedback_source,
    )

    feedback = load_retry_review_feedback_source(
        root,
        predecessor_execution_id=predecessor_execution_id,
        required_object_refs=required_object_refs,
        root_execution_id=root_execution_id,
    )
    target_set = _object(root / "0.plan/target_set.json", label="target set")
    target_by_identity: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in target_set.get("targets") or []:
        if not isinstance(row, Mapping):
            continue
        key = (
            str(row.get("entityType") or "").strip(),
            str(row.get("name") or "").strip(),
        )
        target_by_identity.setdefault(key, []).append(dict(row))
    target_rows: list[dict[str, Any]] = []
    for entity_ref in feedback.entity_refs:
        parsed = parse_entity_ref(entity_ref)
        if parsed is None:
            raise ValueError("review feedback entityRef is malformed")
        domain, entity_type, name = parsed
        rows = target_by_identity.get((f"{domain}/{entity_type}", name), [])
        if len(rows) != 1:
            raise ValueError(
                f"review feedback target binding is missing or ambiguous: {entity_ref}"
            )
        target_rows.append(rows[0])
    # A review failure may be caused by the predecessor source itself.  Keep
    # the exact entity scope, but deliberately do not freeze that failed
    # source-pool candidate into the successor.
    feedback.to_document(successor_execution_id)
    return RetryUnfinishedScope(
        object_refs=feedback.object_refs,
        entity_refs=feedback.entity_refs,
        target_names=feedback.target_names,
        target_rows=tuple(target_rows),
        candidate_ids=(),
        review_feedback_source=feedback,
    )


def _object(path: Path, *, label: str) -> dict[str, Any]:
    value = read_json(path)
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be one object")
    return value


def _exhausted_author_refs(
    root: Path,
    *,
    execution_id: str,
    state: Mapping[str, Any],
) -> set[str]:
    attempt_refs: dict[tuple[str, str], str] = {}
    for history in state.get("agentRunHistory") or []:
        if not isinstance(history, Mapping):
            continue
        for outcome in history.get("outcomes") or []:
            if not isinstance(outcome, Mapping):
                continue
            run_id = str(outcome.get("runId") or "").strip()
            attempt_digest = str(
                outcome.get("invocationAttemptDigest") or ""
            ).strip()
            ref = str(outcome.get("ref") or "").strip()
            if ref:
                if run_id:
                    attempt_refs[("runId", run_id)] = ref
                if attempt_digest:
                    attempt_refs[("invocationAttemptDigest", attempt_digest)] = ref
    exhausted: set[str] = set()
    for request_path in (root / "_shared/semantic_tasks").glob("*/request.json"):
        request = _object(request_path, label="semantic task request")
        if request.get("executionId") != execution_id or request.get("stage") != "author":
            continue
        max_attempts = request.get("maxAttempts")
        attempts = sorted((request_path.parent / "attempts").glob("*.json"))
        if (
            isinstance(max_attempts, bool)
            or not isinstance(max_attempts, int)
            or max_attempts < 1
            or len(attempts) != max_attempts
        ):
            continue
        refs: set[str] = set()
        for path in attempts:
            attempt = _object(path, label="semantic task attempt")
            ref = attempt_refs.get(
                ("runId", str(attempt.get("runId") or "").strip())
            ) or attempt_refs.get(
                (
                    "invocationAttemptDigest",
                    str(attempt.get("attemptDigest") or "").strip(),
                )
            )
            refs.add(ref or "")
        refs.discard("")
        if len(refs) == 1:
            exhausted.update(refs)
    return exhausted


def load_retry_unfinished_scope(
    predecessor_root: Path,
    *,
    predecessor_execution_id: str,
    required_object_refs: Sequence[str],
    successor_execution_id: str | None = None,
    root_execution_id: str | None = None,
) -> RetryUnfinishedScope:
    """Verify exact manual-required refs and their frozen source-pool subset."""

    execution_id = validate_execution_id(predecessor_execution_id)
    root = predecessor_root.expanduser().resolve()
    if root.name != execution_id or not root.is_dir():
        raise ValueError("retry predecessor execution root is unavailable")
    refs = tuple(str(value).strip() for value in required_object_refs)
    if not refs or any(not ref for ref in refs) or len(set(refs)) != len(refs):
        raise ValueError("retry unfinished refs must be non-empty and unique")
    campaign_root_id = str(root_execution_id or "").strip()
    if not campaign_root_id:
        from content.execution.campaign.submission_reconciliation_contract import (
            campaign_root_for_submission,
        )

        campaign_root_id = (
            campaign_root_for_submission(execution_id, output_root=root.parents[2])
            or execution_id
        )
    if _has_review_retry_evidence(
        root,
        root_execution_id=campaign_root_id,
        required_object_refs=refs,
    ):
        if not successor_execution_id:
            raise ValueError(
                "final-review retry requires an explicit successor executionId"
            )
        return _review_retry_scope(
            root,
            predecessor_execution_id=execution_id,
            successor_execution_id=successor_execution_id,
            root_execution_id=campaign_root_id,
            required_object_refs=refs,
        )
    state = _object(root / "_shared/execution_state.json", label="execution state")
    last_run = state.get("lastAgentRun")
    outcomes = last_run.get("outcomes") if isinstance(last_run, Mapping) else None
    failed_refs = tuple(
        str(row.get("ref") or "").strip()
        for row in (outcomes or [])
        if isinstance(row, Mapping)
        and row.get("status") == "error"
        and row.get("started") is False
    )
    if (
        state.get("executionId") != execution_id
        or state.get("status") != "manual_required"
        or state.get("waitingCheckpoint") != "post_author"
        or not isinstance(last_run, Mapping)
        or last_run.get("stage") != "post_author"
        or int(last_run.get("startedCount") or 0) != 0
        or int(last_run.get("infrastructureFailures") or 0) != len(failed_refs)
        or refs != failed_refs
    ):
        raise ValueError(
            "retry unfinished refs must exactly match predecessor manual_required post_author failures"
        )
    exhausted = _exhausted_author_refs(
        root,
        execution_id=execution_id,
        state=state,
    )
    if any(ref not in exhausted for ref in refs):
        raise ValueError("retry unfinished ref has not exhausted its frozen semantic journal")

    plan = _object(root / "_shared/content_plan_packet.json", label="content plan packet")
    by_ref = {
        str(item.get("ref") or ""): item
        for item in plan.get("items") or []
        if isinstance(item, Mapping)
    }
    target_set = _object(root / "0.plan/target_set.json", label="target set")
    target_by_identity: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in target_set.get("targets") or []:
        if not isinstance(row, Mapping):
            continue
        key = (str(row.get("entityType") or "").strip(), str(row.get("name") or "").strip())
        target_by_identity.setdefault(key, []).append(dict(row))

    request = _object(root / "0.plan/request.json", label="execution request")
    selection = request.get("sourcePoolSelection")
    binding = request.get("scaleSourcePool")
    if not isinstance(selection, Mapping) or not isinstance(binding, Mapping):
        raise ValueError("retry predecessor lacks frozen source-pool binding")
    plan_ref = Path(str(binding.get("planRef") or ""))
    output_root = root.parents[2]
    source_plan_path = (output_root / plan_ref).resolve()
    source_plan_path.relative_to(output_root.resolve())
    source_plan = _object(source_plan_path, label="scale source pool")
    selected_ids = tuple(str(value) for value in selection.get("candidateIds") or [])
    selected = {
        str(row.get("candidateId") or ""): dict(row)
        for row in source_plan.get("candidates") or []
        if isinstance(row, Mapping) and str(row.get("candidateId") or "") in selected_ids
    }
    if len(selected) != len(selected_ids):
        raise ValueError("retry predecessor source-pool selection drift")
    candidates_by_entity: dict[str, list[dict[str, Any]]] = {}
    for candidate_id in selected_ids:
        row = selected[candidate_id]
        candidates_by_entity.setdefault(str(row.get("entityRef") or ""), []).append(row)

    entity_refs: list[str] = []
    target_names: list[str] = []
    target_rows: list[dict[str, Any]] = []
    candidate_ids: list[str] = []
    for ref in refs:
        item = by_ref.get(ref)
        item_entities = item.get("entityRefs") if isinstance(item, Mapping) else None
        if not isinstance(item_entities, list) or len(item_entities) != 1:
            raise ValueError(f"unfinished ref has no exact content-plan entity: {ref}")
        entity_ref = str(item_entities[0])
        parsed = parse_entity_ref(entity_ref)
        if parsed is None:
            raise ValueError(f"unfinished ref entity is malformed: {ref}")
        domain, entity_type, name = parsed
        targets = target_by_identity.get((f"{domain}/{entity_type}", name), [])
        candidates = candidates_by_entity.get(entity_ref, [])
        if len(targets) != 1 or len(candidates) != 1:
            raise ValueError(f"unfinished ref target/source-pool binding is missing or ambiguous: {ref}")
        entity_refs.append(entity_ref)
        target_names.append(name)
        target_rows.append(targets[0])
        candidate_ids.append(str(candidates[0]["candidateId"]))
    return RetryUnfinishedScope(
        object_refs=refs,
        entity_refs=tuple(entity_refs),
        target_names=tuple(target_names),
        target_rows=tuple(target_rows),
        candidate_ids=tuple(candidate_ids),
    )


__all__ = ["RetryUnfinishedScope", "load_retry_unfinished_scope"]
