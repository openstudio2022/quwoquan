# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/content-pool-workbench/spec.md#gwt-001.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/content-pool-workbench/spec.md#gwt-001.t2
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/content-pool-workbench/spec.md#gwt-002.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/content-pool-workbench/spec.md#gwt-002.t2
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/content-pool-workbench/spec.md#gwt-003.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/content-pool-workbench/spec.md#gwt-003.t2
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/content-pool-workbench/spec.md#gwt-003.t3
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/content-pool-workbench/spec.md#gwt-006.t2
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/content-pool-workbench/spec.md#gwt-006.t3
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/content-pool-workbench/spec.md#gwt-004.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/content-pool-workbench/spec.md#gwt-004.t2
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/content-pool-workbench/spec.md#gwt-004.t3
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/content-pool-workbench/spec.md#gwt-004.t4
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/content-pool-workbench/spec.md#gwt-004.t5
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/content-pool-workbench/spec.md#gwt-005.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/content-pool-workbench/spec.md#gwt-005.t2
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/content-pool-workbench/spec.md#gwt-005.t3
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/content-pool-workbench/spec.md#gwt-006.t1
"""spec_ref: content-pool-workbench GWT-001, GWT-002, GWT-003, GWT-004, GWT-005."""
import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "quwoquan_data/scripts"))
from governance.content_workbench.service import WorkbenchError, WorkbenchService


def make_publish(tmp_path):
    root = tmp_path / "publish"
    root.mkdir()
    (root / "repository.json").write_text("{}")
    tags = root / "tags"
    for ref in ("Topic", "Topic/A", "Topic/B", "Topic/Zero"):
        path = tags / ref
        path.mkdir(parents=True, exist_ok=True)
        (path / "_definition.json").write_text(json.dumps({"label": path.name}))

    def obj(ref, oid, form, tag_refs, platform="declared-platform"):
        path = root / ref
        path.mkdir(parents=True)
        (path / "manifest.json").write_text(
            json.dumps(
                {
                    "contentId": oid,
                    "contentFormId": form,
                    "title": oid,
                    "tagRefs": tag_refs,
                    "sourceUrls": ["https://ignored-host.example/x"],
                    "sourceAttribution": {
                        "platform": platform,
                        "sourcePostUrl": "https://different-host.example/x",
                        "rightsBasis": "declared-license",
                        "attributionText": "declared attribution",
                    },
                    "assets": [],
                }
            )
        )
        return path

    article = obj("posts/article/x/p0001/a/1", "a", "article", ["Topic/A", "Topic/B"])
    (article / "article.md").write_text("# A body")
    (article / "content_review.json").write_text(
        json.dumps(
            {
                "decision": "approved",
                "qualityScores": {"fact_traceability": 5},
            }
        )
    )
    custom = obj("posts/custom/x/p0001/b/1", "b", "immersive-map", ["Topic/B"])
    (custom / "media").mkdir()
    (custom / "media" / "x.bin").write_bytes(b"abcdef")
    return root


def test_dynamic_forms_taxonomy_filters_pagination_quality_and_detail(tmp_path):
    """spec_ref: GWT-001 GWT-002 GWT-003"""
    publish = make_publish(tmp_path)
    service = WorkbenchService(publish, tmp_path / "ledger")
    overview = service.overview({"tagRefs": ["Topic"], "tagMatch": "subtree"})
    listing = service.query({"tagRefs": ["Topic"], "page": 1, "pageSize": 1})
    assert overview["total"] == listing["total"] == 2
    assert len(listing["items"]) == 1 and listing["pageSize"] == 1
    forms = {item["contentFormId"]: item for item in overview["contentForms"]}
    assert forms["article"]["rendererHint"]["known"] is True
    assert forms["immersive-map"]["rendererHint"] == {"kind": "generic", "known": False}
    topic = overview["taxonomy"][0]
    assert topic["count"] == 2
    assert next(item for item in topic["children"] if item["tagRef"] == "Topic/Zero")["count"] == 0
    assert service.query({"sources": ["declared-platform"], "query": "a"})["total"] == 1
    assert service.query({"tagRefs": ["Topic"], "tagMatch": "direct"})["total"] == 0
    assert overview["volume"]["textBytes"] > 0 and overview["volume"]["mediaBytes"] == 6
    assert overview["qualityScores"] == [{"contentFormId": "article", "dimension": "fact_traceability", "n": 1, "mean": 5.0, "distribution": {"1": 0, "2": 0, "3": 0, "4": 0, "5": 1}}]
    detail = service.detail("a", "R0")
    assert "viewports" not in detail
    assert detail["body"] == "# A body"
    assert detail["sourceDescriptors"][0]["platform"] == "declared-platform"
    assert detail["qualityScores"] == {"fact_traceability": 5}


