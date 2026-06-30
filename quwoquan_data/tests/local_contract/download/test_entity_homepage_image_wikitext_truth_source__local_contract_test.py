"""实体百科底稿图候选「唯一真相源 = wikitext 真实图位」契约。

固化「封面/插图不来自底稿原文」真相源分裂 bug 的修复：
- plan 阶段 `_mediawiki_page_images` 的图候选必须 ⊆ 页面 wikitext `[[File:...]]` 真实图位；
- 排除视频/音频等非位图 transclude（如 .webm），不再用 prop=images 全量 transclude；
- 封面按 sourceOrder 取序首非视频代表图；
- 公有领域(PD)无 LicenseUrl 的真实图不被误丢，termsUrl 回退到 Commons 文件描述页；
- 实体底稿 same_source 绝不混入 commons/openverse 等搜索池 URL。
"""
from __future__ import annotations

from support.source_plan_guidance_fixtures import *  # noqa: F401,F403

from download.research.wiki_media import _file_match_key, _mediawiki_page_images


# 模拟 action=parse&prop=wikitext 返回的页面正文：信息框(非 [[File:]]) + 正文真实图位
# (含一个 .webm 视频) ；panoramio 类页面外图不出现在 wikitext，模拟其只能经 prop=images
# 全量 transclude 混入——修复后绝不应进入候选。
_FAKE_WIKITEXT = """{{Infobox 山
| image = SomeInfoboxOnlyFile.jpg
}}

== 概述 ==
青城后山简介，文字足够构成正文段落，描述泰安古镇与五龙沟的景观特征与历史。
[[File:TaiAn_GuZhen.jpg|thumb|泰安古镇]]

承接上文继续描述五龙沟一带的步道与水景，给出可读的真实事实段落内容。
[[File:WuLongGou.jpg|thumb|五龙沟]]

== 影像 ==
老君阁全景视频，下面这一行是视频文件而非位图，必须被排除。
[[File:Laojunge.webm|thumb|老君阁视频]]
百丈桥位于后山末段，下面这张是真实位图但顺序靠后。
[[File:BaiZhangQiao.jpg|thumb|百丈桥]]
"""

# imageinfo 真相：泰安古镇/五龙沟为 Public domain 且无 LicenseUrl(常见)；百丈桥为 CC BY-SA 2.5。
# panoramio 故意提供 imageinfo，但因不在 wikitext，不会被请求，更不应进入候选。
_FILE_INFO = {
    _file_match_key("File:TaiAn GuZhen.jpg"): {
        "title": "File:TaiAn GuZhen.jpg",
        "imageinfo": [
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/f/f8/TaiAn_GuZhen.jpg",
                "descriptionurl": "https://commons.wikimedia.org/wiki/File:TaiAn_GuZhen.jpg",
                "width": 1416,
                "height": 1064,
                "extmetadata": {
                    "LicenseShortName": {"value": "Public domain"},
                    "LicenseUrl": {"value": ""},
                    "Artist": {"value": "Contributor A"},
                },
            }
        ],
    },
    _file_match_key("File:WuLongGou.jpg"): {
        "title": "File:WuLongGou.jpg",
        "imageinfo": [
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/c/c8/WuLongGou.jpg",
                "descriptionurl": "https://commons.wikimedia.org/wiki/File:WuLongGou.jpg",
                "width": 2832,
                "height": 2128,
                "extmetadata": {
                    "LicenseShortName": {"value": "Public domain"},
                    "LicenseUrl": {"value": ""},
                    "Artist": {"value": "Contributor B"},
                },
            }
        ],
    },
    _file_match_key("File:BaiZhangQiao.jpg"): {
        "title": "File:BaiZhangQiao.jpg",
        "imageinfo": [
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/5/5c/BaiZhangQiao.jpg",
                "descriptionurl": "https://commons.wikimedia.org/wiki/File:BaiZhangQiao.jpg",
                "width": 2832,
                "height": 2128,
                "extmetadata": {
                    "LicenseShortName": {"value": "CC BY-SA 2.5"},
                    "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/2.5"},
                    "Artist": {"value": "Contributor C"},
                },
            }
        ],
    },
    _file_match_key("File:Some_panoramio_external.jpg"): {
        "title": "File:Some panoramio external.jpg",
        "imageinfo": [
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/0/00/Some_panoramio_external.jpg",
                "descriptionurl": "https://commons.wikimedia.org/wiki/File:Some_panoramio_external.jpg",
                "width": 2000,
                "height": 1500,
                "extmetadata": {
                    "LicenseShortName": {"value": "CC BY 3.0"},
                    "LicenseUrl": {"value": "https://creativecommons.org/licenses/by/3.0"},
                },
            }
        ],
    },
}


