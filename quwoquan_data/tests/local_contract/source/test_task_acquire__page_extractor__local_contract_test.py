# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-037.t17
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-037.t18
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-037.t19
"""真实零网络取得保留宿主方法，冻结事实与百科身份不因方法改变。"""
from __future__ import annotations

import copy
import hashlib
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


@pytest.mark.parametrize("license_name,expected", [
    ("CC BY-SA 4.0", "verified"),
    ("权利未知；仅参考事实", "unverified"),
    ("Copyright reserved", "unverified"),
])
def test_page_report_records_license_without_claiming_default_verification(local_source, license_name, expected):
    root, request_path, request = local_source
    source = request["targets"][0]["sources"][0]
    source["license"] = license_name
    result = acquire.acquire(execution_id=EXECUTION_ID, request_path=_write(request_path, request))
    assert result["failed"] == 0
    assert result["targets"][0]["sources"][0]["rightsStatus"] == expected
    originals = {p: p.read_bytes() for p in (root / "sources").rglob("*") if p.is_file()}
    repeated = acquire.acquire(execution_id=EXECUTION_ID, request_path=request_path)
    assert repeated["targets"][0]["sources"][0]["rightsStatus"] == expected
    assert all(p.read_bytes() == body for p, body in originals.items())


def test_method_cannot_promote_ordinary_webpage_to_encyclopedia(local_source) -> None:
    root, request_path, request = local_source
    request["targets"][0]["sources"][0]["sourceUrl"] = "https://example.org/park"
    result = acquire.acquire(execution_id=EXECUTION_ID, request_path=_write(request_path, request))
    assert result["failed"] == 0
    rows = projection._source_rows(root, root / TARGET)
    with pytest.raises(AuthorBindingError, match="百科"):
        homepage_primary_source({"primarySourceRef": rows[0]["sourceRef"]}, rows)


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-045

def _work_input(request_path: Path, source: dict) -> dict:
    response = _write(request_path.parent / "response.json", '{"id":"park-1","images":["b","a"],"icon":"unselected"}')
    source["sourceWork"] = {
        "version": 1, "identity": {"provider": "fixture", "nativeId": "park-1", "pageUrl": source["sourceUrl"]},
        "capture": {"method": "api_response", "coverage": "partial", "scope": "仅已取得的两张图和正文", "evidenceRefs": ["response"]},
        "structure": [
            {"ref": source["sourceUrl"], "role": "gallery", "members": ["https://example.org/b.jpg", "https://example.org/a.jpg"]},
            {"ref": "https://example.org/b.jpg", "role": "cover"},
            {"ref": "https://example.org/b.jpg", "role": "inline", "anchor": "response.images[0]"},
        ],
    }
    source["sourceWorkEvidence"] = [{"id": "response", "inputPath": str(response), "kind": "source_response",
        "sha256": "sha256:" + hashlib.sha256(response.read_bytes()).hexdigest(), "bytes": response.stat().st_size}]
    return source


def test_source_work_preserves_response_order_and_legacy_identity(local_source) -> None:
    root, request_path, request = local_source
    source = _work_input(request_path, request["targets"][0]["sources"][0])
    result = acquire.acquire(execution_id=EXECUTION_ID, request_path=_write(request_path, request))
    assert result["failed"] == 0, result
    unit = root / "sources" / result["targets"][0]["sources"][0]["sourceUnitId"]
    meta = json.loads((unit / "meta.json").read_bytes())
    assert meta["sourceWork"] == source["sourceWork"]
    binding = meta["sourceWorkEvidence"][0]
    assert "inputPath" not in binding
    assert (unit / binding["path"]).read_bytes() == Path(source["sourceWorkEvidence"][0]["inputPath"]).read_bytes()
    assert meta["rawSha256"] == "sha256:" + hashlib.sha256(Path(source["sourceMarkdownPath"]).read_bytes()).hexdigest()
    assert acquire.acquire(execution_id=EXECUTION_ID, request_path=request_path)["failed"] == 0
    assert (unit / "meta.json").read_bytes() == acquire._canonical(meta)


@pytest.mark.parametrize("change", ["coverage", "order", "evidence", "remove"])
def test_source_work_replay_rejects_changed_facts(local_source, change) -> None:
    root, request_path, request = local_source
    source = _work_input(request_path, request["targets"][0]["sources"][0])
    assert acquire.acquire(execution_id=EXECUTION_ID, request_path=_write(request_path, request))["failed"] == 0
    frozen = {p: p.read_bytes() for p in (root / "sources").glob("*/meta.json")}
    if change == "coverage":
        source["sourceWork"]["capture"]["coverage"] = "complete"
    elif change == "order":
        source["sourceWork"]["structure"][0]["members"].reverse()
    elif change == "remove":
        source.pop("sourceWork")
        source.pop("sourceWorkEvidence")
    else:
        row = source["sourceWorkEvidence"][0]
        Path(row["inputPath"]).write_bytes(b"changed actual response")
        row.update(sha256="sha256:" + hashlib.sha256(Path(row["inputPath"]).read_bytes()).hexdigest(), bytes=Path(row["inputPath"]).stat().st_size)
    result = acquire.acquire(execution_id=EXECUTION_ID, request_path=_write(request_path, request))
    assert "CREATE_ONCE_CONFLICT" in json.dumps(result), result
    assert frozen == {p: p.read_bytes() for p in frozen}