def test_stale_read_review_correction_candidate_chain_and_isolation(tmp_path):
    """spec_ref: GWT-004 GWT-005"""
    publish = make_publish(tmp_path)
    staging = tmp_path / "staging"
    staging.mkdir()
    work = tmp_path / "ledger"
    service = WorkbenchService(publish, work, staging_root=staging)
    r0 = service.detail("a", "R0")["item"]
    with pytest.raises(WorkbenchError) as error:
        service.query({"readToken": "sha256:" + "0" * 64})
    assert error.value.code == "CONTENT_WORKBENCH.STALE_READ" and error.value.status == 409
    invalid = {"objectId": "a", "versionId": "R0", "businessDigest": r0["businessDigest"], "decision": "unqualified"}
    with pytest.raises(WorkbenchError) as error:
        service.save_review(invalid)
    assert error.value.code == "CONTENT_WORKBENCH.REVIEW_INVALID"
    payload = {**invalid, "changes": ["fix"], "targetState": "R1"}
    first = service.save_review(payload)
    assert service.save_review(payload) == first
    corrected = service.save_review({"objectId": "a", "versionId": "R0", "businessDigest": r0["businessDigest"], "decision": "qualified"})
    assert corrected["revision"] == 2 and corrected["previousDigest"] == first["recordDigest"]
    assert len(list((work / "reviews" / "records").rglob("*.json"))) == 1
    source = staging / "r1"
    source.mkdir()
    (source / "manifest.json").write_text(json.dumps({"objectId": "a", "contentFormId": "article", "title": "new", "tagRefs": []}))
    request = {"objectId": "a", "parentVersionId": "R0", "versionId": "R1", "sourcePath": "r1"}
    assert service.register_candidate(request) == service.register_candidate(request)
    r1 = service.detail("a", "R1")["item"]
    assert r1["reviewState"] == "pending_review"
    service.save_review({"objectId": "a", "versionId": "R1", "businessDigest": r1["businessDigest"], "decision": "qualified"})
    r2_source = staging / "r2"
    r2_source.mkdir()
    (r2_source / "manifest.json").write_text(json.dumps({"objectId": "a", "contentFormId": "article", "title": "r2", "tagRefs": []}))
    r2 = service.register_candidate({"objectId": "a", "parentVersionId": "R1", "versionId": "R2", "sourcePath": "r2"})
    assert r2["revision"] == 2 and service.detail("a", "R2")["item"]["reviewState"] == "pending_review"
    with pytest.raises(WorkbenchError) as error:
        WorkbenchService(publish, publish / "nested")
    assert error.value.code == "CONTENT_WORKBENCH.ROOT_OVERLAP"


def test_contracts_and_operations_are_single_track():
    """spec_ref: GWT-001 GWT-005"""
    directory = ROOT / "quwoquan_data/schema/governance/content_workbench"
    documents = {path.name: json.loads(path.read_text()) for path in directory.iterdir()}
    operations = documents["operations.json"]["operations"]
    assert [(item["method"], item["path"]) for item in operations] == [
        ("GET", "/api/overview"), ("GET", "/api/facets"), ("GET", "/api/items"),
        ("GET", "/api/items/{objectId}/{versionId}"),
        ("GET", "/api/media/{objectId}/{versionId}/{relativePath}"),
        ("POST", "/api/reviews"), ("POST", "/api/candidates"),
        ("POST", "/api/refresh"),
        ("GET", "/api/items/{objectId}/{versionId}/sources/{sourceUnitId}/evidence/{evidenceId}"),
    ]
    filter_properties = documents["workbench_filter.schema.json"]["properties"]
    assert {"query", "tagMatch", "sort", "page", "pageSize", "readToken"} <= filter_properties.keys()
    all_text = json.dumps(documents)
    assert "/api/workbench" not in all_text and "descendants" not in all_text


