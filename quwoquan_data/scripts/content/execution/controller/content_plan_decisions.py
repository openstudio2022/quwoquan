"""Typed bookkeeping and oversample decisions for content planning."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from content.execution.support import DataIssue, DataIssueCode, ExecutionContext
from content.execution.support import execution_root, read_json, write_json


def persist_video_content_plan_absorb(
    execution_id: str,
    *,
    successful_names: list[str],
    failed_names: list[str],
) -> None:
    """Persist the ready/ineligible repartition after video oversample absorb."""

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
    for name in failed_names:
        if name in known_ineligible:
            continue
        ineligible.append(
            {
                "entityId": name,
                "lanes": ["video"],
                "issues": [
                    f"{name}: [DATA.MEDIA.PUBLISHABLE_SHORTFALL] content_plan "
                    "oversample absorb; retained rights-cleared frames below minimum"
                ],
                "blockers": [
                    {
                        "code": "DATA.MEDIA.PUBLISHABLE_SHORTFALL",
                        "stage": "content_plan",
                        "ref": name,
                        "lane": "video",
                        "recovery": "retry_source_discovery",
                        "message": f"{name}: video oversample absorb after frame shortfall",
                        "attrs": {"carrier": "video", "absorbed": "true"},
                    }
                ],
                "recoveries": ["retry_source_discovery"],
            }
        )
    write_json(
        availability_path,
        {
            "schema": existing.get("schema")
            or "quwoquan_data.source_unavailable_targets",
            "executionId": execution_id,
            "source": "content_plan_video_oversample_absorb",
            "updatedAt": now_iso(),
            "readyTargets": list(successful_names),
            "readyTargetCount": len(successful_names),
            "ineligibleTargets": ineligible,
            "ineligibleTargetCount": len(ineligible),
        },
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


def absorb_video_content_plan_shortfalls(
    *,
    ctx: ExecutionContext,
    active_spec: Mapping[str, Any],
    items: list[dict[str, Any]],
    issues: list[DataIssue],
    video_lane_enabled: bool,
    persist_absorb: Callable[..., None],
) -> bool:
    """Absorb only a rights-safe video oversample tail above approved quota."""

    if not video_lane_enabled or not issues:
        return False
    from content.execution.spec_contract import approved_quota

    quota = approved_quota(ctx.execution_id)
    absorbable_codes = {
        DataIssueCode.MEDIA_PUBLISHABLE_SHORTFALL,
        DataIssueCode.SOURCE_MISSING,
        DataIssueCode.SOURCE_RETAINED_SHORTFALL,
    }
    if len(items) < quota or any(issue.code not in absorbable_codes for issue in issues):
        return False
    successful_names: list[str] = []
    seen: set[str] = set()
    for item in items:
        tags = item.get("entityTags") or []
        name = str(tags[0] if tags else "").strip()
        if name and name not in seen:
            seen.add(name)
            successful_names.append(name)
    if len(successful_names) < quota:
        return False
    failed_names = {
        str(issue.ref or "").strip()
        for issue in issues
        if str(issue.ref or "").strip()
    }
    scope = active_spec.setdefault("scope", {})
    coverage = list(scope.get("coverageTargets") or [])
    scope["coverageTargets"] = [
        row
        for row in coverage
        if str((row or {}).get("name") or "").strip() in seen
    ]
    persist_absorb(
        ctx.execution_id,
        successful_names=successful_names,
        failed_names=sorted(failed_names),
    )
    print(
        "[content_plan] absorbed video oversample shortfall "
        f"planned={len(successful_names)}/quota={quota} "
        f"discarded={len(failed_names)}"
    )
    return True
