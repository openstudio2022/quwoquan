"""地点实体类型唯一真相源桥接（裁决 6：`Entity/地点` 树是唯一定义处）。

本模块是「类型口径归一」的共享消费面：execution 输入门、主清单 verify 门、WP2 枚举
类型标注全部经此读取类型契约，禁止再出现第二处类型定义
（拍平清单 / lint 内联集合 / verify 内联集合都不允许回归）。

三块契约：

- **一级类型集合**：`Entity/{维度}` 树的一级节点（如 `地点/景区`）。entityType
  主类型单值只能取一级节点名——它决定 entityRef 第二段（目录归属）、主页分类
  管理归属与 homepageType 映射，必须是确定性单值。
- **主类型判定优先级表** `PRIMARY_TYPE_PRIORITY`：一地多类型（武侯祠＝景区+博物馆+遗址）
  时按固定优先级取主类型；供 WP2 枚举与 verify 门共同消费，不允许只写在文档里。
- **试点 scope** `PILOT_PRIMARY_TYPES`：本轮放量枚举允许的一级类型集合
  （8 核心 + 温泉/主题乐园可选；餐厅/住宿/交通枢纽 out of scope）。

tags 树是受版本控制的契约子树，按军规「契约跟代码走」以仓内路径解析，
不随运行时 `QWQ_DATA_ROOT` 漂移（测试注入用函数参数 `tags_root`）。
"""
from __future__ import annotations

import functools
from pathlib import Path

from core.paths import CONTROL_PLANE_TAXONOMY_ROOT

# 受版本控制的标签契约根（跟代码走；运行时隔离根不改变类型契约）。
CONTRACT_TAGS_ROOT = CONTROL_PLANE_TAXONOMY_ROOT
ENTITY_GROUP = "Entity"
PLACE_DOMAIN = "地点"

# 裁决 6 主类型判定优先级表（值越小优先级越高；不在表内的类型不参与主类型竞争，
# 兜底为打卡地）。表是唯一真相源：WP2 枚举、verify 门、测试断言全部消费此常量。
PRIMARY_TYPE_PRIORITY: tuple[str, ...] = (
    "景区",
    "博物馆",
    "宗教场所",
    "遗址",
    "古镇",
    "主题乐园",
    "自然景观",
    "公园",
    "温泉",
    "打卡地",
)
PRIMARY_TYPE_FALLBACK = "打卡地"

# 试点覆盖 scope（裁决 6）：8 个核心一级类型 + 2 个可选类型。
PILOT_CORE_PRIMARY_TYPES: frozenset[str] = frozenset(
    {"景区", "自然景观", "打卡地", "遗址", "古镇", "宗教场所", "博物馆", "公园"}
)
PILOT_OPTIONAL_PRIMARY_TYPES: frozenset[str] = frozenset({"温泉", "主题乐园"})
PILOT_PRIMARY_TYPES: frozenset[str] = PILOT_CORE_PRIMARY_TYPES | PILOT_OPTIONAL_PRIMARY_TYPES


def _is_tag_node(path: Path) -> bool:
    return path.is_dir() and (path / "_definition.json").is_file()


@functools.lru_cache(maxsize=8)
def _entity_dimension_names(tags_root: Path) -> tuple[str, ...]:
    entity_root = tags_root / ENTITY_GROUP
    if not entity_root.is_dir():
        return ()
    return tuple(
        sorted(child.name for child in entity_root.iterdir() if child.is_dir() and not child.name.startswith("_"))
    )


def entity_top_level_types(domain: str = PLACE_DOMAIN, *, tags_root: Path | None = None) -> tuple[str, ...]:
    """`Entity/{domain}` 树一级节点名（entityType 主类型合法值域）。"""
    root = (tags_root or CONTRACT_TAGS_ROOT) / ENTITY_GROUP / domain
    if not root.is_dir():
        return ()
    return tuple(sorted(child.name for child in root.iterdir() if _is_tag_node(child)))


def known_entity_type_paths(*, tags_root: Path | None = None) -> set[str]:
    """全部合法 entityType 路径 `{维度}/{一级节点}`（跨 Entity 全部维度）。

    execution 输入门的 entityType 真相源：契约缺失（Entity 树不存在/为空）时显式抛错，
    禁止静默空集把所有类型误判为未知。
    """
    root = tags_root or CONTRACT_TAGS_ROOT
    dims = _entity_dimension_names(root)
    if not dims:
        raise RuntimeError(
            f"Entity 标签契约树缺失或为空: {root / ENTITY_GROUP}（类型口径唯一定义处，禁止静默降级）"
        )
    out: set[str] = set()
    for dim in dims:
        for node in entity_top_level_types(dim, tags_root=root):
            out.add(f"{dim}/{node}")
    if not out:
        raise RuntimeError(f"Entity 标签契约树无任何一级类型节点: {root / ENTITY_GROUP}")
    return out


