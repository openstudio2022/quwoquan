# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/on-demand-content-pool-admission/spec.md#gwt-004.t4
"""hero 名额不得被注定被采纳门排除的水印高风险来源占用。

历史失败形态：Commons 重托管的 Panoramio 原图许可完全合规，采集阶段照单接受并
占满 homepage 唯一的 hero 名额；直到 release 采纳门才按 provenance 排除，该实体
因此零可发布图，整份工作包报废。放量到百级时这类实体是稳定比例，必须在采集处
就跳过并取下一张，而不是让池子里带着注定失败的候选。
"""
from __future__ import annotations

import pytest
from content.source.research.homepage_article_source_ready_mediawiki import (
    acquire_open_image_assets,
)
from content.source.research.network_io import HttpFetchResult
from core.image_decode import ImageProbe
from core.image_safety import ImageVerdict, watermark_prone_source_reason
from core.media_source_provenance import declared_provenance_exclusion_reason
from support.homepage_article_source_ready_acquisition_fixture import CAPTURED_AT

_PANORAMIO_PAGE = (
    "https://commons.wikimedia.org/wiki/File:Qingcheng_-_panoramio_(3).jpg"
)
_CLEAN_PAGE = "https://commons.wikimedia.org/wiki/File:Qingcheng_gate.jpg"


def _row(
    *,
    url: str,
    source_url: str,
    creator: str = "Contributor",
    credit: str = "Contributor",
) -> dict[str, str]:
    return {
        "url": url,
        "sourceUrl": source_url,
        "license": "CC BY-SA 4.0",
        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
        "authorizationProof": source_url,
        "creator": creator,
        "credit": credit,
        "usageScope": "app_publish",
        "modelReleaseStatus": "not_required",
    }


def _watermark_prone_row(*, url: str, source_url: str) -> dict[str, str]:
    """出处类别：第三方图库经批量导入工具搬运，权利人未第一手声明。"""

    return _row(
        url=url,
        source_url=source_url,
        creator="Panoramio upload bot",
        credit="Transferred from Panoramio by Archive Team",
    )