def test_read_models_schema_validates_all_service_responses(tmp_path):
    """spec_ref: GWT-001 GWT-002 GWT-003"""
    service = WorkbenchService(make_publish(tmp_path), tmp_path / "ledger")
    validator = Draft202012Validator(
        json.loads(
            (ROOT / "quwoquan_data/schema/governance/content_workbench/read_models.schema.json").read_text()
        )
    )
    responses = [
        service.overview(),
        service.facets(),
        service.query(),
        service.detail("a", "R0"),
    ]
    for response in responses:
        assert list(validator.iter_errors(response)) == []

def test_zero_argument_make_entry_builds_and_starts_isolated_loopback_workbench():
    """spec_ref: GWT-005 一键入口不要求调用者提供环境变量或 CLI 参数。"""
    makefile = (ROOT / "Makefile").read_text()
    recipe = makefile.split("content-workbench:", 1)[1].split("\n\n", 1)[0]
    assert "npm --prefix quwoquan_data/control_plane/content_workbench/portal ci --ignore-scripts" in recipe
    assert "npm --prefix quwoquan_data/control_plane/content_workbench/portal run build" in recipe
    assert "QWQ_PUBLISH_ROOT=" in recipe
    assert "QWQ_CONTENT_WORKBENCH_ROOT=" in recipe
    assert "QWQ_CONTENT_WORKBENCH_STAGING_ROOT=" in recipe
    assert "--host 127.0.0.1 --port 4319" in recipe
    assert "--publish-root" not in recipe and "--workbench-root" not in recipe



def test_snapshot_is_prewarmed_once_and_canonical_digest_skips_media_bytes(tmp_path, monkeypatch):
    publish = make_publish(tmp_path)
    original = Path.read_bytes
    media_reads = []
    def observed(path):
        if "media" in path.parts: media_reads.append(path)
        return original(path)
    monkeypatch.setattr(Path, "read_bytes", observed)
    service = WorkbenchService(publish, tmp_path / "ledger")
    token = service.startup_stats()["readToken"]
    assert service.startup_stats()["buildCount"] == 1
    import governance.content_workbench.service as service_module
    monkeypatch.setattr(service_module, "_manifest_dirs", lambda root: (_ for _ in ()).throw(AssertionError("unexpected pool scan")))
    service.overview(); service.facets(); service.query(); service.detail("a", "R0"); service.media_path("b", "R0", "media/x.bin")
    assert service.startup_stats()["buildCount"] == 1 and service.startup_stats()["readToken"] == token
    assert media_reads == []


def test_refresh_singleflight_stale_read_and_failure_keeps_old_snapshot(tmp_path, monkeypatch):
    import threading
    service = WorkbenchService(make_publish(tmp_path), tmp_path / "ledger")
    old = service.startup_stats()["readToken"]; entered = threading.Event(); release = threading.Event(); real = service._build_snapshot
    def slow(): entered.set(); release.wait(2); return real()
    monkeypatch.setattr(service, "_build_snapshot", slow)
    result = {}
    refresh_validator = Draft202012Validator(json.loads((ROOT / "quwoquan_data/schema/governance/content_workbench/local_api.schema.json").read_text())["$defs"]["refreshResponse"])
    thread = threading.Thread(target=lambda: result.update(service.refresh()))
    thread.start(); assert entered.wait(1); assert service.overview()["stale_read"] is True
    with pytest.raises(WorkbenchError) as error: service.refresh()
    assert error.value.code == "CONTENT_WORKBENCH.REFRESH_IN_PROGRESS"
    release.set(); thread.join()
    assert result["refreshed"] is True and list(refresh_validator.iter_errors(result)) == []
    refreshed_token = result["readToken"]
    def broken(): raise WorkbenchError("CONTENT_WORKBENCH.REFRESH_FAILED", "boom", 500)
    monkeypatch.setattr(service, "_build_snapshot", broken)
    with pytest.raises(WorkbenchError): service.refresh()
    assert service.startup_stats()["readToken"] == refreshed_token


