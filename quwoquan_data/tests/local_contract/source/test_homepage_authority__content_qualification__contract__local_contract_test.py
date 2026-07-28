from __future__ import annotations

from core.baike_source_contract import HOMEPAGE_SOURCE_POLICY_REVISION, SOURCE_EXTRACTORS
from core.content_source_registry import resolve_homepage_source_role
from core.data_issue import DataIssueCode
from content.homepage.homepage_text import homepage_base_draft_readiness
from content.source.research.baidu_baike import BaiduBaikeResolution
from content.source.research.baike_com import BaikePageResolution
from content.source.research import homepage_authority
from content.source.contracts import HomepageAuthorityProvider
from governance.content_supply_policy import load_content_supply_policy


_POLICY = load_content_supply_policy("travel")
MINIMUM_BODY_CHARS = _POLICY.homepage_minimum_body_chars
MINIMUM_FACT_COUNT = _POLICY.homepage_minimum_fact_count
MINIMUM_FACT_CHARS = _POLICY.homepage_minimum_fact_chars


_FACT_RICH_HOMEPAGE_TEXT = (
    "测试实体位于测试省测试市，始建于2001年，占地10平方公里。\n"
    "该景区包括主展馆、历史街区和公共步道，是当地主要文化地标。\n"
    "测试实体开放时间为每天8:00至17:00，游客可通过官方渠道预约。\n"
    "园区核心建筑保留了完整的历史风貌，并设有服务中心和交通接驳设施。"
    "景区周边分布有公共停车场、游客集散点和步行游览线路，方便不同人群抵达。\n"
    "当地在保护修缮过程中保留了原有格局，并通过展陈说明介绍其历史背景与建设过程。\n"
    "园区按季节组织自然观察、文化讲解和公共教育活动，主要服务区域居民与到访游客。\n"
    "管理方设置了无障碍通道、休憩座椅和基础导览标识，游客可按指引完成主要游览路线。\n"
    "景区与周边公共交通站点保持接驳，入口提供游客咨询、医疗协助和失物招领服务。\n"
    "景区保护展示区域按年度开展建筑巡检、环境整治和导览设施维护，并保留面向公众的教育活动空间。\n"
    "景区主要游览区域设置明确的步行路线、服务节点和安全提示，方便家庭游客与团队按时段游览。\n"
    "景区在重要节假日安排预约分流、交通接驳和安全巡查，服务中心向游客提供路线与设施说明。\n"
    "景区周边保留历史街区、公共绿地和观景平台，形成可连续游览的文化与自然景观空间。"
)


def test_homepage_authority_qualification_requires_fetchable_factual_candidate(monkeypatch):
    candidate = homepage_authority.HomepageAuthorityCandidate(
        provider=HomepageAuthorityProvider.WIKIPEDIA,
        title="测试实体",
        url="https://zh.wikipedia.org/wiki/test",
    )
    discovery = homepage_authority.HomepageAuthorityDiscovery(
        wikipedia_title="测试实体",
        wikipedia_url=candidate.url,
        baidu_baike=None,
        toutiao_baike=None,
    )
    monkeypatch.setattr(homepage_authority, "discover_homepage_authority", lambda *_args, **_kwargs: discovery)
    fetch_options: list[bool] = []

    def fetch_payload(*_args: object, **kwargs: object) -> dict[str, str]:
        fetch_options.append(bool(kwargs["include_page_images"]))
        return {"text": _FACT_RICH_HOMEPAGE_TEXT}

    monkeypatch.setattr(homepage_authority, "fetch_source_payload", fetch_payload)
    monkeypatch.setattr(
        homepage_authority,
        "homepage_base_draft_readiness",
        lambda *_args, **_kwargs: {"ready": True},
    )

    verdict = homepage_authority.qualify_homepage_authority_content(
        "测试实体",
        minimum_body_chars=MINIMUM_BODY_CHARS,
        minimum_fact_count=MINIMUM_FACT_COUNT,
        minimum_fact_chars=MINIMUM_FACT_CHARS,
    )

    assert verdict.accepted is True
    assert verdict.qualified_source is not None
    assert verdict.qualified_source.provider is HomepageAuthorityProvider.WIKIPEDIA
    assert verdict.qualified_source.title == candidate.title
    assert verdict.qualified_source.url == candidate.url
    assert verdict.rejection_code is None
    assert fetch_options == [False]