@pytest.fixture(name="clean_probes")
def _clean_probes(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """所有候选的字节都判定为安全，让结果只由 provenance 决定。"""
    from content.source.research import homepage_article_source_ready_mediawiki as mod
    from core import image_decode

    fetched: list[str] = []

    def fetch(url: str, timeout: float | None = None) -> HttpFetchResult:
        fetched.append(url)
        return HttpFetchResult(0, 200, url, f"bytes-of-{url}".encode())

    monkeypatch.setattr(mod.network_io, "fetch_http", fetch)
    monkeypatch.setattr(
        mod,
        "assess_image",
        lambda *a, **k: ImageVerdict(
            path="fixture",
            status="safe",
            faces=0,
            has_watermark=False,
            text_area_ratio=0.0,
            reasons=(),
            backends=("cv", "ocr"),
        ),
    )
    monkeypatch.setattr(
        image_decode,
        "probe_image_bytes",
        lambda body: ImageProbe(width=1600, height=1000, mime_type="image/jpeg"),
    )
    return fetched


def test_hero_skips_watermark_prone_provenance_and_takes_the_next_candidate(
    clean_probes: list[str],
) -> None:
    acquired = acquire_open_image_assets(
        [
            _watermark_prone_row(
                url="https://upload.wikimedia.org/panoramio-3.jpg",
                source_url=_PANORAMIO_PAGE,
            ),
            _row(url="https://upload.wikimedia.org/gate.jpg", source_url=_CLEAN_PAGE),
        ],
        source_unit_ref="sources/homepage-qingcheng",
        roles=("hero",),
        captured_at=CAPTURED_AT,
    )

    assert len(acquired) == 1
    assert acquired[0].document["sourcePageUrl"] == _CLEAN_PAGE
    # 被排除的候选连字节都不必取回：provenance 判定先于网络 IO。
    assert clean_probes == ["https://upload.wikimedia.org/gate.jpg"]


def test_all_candidates_watermark_prone_is_a_typed_shortfall(
    clean_probes: list[str],
) -> None:
    """短缺必须在采集处以既有 typed 拒绝显现，而不是留一张注定被排除的废图。"""
    from content.source.research.homepage_article_source_ready_types import (
        MediaWikiSourceReadyRejected,
    )

    rows = [
        _watermark_prone_row(
            url="https://upload.wikimedia.org/panoramio-3.jpg",
            source_url=_PANORAMIO_PAGE,
        )
    ]

    with pytest.raises(MediaWikiSourceReadyRejected, match="safe open-license"):
        acquire_open_image_assets(
            rows,
            source_unit_ref="sources/homepage-qingcheng",
            roles=("hero",),
            captured_at=CAPTURED_AT,
        )

    assert clean_probes == []


def test_acquisition_and_admission_share_one_provenance_closed_set() -> None:
    """两侧同源：出处类别裁决与文件身份补充判据共用同一高风险平台闭集。"""
    doomed = _watermark_prone_row(
        url="https://upload.wikimedia.org/panoramio-3.jpg",
        source_url=_PANORAMIO_PAGE,
    )
    clean = _row(url="https://upload.wikimedia.org/gate.jpg", source_url=_CLEAN_PAGE)

    assert declared_provenance_exclusion_reason(doomed) == (
        "watermark_prone_source_provenance:panoramio"
    )
    assert declared_provenance_exclusion_reason(clean) == ""
    # 文件身份层补充判据只关闭 OCR 漏检，其平台闭集与出处裁决同源。
    assert watermark_prone_source_reason(("Transferred from Panoramio",)) == (
        "watermark_prone_source_provenance:panoramio"
    )


def test_watermark_prone_row_does_not_count_toward_the_supplement_threshold() -> None:
    """扩源阈值按可采纳候选计：一张注定被排除的图不得顶满名额。"""
    from content.source.research.homepage_article_source_ready_assets import (
        provenance_admissible_image_rows,
    )

    doomed = _watermark_prone_row(
        url="https://upload.wikimedia.org/panoramio-3.jpg",
        source_url=_PANORAMIO_PAGE,
    )
    clean = _row(url="https://upload.wikimedia.org/gate.jpg", source_url=_CLEAN_PAGE)

    assert provenance_admissible_image_rows([doomed]) == []
    assert provenance_admissible_image_rows([doomed, clean]) == [clean]


def test_single_watermark_prone_page_image_still_triggers_supplement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """青城山形态：条目页只渲染一张 Panoramio 图，扩源必须照样触发。

    历史失败：阈值按原始张数算，`1 < 1` 为假，三个补充源从未被调用，实体拿到
    零张可发布图后整份工作包报废。
    """
    from content.source.mediawiki_page import MediaWikiPageBundle
    from content.source.research import homepage_article_source_ready_mediawiki as mod
    from content.source.research.homepage_article_source_ready_types import AcquiredAsset

    body = (
        "青城山位于成都市都江堰市，是道教名山并列入世界遗产。\n"
        "山中保存多处宫观建筑，公共交通与景区接驳车可达。\n\n"
        "游客可沿步道游览前山与后山，了解道教文化、林木生态与地方历史。"
        "景区设有导览、休息与无障碍设施，参观前应核对开放信息并遵守安全提示。"
    )
    bundle = MediaWikiPageBundle(
        requested_title="青城山",
        resolved_title="青城山",
        redirect_chain=(),
        page_id=10,
        revision_id=20,
        content_sha256="page-sha",
        rendered_text=body,
        wikitext="{{Infobox\n| website = https://example.test/official\n}}",
        rendered_image_titles=("File:panoramio.jpg",),
        raw='{"query":{"pages":{"10":{}}}}',
    )
    doomed = {
        **_watermark_prone_row(
            url="https://upload.wikimedia.org/panoramio-3.jpg",
            source_url=_PANORAMIO_PAGE,
        ),
        "pageRevisionId": 20,
        "pageContentSha256": "page-sha",
    }
    clean = _row(url="https://upload.wikimedia.org/gate.jpg", source_url=_CLEAN_PAGE)
    monkeypatch.setattr(
        mod, "fetch_mediawiki_page_bundle_for_url", lambda *a, **k: bundle
    )
    monkeypatch.setattr(mod, "_mediawiki_page_images", lambda *a, **k: [doomed])
    monkeypatch.setattr(
        mod, "wikidata_commons_images_for_entity", lambda *a, **k: [clean]
    )
    monkeypatch.setattr(mod, "commons_images_for_entity", lambda *a, **k: [])
    monkeypatch.setattr(mod, "openverse_images_for_entity", lambda *a, **k: [])
    offered: list[str] = []

    def acquire_assets(rows, *, source_unit_ref, roles, captured_at):
        offered.extend(str(row.get("url") or "") for row in rows)
        return (
            AcquiredAsset(
                body=b"clean-bytes",
                document={
                    "assetId": "asset-clean",
                    "role": roles[0],
                    "assetRef": f"{source_unit_ref}/assets/clean.jpg",
                    "originalAssetUrl": clean["url"],
                    "sourcePageUrl": _CLEAN_PAGE,
                    "platform": "Wikimedia Commons",
                    "provider": "wikimedia_commons",
                    "creator": "Contributor",
                    "capturedAt": captured_at,
                    "contentSha256": "sha256:" + "c" * 64,
                    "license": "CC BY-SA 4.0",
                    "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                    "authorizationProof": _CLEAN_PAGE,
                    "usageScope": "app_publish",
                    "modelReleaseStatus": "not_required",
                    "authorizationRequired": False,
                    "rightsStatus": "verified",
                    "rightsIssues": [],
                    "acquisitionStatus": "acquired",
                    "distributionDecision": "research_allowed",
                    "qualityStatus": "passed",
                    "safetyStatus": "passed",
                    "generated": False,
                    "width": 1600,
                    "height": 1000,
                    "byteCount": 11,
                    "fileSha256": "sha256:" + "c" * 64,
                    "safetyEvidence": {},
                    "accessEvidence": {},
                },
            ),
        )

    monkeypatch.setattr(mod, "acquire_open_image_assets", acquire_assets)
    acquired = mod.acquire_mediawiki_source_ready_candidate(
        {
            "canonicalEntityRef": "/entity/地点/景区/青城山",
            "candidateName": "青城山",
            "entityType": "地点/景区",
            "province": "四川省",
            "city": "成都市",
            "district": "都江堰市",
            "source": {
                "sourceKind": "wikipedia",
                "extractor": "wikipedia_api",
                "sourceUrl": "https://zh.wikipedia.org/wiki/青城山",
                "resolvedTitle": "青城山",
                "observedAt": CAPTURED_AT,
            },
        },
        carrier="homepage",
        source_revision="sha256:" + "1" * 64,
        source_digest="sha256:" + "2" * 64,
        entity_catalog_digest="sha256:" + "3" * 64,
        captured_at=CAPTURED_AT,
    )

    assert offered == [doomed["url"], clean["url"]]
    assert acquired.candidate["hero"]["sourcePageUrl"] == _CLEAN_PAGE