def test_source_descriptor_default_and_safe_evidence_locator(tmp_path):
    publish = make_publish(tmp_path); item = publish / "posts/article/x/p0001/a/1"; source = item / "sources/s001"; source.mkdir(parents=True)
    body = b"# cited evidence"; (source / "evidence.md").write_bytes(body)
    (source / "source.json").write_text(json.dumps({"sourceId":"s001","sourceUrl":"https://example.test/a","sourceUseMode":"factual_reference_only","fetchedAt":"now","metadata":{"title":"Example","platform":"web"},"assets":[],"evidence":[{"path":"evidence.md","sha256":"sha256:"+__import__("hashlib").sha256(body).hexdigest(),"bytes":len(body),"kind":"source_excerpt"}]}))
    manifest = json.loads((item / "manifest.json").read_text()); manifest["citedSourceRefs"] = ["sources/s001/evidence.md"]; (item / "manifest.json").write_text(json.dumps(manifest))
    service = WorkbenchService(publish, tmp_path / "ledger")
    descriptor = service.detail("a", "R0")["sourceDescriptors"][0]
    assert descriptor["defaultEvidenceId"] == "e001" and descriptor["adopted"] is True
    assert descriptor["canonicalUrl"] == "https://example.test/a"
    assert descriptor["evidence"][0]["displayMode"] == "source-gfm"
    evidence = service.source_evidence("a", "R0", "s001", "e001")
    assert evidence["content"] == body.decode() and evidence["mediaType"] == "text/markdown"
    detail_source = (ROOT / "quwoquan_data/control_plane/content_workbench/portal/src/pages/WorkDetailPage.tsx").read_text()
    renderer_source = (ROOT / "quwoquan_data/control_plane/content_workbench/portal/src/shared/qwqRichMd.tsx").read_text()
    assert "ReactMarkdown" in renderer_source and "skipHtml" in renderer_source
    assert 'rel="noopener noreferrer"' in detail_source and "<iframe" not in detail_source
    (source / "evidence.md").write_text("drift")
    with pytest.raises(WorkbenchError) as error: service.source_evidence("a", "R0", "s001", "e001")
    assert error.value.code == "CONTENT_WORKBENCH.SOURCE_EVIDENCE_DIGEST_MISMATCH"


def test_source_descriptor_normalizes_non_https_and_does_not_invent_digest(tmp_path):
    publish = make_publish(tmp_path); item = publish / "posts/article/x/p0001/a/1"; source = item / "sources/s002"; source.mkdir(parents=True)
    (source / "evidence.txt").write_text("evidence")
    (source / "source.json").write_text(json.dumps({"sourceId":"s002","sourceUrl":"http://unsafe.test/a","sourceUseMode":"factual_reference_only","fetchedAt":"now","metadata":{},"assets":[],"evidence":[{"path":"evidence.txt","bytes":8,"kind":"source_excerpt"}]}))
    manifest = json.loads((item / "manifest.json").read_text()); manifest["citedSourceRefs"] = ["sources/s002/evidence.txt"]; (item / "manifest.json").write_text(json.dumps(manifest))
    service = WorkbenchService(publish, tmp_path / "ledger")
    detail = service.detail("a", "R0"); descriptor = next(row for row in detail["sourceDescriptors"] if row["sourceUnitId"] == "s002")
    assert descriptor["canonicalUrl"] is None and descriptor["evidenceState"] == "unreadable"
    assert descriptor["evidence"][0]["readStatus"] == "descriptor_invalid" and descriptor["defaultEvidenceId"] is None
    validator = Draft202012Validator(json.loads((ROOT / "quwoquan_data/schema/governance/content_workbench/read_models.schema.json").read_text()))
    assert list(validator.iter_errors(detail)) == []


