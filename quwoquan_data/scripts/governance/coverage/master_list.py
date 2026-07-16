"""全国地点主清单共享库（discovery_seed/2，裁决 8：目录即行政层级）。

主清单唯一真相源是 `verticals/travel/coverage/中国/{省}/{市州}.yaml` 目录树本身，
无总控 index；本模块是所有消费方（verify 门 / decompose 阶段 A / coverage probe /
统计报表）共用的 walk・加载・回写・地理覆盖门逻辑，禁止各消费方再自写第二套
目录遍历或状态推导。

直辖市口径（北京/上海/天津/重庆）：行政区树把直辖市的区县挂在市级槽位
（`中国/北京市/东城区` 为叶子），主清单相应落「区县级一文件」——
文件名即区县名，文件内 districts 恰一组且 district == city（见
`city_is_district_level`；verify 门 C4 同口径）。

契约树（tags/行政区树）按「契约跟代码走」以仓内路径解析，
不随运行时 QWQ_DATA_ROOT 漂移；测试注入用函数参数。
"""
from __future__ import annotations

import hashlib
import unicodedata
from pathlib import Path
from typing import Any, Iterator

import yaml

from governance.coverage.entity_type_taxonomy import CONTRACT_TAGS_ROOT
from core.paths import _REPO_DATA_ROOT

COVERAGE_MASTER_ROOT = _REPO_DATA_ROOT / "verticals" / "travel" / "coverage" / "中国"
MASTER_LIST_SCHEMA_PATH = _REPO_DATA_ROOT / "schema" / "governance" / "master_list.schema.json"
ADMIN_REGION_PREFIX = "Topic/地理/行政区"


def coverage_identity_key(
    *,
    country: str,
    province: str,
    city: str,
    district: str,
    entity_type: str,
    canonical_name: str,
) -> str:
    """派生覆盖单元稳定身份；主清单不存运行期 ID 或执行状态。"""
    parts = (country, province, city, district, entity_type, canonical_name)
    normalized = tuple(unicodedata.normalize("NFKC", str(part)).strip() for part in parts)
    if any(not part for part in normalized):
        raise ValueError("coverage identity requires country/province/city/district/entityType/canonicalName")
    # 长度前缀避免字段值本身出现分隔符时产生拼接歧义。
    payload = "".join(f"{len(part)}:{part}" for part in normalized).encode("utf-8")
    return "coverage_" + hashlib.sha256(payload).hexdigest()


# ─── 行政区树（唯一地理真相源） ─────────────────────────────────────────
def is_tag_node(tags_root: Path, ref: str) -> bool:
    node = tags_root / ref
    return node.is_dir() and (node / "_definition.json").is_file()


def is_leaf_tag_node(tags_root: Path, ref: str) -> bool:
    if not is_tag_node(tags_root, ref):
        return False
    node = tags_root / ref
    return not any(
        child.is_dir() and (child / "_definition.json").is_file() for child in node.iterdir()
    )


def admin_children(ref: str, *, tags_root: Path | None = None) -> list[str]:
    """行政区树节点的直接子节点名（排序稳定）。"""
    root = tags_root or CONTRACT_TAGS_ROOT
    node = root / ref
    if not node.is_dir():
        return []
    return sorted(
        child.name
        for child in node.iterdir()
        if child.is_dir() and (child / "_definition.json").is_file()
    )


def admin_geo_ref(*parts: str) -> str:
    return "/".join([ADMIN_REGION_PREFIX, *parts])


def city_is_district_level(country: str, province: str, city: str, *, tags_root: Path | None = None) -> bool:
    """直辖市口径：市州节点本身是行政区树叶子（该节点即区县）。"""
    root = tags_root or CONTRACT_TAGS_ROOT
    return is_leaf_tag_node(root, admin_geo_ref(country, province, city))


# ─── walk / 加载 / 回写 ────────────────────────────────────────────────
def master_list_files(
    *,
    provinces: list[str] | tuple[str, ...] | None = None,
    coverage_root: Path | None = None,
) -> list[Path]:
    """主清单市州文件列表（可按省过滤；排序稳定）。"""
    root = coverage_root or COVERAGE_MASTER_ROOT
    if not root.is_dir():
        return []
    wanted = {str(p).strip() for p in (provinces or []) if str(p).strip()}
    out: list[Path] = []
    for path in sorted(root.rglob("*.yaml")):
        parts = path.relative_to(root).parts
        if len(parts) != 2:
            continue
        if wanted and parts[0] not in wanted:
            continue
        out.append(path)
    return out


def load_master_list_file(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"主清单文件顶层必须是 mapping: {path}")
    return data


def iter_master_leaves(
    data: dict[str, Any],
) -> Iterator[tuple[str, dict[str, Any]]]:
    """遍历单文件 leaves，返回 (district, leaf)。"""
    for group in data.get("districts") or []:
        if not isinstance(group, dict):
            continue
        district = str(group.get("district") or "")
        for leaf in group.get("leaves") or []:
            if isinstance(leaf, dict):
                yield district, leaf


def dump_master_list_file(path: Path, data: dict[str, Any]) -> None:
    """回写主清单文件：保留文件头连续注释块（自解释头），正文重新序列化。"""
    header_lines: list[str] = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("#"):
                header_lines.append(line)
            else:
                break
    body = yaml.safe_dump(
        data,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=120,
    )
    text = ("\n".join(header_lines) + "\n" + body) if header_lines else body
    path.write_text(text, encoding="utf-8")


