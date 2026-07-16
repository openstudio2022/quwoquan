"""行政区标签是控制面静态契约，不属于运行时 publish。"""
from __future__ import annotations

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


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"admin region tag tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
