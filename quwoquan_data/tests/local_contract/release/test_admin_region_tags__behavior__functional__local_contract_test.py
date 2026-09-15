"""行政区标签是控制面静态契约，不属于运行时 publish。"""
from __future__ import annotations

import json
from pathlib import Path

DATA_ROOT = next(
    parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data"
)
CHINA_ROOT = (
    DATA_ROOT
    / "control_plane"
    / "governance"
    / "taxonomy"
    / "Topic"
    / "地理"
    / "行政区"
    / "中国"
)


def _definition_dirs(root: Path) -> list[Path]:
    return sorted(path.parent for path in root.glob("*/_definition.json"))


def _child_labels(root: Path) -> set[str]:
    return {path.name for path in _definition_dirs(root)}


def test_china_admin_region_root_has_34_provincial_nodes():
    labels = _child_labels(CHINA_ROOT)
    assert len(labels) == 34
    assert {
        "广东省",
        "北京市",
        "上海市",
        "香港特别行政区",
        "澳门特别行政区",
        "台湾省",
    } <= labels


def test_guangdong_direct_children_are_complete_prefecture_level():
    labels = _child_labels(CHINA_ROOT / "广东省")
    assert len(labels) == 21
    assert {
        "广州市",
        "深圳市",
        "珠海市",
        "汕头市",
        "佛山市",
        "韶关市",
        "湛江市",
        "肇庆市",
        "江门市",
        "茂名市",
        "惠州市",
        "梅州市",
        "汕尾市",
        "河源市",
        "阳江市",
        "清远市",
        "东莞市",
        "中山市",
        "潮州市",
        "揭阳市",
        "云浮市",
    } <= labels


def test_beijing_direct_children_are_district_level():
    labels = _child_labels(CHINA_ROOT / "北京市")
    assert len(labels) == 16
    assert {"东城区", "西城区", "朝阳区", "海淀区", "通州区", "延庆区"} <= labels


def test_hong_kong_has_all_18_official_districts_as_direct_children():
    # spec_ref: specs/feature-tree/discovery-content/spec.md#dom-002
    # 来源：https://www.had.gov.hk/chs/18_districts/my_map.htm
    # 仅验证控制面名称、真实直挂路径与治理声明，不验证现实边界或消费者闭环。
    expected = {
        "中西区": "Central and Western",
        "东区": "Eastern",
        "南区": "Southern",
        "湾仔区": "Wan Chai",
        "九龙城区": "Kowloon City",
        "油尖旺区": "Yau Tsim Mong",
        "深水埗区": "Sham Shui Po",
        "黄大仙区": "Wong Tai Sin",
        "观塘区": "Kwun Tong",
        "大埔区": "Tai Po",
        "元朗区": "Yuen Long",
        "屯门区": "Tuen Mun",
        "北区": "North",
        "西贡区": "Sai Kung",
        "沙田区": "Sha Tin",
        "荃湾区": "Tsuen Wan",
        "葵青区": "Kwai Tsing",
        "离岛区": "Islands",
    }
    root = CHINA_ROOT / "香港特别行政区"
    assert expected.keys() <= _child_labels(root)
    for label, label_en in expected.items():
        definition = json.loads((root / label / "_definition.json").read_text("utf-8"))
        assert definition["label"] == label
        assert definition["labelEn"] == label_en
        assert definition["description"] == f"香港特别行政区十八个行政区之一：{label}"
        assert definition["collectionChannel"] == "poi"
        assert definition["consumedBy"] == ["recall", "intersection"]


def test_hong_kong_retains_existing_geographic_nodes():
    # spec_ref: specs/feature-tree/discovery-content/spec.md#dom-002
    # 四个旧地理容器不是额外行政区；保留既有名称与可解析路径。
    root = CHINA_ROOT / "香港特别行政区"
    expected = {
        "香港岛": "Hong Kong Island",
        "九龙": "Kowloon",
        "新界": "New Territories",
        "大屿山": "Lantau Island",
    }
    assert expected.keys() <= _child_labels(root)
    for label, label_en in expected.items():
        definition = json.loads((root / label / "_definition.json").read_text("utf-8"))
        assert definition["label"] == label
        assert definition["labelEn"] == label_en


def test_taiwan_has_nlsc_22_counties_and_keeps_kenting_container():
    # spec_ref: specs/feature-tree/discovery-content/spec.md#dom-002
    counties = {
        "台北", "新北", "台中", "台南", "高雄", "基隆市", "桃园市", "新竹市",
        "新竹县", "苗栗县", "彰化县", "云林县", "嘉义市", "嘉义县", "南投",
        "屏东县", "宜兰", "花莲", "台东", "澎湖", "金门", "连江县",
    }
    root = CHINA_ROOT / "台湾省"
    labels = _child_labels(root)
    assert counties <= labels
    assert len(counties) == 22
    assert "垦丁" in labels
    for label in ("桃园市", "新竹市", "新竹县", "嘉义市", "嘉义县", "屏东县", "连江县", "基隆市"):
        definition = json.loads((root / label / "_definition.json").read_text("utf-8"))
        assert definition["label"] == label
        assert "台湾省 22 个县市之一" in definition["description"]


def test_mainland_2025_admin_nodes_exist_without_deleting_history():
    # spec_ref: specs/feature-tree/discovery-content/spec.md#dom-002
    assert (CHINA_ROOT / "海南省" / "三沙市" / "西沙区" / "_definition.json").is_file()
    assert (CHINA_ROOT / "海南省" / "三沙市" / "南沙区" / "_definition.json").is_file()
    assert (CHINA_ROOT / "海南省" / "三沙市" / "西沙群岛" / "_definition.json").is_file()
    assert (CHINA_ROOT / "重庆市" / "两江新区" / "_definition.json").is_file()
    assert (CHINA_ROOT / "重庆市" / "江北区" / "_definition.json").is_file()
    assert (CHINA_ROOT / "重庆市" / "渝北区" / "_definition.json").is_file()
    assert (CHINA_ROOT / "新疆维吾尔自治区" / "喀什地区" / "岑岭县" / "_definition.json").is_file()
    assert (CHINA_ROOT / "新疆维吾尔自治区" / "和田地区" / "和康县" / "_definition.json").is_file()
    assert (CHINA_ROOT / "新疆维吾尔自治区" / "和田地区" / "和安县" / "_definition.json").is_file()
    assert (CHINA_ROOT / "新疆维吾尔自治区" / "草湖市" / "_definition.json").is_file()


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"admin region tag tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
