"""P4 图库 acquisition/rights 分轨与非中文译简体门。

- P4a：图虫可通过受治理公开直链、支持 API 或人工文件取得研究素材；Pinterest
  只允许支持 API 或人工文件，禁止 public_direct；取得不等于授权，provider 分类
  不得伪造逐资产 rightsStatus。
- P4b：research 记录权利缺口但不因未验证而阻断；commercial/enforce 保持硬门。
- P4c 非中文图片元数据门：英文/拉丁主导 caption / 标题须先译简体中文，否则阻断发布。

可直接运行：python3 quwoquan_data/tests/local_contract/core/test_image_provider_compliance__behavior__functional__local_contract_test.py
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


from content.source.research.image_provider_compliance import (  # noqa: E402
    classify_image_provider,
    image_provider_restriction,
    open_license_publishable_providers,
    professional_library_compliance_summary,
)
from content.source.research.source_quality import _collection_gate  # noqa: E402
from core.asset_placement import caption_is_degraded, caption_semantic_issues  # noqa: E402
from core.localization import simplified_chinese_publish_issues  # noqa: E402


# ---------------------------------------------------------------- P4a 分级 + 受限如实标注

def test_p4a_tuchong_and_pinterest_have_governed_research_acquisition_paths():
    tuchong = classify_image_provider(source_id="tuchong")
    assert tuchong["accessMode"] == "creator_authorization_conditional"
    assert tuchong["researchEligible"] is True
    assert tuchong["commercialEvidenceRequired"] is True
    assert set(tuchong["acquisitionPaths"]) == {
        "public_direct", "supported_api", "manual_file"
    }
    assert image_provider_restriction(source_id="tuchong") is None

    pinterest = classify_image_provider(platform="Pinterest")
    assert pinterest["accessMode"] == "attribution_conditional"
    assert pinterest["researchEligible"] is True
    assert pinterest["commercialEvidenceRequired"] is True
    assert set(pinterest["acquisitionPaths"]) == {
        "supported_api", "manual_file"
    }
    assert "public_direct" not in pinterest["acquisitionPaths"]
    assert image_provider_restriction(source_id="pinterest") is None


def test_p4a_open_license_providers_publishable():
    # 开放许可来源（替代路径主体）可发布、无受限记录。
    alt_providers = open_license_publishable_providers()
    assert "wikimedia_commons" in alt_providers
    assert "openverse" in alt_providers
    for sid in ("wikimedia_commons", "openverse"):
        info = classify_image_provider(source_id=sid)
        assert info["accessMode"] == "open_license_conditional"
        assert info["researchEligible"] is True
        assert info["restricted"] is False
        assert image_provider_restriction(source_id=sid) is None


def test_p4a_compliance_summary_is_auditable_and_honest():
    summary = professional_library_compliance_summary()
    assert summary["policy"] == "acquisition_separate_from_distribution_rights"
    assert summary["bypassAttempted"] is False
    eligible_ids = {rec["sourceId"] for rec in summary["researchEligibleProviders"]}
    blocked_ids = {rec["sourceId"] for rec in summary["acquisitionBlockedProviders"]}
    assert {"pinterest", "tuchong", "wikimedia_commons", "openverse"} <= eligible_ids
    assert "xiaohongshu_travel_reference" in blocked_ids


# ---------------------------------------------------------------- P4b 授权审计与垂类执行策略

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
                "modelReleaseStatus": "not_required",
            }
        ],
    }


def test_p4b_full_per_image_authorization_passes_gate():
    verdict = _collection_gate(
        _tuchong_collection(), entity_id="九寨沟", vertical="travel"
    )
    assert verdict["passed"], verdict["issues"]


def test_p4b_missing_authorization_is_audited_not_blocked_during_acquisition():
    bad = copy.deepcopy(_tuchong_collection())
    bad["images"][0].pop("authorizationProof")
    verdict = _collection_gate(bad, entity_id="九寨沟", vertical="travel")
    assert verdict["passed"] is True
    assert verdict["rightsAuditStatus"] == "unverified"
    assert any("authorizationProof" in issue for issue in verdict["rightsAuditIssues"])


def test_p4b_unsupported_license_is_audited_not_blocked_during_acquisition():
    bad = copy.deepcopy(_tuchong_collection())
    bad["images"][0]["license"] = "CC BY-NC 4.0"
    bad["images"][0]["termsUrl"] = "https://creativecommons.org/licenses/by-nc/4.0/"
    verdict = _collection_gate(bad, entity_id="九寨沟", vertical="travel")
    assert verdict["passed"] is True
    assert verdict["rightsAuditStatus"] == "unverified"
    assert verdict["rightsAuditIssues"]


def test_p4b_release_class_is_not_inferred_from_vertical_name():
    bad = copy.deepcopy(_tuchong_collection())
    bad["images"][0].pop("authorizationProof")
    verdict = _collection_gate(bad, entity_id="九寨沟", vertical="photography")
    assert verdict["passed"] is True
    assert verdict["rightsAuditStatus"] == "unverified"
    assert any("authorizationProof" in issue for issue in verdict["rightsAuditIssues"])


# ---------------------------------------------------------------- P4c 非中文译简体门

def test_p4c_non_chinese_image_caption_blocked():
    # 英文/拉丁主导 caption 退化（须先译简体中文）。
    assert caption_is_degraded("Jiuzhaigou Valley National Park scenic area")
    # 中文 caption 合格。
    assert not caption_is_degraded("九寨沟五花海清晨的倒影")

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
