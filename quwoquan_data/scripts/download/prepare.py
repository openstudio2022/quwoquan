"""Prepare inputs for download command steps."""
from __future__ import annotations

from pathlib import Path

from _common.paths import (
    STAGE_DOWNLOAD,
    batch_assistant_task,
    batch_assistant_tasks_dir,
    batch_root,
    batch_shared_dir,
)
from _common.io import write_json, write_assistant_task
from _common.source_catalog import source_plan_guidance, vertical_from_task_id
from _common.source_unit import resolve_entity_object_dir
from vertical.source_registry import build_travel_source_guidance

RESEARCH_PLAN_FILES = {
    "homepage": "homepage_source_plan.json",
    "article": "article_source_plan.json",
    "image": "image_source_plan.json",
}


def _lane_payload(
    lane: str,
    *,
    ref: str,
    ent: dict,
    guidance: dict,
    registry_guidance: dict,
) -> dict:
    common = {
        "entityId": ref,
        "canonicalName": ent.get("canonicalName", ""),
        "entityType": ent.get("entityType", ""),
        "researchLane": lane,
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
            "sourceCategoryGuidance": guidance,
            "sourceRegistryGuidance": registry_guidance,
            "sourceImagePolicy": source_image_policy,
            "primaryEvidenceRef": "",
            "sources": [],
        }
    if lane == "article":
        return {
            **common,
            "sourceCategoryGuidance": guidance,
            "sourceRegistryGuidance": registry_guidance,
            "sourceImagePolicy": source_image_policy,
            "sources": [],
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
            ],
            "discoveryOnlyPlatforms": ["Pinterest", "小红书"],
            "aiImagesAllowed": False,
        },
        "collections": [],
    }


def prepare_source_plan(task_id: str, batch_id: str, entities: list[dict]) -> Path:
    """Prepare three independent research plans for every entity.

    Legacy ``source_plan.json`` is still readable, but new managed batches use
    homepage/article/image plans so one research agent cannot silently supply
    evidence for another modality.
    """
    guidance = source_plan_guidance(vertical_from_task_id(task_id))
    vertical = vertical_from_task_id(task_id)
    registry_guidance = build_travel_source_guidance() if vertical == "travel" else {}
    refs_by_lane: dict[str, list[str]] = {lane: [] for lane in RESEARCH_PLAN_FILES}
    for ent in entities:
        ref = ent.get("entityId", ent.get("id"))
        etype = ent.get("entityType", "")
        obj = resolve_entity_object_dir(task_id, batch_id, ref, etype_hint=etype)
        for lane, filename in RESEARCH_PLAN_FILES.items():
            plan_path = obj / STAGE_DOWNLOAD / filename
            if not plan_path.is_file():
                plan_path.parent.mkdir(parents=True, exist_ok=True)
                write_json(
                    plan_path,
                    {
                        "schemaVersion": "quwoquan_data.stage_envelope",
                        "taskId": task_id,
                        "batchId": batch_id,
                        "step": f"{lane}_research",
                        "ref": ref,
                        "payload": _lane_payload(
                            lane,
                            ref=ref,
                            ent=ent,
                            guidance=guidance,
                            registry_guidance=registry_guidance,
                        ),
                    },
                )
            refs_by_lane[lane].append(ref)

    for lane, refs in refs_by_lane.items():
        manifest_path = (
            batch_assistant_tasks_dir(task_id, batch_id)
            / f"download_{lane}_research.json"
        )
        write_assistant_task(
            manifest_path,
            step=f"{lane}_research",
            input_dir=batch_root(task_id, batch_id) / "entities",
            result_dir=batch_root(task_id, batch_id) / "entities",
            refs=refs,
        )
    return batch_root(task_id, batch_id) / "entities"


def prepare_source_screen(task_id: str, batch_id: str, fetched_sources: list[dict]) -> Path:
    """Prepare source_screen inputs from fetched source summaries."""
    inputs_dir = batch_shared_dir(task_id, batch_id) / "download_source_screen"
    inputs_dir.mkdir(parents=True, exist_ok=True)

    refs = []
    for src in fetched_sources:
        ref = src.get("sourceId", src.get("id"))
        write_json(inputs_dir / f"{ref}.json", {
            "schemaVersion": "quwoquan_data.stage_envelope",
            "taskId": task_id, "batchId": batch_id,
            "step": "source_screen", "ref": ref,
            "payload": src,
        })
        refs.append(ref)

    manifest_path = batch_assistant_task(task_id, batch_id, "download", "source_screen")
    write_assistant_task(manifest_path, step="source_screen", input_dir=inputs_dir, result_dir=inputs_dir, refs=refs)
    return inputs_dir
