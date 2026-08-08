"""Unified content source registry and prompt contracts."""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from core.baike_source_contract import (
    BAIDU_BAIKE_CANONICAL_RESOLUTION,
    TOUTIAO_BAIKE_CANONICAL_RESOLUTION,
    source_contract_issues,
)
from core.content_source_registry import (
    STRUCTURED_FACTS_FIELDS,
    build_content_source_guidance,
    content_source_catalog_digest,
    homepage_source_can_seed_base_draft,
    homepage_structured_facts_policy,
    load_content_source_registry,
    render_lane_source_prompt,
    resolve_homepage_source_role,
    verify_content_source_registry,
)
from core.video_source_admission import (
    assert_video_source_admitted,
)


def test_content_source_registry_is_valid_and_covers_all_lanes():
    assert verify_content_source_registry() == []
    guidance = build_content_source_guidance("travel")
    assert guidance["schema"] == "quwoquan.content_source_registry"
    assert guidance["catalogDigest"] == content_source_catalog_digest()
    assert guidance["catalogDigest"].startswith("sha256:")
    assert set(guidance["lanes"]) == {"homepage", "article", "image", "video"}
    homepage = guidance["lanes"]["homepage"]["sources"]
    image = guidance["lanes"]["image"]["sources"]
    article = guidance["lanes"]["article"]["sources"]
    assert any(row["platform"] == "维基百科" for row in homepage)
    assert {row["sourceKind"] for row in homepage} == {
        "wikipedia",
        "baidu_baike",
        "toutiao_baike",
    }
    assert not any(row["platform"] == "维基导游" for row in homepage)
    assert any(row["platform"] == "今日头条百科" and row["homepageAuthorityRole"] == "primary" for row in homepage)
    assert any(row["platform"] == "Pinterest" for row in image)
    assert any(row["platform"] == "图虫" for row in image)
    professional = {row["sourceId"]: row for row in image}
    assert professional["pinterest"]["researchAcquisitionPaths"] == [
        "supported_api",
        "manual_file",
    ]
    assert professional["tuchong"]["researchAcquisitionPaths"] == [
        "public_direct",
        "supported_api",
        "manual_file",
    ]
    assert any(row["sourceClass"] == "ugc_longform" for row in article)
    assert not any(row["sourceClass"] in {"official_site", "government_tourism"} for row in homepage)


def test_registry_rejects_pinterest_public_direct_acquisition_drift():
    data = load_content_source_registry()
    pinterest = next(
        row for row in data["common"]["image"] if row["sourceId"] == "pinterest"
    )
    pinterest["researchAcquisitionPaths"] = [
        "public_direct",
        "supported_api",
        "manual_file",
    ]

    issues = verify_content_source_registry(data)

    assert any(
        "common.image.pinterest: professional research acquisition paths must equal"
        in issue
        for issue in issues
    )


def test_homepage_role_three_encyclopedia_closed_set_resolution():
    assert resolve_homepage_source_role(
        source_kind="wikipedia",
        url="https://zh.wikipedia.org/wiki/西湖",
        extractor="wikipedia_api",
        policy_revision="encyclopedia-primary",
    ) == "primary"
    assert resolve_homepage_source_role(
        source_kind="toutiao_baike",
        url="https://www.baike.com/wiki/西湖",
        extractor="toutiao_baike_html",
        policy_revision="encyclopedia-primary",
    ) == "primary"
    assert resolve_homepage_source_role(
        source_kind="official_site",
        url="https://wlt.sc.gov.cn/x",
        extractor="static_official_html",
        policy_revision="encyclopedia-primary",
    ) == "other"
    assert resolve_homepage_source_role(
        source_kind="",
        url="https://zh.wikipedia.org/wiki/西湖",
        extractor="wikipedia_api",
        policy_revision="encyclopedia-primary",
    ) == "other", "禁止仅凭 host 猜 sourceKind"
    assert homepage_source_can_seed_base_draft({
        "sourceKind": "baidu_baike",
        "url": "https://baike.baidu.com/item/西湖",
        "extractor": "baidu_baike_html",
        "policyRevision": "encyclopedia-primary",
    })


def test_baike_sources_expose_canonical_resolution_policies():
    assert source_contract_issues({
        "wikipedia_api",
        "baidu_baike_html",
        "toutiao_baike_html",
    }) == []
    assert TOUTIAO_BAIKE_CANONICAL_RESOLUTION.base_url == "https://www.baike.com/wiki/"
    assert TOUTIAO_BAIKE_CANONICAL_RESOLUTION.candidate_limit > 0
    assert BAIDU_BAIKE_CANONICAL_RESOLUTION.base_url == "https://baike.baidu.com/search/word?word="
    assert BAIDU_BAIKE_CANONICAL_RESOLUTION.candidate_limit > 0


