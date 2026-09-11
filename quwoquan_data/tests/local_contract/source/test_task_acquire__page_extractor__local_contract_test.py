# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-037.t17
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-037.t18
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-037.t19
"""真实零网络取得保留宿主方法，冻结事实与百科身份不因方法改变。"""
from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from content.execution.author_bindings import AuthorBindingError, homepage_primary_source
from content.release.canonical import final_surface_projection as projection
from content.source import acquire
from core import paths
from core.schema import assert_valid, load_schema, validate_strict

EXECUTION_ID = "20260910--travel-homepage-extractor--local--pilot-001"
TARGET = "entities/地点/公园/北海公园"


def _write(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture
def local_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, dict]:
    monkeypatch.setattr(paths, "DATA_EXECUTIONS_ROOT", tmp_path / "tasks")
    monkeypatch.setenv("QWQ_LIBRARY_ROOT", str(tmp_path / "library"))

    def refuse(*_args, **_kwargs):
        raise AssertionError("取得本地正文不得出网")

    for name in ("socket", "create_connection", "getaddrinfo"):
        monkeypatch.setattr(socket, name, refuse)
    root = paths.execution_root(EXECUTION_ID)
    _write(root / "execution_manifest.json", {"schema": "quwoquan_data.content_execution_manifest", "executionId": EXECUTION_ID})
    _write(root / "0.plan/target_set.json", {
        "schema": "quwoquan_data.target_set", "executionId": EXECUTION_ID, "carrier": "homepage",
        "selectionPolicy": "frozen", "entityCatalogDigest": "sha256:" + "0" * 64,
        "candidateBinding": {"scope": "output", "ref": "fixture.json", "digest": "sha256:" + "1" * 64, "candidateCount": 1},
        "targetCount": 1, "targetRefs": [TARGET],
        "targets": [{"name": "北海公园", "entityType": "地点/公园", "region": "中国/北京市/西城区",
                     "entityId": "entity-beihai-park-beijing", "entityRef": "/entity/travel/beijing/beihai-park"}],
    })
    source = _write(tmp_path / "source.md", "# 北海公园\n\n网页工具摘录的皇家园林正文。\n\n## 信息区取证\n\n地点：北京。\n")
    request = {"schema": "quwoquan_data.ingest_manifest", "executionId": EXECUTION_ID, "targets": [{"targetRef": TARGET, "sources": [{
        "kind": "page", "sourceUrl": "https://zh.wikipedia.org/wiki/北海公园", "title": "北海公园",
        "sourceMarkdownPath": str(source), "license": "CC BY-SA 4.0", "licenseUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
        "creator": "维基百科贡献者", "relevance": "实体事实", "extractor": "html_text",
    }]}]}
    return root, tmp_path / "ingest.json", request


def test_explicit_html_method_survives_real_ingest_catalog_and_replay(local_source) -> None:
    root, request_path, request = local_source
    result = acquire.acquire(execution_id=EXECUTION_ID, request_path=_write(request_path, request))
    assert (result["ingested"], result["failed"]) == (1, 0), result
    rows = projection._source_rows(root, root / TARGET)
    assert rows[0]["meta"]["extractor"] == "html_text"
    assert_valid(rows[0]["meta"], "source", "atomic_source_unit_meta")
    catalog = projection._source_catalog(rows, entity_name="北海公园")
    primary = catalog["primarySource"]
    assert (primary["sourceKind"], primary["extractor"], primary["policyRevision"]) == ("wikipedia", "html_text", "encyclopedia-primary")
    schema = load_schema("publish", "entity")
    entity_primary = {key: value for key, value in primary.items() if key in schema["properties"]["primarySource"]["properties"]}
    assert validate_strict(entity_primary, schema["properties"]["primarySource"], _root_schema=schema) == []
    frozen = {p: p.read_bytes() for p in (root / "sources").glob("*/meta.json")}
    replay = acquire.acquire(execution_id=EXECUTION_ID, request_path=request_path)
    assert replay["failed"] == 0
    assert frozen == {p: p.read_bytes() for p in frozen}
    request["targets"][0]["sources"][0]["extractor"] = "wikipedia_api"
    conflict = acquire.acquire(execution_id=EXECUTION_ID, request_path=_write(request_path, request))
    assert conflict["failed"] == 1
    assert "CREATE_ONCE_CONFLICT" in json.dumps(conflict)
    assert frozen == {p: p.read_bytes() for p in frozen}


def test_method_cannot_promote_ordinary_webpage_to_encyclopedia(local_source) -> None:
    root, request_path, request = local_source
    request["targets"][0]["sources"][0]["sourceUrl"] = "https://example.org/park"
    result = acquire.acquire(execution_id=EXECUTION_ID, request_path=_write(request_path, request))
    assert result["failed"] == 0
    rows = projection._source_rows(root, root / TARGET)
    with pytest.raises(AuthorBindingError, match="百科"):
        homepage_primary_source({"primarySourceRef": rows[0]["sourceRef"]}, rows)


def test_unknown_method_is_rejected_before_ingest(local_source) -> None:
    _root, request_path, request = local_source
    request["targets"][0]["sources"][0]["extractor"] = "unverified_magic"
    with pytest.raises(ValueError):
        acquire.acquire(execution_id=EXECUTION_ID, request_path=_write(request_path, request))
