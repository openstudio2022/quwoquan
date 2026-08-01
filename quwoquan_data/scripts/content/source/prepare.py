"""Prepare inputs for download command steps."""
from __future__ import annotations

from pathlib import Path

from core.paths import (
    STAGE_DOWNLOAD,
    execution_assistant_task,
    execution_assistant_tasks_dir,
    execution_root,
    execution_shared_dir,
)
from core.io import read_json, write_json, write_assistant_task
from core.carrier_contract import research_plan_files
from core.content_source_registry import build_content_source_guidance
from core.source_catalog import source_plan_guidance, vertical_from_task_id
from core.source_plan_contract import source_plan_rule_signature
from content.source.source_unit import resolve_entity_object_dir
from governance.coverage.source_registry import build_travel_source_guidance

# lane → download 来源计划文件；唯一真相源在 core/carrier_contract.py。
RESEARCH_PLAN_FILES = research_plan_files()


def canonical_coverage_entity_types(execution_id: str) -> dict[str, str]:
    """task spec scope.coverageTargets 的 name/alias -> canonical entityType 映射。"""
    try:
        from content.execution import store

        spec = store.load_spec(execution_id)
    except Exception:  # noqa: BLE001
        return {}
    out: dict[str, str] = {}
    scope = spec.get("scope") if isinstance(spec.get("scope"), dict) else {}
    for target in scope.get("coverageTargets") or []:
        if not isinstance(target, dict):
            continue
        etype = str(target.get("entityType") or "").strip()
        if not etype:
            continue
        name = str(target.get("name") or "").strip()
        if name and name not in out:
            out[name] = etype
        for alias in target.get("aliases") or []:
            alias_name = str(alias or "").strip()
            if alias_name and alias_name not in out:
                out[alias_name] = etype
    return out


def resolve_research_entity_types(
    execution_id: str,
    entity_ids: list[str],
    *,
    fallback_type: str = "",
) -> dict[str, str]:
    """按实体解析 research 目录类型：coverageTargets canonical 优先，缺失即 fail-fast。

    WP5 实测产线 bug：`download research-plan` 旁路允许空/单值 --entity-type 应用到
    全部实体，空串在 resolve_entity_object_dir 静默回退 DEFAULT_DOMAIN_ETYPE
    （地点/打卡地），错值则整批套错类型，在契约外类型目录批量制造漂移产物。
    此处以 task spec 为唯一真相源校正；两边都无类型时抛错而非默认。
    """
    canonical = canonical_coverage_entity_types(execution_id)
    fallback = str(fallback_type or "").strip()
    resolved: dict[str, str] = {}
    for raw_id in entity_ids:
        entity_id = str(raw_id or "").strip()
        if not entity_id:
            continue
        etype = canonical.get(entity_id) or fallback
        if not etype:
            raise ValueError(
                f"entityType missing for research entity {entity_id!r}: "
                "task scope.coverageTargets has no canonical type and no explicit "
                "--entity-type was given; refusing default-type directory drift"
            )
        resolved[entity_id] = etype
    return resolved


def assert_research_entity_type_bindings(
    execution_id: str,
) -> None:
    """Reject external source-plan output outside the frozen target type binding.

    Managed research agents write under ``entities/<domain>/<type>/<name>``.
    The path is therefore part of the immutable target contract, not a
    best-effort routing hint.  Check every existing lane plan before a new
    prepare pass so an old or external write cannot coexist until a later
    source-unit reader happens to encounter the conflicting tree.
    """
    canonical = canonical_coverage_entity_types(execution_id)
    entities_root = execution_root(execution_id) / "entities"
    if not entities_root.is_dir() or not canonical:
        return
    filenames = set(RESEARCH_PLAN_FILES.values())
    for plan_path in entities_root.rglob("*.json"):
        if plan_path.name not in filenames:
            continue
        try:
            relative = plan_path.relative_to(entities_root)
        except ValueError:
            continue
        # entities/<domain>/<type>/<name>/1.download/<lane>_source_plan.json
        if len(relative.parts) != 5 or relative.parts[-2] != STAGE_DOWNLOAD:
            continue
        domain, subtype, path_name = relative.parts[:3]
        expected = canonical.get(path_name)
        if expected is None:
            continue
        actual = f"{domain}/{subtype}"
        if actual != expected:
            raise ValueError(
                "entity type drift: frozen coverage target "
                f"{expected}/{path_name} has research output at "
                f"{actual}/{path_name}: "
                f"{plan_path.relative_to(execution_root(execution_id)).as_posix()}"
            )
        try:
            payload = read_json(plan_path)
        except (OSError, ValueError, TypeError) as exc:
            raise ValueError(
                f"invalid research source plan: "
                f"{plan_path.relative_to(execution_root(execution_id)).as_posix()}"
            ) from exc
        plan_execution_id = str(payload.get("executionId") or "").strip()
        plan_ref = str(payload.get("ref") or "").strip()
        lane_payload = payload.get("payload")
        lane_payload = lane_payload if isinstance(lane_payload, dict) else {}
        plan_entity_type = str(lane_payload.get("entityType") or "").strip()
        if plan_execution_id != execution_id:
            raise ValueError(
                f"research source plan executionId mismatch at "
                f"{plan_path.relative_to(execution_root(execution_id)).as_posix()}"
            )
        if plan_ref != path_name or str(lane_payload.get("entityId") or "").strip() != path_name:
            raise ValueError(
                f"research source plan entity binding mismatch at "
                f"{plan_path.relative_to(execution_root(execution_id)).as_posix()}"
            )
        if plan_entity_type != expected:
            raise ValueError(
                f"research source plan entityType mismatch for {path_name}: "
                f"frozen={expected}, plan={plan_entity_type or '<missing>'}"
            )