# ─── 统计（报表 / registry 回填口径） ──────────────────────────────────
def master_list_stats(
    *,
    provinces: list[str] | None = None,
    coverage_root: Path | None = None,
) -> dict[str, Any]:
    """主清单统计：文件/区县/叶子规模、类型分布与跨省地点。"""
    stats: dict[str, Any] = {
        "files": 0,
        "districts": 0,
        "leaves": 0,
        "byProvince": {},
        "byEntityType": {},
        "crossProvinceLeaves": [],
    }
    for path in master_list_files(provinces=provinces, coverage_root=coverage_root):
        data = load_master_list_file(path)
        province = str(data.get("province") or path.parent.name)
        prov_stat = stats["byProvince"].setdefault(province, {"files": 0, "districts": 0, "leaves": 0})
        stats["files"] += 1
        prov_stat["files"] += 1
        seen_districts: set[str] = set()
        for district, leaf in iter_master_leaves(data):
            seen_districts.add(district)
            stats["leaves"] += 1
            prov_stat["leaves"] += 1
            etype = str(leaf.get("entityType") or "")
            stats["byEntityType"][etype] = stats["byEntityType"].get(etype, 0) + 1
            geo_refs = [str(g) for g in (leaf.get("geoTagRefs") or []) if str(g).strip()]
            ref_provinces = {ref.split("/")[4] for ref in geo_refs if len(ref.split("/")) > 4}
            if len(ref_provinces) > 1:
                stats["crossProvinceLeaves"].append(
                    {
                        "canonicalName": str(leaf.get("canonicalName") or ""),
                        "geoTagRef": str(leaf.get("geoTagRef") or ""),
                        "geoTagRefs": geo_refs,
                    }
                )
        stats["districts"] += len(seen_districts)
        prov_stat["districts"] += len(seen_districts)
    return stats


# ─── 地理覆盖发现门（decompose 阶段 A 出口） ───────────────────────────
def geo_coverage_issues(
    provinces: list[str] | tuple[str, ...],
    *,
    country: str = "中国",
    coverage_root: Path | None = None,
    tags_root: Path | None = None,
) -> list[str]:
    """省级枚举地理覆盖门：市州文件覆盖率 + 文件内区县覆盖率。

    行政区树是唯一地理真相源：省下每个市州必须有主清单文件；每个市州文件
    必须覆盖行政区树上该市州的全部区县（直辖市区县级文件覆盖自身）。
    叶子 geoTagRef 合法性与类型 scope 由 verify 门 C5/C7 承担，这里不重复。
    """
    root = coverage_root or COVERAGE_MASTER_ROOT
    tags = tags_root or CONTRACT_TAGS_ROOT
    issues: list[str] = []
    for province in provinces:
        province = str(province).strip()
        if not province:
            continue
        province_geo = admin_geo_ref(country, province)
        if not is_tag_node(tags, province_geo):
            issues.append(f"geo-coverage: 省 '{province}' 未命中行政区树 {province_geo}")
            continue
        expected_cities = admin_children(province_geo, tags_root=tags)
        province_dir = root / province
        on_disk = {p.stem for p in province_dir.glob("*.yaml")} if province_dir.is_dir() else set()
        for city in expected_cities:
            if city not in on_disk:
                issues.append(f"geo-coverage: {province} 缺市州文件 '{city}.yaml'")
        for city in sorted(on_disk):
            city_geo = f"{province_geo}/{city}"
            if not is_tag_node(tags, city_geo):
                continue  # C1 已阻断，不重复报
            try:
                data = load_master_list_file(province_dir / f"{city}.yaml")
            except Exception as exc:  # noqa: BLE001
                issues.append(f"geo-coverage: {province}/{city}.yaml 解析失败: {exc}")
                continue
            covered = {district for district, _ in iter_master_leaves(data)}
            if city_is_district_level(country, province, city, tags_root=tags):
                if covered - {city}:
                    issues.append(
                        f"geo-coverage: {province}/{city}.yaml 直辖市区县级文件只允许 district == '{city}'"
                    )
                continue
            for district in admin_children(city_geo, tags_root=tags):
                if district not in covered:
                    issues.append(f"geo-coverage: {province}/{city}.yaml 缺区县 '{district}'")
    return issues


# ─── decompose 阶段 A 派生（省 → 市州 → 区县 分区树） ──────────────────
def discovery_partitions_from_master_list(
    provinces: list[str] | tuple[str, ...],
    *,
    coverage_root: Path | None = None,
) -> list[dict[str, Any]]:
    """从主清单派生 decompose 分区树（与 `task decompose load` discovery JSON 同构）。

    分区维度固定为地理三级：省 → 市州 → 区县；叶子挂区县分区，
    leaf = {name: canonicalName, entityType}（ref 由主清单稳定字段派生）。
    主清单本身仍是唯一真相源，此函数只做只读投影，不回写。
    """
    partitions: list[dict[str, Any]] = []
    for province in provinces:
        province = str(province).strip()
        if not province:
            continue
        city_parts: list[dict[str, Any]] = []
        for path in master_list_files(provinces=[province], coverage_root=coverage_root):
            data = load_master_list_file(path)
            city = str(data.get("city") or path.stem)
            district_parts: dict[str, dict[str, Any]] = {}
            for district, leaf in iter_master_leaves(data):
                canonical = str(leaf.get("canonicalName") or leaf.get("name") or "").strip()
                if not canonical or not district:
                    continue
                node = district_parts.setdefault(
                    district, {"key": district, "leaves": []}
                )
                node["leaves"].append(
                    {
                        "name": canonical,
                        "entityType": str(leaf.get("entityType") or ""),
                    }
                )
            if district_parts:
                city_parts.append(
                    {
                        "key": city,
                        "partitions": [district_parts[k] for k in sorted(district_parts)],
                    }
                )
        if city_parts:
            partitions.append({"key": province, "partitions": city_parts})
    return partitions
