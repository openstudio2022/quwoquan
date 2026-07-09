"""publish 质量元数据沉淀 + 对比替换门契约。

覆盖：
- collect_entity_quality_evidence 从过程证据（2.quality/5.review）提炼 quality 节；
- quality_rank_key / should_replace_published_entity 的「新版不劣才覆盖」语义；
- promote 实体通道：劣于已发布 → 跳过并记 publish_compare 证据；不劣 → 覆盖并沉淀 quality；
- mandatory 重做无旁路：同一通道同一对比门。
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

import json

from _common.publish_quality import (  # noqa: E402
    collect_entity_quality_evidence,
    quality_rank_key,
    read_published_entity_quality,
    should_replace_published_entity,
    write_entity_quality_into_manifest,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _seed_entity_object(
    root: Path,
    *,
    platform: str = "wikipedia",
    authority_rank: int = 0,
    fact_count: int = 12,
    fetch_score: float = 3.5,
    decision: str = "approved",
) -> Path:
    entity_dir = root / "entities" / "地点" / "景区" / "黄龙"
    entity_dir.mkdir(parents=True, exist_ok=True)
    (entity_dir / "page.md").write_text("# 黄龙\n\n五彩池。\n", encoding="utf-8")
    _write_json(entity_dir / "_entity.json", {"label": "黄龙", "domain": "地点", "type": "景区"})
    _write_json(entity_dir / "manifest.json", {"schemaVersion": "quwoquan_data.entity_manifest", "assets": []})
    _write_json(
        entity_dir / "2.quality" / "quality_analysis.json",
        {
            "recommendation": "proceed",
            "baseDraft": {
                "sourceRef": "sources/黄龙__home_wikipedia__ab12cd34/source.md",
                "primarySource": {
                    "platform": platform,
                    "sourceKind": "home_wikipedia",
                    "authorityRank": authority_rank,
                    "factCount": fact_count,
                    "fetchScore": fetch_score,
                },
            },
            "candidates": [],
            "sourcePaths": ["sources/黄龙__home_wikipedia__ab12cd34/source.md"],
        },
    )
    _write_json(entity_dir / "5.review" / "review.json", {"decision": decision, "checks": {}})
    return entity_dir


def test_collect_quality_evidence_from_stage_files(tmp_path):
    entity_dir = _seed_entity_object(tmp_path, authority_rank=1, fact_count=9, fetch_score=2.5)
    quality = collect_entity_quality_evidence(
        entity_dir, source_task_id="任务A", source_batch_id="批次1", generated_at="2026-07-01T00:00:00Z"
    )
    assert quality["primarySource"]["platform"] == "wikipedia"
    assert quality["primarySource"]["authorityRank"] == 1
    assert quality["factCount"] == 9
    assert quality["fetchScore"] == 2.5
    assert quality["reviewDecision"] == "approved"
    assert quality["generatedAt"] == "2026-07-01T00:00:00Z"
    assert quality["sourceTaskId"] == "任务A"


def test_collect_quality_falls_back_to_manifest_quality_when_no_stages(tmp_path):
    """release 树只拷成品：过程阶段缺失时读取自带 manifest.quality。"""
    entity_dir = tmp_path / "entities" / "地点" / "景区" / "武侯祠"
    entity_dir.mkdir(parents=True)
    baked = {
        "schemaVersion": "quwoquan_data.publish_entity_quality/1",
        "primarySource": {"platform": "wikipedia", "authorityRank": 0},
        "factCount": 7,
        "fetchScore": 1.0,
        "reviewDecision": "approved",
        "generatedAt": "2026-06-30T00:00:00Z",
    }
    _write_json(entity_dir / "manifest.json", {"quality": baked})
    quality = collect_entity_quality_evidence(entity_dir)
    assert quality["factCount"] == 7
    assert quality["primarySource"]["authorityRank"] == 0


def test_rank_key_orders_authority_then_facts_then_score_then_time():
    def q(rank, facts, score, ts):
        return {
            "primarySource": {"authorityRank": rank},
            "factCount": facts,
            "fetchScore": score,
            "generatedAt": ts,
        }

    # authorityRank 越小越权威 → key 越大。
    assert quality_rank_key(q(0, 5, 1.0, "a")) > quality_rank_key(q(1, 99, 9.0, "z"))
    # 同权威比 factCount。
    assert quality_rank_key(q(1, 10, 1.0, "a")) > quality_rank_key(q(1, 9, 9.0, "z"))
    # 同权威同事实数比 fetch score。
    assert quality_rank_key(q(1, 10, 2.0, "a")) > quality_rank_key(q(1, 10, 1.0, "z"))
    # 全同比生成时间（ISO 字典序）。
    assert quality_rank_key(q(1, 10, 1.0, "2026-07-02")) > quality_rank_key(q(1, 10, 1.0, "2026-07-01"))
    # 缺 quality 节视为最低。
    assert quality_rank_key(q(20, 0, 0.0, "")) > quality_rank_key(None)


def test_should_replace_equal_quality_allows_idempotent_rerun():
    q = {
        "primarySource": {"authorityRank": 1},
        "factCount": 5,
        "fetchScore": 1.0,
        "generatedAt": "2026-07-01",
    }
    assert should_replace_published_entity(q, dict(q)) is True


def test_promote_entities_skips_inferior_and_records_compare(tmp_path, monkeypatch):
    """端到端：已发布高权威实体不被低权威新批覆盖；反向则覆盖并沉淀 quality。"""
    import importlib

    import publish_ops.promote_to_publish as promote_mod

    promote_mod = importlib.reload(promote_mod)
    publish_root = tmp_path / "publish"
    monkeypatch.setattr(promote_mod, "PUBLISH_ROOT", publish_root)

    # 先发布一个高权威版本（authorityRank=0, factCount=12）。
    strong_src = _seed_entity_object(tmp_path / "strong", authority_rank=0, fact_count=12)
    strong_quality = collect_entity_quality_evidence(strong_src, generated_at="2026-07-01T00:00:00Z")
    published_dir = publish_root / "entities" / "地点" / "景区" / "黄龙"
    promote_mod._copy_entity_into_publish(strong_src, published_dir, strong_quality)
    assert read_published_entity_quality(published_dir)["factCount"] == 12

    # 低权威新批（authorityRank=5, factCount=4）→ 对比门必须拒绝。
    weak_src = _seed_entity_object(tmp_path / "weak", authority_rank=5, fact_count=4)
    weak_quality = collect_entity_quality_evidence(weak_src, generated_at="2026-07-02T00:00:00Z")
    replace, record = promote_mod._entity_compare_verdict("地点/景区/黄龙", published_dir, weak_quality)
    assert replace is False
    assert record["decision"] == "skip_inferior"

    # 更强新批（同权威、更多事实）→ 放行覆盖。
    better_src = _seed_entity_object(tmp_path / "better", authority_rank=0, fact_count=15)
    better_quality = collect_entity_quality_evidence(better_src, generated_at="2026-07-03T00:00:00Z")
    replace, record = promote_mod._entity_compare_verdict("地点/景区/黄龙", published_dir, better_quality)
    assert replace is True
    promote_mod._copy_entity_into_publish(better_src, published_dir, better_quality)
    assert read_published_entity_quality(published_dir)["factCount"] == 15

    # compare 证据落盘。
    report_path = promote_mod._flush_compare_report("测试来源")
    assert report_path is not None and report_path.is_file()
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    decisions = {row["decision"] for row in payload["decisions"]}
    assert {"skip_inferior", "replace"} <= decisions


def test_mandatory_redo_goes_through_same_compare_gate():
    """mandatory 点名重做无旁路：promote 实体通道只有一个对比门实现。"""
    import inspect

    import publish_ops.promote_to_publish as promote_mod

    src = inspect.getsource(promote_mod.promote_task_entities)
    assert "_entity_compare_verdict" in src, "promote_task_entities 必须走对比门"
    assert "mandatory" not in src.casefold(), "禁止 mandatory 旁路分支"
    src_release = inspect.getsource(promote_mod._promote_entities_from_root)
    assert "_entity_compare_verdict" in src_release, "release 实体通道必须走同一对比门"


def test_write_quality_into_manifest_preserves_existing_fields(tmp_path):
    entity_dir = tmp_path / "e"
    entity_dir.mkdir()
    _write_json(entity_dir / "manifest.json", {"assets": [{"assetId": "x"}], "entityRef": "/entity/地点/景区/黄龙"})
    write_entity_quality_into_manifest(entity_dir, {"factCount": 3})
    manifest = json.loads((entity_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["assets"] == [{"assetId": "x"}]
    assert manifest["entityRef"] == "/entity/地点/景区/黄龙"
    assert manifest["quality"]["factCount"] == 3