def test_homepage_authority_candidate_emits_complete_primary_identity():
    candidate = homepage_authority.HomepageAuthorityCandidate(
        provider=HomepageAuthorityProvider.WIKIPEDIA,
        title="测试实体",
        url="https://zh.wikipedia.org/wiki/test",
    )

    metadata = candidate.source_metadata()

    assert metadata["source_id"] == "home_wikipedia"
    assert metadata["resolvedTitle"] == candidate.title
    assert metadata["researchLane"] == "homepage"
    assert metadata["extractor"] == SOURCE_EXTRACTORS["wikipedia"]
    assert metadata["policyRevision"] == HOMEPAGE_SOURCE_POLICY_REVISION
    assert resolve_homepage_source_role(
        source_kind=metadata["sourceKind"],
        url=metadata["canonicalUrl"],
        extractor=metadata["extractor"],
        policy_revision=metadata["policyRevision"],
    ) == "primary"


def test_homepage_authority_candidate_is_admitted_to_homepage_lane(monkeypatch):
    candidate = homepage_authority.HomepageAuthorityCandidate(
        provider=HomepageAuthorityProvider.WIKIPEDIA,
        title="测试实体",
        url="https://zh.wikipedia.org/wiki/test",
    )
    monkeypatch.setattr(
        "core.homepage_source_judge.source_judge_admission",
        lambda **_kwargs: {"decision": "primary", "issue": ""},
    )

    readiness = homepage_base_draft_readiness(
        candidate.source_metadata(),
        _FACT_RICH_HOMEPAGE_TEXT,
        entity_name="测试实体",
        minimum_body_chars=MINIMUM_BODY_CHARS,
        minimum_fact_count=MINIMUM_FACT_COUNT,
        minimum_fact_chars=MINIMUM_FACT_CHARS,
    )

    assert readiness["ready"] is True
    assert readiness["priority"] > 0


def test_homepage_authority_rejects_short_fact_summary(monkeypatch) -> None:
    candidate = homepage_authority.HomepageAuthorityCandidate(
        provider=HomepageAuthorityProvider.WIKIPEDIA,
        title="测试实体",
        url="https://zh.wikipedia.org/wiki/test",
    )
    monkeypatch.setattr(
        "core.homepage_source_judge.source_judge_admission",
        lambda **_kwargs: {"decision": "primary", "issue": ""},
    )

    readiness = homepage_base_draft_readiness(
        candidate.source_metadata(),
        "测试实体位于测试省。测试实体建于2001年。测试实体占地10平方公里。测试实体是知名景区。",
        entity_name="测试实体",
        minimum_body_chars=MINIMUM_BODY_CHARS,
        minimum_fact_count=MINIMUM_FACT_COUNT,
        minimum_fact_chars=MINIMUM_FACT_CHARS,
    )

    assert readiness["ready"] is False
    assert readiness["factCount"] >= MINIMUM_FACT_COUNT
    assert readiness["factChars"] < MINIMUM_FACT_CHARS


def test_homepage_authority_rejects_thin_source_even_when_fact_fragments_overlap(
    monkeypatch,
) -> None:
    candidate = homepage_authority.HomepageAuthorityCandidate(
        provider=HomepageAuthorityProvider.WIKIPEDIA,
        title="测试实体",
        url="https://zh.wikipedia.org/wiki/test",
    )
    monkeypatch.setattr(
        "core.homepage_source_judge.source_judge_admission",
        lambda **_kwargs: {"decision": "primary", "issue": ""},
    )
    thin_source = (
        "测试实体位于测试省测试市东部的山地与湖泊之间，是面向公众开放的当地旅游景区。"
        "测试实体占地约十平方公里，主园区由历史街区、观景步道和公共服务设施组成。"
        "测试实体始建于2000年，后续完成保护修缮并形成以文化展示为重点的游览空间。"
        "测试实体设有预约、交通接驳和安全提示，游客可按开放时段完成主要游览路线。"
    )

    readiness = homepage_base_draft_readiness(
        candidate.source_metadata(),
        thin_source,
        entity_name="测试实体",
        minimum_body_chars=MINIMUM_BODY_CHARS,
        minimum_fact_count=MINIMUM_FACT_COUNT,
        minimum_fact_chars=MINIMUM_FACT_CHARS,
    )

    assert readiness["bodyChars"] < MINIMUM_BODY_CHARS
    assert readiness["ready"] is False
    assert readiness["issue"] == (
        f"usable source chars {readiness['bodyChars']}<{MINIMUM_BODY_CHARS}"
    )