@pytest.mark.parametrize("change", ["digest", "bytes", "missing", "symlink", "parent_symlink", "dangling", "duplicate_id", "mislabeled_excerpt"])
def test_source_work_rejects_invalid_original_evidence(local_source, change) -> None:
    _root, request_path, request = local_source
    source = _work_input(request_path, request["targets"][0]["sources"][0])
    row = source["sourceWorkEvidence"][0]
    original = Path(row["inputPath"])
    if change == "digest":
        row["sha256"] = "sha256:" + "0" * 64
    elif change == "bytes":
        row["bytes"] += 1
    elif change == "missing":
        original.unlink()
    elif change == "symlink":
        alias = original.with_name("alias.json")
        alias.symlink_to(original)
        row["inputPath"] = str(alias)
    elif change == "parent_symlink":
        alias = original.parent / "alias-dir"
        alias.symlink_to(original.parent, target_is_directory=True)
        row["inputPath"] = str(alias / original.name)
    elif change == "mislabeled_excerpt":
        row["inputPath"] = source["sourceMarkdownPath"]
        body = Path(row["inputPath"]).read_bytes()
        row.update(bytes=len(body), sha256="sha256:" + hashlib.sha256(body).hexdigest())
    elif change == "dangling":
        source["sourceWork"]["capture"]["evidenceRefs"] = ["absent"]
    else:
        source["sourceWorkEvidence"].append(copy.deepcopy(row))
    result = acquire.acquire(execution_id=EXECUTION_ID, request_path=_write(request_path, request))
    assert result["failed"] == 1, result
    assert "SOURCE_WORK" in json.dumps(result), result


@pytest.mark.parametrize("mutation", ["duplicate_members", "missing_members", "wrong_members", "version"])
def test_source_work_shared_schema_rejects_invalid_structure(local_source, mutation) -> None:
    _root, request_path, request = local_source
    work = _work_input(request_path, request["targets"][0]["sources"][0])["sourceWork"]
    if mutation == "duplicate_members":
        work["structure"][0]["members"] *= 2
    elif mutation == "missing_members":
        work["structure"][0].pop("members")
    elif mutation == "wrong_members":
        work["structure"][1]["members"] = ["https://example.org/a.jpg"]
    else:
        work["version"] = 2
    with pytest.raises(ValueError):
        assert_valid(work, "source", "source_work")


def test_source_work_media_metadata_and_frozen_evidence_replay(local_source) -> None:
    from PIL import Image
    root, request_path, request = local_source
    image = request_path.parent / "image.png"
    Image.new("RGB", (4, 4), "blue").save(image)
    source = request["targets"][0]["sources"][0]
    source.pop("sourceMarkdownPath")
    source.pop("title")
    source.pop("extractor")
    source.update(kind="image", directUrl="https://example.org/image.png", filePath=str(image),
                  watermarkStatus="absent", watermarkKind="none")
    _work_input(request_path, source)
    source["sourceWorkEvidence"][0]["kind"] = "source_metadata"
    result = acquire.acquire(execution_id=EXECUTION_ID, request_path=_write(request_path, request))
    assert result["failed"] == 0, result
    unit = root / "sources" / result["targets"][0]["sources"][0]["sourceUnitId"]
    meta = json.loads((unit / "meta.json").read_bytes())
    assert meta["rawSha256"] == "sha256:" + hashlib.sha256(image.read_bytes()).hexdigest()
    assert meta["sourceWork"] == source["sourceWork"]
    (unit / meta["sourceWorkEvidence"][0]["path"]).write_bytes(b"frozen original drift")
    result = acquire.acquire(execution_id=EXECUTION_ID, request_path=request_path)
    assert "SOURCE_WORK_EVIDENCE_DRIFT" in json.dumps(result), result


def test_undeclared_source_work_keeps_exact_identity_on_replay(local_source) -> None:
    root, request_path, request = local_source
    result = acquire.acquire(execution_id=EXECUTION_ID, request_path=_write(request_path, request))
    unit_id = result["targets"][0]["sources"][0]["sourceUnitId"]
    meta_path = root / "sources" / unit_id / "meta.json"
    original = meta_path.read_bytes()
    assert "sourceWork" not in json.loads(original)
    assert "sourceWorkEvidence" not in json.loads(original)
    assert acquire.acquire(execution_id=EXECUTION_ID, request_path=request_path) == result
    assert meta_path.read_bytes() == original
    _work_input(request_path, request["targets"][0]["sources"][0])
    conflict = acquire.acquire(execution_id=EXECUTION_ID, request_path=_write(request_path, request))
    assert "CREATE_ONCE_CONFLICT" in json.dumps(conflict), conflict
    assert meta_path.read_bytes() == original