def _fake_wiki_api(host, params):
    action = str(params.get("action") or "")
    if action == "parse":
        assert str(params.get("prop") or "") == "wikitext"
        return {"parse": {"title": "青城山", "wikitext": {"*": _FAKE_WIKITEXT}}}
    if action == "query" and "imageinfo" in str(params.get("prop") or ""):
        titles = [t for t in str(params.get("titles") or "").split("|") if t]
        pages = {}
        for index, requested in enumerate(titles):
            row = _FILE_INFO.get(_file_match_key(requested))
            if row is not None:
                pages[str(index)] = row
        return {"query": {"pages": pages}}
    return {}


def _run_with_fake_wiki_api(callable_):
    import download.research_plan as research_mod

    original = research_mod._wiki_api
    try:
        research_mod._wiki_api = _fake_wiki_api
        return callable_()
    finally:
        research_mod._wiki_api = original


def test_mediawiki_page_images_only_returns_wikitext_real_placements_ordered():
    images = _run_with_fake_wiki_api(
        lambda: _mediawiki_page_images(
            "zh.wikipedia.org", "青城山", entity_id="青城山", limit=10
        )
    )
    # 候选 ⊆ wikitext 真实 [[File:]] 图位（非视频子集），且不含页面外 panoramio。
    file_keys = [_file_match_key(img["fileTitle"]) for img in images]
    assert file_keys == [
        _file_match_key("File:TaiAn GuZhen.jpg"),
        _file_match_key("File:WuLongGou.jpg"),
        _file_match_key("File:BaiZhangQiao.jpg"),
    ]
    # 视频 .webm 被排除（不出现在任何候选 url / fileTitle）。
    assert all(".webm" not in img["url"].lower() for img in images)
    assert all("laojunge" not in _file_match_key(img["fileTitle"]) for img in images)
    # 页面外（panoramio/信息框专属）图绝不进入候选。
    assert all("panoramio" not in img["url"].lower() for img in images)
    assert all("infoboxonly" not in _file_match_key(img["fileTitle"]) for img in images)
    # 顺序按 wikitext sourceOrder：单调递增。
    assert [img["sourceOrder"] for img in images] == [0, 1, 2]


def test_mediawiki_page_images_cover_is_first_real_placement_not_tail_minor_scene():
    images = _run_with_fake_wiki_api(
        lambda: _mediawiki_page_images(
            "zh.wikipedia.org", "青城山", entity_id="青城山", limit=10
        )
    )
    cover = images[0]
    # 封面取序首代表图（泰安古镇），不是末尾后山小景（百丈桥）。
    assert _file_match_key(cover["fileTitle"]) == _file_match_key("File:TaiAn GuZhen.jpg")
    assert cover["caption"] == "泰安古镇"
    assert "BaiZhangQiao" not in cover["fileTitle"]


def test_mediawiki_page_images_keeps_public_domain_image_without_license_url():
    images = _run_with_fake_wiki_api(
        lambda: _mediawiki_page_images(
            "zh.wikipedia.org", "青城山", entity_id="青城山", limit=10
        )
    )
    by_key = {_file_match_key(img["fileTitle"]): img for img in images}
    taian = by_key[_file_match_key("File:TaiAn GuZhen.jpg")]
    # PD 无 LicenseUrl 仍合规保留；termsUrl 回退到 Commons 文件描述页（可审计）。
    assert taian["license"] == "Public domain"
    assert taian["termsUrl"] == "https://commons.wikimedia.org/wiki/File:TaiAn_GuZhen.jpg"
    assert taian["authorizationProof"].startswith("https://commons.wikimedia.org/wiki/File:")


def test_mediawiki_page_images_caption_comes_from_wikitext_placement():
    images = _run_with_fake_wiki_api(
        lambda: _mediawiki_page_images(
            "zh.wikipedia.org", "青城山", entity_id="青城山", limit=10
        )
    )
    captions = {_file_match_key(img["fileTitle"]): img["caption"] for img in images}
    assert captions[_file_match_key("File:WuLongGou.jpg")] == "五龙沟"
    assert captions[_file_match_key("File:BaiZhangQiao.jpg")] == "百丈桥"


