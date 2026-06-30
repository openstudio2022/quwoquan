"""P4 图库合规契约：图虫/Pinterest 受限如实标注 + 授权完整性硬门 + 非中文译简体门。

- P4a 图库分级：registry rightsPolicy 为唯一真相源；图虫=逐图创作者授权、Pinterest=仅参考，
  均如实标注 restricted + bypassAttempted=false + 替代路径=开放许可图池；Commons/Openverse 可发布。
- P4b 授权完整性硬门：集合/页级授权必须传播到每张图；缺逐图 authorizationProof 一律不进发布面。
- P4c 非中文图片元数据门：英文/拉丁主导 caption / 标题须先译简体中文，否则阻断发布。

可直接运行：python3 quwoquan_data/tests/local_contract/common/test_image_provider_compliance__local_contract_test.py
"""
from __future__ import annotations

import copy
import sys
import tempfile
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import os  # noqa: E402

os.environ.setdefault("QWQ_RUNTIME_ROOT", tempfile.mkdtemp(prefix="image_compliance_rt_"))

from download.research.image_provider_compliance import (  # noqa: E402
    classify_image_provider,
    image_provider_restriction,
    open_license_publishable_providers,
    professional_library_compliance_summary,
)
from download.research.source_quality import _collection_gate  # noqa: E402
from _common.asset_placement import _caption_is_degraded, caption_semantic_issues  # noqa: E402
from _common.localization import simplified_chinese_publish_issues  # noqa: E402


# ---------------------------------------------------------------- P4a 分级 + 受限如实标注

def test_p4a_tuchong_pinterest_restricted_with_alternative_path():
    # 图虫：逐图创作者授权后才可发布；如实标注受限，不抓取绕过。
    tuchong = classify_image_provider(source_id="tuchong")
    assert tuchong["accessMode"] == "restricted_creator_authorization"
    assert tuchong["restricted"] is True
    assert tuchong["publishable"] is False

    tuchong_rec = image_provider_restriction(source_id="tuchong")
    assert tuchong_rec is not None
    assert tuchong_rec["bypassAttempted"] is False
    assert tuchong_rec["restrictionKind"] == "creator_authorization_required"
    assert "authorizationProof" in tuchong_rec["requiresProof"]
    assert tuchong_rec["alternativePath"]["strategy"] == "open_license_pools"

    # Pinterest：ToS 仅参考，永不直接发布；如实标注受限，不绕过 ToS/登录墙。
    pinterest = classify_image_provider(platform="Pinterest")
    assert pinterest["accessMode"] == "restricted_reference_only"
    assert pinterest["restricted"] is True
    assert pinterest["publishable"] is False

    pin_rec = image_provider_restriction(source_id="pinterest")
    assert pin_rec is not None
    assert pin_rec["bypassAttempted"] is False
    assert pin_rec["restrictionKind"] == "platform_reference_only"
    assert pin_rec["alternativePath"]["providers"], "替代路径必须给出开放许可图库"


def test_p4a_open_license_providers_publishable():
    # 开放许可来源（替代路径主体）可发布、无受限记录。
    alt_providers = open_license_publishable_providers()
    assert "wikimedia_commons" in alt_providers
    assert "openverse" in alt_providers
    for sid in ("wikimedia_commons", "openverse"):
        info = classify_image_provider(source_id=sid)
        assert info["accessMode"] == "open_license_publishable"
        assert info["publishable"] is True
        assert info["restricted"] is False
        assert image_provider_restriction(source_id=sid) is None


def test_p4a_compliance_summary_is_auditable_and_honest():
    summary = professional_library_compliance_summary()
    assert summary["policy"] == "registry_rights_policy_single_source"
    assert summary["bypassAttempted"] is False
    restricted_ids = {rec["sourceId"] for rec in summary["restrictedProviders"]}
    assert {"tuchong", "pinterest"} <= restricted_ids
    # 商业图库（如 Getty）同样受限。
    assert "getty_images" in restricted_ids
    # 替代路径稳定指向开放许可图池。
    assert "wikimedia_commons" in summary["alternativePath"]["providers"]


# ---------------------------------------------------------------- P4b 授权完整性硬门

def _tuchong_collection() -> dict:
    return {
        "sourceCollectionId": "图虫-九寨沟-001",
        "creator": "摄影师A",
        "collectionPageUrl": "https://tuchong.com/123/九寨沟/",
        "platform": "图虫",
        "images": [
            {
                "url": "https://photo.tuchong.com/123/九寨沟.jpg",
                "caption": "九寨沟五花海清晨",
                "license": "CC BY 4.0",
                "credit": "摄影师A",
                "sourceUrl": "https://tuchong.com/123/九寨沟/",
                "termsUrl": "https://creativecommons.org/licenses/by/4.0/",
                "authorizationProof": "https://tuchong.com/123/九寨沟/license",
                "usageScope": "app_publish",
            }
        ],
    }


def test_p4b_full_per_image_authorization_passes_gate():
    verdict = _collection_gate(_tuchong_collection(), entity_id="九寨沟")
    assert verdict["passed"], verdict["issues"]


def test_p4b_missing_per_image_authorization_blocks_publish():
    # 缺逐图 authorizationProof：页/集合级授权未传播到每张图 → 不进发布面。
    bad = copy.deepcopy(_tuchong_collection())
    bad["images"][0].pop("authorizationProof")
    verdict = _collection_gate(bad, entity_id="九寨沟")
    assert verdict["passed"] is False
    assert any("authorizationProof" in issue for issue in verdict["issues"]), verdict["issues"]


def test_p4b_unsupported_license_blocks_publish():
    # NC/ND 非自由许可不进发布面（与图库平台名无关，按逐资产权利判定）。
    bad = copy.deepcopy(_tuchong_collection())
    bad["images"][0]["license"] = "CC BY-NC 4.0"
    bad["images"][0]["termsUrl"] = "https://creativecommons.org/licenses/by-nc/4.0/"
    verdict = _collection_gate(bad, entity_id="九寨沟")
    assert verdict["passed"] is False


# ---------------------------------------------------------------- P4c 非中文译简体门

def test_p4c_non_chinese_image_caption_blocked():
    # 英文/拉丁主导 caption 退化（须先译简体中文）。
    assert _caption_is_degraded("Jiuzhaigou Valley National Park scenic area")
    # 中文 caption 合格。
    assert not _caption_is_degraded("九寨沟五花海清晨的倒影")

    issues = caption_semantic_issues(
        [{"assetId": "a1", "caption": "Jiuzhaigou Valley National Park", "fileName": "x.jpg"}]
    )
    assert issues, "英文 caption 必须被阻断"
    ok = caption_semantic_issues(
        [{"assetId": "a2", "caption": "九寨沟五花海清晨", "fileName": "y.jpg"}]
    )
    assert not ok


def test_p4c_non_chinese_title_blocked_for_publish():
    issues = simplified_chinese_publish_issues(
        title="Jiuzhaigou Valley Travel Guide", body="九寨沟清晨抵达五花海，水色清澈。"
    )
    assert any("标题" in issue for issue in issues), issues
    clean = simplified_chinese_publish_issues(
        title="九寨沟旅行攻略", body="九寨沟清晨抵达五花海，水色清澈。"
    )
    assert not clean


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"image provider compliance tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