def test_native_member_ids_survive_download_url_changes(local_source) -> None:
    root, request_path, request = local_source
    source = _work_input(request_path, request["targets"][0]["sources"][0])
    work = source["sourceWork"]
    work["structure"] = [
        {"ref": "work:park-1", "role": "gallery", "members": ["photo:b", "photo:a"]},
        {"ref": "photo:b", "role": "cover"},
        {"ref": "photo:b", "role": "inline", "anchor": "正文第2段"},
        {"ref": "https://example.org/reference", "role": "reference"},
    ]
    frozen_structure = copy.deepcopy(work["structure"])
    row = source["sourceWorkEvidence"][0]
    for query in ("size=small&signature=one", "size=large&signature=two"):
        response = {"images": [{"id": member, "downloadUrl": f"https://example.org/{member}?{query}"}
                               for member in work["structure"][0]["members"]]}
        body = json.dumps(response).encode()
        Path(row["inputPath"]).write_bytes(body)
        row.update(sha256="sha256:" + hashlib.sha256(body).hexdigest(), bytes=len(body))
        assert_valid(request, "source", "ingest_manifest")
        assert work["structure"] == frozen_structure
    result = acquire.acquire(execution_id=EXECUTION_ID, request_path=_write(request_path, request))
    assert result["failed"] == 0, result
    unit = root / "sources" / result["targets"][0]["sources"][0]["sourceUnitId"]
    assert json.loads((unit / "meta.json").read_bytes())["sourceWork"]["structure"] == frozen_structure


@pytest.mark.parametrize("ref", ["photo:b", "http://example.org/ref", "file:///tmp/source", "https://", "https:///bad", "https://?query"])
def test_reference_usage_requires_https_link(local_source, ref) -> None:
    _, request_path, request = local_source
    work = _work_input(request_path, request["targets"][0]["sources"][0])["sourceWork"]
    work["structure"] = [{"ref": ref, "role": "reference"}]
    with pytest.raises(ValueError):
        assert_valid(work, "source", "source_work")


@pytest.mark.parametrize("kind", ["page", "image"])
@pytest.mark.parametrize("removed", ["sourceWork", "sourceWorkEvidence"])
def test_source_work_ingest_requires_paired_transport(local_source, kind, removed) -> None:
    _, request_path, request = local_source
    source = _work_input(request_path, request["targets"][0]["sources"][0])
    if kind == "image":
        for key in ("title", "extractor", "sourceMarkdownPath"):
            source.pop(key)
        source.update(kind="image", directUrl="https://example.org/image.png", filePath="local.png",
                      watermarkStatus="absent", watermarkKind="none")
    source.pop(removed)
    with pytest.raises(ValueError):
        assert_valid(request, "source", "ingest_manifest")


@pytest.mark.parametrize("removed", ["sourceWork", "sourceWorkEvidence"])
def test_source_work_meta_requires_paired_transport(local_source, removed) -> None:
    root, request_path, request = local_source
    _work_input(request_path, request["targets"][0]["sources"][0])
    result = acquire.acquire(execution_id=EXECUTION_ID, request_path=_write(request_path, request))
    assert result["failed"] == 0, result
    unit = root / "sources" / result["targets"][0]["sources"][0]["sourceUnitId"]
    meta = json.loads((unit / "meta.json").read_bytes())
    meta.pop(removed)
    with pytest.raises(ValueError):
        assert_valid(meta, "source", "atomic_source_unit_meta")


@pytest.mark.parametrize("bad_path", ["/workspace/response.json", "../response.json", "evidence/response.json"])
def test_stored_and_published_evidence_reject_nonlocal_paths(local_source, bad_path) -> None:
    root, request_path, request = local_source
    _work_input(request_path, request["targets"][0]["sources"][0])
    result = acquire.acquire(execution_id=EXECUTION_ID, request_path=_write(request_path, request))
    assert result["failed"] == 0, result
    unit = root / "sources" / result["targets"][0]["sources"][0]["sourceUnitId"]
    meta = json.loads((unit / "meta.json").read_bytes())
    binding = meta["sourceWorkEvidence"][0]
    binding["path"] = bad_path
    with pytest.raises(ValueError):
        assert_valid(meta, "source", "atomic_source_unit_meta")
    document = {"schema": "quwoquan_data.publish_source", "sourceId": "fixture", "sourceUrl": meta["canonicalUrl"],
                "sourceUseMode": meta["sourceUseMode"], "fetchedAt": meta["fetchedAt"], "metadata": {}, "assets": [],
                "sourceWork": meta["sourceWork"], "evidence": [binding]}
    with pytest.raises(ValueError):
        assert_valid(document, "publish", "source")


def test_unknown_method_is_rejected_before_ingest(local_source) -> None:
    _root, request_path, request = local_source
    request["targets"][0]["sources"][0]["extractor"] = "unverified_magic"
    with pytest.raises(ValueError):
        acquire.acquire(execution_id=EXECUTION_ID, request_path=_write(request_path, request))