def test_nearest_rank_p95_uses_the_29th_sorted_value_for_30_samples():
    """机制证明使用确定样本；真实浏览器 warm interaction 数值由 UAT 单独提供。"""
    samples = [3000, *range(29, 0, -1)]
    ordered = sorted(samples)
    rank = __import__("math").ceil(0.95 * len(ordered))
    p95 = ordered[rank - 1]
    assert len(samples) == 30 and rank == 29 and p95 == ordered[28] == 29
    assert p95 <= 3000


def test_workbench_reports_cold_warmup_refresh_and_warm_interaction_separately():
    makefile = (ROOT / "Makefile").read_text()
    recipe = makefile.split("content-workbench:", 1)[1].split("\n\n", 1)[0]
    ordered_phases = [
        recipe.index("run_phase frontend-install"),
        recipe.index("run_phase frontend-build"),
        recipe.index("START phase=backend-start-warmup"),
    ]
    assert ordered_phases == sorted(ordered_phases)
    spec = (ROOT / "specs/feature-tree/discovery-content/object-homepage-coverage-scaling/content-pool-workbench/spec.md").read_text()
    readme = (ROOT / "quwoquan_data/control_plane/content_workbench/portal/README.md").read_text()
    assert "安装、构建、进程启动、索引预热、显式 refresh 和 warm interaction 必须形成分栏结果" in spec
    assert "冷依赖安装、前端构建和 backend 启动预热分别输出实际耗时" in readme
    assert "显式刷新" in readme and "不应与安装、构建或启动预热合并" in readme


def _semantic_fixture(*, schema_version="1.0.0", extra_capability=None, node_kind="paragraph"):
    capabilities = ["parse.markdown", "parse.html", "serialize.markdown", "render.app", "render.web", "render.workbench", "author.editContent"]
    if extra_capability: capabilities.append(extra_capability)
    anchor = {"origin": "source-gfm", "start": 0, "end": 4, "selector": "p:1"}
    node = {"nodeId": "n1", "kind": node_kind, "disposition": "normalized", "policyVersion": "p1", "requiredCapabilities": capabilities, "losses": [], "semanticFingerprint": "node-fp", "sourceAnchor": anchor, "attributes": {"plainText": "正文"}, "inlines": []}
    return {"schemaVersion": schema_version, "dialectVersion": "1.0.0", "canonicalizationVersion": "1.0.0", "offsetEncoding": "unicode_scalar_value", "nodes": [node], "requiredCapabilities": capabilities, "assets": {}, "sourceMap": {"n1": anchor}, "policyVersion": "p1", "losses": [], "semanticFingerprint": "document-fp", "canonicalDigest": "digest"}


def test_fidelity_fields_sidecar_filters_and_wikipedia_canonical_identity(tmp_path):
    """canonical source.semantic.json 经 generated validator 后进入详情。"""
    publish = make_publish(tmp_path); item = publish / "posts/article/x/p0001/a/1"; source = item / "sources/zh_wikipedia__revision"; source.mkdir(parents=True)
    (source / "source.json").write_text(json.dumps({"sourceId": "zh_wikipedia", "sourceKind": "wikipedia", "sourceUrl": "https://zh.wikipedia.org/wiki/A", "sourceUseMode": "factual_reference_only", "sourceAttribution": {"platform": "错误展示平台"}, "evidence": []}))
    semantic = _semantic_fixture(); (source / "source.semantic.json").write_text(json.dumps(semantic))
    manifest_path = item / "manifest.json"; manifest = json.loads(manifest_path.read_text()); manifest.update({"citedSourceRefs": ["sources/zh_wikipedia__revision/source.json"], "markdownDialect": "qwq-rich-md", "modelBatch": "batch-7", "reviewGate": {"decision": "publish"}}); manifest_path.write_text(json.dumps(manifest))
    service = WorkbenchService(publish, tmp_path / "ledger"); detail = service.detail("a", "R0")
    assert detail["sourceDescriptors"][0]["platform"] == "Wikipedia"
    assert detail["semanticValidation"] == {"code": "ok", "detail": "", "publishEligible": True}
    assert [(node["kind"], node["attributes"]["plainText"], node["semanticFingerprint"]) for node in detail["semanticTree"]["nodes"]] == [("paragraph", "正文", "node-fp")]
    assert detail["item"]["semanticFingerprint"] == "document-fp"
    assert service.query({"modelBatches": ["batch-7"], "semanticFingerprints": ["document-fp"]})["total"] == 1


