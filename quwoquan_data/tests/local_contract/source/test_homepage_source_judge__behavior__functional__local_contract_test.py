"""homepage_source_judge local_contract：预筛硬证据 / verdict schema / fail-closed 准入。

回归背书（S100 舟山批次实测问题）：
- 东沙古镇的 primary 底稿实为维基「岱山县」页（父级行政区替代页）；
- 摩星山（岱山）的 official 来源是 daishan.gov.cn 门户首页；
- 灰区来源（标题证据与实体不完全一致）必须 fail-closed 等待模型 verdict。
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from core.homepage_source_judge import (  # noqa: E402
    ADMISSION_PENDING_JUDGE,
    ADMISSION_PRIMARY,
    ADMISSION_REJECT,
    ENTITY_PAGE_FAILURE_SCHEMA_VERSION,
    PRESCREEN_AUTO_PRIMARY,
    PRESCREEN_AUTO_REJECT,
    PRESCREEN_NEEDS_MODEL,
    SOURCE_JUDGE_SCHEMA_VERSION,
    SOURCE_JUDGE_VERDICT_FILE,
    build_judge_request,
    deterministic_prescreen,
    entity_page_failure_issues,
    judge_verdict_issues,
    render_judge_prompt,
    source_judge_admission,
)

_WIKI_ENC_META = {
    "sourceKind": "encyclopedia",
    "platform": "维基百科",
    "url": "https://zh.wikipedia.org/wiki/%E7%A7%80%E5%B1%B1%E5%B2%9B",
}


def test_prescreen_exact_wiki_slug_auto_primary() -> None:
    result = deterministic_prescreen(entity_name="秀山岛", meta=_WIKI_ENC_META)
    assert result["decision"] == PRESCREEN_AUTO_PRIMARY
    assert result["entityMatch"] == "exact"


def test_prescreen_rejects_wiki_redirect_to_different_entity() -> None:
    meta = {
        "sourceKind": "encyclopedia",
        "platform": "维基百科",
        "url": "https://zh.wikipedia.org/wiki/%E5%8D%97%E9%9B%81%E8%8D%A1%E5%B1%B1",
        "resolvedTitle": "雁荡山",
        "redirectChain": ["南雁荡山 -> 雁荡山"],
    }
    result = deterministic_prescreen(entity_name="南雁荡山", meta=meta)
    assert result["decision"] == PRESCREEN_AUTO_REJECT
    assert result["sourcePageType"] == "other_entity"
    assert result["matchedTitle"] == "雁荡山"


def test_prescreen_site_suffix_title_auto_primary() -> None:
    meta = {"sourceKind": "encyclopedia", "title": "东极岛 - 维基百科，自由的百科全书", "url": ""}
    result = deterministic_prescreen(entity_name="东极岛", meta=meta)
    assert result["decision"] == PRESCREEN_AUTO_PRIMARY


def test_prescreen_parent_admin_region_auto_reject() -> None:
    # 东沙古镇的底稿实为「岱山县」页：父级行政区替代页必须确定性拒绝。
    meta = {
        "sourceKind": "encyclopedia",
        "platform": "维基百科",
        "url": "https://zh.wikipedia.org/wiki/%E5%B2%B1%E5%B1%B1%E5%8E%BF",
    }
    result = deterministic_prescreen(entity_name="东沙古镇", meta=meta)
    assert result["decision"] == PRESCREEN_AUTO_REJECT
    assert result["sourcePageType"] == "parent_region_overview"


def test_prescreen_portal_root_url_auto_reject() -> None:
    meta = {"sourceKind": "official", "platform": "政府", "url": "https://www.daishan.gov.cn/"}
    result = deterministic_prescreen(entity_name="摩星山（岱山）", meta=meta)
    assert result["decision"] == PRESCREEN_AUTO_REJECT
    assert result["sourcePageType"] == "portal_home"


def test_prescreen_gray_zone_needs_model() -> None:
    # 东沙角与东沙古镇共享前缀但非同一实体：不可确定性裁决，交模型。
    meta = {
        "sourceKind": "encyclopedia",
        "platform": "维基百科",
        "url": "https://zh.wikipedia.org/wiki/%E4%B8%9C%E6%B2%99%E8%A7%92",
    }
    result = deterministic_prescreen(entity_name="东沙古镇", meta=meta)
    assert result["decision"] == PRESCREEN_NEEDS_MODEL


def _valid_verdict(entity: str = "东沙古镇") -> dict:
    return {
        "schemaVersion": SOURCE_JUDGE_SCHEMA_VERSION,
        "targetEntity": entity,
        "sourcePageType": "entity_homepage",
        "entityMatch": "exact",
        "primaryEligible": True,
        "recommendedAction": "primary",
        "confidence": 0.9,
        "reasons": ["正文围绕东沙古镇本体展开"],
        "evidence": [{"field": "headText", "quote": "东沙古镇位于岱山岛西北端"}],
    }


def test_verdict_schema_validation() -> None:
    assert judge_verdict_issues(_valid_verdict(), entity_name="东沙古镇") == []
    # primary 的组合约束：低置信 / 非主页类型 / mismatch 一律拒绝。
    low_conf = {**_valid_verdict(), "confidence": 0.5}
    assert any("confidence" in issue for issue in judge_verdict_issues(low_conf, entity_name="东沙古镇"))
    wrong_type = {**_valid_verdict(), "sourcePageType": "parent_region_overview"}
    assert any("sourcePageType" in issue for issue in judge_verdict_issues(wrong_type, entity_name="东沙古镇"))
    stale_target = _valid_verdict("岱山县")
    assert any("targetEntity" in issue for issue in judge_verdict_issues(stale_target, entity_name="东沙古镇"))
    no_evidence = {**_valid_verdict(), "evidence": []}
    assert any("evidence" in issue for issue in judge_verdict_issues(no_evidence, entity_name="东沙古镇"))


def test_admission_gray_zone_fail_closed_then_verdict_wins() -> None:
    meta = {
        "sourceKind": "encyclopedia",
        "platform": "维基百科",
        "url": "https://zh.wikipedia.org/wiki/%E4%B8%9C%E6%B2%99%E8%A7%92",
    }
    with tempfile.TemporaryDirectory() as tmp:
        unit_dir = Path(tmp)
        pending = source_judge_admission(
            entity_name="东沙古镇", meta=meta, source_text="东沙角是岱山县的一个大型居民区……", unit_dir=unit_dir
        )
        assert pending["decision"] == ADMISSION_PENDING_JUDGE
        # Agent 写回 reject verdict → 准入拒绝。
        reject_verdict = {
            **_valid_verdict(),
            "sourcePageType": "other_entity",
            "entityMatch": "mismatch",
            "primaryEligible": False,
            "recommendedAction": "reject",
            "reasons": ["页面主体是东沙角居民区，不是东沙古镇"],
        }
        (unit_dir / SOURCE_JUDGE_VERDICT_FILE).write_text(
            json.dumps(reject_verdict, ensure_ascii=False), encoding="utf-8"
        )
        rejected = source_judge_admission(
            entity_name="东沙古镇", meta=meta, source_text="……", unit_dir=unit_dir
        )
        assert rejected["decision"] == ADMISSION_REJECT
        # 换成合法 primary verdict → 准入通过。
        (unit_dir / SOURCE_JUDGE_VERDICT_FILE).write_text(
            json.dumps(_valid_verdict(), ensure_ascii=False), encoding="utf-8"
        )
        accepted = source_judge_admission(
            entity_name="东沙古镇", meta=meta, source_text="……", unit_dir=unit_dir
        )
        assert accepted["decision"] == ADMISSION_PRIMARY
        assert accepted["verdictSource"] == "verdict"


def test_admission_encyclopedia_without_title_evidence_trusted() -> None:
    # 离线 fixture（无 URL/标题证据）的百科来源沿用 registry 权威信任，不强制模型判别。
    meta = {"sourceKind": "encyclopedia", "platform": "维基百科", "url": ""}
    result = source_judge_admission(entity_name="测试景区", meta=meta, source_text="正文")
    assert result["decision"] == ADMISSION_PRIMARY
    assert result["verdictSource"] == "prescreen_encyclopedia_trust"


def test_judge_request_and_prompt_render() -> None:
    meta = {
        "sourceKind": "official",
        "platform": "政府",
        "url": "https://www.daishan.gov.cn/art/2024/1/1/art_123.html",
    }
    prescreen = deterministic_prescreen(entity_name="摩星山（岱山）", meta=meta)
    request = build_judge_request(
        entity_name="摩星山（岱山）",
        entity_type="地点/自然景观",
        meta=meta,
        source_text="摩星山景区位于岱山岛东南部……",
        unit_ref="sources/摩星山__official__x/source.md",
        prescreen=prescreen,
    )
    assert request["schemaVersion"] == SOURCE_JUDGE_SCHEMA_VERSION
    assert request["source"]["headText"].startswith("摩星山景区")
    prompt = render_judge_prompt(request)
    assert "摩星山（岱山）" in prompt
    assert "source.judge.json" in prompt
    assert "entity_homepage" in prompt  # 闭集枚举在 system 输出契约中


def test_entity_page_failure_schema() -> None:
    failure = {
        "schemaVersion": ENTITY_PAGE_FAILURE_SCHEMA_VERSION,
        "targetEntity": "东沙古镇",
        "failureKind": "source_entity_mismatch",
        "reasons": ["底稿是岱山县整县概况"],
        "evidence": [{"field": "baseDraft", "quote": "岱山县，隶属浙江省舟山市"}],
    }
    assert entity_page_failure_issues(failure, entity_name="东沙古镇") == []
    bad_kind = {**failure, "failureKind": "whatever"}
    assert any("failureKind" in issue for issue in entity_page_failure_issues(bad_kind, entity_name="东沙古镇"))
    wrong_entity = {**failure, "targetEntity": "岱山县"}
    assert any("targetEntity" in issue for issue in entity_page_failure_issues(wrong_entity, entity_name="东沙古镇"))


def _run() -> None:
    test_prescreen_exact_wiki_slug_auto_primary()
    test_prescreen_rejects_wiki_redirect_to_different_entity()
    test_prescreen_site_suffix_title_auto_primary()
    test_prescreen_parent_admin_region_auto_reject()
    test_prescreen_portal_root_url_auto_reject()
    test_prescreen_gray_zone_needs_model()
    test_verdict_schema_validation()
    test_admission_gray_zone_fail_closed_then_verdict_wins()
    test_admission_encyclopedia_without_title_evidence_trusted()
    test_judge_request_and_prompt_render()
    test_entity_page_failure_schema()
    print("OK: homepage source judge contract passed")


if __name__ == "__main__":
    _run()
