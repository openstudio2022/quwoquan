# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-027.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-027.t2
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-027.t3
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-027.t4
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-027.t5
"""local_contract：逐载体对象字节预算的单点声明与下载截面判否。

这套用例钉住 `REQ-012` 的三件事：预算取值只能来自 policy 文件那一处声明；超预算候选
在 `1.download` 截面就地收敛（能降采样就降，降不下去就 typed 判否点名该资产）；载体来自
来源单元自己声明的 research lane，lane 说不清时不替它挑预算。

图片体用真实 JPEG/WebP 编解码构造，不用假字节：判据读的是「重编码后的实际体积能不能
装进预算」，用假字节只会让断言变成对常量的复述。
"""

from __future__ import annotations

import io
import tempfile
from pathlib import Path

import pytest
from PIL import Image

import content.source.image_download as image_download
from core.data_issue import DataIssueCode
from core.image_variants import (
    budget_compliant_profiles,
    derive_budget_compliant_variant,
)
from core.media_processing_policy import (
    MEDIA_PROCESSING_POLICY,
    MEDIA_PROCESSING_POLICY_PATH,
    OBJECT_STORAGE_BUDGET_DEFAULT_CARRIER,
    _required_carrier_budget_table,
)
from core.schema import assert_valid
from core.object_storage_budget import (
    object_storage_budget_bytes,
    publish_carrier_for_research_lane,
    source_unit_asset_budget_bytes,
)
from core.page_media import PageImageDropCode

MEBIBYTE = 1024 * 1024


class _OkVerdict:
    blocks_image_publish = False
    status = "ok"
    reasons: list[str] = []


def _photo_jpeg(width: int, height: int) -> bytes:
    """一张不可压缩的真实 JPEG：像素噪声保证体积由尺寸决定而不是由熵折叠掉。"""

    import random

    rng = random.Random(f"{width}x{height}")
    image = Image.new("RGB", (width, height))
    image.putdata(
        [
            (rng.randrange(256), rng.randrange(256), rng.randrange(256))
            for _ in range(width * height)
        ]
    )
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=95, subsampling=0)
    return buffer.getvalue()


def _run_download(
    monkeypatch: pytest.MonkeyPatch,
    *,
    payload_bytes: bytes,
    research_lane: str,
    assess_ok: bool = True,
):
    """跑一次单候选的下载处置，只桩掉网络与外部评估，预算判据本身仍是被测真相源。"""

    monkeypatch.setattr(
        image_download, "_cached_source_image_payload", lambda *a, **k: None
    )
    monkeypatch.setattr(
        image_download,
        "fetch_image_payload",
        lambda url, max_bytes=0: {
            "bytes": payload_bytes,
            "ext": ".jpg",
            "url": url,
            "requestedUrl": url,
            "contentType": "image/jpeg",
            "sha256": "0" * 64,
        },
    )
    monkeypatch.setattr(
        image_download,
        "_write_image_check_temp_file",
        lambda execution_id, subdir=None, payload=None: Path(tempfile.mkstemp()[1]),
    )
    monkeypatch.setattr(
        image_download,
        "_assess_source_image",
        lambda temp, spec, execution_id=None: _OkVerdict(),
    )
    monkeypatch.setattr(
        image_download, "_cleanup_image_check_temp_file", lambda p: None
    )
    assert assess_ok
    return image_download._download_source_unit_images(
        {
            "source_id": "home_wikipedia",
            "imageUrls": [
                {
                    "url": "https://img.example/hero.jpg",
                    "caption": "剑门关山顶全景，直接呈现目标景区关楼与栈道",
                    "relevance": "剑门关关楼与鸟道栈道实景，摄于山顶观景台",
                    "sourceOrder": 1,
                }
            ],
            "license": "CC BY-SA 4.0",
            "credit": "wiki",
            "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
            "url": "https://zh.wikipedia.org/wiki/剑门关",
        },
        execution_id="t-budget",
        entity_id="剑门关",
        object_dir=Path(tempfile.mkdtemp(prefix="budget_obj_")),
        ordinal=1,
        vertical="travel",
        research_lane=research_lane,
    )


def test_budget_value_has_exactly_one_declaration_site():
    """预算取值只能来自 policy 文件；载体分档与 default 兜底都写在同一处。"""

    table = MEDIA_PROCESSING_POLICY.object_storage_budget_bytes_by_carrier
    assert OBJECT_STORAGE_BUDGET_DEFAULT_CARRIER in table
    # 具名载体档优先，缺档回落 default——两跳都是查表，没有一步是从取值形态推出来的。
    assert object_storage_budget_bytes("video") == table["video"]
    assert (
        object_storage_budget_bytes("entity")
        == table[OBJECT_STORAGE_BUDGET_DEFAULT_CARRIER]
    )
    # 下载截面与 publish 截面对同一载体读到同一个值。
    assert source_unit_asset_budget_bytes("homepage") == object_storage_budget_bytes(
        "entity"
    )
    assert source_unit_asset_budget_bytes("video") == object_storage_budget_bytes(
        "video"
    )


