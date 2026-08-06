"""图片下载 6 项契约与行为门禁：相关性必填非模板、每实体≥2、最小像素、
contentType+完整版权持久化、多变体(webp)格式化、感知哈希去重。

可直接运行：python3 quwoquan_data/tests/local_contract/source/test_image_download_gates__behavior__functional__local_contract_test.py
"""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import hashlib
import io
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(SCRIPTS_ROOT))

import numpy as np  # noqa: E402
from content.source.contracts import (  # noqa: E402
    MediaProvenance,
    ModelReleaseStatus,
    RightsAuditStatus,
)
from content.source.source_unit import write_source_unit  # noqa: E402
from core.image_rules import (  # noqa: E402
    MIN_ENTITY_IMAGES,
    image_caption_quality_issue,
    is_generic_relevance,
    min_count_issue,
    pixel_size_issue,
    relevance_issue,
)
from core.image_safety import dedupe_image_payloads  # noqa: E402
from core.image_variants import build_local_variants, image_dimensions  # noqa: E402
from core.paths import execution_source_unit_dir  # noqa: E402
from PIL import Image  # noqa: E402
from support.execution_manifest_fixture import build_execution_fixture  # noqa: E402


def _jpeg(seed: int, size=(800, 600)) -> bytes:
    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 256, size=(size[1], size[0], 3), dtype="uint8")
    buf = io.BytesIO()
    Image.fromarray(arr, "RGB").save(buf, format="JPEG", quality=85)
    return buf.getvalue()


# ── Gate 1: 相关性必填且非模板 ──────────────────────────────────────
def test_relevance_generic_and_template_blocked():
    assert is_generic_relevance("")
    assert is_generic_relevance("实景主图")
    assert is_generic_relevance("峨眉山 实景主图", entity_id="峨眉山")
    assert is_generic_relevance("覆盖该对象的基础事实/交通")
    assert not is_generic_relevance("金顶日出云海，峨眉山徒步终点的标志景观", entity_id="峨眉山")
    assert relevance_issue("封面图", entity_id="峨眉山", asset_id="001") is not None
    assert relevance_issue("牛奶海高山湖泊实景", entity_id="稻城亚丁", asset_id="001") is None
    assert relevance_issue(
        "距墨石公园14公里的惠远寺，支撑互补藏文化游线",
        entity_id="墨石公园",
        asset_id="002",
    ) is not None
    assert relevance_issue(
        "塔公草原实况，支撑墨石公园与塔公草原组合一日游",
        entity_id="墨石公园",
        asset_id="003",
    ) is not None


def test_low_quality_image_caption_blocks_garbled_platform_template():
    assert image_caption_quality_issue(
        "500px provided description: ???????????????????????? [#?? ,#??]",
        entity_id="光雾山",
        asset_id="光雾山#1",
    ) is not None
    assert image_caption_quality_issue(
        "光雾山云雾山脊与森林景观",
        entity_id="光雾山",
        asset_id="光雾山#2",
    ) is None


def test_media_provenance_derives_model_release_before_rights_audit():
    provenance = MediaProvenance.from_mapping(
        {
            "sourceUrl": "https://upload.wikimedia.org/example.jpg",
            "license": "CC BY 4.0",
            "credit": "Example photographer",
            "termsUrl": "https://creativecommons.org/licenses/by/4.0/",
            "authorizationProof": "https://commons.wikimedia.org/wiki/File:Example.jpg",
            "usageScope": "app_publish",
            "caption": "测试实体丙山景",
        },
        vertical="travel",
    )

    assert provenance.model_release_status is ModelReleaseStatus.NOT_REQUIRED
    assert provenance.rights_audit_status is RightsAuditStatus.VERIFIED
    assert not any("modelReleaseStatus" in issue for issue in provenance.rights_audit_issues)


# ── Gate 2: 每实体最少图片数 ────────────────────────────────────────
def test_min_count_gate():
    assert MIN_ENTITY_IMAGES >= 2
    assert min_count_issue(1, entity_id="峨眉山") is not None
    assert min_count_issue(MIN_ENTITY_IMAGES, entity_id="峨眉山") is None


# ── Gate 3: 最小像素尺寸 ────────────────────────────────────────────
def test_pixel_size_gate():
    small = _jpeg(1, size=(320, 200))
    big = _jpeg(2, size=(1024, 768))
    assert image_dimensions(small) == (320, 200)
    assert image_dimensions(big) == (1024, 768)
    assert pixel_size_issue(320, 200, asset_id="001") is not None
    assert pixel_size_issue(None, None, asset_id="001") is not None
    assert pixel_size_issue(1024, 768, asset_id="001") is None


# ── Gate 5: 多变体格式化（webp，仅缩小） ────────────────────────────
def test_build_local_variants_webp_downscale_only():
    big = _jpeg(3, size=(2400, 1600))
    variants = build_local_variants(big, base_name="001_emei")
    profiles = {v["profile"] for v in variants}
    assert {"thumbnail", "display", "cover", "full"}.issubset(profiles), profiles
    for v in variants:
        assert v["format"] == "webp"
        assert v["fileName"].startswith("001_emei.variants/")
        assert v["bytes"]  # 字节存在，调用方落盘
        # 仅缩小：变体宽不超过源宽
        assert v["width"] <= 2400


