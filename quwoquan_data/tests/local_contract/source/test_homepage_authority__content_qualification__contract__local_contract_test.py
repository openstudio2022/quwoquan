from __future__ import annotations

from core.baike_source_contract import HOMEPAGE_SOURCE_POLICY_REVISION, SOURCE_EXTRACTORS
from core.content_source_registry import resolve_homepage_source_role
from core.data_issue import DataIssueCode
from content.homepage.homepage_text import homepage_base_draft_readiness
from content.source.research.baike_com import BaikePageResolution
from content.source.research import homepage_authority
from content.source.contracts import HomepageAuthorityProvider


_FACT_RICH_HOMEPAGE_TEXT = (
    "测试实体位于测试省测试市，始建于2001年，占地10平方公里。\n"
    "该景区包括主展馆、历史街区和公共步道，是当地主要文化地标。\n"
    "测试实体开放时间为每天8:00至17:00，游客可通过官方渠道预约。\n"
    "园区核心建筑保留了完整的历史风貌，并设有服务中心和交通接驳设施。"
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

    verdict = homepage_authority.qualify_homepage_authority_content("测试实体")

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
        "测试实体位于测试省。测试实体建于2001年。测试实体占地10平方公里。测试实体是知名景区。",
        entity_name="测试实体",
    )

    assert readiness["ready"] is True
    assert readiness["priority"] > 0


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

    verdict = homepage_authority.qualify_homepage_authority_content("测试实体")

    assert verdict.accepted is False
    assert verdict.qualified_source is None
    assert verdict.rejection_code is DataIssueCode.SOURCE_CONTENT_INCOMPLETE


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

    verdict = homepage_authority.qualify_homepage_authority_content("平湖九龙山旅游度假区")

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

    verdict = homepage_authority.qualify_homepage_authority_content("示例楼（甲地）")

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

    verdict = homepage_authority.qualify_homepage_authority_content("蛇蟠岛")

    assert verdict.accepted is True
    assert verdict.qualified_source is not None
    assert verdict.rejection_code is None