def entity_type_tag_node_exists(tag_ref: str, *, tags_root: Path | None = None) -> bool:
    """tagRef（如 `Entity/地点/景区/5A景区`）是否命中契约树节点。"""
    ref = str(tag_ref or "").strip().strip("/")
    if not ref:
        return False
    node = (tags_root or CONTRACT_TAGS_ROOT) / ref
    return _is_tag_node(node)


def entity_type_leaf_refs(domain: str = PLACE_DOMAIN, *, tags_root: Path | None = None) -> set[str]:
    """`Entity/{domain}` 全树节点 tagRef 集合（含一级节点与叶子细分）。"""
    root = tags_root or CONTRACT_TAGS_ROOT
    domain_root = root / ENTITY_GROUP / domain
    out: set[str] = set()
    if not domain_root.is_dir():
        return out
    for definition in domain_root.rglob("_definition.json"):
        out.add(definition.parent.relative_to(root).as_posix())
    return out


def resolve_primary_entity_type(type_names: list[str] | tuple[str, ...] | set[str]) -> str:
    """按裁决 6 优先级表从多类型集合判定主类型单值。

    输入是一级类型名集合（如 {"博物馆", "遗址", "景区"} → "景区"）。
    集合为空或全部不在优先级表内时兜底 `打卡地`。
    """
    candidates = {str(name).strip() for name in (type_names or []) if str(name).strip()}
    for name in PRIMARY_TYPE_PRIORITY:
        if name in candidates:
            return name
    return PRIMARY_TYPE_FALLBACK


def find_entity_type_node_path(domain: str, type_name: str, *, tags_root: Path | None = None) -> str | None:
    """在 `Entity/{domain}` 树内查找类型名对应节点（任意层），返回 tagRef 或 None。

    用于校验细分类型与 Entity 树层级的一致性：`咖啡馆` → `Entity/地点/餐厅/咖啡馆`。
    """
    name = str(type_name or "").strip()
    if not name:
        return None
    root = tags_root or CONTRACT_TAGS_ROOT
    domain_root = root / ENTITY_GROUP / domain
    if not domain_root.is_dir():
        return None
    if _is_tag_node(domain_root / name):
        return (domain_root / name).relative_to(root).as_posix()
    matches = sorted(
        definition.parent.relative_to(root).as_posix()
        for definition in domain_root.rglob("_definition.json")
        if definition.parent.name == name
    )
    return matches[0] if matches else None

TYPE_TO_DOMAIN_ETYPE: dict[str, tuple[str, str]] = {
    "景区": ("地点", "景区"),
    "景点": ("地点", "景区"),
    "博物馆": ("地点", "博物馆"),
    "古镇": ("地点", "古镇"),
    "遗址": ("地点", "遗址"),
    "打卡地": ("地点", "打卡地"),
    "餐厅": ("地点", "餐厅"),
    "民宿": ("地点", "民宿"),
    "山峰": ("地点", "自然景观"),
    "湖泊": ("地点", "自然景观"),
    "自然景观": ("地点", "自然景观"),
    "牧场": ("地点", "自然景观"),
    "学校": ("机构", "学校"),
}
DEFAULT_DOMAIN_ETYPE = ("地点", "打卡地")


def resolve_domain_etype(
    etype_hint: str | None,
    *,
    allow_default_on_missing: bool = True,
    allow_default_on_unknown: bool = True,
) -> tuple[str, str]:
    """Normalize an entity type against the governed Entity taxonomy."""
    if not etype_hint or not str(etype_hint).strip().strip("/"):
        if allow_default_on_missing:
            return DEFAULT_DOMAIN_ETYPE
        raise ValueError("entityType missing")
    hint = str(etype_hint).strip().strip("/")
    if "/" in hint:
        parts = hint.split("/", 1)
        if all(parts):
            return parts[0], parts[1]
    mapped = TYPE_TO_DOMAIN_ETYPE.get(hint)
    if mapped is not None:
        return mapped
    matches = sorted(
        path for path in known_entity_type_paths() if path.rsplit("/", 1)[-1] == hint
    )
    if len(matches) == 1:
        domain, entity_type = matches[0].split("/", 1)
        return domain, entity_type
    if allow_default_on_unknown:
        return DEFAULT_DOMAIN_ETYPE
    raise ValueError(f"unknown entityType hint: {etype_hint!r}")


def require_domain_etype(
    etype_hint: str | None, *, context: str = "entityType"
) -> tuple[str, str]:
    try:
        return resolve_domain_etype(
            etype_hint,
            allow_default_on_missing=False,
            allow_default_on_unknown=False,
        )
    except ValueError as exc:
        raise ValueError(f"{context}: {exc}") from exc


def entity_ref(domain: str, entity_type: str, name: str) -> str:
    return f"/entity/{domain}/{entity_type}/{name}"
