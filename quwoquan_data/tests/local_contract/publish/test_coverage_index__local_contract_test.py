"""覆盖账本契约（WP4-1/WP4-2，local_contract）：

- coverage/{省}.ndjson 从主清单 × publish 主线 × env_releases 导入证据派生；
- 跨省地点主/次省分片均出现（isPrimary 标注），全国汇总按 primary 去重；
- introductionUrl 四环境 base 来自 environment_topology_manifest，path 来自
  service.yaml；homepageId 有 v2 映射产物时展开真值，dryRun 导入不算生效；
- publish 有而主清单缺的实体补 masterListed=false 行。

（WP4-2 标签→实体主页路由绑定的契约断言在 tests/publish/test_tag_link_targets.py。）
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
import os
import tempfile

_TMP = Path(tempfile.mkdtemp(prefix="coverage_index_"))
os.environ["QWQ_DATA_ROOT"] = str(_TMP)
os.environ["QWQ_PUBLISH_ROOT"] = str(_TMP / "publish")

from _common import coverage_master_list  # noqa: E402
from _common.io import read_ndjson, write_json  # noqa: E402
from _common.paths import PUBLISH_ROOT  # noqa: E402
from publish_ops.build_publish_lookup_indexes import build_publish_lookup_indexes  # noqa: E402

# 主清单目录注入：从 paths 进程级单例派生（桥壳二次 exec 幂等，不引第二套覆写链）。
COVERAGE_ROOT = PUBLISH_ROOT.parent / "coverage" / "中国"
_ORIGINAL_COVERAGE_MASTER_ROOT = coverage_master_list.COVERAGE_MASTER_ROOT
coverage_master_list.COVERAGE_MASTER_ROOT = COVERAGE_ROOT

GEO_JZG = "Topic/地理/行政区/中国/四川省/阿坝藏族羌族自治州/九寨沟县"
GEO_LGH_SC = "Topic/地理/行政区/中国/四川省/凉山彝族自治州/盐源县"
GEO_LGH_YN = "Topic/地理/行政区/中国/云南省/丽江市/宁蒗彝族自治县"


def _master_file(province: str, city: str, districts: list[dict]) -> None:
    path = COVERAGE_ROOT / province / f"{city}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    import yaml

    path.write_text(
        yaml.safe_dump(
            {
                "schemaVersion": "quwoquan_data.discovery_seed/2",
                "country": "中国",
                "province": province,
                "city": city,
                "districts": districts,
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _publish_entity(entity_ref: str, *, geo_ref: str, tag_refs: list[str], promoted_at: str = "") -> None:
    entity_dir = PUBLISH_ROOT / "entities" / entity_ref
    entity_dir.mkdir(parents=True, exist_ok=True)
    (entity_dir / "page.md").write_text(f"# {entity_ref.split('/')[-1]}\n\n主页。", encoding="utf-8")
    write_json(
        entity_dir / "_entity.json",
        {
            "label": entity_ref.split("/")[-1],
            "domain": entity_ref.split("/")[0],
            "type": entity_ref.split("/")[1],
            "sourceTaskId": "t",
            "geoTagRef": geo_ref,
            "tagRefs": tag_refs,
        },
    )
    manifest: dict = {"assets": []}
    if promoted_at:
        manifest["quality"] = {"promotedAt": promoted_at}
    write_json(entity_dir / "manifest.json", manifest)


def _tag(ref: str, label: str) -> None:
    write_json(PUBLISH_ROOT / "tags" / ref / "_definition.json", {"label": label})


def _env_release(release_id: str, env: str, *, entities: list[str], dry_run: bool,
                 finished_at: str, mapping: dict[str, str] | None = None) -> None:
    release_dir = PUBLISH_ROOT / "env_releases" / release_id
    write_json(release_dir / f"{env}.json", {
        "schemaVersion": "quwoquan.data_env_release.v1",
        "releaseId": release_id,
        "environment": env,
        "desiredRefs": {"posts": [], "entities": entities},
    })
    write_json(release_dir / f"import-homepage-{env}.json", {
        "schemaVersion": "quwoquan_service.homepage_import_report/2",
        "env": env,
        "dryRun": dry_run,
        "created": [],
        "updated": [],
        "skipped": [],
        "entityRefToHomepageId": mapping or {},
        "finishedAt": finished_at,
    })


def _seed() -> None:
    _master_file("四川省", "阿坝藏族羌族自治州", [
        {"district": "九寨沟县", "leaves": [{
            "name": "九寨沟", "canonicalName": "九寨沟", "entityType": "地点/景区",
            "typeTagRefs": ["Entity/地点/景区/5A景区"], "geoTagRef": GEO_JZG,
            "selectionPriority": 1,
            "sourceReadiness": "ready",
        }]},
    ])
    _master_file("四川省", "凉山彝族自治州", [
        {"district": "盐源县", "leaves": [{
            "name": "泸沽湖", "canonicalName": "泸沽湖", "entityType": "地点/景区",
            "typeTagRefs": ["Entity/地点/景区/4A景区"], "geoTagRef": GEO_LGH_SC,
            "geoTagRefs": [GEO_LGH_SC, GEO_LGH_YN],
            "selectionPriority": 1,
            "sourceReadiness": "ready",
        }]},
    ])
    _master_file("四川省", "成都市", [
        {"district": "都江堰市", "leaves": [{
            "name": "灌县古城", "canonicalName": "灌县古城", "entityType": "地点/古镇",
            "typeTagRefs": ["Entity/地点/古镇/历史古镇"],
            "geoTagRef": "Topic/地理/行政区/中国/四川省/成都市/都江堰市",
            "selectionPriority": 1,
            "sourceReadiness": "pending",
        }]},
    ])
    _tag("Entity/地点/景区/5A景区", "5A景区")
    _publish_entity(
        "地点/景区/九寨沟",
        geo_ref=GEO_JZG,
        tag_refs=["Entity/地点/景区/5A景区"],
        promoted_at="2026-07-07T09:00:00+00:00",
    )
    # publish 有而主清单缺的历史实体。
    _publish_entity(
        "地点/景区/黄龙",
        geo_ref="Topic/地理/行政区/中国/四川省/阿坝藏族羌族自治州/松潘县",
        tag_refs=[],
    )
    # gamma：旧 dryRun（应忽略）+ 新 apply（v2 映射产物展开真值）。
    _env_release("rel_dry", "gamma", entities=["地点/景区/九寨沟"], dry_run=True,
                 finished_at="2026-07-07T12:00:00Z")
    _env_release("rel_apply", "gamma", entities=["地点/景区/九寨沟"], dry_run=False,
                 finished_at="2026-07-07T10:00:00Z",
                 mapping={"地点/景区/九寨沟": "homepage_9"})


_seed()
try:
    _COUNTS = build_publish_lookup_indexes()
finally:
    coverage_master_list.COVERAGE_MASTER_ROOT = _ORIGINAL_COVERAGE_MASTER_ROOT


def _coverage_rows(province: str) -> list[dict]:
    return read_ndjson(PUBLISH_ROOT / "index" / "coverage" / f"{province}.ndjson")


def test_coverage_shards_by_province_with_homepage_and_promoted_at():
    rows = {r["entityRef"]: r for r in _coverage_rows("四川省")}
    jzg = rows["地点/景区/九寨沟"]
    assert jzg["hasHomepage"] and jzg["masterListed"] and jzg["isPrimary"]
    assert jzg["promotedAt"] == "2026-07-07T09:00:00+00:00"
    guanxian = rows["地点/古镇/灌县古城"]
    assert not guanxian["hasHomepage"] and guanxian["sourceReadiness"] == "pending"


def test_cross_province_leaf_appears_in_both_shards_dedup_by_primary():
    sc = {r["entityRef"]: r for r in _coverage_rows("四川省")}
    yn = {r["entityRef"]: r for r in _coverage_rows("云南省")}
    assert sc["地点/景区/泸沽湖"]["isPrimary"] is True
    assert yn["地点/景区/泸沽湖"]["isPrimary"] is False
    manifest = json.loads((PUBLISH_ROOT / "index" / "_manifest.json").read_text(encoding="utf-8"))
    # 全国汇总按 primary 去重：4 实体（九寨沟/泸沽湖/灌县古城 + publish-only 黄龙）。
    assert manifest["coverage"]["entities"] == 4
    assert manifest["coverage"]["rows"] == 5
    assert manifest["coverage"]["entitiesWithHomepage"] == 2


def test_env_imports_use_latest_non_dry_run_and_expand_homepage_id():
    jzg = {r["entityRef"]: r for r in _coverage_rows("四川省")}["地点/景区/九寨沟"]
    gamma = jzg["envImports"]["gamma"]
    assert gamma["imported"] is True
    assert gamma["releaseId"] == "rel_apply"
    # v2 映射产物展开真实 homepageId；base 来自 environment_topology_manifest。
    assert gamma["introductionUrl"].endswith("/v1/homepages/homepage_9/introduction")
    assert gamma["introductionUrl"].startswith("https://gamma-api.")
    assert jzg["envImports"]["prod"] == {"imported": False}


def test_publish_only_entity_gets_master_listed_false_row():
    rows = {r["entityRef"]: r for r in _coverage_rows("四川省")}
    huanglong = rows["地点/景区/黄龙"]
    assert huanglong["masterListed"] is False
    assert huanglong["hasHomepage"] is True


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"coverage index tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