def test_structured_facts_admit_official_sources_without_widening_the_narrative_set():
    policy = homepage_structured_facts_policy()
    assert policy["revision"] == "audited-official-structured-facts"
    assert tuple(policy["fields"]) == STRUCTURED_FACTS_FIELDS
    assert set(policy["allowedSourceClasses"]) == {
        "encyclopedia",
        "official_site",
        "government_tourism",
    }
    assert policy["requiresFactSourceProvenance"] is True
    assert policy["narrativeBodyRemainsEncyclopediaOnly"] is True

    # 放开只作用于结构化事实：官网/政务文旅仍不得成为主页正文来源。
    assert resolve_homepage_source_role(
        source_kind="government_tourism",
        url="https://wlt.sc.gov.cn/x",
        extractor="static_official_html",
        policy_revision="encyclopedia-primary",
    ) == "other"
    assert not homepage_source_can_seed_base_draft({
        "sourceKind": "official_site",
        "url": "https://www.hzwestlake.com/",
        "extractor": "static_official_html",
        "policyRevision": "encyclopedia-primary",
    })

    entity_rows = load_content_source_registry()["common"]["entity"]
    evidence = {
        row["sourceId"]: row
        for row in entity_rows
        if row.get("structuredFactsRole") == "audited_evidence"
    }
    assert set(evidence) == {"official_site", "government_tourism"}
    for source_id, row in evidence.items():
        assert row.get("lanes") in (None, []), f"{source_id} 不得进入任何内容 lane"
        assert row["defaultRole"] == "reference_only"


def test_registry_rejects_structured_facts_evidence_that_joins_a_content_lane():
    data = load_content_source_registry()
    for row in data["common"]["entity"]:
        if row.get("sourceId") == "official_site":
            row["lanes"] = ["homepage"]
    issues = verify_content_source_registry(data)
    assert any("must not join a content lane" in issue for issue in issues)


def test_registry_rejects_dropping_the_narrative_guard():
    data = load_content_source_registry()
    policy = data["lanePolicies"]["homepage"]["structuredFactsPolicy"]
    policy["narrativeBodyRemainsEncyclopediaOnly"] = False
    policy["allowedSourceClasses"] = ["encyclopedia", "official_site", "government_tourism", "ota"]
    issues = verify_content_source_registry(data)
    assert any("narrativeBodyRemainsEncyclopediaOnly" in issue for issue in issues)
    assert any("allowedSourceClasses" in issue for issue in issues)


def test_reference_only_video_sources_have_no_acquisition_or_release_admission():
    data = load_content_source_registry()
    matrix = {
        row["sourceId"]: row
        for row in data["lanePolicies"]["video"]["commercialAdmissionMatrix"]
    }
    video_sources = {
        row["sourceId"]: row
        for row in data["common"]["video"]
    }
    for source_id in ("youtube", "vimeo", "bilibili"):
        source = video_sources[source_id]
        assert source["defaultRole"] == "reference_only"
        assert source["fetchMode"] == "platform_reference"
        assert source.get("researchAcquisitionPaths") in (None, [])
        assert matrix[source_id]["publicationAdmissions"] == []
        try:
            assert_video_source_admitted(
                data,
                source_id=source_id,
                source_kind="tourism_video_site",
                publication_admission="research_release",
            )
        except ValueError as exc:
            assert "GATE_BLOCK DATA.CONTRACT.INVALID" in str(exc)
        else:
            raise AssertionError(f"{source_id} reference-only admission was accepted")


def test_registry_typed_gate_blocks_reference_only_video_configuration_conflicts():
    data = load_content_source_registry()
    matrix = data["lanePolicies"]["video"]["commercialAdmissionMatrix"]
    next(row for row in matrix if row["sourceId"] == "bilibili")[
        "publicationAdmissions"
    ] = ["research_release", "commercial_release"]
    bilibili = next(
        row for row in data["common"]["video"] if row["sourceId"] == "bilibili"
    )
    bilibili["researchAcquisitionPaths"] = ["public_direct"]

    issues = verify_content_source_registry(data)

    assert (
        "GATE_BLOCK DATA.CONTRACT.INVALID: video source bilibili is "
        "reference_only/platform_reference but declares research acquisition paths"
    ) in issues
    assert (
        "GATE_BLOCK DATA.CONTRACT.INVALID: video matrix bilibili is "
        "reference_only/platform_reference but declares release admissions"
    ) in issues


def test_lane_prompt_is_rendered_from_registry_policy():
    article_prompt = render_lane_source_prompt(
        "article",
        vertical="travel",
        per_target_articles=3,
        article_intents=["planning_consultation", "decision_experience", "route_transport"],
    )
    image_prompt = render_lane_source_prompt(
        "image",
        vertical="travel",
        per_target_image_works=2,
        image_asset_strategy="attribution_audited_publish",
    )
    homepage_prompt = render_lane_source_prompt("homepage", vertical="travel")
    assert "不得因 UGC/垂类专业/平台文章类别天然升降级" in article_prompt
    assert "去哪儿攻略" in article_prompt and "马蜂窝" in article_prompt
    assert "Pinterest" in image_prompt and "图虫" in image_prompt
    assert "imageAssetStrategy=attribution_audited_publish" in image_prompt
    assert "公开直链、平台支持 API 或人工文件" in image_prompt
    assert "rightsStatus" in image_prompt
    assert "最多保留 5 个核心来源" in homepage_prompt
    assert "维基导游" in homepage_prompt and "不得进入主页" in homepage_prompt
    assert "今日头条百科" in homepage_prompt


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"content source registry tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
