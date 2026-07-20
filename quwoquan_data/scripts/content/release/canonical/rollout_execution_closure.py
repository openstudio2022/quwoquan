"""Validate execution membership and publish closure for rollout releases."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from core.codec import JsonObjectDecodeError
from core.control_types import ContentType, RolloutMilestone
from content.execution.identity import ExecutionIdentity, parse_execution_id
from content.execution.workspace import execution_root
from content.release.canonical.rollout_contract import (
    MILESTONE_ORDER,
    RolloutContract,
    RolloutMilestoneError,
    identity_matches,
)
from content.release.canonical.rollout_evidence import (
    ExecutionPublishReference,
    HomepageMediaCompleteness,
    ReleasePayload,
    RolloutEvidenceError,
)
from verify.verify_execution_readiness import execution_readiness_issues
from verify.verify_homepage_media_completeness import (
    homepage_media_completeness_report,
)


def release_execution_identities(
    release: ReleasePayload,
    contract: RolloutContract,
) -> tuple[ExecutionIdentity, ...]:
    try:
        identities = tuple(parse_execution_id(value) for value in release.execution_ids)
    except ValueError as exc:
        raise RolloutMilestoneError(f"release has invalid executionId: {exc}") from exc
    if len({item.execution_id for item in identities}) != len(identities):
        raise RolloutMilestoneError("release executionIds are duplicated")
    scopes = {row.scope for row in contract.provinces}
    if any(
        item.vertical != contract.vertical
        or item.intent not in {contract.intent, "cold-start"}
        or item.scope not in scopes
        or item.milestone not in MILESTONE_ORDER
        for item in identities
    ):
        raise RolloutMilestoneError(
            "release executionIds do not belong to the configured rollout"
        )
    if any(
        item.content_type is ContentType.HOMEPAGE
        and not identity_matches(item, contract)
        for item in identities
    ):
        raise RolloutMilestoneError(
            "homepage executionIds do not match the configured rollout"
        )
    milestone = release.milestone
    current_index = MILESTONE_ORDER.index(milestone)
    if any(MILESTONE_ORDER.index(item.milestone) > current_index for item in identities):
        raise RolloutMilestoneError(
            "release contains an execution from a future milestone"
        )
    if {item.scope for item in identities} != scopes:
        raise RolloutMilestoneError(
            "release must include both Zhejiang and Sichuan executions"
        )
    identity_keys = {
        (item.content_type, item.scope, item.milestone) for item in identities
    }
    if len(identity_keys) != len(identities):
        raise RolloutMilestoneError(
            "release must include only one successful execution per "
            "contentType/scope/milestone"
        )
    expected_content_types = (
        {ContentType.HOMEPAGE}
        if milestone is RolloutMilestone.M3
        else set(ContentType)
    )
    expected_current = {
        (content_type, scope)
        for content_type in expected_content_types
        for scope in scopes
    }
    actual_current = {
        (item.content_type, item.scope)
        for item in identities
        if item.milestone == milestone
    }
    if actual_current != expected_current:
        raise RolloutMilestoneError(
            "release must include homepage/article/image/video executions for both "
            "provinces at rolloutMilestone"
        )
    return identities


def execution_publish_reference(
    identity: ExecutionIdentity,
    *,
    execution_root_resolver: Callable[[str], Path] = execution_root,
) -> ExecutionPublishReference:
    root = execution_root_resolver(identity.execution_id)
    try:
        payload = ExecutionPublishReference.load(root / "publish_ref.json")
        payload.assert_matches_execution(identity.execution_id)
    except RolloutEvidenceError as exc:
        raise RolloutMilestoneError(
            f"{identity.execution_id}: publish_ref unreadable: {exc}"
        ) from exc
    return payload


def execution_refs_by_scope(
    identities: tuple[ExecutionIdentity, ...],
    *,
    milestone: RolloutMilestone,
    contract: RolloutContract,
    execution_root_resolver: Callable[[str], Path] = execution_root,
    readiness_checker: Callable[..., list[str]] = execution_readiness_issues,
    homepage_media_reporter: Callable[[str], dict[str, object]] = (
        homepage_media_completeness_report
    ),
) -> tuple[dict[str, set[str]], dict[str, set[str]], set[str]]:
    refs_by_scope: dict[str, set[str]] = {}
    batch_refs_by_scope: dict[str, set[str]] = {}
    post_refs: set[str] = set()
    for identity in identities:
        issues = readiness_checker(
            identity.execution_id,
            require_reviewed=True,
        )
        if issues:
            raise RolloutMilestoneError(
                f"{identity.execution_id}: execution readiness failed: {issues[0]}"
            )
        payload = execution_publish_reference(
            identity,
            execution_root_resolver=execution_root_resolver,
        )
        entities = set(payload.entity_refs)
        posts = set(payload.post_refs)
        if identity.content_type is ContentType.HOMEPAGE:
            if posts or not entities:
                raise RolloutMilestoneError(
                    f"{identity.execution_id}: homepage execution publish refs are invalid"
                )
            try:
                media = HomepageMediaCompleteness.from_document(
                    homepage_media_reporter(identity.execution_id)
                )
            except (JsonObjectDecodeError, ValueError) as exc:
                raise RolloutMilestoneError(
                    f"{identity.execution_id}: homepage media completeness receipt "
                    f"is invalid: {exc}"
                ) from exc
            if not media.passed:
                raise RolloutMilestoneError(
                    f"{identity.execution_id}: homepage media completeness failed"
                )
            refs_by_scope.setdefault(identity.scope, set()).update(entities)
            if identity.milestone == milestone:
                batch_refs_by_scope.setdefault(identity.scope, set()).update(entities)
            continue
        if entities or not posts:
            raise RolloutMilestoneError(
                f"{identity.execution_id}: post execution publish refs are invalid"
            )
        province = contract.province_for_scope(identity.scope)
        expected_count = (
            contract.cumulative_count(identity.milestone, province)
            if identity.milestone is RolloutMilestone.H10K
            else contract.batch_count(identity.milestone, province)
        )
        if len(posts) != expected_count:
            raise RolloutMilestoneError(
                f"{identity.execution_id}: post batch count mismatch: "
                f"expected={expected_count} actual={len(posts)}"
            )
        overlap = post_refs.intersection(posts)
        if overlap:
            raise RolloutMilestoneError(
                f"{identity.execution_id}: post refs overlap another execution"
            )
        post_refs.update(posts)
    return refs_by_scope, batch_refs_by_scope, post_refs