def test_generated_semantic_validator_fail_closed_for_unknown_version_capability_and_experimental(tmp_path):
    publish = make_publish(tmp_path); item = publish / "posts/article/x/p0001/a/1"; source = item / "sources/s001"; source.mkdir(parents=True)
    manifest_path = item / "manifest.json"; manifest = json.loads(manifest_path.read_text()); manifest["citedSourceRefs"] = ["sources/s001/source.json"]; manifest_path.write_text(json.dumps(manifest))
    (source / "source.json").write_text(json.dumps({"sourceId": "s001", "sourceUrl": "https://example.test", "sourceUseMode": "factual_reference_only", "evidence": []}))
    cases = [
        (_semantic_fixture(schema_version="2.0.0"), "SEMANTIC_DOCUMENT.INCOMPATIBLE.SCHEMA_MAJOR"),
        (_semantic_fixture(extra_capability="unknown.capability"), "SEMANTIC_DOCUMENT.CAPABILITY.MISSING"),
        (_semantic_fixture(node_kind="interactiveWidget"), "SEMANTIC_DOCUMENT.EXPERIMENTAL.PUBLISH_FORBIDDEN"),
    ]
    for index, (semantic, expected) in enumerate(cases):
        (source / "source.semantic.json").write_text(json.dumps(semantic)); service = WorkbenchService(publish, tmp_path / f"ledger-{index}"); detail = service.detail("a", "R0")
        assert detail["semanticTree"] is None and detail["semanticValidation"]["code"] == expected and detail["semanticValidation"]["publishEligible"] is False



# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/content-pool-workbench/spec.md#gwt-003.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/content-pool-workbench/spec.md#gwt-005.t1
def test_surface_diagnostics_aligns_source_and_product_ast_with_typed_authority(tmp_path):
    publish = make_publish(tmp_path); item = publish / "posts/article/x/p0001/a/1"; source = item / "sources/s001"; source.mkdir(parents=True)
    manifest_path = item / "manifest.json"; manifest = json.loads(manifest_path.read_text()); manifest.update({"citedSourceRefs": ["sources/s001/source.json"], "semanticDocumentRef": "semantic.document.json"}); manifest_path.write_text(json.dumps(manifest))
    source_ast = _semantic_fixture(); source_ast["nodes"].append({**source_ast["nodes"][0], "nodeId": "lost", "kind": "table", "semanticFingerprint": "source-table", "sourceAnchor": {"origin":"parsoid_html","start":5,"end":20,"selector":"table:1"}, "attributes":{"logicalGrid":[[{"header":True,"text":"A"}]]}}); source_ast["sourceMap"]["lost"] = source_ast["nodes"][1]["sourceAnchor"]
    target_ast = _semantic_fixture(); target_ast["nodes"][0] = {**target_ast["nodes"][0], "semanticFingerprint":"normalized-fp", "attributes":{"plainText":"规范化正文"}}
    target_ast["nodes"].append({**target_ast["nodes"][0], "nodeId":"added", "kind":"figure", "semanticFingerprint":"media-fp", "sourceAnchor":{"origin":"product","start":0,"end":0,"selector":"figure:1"}, "attributes":{"assetId":"asset-1","caption":"图注"}}); target_ast["sourceMap"]["added"] = target_ast["nodes"][1]["sourceAnchor"]
    (source / "source.semantic.json").write_text(json.dumps(source_ast)); (item / "semantic.document.json").write_text(json.dumps(target_ast))
    (source / "source.json").write_text(json.dumps({"sourceId":"s001","sourceUrl":"https://example.test","sourceUseMode":"factual_reference_only","evidence":[]}))
    review = json.loads((item / "content_review.json").read_text()); review["dispositions"] = [{"issueId":"i1","nodeId":"n1","reviewStatus":"human_decision_pending","actor":{"actorId":"reviewer","actorType":"independent_reviewer"},"reason":"需核对","protocol":{"schemaVersion":"1.0.0","dialectVersion":"1.0.0","canonicalizationVersion":"1.0.0"},"objectRevision":{"contentRevision":1,"sourceRevision":1,"layoutRevision":1}}]; (item / "content_review.json").write_text(json.dumps(review))
    decision = {"schema":"quwoquan_data.semantic_human_decision","decisionId":"d1","issueId":"i1","inputDigest":"sha256:"+"1"*64,"decision":"revise_content","actor":{"actorId":"human","actorType":"human_operator"},"reason":"修改","inputProtocol":{"schemaVersion":"1.0.0","dialectVersion":"1.0.0","canonicalizationVersion":"1.0.0"},"inputObjectRevision":{"contentRevision":1,"sourceRevision":1,"layoutRevision":1},"resultObjectRevision":{"contentRevision":2,"sourceRevision":1,"layoutRevision":1}}; (item / "semantic_human_decision.json").write_text(json.dumps(decision))
    service = WorkbenchService(publish, tmp_path / "ledger"); detail = service.detail("a", "R0")
    assert [row["alignmentStatus"] for row in detail["nodeDiff"]] == ["normalized", "missing", "added"]
    assert detail["nodeDiff"][1]["sourceNode"]["attributes"]["logicalGrid"][0][0]["text"] == "A"
    assert detail["nodeDiff"][2]["targetNode"]["attributes"]["caption"] == "图注"
    assert detail["canonicalDispositions"][0]["authority"] == "canonical_content_review"
    assert detail["canonicalHumanDecisions"][0]["authority"] == "canonical_human_decision"
    assert detail["offlineSuggestion"] is None
    saved = service.save_review({"objectId":"a","versionId":"R0","businessDigest":detail["item"]["businessDigest"],"decision":"unqualified","changes":["核对节点"],"targetState":"R1"})
    refreshed = service.detail("a", "R0")
    assert saved["decision"] == "unqualified" and refreshed["offlineSuggestion"]["authority"] == "workbench_offline_suggestion"
    assert refreshed["canonicalHumanDecisions"][0]["decisionId"] == "d1"


