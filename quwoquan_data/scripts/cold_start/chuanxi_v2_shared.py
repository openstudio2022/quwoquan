"""川西 v2 冷启动共享常量与工具。"""
from __future__ import annotations

from cold_start.chuanxi_catalog_v2 import (
    CHUANXI_V2_RELEASE_ID,
    CHUANXI_V2_TASK_ID,
    ArticleSpec,
    build_all_article_specs,
)

V2_BATCHES = (
    "entity_intro",
    "weekend_chengdu",
    "loop_3_5d",
    "deep_7_14d",
    "inbound_hub",
    "images_p0",
)

GWT_REFS: list[tuple[str, str, str]] = [
    ("entity_intro", "article", "九寨沟_攻略"),
    ("weekend_chengdu", "article", "青城山都江堰_公共交通"),
    ("loop_3_5d", "article", "九寨黄龙环线_跟团_夏"),
    ("deep_7_14d", "article", "格聂徒步穿越_自驾_夏"),
    ("inbound_hub", "article", "北京出发_稻城亚丁经典线_散团_夏"),
    ("images_p0", "image", "四姑娘山_图文画报"),
]


def entity_names_from_refs(refs: tuple[str, ...]) -> list[str]:
    return [ref.split("/")[-1] for ref in refs if ref]


def spec_by_ref(ref: str) -> ArticleSpec | None:
    for spec in build_all_article_specs():
        if spec.ref == ref:
            return spec
    return None


def specs_for_batch(batch_id: str) -> list[ArticleSpec]:
    return [s for s in build_all_article_specs() if s.batch == batch_id]


def entities_for_batch(batch_id: str) -> set[str]:
    names: set[str] = set()
    for spec in specs_for_batch(batch_id):
        names.update(download_keys_for_spec(spec))
    return names


_ROUTE_TRANSPORTS = ("自驾", "公共交通", "跟团", "散团", "徒步", "巴士")


def download_keys_for_spec(spec: ArticleSpec) -> list[str]:
    keys = entity_names_from_refs(spec.entity_refs)
    if keys:
        return keys
    ref = spec.ref
    if ref.endswith("_图文画报"):
        return [ref[: -len("_图文画报")]]
    for transport in _ROUTE_TRANSPORTS:
        suffix = f"_{transport}"
        if ref.endswith(suffix):
            return [ref[: -len(suffix)]]
    return [ref.split("_")[0]]


__all__ = [
    "CHUANXI_V2_TASK_ID",
    "CHUANXI_V2_RELEASE_ID",
    "V2_BATCHES",
    "GWT_REFS",
    "entity_names_from_refs",
    "spec_by_ref",
    "specs_for_batch",
    "entities_for_batch",
    "download_keys_for_spec",
]