def test_homepage_authority_ignores_media_anchor_syntax_in_body_admission(
    monkeypatch,
) -> None:
    """Binding an inline image must not alter source text admission."""
    candidate = homepage_authority.HomepageAuthorityCandidate(
        provider=HomepageAuthorityProvider.WIKIPEDIA,
        title="测试实体",
        url="https://zh.wikipedia.org/wiki/test",
    )
    monkeypatch.setattr(
        "core.homepage_source_judge.source_judge_admission",
        lambda **_kwargs: {"decision": "primary", "issue": ""},
    )
    prose = (
        "测试实体位于测试省测试市，始建于2001年，占地10平方公里。"
        "测试实体包括主展馆、历史街区和公共步道，是当地文化地标。"
        "测试实体每天开放，游客可通过官方渠道预约并使用交通接驳。"
        "测试实体保护历史建筑和自然景观，长期开展公共教育活动。"
    )
    prose += "补" * (MINIMUM_BODY_CHARS - 1 - len(prose))
    planned = prose + "\n:::figure\n![图像资料](asset://source-inline-001)\n图像资料\n:::"
    bound = planned.replace("source-inline-001", "001_001")

    planned_readiness = homepage_base_draft_readiness(
        candidate.source_metadata(),
        planned,
        entity_name="测试实体",
        minimum_body_chars=MINIMUM_BODY_CHARS,
        minimum_fact_count=MINIMUM_FACT_COUNT,
        minimum_fact_chars=MINIMUM_FACT_CHARS,
    )
    bound_readiness = homepage_base_draft_readiness(
        candidate.source_metadata(),
        bound,
        entity_name="测试实体",
        minimum_body_chars=MINIMUM_BODY_CHARS,
        minimum_fact_count=MINIMUM_FACT_COUNT,
        minimum_fact_chars=MINIMUM_FACT_CHARS,
    )

    assert planned_readiness["bodyChars"] == MINIMUM_BODY_CHARS - 1
    assert bound_readiness["bodyChars"] == planned_readiness["bodyChars"]
    assert planned_readiness["ready"] is False
    assert bound_readiness["ready"] is False

    discovery = homepage_authority.HomepageAuthorityDiscovery(
        wikipedia_title=candidate.title,
        wikipedia_url=candidate.url,
        baidu_baike=None,
        toutiao_baike=None,
    )
    monkeypatch.setattr(
        homepage_authority,
        "discover_homepage_authority",
        lambda *_args, **_kwargs: discovery,
    )
    monkeypatch.setattr(
        homepage_authority,
        "fetch_source_payload",
        lambda *_args, **_kwargs: {"text": planned},
    )

    qualification = homepage_authority.qualify_homepage_authority_content(
        "测试实体",
        minimum_body_chars=MINIMUM_BODY_CHARS,
        minimum_fact_count=MINIMUM_FACT_COUNT,
        minimum_fact_chars=MINIMUM_FACT_CHARS,
    )

    assert qualification.accepted is False
    assert qualification.rejection_code is DataIssueCode.SOURCE_CONTENT_INCOMPLETE


def test_non_mediawiki_authority_title_is_available_to_the_shared_judge() -> None:
    candidate = homepage_authority.HomepageAuthorityCandidate(
        provider=HomepageAuthorityProvider.BAIDU_BAIKE,
        title="测试实体",
        url="https://baike.baidu.com/item/test",
    )

    readiness = homepage_base_draft_readiness(
        candidate.source_metadata(),
        _FACT_RICH_HOMEPAGE_TEXT,
        entity_name="测试实体",
        minimum_body_chars=MINIMUM_BODY_CHARS,
        minimum_fact_count=MINIMUM_FACT_COUNT,
        minimum_fact_chars=MINIMUM_FACT_CHARS,
    )

    assert readiness["ready"] is True
    assert readiness["judge"]["decision"] == "primary"


