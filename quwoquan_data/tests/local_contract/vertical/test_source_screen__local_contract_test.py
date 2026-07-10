"""排产前 sourceScreen 深核验（source_screen）合约测试。

覆盖 GWT2（前置核验与折扣率出数）的本地契约面：
- 深核验口径：消歧义页/正文过短不算 ready；实质正文达标才 ready。
- 三态回写：ready 降级 no_primary_source 带时间戳与证据；不结论（网络/反爬）
  不回写不打时间戳（防误降级/陈旧定格）。
- 折扣率：readyBefore/readyConfirmed 比值出数；扩源缺口清单逐项归因。
- 新鲜期：sourceScreenedAt 在 max_age_days 内跳过重验。
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

import tempfile
from datetime import datetime, timedelta, timezone

import yaml

import vertical.source_screen as mod  # noqa: E402
from vertical.source_screen import (  # noqa: E402
    _screen_is_fresh,
    screen_leaf,
    screen_master_list_sources,
)


class _FakeBridge:
    """按词条脚本化的 wiki/baidu 探测桩。"""

    def __init__(self, wiki_pages: dict[str, dict], baidu_text: dict[str, str] | None = None):
        self.wiki_pages = wiki_pages
        self.baidu_text = baidu_text or {}

    def _wiki_api(self, host: str, params: dict) -> dict:
        term = str(params.get("titles") or "")
        page = self.wiki_pages.get(term)
        if page is None:
            return {"query": {"pages": {"-1": {"missing": ""}}}}
        if page.get("network_error"):
            return {}
        return {"query": {"pages": {"1": {"pageid": 1, "title": term, **page}}}}

    def _curl_text(self, url: str, *, timeout: int = 15) -> str:
        import urllib.parse

        term = urllib.parse.unquote(url.rsplit("/", 1)[-1])
        return self.baidu_text.get(term, "抱歉，您所访问的页面不存在")


def test_screen_leaf_requires_substantive_extract():
    # 正文达标 → ready
    bridge = _FakeBridge({"普陀山": {"extract": "普" * 300}})
    verdict = screen_leaf({"canonicalName": "普陀山"}, sleep_seconds=0, bridge=bridge)
    assert verdict["status"] == "ready"
    assert "extract=300ch" in verdict["evidence"]
    # 正文过短 + 百度缺失 → no_primary_source（轻探测口径会误判 ready 的场景）
    bridge = _FakeBridge({"金鹰山荘": {"extract": "短文"}})
    verdict = screen_leaf({"canonicalName": "金鹰山荘"}, sleep_seconds=0, bridge=bridge)
    assert verdict["status"] == "no_primary_source"
    assert "正文过短" in verdict["evidence"]
    # 消歧义页不算主源
    bridge = _FakeBridge({"东湖": {"extract": "东" * 300, "pageprops": {"disambiguation": ""}}})
    verdict = screen_leaf({"canonicalName": "东湖"}, sleep_seconds=0, bridge=bridge)
    assert verdict["status"] == "no_primary_source"
    # 网络不结论 → pending（不误降级）
    bridge = _FakeBridge({"雁荡山": {"network_error": True}})
    verdict = screen_leaf({"canonicalName": "雁荡山"}, sleep_seconds=0, bridge=bridge)
    assert verdict["status"] == "pending"


def test_screen_is_fresh_window():
    now = datetime.now(timezone.utc)
    fresh = {"sourceScreenedAt": now.strftime("%Y-%m-%dT%H:%M:%SZ")}
    stale = {"sourceScreenedAt": (now - timedelta(days=40)).strftime("%Y-%m-%dT%H:%M:%SZ")}
    assert _screen_is_fresh(fresh, max_age_days=30)
    assert not _screen_is_fresh(stale, max_age_days=30)
    assert not _screen_is_fresh({}, max_age_days=30)


def test_screen_master_list_discount_rate_and_writeback(monkeypatch):
    with tempfile.TemporaryDirectory(prefix="qwq_screen_") as tmp:
        tmp_path = Path(tmp)
        city_file = tmp_path / "浙江省" / "舟山市.yaml"
        city_file.parent.mkdir(parents=True)
        city_file.write_text(
            yaml.safe_dump(
                {
                    "schemaVersion": "quwoquan_data.discovery_seed/2",
                    "country": "中国",
                    "province": "浙江省",
                    "city": "舟山市",
                    "districts": [
                        {
                            "district": "普陀区",
                            "leaves": [
                                {
                                    "name": "普陀山",
                                    "canonicalName": "普陀山",
                                    "entityType": "地点/景区",
                                    "typeTagRefs": ["Entity/地点/景区/5A景区"],
                                    "geoTagRef": "Topic/地理/行政区/中国/浙江省/舟山市/普陀区",
                                    "selectionPriority": 1,
                                    "sourceReadiness": "ready",
                                },
                                {
                                    "name": "虚高景点",
                                    "canonicalName": "虚高景点",
                                    "entityType": "地点/打卡地",
                                    "typeTagRefs": ["Entity/地点/打卡地"],
                                    "geoTagRef": "Topic/地理/行政区/中国/浙江省/舟山市/普陀区",
                                    "selectionPriority": 2,
                                    "sourceReadiness": "ready",
                                },
                                {
                                    "name": "断网景点",
                                    "canonicalName": "断网景点",
                                    "entityType": "地点/打卡地",
                                    "typeTagRefs": ["Entity/地点/打卡地"],
                                    "geoTagRef": "Topic/地理/行政区/中国/浙江省/舟山市/普陀区",
                                    "selectionPriority": 3,
                                    "sourceReadiness": "ready",
                                },
                            ],
                        }
                    ],
                },
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        bridge = _FakeBridge(
            {
                "普陀山": {"extract": "普" * 300},
                "虚高景点": {"extract": "短"},
                "断网景点": {"network_error": True},
            }
        )
        monkeypatch.setattr(mod, "_research_bridge", lambda: bridge)
        monkeypatch.setattr(mod, "SCREEN_RUNTIME_DIR", tmp_path / "runtime")
        monkeypatch.setattr(mod, "master_list_files", lambda **kw: [city_file])

        report = screen_master_list_sources(
            provinces=["浙江省"], sleep_seconds=0, only_ready=True
        )
        assert report["readyBefore"] == 3
        assert report["readyConfirmed"] == 1
        assert report["readyDowngraded"] == 1
        assert report["inconclusive"] == 1  # 断网不结论
        assert report["readyDiscountRate"] == round(1 / 3, 4)
        assert len(report["expansionGaps"]) == 1
        assert report["expansionGaps"][0]["canonicalName"] == "虚高景点"

        data = yaml.safe_load(city_file.read_text(encoding="utf-8"))
        leaves = data["districts"][0]["leaves"]
        by_name = {l["canonicalName"]: l for l in leaves}
        assert by_name["普陀山"]["sourceReadiness"] == "ready"
        assert by_name["普陀山"]["sourceScreenedAt"]
        assert by_name["虚高景点"]["sourceReadiness"] == "no_primary_source"
        assert "正文过短" in by_name["虚高景点"]["sourceScreenEvidence"]
        # 不结论：不回写、不打时间戳
        assert by_name["断网景点"]["sourceReadiness"] == "ready"
        assert "sourceScreenedAt" not in by_name["断网景点"]

        # 二跑：新鲜核验跳过（断网叶子仍会重试）
        report2 = screen_master_list_sources(
            provinces=["浙江省"], sleep_seconds=0, only_ready=True
        )
        assert report2["skippedFresh"] == 1  # 普陀山（虚高景点已降级不在 ready scope）
        assert report2["inconclusive"] == 1
