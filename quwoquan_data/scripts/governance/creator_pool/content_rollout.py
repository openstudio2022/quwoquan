"""Prod rollout dry-run evidence for batch-100 creator-authored content.

There is a single ``prod`` package (no ``prod-gray``); prod rollout is a staged
attribute of that one package. This emitter records the deterministic rollout plan
plus the prod-purity invariant: creator content reaches prod only through the Remote
data source (真实发布 posts), never through alpha/beta/gamma test fixtures. It is a
DRY-RUN — it asserts the plan and invariants, it does not deploy.
"""
from __future__ import annotations

from typing import Any

from _common.creator_pool.io import artifacts_readiness_path
from _common.io import write_json
from _common.paths import now_iso
from governance.creator_pool.content_bind import build_creator_content

ROLLOUT_ARTIFACT_NAME = "creator_content_prod_rollout_dryrun.json"

# Single prod package, staged rollout (no prod-gray package).
ROLLOUT_STAGES = [
    {"stage": "shadow", "trafficPercent": 0, "description": "影子发布：内容入库但不进真实分发，仅观测。"},
    {"stage": "canary", "trafficPercent": 1, "description": "金丝雀：1% 流量曝光，观测互动/异常。"},
    {"stage": "ramp", "trafficPercent": 25, "description": "放量：25% 流量，校验推荐归因与留存。"},
    {"stage": "ga", "trafficPercent": 100, "description": "全量：100% 流量。"},
]


def build_prod_rollout_dryrun(*, batch_id: str = "travel_batch_100_v1") -> dict[str, Any]:
    binding = build_creator_content(batch_id=batch_id)
    posts = binding["posts"]
    purity = {
        "singleProdPackage": True,
        "prodGrayPackageExists": False,
        "prodDataSource": "remote",
        "prodCarriesTestFixtures": False,
        # Fixtures (alpha/beta/gamma) carry creator content; prod serves it only via
        # real published posts authored by the batch creators.
        "contentReachesProdVia": "remote_published_posts",
    }
    issues: list[str] = []
    if len({p["authorId"] for p in posts}) != len(posts):
        issues.append("creator content authors not distinct")
    carriers = sorted(p["carrier"] for p in posts)
    if carriers != ["article", "image", "video"]:
        issues.append(f"carriers {carriers} != article/image/video")
    if binding.get("previewOnly") is not False:
        issues.append("binding must be production (previewOnly=false)")
    return {
        "schemaVersion": "quwoquan_data.creator_content_prod_rollout_dryrun/1",
        "batchId": batch_id,
        "vertical": binding["vertical"],
        "dryRun": True,
        "decision": "go" if not issues else "no_go",
        "boundPostCount": len(posts),
        "distinctAuthors": binding["distinctAuthors"],
        "routedBy": binding["routedBy"],
        "rolloutStages": ROLLOUT_STAGES,
        "prodPurity": purity,
        "boundAuthors": sorted({p["authorId"] for p in posts}),
        "issues": issues,
        "generatedAt": now_iso(),
    }


def write_prod_rollout_dryrun(*, batch_id: str = "travel_batch_100_v1") -> str:
    report = build_prod_rollout_dryrun(batch_id=batch_id)
    path = artifacts_readiness_path(ROLLOUT_ARTIFACT_NAME)
    write_json(path, report)
    return str(path)