def test_homepage_authority_qualification_rejects_unusable_resolved_page(monkeypatch):
    candidate = homepage_authority.HomepageAuthorityCandidate(
        provider=HomepageAuthorityProvider.WIKIPEDIA,
        title="测试实体",
        url="https://zh.wikipedia.org/wiki/测试实体",
    )
    discovery = homepage_authority.HomepageAuthorityDiscovery(
        wikipedia_title=candidate.title,
        wikipedia_url=candidate.url,
        baidu_baike=None,
        toutiao_baike=None,
    )
    monkeypatch.setattr(homepage_authority, "discover_homepage_authority", lambda *_args, **_kwargs: discovery)
    monkeypatch.setattr(
        homepage_authority,
        "fetch_source_payload",
        lambda *_args, **_kwargs: {"text": "信息不足"},
    )
    monkeypatch.setattr(
        homepage_authority,
        "homepage_base_draft_readiness",
        lambda *_args, **_kwargs: {"ready": False},
    )

    verdict = homepage_authority.qualify_homepage_authority_content(
        "测试实体",
        minimum_body_chars=MINIMUM_BODY_CHARS,
        minimum_fact_count=MINIMUM_FACT_COUNT,
        minimum_fact_chars=MINIMUM_FACT_CHARS,
    )

    assert verdict.accepted is False
    assert verdict.qualified_source is None
    assert verdict.rejection_code is DataIssueCode.SOURCE_CONTENT_INCOMPLETE


def test_homepage_authority_qualification_does_not_freeze_nonfetchable_provider(monkeypatch):
    initial = homepage_authority.HomepageAuthorityDiscovery(
        wikipedia_title="",
        wikipedia_url="",
        baidu_baike=None,
        toutiao_baike=None,
    )
    external = homepage_authority.HomepageAuthorityDiscovery(
        wikipedia_title="",
        wikipedia_url="",
        baidu_baike=BaiduBaikeResolution(
            title="测试实体",
            url="https://baike.baidu.com/item/%E6%B5%8B%E8%AF%95%E5%AE%9E%E4%BD%93",
            matched_term="测试实体",
            match_confidence=1.0,
        ),
        toutiao_baike=None,
    )
    fetch_calls: list[object] = []

    monkeypatch.setattr(
        homepage_authority,
        "discover_homepage_authority",
        lambda *_args, **kwargs: external if kwargs["include_external"] else initial,
    )
    monkeypatch.setattr(
        homepage_authority,
        "fetch_source_payload",
        lambda *_args, **_kwargs: fetch_calls.append(object()),
    )

    verdict = homepage_authority.qualify_homepage_authority_content(
        "测试实体",
        minimum_body_chars=MINIMUM_BODY_CHARS,
        minimum_fact_count=MINIMUM_FACT_COUNT,
        minimum_fact_chars=MINIMUM_FACT_CHARS,
    )

    assert verdict.accepted is False
    assert verdict.qualified_source is None
    assert verdict.rejection_code is DataIssueCode.SOURCE_UNREADABLE
    assert fetch_calls == []


def test_homepage_authority_discovery_skips_only_disabled_external_provider(monkeypatch):
    monkeypatch.setattr(homepage_authority, "_wiki_title_for_entity", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(
        homepage_authority,
        "resolve_baidu_baike_page",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("non-fetchable provider must not be resolved")
        ),
    )
    monkeypatch.setattr(
        homepage_authority,
        "resolve_toutiao_baike_page",
        lambda *_args, **_kwargs: None,
    )

    discovery = homepage_authority.discover_homepage_authority(
        "测试实体",
        include_external=True,
    )

    assert discovery.available is False
    assert discovery.candidates == ()


