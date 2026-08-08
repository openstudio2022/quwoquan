"""覆盖账本契约（WP4-1/WP4-2，local_contract）：

- coverage/{省}.ndjson 只从主清单 × canonical objects 派生；
- 跨省地点主/次省分片均出现（isPrimary 标注），全国汇总按 primary 去重；
- homepageId、environment URL 与导入状态只进入 append-only environment receipt；
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
import tempfile

_TMP = Path(tempfile.mkdtemp(prefix="coverage_index_"))
TAXONOMY_ROOT = _TMP / "control_plane" / "governance" / "taxonomy"

from governance.coverage import master_list as coverage_master_list  # noqa: E402
from core.io import read_ndjson, write_json  # noqa: E402
from core.paths import OUTPUT_ROOT, PUBLISH_ROOT, RELEASE_ROOT  # noqa: E402
from content.release.canonical.build_lookup_indexes import build_publish_lookup_indexes  # noqa: E402
from content.release.environment.coverage_receipt import write_environment_coverage_receipt  # noqa: E402

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
                "schema": "quwoquan_data.discovery_seed",
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
            "originTaskId": "t",
            "geoTagRef": geo_ref,
            "tagRefs": tag_refs,
        },
    )
    manifest: dict = {"assets": []}
    if promoted_at:
        manifest["quality"] = {"promotedAt": promoted_at}
    write_json(entity_dir / "manifest.json", manifest)


def _tag(ref: str, label: str) -> None:
    write_json(TAXONOMY_ROOT / ref / "_definition.json", {"label": label})


def _homepage_import_report(
    env: str,
    *,
    dry_run: bool,
    mapping: dict[str, str] | None = None,
) -> dict:
    return {
        "schema": "quwoquan_service.homepage_import_report",
        "env": env,
        "dryRun": dry_run,
        "mode": "upsert",
        "sourceOwner": "qwq_data",
        "created": [],
        "updated": [],
        "offlined": [],
        "skipped": [],
        "entityRefToHomepageId": mapping or {},
        "finishedAt": "2026-07-07T10:00:00Z",
    }


def _seed() -> None:
    _master_file("四川省", "阿坝藏族羌族自治州", [
        {"district": "九寨沟县", "leaves": [{
            "name": "九寨沟", "canonicalName": "九寨沟", "entityType": "地点/景区",
            "typeTagRefs": ["Entity/地点/景区/5A景区"], "geoTagRef": GEO_JZG,
            "selectionPriority": 1,
        }]},
    ])
    _master_file("四川省", "凉山彝族自治州", [
        {"district": "盐源县", "leaves": [{
            "name": "泸沽湖", "canonicalName": "泸沽湖", "entityType": "地点/景区",
            "typeTagRefs": ["Entity/地点/景区/4A景区"], "geoTagRef": GEO_LGH_SC,
            "geoTagRefs": [GEO_LGH_SC, GEO_LGH_YN],
            "selectionPriority": 1,
        }]},
    ])
    _master_file("四川省", "成都市", [
        {"district": "都江堰市", "leaves": [{
            "name": "灌县古城", "canonicalName": "灌县古城", "entityType": "地点/古镇",
            "typeTagRefs": ["Entity/地点/古镇/历史古镇"],
            "geoTagRef": "Topic/地理/行政区/中国/四川省/成都市/都江堰市",
            "selectionPriority": 1,
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
    _publish_entity(
        "地点/景区/不属于当前发布",
        geo_ref="Topic/地理/行政区/中国/四川省/成都市/武侯区",
        tag_refs=[],
    )
    write_json(RELEASE_ROOT / "coverage-index" / "payload" / "desired_state.json", {
        "schema": "quwoquan_data.release_desired_state",
        "releaseId": "coverage-index",
        "desiredRefs": {
            "posts": [],
            "entities": ["地点/景区/九寨沟", "地点/景区/黄龙"],
            "creators": [],
            "tags": ["Entity/地点/景区/5A景区"],
        },
    })


_seed()
try:
    _COUNTS = build_publish_lookup_indexes(
        release_id="coverage-index", taxonomy_root=TAXONOMY_ROOT
    )
finally:
    coverage_master_list.COVERAGE_MASTER_ROOT = _ORIGINAL_COVERAGE_MASTER_ROOT

_SICHUAN_COVERAGE = (
    RELEASE_ROOT
    / "coverage-index"
    / "payload"
    / "index"
    / "lookups"
    / "coverage"
    / "四川省.ndjson"
)
_COVERAGE_BYTES_BEFORE_RECEIPT = _SICHUAN_COVERAGE.read_bytes()
_CANONICAL_BYTES_BEFORE_RECEIPTS = {
    path.relative_to(PUBLISH_ROOT).as_posix(): path.read_bytes()
    for path in sorted(PUBLISH_ROOT.rglob("*"))
    if path.is_file()
}
_COVERAGE_RECEIPTS = {
    environment: write_environment_coverage_receipt(
        environment=environment,
        release_id="coverage-index",
        run_id="apply-1",
        release_root=RELEASE_ROOT / "coverage-index",
        run_root=(
            OUTPUT_ROOT
            / "env"
            / environment
            / "runs"
            / "data-release"
            / "coverage-index"
            / "apply-1"
        ),
        importer_report=_homepage_import_report(
            environment,
            dry_run=False,
            mapping={"地点/景区/九寨沟": f"homepage_{environment}"},
        ),
        api_base_url=f"https://api.{environment}.example",
    )
    for environment in ("alpha", "beta", "gamma", "prod")
}


def _coverage_rows(province: str) -> list[dict]:
    return read_ndjson(
        RELEASE_ROOT / "coverage-index" / "payload" / "index" / "lookups" / "coverage" / f"{province}.ndjson"
    )


def test_coverage_shards_by_province_with_homepage_and_promoted_at():
    rows = {r["entityRef"]: r for r in _coverage_rows("四川省")}
    jzg = rows["地点/景区/九寨沟"]
    assert jzg["hasHomepage"] and jzg["masterListed"] and jzg["isPrimary"]
    assert jzg["promotedAt"] == "2026-07-07T09:00:00+00:00"
    guanxian = rows["地点/古镇/灌县古城"]
    assert not guanxian["hasHomepage"]
    assert {
        "entityRef",
        "canonicalName",
        "entityType",
        "geoTagRef",
        "province",
        "hasHomepage",
        "masterListed",
        "isPrimary",
    }.issubset(guanxian)
    assert "envImports" not in guanxian
    assert all("readiness" not in key.lower() and "primarysource" not in key.lower() for key in guanxian)


def test_cross_province_leaf_appears_in_both_shards_dedup_by_primary():
    sc = {r["entityRef"]: r for r in _coverage_rows("四川省")}
    yn = {r["entityRef"]: r for r in _coverage_rows("云南省")}
    assert sc["地点/景区/泸沽湖"]["isPrimary"] is True
    assert yn["地点/景区/泸沽湖"]["isPrimary"] is False
    manifest = json.loads(
        (
            RELEASE_ROOT
            / "coverage-index"
            / "payload"
            / "index"
            / "lookups"
            / "manifest.json"
        ).read_text(encoding="utf-8")
    )
    # 全国汇总按 primary 去重：4 实体（九寨沟/泸沽湖/灌县古城 + publish-only 黄龙）。
    assert manifest["coverage"]["entities"] == 4
    assert manifest["coverage"]["rows"] == 5
    assert manifest["coverage"]["entitiesWithHomepage"] == 2


def test_environment_receipt_expands_homepage_without_mutating_release():
    for environment, receipt_path in _COVERAGE_RECEIPTS.items():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        rows = {row["entityRef"]: row for row in receipt["rows"]}
        projected = rows["地点/景区/九寨沟"]
        assert projected["imported"] is True
        assert projected["homepageId"] == f"homepage_{environment}"
        assert projected["introductionUrl"] == (
            f"https://api.{environment}.example/homepages/"
            f"homepage_{environment}/introduction"
        )
    assert _SICHUAN_COVERAGE.read_bytes() == _COVERAGE_BYTES_BEFORE_RECEIPT
    assert {
        path.relative_to(PUBLISH_ROOT).as_posix(): path.read_bytes()
        for path in sorted(PUBLISH_ROOT.rglob("*"))
        if path.is_file()
    } == _CANONICAL_BYTES_BEFORE_RECEIPTS
    serialized_release = json.dumps(
        [
            json.loads(line)
            for path in sorted(
                (RELEASE_ROOT / "coverage-index/payload").rglob("*.ndjson")
            )
            for line in path.read_text(encoding="utf-8").splitlines()
            if line
        ],
        ensure_ascii=False,
    )
    assert all(
        f"https://api.{environment}.example" not in serialized_release
        for environment in ("alpha", "beta", "gamma", "prod")
    )


def test_publish_only_entity_gets_master_listed_false_row():
    rows = {r["entityRef"]: r for r in _coverage_rows("四川省")}
    huanglong = rows["地点/景区/黄龙"]
    assert huanglong["masterListed"] is False
    assert huanglong["hasHomepage"] is True
    assert "地点/景区/不属于当前发布" not in rows


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"coverage index tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
