"""数据生产链路最小证据契约。

本模块只表达工程事实边界：每阶段保留什么输入/输出，哪些中间态禁止进入
高频报告或最终发布包。它不承载业务判断，避免形成第二套内容真相源。
"""
from __future__ import annotations

from typing import Any, Mapping


QUALITY_ALLOWED_KEYS = {
    "topicId",
    "qualityScore",
    "breakdown",
    "recommendation",
    "templateId",
    "title",
    "evidenceBundle",
    "sourceUrls",
    "sourcePaths",
}

QUALITY_FORBIDDEN_TOP_LEVEL_KEYS = {
    "storySpine",
    "sourceQuality",
    "relatedSearchPlan",
}

POST_MANIFEST_FORBIDDEN_KEYS = {
    "sourceQuality",
    "relatedSearchPlan",
    "evidenceBundle",
    "sourcePaths",
    "articleAssetManifest",
    "assetManifestSha256",
    "documentVersionSha256",
    "articleMarkdownDigest",
}

# 阶段输入/输出路径以内容对象树为真相源（规格 §15.1）：实体对象在 entities/…，
# 内容对象在 posts/{contentType}/{angle}/{title}/{seq}/，过程阶段统一编号挂对象目录下。
STAGE_EVIDENCE_CONTRACT = {
    "download": {
        "input": "entities/{domain}/{type}/{name}/1.download/source_plan.json",
        "output": "entities/{domain}/{type}/{name}/1.download/sources/{NN}.{kind}/source.md + assets/",
    },
    "quality_analysis": {
        "input": "entities/{domain}/{type}/{name}/1.download/sources/{NN}.{kind}/source.md",
        "output": "posts/{contentType}/{angle}/{title}/{seq}/2.quality/quality_analysis.json.payload.evidenceBundle",
    },
    "agent_draft": {
        "input": "posts/{contentType}/{angle}/{title}/{seq}/3.compose/{writing_pack.json,prompt.md}",
        "output": "posts/{contentType}/{angle}/{title}/{seq}/4.draft/{draft.article.md,draft_meta.json}",
    },
    "review": {
        "input": "agent draft.article.md + sourcePaths",
        "output": "posts/{contentType}/{angle}/{title}/{seq}/5.review/{review.json,review_ledger.json,provenance.json}",
    },
    "materialize": {
        "input": "approved review + agent draft.article.md",
        "output": "posts/{contentType}/{angle}/{title}/{seq}/{article.md,manifest.json,assets/,_object.json}",
    },
}


def quality_payload_contract_issues(payload: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    for key in sorted(QUALITY_FORBIDDEN_TOP_LEVEL_KEYS):
        if key in payload:
            issues.append(f"quality_analysis payload must not contain top-level {key}")
    for key in sorted(payload.keys()):
        if key not in QUALITY_ALLOWED_KEYS:
            issues.append(f"quality_analysis payload has unsupported key {key}")
    bundle = payload.get("evidenceBundle")
    if not isinstance(bundle, Mapping):
        issues.append("quality_analysis payload must contain evidenceBundle object")
    elif not isinstance(bundle.get("storySpine"), Mapping):
        issues.append("evidenceBundle.storySpine must be the single story spine source")
    return issues


def post_manifest_contract_issues(manifest: Mapping[str, Any]) -> list[str]:
    return [
        f"post manifest must not contain intermediate field {key}"
        for key in sorted(POST_MANIFEST_FORBIDDEN_KEYS)
        if key in manifest
    ]
