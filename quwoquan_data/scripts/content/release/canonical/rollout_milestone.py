"""Gamma-backed rollout milestones for the Zhejiang/Sichuan homepage program.

An execution may be created only after the preceding milestone has an immutable
release whose real Gamma import, API, App UAT, rollback, and replay evidence all
close.  This module deliberately derives that decision from release evidence;
it never maintains a campaign state directory or a mutable progress index.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from core.io import read_json, write_json
from core.paths import OUTPUT_ROOT, RELEASE_ROOT
from core.release_layout import attestation_root, payload_digest, payload_file
from core.schema import assert_valid
from content.execution.identity import ExecutionIdentity, parse_execution_id
from core.control_types import RolloutMilestone
from content.execution.workspace import execution_root
from content.release.canonical.rollout_contract import (
    MILESTONE_ORDER,
    MILESTONE_PREDECESSOR,
    RolloutContract,
    RolloutMilestoneError,
    identity_matches,
    load_rollout_contract,
)
from content.release.canonical.rollout_attestation import _milestone_attestation_issues
from verify.verify_execution_readiness import execution_readiness_issues
from verify.verify_homepage_media_completeness import homepage_media_completeness_report
from verify.verify_release_lifecycle import release_lifecycle_issues


ATTESTATION_FILE = "rollout_milestone_closure.json"


def _read_object(path: Path, *, label: str) -> Mapping[str, Any]:
    try:
        payload = read_json(path)
    except (OSError, TypeError, ValueError) as exc:
        raise RolloutMilestoneError(f"{label} unreadable: {path}: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise RolloutMilestoneError(f"{label} must be an object: {path}")
    return payload


def _retry_target_selection_path(retry_of: str) -> Path:
    """Resolve only the immutable target set of a prior execution.

    Invalidated executions are never release evidence. Their frozen target set
    remains valid solely for binding a mandatory ``retryOf`` to the same
    objects after source-digest invalidation.
    """
    active = execution_root(retry_of) / "_shared/target_selection.json"
    if active.is_file():
        return active

    invalidated_root = OUTPUT_ROOT / "data/local/workspace/invalidated"
    candidates: list[Path] = []
    if invalidated_root.is_dir():
        for receipt_path in sorted(
            invalidated_root.glob(
                f"*/tasks/{retry_of}/invalidation_receipt.json"
            )
        ):
            receipt = _read_object(
                receipt_path,
                label="retryOf invalidation receipt",
            )
            expected_original = f".qwq_output/data/tasks/{retry_of}"
            if (
                receipt.get("schema") != "quwoquan_data.local_evidence_invalidation"
                or receipt.get("evidenceType") != "execution"
                or receipt.get("evidenceId") != retry_of
                or receipt.get("originalPath") != expected_original
                or receipt.get("admission") != "invalidated_not_release_evidence"
            ):
                raise RolloutMilestoneError(
                    f"retryOf invalidation receipt is not trustworthy: {receipt_path}"
                )
            selection = receipt_path.parent / "_shared/target_selection.json"
            if selection.is_file():
                candidates.append(selection)
    if len(candidates) != 1:
        raise RolloutMilestoneError(
            f"retryOf target selection must resolve exactly once, got {len(candidates)}"
        )
    return candidates[0]
































def _closed_milestone_releases(
    *, contract: RolloutContract, milestone: str
) -> list[Path]:
    if not RELEASE_ROOT.is_dir():
        return []
    releases: list[Path] = []
    for release_root in sorted(path for path in RELEASE_ROOT.iterdir() if path.is_dir()):
        path = attestation_root(release_root) / ATTESTATION_FILE
        if path.is_file() and not _milestone_attestation_issues(
            path,
            contract=contract,
            expected=milestone,
        ):
            releases.append(release_root)
    return releases


def _single_closed_milestone_release(
    *, contract: RolloutContract, milestone: str
) -> Path:
    releases = _closed_milestone_releases(contract=contract, milestone=milestone)
    if not releases:
        raise RolloutMilestoneError(
            f"no immutable Gamma-closed {milestone} release exists for {contract.rollout_id}"
        )
    if len(releases) != 1:
        raise RolloutMilestoneError(
            f"multiple Gamma-closed {milestone} releases exist; delete superseded runtime evidence"
        )
    return releases[0]


def assert_milestone_closed(milestone: RolloutMilestone) -> Path:
    """Return the single immutable Gamma-closed release for a homepage milestone."""
    if milestone not in MILESTONE_ORDER:
        raise RolloutMilestoneError(f"unsupported homepage rollout milestone: {milestone}")
    return _single_closed_milestone_release(
        contract=load_rollout_contract(),
        milestone=milestone.value,
    )


def _predecessor_target_names(
    *, identity: ExecutionIdentity, contract: RolloutContract
) -> tuple[str, ...]:
    predecessor = MILESTONE_PREDECESSOR[identity.milestone]
    if predecessor is None:
        return ()
    release = _single_closed_milestone_release(
        contract=contract,
        milestone=predecessor,
    )
    payload = _read_object(
        attestation_root(release) / ATTESTATION_FILE,
        label=f"{predecessor} rollout milestone closure",
    )
    by_scope = payload.get("approvedEntityRefsByScope")
    rows = by_scope.get(identity.scope) if isinstance(by_scope, Mapping) else None
    if not isinstance(rows, list):
        raise RolloutMilestoneError(
            f"{predecessor} release has no approved refs for {identity.scope}"
        )
    names = tuple(sorted({str(ref).rsplit("/", 1)[-1].strip() for ref in rows if str(ref).strip()}))
    province = contract.province_for_scope(identity.scope)
    if len(names) != contract.cumulative_count(predecessor, province):
        raise RolloutMilestoneError(
            f"{predecessor} approved refs for {identity.scope} are incomplete"
        )
    return names


def _retry_target_names(
    *, identity: ExecutionIdentity, retry_of: str
) -> tuple[str, ...]:
    previous = parse_execution_id(retry_of)
    if (
        previous.vertical,
        previous.content_type,
        previous.intent,
        previous.scope,
        previous.milestone,
    ) != (
        identity.vertical,
        identity.content_type,
        identity.intent,
        identity.scope,
        identity.milestone,
    ):
        raise RolloutMilestoneError("retryOf must identify the same rollout batch")
    if identity.sequence <= previous.sequence:
        raise RolloutMilestoneError("retry execution sequence must increase")
    selection = _read_object(
        _retry_target_selection_path(retry_of),
        label="retryOf target selection",
    )
    rows = selection.get("targets")
    if not isinstance(rows, list) or not rows:
        raise RolloutMilestoneError("retryOf target selection has no frozen targets")
    names = tuple(
        str(row.get("name") or "").strip()
        for row in rows
        if isinstance(row, Mapping) and str(row.get("name") or "").strip()
    )
    if len(names) != len(rows) or len(set(names)) != len(names):
        raise RolloutMilestoneError("retryOf frozen targets are empty or duplicated")
    return names


def retry_target_names(
    *, identity: ExecutionIdentity, retry_of: str
) -> tuple[str, ...]:
    """Read the immutable frozen target set for a same-batch retry."""
    return _retry_target_names(identity=identity, retry_of=retry_of)


def rollout_start_issues(execution_id: str) -> list[str]:
    """Return the exact immutable predecessor failure before an execution exists."""
    try:
        identity = parse_execution_id(execution_id)
        contract = load_rollout_contract()
    except (ValueError, RolloutMilestoneError) as exc:
        return [str(exc)]
    if not identity_matches(identity, contract):
        return []
    try:
        contract.province_for_scope(identity.scope)
    except RolloutMilestoneError as exc:
        return [str(exc)]
    predecessor = MILESTONE_PREDECESSOR[identity.milestone]
    if predecessor is None:
        return []
    if not RELEASE_ROOT.is_dir():
        return [f"{identity.milestone} requires a Gamma-closed {predecessor} release, but no releases exist"]
    candidates = _closed_milestone_releases(contract=contract, milestone=predecessor)
    if not candidates:
        return [
            f"{identity.milestone} requires an immutable Gamma-closed {predecessor} release "
            f"for rollout {contract.rollout_id}"
        ]
    if len(candidates) != 1:
        return [
            f"{identity.milestone} requires exactly one Gamma-closed {predecessor} release; "
            f"found {len(candidates)}"
        ]
    return []


def assert_rollout_start(execution_id: str) -> None:
    issues = rollout_start_issues(execution_id)
    if issues:
        raise RolloutMilestoneError("; ".join(issues))


def geo_rollout_parameters(
    *,
    execution_id: str,
    retry_of: str | None = None,
) -> tuple[str, int, str | None, tuple[str, ...]]:
    """Resolve fixed two-province canary/M1/M2/M3/H10K parameters before manifest creation."""
    identity = parse_execution_id(execution_id)
    contract = load_rollout_contract()
    if not identity_matches(identity, contract):
        raise RolloutMilestoneError(
            f"execution {execution_id} does not belong to rollout {contract.rollout_id}"
        )
    province_contract = contract.province_for_scope(identity.scope)
    expected_limit = contract.batch_count(identity.milestone, province_contract)
    excluded = _predecessor_target_names(identity=identity, contract=contract)
    mandatory: str | None = None
    if retry_of:
        retry_names = _retry_target_names(identity=identity, retry_of=retry_of)
        if len(retry_names) != expected_limit:
            raise RolloutMilestoneError(
                f"retryOf target count {len(retry_names)} != {expected_limit}"
            )
        mandatory = ",".join(retry_names)
    elif identity.milestone == RolloutMilestone.CANARY:
        mandatory = ",".join(province_contract.canary_targets)
    return province_contract.province, expected_limit, mandatory, excluded


__all__ = [
    "ATTESTATION_FILE",
    "RolloutMilestoneError",
    "assert_rollout_start",
    "assert_milestone_closed",
    "geo_rollout_parameters",
    "load_rollout_contract",
    "rollout_start_issues",
    "retry_target_names",
]