def test_source_evidence_descriptors_keep_missing_and_lazy_digest_drift_typed(tmp_path):
    import hashlib
    publish = make_publish(tmp_path); item = publish / "posts/article/x/p0001/a/1"; source = item / "sources/s001"; source.mkdir(parents=True)
    html = b'<script>alert(1)</script><table><tr><td>A</td></tr></table>'; (source / "source.parsoid.html").write_bytes(html)
    source_json = {"sourceId":"s001","sourceUrl":"https://example.test","sourceUseMode":"factual_reference_only","revision":42,"evidence":[{"evidenceId":"html","path":"source.parsoid.html","sha256":"sha256:"+hashlib.sha256(html).hexdigest(),"bytes":len(html),"kind":"parsoid_html"},{"evidenceId":"wiki","path":"source.wikitext","sha256":"sha256:"+"0"*64,"bytes":10,"kind":"wikitext"}]}; (source / "source.json").write_text(json.dumps(source_json))
    manifest = json.loads((item / "manifest.json").read_text()); manifest["citedSourceRefs"]=["sources/s001/source.json"]; (item / "manifest.json").write_text(json.dumps(manifest))
    service=WorkbenchService(publish,tmp_path/"ledger"); descriptor=service.detail("a","R0")["sourceDescriptors"][0]
    by_id={row["evidenceId"]:row for row in descriptor["evidence"]}; assert by_id["html"]["readStatus"]=="available" and by_id["html"]["displayMode"]=="raw" and by_id["html"]["revision"]==42; assert by_id["wiki"]["readStatus"]=="missing"
    assert service.source_evidence("a","R0","s001","html")["content"].startswith("<script>")
    (source / "source.parsoid.html").write_text("drift")
    with pytest.raises(WorkbenchError) as error: service.source_evidence("a","R0","s001","html")
    assert error.value.code == "CONTENT_WORKBENCH.SOURCE_EVIDENCE_DIGEST_MISMATCH"