def research_entity_type_binding_error(execution_id: str) -> str | None:
    """Return the frozen-tree binding failure in checkpoint-friendly form."""
    try:
        assert_research_entity_type_bindings(execution_id)
    except ValueError as exc:
        return str(exc)
    return None


def _lane_payload(
    lane: str,
    *,
    ref: str,
    ent: dict,
    guidance: dict,
    guidance_ref: str,
) -> dict:
    common = {
        "entityId": ref,
        "canonicalName": ent.get("canonicalName", ""),
        "entityType": ent.get("entityType", ""),
        "researchLane": lane,
    }
    # 静态 vertical 级采源指引（类别明细 + 站点注册表）体量上千行且对所有实体完全相同，
    # 抽到批次共享文件作单一真相源，per-entity 计划只保留「必须覆盖的类别摘要 + 引用」，
    # 避免把同一份指引在每实体每 lane 复制一遍把计划文件撑到几千行。
    category_summary = {
        "minCategoriesPerEntity": guidance.get("minCategoriesPerEntity"),
        "coreCategories": guidance.get("coreCategories", []),
        "preferredCategories": guidance.get("preferredCategories", []),
        "instruction": guidance.get("instruction", ""),
    }
    source_image_policy = {
        "sameSourceRequired": True,
        "requiredFields": [
            "url",
            "license",
            "credit",
            "sourceUrl",
            "termsUrl",
            "licenseSnapshot",
            "authorizationProof",
            "usageScope",
            "modelReleaseStatus",
            "width",
            "height",
            "relevance",
        ],
        "minWidth": 640,
        "minHeight": 426,
        "minLongEdge": 800,
        "rejectPatterns": ["thumbnail", "r_720x480", "600x600", "compressed preview"],
        "note": "source image is part of this text source draft; do not mix homepage/image lane assets",
    }
    if lane == "homepage":
        return {
            **common,
            "policyRevision": "encyclopedia-primary",
            "sourceGuidanceRef": guidance_ref,
            "sourceCategorySummary": category_summary,
            "sourceImagePolicy": {
                **source_image_policy,
                "sameSourceRequired": False,
                "sameSourcePreferred": True,
                "fallbackEvidenceMode": "independent_rights_cleared",
                "note": (
                    "prefer images placed in the primary encyclopedia page; when absent, "
                    "use only a separate entity-matched media collection with complete "
                    "asset-level rights evidence"
                ),
            },
            "primaryEvidenceRef": "",
            "sources": [],
            "homepageMediaCollections": [],
        }
    if lane == "article":
        return {
            **common,
            "sourceGuidanceRef": guidance_ref,
            "sourceCategorySummary": category_summary,
            "sourceImagePolicy": source_image_policy,
            "sources": [],
        }
    if lane == "video":
        return {
            **common,
            "sourceGuidanceRef": guidance_ref,
            "sourceCategorySummary": category_summary,
            "renderStrategy": "rights_cleared_image_sequence",
            "sourceAssetPolicy": {
                "sameEntityRequired": True,
                "rightsEvidenceRequired": True,
                "commercialUseRequired": True,
                "watermarkForbidden": True,
                "requiredFields": [
                    "assetRef",
                    "sha256",
                    "license",
                    "authorizationProof",
                    "sourceUrl",
                ],
            },
            "assets": [],
        }
    return {
        **common,
        "sourceCollectionPolicy": {
            "minImagesPerWork": 1,
            "maxImagesPerWork": 20,
            "sameCollectionRequired": True,
            "requiredFields": [
                "sourceCollectionId",
                "creator",
                "collectionPageUrl",
                "license",
                "termsUrl",
                "authorizationProof",
                "usageScope",
                "modelReleaseStatus",
            ],
            "discoveryPolicy": (
                "平台不按来源名硬阻断；Pinterest/小红书/微博/抖音/B站等可做发现或参考，"
                "但进入 collections 的每张图都必须具备资产级许可、署名、条款和授权证据。"
            ),
            "defaultDiscoveryRoles": ["discovery_only", "reference_only", "licensed_candidate", "publish_candidate"],
            "aiImagesAllowed": False,
        },
        "collections": [],
    }