def test_the_declaration_site_is_the_version_controlled_policy_file():
    """声明位是受版本控制的文件，任一生效值都能指回它。"""

    assert MEDIA_PROCESSING_POLICY_PATH.name == "media_processing.policy.yaml"
    declared = MEDIA_PROCESSING_POLICY_PATH.read_text(encoding="utf-8")
    assert "objectStorageBudgetBytesByCarrier:" in declared


def test_policy_assembly_refuses_a_budget_table_without_default():
    """`default` 是必需参数：缺了就在装配期判否，不静默降级成某个内置数字。"""

    with pytest.raises(ValueError, match="objectStorageBudgetBytesByCarrier"):
        _required_carrier_budget_table(
            {"objectStorageBudgetBytesByCarrier": {"video": 52428800}},
            "objectStorageBudgetBytesByCarrier",
        )
    with pytest.raises(ValueError, match="objectStorageBudgetBytesByCarrier"):
        _required_carrier_budget_table({}, "objectStorageBudgetBytesByCarrier")
    # 同一必需性由 schema 独立强制，两处不得只有一处判否。
    with pytest.raises(Exception):
        assert_valid(
            {
                "policyId": "media_processing",
                "sourceAssetMaxBytes": 25165824,
                "pageImageRenditionWidth": 1920,
                "maxPublishableImagePixels": 80000000,
                "maxAssessmentImagePixels": 2000000,
                "assessmentJpegQuality": 85,
                "ocrImagePixels": 2000000,
                "baseDraftImageCandidates": 8,
                "imageFetchTargetSurplus": 2,
                "imageCandidateSurplus": 4,
                "webpMethod": 4,
                "homepageBaseDraftMaxChars": 12000,
            },
            "content",
            "media_processing_policy",
            label="budget-table-missing",
        )


def test_download_derives_a_budget_compliant_variant_for_an_oversized_candidate(
    monkeypatch: pytest.MonkeyPatch,
):
    """超预算但能降采样的候选原地换成最宽的合规交付档，并按新字节身份重登记。"""

    budget = source_unit_asset_budget_bytes("homepage")
    oversized = _photo_jpeg(4200, 2400)
    assert len(oversized) > budget
    derived = derive_budget_compliant_variant(oversized, budget_bytes=budget)
    assert derived is not None
    # 降采样只降到必要程度：取的是第一个装进预算的最宽档。
    assert derived["profile"] == budget_compliant_profiles()[0]

    images, issues, funnel = _run_download(
        monkeypatch, payload_bytes=oversized, research_lane="homepage"
    )
    assert issues == []
    assert funnel["keptCount"] == 1
    assert funnel["assetBudgetBytes"] == budget
    assert len(images[0]["bytes"]) <= budget
    # 字节身份随派生体改写，旧摘要不得继续流转。
    assert images[0]["contentSha256"] == "sha256:" + derived["sha256"]
    assert images[0]["contentType"] == "image/webp"
    assert images[0]["width"] == derived["width"]
    assert images[0]["height"] == derived["height"]
    assert funnel["budgetDerivations"][0]["derivation"].startswith(
        "budget_compliant_variant:"
    )


def test_download_refuses_a_candidate_no_declared_profile_can_fit(
    monkeypatch: pytest.MonkeyPatch,
):
    """每档都装不进预算时在下载截面 typed 判否并点名该资产，不推迟到 publish。"""

    oversized = _photo_jpeg(2000, 1200)
    tight_budget = 4096
    assert derive_budget_compliant_variant(oversized, budget_bytes=tight_budget) is None
    monkeypatch.setattr(
        image_download, "source_unit_asset_budget_bytes", lambda lane: tight_budget
    )

    images, issues, funnel = _run_download(
        monkeypatch, payload_bytes=oversized, research_lane="homepage"
    )
    assert images == []
    assert funnel["keptCount"] == 0
    assert funnel["dropReasonCounts"] == {PageImageDropCode.BUDGET_POLICY.value: 1}
    assert len(issues) == 1
    assert DataIssueCode.MEDIA_ASSET_OVER_BUDGET.value in issues[0]
    # 判否必须点名该资产，运维据此换素材而不是回头猜哪一张。
    assert "剑门关/home_wikipedia#1" in issues[0]
    assert "https://img.example/hero.jpg" in funnel["drops"][0]["url"]


def test_download_refuses_a_source_unit_whose_research_lane_is_undeclared(
    monkeypatch: pytest.MonkeyPatch,
):
    """lane 缺席或落在闭集之外时拿不到载体，因此也不替它挑一个预算。"""

    for lane in ("", "unknown_lane"):
        with pytest.raises(ValueError, match="researchLane"):
            _run_download(
                monkeypatch,
                payload_bytes=_photo_jpeg(1200, 800),
                research_lane=lane,
            )


def test_publish_carrier_is_a_table_lookup_over_the_declared_lane_closed_set():
    """lane 到载体是查表，四个 lane 各自指向预算表里的一档。"""

    assert publish_carrier_for_research_lane("homepage") == "entity"
    assert publish_carrier_for_research_lane("article") == "article"
    assert publish_carrier_for_research_lane("image") == "image"
    assert publish_carrier_for_research_lane("video") == "video"
