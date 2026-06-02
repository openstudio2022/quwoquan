"""data download — multi-platform source acquisition."""
from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
import sys

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_ROOT))

from _common.io import write_json  # noqa: E402
from _common.paths import ensure_batch_layout, batch_command_root  # noqa: E402
from _common.content_evidence import anonymize_source_markdown, score_source_markdown  # noqa: E402
from _common.source_catalog import coverage_issues, source_category_coverage, vertical_from_task_id  # noqa: E402
from _common.stage_reports import write_gate_report, write_stage_result  # noqa: E402
from download.source_inputs import curated_sources_for_entity, curated_images_for_entity, source_frontmatter  # noqa: E402
from download.fetch import fetch_source, fetch_image  # noqa: E402
from download.prepare import prepare_source_plan, prepare_source_screen  # noqa: E402


def handle_download(args: argparse.Namespace) -> None:
    """Orchestrate download: source_plan → fetch → source_screen.

    Steps:
    1. source_plan: Agent plans multi-platform download strategy per entity
    2. fetch: Script executes HTTP fetches + text extraction
    3. source_screen: Agent screens quality/relevance/copyright

    Output: batches/{batch_id}/download/sources/{entity_id}/{source_id}/source.md
    """
    task_id = args.task
    batch_id = args.batch
    entity_ids = args.entity_ids.split(",") if args.entity_ids else []

    ensure_batch_layout(task_id, batch_id, "download")
    dl_root = batch_command_root(task_id, batch_id, "download")

    print(f"[download] Task: {task_id}, Batch: {batch_id}")
    print(f"[download] Target entities: {entity_ids}")
    print(f"[download] Work dir: {dl_root}")
    print(f"[download] Steps: source_plan → fetch → source_screen")

    entity_type = getattr(args, "entity_type", "") or ""
    vertical = vertical_from_task_id(task_id)
    entities = [{"entityId": entity_id, "canonicalName": entity_id, "entityType": entity_type} for entity_id in entity_ids]
    prepare_source_plan(task_id, batch_id, entities)
    for entity in entities:
        planned_sources = [
            {
                "platform": source["platform"],
                "url": source["url"],
                "expectedContentType": "article",
                "priority": index + 1,
            }
            for index, source in enumerate(curated_sources_for_entity(task_id, batch_id, entity["entityId"]))
        ]
        write_stage_result(
            task_id,
            batch_id,
            "download",
            "source_plan",
            entity["entityId"],
            {
                "entityId": entity["entityId"],
                "sources": planned_sources,
            },
        )
        # 源类别覆盖门（「全」硬约束）：≥2 源 + 覆盖 ≥N 类（含核心类），杜绝同质单一来源。
        coverage = source_category_coverage(planned_sources, vertical=vertical)
        plan_issues: list[str] = []
        if len(planned_sources) < 2:
            plan_issues.append("sourcePlan: fewer than 2 planned sources")
        plan_issues.extend(coverage_issues(planned_sources, vertical=vertical, entity_id=entity["entityId"]))
        write_gate_report(
            task_id=task_id,
            batch_id=batch_id,
            command="download",
            step="source_plan",
            ref=entity["entityId"],
            passed=not plan_issues,
            issues=plan_issues,
            evidence_summary={
                "plannedSourceCount": len(planned_sources),
                "coveredCategories": coverage["coveredCategories"],
                "coveredCount": coverage["coveredCount"],
                "minCategories": coverage["minCategories"],
                "missingCore": coverage["missingCore"],
                "unknownPlatforms": coverage["unknownPlatforms"],
            },
            next_step="fetch",
            fallback_stage="source_plan" if plan_issues else None,
        )

    fetched_sources: list[dict] = []
    quality_by_entity: dict[str, list[dict]] = defaultdict(list)
    for entity_id in entity_ids:
        entity_dir = dl_root / "sources" / entity_id
        entity_dir.mkdir(parents=True, exist_ok=True)
        for source in curated_sources_for_entity(task_id, batch_id, entity_id):
            src_dir = entity_dir / source["source_id"]
            src_dir.mkdir(parents=True, exist_ok=True)
            try:
                meta = fetch_source(source["url"], src_dir)
                source_md = Path(meta["sourceMdPath"]).read_text(encoding="utf-8")
            except Exception as exc:
                source_md = source_frontmatter(source, entity_id)
                (src_dir / "source.md").write_text(source_md, encoding="utf-8")
                meta = {"url": source["url"], "statusCode": 0, "error": str(exc), "sourceMdPath": str(src_dir / "source.md")}
            else:
                (src_dir / "source.md").write_text(source_md, encoding="utf-8")
            clean_md = anonymize_source_markdown(source_md)
            (src_dir / "source.clean.md").write_text(clean_md, encoding="utf-8")
            assessment = score_source_markdown(source["source_id"], source_md, entity_name=entity_id)
            write_json(
                src_dir / "source.quality.json",
                {
                    "sourceId": source["source_id"],
                    "entity": entity_id,
                    "quality": assessment.quality,
                    "score": assessment.score,
                    "reasons": list(assessment.reasons),
                    "excerpt": assessment.excerpt,
                    "url": source["url"],
                    "statusCode": meta.get("statusCode", 0),
                },
            )
            quality_by_entity[entity_id].append(
                {
                    "sourceId": source["source_id"],
                    "quality": assessment.quality,
                    "score": assessment.score,
                    "url": source["url"],
                    "statusCode": meta.get("statusCode", 0),
                }
            )
            fetched_sources.append(
                {
                    "sourceId": source["source_id"],
                    "url": source["url"],
                    "quality": assessment.quality,
                    "score": assessment.score,
                    "entityId": entity_id,
                }
            )

        image_specs = curated_images_for_entity(task_id, batch_id, entity_id)
        image_manifest: list[dict] = []
        if image_specs:
            images_dir = entity_dir / "images"
            for idx, spec in enumerate(image_specs, start=1):
                meta = fetch_image(spec["url"], images_dir, index=idx)
                if meta is None:
                    continue
                meta["license"] = spec.get("license", "")
                meta["credit"] = spec.get("credit", "")
                image_manifest.append(meta)
            if image_manifest:
                write_json(
                    images_dir / "index.json",
                    {"entity": entity_id, "imageCount": len(image_manifest), "images": image_manifest},
                )
        write_gate_report(
            task_id=task_id,
            batch_id=batch_id,
            command="download",
            step="image_fetch",
            ref=entity_id,
            passed=len(image_manifest) >= 1,
            issues=[]
            if image_manifest
            else ["imageFetch: 未下到真实图片，请在 source_plan 提供可用 imageUrls(CC/PD/授权)"],
            evidence_summary={"plannedImages": len(image_specs), "downloadedImages": len(image_manifest)},
            next_step="quality_analysis",
            fallback_stage="source_plan" if not image_manifest else None,
        )

    prepare_source_screen(task_id, batch_id, fetched_sources)
    for source in fetched_sources:
        issues: list[str] = []
        if source["quality"] == "Reject":
            issues.append("sourceScreen: source scored Reject")
        write_stage_result(
            task_id,
            batch_id,
            "download",
            "source_screen",
            source["sourceId"],
            {
                "sourceId": source["sourceId"],
                "decision": "retain" if source["quality"] != "Reject" else "reject",
                "qualityScore": source["score"],
                "relevanceScore": source["score"],
                "copyrightStatus": "internal_reference",
                "reason": "quality gate auto-screen",
                "entityId": source["entityId"],
            },
        )
        write_gate_report(
            task_id=task_id,
            batch_id=batch_id,
            command="download",
            step="source_screen",
            ref=source["sourceId"],
            passed=not issues,
            issues=issues,
            evidence_summary={
                "entityId": source["entityId"],
                "quality": source["quality"],
                "score": source["score"],
            },
            next_step="quality_analysis",
            fallback_stage="fetch" if issues else None,
        )
    for entity_id, rows in quality_by_entity.items():
        retained = [row for row in rows if row["quality"] != "Reject"]
        issues: list[str] = []
        if len(retained) < 1:
            issues.append("sourceScreen: no retained source for entity")
        write_gate_report(
            task_id=task_id,
            batch_id=batch_id,
            command="download",
            step="entity_source_bundle",
            ref=entity_id,
            passed=not issues,
            issues=issues,
            evidence_summary={
                "sourceCount": len(rows),
                "retainedCount": len(retained),
                "qualities": [row["quality"] for row in rows],
            },
            next_step="quality_analysis",
            fallback_stage="source_plan" if issues else None,
        )
    print(f"[download] Planned {len(entities)} entity/entities and fetched {len(fetched_sources)} source bundle(s)")


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("download", help="Multi-platform source acquisition")
    p.add_argument("--task", required=True, help="Task ID")
    p.add_argument("--batch", required=True, help="Batch ID")
    p.add_argument("--entity-ids", required=True, help="Comma-separated entity IDs")
    p.add_argument("--entity-type", default="", help="实体类型(可选，仅记录到 source_plan)")
    p.set_defaults(handler=handle_download)
