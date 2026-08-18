"""Report summarization and artifacts for auto research plans."""
from __future__ import annotations

from typing import Any

from core.data_issue import DataIssue
from core.io import write_json
from core.paths import execution_root

_AUTO_DISCOVERY_REPORT = "auto_research_plan.json"

# Every list-valued, per-entity evidence field emitted by the lane writers must
# survive both per-entity future aggregation and an interrupted-run resume merge.
# Keeping the inventory here prevents video/article evidence from silently
# disappearing when a partially completed exact workload is resumed.
AUTO_RESEARCH_MERGE_ROW_KEYS = (
    "updated",
    "issues",
    "candidates",
    "articleSourceDiscovery",
    "imageCollections",
    "homepageMediaCollections",
    "homepageMediaAdvisories",
    "sourceUnavailable",
    "rescueEvents",
    "videoDiscovery",
    "videoProviderFunnels",
)

def _source_availability_summary(report: dict[str, Any], entity_ids: list[str]) -> dict[str, Any]:
    unavailable_by_entity: dict[str, list[DataIssue]] = {}
    for item in report.get("sourceUnavailable") or []:
        if not isinstance(item, dict):
            raise TypeError("sourceUnavailable rows must use DataIssue objects")
        issue = DataIssue.from_dict(item)
        entity_id = issue.ref
        if entity_id:
            unavailable_by_entity.setdefault(entity_id, []).append(issue)
    issue_by_entity: dict[str, list[tuple[str, str]]] = {}
    passed_lanes_by_entity: dict[str, set[str]] = {}
    for item in report.get("candidates") or []:
        if not isinstance(item, dict) or not bool(item.get("passed")):
            continue
        entity_id = str(item.get("entityId") or "").strip()
        lane = str(item.get("lane") or "").strip()
        if entity_id and lane:
            passed_lanes_by_entity.setdefault(entity_id, set()).add(lane)
    for item in report.get("candidates") or []:
        if not isinstance(item, dict) or bool(item.get("passed")):
            continue
        entity_id = str(item.get("entityId") or "").strip()
        if not entity_id:
            continue
        lane = str(item.get("lane") or "").strip()
        if lane and lane in passed_lanes_by_entity.get(entity_id, set()):
            # Rejected discovery candidates are diagnostics. They must not
            # mark the whole lane unavailable after another candidate already
            # passed and became eligible for the consumable source content.execution.planning.
            continue
        source_id = str(item.get("source_id") or "").strip()
        issues = [str(issue) for issue in (item.get("issues") or []) if str(issue).strip()]
        if not issues:
            issues = ["source candidate gate failed"]
        prefix = f"{entity_id}: {lane} candidate {source_id}".strip()
        issue_by_entity.setdefault(entity_id, []).extend(
            (lane or "all", f"{prefix}: {issue}") for issue in issues
        )

    scoring_policy = report.get("scoringPolicy") if isinstance(report.get("scoringPolicy"), dict) else {}
    image_saturation = int(scoring_policy.get("imageBonusSaturationCount") or 1)
    image_counts_by_entity: dict[str, int] = {}
    for item in report.get("imageCollections") or []:
        if not isinstance(item, dict) or not bool(item.get("passed")):
            continue
        entity_id = str(item.get("entityId") or "").strip()
        if not entity_id:
            continue
        image_counts_by_entity[entity_id] = image_counts_by_entity.get(entity_id, 0) + 1

    def _image_count_score(entity_id: str) -> float:
        if image_saturation <= 0:
            return 1.0
        return round(min(image_counts_by_entity.get(entity_id, 0) / image_saturation, 1.0), 4)

    ineligible: list[dict[str, Any]] = []
    scored_targets: list[dict[str, Any]] = []
    image_soft_warnings: list[dict[str, Any]] = []
    for entity_id in entity_ids:
        blockers = list(unavailable_by_entity.get(entity_id) or [])
        issue_rows = issue_by_entity.get(entity_id) or []
        lanes = {
            item.lane.value
            for item in blockers
            if item.lane.value
        }
        lanes.update(lane for lane, _message in issue_rows if lane)
        # Standalone image works are a soft scoring dimension. Homepage
        # readiness is determined by its admitted encyclopedia base draft;
        # media availability remains a separately auditable result.
        fatal_blockers = [item for item in blockers if item.lane.value != "image"]
        fatal_issues = [message for lane, message in issue_rows if lane != "image"]
        soft_blockers = [item for item in blockers if item.lane.value == "image"]
        soft_issues = [message for lane, message in issue_rows if lane == "image"]
        image_score = _image_count_score(entity_id)
        eligible = not fatal_blockers and not fatal_issues
        composite_score = round((80.0 if eligible else 0.0) + (20.0 * image_score if eligible else 0.0), 2)
        scored_row = {
            "entityId": entity_id,
            "eligible": eligible,
            "compositeScore": composite_score,
            "minimumQualityScore": 80.0 if eligible else 0.0,
            "imageBonusScore": round(20.0 * image_score if eligible else 0.0, 2),
            "imageCountScore": image_score,
            "publishableImageCollectionCount": image_counts_by_entity.get(entity_id, 0),
            "imageBonusSaturationCount": image_saturation,
        }
        scored_targets.append(scored_row)
        if soft_blockers or soft_issues:
            image_soft_warnings.append(
                {
                    "entityId": entity_id,
                    "lanes": ["image"],
                    "issues": soft_issues,
                    "blockers": [item.as_dict() for item in soft_blockers],
                    "recoveries": sorted({item.recovery.value for item in soft_blockers}),
                    "scoreImpact": {
                        "imageCountScore": image_score,
                        "imageBonusScore": scored_row["imageBonusScore"],
                    },
                }
            )
        if not eligible:
            ineligible.append(
                {
                    "entityId": entity_id,
                    "lanes": sorted(lanes),
                    "issues": fatal_issues,
                    "blockers": [item.as_dict() for item in fatal_blockers],
                    "softImageWarnings": {
                        "issues": soft_issues,
                        "blockers": [item.as_dict() for item in soft_blockers],
                    },
                    "recoveries": sorted({item.recovery.value for item in fatal_blockers}),
                }
            )
    ranked_targets = sorted(
        scored_targets,
        key=lambda row: (-float(row.get("compositeScore") or 0.0), str(row.get("entityId") or "")),
    )
    ready = [str(row["entityId"]) for row in ranked_targets if bool(row.get("eligible"))]
    return {
        "readyTargets": ready,
        "readyTargetCount": len(ready),
        "ineligibleTargets": ineligible,
        "ineligibleTargetCount": len(ineligible),
        "rankedTargets": ranked_targets,
        "imageSoftWarnings": image_soft_warnings,
        "scoringPolicy": scoring_policy,
    }

def _write_auto_report_artifacts(execution_id: str, report: dict[str, Any]) -> None:
    shared_dir = execution_root(execution_id) / "_shared"
    shared_dir.mkdir(parents=True, exist_ok=True)
    write_json(shared_dir / _AUTO_DISCOVERY_REPORT, report)

def _merge_auto_reports(base: dict[str, Any], incoming: dict[str, Any]) -> None:
    for key in AUTO_RESEARCH_MERGE_ROW_KEYS:
        rows = incoming.get(key) if isinstance(incoming.get(key), list) else []
        base.setdefault(key, []).extend(rows)
