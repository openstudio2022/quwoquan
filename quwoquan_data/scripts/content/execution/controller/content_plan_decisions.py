"""Typed bookkeeping and oversample decisions for content planning."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from content.execution.support import DataIssue, DataIssueCode, ExecutionContext
from content.execution.support import execution_root, read_json, write_json


def planned_item_owning_target(item: Mapping[str, Any]) -> str:
    """Return the coverage target one planned item belongs to.

    ``entityRefs`` names the owning coverage target, while ``entityTags`` is the
    multi-label set of entities one object covers. Those two are not
    interchangeable: an article planned for 峨眉山 off a source that also describes
    乐山大佛 carries ``entityTags=['乐山大佛','峨眉山']``, so reading the first tag
    attributes the object to the wrong entity and silently drops the real owner
    out of the ready set. Carriers that plan one object per entity (video, image)
    emit tags without refs, and there the single tag *is* the owner, so it stays
    the fallback rather than the primary reading.
    """
    refs = item.get("entityRefs")
    if isinstance(refs, list) and refs:
        return str(refs[0] or "").strip().rstrip("/").rsplit("/", 1)[-1]
    tags = item.get("entityTags")
    if isinstance(tags, list) and tags:
        return str(tags[0] or "").strip()
    return ""


def persist_content_plan_shortfall_absorb(
    execution_id: str,
    *,
    successful_names: list[str],
    issues: list[DataIssue],
    object_refs: Mapping[str, str],
    carrier: str,
    ready_work_unit_ids: list[str] | None = None,
) -> None:
    """Persist object-typed content-plan decisions for one partial closure."""

    from core.paths import now_iso

    availability_path = (
        execution_root(execution_id) / "_shared" / "source_unavailable_targets.json"
    )
    existing = read_json(availability_path) if availability_path.is_file() else {}
    if not isinstance(existing, dict):
        existing = {}
    successful = set(successful_names)
    ineligible = [
        row
        for row in (existing.get("ineligibleTargets") or [])
        if isinstance(row, dict)
        and str(row.get("entityId") or "").strip() not in successful
    ]
    known_ineligible = {
        str(row.get("entityId") or "").strip()
        for row in ineligible
        if str(row.get("entityId") or "").strip()
    }
    issues_by_ref: dict[str, list[DataIssue]] = defaultdict(list)
    for issue in issues:
        if issue.ref:
            issues_by_ref[issue.ref].append(issue)
    for name, target_issues in sorted(issues_by_ref.items()):
        if name in successful:
            continue
        if name in known_ineligible:
            continue
        ineligible.append(
            {
                "entityId": name,
                "objectRef": object_refs.get(name) or name,
                "lanes": [carrier],
                "issues": [str(issue) for issue in target_issues],
                "blockers": [issue.as_dict() for issue in target_issues],
                "recoveries": sorted(
                    {issue.recovery.value for issue in target_issues}
                ),
            }
        )
    typed_decisions = [
        {
            "objectRef": object_refs.get(issue.ref) or issue.ref,
            "disposition": (
                "qualified_partial"
                if issue.ref in successful
                else "discarded"
            ),
            "stage": issue.stage.value,
            "issue": issue.code.value,
            "recovery": issue.recovery.value,
        }
        for issue in issues
    ]
    payload: dict[str, Any] = {
            "schema": existing.get("schema")
            or "quwoquan_data.source_unavailable_targets",
            "executionId": execution_id,
            "source": "content_plan_partial_closure",
            "updatedAt": now_iso(),
            "readyTargets": list(successful_names),
            "readyTargetCount": len(successful_names),
            "ineligibleTargets": ineligible,
            "ineligibleTargetCount": len(ineligible),
            "contentPlanDecisions": typed_decisions,
        }
    if ready_work_unit_ids is not None:
        payload["readyWorkUnitIds"] = list(ready_work_unit_ids)
        payload["readyWorkUnitCount"] = len(ready_work_unit_ids)
    _require_absorbed_partition(existing, payload)
    write_json(availability_path, payload)


def _require_absorbed_partition(
    existing: Mapping[str, Any],
    payload: Mapping[str, Any],
) -> None:
    """Fail where the partition breaks instead of at the next consumer.

    Downstream stages narrow the frozen scope by this file and require it to
    partition the frozen target set. When an absorbed closure classifies a
    target as neither ready nor ineligible the loss is silent here and only
    surfaces much later as an opaque ``must partition the frozen target set``,
    so the unclassified targets are named at the point they go missing.
    """
    prior_ready = {
        str(name or "").strip()
        for name in (existing.get("readyTargets") or [])
        if str(name or "").strip()
    }
    prior_ineligible = {
        str(row.get("entityId") or "").strip()
        for row in (existing.get("ineligibleTargets") or [])
        if isinstance(row, Mapping) and str(row.get("entityId") or "").strip()
    }
    absorbed_scope = prior_ready | prior_ineligible
    if not absorbed_scope:
        # 首次写入（download 阶段没有留下可用分区）时没有可比对的冻结集合。
        return
    ready = {str(name or "").strip() for name in payload.get("readyTargets") or []}
    ineligible = {
        str(row.get("entityId") or "").strip()
        for row in payload.get("ineligibleTargets") or []
        if isinstance(row, Mapping)
    }
    overlap = sorted(ready & ineligible)
    if overlap:
        raise ValueError(
            "content_plan absorption marked targets both ready and ineligible: "
            f"{overlap}"
        )
    unclassified = sorted(absorbed_scope - ready - ineligible)
    if unclassified:
        raise ValueError(
            "content_plan absorption left targets unclassified "
            "(neither planned nor blocked): "
            f"{unclassified}"
        )


@dataclass
class ContentPlanRejectLedger:
    article_rejects: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    article_reject_examples: dict[str, list[str]] = field(
        default_factory=lambda: defaultdict(list)
    )
    article_image_warnings: dict[str, int] = field(
        default_factory=lambda: defaultdict(int)
    )
    article_image_warning_examples: dict[str, list[str]] = field(
        default_factory=lambda: defaultdict(list)
    )
    image_rejects: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    image_reject_examples: dict[str, list[str]] = field(
        default_factory=lambda: defaultdict(list)
    )

    @staticmethod
    def _record(
        counts: dict[str, int],
        examples_by_reason: dict[str, list[str]],
        reason: str,
        source_id: str,
        detail: str,
    ) -> None:
        counts[reason] += 1
        examples = examples_by_reason[reason]
        if len(examples) < 5:
            examples.append(f"{source_id}{(': ' + detail) if detail else ''}")

    def reject_article(self, reason: str, source_id: str, detail: str = "") -> None:
        self._record(
            self.article_rejects,
            self.article_reject_examples,
            reason,
            source_id,
            detail,
        )

    def warn_article_image(
        self,
        reason: str,
        source_id: str,
        detail: str = "",
    ) -> None:
        self._record(
            self.article_image_warnings,
            self.article_image_warning_examples,
            reason,
            source_id,
            detail,
        )

    def reject_image(self, reason: str, source_id: str, detail: str = "") -> None:
        self._record(
            self.image_rejects,
            self.image_reject_examples,
            reason,
            source_id,
            detail,
        )


def missing_source_diagnostic(
    *,
    target: str,
    per_target_articles: int,
    minimum_articles: int,
    per_target_images: int,
    minimum_images: int,
    article_lane_enabled: bool,
    image_lane_enabled: bool,
) -> dict[str, Any]:
    """Build the closed diagnostic shape for a missing source directory."""

    article_missing = {"sources_directory_missing": 1} if article_lane_enabled else {}
    image_missing = {"sources_directory_missing": 1} if image_lane_enabled else {}
    article_examples = {"sources_directory_missing": [target]} if article_lane_enabled else {}
    image_examples = {"sources_directory_missing": [target]} if image_lane_enabled else {}
    return {
        "desiredArticleSources": per_target_articles,
        "minimumRequiredArticleSources": minimum_articles,
        "rawArticleBaseSources": 0,
        "qualifiedArticleBaseSources": 0,
        "pickedArticleBaseSources": 0,
        "desiredImageSources": per_target_images,
        "minimumRequiredImageSources": minimum_images,
        "rawImageAssets": 0,
        "qualifiedImageAssets": 0,
        "pickedImageSources": 0,
        "articleLaneEnabled": article_lane_enabled,
        "imageLaneEnabled": image_lane_enabled,
        "minimumQualityPassed": False,
        "articleQualityScore": 0.0,
        "articleLengthScore": 0.0,
        "imageCountScore": 0.0,
        "compositeScore": 0.0,
        "articleRejects": article_missing,
        "articleRejectExamples": article_examples,
        "articleImageSoftWarnings": {},
        "articleImageSoftWarningExamples": {},
        "imageRejects": image_missing,
        "imageRejectExamples": image_examples,
    }


def absorb_content_plan_shortfalls(
    *,
    ctx: ExecutionContext,
    active_spec: Mapping[str, Any],
    items: list[dict[str, Any]],
    issues: list[DataIssue],
    carrier: str,
    persist_absorb: Callable[..., None],
) -> bool:
    """Absorb object shortfalls whenever a non-empty real plan remains."""

    if carrier not in {"article", "image", "video"} or not issues:
        return False
    from content.execution.spec_contract import approved_quota

    quota = approved_quota(ctx.execution_id)
    absorbable_codes = {
        DataIssueCode.MEDIA_PUBLISHABLE_SHORTFALL,
        DataIssueCode.SOURCE_MISSING,
        DataIssueCode.SOURCE_RETAINED_SHORTFALL,
    }
    if not items or any(issue.code not in absorbable_codes for issue in issues):
        return False
    content = (
        active_spec.get("content")
        if isinstance(active_spec.get("content"), Mapping)
        else {}
    )
    work_unit_mode = "workUnits" in content
    ready_work_unit_ids: list[str] | None = None
    successful_names: list[str] = []
    seen: set[str] = set()
    if work_unit_mode:
        raw_work_units = content.get("workUnits")
        if not isinstance(raw_work_units, list):
            return False
        expected_by_id = {
            str(row.get("workUnitId") or "").strip(): row
            for row in raw_work_units
            if isinstance(row, Mapping)
            and str(row.get("workUnitId") or "").strip()
        }
        ready_work_unit_ids = []
        for item in items:
            work_unit_id = str(item.get("workUnitId") or "").strip()
            if not work_unit_id or work_unit_id not in expected_by_id:
                return False
            if work_unit_id not in ready_work_unit_ids:
                ready_work_unit_ids.append(work_unit_id)
        ready_work_units = [
            dict(expected_by_id[work_unit_id])
            for work_unit_id in ready_work_unit_ids
        ]
        if not ready_work_units:
            return False
        for row in ready_work_units:
            target = row.get("coverageTarget")
            name = (
                str(target.get("name") or "").strip()
                if isinstance(target, Mapping)
                else ""
            )
            if name and name not in seen:
                seen.add(name)
                successful_names.append(name)
        content["workUnits"] = ready_work_units
        policy = active_spec.setdefault("executionPolicy", {})
        policy["targetObjectCount"] = len(ready_work_units)
        policy["targetEntityCount"] = len(successful_names)
        acceptance = active_spec.setdefault("acceptance", {})
        acceptance["minEntities"] = len(successful_names)
        acceptance["minPostsPerEntity"] = 0
    else:
        for item in items:
            name = planned_item_owning_target(item)
            if name and name not in seen:
                seen.add(name)
                successful_names.append(name)
    if not successful_names:
        return False
    scope = active_spec.setdefault("scope", {})
    coverage = list(scope.get("coverageTargets") or [])
    object_refs: dict[str, str] = {}
    for row in coverage:
        if not isinstance(row, Mapping):
            continue
        name = str(row.get("name") or "").strip()
        entity_type = str(row.get("entityType") or "").strip()
        if name and entity_type:
            object_refs[name] = f"/entity/{entity_type}/{name}"
    scope["coverageTargets"] = [
        row
        for row in coverage
        if str((row or {}).get("name") or "").strip() in seen
    ]
    persist_absorb(
        ctx.execution_id,
        successful_names=successful_names,
        issues=issues,
        object_refs=object_refs,
        carrier=carrier,
        ready_work_unit_ids=ready_work_unit_ids,
    )
    print(
        "[content_plan] absorbed object-level shortfall "
        f"carrier={carrier} planned={len(items)} "
        f"readyTargets={len(successful_names)}/quota={quota} "
        f"shortfalls={len(issues)}"
    )
    return True