# ── Gate 6: 感知哈希去重 ────────────────────────────────────────────
def test_dedupe_image_payloads_removes_near_duplicates():
    a = _jpeg(11)
    a_again = a  # 字节完全相同 → 必判重
    b = _jpeg(97)
    payloads = [
        {"bytes": a, "url": "a"},
        {"bytes": a_again, "url": "a2"},
        {"bytes": b, "url": "b"},
    ]
    kept, dup = dedupe_image_payloads(payloads)
    assert len(kept) == 2, [k["url"] for k in kept]
    assert len(dup) == 1


# ── Gate 4 + 5 落盘：write_source_unit 持久化 contentType/版权/尺寸/变体 ──
def test_source_unit_persists_meta_and_variants():
    obj = Path(tempfile.mkdtemp(prefix="img_gate_obj_")) / "测试实体丙"
    body = _jpeg(5, size=(1280, 960))
    execution_id = "20260711--travel-image-download--test-region-b--pilot-001"
    build_execution_fixture(execution_id)
    manifest = write_source_unit(
        obj,
        execution_id=execution_id,
        ordinal=1,
        source_id="overview_baike",
        source_md="# 测试实体丙\n\n概述",
        platform="baike",
        source_category="overview_baike",
        url="https://zh.wikipedia.org/wiki/测试实体丙",
        title="测试实体丙（百科）",
        target_ref="/entity/地点/景区/测试实体丙",
        images=[
            {
                "bytes": body,
                "ext": ".jpg",
                "url": "https://upload.wikimedia.org/x.jpg",
                "sourceUrl": "https://commons.wikimedia.org/wiki/File:x.jpg",
                "contentType": "image/jpeg",
                "license": "CC BY-SA 3.0",
                "credit": "Carol",
                "termsUrl": "https://creativecommons.org/licenses/by-sa/3.0/",
                "caption": "测试实体丙一号冰川",
                "relevance": "支撑低海拔现代冰川核心体验段落",
                "slug": "测试实体丙_1",
            }
        ],
    )
    assert manifest["assetCount"] == 1
    unit = execution_source_unit_dir(execution_id, manifest["sourceUnitId"])
    idx = json.loads((unit / "assets" / "index.json").read_text("utf-8"))
    asset = idx["assets"][0]
    assert asset["contentType"] == "image/jpeg"
    assert asset["license"] == "CC BY-SA 3.0"
    assert asset["termsUrl"].startswith("https://creativecommons.org")
    assert asset["modelReleaseStatus"] == "not_required"
    assert not any("modelReleaseStatus" in issue for issue in asset["rightsAuditIssues"])
    assert asset["width"] == 1280 and asset["height"] == 960
    assert asset["relevance"] == "支撑低海拔现代冰川核心体验段落"
    assert asset["variants"], "assets/index.json 应记录多变体"
    for v in asset["variants"]:
        assert (unit / "assets" / v["fileName"]).is_file(), v


def test_source_unit_preserves_professional_acquisition_identity():
    obj = Path(tempfile.mkdtemp(prefix="professional_img_obj_")) / "九寨沟"
    body = _jpeg(23, size=(1280, 960))
    content_sha256 = "sha256:" + hashlib.sha256(body).hexdigest()
    execution_id = "20260805--travel-image-m100--china--scale-911"
    build_execution_fixture(execution_id)
    manifest = write_source_unit(
        obj,
        execution_id=execution_id,
        ordinal=1,
        source_id="pinterest",
        source_md="# 九寨沟专业摄影来源",
        platform="Pinterest",
        source_category="image_collection",
        source_kind="image_collection",
        source_use_mode="rights_audit_only",
        research_lane="image",
        url="https://www.pinterest.com/pin/example/",
        title="九寨沟五花海",
        target_ref="/entity/地点/景区/九寨沟",
        build_variants=False,
        images=[
            {
                "bytes": body,
                "ext": ".jpg",
                "url": "https://cdn.example.test/jiuzhaigou.jpg",
                "sourceUrl": "https://www.pinterest.com/pin/example/",
                "contentType": "image/jpeg",
                "license": "unknown",
                "credit": "摄影师甲",
                "rightsStatus": "unverified",
                "rightsIssues": ["commercial authorization is unverified"],
                "acquisitionReceiptRef": f"receipts/{'a' * 64}.json",
                "professionalAssetId": "pin-example",
                "professionalContentSha256": content_sha256,
                "caption": "九寨沟五花海清晨",
                "relevance": "画面主体为九寨沟五花海",
            }
        ],
    )
    unit = execution_source_unit_dir(execution_id, manifest["sourceUnitId"])
    asset = json.loads(
        (unit / "assets/index.json").read_text(encoding="utf-8")
    )["assets"][0]
    assert asset["acquisitionReceiptRef"] == f"receipts/{'a' * 64}.json"
    assert asset["professionalAssetId"] == "pin-example"
    assert asset["professionalContentSha256"] == content_sha256


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"image download gate tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
