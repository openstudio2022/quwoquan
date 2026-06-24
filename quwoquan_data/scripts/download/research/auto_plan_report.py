"""Report summarization and artifacts for auto research plans."""
from __future__ import annotations

import re
from typing import Any

from _common.io import write_json
from _common.paths import batch_root

_AUTO_DISCOVERY_REPORT = "auto_research_plan.json"

def _source_availability_summary(report: dict[str, Any], entity_ids: list[str]) -> dict[str, Any]:
    unavailable_by_entity: dict[str, list[dict[str, Any]]] = {}
    for item in report.get("sourceUnavailable") or []:
        if not isinstance(item, dict):
            continue
        entity_id = str(item.get("entityId") or "").strip()
        if entity_id:
            unavailable_by_entity.setdefault(entity_id, []).append(item)
    issue_by_entity: dict[str, list[str]] = {}
    for issue in report.get("issues") or []:
        text = str(issue or "")
        entity = text.split(":", 1)[0].strip() if ":" in text else ""
        if entity:
            issue_by_entity.setdefault(entity, []).append(text)
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
            # passed and became eligible for the consumable source plan.
            continue
        source_id = str(item.get("source_id") or "").strip()
        issues = [str(issue) for issue in (item.get("issues") or []) if str(issue).strip()]
        if not issues:
            issues = ["source candidate gate failed"]
        prefix = f"{entity_id}: {lane} candidate {source_id}".strip()
        issue_by_entity.setdefault(entity_id, []).extend(f"{prefix}: {issue}" for issue in issues)

    def _lane_for_issue(issue: str) -> str:
        lower = issue.lower()
        if "article" in lower or "travelogue" in lower or "guidebook" in lower:
            return "article"
        if "image" in lower or "open-license images" in lower or "rights-compatible" in lower:
            return "image"
        if "homepage" in lower:
            return "homepage"
        if "source discovery infrastructure" in lower:
            return "all"
        return ""

    def _normalized_issue(issue: str) -> str:
        text = issue.split(":", 1)[1].strip() if ":" in issue else issue
        text = re.sub(r"=\d+", "=N", text)
        text = re.sub(r"\d+", "N", text)
        return text

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
        issues = issue_by_entity.get(entity_id) or []
        lanes = {
            str(item.get("lane") or "")
            for item in blockers
            if item.get("lane")
        }
        lanes.update(lane for lane in (_lane_for_issue(issue) for issue in issues) if lane)
        fatal_blockers = [item for item in blockers if str(item.get("lane") or "") != "image"]
        fatal_issues = [issue for issue in issues if _lane_for_issue(issue) != "image"]
        soft_blockers = [item for item in blockers if str(item.get("lane") or "") == "image"]
        soft_issues = [issue for issue in issues if _lane_for_issue(issue) == "image"]
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
                    "issueReasons": sorted({_normalized_issue(issue) for issue in soft_issues}),
                    "blockers": soft_blockers,
                    "nextActions": sorted({str(item.get("nextAction") or "") for item in soft_blockers if item.get("nextAction")}),
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
                    "issueReasons": sorted({_normalized_issue(issue) for issue in fatal_issues}),
                    "blockers": fatal_blockers,
                    "softImageWarnings": {
                        "issues": soft_issues,
                        "blockers": soft_blockers,
                    },
                    "nextActions": sorted({str(item.get("nextAction") or "") for item in fatal_blockers if item.get("nextAction")}),
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

def _write_auto_report_artifacts(task_id: str, batch_id: str, report: dict[str, Any]) -> None:
    shared_dir = batch_root(task_id, batch_id) / "_shared"
    shared_dir.mkdir(parents=True, exist_ok=True)
    write_json(shared_dir / _AUTO_DISCOVERY_REPORT, report)
    availability = report.get("sourceAvailability") if isinstance(report.get("sourceAvailability"), dict) else {}
    write_json(shared_dir / "source_unavailable_targets.json", availability)

def _merge_auto_reports(base: dict[str, Any], incoming: dict[str, Any]) -> None:
    for key in ("updated", "issues", "candidates", "imageCollections", "sourceUnavailable", "rescueEvents"):
        rows = incoming.get(key) if isinstance(incoming.get(key), list) else []
        base.setdefault(key, []).extend(rows)
