"""Frozen execution-spec materialization and pre-freeze source qualification."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.control_types import TargetSelector
from core.data_issue import DataIssueCode
from core.paths import REPO_ROOT
from core.runtime_policy import active_runtime_policy

from content.execution import store
from content.execution.identity import SelectionPolicy
from content.execution.planning.selection import (
    SelectionRequest,
    create_execution_selection,
)
from content.execution.planning.source_selection import (
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


@dataclass(frozen=True, slots=True)
class _SourceQualificationBinding:
    """One prebuilt qualifier plus its upstream, carrier-neutral supply scope."""

    qualifier: Any
    candidate_names: tuple[str, ...] | None = None
    available_supply_count: int | None = None
    work_unit_candidates: tuple[dict[str, Any], ...] = ()


def _video_work_unit_bindings(
    context: Any,
    kind: str,
) -> dict[tuple[str, str], dict[str, Any]]:
    """Join each receipt asset to aliases from its exact verified manifest."""
    from core.io import read_json
    from core.schema import assert_valid
    from content.execution.campaign.external_inputs import file_digest, payload_digest

    root = context.acquisition_root(kind).resolve()
    bindings: dict[tuple[str, str], dict[str, Any]] = {}
    for descriptor in context.descriptors(kind):
        relative = Path(str(descriptor["manifestRef"]))
        path = (root / relative).resolve()
        if relative.is_absolute() or root not in path.parents or not path.is_file():
            raise ValueError("professional video manifestRef is unsafe or missing")
        manifest = read_json(path)
        if not isinstance(manifest, Mapping):
            raise TypeError("professional video manifest must be an object")
        assert_valid(
            dict(manifest),
            "source",
            "professional_video_acquisition_manifest",
            label="professional video work-unit manifest",
        )
        if (
            descriptor.get("manifestDigest") != payload_digest(manifest)
            or descriptor.get("manifestFileDigest") != file_digest(path)
            or descriptor.get("manifestId") != manifest.get("manifestId")
        ):
            raise ValueError("professional video work-unit manifest descriptor drift")
        receipt_ref = str(descriptor["receiptRef"])
        for raw in manifest["items"]:
            item = dict(raw)
            asset_id = str(item.get("assetId") or "").strip()
            entity_id = str(item.get("entityId") or "").strip()
            aliases = tuple(
                dict.fromkeys(
                    str(value).strip()
                    for value in item.get("entityAliases") or []
                    if str(value).strip()
                )
            )
            key = (receipt_ref, asset_id)
            if not asset_id or not entity_id or key in bindings:
                raise ValueError("professional video manifest asset identity is invalid")
            bindings[key] = {
                "manifestRef": str(descriptor["manifestRef"]),
                "manifestDigest": str(descriptor["manifestDigest"]),
                "receiptDigest": str(descriptor["receiptDigest"]),
                "sourceEntityId": entity_id,
                "sourceEntityAliases": aliases,
            }
    return bindings


def _homepage_source_qualifier(
    execution_id: str,
    target: TargetSourceCandidate,
) -> TargetSourceQualification:
    from content.homepage.quality_policy import (
        homepage_body_char_minimum,
        homepage_fact_char_minimum,
        homepage_fact_count_minimum,
    )
    from content.source.research.baike_com import geo_context_terms_from_ref
    from content.source.research.homepage_authority import (
        qualify_homepage_authority_content,
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
    execution_id: str,
    target: TargetSourceCandidate,
    *,
    verified_index: Any | None = None,
) -> TargetSourceQualification:
    """Qualify frozen professional video first, otherwise use bounded Commons."""

    if verified_index is not None:
        videos = verified_index.specs_for_names(
            tuple(dict.fromkeys([target.name, *target.aliases]))
        )
        if videos:
            candidate = videos[0]
            return TargetSourceQualification(
                accepted=True,
                qualified_source=_QualifiedVideoSource(
                    title=str(candidate.get("title") or target.name),
                    url=str(candidate.get("assetUrl") or ""),
                    mode="sourced_video",
                ),
            )
        return TargetSourceQualification(
            accepted=False,
            qualified_source=None,
            rejection_code=DataIssueCode.MEDIA_PUBLISHABLE_SHORTFALL,
        )

    from content.execution.campaign.external_input_runtime import (
        bound_runtime_external_input_context,
    )
    from content.execution.campaign.external_inputs import (
        PROFESSIONAL_VIDEO_ACQUISITION_KIND,
    )

    context = bound_runtime_external_input_context(execution_id, "video")
    if context is not None and context.has_kind(
        PROFESSIONAL_VIDEO_ACQUISITION_KIND
    ):
        from content.source.professional_video_receipt import (
            acquired_video_specs_for_entity,
        )

        receipt_refs = context.receipt_refs(
            PROFESSIONAL_VIDEO_ACQUISITION_KIND
        )
        acquisition_root = context.acquisition_root(
            PROFESSIONAL_VIDEO_ACQUISITION_KIND
        )
        try:
            # receipt 的 entityId 可能是 catalog canonical 名的别名
            # （例如 receipt「西湖」对应 catalog「杭州西湖」）。按 canonical
            # 名 + aliases 依次归一化匹配；这是名字规范化，不改变
            # frozen receipt 集合，也不绕过安全审查结论。
            videos: list[dict[str, Any]] = []
            for entity_name in dict.fromkeys([target.name, *target.aliases]):
                videos = acquired_video_specs_for_entity(
                    receipt_refs,
                    entity_id=entity_name,
                    root=acquisition_root,
                )
                if videos:
                    break
        except (OSError, TypeError, ValueError):
            return TargetSourceQualification(
                accepted=False,
                qualified_source=None,
                rejection_code=DataIssueCode.MEDIA_PUBLISHABLE_SHORTFALL,
            )
        if videos:
            candidate = videos[0]
            return TargetSourceQualification(
                accepted=True,
                qualified_source=_QualifiedVideoSource(
                    title=str(candidate.get("title") or target.name),
                    url=str(candidate.get("assetUrl") or ""),
                    mode="sourced_video",
                ),
            )
        return TargetSourceQualification(
            accepted=False,
            qualified_source=None,
            rejection_code=DataIssueCode.MEDIA_PUBLISHABLE_SHORTFALL,
        )

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


def _video_source_qualification_binding(
    execution_id: str,
) -> _SourceQualificationBinding:
    """Verify frozen video supply once, then serve O(1) in-memory qualifiers."""
    from content.execution.campaign.external_input_runtime import (
        bound_runtime_external_input_context,
    )
    from content.execution.campaign.external_inputs import (
        PROFESSIONAL_VIDEO_ACQUISITION_KIND,
    )

    context = bound_runtime_external_input_context(execution_id, "video")
    if context is None or not context.has_kind(
        PROFESSIONAL_VIDEO_ACQUISITION_KIND
    ):
        return _SourceQualificationBinding(
            qualifier=lambda target: _video_source_qualifier(execution_id, target)
        )

    from content.source.professional_video_receipt import (
        build_acquired_video_spec_index,
    )

    index = build_acquired_video_spec_index(
        context.receipt_refs(PROFESSIONAL_VIDEO_ACQUISITION_KIND),
        root=context.acquisition_root(PROFESSIONAL_VIDEO_ACQUISITION_KIND),
        work_unit_bindings=_video_work_unit_bindings(
            context,
            PROFESSIONAL_VIDEO_ACQUISITION_KIND,
        ),
    )
    return _SourceQualificationBinding(
        qualifier=lambda target: _video_source_qualifier(
            execution_id,
            target,
            verified_index=index,
        ),
        candidate_names=index.entity_names,
        available_supply_count=index.accepted_asset_count,
        work_unit_candidates=index.work_unit_candidates,
    )


def _image_source_qualification_binding(
    execution_id: str,
) -> _SourceQualificationBinding | None:
    from content.execution.campaign.external_input_runtime import (
        bound_runtime_external_input_context,
    )
    from content.execution.campaign.external_inputs import (
        PROFESSIONAL_IMAGE_ACQUISITION_KIND,
    )

    context = bound_runtime_external_input_context(execution_id, "image")
    if context is None or not context.has_kind(PROFESSIONAL_IMAGE_ACQUISITION_KIND):
        return None
    from content.source.professional_image_acquisition_index import (
        build_acquired_image_spec_index,
    )

    index = build_acquired_image_spec_index(
        context.receipt_refs(PROFESSIONAL_IMAGE_ACQUISITION_KIND),
        root=context.acquisition_root(PROFESSIONAL_IMAGE_ACQUISITION_KIND),
        descriptors=context.descriptors(PROFESSIONAL_IMAGE_ACQUISITION_KIND),
    )
    return _SourceQualificationBinding(
        qualifier=None,
        candidate_names=index.entity_names,
        available_supply_count=index.accepted_asset_count,
        work_unit_candidates=index.work_unit_candidates,
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
    source_pool_targets: tuple[dict[str, Any], ...] = ()
    if isinstance(selection.get("scaleSourcePool"), dict):
        from content.source.research.scale_source_pool_runtime import (
            frozen_scale_source_pool_targets,
        )

        source_pool_targets = frozen_scale_source_pool_targets(
            execution_id,
            content_type,
            direct_selection=selection,
        )
    source_qualifier = None
    qualification_source_key = "qualifiedHomepageSource"
    persist_qualified_source = True
    qualification_candidate_names: tuple[str, ...] | None = None
    qualification_supply_count: int | None = None
    media_work_unit_candidates: tuple[dict[str, Any], ...] = ()
    media_binding: _SourceQualificationBinding | None = None
    if content_type == "image":
        media_binding = _image_source_qualification_binding(execution_id)
    elif content_type == "video":
        media_binding = _video_source_qualification_binding(execution_id)
    if media_binding is not None:
        qualification_candidate_names = media_binding.candidate_names
        qualification_supply_count = media_binding.available_supply_count
        media_work_unit_candidates = media_binding.work_unit_candidates
    if target_selector is TargetSelector.SOURCE_READY_PRIORITY:
        if content_type == "homepage":
            source_qualifier = lambda target: _homepage_source_qualifier(execution_id, target)
        elif content_type == "video":
            binding = media_binding or _video_source_qualification_binding(execution_id)
            source_qualifier = binding.qualifier
            qualification_candidate_names = binding.candidate_names
            qualification_supply_count = binding.available_supply_count
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
            capacity_calibration=dict(selection["capacityCalibration"]),
            worker_host_set_binding=(
                dict(selection["workerHostSetBinding"])
                if isinstance(selection.get("workerHostSetBinding"), dict)
                else None
            ),
            scale_source_pool=(
                dict(selection["scaleSourcePool"])
                if isinstance(selection.get("scaleSourcePool"), dict)
                else None
            ),
            source_pool_evidence_root_ref=(
                str(selection["sourcePoolEvidenceRootRef"])
                if selection.get("sourcePoolEvidenceRootRef") is not None
                else None
            ),
            source_pool_selection=(
                dict(selection["sourcePoolSelection"])
                if isinstance(selection.get("sourcePoolSelection"), dict)
                else None
            ),
            source_pool_targets=source_pool_targets,
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
            qualification_candidate_names=qualification_candidate_names,
            qualification_supply_count=qualification_supply_count,
            media_work_unit_candidates=media_work_unit_candidates,
            target_names=target_names,
            inherit_frozen_targets=bool(inherit_frozen_targets),
            inherited_targets=inherited_targets,
        )
    )
    return execution_id


__all__ = ["ensure_execution_spec"]
