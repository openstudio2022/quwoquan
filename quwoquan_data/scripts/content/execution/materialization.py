"""Frozen execution-spec materialization and pre-freeze source qualification."""
from __future__ import annotations

from dataclasses import dataclass

from core.control_types import TargetSelector
from core.data_issue import DataIssueCode
from core.paths import REPO_ROOT
from core.runtime_policy import active_runtime_policy
from content.execution import store
from content.execution.identity import SelectionPolicy
from content.execution.selection import (
    SelectionRequest,
    create_execution_selection,
)
from content.execution.source_selection import (
    TargetSourceCandidate,
    TargetSourceQualification,
)


@dataclass(frozen=True, slots=True)
class _QualifiedVideoSource:
    """Non-persisted pre-freeze proof that a target has media supply."""

    title: str
    url: str
    mode: str

    def to_dict(self) -> dict[str, str]:
        return {
            "provider": "video_media_precheck",
            "title": self.title,
            "url": self.url,
            "mode": self.mode,
        }


def _homepage_source_qualifier(
    execution_id: str,
    target: TargetSourceCandidate,
) -> TargetSourceQualification:
    from content.source.research.baike_com import geo_context_terms_from_ref
    from content.source.research.homepage_authority import qualify_homepage_authority_content
    from content.homepage.quality_policy import (
        homepage_body_char_minimum,
        homepage_fact_count_minimum,
        homepage_fact_char_minimum,
    )

    qualification = qualify_homepage_authority_content(
        target.name,
        entity_aliases=target.aliases,
        geo_context_terms=geo_context_terms_from_ref(target.geo_tag_ref),
        minimum_body_chars=homepage_body_char_minimum(execution_id),
        minimum_fact_count=homepage_fact_count_minimum(execution_id),
        minimum_fact_chars=homepage_fact_char_minimum(execution_id),
    )
    return TargetSourceQualification(
        accepted=qualification.accepted,
        qualified_source=qualification.qualified_source,
        rejection_code=qualification.rejection_code,
    )


def _video_source_qualifier(
    target: TargetSourceCandidate,
) -> TargetSourceQualification:
    """Fast, bounded Commons precheck before the deeper frozen plan is built."""

    from content.source.research.auto_plan_video import (
        discover_commons_sourced_videos,
    )

    aliases = list(dict.fromkeys([target.name, *target.aliases]))
    try:
        videos = discover_commons_sourced_videos(
            target.name,
            entity_aliases=aliases,
            diagnostics=[],
        )
    except (OSError, TimeoutError, ValueError):
        return TargetSourceQualification(
            accepted=False,
            qualified_source=None,
            rejection_code=DataIssueCode.MEDIA_PUBLISHABLE_SHORTFALL,
        )
    if videos:
        return TargetSourceQualification(
            accepted=True,
            qualified_source=_QualifiedVideoSource(
                title=target.name,
                url=str(videos[0]["assetUrl"]),
                mode="sourced_video",
            ),
        )
    return TargetSourceQualification(
        accepted=False,
        qualified_source=None,
        rejection_code=DataIssueCode.MEDIA_PUBLISHABLE_SHORTFALL,
    )


def ensure_execution_spec(
    recipe: dict[str, Any],
    selection: dict[str, Any],
    *,
    execution_id: str,
    target_selector: TargetSelector,
    content_type: str,
    target_names: tuple[str, ...],
    inherit_frozen_targets: bool = False,
    inherited_targets: tuple[dict[str, Any], ...] = (),
) -> str:
    if not selection:
        raise SystemExit("[task execute] recipe.selection is required for an execution work package")
    if content_type == "homepage" and target_selector is not TargetSelector.SOURCE_READY_PRIORITY:
        raise SystemExit(
            "[task execute] GATE_BLOCK homepage carrier requires --selector source-ready-priority"
        )
    if store.spec_exists(execution_id):
        return execution_id
    source_qualifier = None
    qualification_source_key = "qualifiedHomepageSource"
    persist_qualified_source = True
    if target_selector is TargetSelector.SOURCE_READY_PRIORITY:
        if content_type == "homepage":
            source_qualifier = lambda target: _homepage_source_qualifier(execution_id, target)
        elif content_type == "video":
            source_qualifier = _video_source_qualifier
            qualification_source_key = "qualifiedVideoSource"
            persist_qualified_source = False
        else:
            raise SystemExit(
                "[task execute] GATE_BLOCK source-ready-priority requires homepage or video carrier"
            )
        if inherit_frozen_targets:
            # Qualifier remains only to satisfy the selector contract; inherited
            # names are frozen without another network precheck.
            persist_qualified_source = False
    create_execution_selection(
        SelectionRequest(
            execution_id=execution_id,
            discovery_path=REPO_ROOT / str(selection.get("discovery")),
            limit=int(selection.get("limit")),
            quota=int(selection["approvedQuota"]),
            oversample_factor=active_runtime_policy().oversample_factor,
            region=str(selection["region"]),
            category=str(selection["category"]),
            name=str(selection["name"]),
            title=str(selection["title"]),
            intent_label=str(selection["intentLabel"]),
            preset_ref=str(recipe.get("presetRef")),
            entity_articles_per_target=int(selection["entityArticlesPerTarget"]),
            entity_homepages_per_target=int(selection["entityHomepagesPerTarget"]),
            image_works_per_target=int(selection["imageWorksPerTarget"]),
            video_works_per_target=int(selection["videoWorksPerTarget"]),
            created_by="task execute",
            selection_policy=SelectionPolicy.FROZEN,
            target_selector=target_selector,
            source_qualifier=source_qualifier,
            qualification_source_key=qualification_source_key,
            persist_qualified_source=persist_qualified_source,
            target_names=target_names,
            inherit_frozen_targets=bool(inherit_frozen_targets),
            inherited_targets=inherited_targets,
        )
    )
    return execution_id


__all__ = ["ensure_execution_spec"]
