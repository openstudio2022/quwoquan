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
    "documentBundleSha256",
    "articleMarkdownDigest",
}

POST_MANIFEST_REQUIRED_TIME_KEYS = {
    "createdAt",
    "updatedAt",
}

POST_MANIFEST_CREATOR_KEYS = {
    "authorId",
    "creatorProfileId",
    "creatorArchetype",
    "creatorProfileDigest",
    "creatorDisclosure",
    "experienceClaimMode",
    "authorQualitySignals",
}

VALID_EXPERIENCE_CLAIM_MODES = {
    "editorial_synthesis",
    "authorized_first_person",
    "public_data_analysis",
    "visual_discovery",
}

# 阶段输入/输出路径以内容对象树为真相源（规格 §15.1）：实体对象在 entities/…，
# 内容对象在 posts/{contentType}/{angle}/{title}/{seq}/，过程阶段统一编号挂对象目录下。
STAGE_EVIDENCE_CONTRACT = {
    "download": {
        "input": "entities/{domain}/{type}/{name}/1.download/{homepage,article,image}_source_plan.json",
        "output": "sources/{sourceUnitId}/source.md + assets/ and entities/{domain}/{type}/{name}/1.download/source_refs.json",
    },
    "quality_analysis": {
        "input": "entities/{domain}/{type}/{name}/1.download/source_refs.json -> sources/{sourceUnitId}/source.md",
        "output": "posts/{contentType}/{angle}/{title}/{seq}/2.quality/quality_analysis.json.payload.evidenceBundle",
    },
    "agent_draft": {
        "input": "3.compose/{entity_page_input.json|writing_pack.json}",
        "output": "4.draft/{page.md|draft.article.md|image_work.json|video_script.json}",
    },
    "review": {
        "input": "4.draft outputs + exact source/quality/compose/media identity",
        "output": "5.review/content_review.json",
    },
    "materialize": {
        "input": "approved content_review.json + AI-prepared final artifacts",
        "output": "homepage: {_entity.json,page.md,manifest.json}; article: {article.md,manifest.json}; image/video: {manifest.json}",
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
    issues = [
        f"post manifest must not contain intermediate field {key}"
        for key in sorted(POST_MANIFEST_FORBIDDEN_KEYS)
        if key in manifest
    ]
    for key in sorted(POST_MANIFEST_REQUIRED_TIME_KEYS):
        value = str(manifest.get(key) or "").strip()
        if not value:
            issues.append(f"post manifest missing required time fact {key}")
    creator_keys_present = [key for key in POST_MANIFEST_CREATOR_KEYS if key in manifest]
    system_author = str(manifest.get("authorId") or "").startswith(("agent_author_", "builtin_"))
    if creator_keys_present or system_author:
        for key in sorted(POST_MANIFEST_CREATOR_KEYS):
            if key not in manifest or manifest.get(key) in (None, "", {}):
                issues.append(f"post manifest missing required creator projection {key}")
        disclosure = manifest.get("creatorDisclosure")
        if not isinstance(disclosure, Mapping):
            issues.append("post manifest creatorDisclosure must be an object")
        else:
            if disclosure.get("type") != "platform_virtual_creator":
                issues.append("post manifest creatorDisclosure.type must be platform_virtual_creator")
            if disclosure.get("visible") is not True:
                issues.append("post manifest creatorDisclosure.visible must be true")
            if not str(disclosure.get("displayText") or "").strip():
                issues.append("post manifest creatorDisclosure.displayText is required")
        if manifest.get("experienceClaimMode") not in VALID_EXPERIENCE_CLAIM_MODES:
            issues.append("post manifest experienceClaimMode is unsupported")
    return issues