def test_homepage_source_images_are_same_source_only_no_search_pool_urls():
    """实体主页来源(home_wikipedia)的 imageUrls 必须只来自页面真实图位(同源)。

    即便 commons/openverse 等搜索池非空，也绝不混入实体底稿；封面取 wiki 图位序首。

    注：`auto_plan_writer` 对 `_wiki_title_for_entity` 等用模块内直接绑定，对搜索池经
    `_discover_open_license_image_pools` → runtime_bridge 解析 `download.research_plan.*`；
    为 hermetic（不联网）需分别在 apw / rp 两处打桩。
    """
    import download.research_plan as research_mod
    import download.research.auto_plan_writer as apw

    task = "旅行/地域/测试省/景区/底稿同源隔离"
    batch = "homepage_same_source_truth"
    entity = "同源隔离景区"

    def _wiki_img(name: str, caption: str, order: int) -> dict:
        return {
            "url": f"https://upload.wikimedia.org/wikipedia/commons/aa/{name}.jpg",
            "platform": "维基百科",
            "license": "Public domain",
            "credit": "Wiki contributor",
            "sourceUrl": f"https://commons.wikimedia.org/wiki/File:{name}.jpg",
            "termsUrl": f"https://commons.wikimedia.org/wiki/File:{name}.jpg",
            "licenseSnapshot": "Public domain recorded on zh.wikipedia.org file metadata",
            "authorizationProof": f"https://commons.wikimedia.org/wiki/File:{name}.jpg",
            "usageScope": "app_publish",
            "width": 1600,
            "height": 1000,
            "caption": caption,
            "relevance": caption,
            "creator": "Wiki contributor",
            "collectionPageUrl": "https://zh.wikipedia.org/wiki/同源隔离景区",
            "sourceOrder": order,
            "fileTitle": f"File:{name}.jpg",
        }

    wiki_page_images = [
        _wiki_img("RealCover", "真实封面图位", 0),
        _wiki_img("RealSecond", "真实第二图位", 1),
    ]
    # 搜索池图（commons/openverse）——绝不应进入实体主页 imageUrls。
    search_pool_image = {
        "url": "https://img.openverse.example/external-search.jpg",
        "license": "CC BY-SA 4.0",
        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
        "authorizationProof": "https://openverse.example/item/123",
        "width": 1600,
        "height": 1000,
        "caption": entity,
        "relevance": entity,
        "creator": "Openverse",
        "collectionPageUrl": "https://openverse.example/item/123",
    }

    def _mediawiki_page_images_stub(host, title, entity_id, limit=6):
        return list(wiki_page_images) if host == "zh.wikipedia.org" and title == entity else []

    # apw 直接绑定的发现/网络函数：打桩到 auto_plan_writer 模块以保证 hermetic。
    apw_patches = {
        "_wiki_title_for_entity": lambda host, entity_id, entity_aliases=(): (
            entity if host == "zh.wikipedia.org" else ""
        ),
        "_wiki_related_titles_for_entity": lambda host, entity_id, entity_aliases=(): [],
        "_wikidata_item_for_zhwiki": lambda title: "",
        "_wikidata_item_for_entity_search": lambda entity_id: "",
        "_wikidata_entity_aliases": lambda qid: [],
        "_official_website": lambda qid: "",
        "_trusted_external_links": lambda title, limit=4: [],
        "_qunar_travelogue_sources": lambda entity_id, entity_aliases=(), limit=4: [],
        "_mediawiki_page_images": _mediawiki_page_images_stub,
    }
    # 搜索池经 _discover_open_license_image_pools → runtime_bridge 解析 research_plan.*。
    rp_patches = {
        "_commons_images": lambda entity_id, entity_aliases=(), limit=10: [search_pool_image],
        "_commons_category_images": lambda category, entity_id, entity_aliases=(), limit=8: [],
        "_wikidata_commons_images": lambda qid, entity_id, entity_aliases=(), limit=10: [search_pool_image],
        "_openverse_images": lambda entity_id, entity_aliases=(), limit=12: [search_pool_image],
        "_mediawiki_page_images": _mediawiki_page_images_stub,
    }
    apw_originals = {name: getattr(apw, name) for name in apw_patches}
    rp_originals = {name: getattr(research_mod, name) for name in rp_patches}
    try:
        for name, value in apw_patches.items():
            setattr(apw, name, value)
        for name, value in rp_patches.items():
            setattr(research_mod, name, value)
        write_auto_research_plans(
            task,
            batch,
            [entity],
            entity_type="景区",
            force=True,
            lanes={"homepage", "article"},
        )
    finally:
        for name, value in apw_originals.items():
            setattr(apw, name, value)
        for name, value in rp_originals.items():
            setattr(research_mod, name, value)

    plan = (
        resolve_entity_object_dir(task, batch, entity, etype_hint="景区")
        / "1.download"
        / "homepage_source_plan.json"
    )
    sources = read_json(plan)["payload"]["sources"]
    wiki_sources = [s for s in sources if s.get("source_id") == "home_wikipedia"]
    assert wiki_sources, sources
    image_urls = wiki_sources[0].get("imageUrls") or []
    urls = [str(img.get("url") or "") for img in image_urls]
    # 同源：实体主页图位只来自页面真实图位（wiki），封面序首。
    assert urls[0] == "https://upload.wikimedia.org/wikipedia/commons/aa/RealCover.jpg"
    assert set(urls) <= {img["url"] for img in wiki_page_images}
    # 搜索池 URL 绝不混入实体底稿。
    assert all("openverse" not in url.lower() for url in urls)
    assert search_pool_image["url"] not in urls
    assert str(wiki_sources[0].get("imageEvidenceMode") or "") == "same_source"
