"""Blueprint validation helpers."""
from __future__ import annotations

from typing import Any


REQUIRED_BLUEPRINT_FIELDS = [
    "templateId",
    "version",
    "subject",
    "vertical",
    "intent",
    "carrier",
    "styleFamily",
    "styleProfile",
    "audiences",
    "editorialIntent",
    "render",
    "structure",
    "wordCount",
    "imagePlan",
    "crossRefs",
    "recommendation",
]


REQUIRED_CREATOR_FIELDS = [
    "creatorProfileId",
    "subAccountId",
    "authorId",
    "isSystemBuiltin",
    "displayName",
    "userHandle",
    "headline",
    "bio",
    "creatorArchetype",
    "status",
    "verticalRefs",
    "scenarioRefs",
    "claimPolicy",
    "disclosure",
    "publishCadence",
    "qualityScore",
    "fatigueScore",
    "riskTier",
    "profileVersion",
    "publicProfileTagRefs",
    "recommendationTagRefs",
    "preferredBlueprintIds",
    "voiceStyle",
    "expertiseClaims",
    "mustNotClaim",
    "coverageScope",
    "carrierAffinity",
]


def validate_required(data: dict[str, Any], fields: list[str], label: str) -> list[str]:
    return [f"{label}: missing required field '{field}'" for field in fields if field not in data]


def blueprint_angle_leaf(blueprint: dict[str, Any]) -> str:
    """蓝图的内容角度叶子（templateId 在首个下划线后的部分）。

    与目录末段文件名一致，例如 ``景区_攻略`` -> ``攻略``、``线路_环线攻略`` -> ``环线攻略``。
    """
    template_id = str(blueprint.get("templateId") or "")
    if "_" in template_id:
        return template_id.split("_", 1)[1]
    return template_id


def canonical_blueprint_relpath(blueprint: dict[str, Any]) -> str | None:
    """由蓝图内容确定性推导出与标签系统同构的相对路径（相对 blueprints 根）。

    - entity 蓝图：``Entity/{subject.type}/{角度}.tmpl.yaml``（与 ``publish/tags/Entity/{domain}/{type}`` 同构，角度落叶子文件名）。
    - topic  蓝图：``Format/内容角度/{subject.type 末段}/{角度}.tmpl.yaml``（与 ``publish/tags/Format/内容角度`` 同构）。

    返回 None 表示该蓝图缺 subject/templateId 无法推导（由其它 required 校验兜底报错）。
    """
    subject = blueprint.get("subject")
    if not isinstance(subject, dict):
        return None
    angle = blueprint_angle_leaf(blueprint)
    if not angle:
        return None
    kind = subject.get("kind")
    if kind == "entity":
        subject_type = str(subject.get("type") or "").strip("/")
        if not subject_type:
            return None
        return f"Entity/{subject_type}/{angle}.tmpl.yaml"
    if kind == "topic":
        subject_type = str(subject.get("type") or "")
        leaf = subject_type.split("/")[-1] if subject_type else ""
        prefix = f"Format/内容角度/{leaf}" if leaf else "Format/内容角度"
        return f"{prefix}/{angle}.tmpl.yaml"
    return None


def collect_tag_refs(value: Any) -> list[str]:
    refs: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key.endswith("TagRef") and isinstance(child, str):
                refs.append(child)
            elif key.endswith("TagRefs") and isinstance(child, list):
                refs.extend(str(item) for item in child)
            else:
                refs.extend(collect_tag_refs(child))
    elif isinstance(value, list):
        for child in value:
            refs.extend(collect_tag_refs(child))
    return refs


def render_template(data: dict[str, Any]) -> str | None:
    render = data.get("render")
    if not isinstance(render, dict):
        return None
    template = render.get("articleTemplate")
    return str(template) if template is not None else None


def render_font(data: dict[str, Any]) -> str | None:
    render = data.get("render")
    if not isinstance(render, dict):
        return None
    font = render.get("fontPreset")
    return str(font) if font is not None else None
