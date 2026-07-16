"""主清单候选合并与发现管线合约测试。

覆盖 GWT1（省级全覆盖口径达成）的本地契约面：
- 去重：候选命中主清单 canonicalName/name/aliases（归一化口径）不重复写回。
- 类型打标保守性：分类等级证据 > OSM tag > 名称规则；全不结论 → 缺口不写回。
- 区县归属：OSM 自带精确归属；wiki 文本唯一命中才结论；跨市州同名区县不误归。
- 写回：dump 后 schema 字段完整（含 selectionPriority 递增），
  保留文件头注释；dry-run 不落盘。
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
import tempfile

import yaml

from governance.coverage.coverage_merge import (  # noqa: E402
    _classify_by_category,
    _classify_by_name,
    _classify_by_osm,
    _resolve_district_from_text,
    merge_candidates,
)
from governance.coverage.coverage_runtime import coverage_workspace_root as _expand_runtime_dir  # noqa: E402
from governance.coverage.coverage_semantics import normalize_name, semantic_rejection_reason as _semantic_rejection_reason  # noqa: E402


def test_expand_runtime_dir_uses_canonical_data_runtime_root(monkeypatch, tmp_path):
    monkeypatch.delenv("QWQ_DATA_ROOT", raising=False)
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path / "output"))

    assert _expand_runtime_dir() == (
        tmp_path / "output" / "data" / "local" / "workspace" / "coverage"
    )


def test_normalize_name_strips_scenic_suffix_variants():
    assert normalize_name("普陀山风景名胜区") == "普陀山"
    assert normalize_name("普陀山景区") == "普陀山"
    assert normalize_name(" 普陀山 ") == "普陀山"
    # 后缀本身即全名时不剥（护栏：len 检查）
    assert normalize_name("景区") == "景区"


def test_classify_priority_category_grade_over_name_rule():
    # 分类等级证据（政府名录镜像）优先：4A 分类 → 景区/4A
    assert _classify_by_category(["Category:浙江省国家4A级旅游景区"]) == (
        "地点/景区",
        "Entity/地点/景区/4A景区",
    )
    assert _classify_by_category(["Category:浙江全国重点文物保护单位"]) == (
        "地点/遗址",
        "Entity/地点/遗址/文化遗产",
    )
    # 名称规则结论性后缀
    assert _classify_by_name("舟山博物馆") == ("地点/博物馆", "Entity/地点/博物馆")
    assert _classify_by_name("普济禅寺") == ("地点/宗教场所", "Entity/地点/宗教场所")
    # 不结论 → None（缺口，交 Agent 语义复核）
    assert _classify_by_name("东极") is None
    # OSM 结论性 tag
    assert _classify_by_osm({"tourism": "museum"}) == ("地点/博物馆", "Entity/地点/博物馆")
    assert _classify_by_osm({"historic": "memorial"}) == ("地点/遗址", "Entity/地点/遗址/历史建筑")
    assert _classify_by_osm({"tourism": "attraction"}) is None


def test_resolve_district_unique_hit_and_cross_city_ambiguity():
    # 唯一命中 → 结论
    assert _resolve_district_from_text(
        "位于浙江省舟山市定海区的历史街区", province="浙江省"
    ) == ("舟山市", "定海区")
    # 四川两个「市中区」（乐山/内江）：无市州线索不结论
    assert _resolve_district_from_text("位于市中区", province="四川省") is None
    # 有市州名先锁 → 正确归属
    assert _resolve_district_from_text(
        "位于四川省乐山市市中区", province="四川省"
    ) == ("乐山市", "市中区")
    # 零命中 → 不结论
    assert _resolve_district_from_text("位于中国东部", province="浙江省") is None


def _write_candidates(path: Path, items: list[dict]) -> Path:
    with path.open("w", encoding="utf-8") as fh:
        for item in items:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")
    return path


def test_merge_dedup_gap_and_apply_writeback(monkeypatch):
    import governance.coverage.coverage_merge as mod

    with tempfile.TemporaryDirectory(prefix="qwq_cov_expand_") as tmp:
        tmp_path = Path(tmp)
        coverage_root = tmp_path / "coverage" / "中国"
        city_file = coverage_root / "浙江省" / "舟山市.yaml"
        city_file.parent.mkdir(parents=True)
        city_file.write_text(
            "# 测试主清单头注释\n"
            + yaml.safe_dump(
                {
                    "schemaVersion": "quwoquan_data.discovery_seed/2",
                    "country": "中国",
                    "province": "浙江省",
                    "city": "舟山市",
                    "districts": [
                        {
                            "district": "定海区",
                            "leaves": [
                                {
                                    "name": "定海古城",
                                    "canonicalName": "定海古城",
                                    "entityType": "地点/古镇",
                                    "typeTagRefs": ["Entity/地点/古镇/历史古镇"],
                                    "geoTagRef": "Topic/地理/行政区/中国/浙江省/舟山市/定海区",
                                    "aliases": ["定海老城"],
                                    "selectionPriority": 2,
                                }
                            ],
                        }
                    ],
                },
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(mod, "COVERAGE_MASTER_ROOT", coverage_root)
        monkeypatch.setattr(mod, "coverage_workspace_root", lambda: tmp_path / "runtime")
        # master_list_files/_existing_name_index 消费 coverage_root 参数注入
        monkeypatch.setattr(
            mod,
            "master_list_files",
            lambda **kw: [city_file],
        )

        candidates = _write_candidates(
            tmp_path / "cands.ndjson",
            [
                # 1) 仅别名、无稳定 ID/区县坐标：禁止猜 identity，进入缺口。
                {"name": "定海老城", "province": "浙江省", "source": "wiki_category", "categories": [], "extract": ""},
                # 2) OSM 只能定位；同 QID 的 wiki 非 OSM 证据完成准入 → 写回
                {
                    "name": "灯塔博物馆",
                    "province": "浙江省",
                    "city": "舟山市",
                    "district": "定海区",
                    "source": "osm_poi",
                    "identityRefs": {"qid": "Q123", "osmType": "way", "osmId": "123"},
                    "coordinates": {"lat": 30.0, "lon": 120.0},
                    "osmTags": {"tourism": "museum"},
                    "osmType": "way",
                },
                {
                    "name": "灯塔博物馆",
                    "province": "浙江省",
                    "source": "wiki_category",
                    "identityRefs": {"qid": "Q123", "wikipediaPageId": 456},
                    "categories": ["Category:浙江省的博物馆"],
                    "extract": "灯塔博物馆位于浙江省舟山市定海区。",
                },
                # 3) 即使名称可分类，OSM-only 仍只进缺口
                {
                    "name": "东福山",
                    "province": "浙江省",
                    "city": "舟山市",
                    "district": "普陀区",
                    "source": "osm_poi",
                    "identityRefs": {"osmType": "node", "osmId": "999"},
                    "coordinates": {"lat": 30.1, "lon": 122.1},
                    "osmTags": {"tourism": "attraction"},
                    "osmType": "node",
                },
            ],
        )
        report = merge_candidates(
            ["浙江省"], candidate_files=[candidates], apply=False
        )
        assert report["duplicatesAgainstMaster"] == 0
        assert report["appended"] == 1
        assert report["gaps"] == 2
        assert report["osmOnlyRejected"] == 1
        assert report["identityUnresolved"] == 1
        # dry-run 不写回
        text_before = city_file.read_text(encoding="utf-8")
        assert "灯塔博物馆" not in text_before

        report2 = merge_candidates(
            ["浙江省"], candidate_files=[candidates], apply=True
        )
        assert report2["appended"] == 1
        text_after = city_file.read_text(encoding="utf-8")
        assert text_after.startswith("# 测试主清单头注释")
        data = yaml.safe_load(text_after)
        by_district = {g["district"]: g["leaves"] for g in data["districts"]}
        dinghai = by_district["定海区"]
        added = [l for l in dinghai if l["canonicalName"] == "灯塔博物馆"]
        assert added and added[0]["entityType"] == "地点/博物馆"
        assert added[0]["identityRefs"]["qid"] == "Q123"
        assert added[0]["discoverySources"] == ["osm_poi", "wiki_category"]
        assert set(added[0]) == {
            "name",
            "canonicalName",
            "entityType",
            "geoTagRef",
            "typeTagRefs",
            "identityRefs",
            "coordinates",
            "discoverySources",
            "selectionPriority",
        }
        assert added[0]["selectionPriority"] == 3  # 现有 max=2 → 3
        assert "普陀区" not in by_district


def test_wiki_category_members_keeps_ns0_pages_and_ns14_subcats():
    """ns=0（条目主命名空间）是 falsy：禁止 `int(x or -1)` 兜底把全部条目丢弃。

    2026-07-09 生产回归：两省 discover 批 wiki_category 全程 0 条目产出，
    根因即该 falsy 陷阱（子分类 ns=14 truthy 不受影响，掩盖了问题）。
    """
    import governance.coverage.coverage_discovery as mod

    class _Bridge:
        @staticmethod
        def wiki_api(host, params):
            return {
                "query": {
                    "categorymembers": [
                        {"ns": 0, "title": "西湖", "pageid": 1},
                        {"ns": 0, "title": "灵隐寺", "pageid": 2},
                        {"ns": 14, "title": "Category:杭州园林", "pageid": 3},
                    ]
                }
            }

    pages, subcats = mod._wiki_category_members(_Bridge(), "Category:杭州旅游景点")
    assert pages == ["西湖", "灵隐寺"], "ns=0 条目页必须保留"
    assert subcats == ["Category:杭州园林"]


def test_wiki_api_with_retry_backs_off_on_empty_response(monkeypatch):
    """限流返回空体时必须退避重试，不得静默空产。"""
    import governance.coverage.coverage_discovery as mod

    responses = iter([{}, {}, {"query": {"categorymembers": []}}])
    calls = {"n": 0}

    class _Bridge:
        @staticmethod
        def wiki_api(host, params):
            calls["n"] += 1
            return next(responses)

    sleeps: list[float] = []
    monkeypatch.setattr(mod.time, "sleep", sleeps.append)
    data = mod._wiki_api_with_retry(_Bridge(), "zh.wikipedia.org", {}, retries=3, backoff_seconds=5.0)
    assert calls["n"] == 3
    assert sleeps == [5.0, 10.0], "指数退避"
    assert data == {"query": {"categorymembers": []}}


def test_overpass_query_distinguishes_empty_result_from_failure(monkeypatch):
    """空 elements=[]（真空区县）ok=True；无 elements（限流/失败）重试后 ok=False。"""
    import governance.coverage.coverage_discovery as mod

    monkeypatch.setattr(mod.time, "sleep", lambda s: None)

    class _OkBridge:
        @staticmethod
        def curl_json(url, timeout=90):
            return {"elements": []}

    elements, ok = mod._overpass_query(_OkBridge(), "q")
    assert ok is True and elements == []

    class _FailBridge:
        calls = 0

        @classmethod
        def curl_json(cls, url, timeout=90):
            cls.calls += 1
            return {}

    elements, ok = mod._overpass_query(_FailBridge(), "q", retries=3)
    assert ok is False and elements == []
    assert _FailBridge.calls == 3, "失败必须重试满 retries 次"


def test_merge_gap_when_type_and_district_unresolvable(monkeypatch):
    import governance.coverage.coverage_merge as mod

    with tempfile.TemporaryDirectory(prefix="qwq_cov_expand_") as tmp:
        tmp_path = Path(tmp)
        monkeypatch.setattr(mod, "coverage_workspace_root", lambda: tmp_path / "runtime")
        monkeypatch.setattr(mod, "master_list_files", lambda **kw: [])
        candidates = _write_candidates(
            tmp_path / "cands.ndjson",
            [
                {"name": "东极", "province": "浙江省", "source": "wiki_category", "categories": [], "extract": "位于中国东部海域"},
            ],
        )
        report = merge_candidates(["浙江省"], candidate_files=[candidates], apply=False)
        assert report["appended"] == 0
        assert report["gaps"] == 1
        gap = report["gapItems"][0]
        assert set(gap["missing"]) == {"stableIdentityOrNameCountyCoordinate"}
        assert gap["reason"] == "identity_unresolved_without_guessing"


def test_generic_osm_facilities_are_semantically_rejected():
    cases = [
        (
            {"name": "Quarry", "source": "osm_poi", "osmTags": {"historic": "yes"}},
            "generic_or_placeholder_name",
        ),
        (
            {"name": "万达广场停车场", "source": "osm_poi", "osmTags": {"amenity": "parking"}},
            "ordinary_facility",
        ),
        (
            {"name": "锦江酒店", "source": "osm_poi", "osmTags": {"tourism": "hotel"}},
            "ordinary_lodging_or_commerce",
        ),
        (
            {"name": "人民路公交站", "source": "osm_poi", "osmTags": {"highway": "bus_stop"}},
            "transport_or_road",
        ),
    ]
    for item, reason in cases:
        assert _semantic_rejection_reason(item) == reason


def test_same_name_different_counties_are_not_merged_and_osm_tags_do_not_choose_type(
    monkeypatch,
):
    import governance.coverage.coverage_merge as mod

    with tempfile.TemporaryDirectory(prefix="qwq_cov_identity_") as tmp:
        tmp_path = Path(tmp)
        monkeypatch.setattr(mod, "coverage_workspace_root", lambda: tmp_path / "runtime")
        monkeypatch.setattr(mod, "master_list_files", lambda **kw: [])
        candidates = _write_candidates(
            tmp_path / "cands.ndjson",
            [
                {
                    "name": "人民公园",
                    "province": "四川省",
                    "city": "成都市",
                    "district": "青羊区",
                    "source": "wikidata_geo",
                    "identityRefs": {"qid": "Q100"},
                    "coordinates": {"lat": 30.67, "lon": 104.05},
                    "typeTagRefs": ["Entity/地点/公园"],
                },
                {
                    "name": "人民公园",
                    "province": "四川省",
                    "city": "自贡市",
                    "district": "自流井区",
                    "source": "wikidata_geo",
                    "identityRefs": {"qid": "Q200"},
                    "coordinates": {"lat": 29.35, "lon": 104.77},
                    "typeTagRefs": ["Entity/地点/公园"],
                },
                {
                    "name": "未知设施",
                    "province": "四川省",
                    "city": "成都市",
                    "district": "青羊区",
                    "source": "osm_poi",
                    "identityRefs": {"osmType": "way", "osmId": "300"},
                    "osmTags": {"historic": "yes", "leisure": "park"},
                },
            ],
        )
        report = merge_candidates(["四川省"], candidate_files=[candidates], apply=False)
        assert report["appended"] == 2
        assert report["osmOnlyRejected"] == 1
        assert {row["district"] for row in report["appendedItems"]} == {"青羊区", "自流井区"}


def test_cross_province_stable_identity_is_one_entity_with_multi_geo_and_multi_type(
    monkeypatch,
):
    import governance.coverage.coverage_merge as mod

    with tempfile.TemporaryDirectory(prefix="qwq_cov_cross_region_") as tmp:
        tmp_path = Path(tmp)
        monkeypatch.setattr(mod, "coverage_workspace_root", lambda: tmp_path / "runtime")
        monkeypatch.setattr(mod, "master_list_files", lambda **kw: [])
        candidates = _write_candidates(
            tmp_path / "cands.ndjson",
            [
                {
                    "name": "跨省湖",
                    "province": "四川省",
                    "city": "凉山彝族自治州",
                    "district": "盐源县",
                    "source": "wikidata_geo",
                    "identityRefs": {"qid": "Q999"},
                    "coordinates": {"lat": 27.7, "lon": 100.8},
                    "typeTagRefs": [
                        "Entity/地点/自然景观/水体",
                        "Entity/地点/景区/国家公园",
                    ],
                },
                {
                    "name": "跨省湖",
                    "province": "云南省",
                    "city": "丽江市",
                    "district": "宁蒗彝族自治县",
                    "source": "wiki_category",
                    "identityRefs": {"qid": "Q999", "wikipediaPageId": 999},
                    "categories": ["Category:国家公园"],
                    "extract": "跨省湖位于云南省丽江市宁蒗彝族自治县。",
                    "typeTagRefs": ["Entity/地点/自然景观/水体"],
                },
            ],
        )
        report = merge_candidates(
            ["四川省", "云南省"], candidate_files=[candidates], apply=False
        )
        assert report["appended"] == 1
        item = report["appendedItems"][0]
        assert item["entityType"] == "地点/景区"
        assert item["typeTagRefs"] == [
            "Entity/地点/景区/国家公园",
            "Entity/地点/自然景观/水体",
        ]
        assert item["geoTagRef"].endswith("/四川省/凉山彝族自治州/盐源县")
        assert len(item["geoTagRefs"]) == 2
        assert report["crossRegionCanonicalEntities"] == 1
