"""article 车道来源单元的注册表身份与 attribution。

article 车道只接受注册表登记的站点：`sourceKind`/`extractor`/`policyRevision`
与商用准入由注册表解析，非百科站点的 attribution 由计划期铸出。测试若自己拼这
几个字段，fixture 就会与「可交付来源单元」的真实判定分叉——写盘期 fail-closed
拦的正是这条链路，而 fixture 里手填的身份永远拦不住。

因此这里不复制任何身份推导，一律从注册表派生。有两种用法：

- `article_registry_write_kwargs`：来源 URL 本身就是注册表承认的真实页面，走生产
  用的同一个绑定函数，连 URL 准入一起被校验。
- `ARTICLE_SOURCE_UNIT_IDENTITY` 加 `article_source_registry_binding`：来源 URL
  只是脚手架（测试要断言的是容量、目录布局这类与站点无关的行为），此时身份与
  profile 摘要仍取自一条真实注册表记录，只有 URL 是测试自造的。摘要真实的好处是
  注册表一改，摘要跟着变，fixture 不会停在一个早就不存在的站点画像上。
"""

from __future__ import annotations

from typing import Any

from content.source.research.article_frontier_contract import (
    public_article_source_attribution,
)
from content.source.research.article_frontier_profile import (
    article_profile_digest,
    article_search_sites,
)
from content.source.research.article_source_unit_catalog import (
    ARTICLE_SOURCE_POLICY_REVISION,
)
from content.source.research.auto_plan_article import registry_bound_article_source

#: 注册表当前承认的 article 站点的 URL 形态。取值必须落在站点 domains 内，
#: 否则 `registry_bound_article_source` 会判它不被 article 车道接纳。
QUNAR_TRAVELOGUE_URL = "https://travel.qunar.com/youji/{slug}"
CTRIP_SIGHT_URL = "https://you.ctrip.com/sight/{slug}/{sight_id}.html"
WIKIVOYAGE_URL = "https://zh.wikivoyage.org/wiki/{slug}"
WIKIPEDIA_URL = "https://zh.wikipedia.org/wiki/{slug}"

#: URL 只作脚手架时借用的注册表记录。取游记站而非百科站，是因为百科站的
#: attribution 由写盘期的解析器兜住，反而测不到「必须自带铸造 attribution」这条。
DEFAULT_ARTICLE_SITE_ID = "qunar_guide"

#: fixture 的采集时刻固定，避免 attribution 里出现每次运行都不同的字节。
FIXTURE_CAPTURED_AT = "2026-08-05T00:00:00Z"


def _registry_site(site_id: str) -> dict[str, Any]:
    for site in article_search_sites(site_ids=frozenset({site_id})):
        if str(site.get("siteId") or "") == site_id:
            return dict(site)
    raise AssertionError(
        f"article source registry no longer admits this site for crawling: {site_id}"
    )


def _site_crawl_profile(site: dict[str, Any]) -> dict[str, Any]:
    profile = site.get("siteCrawlProfile")
    return dict(profile) if isinstance(profile, dict) else {}


def _identity_from_site(site_id: str) -> dict[str, Any]:
    site = _registry_site(site_id)
    profile = _site_crawl_profile(site)
    return {
        "source_kind": str(site.get("category") or ""),
        "extractor": str(profile.get("extractor") or site.get("extractor") or ""),
        "policy_revision": ARTICLE_SOURCE_POLICY_REVISION,
        # article 车道对两者都强制 factual_reference_only：来源单元 schema 的
        # article 分支把它们声明为同一个 const，这里不另立第二口径。
        "source_use_mode": "factual_reference_only",
        "rights_mode": "factual_reference_only",
    }


#: 直接 `**` 展开给 `write_source_unit`，给出 article 车道的身份与权利口径。
ARTICLE_SOURCE_UNIT_IDENTITY = _identity_from_site(DEFAULT_ARTICLE_SITE_ID)


def article_source_registry_binding(
    *,
    platform: str,
    url: str,
    site_id: str = DEFAULT_ARTICLE_SITE_ID,
    captured_at: str = FIXTURE_CAPTURED_AT,
    **extra: Any,
) -> dict[str, Any]:
    """注册表准入三件套加铸好的 attribution，传给 `write_source_unit(source=...)`。

    与 `article_registry_write_kwargs` 的差别只在 URL 准入：这里的 URL 不必落在
    站点 domains 内，供那些与站点无关的行为断言使用。
    """
    site = _registry_site(site_id)
    profile = _site_crawl_profile(site)
    binding: dict[str, Any] = {
        "url": url,
        "platform": platform,
        "articleSiteId": site_id,
        "sourceDiscoveryProfileDigest": article_profile_digest(site),
        "articleCommercialAdmission": str(
            profile.get("articleCommercialAdmission") or ""
        ),
        "sourceAttribution": public_article_source_attribution(
            platform=platform,
            canonical_url=url,
            terms_url=str(profile.get("termsUrl") or site.get("termsUrl") or ""),
            captured_at=captured_at,
        ),
    }
    binding.update(extra)
    return binding


def article_registry_source(
    *,
    url: str,
    platform: str = "",
    **extra: Any,
) -> dict[str, Any]:
    """返回一条已绑定注册表身份与 attribution 的 article 来源 payload。

    传给 `write_source_unit(source=...)` 即可让来源单元带齐 article 车道的
    可交付身份。URL 不被注册表接纳时直接失败，而不是退回一份能写盘但交付期
    才炸的残缺身份。
    """
    payload: dict[str, Any] = {"url": url}
    if platform:
        payload["platform"] = platform
    payload.update(extra)
    bound = registry_bound_article_source(payload)
    if bound is None:
        raise AssertionError(
            "article source registry does not admit this URL for the article "
            f"lane: {url}"
        )
    return bound


def article_registry_write_kwargs(
    *,
    url: str,
    platform: str = "",
    source_role: str = "base",
    publish_media_mode: str = "text_only",
    **extra: Any,
) -> dict[str, Any]:
    """写一条合规 article 来源单元所需的全部 `write_source_unit` 关键字。

    身份与权利口径都来自注册表绑定：`sourceUseMode` 与 `rightsMode` 在 article
    车道同为 `factual_reference_only`，所以两者取同一个值而不是各写一遍字面量。
    `sourceRole` 与 `publishMediaMode` 是本次工作包内的角色决定，不是注册表事实，
    因此由调用方给出。
    """
    bound = article_registry_source(url=url, platform=platform, **extra)
    use_mode = str(bound["sourceUseMode"])
    return {
        "research_lane": "article",
        "url": url,
        "platform": platform,
        "source_kind": str(bound["sourceKind"]),
        "extractor": str(bound["extractor"]),
        "policy_revision": str(bound["policyRevision"]),
        "source_use_mode": use_mode,
        "rights_mode": use_mode,
        "source_role": source_role,
        "publish_media_mode": publish_media_mode,
        "source": bound,
    }


__all__ = [
    "ARTICLE_SOURCE_UNIT_IDENTITY",
    "CTRIP_SIGHT_URL",
    "DEFAULT_ARTICLE_SITE_ID",
    "FIXTURE_CAPTURED_AT",
    "QUNAR_TRAVELOGUE_URL",
    "WIKIPEDIA_URL",
    "WIKIVOYAGE_URL",
    "article_registry_source",
    "article_registry_write_kwargs",
    "article_source_registry_binding",
]
