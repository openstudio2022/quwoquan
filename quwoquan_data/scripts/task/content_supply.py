"""Platform-level content supply planning.

This module keeps the cold-start / continuous-supply contract deterministic
and cheap to dry-run.  Large author pools are represented by stable shards and
samples; executors can later expand a shard without changing IDs.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

from _common.io import read_json, write_json
from _common.paths import DATA_ROOT, RUNTIME_ROOT


TASK_SCHEMA = "quwoquan.content_supply.task"
PREP_SCHEMA = "quwoquan.content_supply.prep_report"
DELTA_SCHEMA = "quwoquan.content_supply.delta_plan"
AUTHOR_POOL_MULTIPLIER = 3
DEFAULT_AUTHOR_SHARD_SIZE = 1000
DEFAULT_CONTENT_SHARD_SIZE = 1000
DEFAULT_SAMPLE_LIMIT = 100

VALID_VERTICALS = ("travel", "campus", "photography", "tech", "car")
VALID_SCENARIOS = (
    "cold_start",
    "long_tail_fill",
    "hotspot_tracking",
    "optimize_existing",
    "refresh_stale",
    "reported_revision",
)
# 可生产 content_type 单一真相源：moment(随记/casual) 不属于"作品"，禁止进入生产。
# 与 schema/produce/post_manifest.schema.json 的 contentType enum(article/image/video) 对齐：
# imagePost→image、videoPost→video、knowledgeCard→article、homepage→实体主页独立流程。
VALID_CONTENT_TYPES = ("homepage", "article", "imagePost", "videoPost", "knowledgeCard")
VALID_RUN_MODES = ("new", "fill_missing", "optimize_existing", "refresh_stale", "repair_failed")
VALID_CREATOR_STATUSES = ("draft", "ai_reviewed", "active", "throttled", "suspended", "retired")
VALID_RISK_TIERS = ("low", "medium", "high")
VALID_EXPERIENCE_CLAIM_MODES = (
    "editorial_synthesis",
    "authorized_first_person",
    "public_data_analysis",
    "visual_discovery",
)
QUEUE_BACKEND_LOCAL = "local_file"
QUEUE_BACKEND_RELIABLETASK = "reliabletask"

DEFAULT_CONTENT_MIX = {
    "article": 0.50,
    "imagePost": 0.30,
    "videoPost": 0.20,
}

SCENARIO_RUN_MODE = {
    "cold_start": "new",
    "long_tail_fill": "fill_missing",
    "hotspot_tracking": "new",
    "optimize_existing": "optimize_existing",
    "refresh_stale": "refresh_stale",
    "reported_revision": "repair_failed",
}

SCENARIO_SOP_REFS = {
    scenario: f"sop/scenarios/{scenario}.md"
    for scenario in VALID_SCENARIOS
}

CONTENT_SPEC_REFS = {
    "homepage": "sop/主页",
    "article": "sop/article.md",
    "imagePost": "sop/image.md",
    "videoPost": "sop/video.md",
    "knowledgeCard": "sop/article.md",
}

VERTICAL_LABELS = {
    "travel": "旅行",
    "campus": "校园",
    "photography": "摄影",
    "tech": "科技",
    "car": "汽车",
}

DEFAULT_ARCHETYPES = {
    "travel": ["travel_blogger", "pro_guide", "self_drive_expert", "landscape_photographer", "geo_editor"],
    "campus": ["campus_blogger", "student_mentor", "career_mentor"],
    "photography": ["landscape_photographer", "geo_editor"],
    "tech": ["tech_practitioner", "knowledge_editor", "tool_reviewer", "trend_observer"],
    "car": ["auto_editor", "brand_analyst", "owner_guide", "tech_explainer"],
}

DEFAULT_TOKEN_BUDGET = {
    "sopSummaryMaxTokens": 500,
    "creatorProfileSummaryMaxTokens": 300,
    "evidenceSummaryMaxTokens": {
        "homepage": 1200,
        "article": 1800,
        "imagePost": 700,
        "videoPost": 1200,
        "knowledgeCard": 900,
    },
    "draftMaxTokens": {
        "homepage": 2500,
        "article": 3200,
        "imagePost": 600,
        "videoPost": 1800,
        "knowledgeCard": 1200,
    },
    "reviewMaxTokens": 900,
    "overflowAction": "summarize_or_reject",
}

CREATOR_REQUIRED_FIELDS = [
    "creatorProfileId",
    "authorId",
    "subAccountId",
    "status",
    "verticalRefs",
    "scenarioRefs",
    "creatorArchetype",
    "voiceStyle",
    "claimPolicy",
    "disclosure",
    "publishCadence",
    "qualityScore",
    "fatigueScore",
    "riskTier",
    "profileVersion",
]


def now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _stable_int(*parts: object) -> int:
    raw = "|".join(str(p) for p in parts).encode("utf-8")
    return int(hashlib.sha256(raw).hexdigest()[:16], 16)


def _stable_id(prefix: str, *parts: object, length: int = 16) -> str:
    raw = "|".join(str(p) for p in parts).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(raw).hexdigest()[:length]}"


def _slug(value: str) -> str:
    out = re.sub(r"[^0-9A-Za-z_]+", "_", value.strip())
    out = re.sub(r"_+", "_", out).strip("_").lower()
    return out or "x"


def _split_csv(value: str | None) -> list[str]:
    return [x.strip() for x in (value or "").split(",") if x.strip()]


def _relative_exists(ref: str) -> bool:
    return (DATA_ROOT / ref).exists()


def content_supply_root(supply_task_id: str) -> Path:
    return RUNTIME_ROOT / "_shared" / "content_supply" / supply_task_id


def task_spec_path(supply_task_id: str) -> Path:
    return content_supply_root(supply_task_id) / "content_supply_task.json"


def prep_report_path(supply_task_id: str) -> Path:
    return content_supply_root(supply_task_id) / "prep_report.json"


def delta_plan_path(supply_task_id: str) -> Path:
    return content_supply_root(supply_task_id) / "delta_plan.json"


def parse_content_mix(raw: str | None) -> dict[str, float]:
    """Parse article=0.5,imagePost=0.3 style mix and normalize it."""
    if not raw:
        return dict(DEFAULT_CONTENT_MIX)
    mix: dict[str, float] = {}
    for item in _split_csv(raw):
        if "=" not in item:
            raise ValueError(f"content mix item must be key=value: {item}")
        key, value = item.split("=", 1)
        key = key.strip()
        if key not in VALID_CONTENT_TYPES:
            raise ValueError(f"unsupported content type in mix: {key}")
        number = float(value.strip())
        if number < 0:
            raise ValueError(f"content mix cannot be negative: {item}")
        if number > 1:
            number = number / 100.0
        mix[key] = number
    total = sum(mix.values())
    if total <= 0:
        raise ValueError("content mix sum must be positive")
    return {k: v / total for k, v in mix.items() if v > 0}


def allocate_counts(total: int, mix: dict[str, float]) -> dict[str, int]:
    if total < 0:
        raise ValueError("total must be >= 0")
    raw = {k: total * v for k, v in mix.items()}
    counts = {k: int(math.floor(v)) for k, v in raw.items()}
    remaining = total - sum(counts.values())
    # Deterministic largest-remainder allocation.
    order = sorted(raw, key=lambda k: (raw[k] - math.floor(raw[k]), k), reverse=True)
    for key in order[:remaining]:
        counts[key] += 1
    return {k: counts[k] for k in sorted(counts)}


def parse_subject_refs(raw: str | None) -> list[str]:
    refs = _split_csv(raw)
    return refs or ["subject:auto"]


def build_content_supply_task(
    *,
    goal: str,
    vertical: str,
    scenarios: list[str],
    daily_content_target: int,
    content_mix: dict[str, float],
    subject_kind: str,
    subject_type: str,
    subject_refs: list[str],
    supply_task_id: str | None = None,
    plan_date: str | None = None,
    author_pool_multiplier: int = AUTHOR_POOL_MULTIPLIER,
    creator_archetypes: list[str] | None = None,
    queue_backend: str | None = None,
) -> dict[str, Any]:
    if vertical not in VALID_VERTICALS:
        raise ValueError(f"unsupported vertical: {vertical}")
    if daily_content_target <= 0:
        raise ValueError("dailyContentTarget must be positive")
    bad_scenarios = [s for s in scenarios if s not in VALID_SCENARIOS]
    if bad_scenarios:
        raise ValueError(f"unsupported scenarios: {bad_scenarios}")
    bad_types = [k for k in content_mix if k not in VALID_CONTENT_TYPES]
    if bad_types:
        raise ValueError(f"unsupported content types: {bad_types}")
    if author_pool_multiplier < 1:
        raise ValueError("authorPoolMultiplier must be >= 1")
    if queue_backend and queue_backend not in (QUEUE_BACKEND_LOCAL, QUEUE_BACKEND_RELIABLETASK):
        raise ValueError(f"unsupported queue backend: {queue_backend}")

    normalized_scenarios = scenarios or ["cold_start"]
    normalized_subject_refs = subject_refs or ["subject:auto"]
    supply_id = supply_task_id or _stable_id("supply", vertical, goal, ",".join(normalized_scenarios), daily_content_target)
    archetypes = creator_archetypes or DEFAULT_ARCHETYPES.get(vertical, ["general_creator"])
    plan_date = plan_date or _dt.date.today().isoformat()
    resolved_queue_backend = (
        queue_backend
        or (QUEUE_BACKEND_LOCAL if int(daily_content_target) <= 1000 else QUEUE_BACKEND_RELIABLETASK)
    )

    return {
        "schemaVersion": TASK_SCHEMA,
        "supplyTaskId": supply_id,
        "goal": goal,
        "vertical": vertical,
        "verticalLabel": VERTICAL_LABELS.get(vertical, vertical),
        "scenarios": normalized_scenarios,
        "dailyContentTarget": int(daily_content_target),
        "authorPool": {
            "domain": "CreatorProfile/SystemAuthor",
            "multiplier": int(author_pool_multiplier),
            "size": int(daily_content_target) * int(author_pool_multiplier),
            "activation": "daily_quota",
            "dailyActiveAuthorTarget": int(daily_content_target),
            "publishIntervalDays": {"min": 1, "max": 5, "mean": 3},
            "defaultStatus": "active",
            "lifecycle": list(VALID_CREATOR_STATUSES),
            "identityPolicy": {
                "transparentSystemCreator": True,
                "forbidFakeRealExperience": True,
                "forbidUnprovenOfficialOrProfessionalClaims": True,
                "doNotMaterializeEachAuthorAsTagOrEntity": True,
            },
            "claimPolicy": {
                "defaultExperienceClaimMode": "editorial_synthesis",
                "allowedExperienceClaimModes": list(VALID_EXPERIENCE_CLAIM_MODES),
                "firstPersonRequiresHumanOrLicensedEvidence": True,
                "forbidOfficialOrProfessionalClaimWithoutEvidence": True,
            },
            "disclosure": {
                "required": True,
                "type": "platform_virtual_creator",
                "displayText": "平台虚拟创作者，内容由资料整理与 AI 辅助生成，经平台审核发布。",
                "mustBeUserVisible": True,
            },
            "creatorArchetypes": archetypes,
        },
        "contentMix": content_mix,
        "contentTargets": allocate_counts(int(daily_content_target), content_mix),
        "subject": {
            "kind": subject_kind,
            "type": subject_type,
            "refs": normalized_subject_refs,
        },
        "sopRefs": {
            "verticalSopRef": f"verticals/{vertical}/coverage/registry.yaml",
            "scenarioSopRefs": {scenario: SCENARIO_SOP_REFS[scenario] for scenario in normalized_scenarios},
            "contentSpecRefs": {ctype: CONTENT_SPEC_REFS[ctype] for ctype in content_mix},
        },
        "runModes": sorted({SCENARIO_RUN_MODE[s] for s in normalized_scenarios}),
        "planningContract": {
            "requiredBindings": ["verticalSopRef", "scenarioSopRef", "creatorProfileId", "contentSpecRef"],
            "layers": ["vertical", "scenario", "creator", "content"],
            "dedupBeforeGeneration": True,
            "aiReviewDefault": True,
            "humanReviewMode": "spot_check_or_high_risk",
            "forbidBareTopicGeneration": True,
            "creatorRequiredFields": CREATOR_REQUIRED_FIELDS,
            "activeRefsProjection": "semanticMentions.published_only",
        },
        "creatorGovernance": {
            "domain": "CreatorProfile/SystemAuthor",
            "stateMachine": {
                "draft": ["ai_reviewed", "retired"],
                "ai_reviewed": ["active", "suspended"],
                "active": ["throttled", "suspended", "retired"],
                "throttled": ["active", "suspended", "retired"],
                "suspended": ["active", "retired"],
                "retired": [],
            },
            "humanReview": "spot_check_high_risk_or_publish_boundary_change",
            "tagEntityPolicy": {
                "authorClassificationTagsOnly": True,
                "doNotCreateTagPerAuthor": True,
                "doNotCreateEntityPerVirtualAuthor": True,
            },
        },
        "queuePolicy": {
            "localFileQueueMaxDailyTarget": 1000,
            "backend": resolved_queue_backend,
            "productionBackends": [QUEUE_BACKEND_RELIABLETASK],
            "defaultProductionBackend": QUEUE_BACKEND_RELIABLETASK,
            "reliableTask": {
                "taskType": "data.content_object.execute",
                "queue": "reliabletask.data.content_supply",
                "store": "MongoStore",
                "readyIndex": "RedisReadyIndex",
            },
            "leaseSeconds": 900,
            "heartbeatSeconds": 60,
            "deadLetterAfterAttempts": 3,
            "partitioning": ["vertical", "scenario", "authorShard", "contentShard"],
        },
        "tokenBudget": DEFAULT_TOKEN_BUDGET,
        "releasePolicy": {
            "mode": "isolated_release_first",
            "publishRequiresReleaseVerify": True,
            "importRequiresProjectionVerify": True,
            "allowPendingReviewMentions": True,
            "activeRefsProjection": "semanticMentions.published_only",
        },
        "planDate": plan_date,
        "createdAt": now_iso(),
    }


def load_content_supply_task(supply_task_id: str | None = None, spec_path: str | None = None) -> dict[str, Any]:
    path = Path(spec_path) if spec_path else task_spec_path(str(supply_task_id))
    if not path.is_file():
        raise FileNotFoundError(path)
    return read_json(path)


def save_content_supply_task(spec: dict[str, Any]) -> Path:
    path = task_spec_path(str(spec["supplyTaskId"]))
    write_json(path, spec)
    return path


def build_prep_report(spec: dict[str, Any], *, allow_missing_sop: bool = False) -> dict[str, Any]:
    sop_refs = spec.get("sopRefs") or {}
    refs: list[str] = []
    vertical_ref = sop_refs.get("verticalSopRef")
    if vertical_ref:
        refs.append(str(vertical_ref))
    refs.extend(str(x) for x in (sop_refs.get("scenarioSopRefs") or {}).values())
    refs.extend(str(x) for x in (sop_refs.get("contentSpecRefs") or {}).values())

    subject_type = str((spec.get("subject") or {}).get("type") or "")
    if "homepage" in (spec.get("contentTargets") or {}) and subject_type:
        bits = [x for x in subject_type.split("/") if x]
        if len(bits) >= 2:
            refs.append(f"sop/主页/{bits[-2]}/{bits[-1]}/guide.md")

    missing = sorted({ref for ref in refs if not _relative_exists(ref)})
    blocking = [] if allow_missing_sop else [f"missing SOP or registry: {ref}" for ref in missing]
    pool = spec.get("authorPool") or {}
    daily_target = int(spec.get("dailyContentTarget") or 0)
    pool_size = int(pool.get("size") or 0)
    if pool_size != daily_target * int(pool.get("multiplier") or AUTHOR_POOL_MULTIPLIER):
        blocking.append("authorPool.size must equal dailyContentTarget * multiplier")
    if int(pool.get("dailyActiveAuthorTarget") or 0) != daily_target:
        blocking.append("authorPool.dailyActiveAuthorTarget must equal dailyContentTarget")
    if (pool.get("identityPolicy") or {}).get("doNotMaterializeEachAuthorAsTagOrEntity") is not True:
        blocking.append("authorPool.identityPolicy.doNotMaterializeEachAuthorAsTagOrEntity must be true")
    if (pool.get("disclosure") or {}).get("required") is not True:
        blocking.append("authorPool.disclosure.required must be true")
    if (spec.get("planningContract") or {}).get("forbidBareTopicGeneration") is not True:
        blocking.append("planningContract.forbidBareTopicGeneration must be true")
    queue_policy = spec.get("queuePolicy") or {}
    if queue_policy.get("backend") not in (QUEUE_BACKEND_LOCAL, QUEUE_BACKEND_RELIABLETASK):
        blocking.append("queuePolicy.backend must be local_file or reliabletask")
    if daily_target > int(queue_policy.get("localFileQueueMaxDailyTarget") or 1000):
        if queue_policy.get("backend") != QUEUE_BACKEND_RELIABLETASK:
            blocking.append("queuePolicy.backend must be reliabletask for daily targets above localFileQueueMaxDailyTarget")
    if spec.get("schemaVersion") != TASK_SCHEMA:
        blocking.append(f"schemaVersion must be {TASK_SCHEMA}; old content supply tasks are read-only production memory")
    release_policy = spec.get("releasePolicy") or {}
    if release_policy.get("publishRequiresReleaseVerify") is not True:
        blocking.append("releasePolicy.publishRequiresReleaseVerify must be true")
    if release_policy.get("importRequiresProjectionVerify") is not True:
        blocking.append("releasePolicy.importRequiresProjectionVerify must be true")
    token_budget = spec.get("tokenBudget") or {}
    if int(token_budget.get("sopSummaryMaxTokens") or 0) > 500:
        blocking.append("tokenBudget.sopSummaryMaxTokens must be <= 500")
    if int(token_budget.get("creatorProfileSummaryMaxTokens") or 0) > 300:
        blocking.append("tokenBudget.creatorProfileSummaryMaxTokens must be <= 300")

    return {
        "schemaVersion": PREP_SCHEMA,
        "supplyTaskId": spec.get("supplyTaskId"),
        "passed": not blocking,
        "blockingIssues": blocking,
        "warnings": [f"optional SOP missing: {ref}" for ref in missing] if allow_missing_sop else [],
        "resolved": {
            "dailyContentTarget": daily_target,
            "authorPoolSize": pool_size,
            "contentTargets": spec.get("contentTargets") or {},
            "sopRefsChecked": sorted(set(refs)),
            "creatorArchetypes": pool.get("creatorArchetypes") or [],
            "queueBackend": queue_policy.get("backend"),
            "tokenBudget": token_budget,
        },
        "nextAction": "task plan" if not blocking else "task prep: create or register missing SOP/source prerequisites",
        "createdAt": now_iso(),
    }


def save_prep_report(report: dict[str, Any]) -> Path:
    path = prep_report_path(str(report["supplyTaskId"]))
    write_json(path, report)
    return path


def _author_id(spec: dict[str, Any], index: int) -> str:
    vertical = str(spec.get("vertical") or "x")
    scenario = str((spec.get("scenarios") or ["cold_start"])[index % len(spec.get("scenarios") or ["cold_start"])])
    return f"agent_creator_{_slug(vertical)}_{_slug(scenario)}_{index:09d}"


def _author_profile(spec: dict[str, Any], index: int) -> dict[str, Any]:
    pool = spec.get("authorPool") or {}
    batch_id = str(pool.get("creatorBatchId") or "").strip()
    if batch_id:
        from _common.creator_pool.registry_bridge import author_pool_profile_from_batch

        bridged = author_pool_profile_from_batch(batch_id, index)
        if bridged:
            return bridged
    archetypes = pool.get("creatorArchetypes") or ["general_creator"]
    archetype = str(archetypes[index % len(archetypes)])
    interval = 1 + (_stable_int(spec.get("supplyTaskId"), "interval", index) % 5)
    creator_id = _author_id(spec, index)
    scenario = str((spec.get("scenarios") or ["cold_start"])[index % len(spec.get("scenarios") or ["cold_start"])])
    quality_score = 0.72 + ((_stable_int(spec.get("supplyTaskId"), "quality", index) % 21) / 100.0)
    fatigue_score = round((6 - interval) / 10.0, 2)
    return {
        "creatorProfileId": creator_id,
        "subAccountId": creator_id.replace("agent_creator_", "agent_sub_account_", 1),
        "authorId": creator_id.replace("agent_creator_", "agent_author_", 1),
        "status": "active",
        "verticalRefs": [str(spec.get("vertical") or "")],
        "scenarioRefs": [scenario],
        "creatorArchetype": archetype,
        "displayName": f"{VERTICAL_LABELS.get(str(spec.get('vertical') or ''), '垂类')}创作者{index + 1:06d}",
        "userHandle": creator_id.replace("agent_creator_", "creator_", 1),
        "isVirtualSystemCreator": True,
        "isSystemBuiltin": False,
        "voiceStyle": {
            "pointOfView": "editorial_synthesis",
            "tone": "清楚、具体、保留资料边界",
            "forbidFakeFirstPersonExperience": True,
        },
        "claimPolicy": {
            "experienceClaimMode": "editorial_synthesis",
            "mayUseFirstPerson": False,
            "mustCiteEvidenceForClaims": True,
            "forbiddenClaims": ["真实亲历", "官方身份", "专业资质", "商业合作"],
        },
        "disclosure": {
            "type": "platform_virtual_creator",
            "displayText": str((pool.get("disclosure") or {}).get("displayText") or "平台虚拟创作者"),
            "visible": True,
        },
        "publishCadence": {
            "intervalDays": interval,
            "randomizedRangeDays": [1, 5],
            "maxDailyPosts": 1,
        },
        "publishIntervalDays": interval,
        "qualityScore": round(quality_score, 2),
        "fatigueScore": fatigue_score,
        "riskTier": "low" if quality_score >= 0.80 else "medium",
        "profileVersion": "1.0.0",
        "identityDisclosure": "platform_virtual_creator",
    }


def _shards(total: int, size: int, prefix: str) -> list[dict[str, int | str]]:
    out: list[dict[str, int | str]] = []
    if total <= 0:
        return out
    count = math.ceil(total / size)
    for idx in range(count):
        start = idx * size
        end = min(total, start + size)
        out.append({"shardId": f"{prefix}_{idx:05d}", "start": start, "endExclusive": end, "count": end - start})
    return out


def _semantic_fingerprint(spec: dict[str, Any], content_type: str, subject_ref: str, ordinal: int) -> str:
    return _stable_id("sem", spec.get("supplyTaskId"), spec.get("vertical"), content_type, subject_ref, ordinal, length=20)


def _object_key(spec: dict[str, Any], content_type: str, subject_ref: str, ordinal: int) -> str:
    return _stable_id("content", spec.get("supplyTaskId"), content_type, subject_ref, ordinal, length=20)


def load_memory(path: str | None) -> dict[str, set[str]]:
    if not path:
        return {"existingObjectKeys": set(), "contentFingerprints": set(), "usedBaseSourceRefs": set()}
    data = read_json(path)
    return {
        "existingObjectKeys": set(str(x) for x in data.get("existingObjectKeys", [])),
        "contentFingerprints": set(str(x) for x in data.get("contentFingerprints", [])),
        "usedBaseSourceRefs": set(str(x) for x in data.get("usedBaseSourceRefs", [])),
    }


def _feedback_actions(feedback_path: str | None) -> list[dict[str, Any]]:
    if not feedback_path:
        return []
    data = read_json(feedback_path)
    actions: list[dict[str, Any]] = []
    for idx, event in enumerate(data.get("events") or []):
        if not isinstance(event, dict):
            continue
        event_type = str(event.get("type") or "")
        target_id = str(event.get("targetId") or "")
        if event_type == "report" and target_id:
            actions.append({
                "actionId": _stable_id("revision", target_id, event.get("reason"), idx),
                "targetId": target_id,
                "action": "freeze_and_repair",
                "runMode": "repair_failed",
                "reason": event.get("reason") or "reported",
                "aiReviewRequired": True,
                "humanReviewMode": "spot_check_or_high_risk",
            })
        elif event_type == "metric" and target_id:
            impressions = float(event.get("impressions") or 0)
            ctr = float(event.get("ctr") or 0)
            report_rate = float(event.get("reportRate") or 0)
            if impressions >= 500 and ctr < 0.005:
                actions.append({
                    "actionId": _stable_id("optimize", target_id, "low_ctr", idx),
                    "targetId": target_id,
                    "action": "optimize_existing",
                    "runMode": "optimize_existing",
                    "reason": "low_ctr",
                    "aiReviewRequired": True,
                })
            if impressions >= 100 and report_rate >= 0.01:
                actions.append({
                    "actionId": _stable_id("revision", target_id, "high_report_rate", idx),
                    "targetId": target_id,
                    "action": "freeze_and_repair",
                    "runMode": "repair_failed",
                    "reason": "high_report_rate",
                    "aiReviewRequired": True,
                    "humanReviewMode": "spot_check_or_high_risk",
                })
    return actions


def build_delta_plan(
    spec: dict[str, Any],
    *,
    memory: dict[str, set[str]] | None = None,
    feedback_path: str | None = None,
    sample_limit: int = DEFAULT_SAMPLE_LIMIT,
    author_shard_size: int = DEFAULT_AUTHOR_SHARD_SIZE,
    content_shard_size: int = DEFAULT_CONTENT_SHARD_SIZE,
) -> dict[str, Any]:
    memory = memory or load_memory(None)
    target = int(spec.get("dailyContentTarget") or 0)
    pool_size = int((spec.get("authorPool") or {}).get("size") or target * AUTHOR_POOL_MULTIPLIER)
    sample_limit = max(0, int(sample_limit))
    author_sample_count = min(sample_limit, pool_size)
    object_sample_count = min(sample_limit, target)

    interval_distribution = {str(i): 0 for i in range(1, 6)}
    for idx in range(pool_size):
        interval = 1 + (_stable_int(spec.get("supplyTaskId"), "interval", idx) % 5)
        interval_distribution[str(interval)] += 1

    sample_authors = [_author_profile(spec, idx) for idx in range(author_sample_count)]
    content_counts = spec.get("contentTargets") or allocate_counts(target, spec.get("contentMix") or DEFAULT_CONTENT_MIX)
    subjects = list((spec.get("subject") or {}).get("refs") or ["subject:auto"])
    scenarios = list(spec.get("scenarios") or ["cold_start"])
    vertical_sop_ref = str(((spec.get("sopRefs") or {}).get("verticalSopRef")) or "")
    scenario_sop_refs = (spec.get("sopRefs") or {}).get("scenarioSopRefs") or {}
    content_spec_refs = (spec.get("sopRefs") or {}).get("contentSpecRefs") or {}

    sample_objects: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    generated_count = 0
    skipped_count = 0
    global_ordinal = 0
    remaining_by_type = {k: int(v) for k, v in content_counts.items()}
    ordinal_by_type = {k: 0 for k in content_counts}
    content_type_order = sorted(content_counts)
    while any(v > 0 for v in remaining_by_type.values()):
        for content_type in content_type_order:
            if remaining_by_type.get(content_type, 0) <= 0:
                continue
            type_ordinal = ordinal_by_type[content_type]
            ordinal_by_type[content_type] += 1
            remaining_by_type[content_type] -= 1

            subject_ref = str(subjects[global_ordinal % len(subjects)])
            scenario = str(scenarios[global_ordinal % len(scenarios)])
            object_key = _object_key(spec, content_type, subject_ref, type_ordinal)
            fingerprint = _semantic_fingerprint(spec, content_type, subject_ref, type_ordinal)
            creator_index = global_ordinal % max(1, pool_size)
            duplicate_reason = ""
            if object_key in memory["existingObjectKeys"]:
                duplicate_reason = "existing_object_key"
            elif fingerprint in memory["contentFingerprints"]:
                duplicate_reason = "semantic_fingerprint"
            if duplicate_reason:
                skipped_count += 1
                if len(skipped) < sample_limit:
                    skipped.append({
                        "objectKey": object_key,
                        "contentType": content_type,
                        "subjectRef": subject_ref,
                        "reason": duplicate_reason,
                        "semanticFingerprint": fingerprint,
                    })
                global_ordinal += 1
                continue
            generated_count += 1
            if len(sample_objects) < object_sample_count:
                creator = _author_profile(spec, creator_index)
                run_mode = SCENARIO_RUN_MODE.get(scenario, "new")
                token_budget = spec.get("tokenBudget") or DEFAULT_TOKEN_BUDGET
                evidence_budget = (token_budget.get("evidenceSummaryMaxTokens") or {}).get(content_type)
                draft_budget = (token_budget.get("draftMaxTokens") or {}).get(content_type)
                sample_objects.append({
                    "objectKey": object_key,
                    "contentType": content_type,
                    "subjectRef": subject_ref,
                    "scenario": scenario,
                    "runMode": run_mode,
                    "creatorProfileId": creator["creatorProfileId"],
                    "authorId": creator["authorId"],
                    "creatorArchetype": creator["creatorArchetype"],
                    "creatorProfileVersion": creator["profileVersion"],
                    "creatorDisclosure": creator["disclosure"],
                    "experienceClaimMode": creator["claimPolicy"]["experienceClaimMode"],
                    "authorQualitySignals": {
                        "qualityScore": creator["qualityScore"],
                        "fatigueScore": creator["fatigueScore"],
                        "riskTier": creator["riskTier"],
                    },
                    "verticalSopRef": vertical_sop_ref,
                    "scenarioSopRef": scenario_sop_refs.get(scenario),
                    "contentSpecRef": content_spec_refs.get(content_type) or CONTENT_SPEC_REFS.get(content_type),
                    "semanticFingerprint": fingerprint,
                    "tokenBudget": {
                        "sopSummaryMaxTokens": token_budget.get("sopSummaryMaxTokens"),
                        "creatorProfileSummaryMaxTokens": token_budget.get("creatorProfileSummaryMaxTokens"),
                        "evidenceSummaryMaxTokens": evidence_budget,
                        "draftMaxTokens": draft_budget,
                        "reviewMaxTokens": token_budget.get("reviewMaxTokens"),
                    },
                    "qualityGateSet": ["facts", "rights", "safety", "dedup", "creator_boundary", "consumer_value"],
                })
            global_ordinal += 1

    return {
        "schemaVersion": DELTA_SCHEMA,
        "supplyTaskId": spec.get("supplyTaskId"),
        "planDate": spec.get("planDate"),
        "summary": {
            "dailyContentTarget": target,
            "authorPoolSize": pool_size,
            "dailyActiveAuthorTarget": target,
            "generatedCount": generated_count,
            "skippedDuplicateCount": skipped_count,
            "feedbackActionCount": len(_feedback_actions(feedback_path)),
            "contentTargets": content_counts,
            "sampledAuthors": len(sample_authors),
            "sampledObjects": len(sample_objects),
        },
        "authorPool": {
            "materialization": "lazy_sharded",
            "shardSize": author_shard_size,
            "shards": _shards(pool_size, author_shard_size, "authors"),
            "publishIntervalDistribution": interval_distribution,
            "sample": sample_authors,
        },
        "contentObjects": {
            "materialization": "lazy_sharded",
            "shardSize": content_shard_size,
            "shards": _shards(target, content_shard_size, "content"),
            "sample": sample_objects,
            "skippedDuplicateSample": skipped,
            "creatorAssignmentPolicy": {
                "samplePolicy": "preview_only_round_robin",
                "previewOnly": True,
                "note": (
                    "delta_plan.sample 的 creator 为 round-robin 体量/排期预览，"
                    "不是发布绑定真相源；真实内容生产必须经 match_creator / "
                    "resolve_registry_creator_assignment 按 carrier/region/vertical/"
                    "preferredBlueprintIds 择优绑定，并经 creator_assignment_issues 语义门校验。"
                ),
                "productionResolver": "resolve_registry_creator_assignment",
            },
        },
        "dedupPolicy": {
            "beforeGeneration": True,
            "keys": ["objectKey", "semanticFingerprint", "baseSourceRef", "sourceCollectionId", "assetSha256", "assetPHash"],
            "sameAuthorSimilarTopic": "block_until_next_interval",
        },
        "qualityPolicy": {
            "aiReviewDefault": True,
            "humanReview": "spot_check_or_high_risk",
            "requiredBindings": ["verticalSopRef", "scenarioSopRef", "creatorProfileId", "contentSpecRef"],
            "creatorBoundary": {
                "forbidFakeRealExperience": True,
                "forbidUnprovenOfficialOrProfessionalClaims": True,
                "requireVisibleDisclosure": True,
            },
            "consumerValue": {
                "minInformationDensity": 0.72,
                "minTitleFulfillment": 0.80,
                "maxTemplateFeel": 0.35,
            },
        },
        "queuePolicy": spec.get("queuePolicy") or {},
        "tokenBudget": spec.get("tokenBudget") or DEFAULT_TOKEN_BUDGET,
        "feedbackActions": _feedback_actions(feedback_path),
        "createdAt": now_iso(),
    }


def save_delta_plan(plan: dict[str, Any]) -> Path:
    path = delta_plan_path(str(plan["supplyTaskId"]))
    write_json(path, plan)
    return path


def _emit(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def handle_clarify(args: argparse.Namespace) -> None:
    try:
        mix = parse_content_mix(args.content_mix)
        spec = build_content_supply_task(
            goal=args.goal,
            vertical=args.vertical,
            scenarios=_split_csv(args.scenarios) or ["cold_start"],
            daily_content_target=args.daily_target,
            content_mix=mix,
            subject_kind=args.subject_kind,
            subject_type=args.subject_type,
            subject_refs=parse_subject_refs(args.subjects),
            supply_task_id=args.supply_task,
            plan_date=args.plan_date,
            creator_archetypes=_split_csv(args.creator_archetypes) or None,
            queue_backend=args.queue_backend,
        )
    except ValueError as exc:
        print(f"[task clarify] ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
    path = save_content_supply_task(spec) if args.write else None
    payload = {"spec": spec, "path": str(path) if path else None}
    _emit(payload)


def handle_prep(args: argparse.Namespace) -> None:
    spec = load_content_supply_task(args.supply_task, args.spec)
    report = build_prep_report(spec, allow_missing_sop=args.allow_missing_sop)
    path = save_prep_report(report) if args.write else None
    payload = {"report": report, "path": str(path) if path else None}
    _emit(payload)
    if not report["passed"] and not args.allow_fail:
        raise SystemExit(1)


def handle_plan(args: argparse.Namespace) -> None:
    spec = load_content_supply_task(args.supply_task, args.spec)
    memory = load_memory(args.memory)
    plan = build_delta_plan(
        spec,
        memory=memory,
        feedback_path=args.feedback,
        sample_limit=args.sample_limit,
        author_shard_size=args.author_shard_size,
        content_shard_size=args.content_shard_size,
    )
    path = save_delta_plan(plan) if args.write else None
    payload = {"plan": plan, "path": str(path) if path else None}
    _emit(payload)


def register_content_supply_parsers(sub: argparse._SubParsersAction) -> None:
    pc = sub.add_parser("clarify", help="平台级内容供给任务澄清：垂类×场景×作者×载体")
    pc.add_argument("--supply-task", dest="supply_task", help="supplyTaskId；不填则稳定派生")
    pc.add_argument("--goal", required=True)
    pc.add_argument("--vertical", required=True, choices=VALID_VERTICALS)
    pc.add_argument("--scenarios", default="cold_start", help=f"逗号分隔：{','.join(VALID_SCENARIOS)}")
    pc.add_argument("--daily-target", dest="daily_target", type=int, required=True)
    pc.add_argument("--content-mix", dest="content_mix", help="article=0.5,imagePost=0.3,videoPost=0.2")
    pc.add_argument("--subject-kind", dest="subject_kind", default="Entity")
    pc.add_argument("--subject-type", dest="subject_type", default="")
    pc.add_argument("--subjects", help="subject refs 逗号分隔；不填则为 subject:auto")
    pc.add_argument("--creator-archetypes", dest="creator_archetypes", help="覆盖默认作者 archetype，逗号分隔")
    pc.add_argument("--queue-backend", dest="queue_backend", choices=[QUEUE_BACKEND_LOCAL, QUEUE_BACKEND_RELIABLETASK])
    pc.add_argument("--plan-date", dest="plan_date")
    pc.add_argument("--write", action="store_true", help="写入 runtime/_shared/content_supply/<id>/content_supply_task.json")
    pc.set_defaults(handler=handle_clarify)

    pp = sub.add_parser("prep", help="内容供给前置检查：SOP/作者池/配额/基础契约")
    pp.add_argument("--supply-task", dest="supply_task")
    pp.add_argument("--spec", help="content_supply_task.json 路径")
    pp.add_argument("--allow-missing-sop", dest="allow_missing_sop", action="store_true")
    pp.add_argument("--allow-fail", dest="allow_fail", action="store_true", help="报告失败但返回 0")
    pp.add_argument("--write", action="store_true")
    pp.set_defaults(handler=handle_prep)

    ppl = sub.add_parser("plan", help="生成分层 delta_plan：作者排期、内容对象、去重、反馈修订")
    ppl.add_argument("--supply-task", dest="supply_task")
    ppl.add_argument("--spec", help="content_supply_task.json 路径")
    ppl.add_argument("--memory", help="生产记忆 JSON：existingObjectKeys/contentFingerprints/usedBaseSourceRefs")
    ppl.add_argument("--feedback", help="反馈 JSON：events[]，支持 report/metric")
    ppl.add_argument("--sample-limit", dest="sample_limit", type=int, default=DEFAULT_SAMPLE_LIMIT)
    ppl.add_argument("--author-shard-size", dest="author_shard_size", type=int, default=DEFAULT_AUTHOR_SHARD_SIZE)
    ppl.add_argument("--content-shard-size", dest="content_shard_size", type=int, default=DEFAULT_CONTENT_SHARD_SIZE)
    ppl.add_argument("--write", action="store_true")
    ppl.set_defaults(handler=handle_plan)
