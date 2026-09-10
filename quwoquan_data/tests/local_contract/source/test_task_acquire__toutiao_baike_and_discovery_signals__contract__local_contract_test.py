# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-037.t10
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-037.t11
"""头条百科（www.baike.com）是百科闭集成员；discoverySignals 只记录透传到 source unit meta。"""
from __future__ import annotations

import hashlib
import json
import socket
import sys
from pathlib import Path

import pytest

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from content.release.canonical import final_surface_projection  # noqa: E402
from content.source import acquire as acquire_module  # noqa: E402
from core import paths  # noqa: E402
from core.schema import assert_valid, load_schema, validate_strict  # noqa: E402

EXECUTION_ID = "20260907--travel-homepage-six-step-m1000--toutiao--pilot-001"
TARGET = "entities/地点/自然景观/格聂神山"
PAGE_URL = "https://www.baike.com/wiki/%E6%A0%BC%E8%81%82%E7%A5%9E%E5%B1%B1"


def _canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _write(path: Path, data: bytes | str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    return path


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _refuse(*_args, **_kwargs):
        raise AssertionError("task acquire 不得发起任何网络连接")

    monkeypatch.setattr(socket, "socket", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)
    monkeypatch.setattr(socket, "getaddrinfo", _refuse)


@pytest.fixture()
def execution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    tasks = tmp_path / "data/tasks"
    monkeypatch.setattr(paths, "DATA_EXECUTIONS_ROOT", tasks)
    monkeypatch.delenv("QWQ_LIBRARY_ROOT", raising=False)
    root = tasks / EXECUTION_ID
    _write(root / "execution_manifest.json", _canonical({"schema": "quwoquan_data.content_execution_manifest", "executionId": EXECUTION_ID}))
    _write(root / "0.plan/target_set.json", _canonical({
        "schema": "quwoquan_data.target_set", "executionId": EXECUTION_ID, "carrier": "homepage",
        "selectionPolicy": "frozen", "entityCatalogDigest": "sha256:" + "0" * 64,
        "candidateBinding": {"scope": "output", "ref": "x.json", "digest": "sha256:" + "1" * 64, "candidateCount": 1},
        "targetCount": 1, "targetRefs": [TARGET],
        "targets": [{"name": "格聂神山", "entityType": "地点/自然景观", "region": "中国/四川省/甘孜藏族自治州"}],
    }))
    return root


def test_toutiao_baike_page_is_encyclopedia_and_projects_into_publish_entity_source_kind(execution: Path, tmp_path: Path) -> None:
    source_md = _write(tmp_path / "downloads/genie.source.md", "# 格聂神山\n\n格聂神山位于四川省甘孜州理塘县，海拔 6204 米。\n\n## 信息区取证\n\n- 海拔：6204 米\n")
    manifest = _write(tmp_path / "ingest.json", _canonical({
        "schema": "quwoquan_data.ingest_manifest", "executionId": EXECUTION_ID,
        "targets": [{"targetRef": TARGET, "sources": [{
            "kind": "page", "sourceUrl": PAGE_URL, "title": "格聂神山",
            "sourceMarkdownPath": str(source_md), "license": "CC BY-SA 4.0",
            "licenseUrl": "https://creativecommons.org/licenses/by-sa/4.0/", "creator": "头条百科编辑们",
            "relevance": "实体主页事实来源",
            "discoverySignals": {"ctripHeat": 8.1, "ctripReviews": 1320, "wikiViews30d": 0},
        }]}],
    }))

    result = acquire_module.acquire(execution_id=EXECUTION_ID, request_path=manifest)
    assert result["ingested"] == 1 and result["failed"] == 0

    refs = json.loads((execution / TARGET / "1.download/source_refs.json").read_bytes())
    row = refs["sources"][0]
    assert row["sourceId"] == "toutiao_baike" and row["sourceClass"] == "encyclopedia"
    unit = execution / row["metaRef"].rsplit("/", 1)[0]
    meta = json.loads((unit / "meta.json").read_bytes())
    assert meta["sourceClass"] == "encyclopedia" and meta["sourceId"] == "toutiao_baike"
    assert_valid(meta, "source", "atomic_source_unit_meta", label="meta")

    # homepage 事务用同一 sourceId 判定百科闭集成员，投影落到 publish entity schema 的 toutiao 枚举。
    kind, extractor, policy = final_surface_projection._homepage_source_kind({"sourceId": row["sourceId"], "meta": meta})
    assert (kind, extractor, policy) == ("toutiao_baike", "toutiao_baike_html", "encyclopedia-primary")
    primary = {
        "sourceKind": kind, "extractor": extractor, "policyRevision": policy,
        "entityName": "格聂神山", "canonicalUrl": PAGE_URL, "sourceUrl": PAGE_URL, "title": "格聂神山",
        "fetchedAt": meta["fetchedAt"], "snapshotHash": meta["rawSha256"], "sourceUseMode": "factual_reference_only",
    }
    entity_schema = load_schema("publish", "entity")
    assert validate_strict(primary, entity_schema["properties"]["primarySource"], _root_schema=entity_schema) == []

    # 对照：百度百科 host 仍按其自身枚举登记；普通网页不是百科。
    assert acquire_module._platform_of({"sourceUrl": PAGE_URL}) == "头条百科"
    assert acquire_module._ingest_page({"sourceUrl": "https://you.ctrip.com/travels/x/1.html", "title": "游记",
                                        "sourceMarkdownPath": str(source_md), "license": "All rights reserved",
                                        "licenseUrl": "https://you.ctrip.com/", "creator": "某作者"})["sourceClass"] == "web_page"


def test_discovery_signals_are_transcribed_verbatim_and_never_judged(execution: Path, tmp_path: Path) -> None:
    source_md = _write(tmp_path / "downloads/genie.source.md", "# 格聂神山\n\n正文。\n")
    base = {
        "kind": "page", "sourceUrl": PAGE_URL, "title": "格聂神山", "sourceMarkdownPath": str(source_md),
        "license": "CC BY-SA 4.0", "licenseUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
        "creator": "头条百科编辑们", "relevance": "实体主页事实来源",
    }
    # 极低热度也照常 ingest：信号不参与任何判否。
    signals = {"ctripHeat": 0.1, "ctripReviews": 0, "flickrFaves": 0}
    manifest = _write(tmp_path / "ingest.json", _canonical({
        "schema": "quwoquan_data.ingest_manifest", "executionId": EXECUTION_ID,
        "targets": [{"targetRef": TARGET, "sources": [{**base, "discoverySignals": signals}]}],
    }))
    result = acquire_module.acquire(execution_id=EXECUTION_ID, request_path=manifest)
    assert result["ingested"] == 1
    refs = json.loads((execution / TARGET / "1.download/source_refs.json").read_bytes())
    unit = execution / refs["sources"][0]["metaRef"].rsplit("/", 1)[0]
    meta = json.loads((unit / "meta.json").read_bytes())
    assert meta["discoverySignals"] == signals
    assert meta["rawSha256"] == "sha256:" + hashlib.sha256(source_md.read_bytes()).hexdigest()

    # 非数值信号由 schema 拒绝；缺席时 meta 不含该键。
    bad = _write(tmp_path / "bad.json", _canonical({
        "schema": "quwoquan_data.ingest_manifest", "executionId": EXECUTION_ID,
        "targets": [{"targetRef": TARGET, "sources": [{**base, "discoverySignals": {"ctripHeat": "hot"}}]}],
    }))
    with pytest.raises(ValueError):
        acquire_module.acquire(execution_id=EXECUTION_ID, request_path=bad)
