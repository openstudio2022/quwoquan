"""Frozen execution-spec materialization and pre-freeze source qualification."""
from __future__ import annotations

from core.control_types import TargetSelector
from core.paths import REPO_ROOT
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


def _homepage_source_qualifier(target: TargetSourceCandidate) -> TargetSourceQualification:
    from content.source.research.baike_com import geo_context_terms_from_ref
    from content.source.research.homepage_authority import qualify_homepage_authority_content

    qualification = qualify_homepage_authority_content(
        target.name,
        entity_aliases=target.aliases,
        geo_context_terms=geo_context_terms_from_ref(target.geo_tag_ref),
    )
    return TargetSourceQualification(
        accepted=qualification.accepted,
        qualified_source=qualification.qualified_source,
        rejection_code=qualification.rejection_code,
    )


def ensure_execution_spec(
    recipe: dict[str, Any],
    selection: dict[str, Any],
    *,
    execution_id: str,
    target_selector: TargetSelector,
    content_type: str,
    target_names: tuple[str, ...],
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
    if target_selector is TargetSelector.SOURCE_READY_PRIORITY:
        if content_type != "homepage":
            raise SystemExit(
                "[task execute] GATE_BLOCK source-ready-priority currently requires homepage carrier"
            )
        source_qualifier = _homepage_source_qualifier
    create_execution_selection(
        SelectionRequest(
            execution_id=execution_id,
            discovery_path=REPO_ROOT / str(selection.get("discovery")),
            limit=int(selection.get("limit")),
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
            target_names=target_names,
        )
    )
    return execution_id


__all__ = ["ensure_execution_spec"]