def prepare_source_plan(execution_id: str, entities: list[dict]) -> Path:
    """Prepare one isolated research plan per formal content carrier."""
    assert_research_entity_type_bindings(execution_id)
    guidance = source_plan_guidance(vertical_from_task_id(execution_id))
    vertical = vertical_from_task_id(execution_id)
    registry_guidance = build_travel_source_guidance() if vertical == "travel" else {}
    content_source_guidance = build_content_source_guidance(vertical)
    if registry_guidance:
        registry_guidance = {
            **registry_guidance,
            "contentSourceGuidance": content_source_guidance,
        }
    else:
        registry_guidance = {"contentSourceGuidance": content_source_guidance}
    # 把静态 vertical 级采源指引写一次到批次共享文件（单一真相源），
    # per-entity 计划只引用，避免上千行指引在每实体每 lane 重复内联。
    shared_dir = execution_shared_dir(execution_id)
    shared_dir.mkdir(parents=True, exist_ok=True)
    guidance_path = shared_dir / "source_research_guidance.json"
    write_json(
        guidance_path,
        {
            "schema": "quwoquan_data.source_research_guidance",
            "vertical": vertical,
            "sourceCategoryGuidance": guidance,
            "sourceRegistryGuidance": registry_guidance,
        },
    )
    guidance_ref = str(guidance_path.relative_to(execution_root(execution_id)))
    # 类型校正单一真相源：coverageTargets canonical 覆盖调用方 hint；
    # 两边都缺类型直接抛错，禁止静默落 DEFAULT_DOMAIN_ETYPE 制造契约外类型目录。
    canonical_types = canonical_coverage_entity_types(execution_id)
    refs_by_lane: dict[str, list[str]] = {lane: [] for lane in RESEARCH_PLAN_FILES}
    for ent in entities:
        ref = ent.get("entityId", ent.get("id"))
        hinted = str(ent.get("entityType") or "").strip()
        etype = canonical_types.get(str(ref or "").strip()) or hinted
        if not etype:
            raise ValueError(
                f"entityType missing for research entity {ref!r}: "
                "task scope.coverageTargets has no canonical type and caller "
                "provided none; refusing default-type directory drift"
            )
        if etype != hinted:
            ent = {**ent, "entityType": etype}
        obj = resolve_entity_object_dir(execution_id, ref, etype_hint=etype)
        for lane, filename in RESEARCH_PLAN_FILES.items():
            plan_path = obj / STAGE_DOWNLOAD / filename
            if not plan_path.is_file():
                plan_path.parent.mkdir(parents=True, exist_ok=True)
                write_json(
                    plan_path,
                    {
                        "schema": "quwoquan_data.stage_envelope",
                        "executionId": execution_id,
                        "step": f"{lane}_research",
                        "ref": ref,
                        "sourceRuleSignature": source_plan_rule_signature(vertical, str(ref or "")),
                        "payload": _lane_payload(
                            lane,
                            ref=ref,
                            ent=ent,
                            guidance=guidance,
                            guidance_ref=guidance_ref,
                        ),
                    },
                )
            refs_by_lane[lane].append(ref)

    for lane, refs in refs_by_lane.items():
        manifest_path = (
            execution_assistant_tasks_dir(execution_id)
            / f"download_{lane}_research.json"
        )
        write_assistant_task(
            manifest_path,
            step=f"{lane}_research",
            input_dir=execution_root(execution_id) / "entities",
            result_dir=execution_root(execution_id) / "entities",
            refs=refs,
        )
    return execution_root(execution_id) / "entities"


def prepare_source_screen(execution_id: str, fetched_sources: list[dict]) -> Path:
    """Prepare source_screen inputs from fetched source summaries."""
    inputs_dir = execution_shared_dir(execution_id) / "download_source_screen"
    inputs_dir.mkdir(parents=True, exist_ok=True)

    refs = []
    for src in fetched_sources:
        ref = src.get("sourceId", src.get("id"))
        write_json(inputs_dir / f"{ref}.json", {
            "schema": "quwoquan_data.stage_envelope",
            "executionId": execution_id,
            "step": "source_screen", "ref": ref,
            "payload": src,
        })
        refs.append(ref)

    manifest_path = execution_assistant_task(execution_id, "source", "source_screen")
    write_assistant_task(manifest_path, step="source_screen", input_dir=inputs_dir, result_dir=inputs_dir, refs=refs)
    return inputs_dir
