"""P4 图库合规契约：来源分类、垂类权利策略与非中文译简体门。

- P4a 图库分级：registry rightsPolicy 为唯一真相源；图虫=逐图创作者授权、Pinterest=归因无水印发布，
  受限来源如实标注 restricted + bypassAttempted=false；Pinterest 必须逐图归因与扫描证据完整；Commons/Openverse 可发布。
- P4b 垂类权利策略：travel 冷启动记录审计状态但不按许可过滤；enforce 垂类保持授权硬门。
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
from core.asset_placement import _caption_is_degraded, caption_semantic_issues  # noqa: E402
from core.localization import simplified_chinese_publish_issues  # noqa: E402


# ---------------------------------------------------------------- P4a 分级 + 受限如实标注

def test_p4a_tuchong_restricted_pinterest_attribution_publishable():
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

    # Pinterest：走 attribution_no_watermark 正式权利模型后，可在逐图证据完整时进入发布候选。
    pinterest = classify_image_provider(platform="Pinterest")
    assert pinterest["accessMode"] == "attribution_publishable"
    assert pinterest["restricted"] is False
    assert pinterest["publishable"] is True
    assert image_provider_restriction(source_id="pinterest") is None


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
    assert "tuchong" in restricted_ids
    assert "pinterest" not in restricted_ids
    assert "pinterest" in set(summary["publishableProviders"])
    # 商业图库（如 Getty）同样受限。
    assert "getty_images" in restricted_ids
    # 替代路径稳定指向开放许可图池。
    assert "wikimedia_commons" in summary["alternativePath"]["providers"]


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


def test_p4b_travel_missing_authorization_is_blocked():
    bad = copy.deepcopy(_tuchong_collection())
    bad["images"][0].pop("authorizationProof")
    verdict = _collection_gate(bad, entity_id="九寨沟", vertical="travel")
    assert verdict["passed"] is False
    assert verdict["rightsAuditStatus"] == "unverified"
    assert any("authorizationProof" in issue for issue in verdict["rightsAuditIssues"])


def test_p4b_travel_unsupported_license_is_blocked():
    bad = copy.deepcopy(_tuchong_collection())
    bad["images"][0]["license"] = "CC BY-NC 4.0"
    bad["images"][0]["termsUrl"] = "https://creativecommons.org/licenses/by-nc/4.0/"
    verdict = _collection_gate(bad, entity_id="九寨沟", vertical="travel")
    assert verdict["passed"] is False
    assert verdict["rightsAuditStatus"] == "unverified"
    assert verdict["rightsAuditIssues"]


def test_p4b_enforced_vertical_still_blocks_incomplete_rights():
    bad = copy.deepcopy(_tuchong_collection())
    bad["images"][0].pop("authorizationProof")
    verdict = _collection_gate(bad, entity_id="九寨沟", vertical="photography")
    assert verdict["passed"] is False
    assert any("authorizationProof" in issue for issue in verdict["issues"])


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