def test_homepage_authority_qualification_rejects_disambiguation_page_type(monkeypatch):
    candidate = homepage_authority.HomepageAuthorityCandidate(
        provider=HomepageAuthorityProvider.WIKIPEDIA,
        title="九龍山",
        url="https://zh.wikipedia.org/wiki/%E4%B9%9D%E9%BE%8D%E5%B1%B1",
    )
    discovery = homepage_authority.HomepageAuthorityDiscovery(
        wikipedia_title=candidate.title,
        wikipedia_url=candidate.url,
        baidu_baike=None,
        toutiao_baike=None,
    )
    disambiguation_text = (
        "九龙山可以指：\n\n"
        "* 九龍山 (天津)\n"
        "* 九龍山 (嘉兴)\n"
        "* 九龍山 (香港)\n"
    )
    monkeypatch.setattr(homepage_authority, "discover_homepage_authority", lambda *_args, **_kwargs: discovery)
    monkeypatch.setattr(
        homepage_authority,
        "fetch_source_payload",
        lambda *_args, **_kwargs: {"text": disambiguation_text},
    )
    monkeypatch.setattr(
        homepage_authority,
        "homepage_base_draft_readiness",
        lambda *_args, **_kwargs: {"ready": True},
    )

    verdict = homepage_authority.qualify_homepage_authority_content(
        "平湖九龙山旅游度假区",
        minimum_body_chars=MINIMUM_BODY_CHARS,
        minimum_fact_count=MINIMUM_FACT_COUNT,
        minimum_fact_chars=MINIMUM_FACT_CHARS,
    )

    assert verdict.accepted is False
    assert verdict.qualified_source is None
    assert verdict.rejection_code is DataIssueCode.SOURCE_PAGE_TYPE_INVALID


def test_homepage_authority_qualification_rejects_flattened_bare_disambiguation_lead(monkeypatch):
    candidate = homepage_authority.HomepageAuthorityCandidate(
        provider=HomepageAuthorityProvider.WIKIPEDIA,
        title="示例楼",
        url="https://zh.wikipedia.org/wiki/example-tower",
    )
    discovery = homepage_authority.HomepageAuthorityDiscovery(
        wikipedia_title=candidate.title,
        wikipedia_url=candidate.url,
        baidu_baike=None,
        toutiao_baike=None,
    )
    monkeypatch.setattr(homepage_authority, "discover_homepage_authority", lambda *_args, **_kwargs: discovery)
    monkeypatch.setattr(
        homepage_authority,
        "fetch_source_payload",
        lambda *_args, **_kwargs: {
            "text": "示例楼可以指：\n\n示例楼甲，位于甲地。示例楼乙，位于乙地。"
        },
    )
    monkeypatch.setattr(
        homepage_authority,
        "homepage_base_draft_readiness",
        lambda *_args, **_kwargs: {"ready": True},
    )

    verdict = homepage_authority.qualify_homepage_authority_content(
        "示例楼（甲地）",
        minimum_body_chars=MINIMUM_BODY_CHARS,
        minimum_fact_count=MINIMUM_FACT_COUNT,
        minimum_fact_chars=MINIMUM_FACT_CHARS,
    )

    assert verdict.accepted is False
    assert verdict.qualified_source is None
    assert verdict.rejection_code is DataIssueCode.SOURCE_PAGE_TYPE_INVALID


def test_homepage_authority_qualification_uses_the_shared_readiness_fact_gate(monkeypatch):
    candidate = homepage_authority.HomepageAuthorityCandidate(
        provider=HomepageAuthorityProvider.WIKIPEDIA,
        title="蛇蟠岛",
        url="https://zh.wikipedia.org/wiki/%E8%9B%87%E8%9F%A0%E5%B2%9B",
    )
    discovery = homepage_authority.HomepageAuthorityDiscovery(
        wikipedia_title=candidate.title,
        wikipedia_url=candidate.url,
        baidu_baike=None,
        toutiao_baike=None,
    )
    thin_but_sentence_counted = (
        "蛇蟠岛位于三门湾。蛇蟠岛属于浙江省。"
        "蛇蟠岛曾经面积17.4平方公里。蛇蟠岛以采石洞穴闻名。"
    )
    monkeypatch.setattr(homepage_authority, "discover_homepage_authority", lambda *_args, **_kwargs: discovery)
    monkeypatch.setattr(
        homepage_authority,
        "fetch_source_payload",
        lambda *_args, **_kwargs: {"text": thin_but_sentence_counted},
    )
    monkeypatch.setattr(
        homepage_authority,
        "homepage_base_draft_readiness",
        lambda *_args, **_kwargs: {"ready": True},
    )

    verdict = homepage_authority.qualify_homepage_authority_content(
        "蛇蟠岛",
        minimum_body_chars=MINIMUM_BODY_CHARS,
        minimum_fact_count=MINIMUM_FACT_COUNT,
        minimum_fact_chars=MINIMUM_FACT_CHARS,
    )

    assert verdict.accepted is True
    assert verdict.qualified_source is not None
    assert verdict.rejection_code is None
