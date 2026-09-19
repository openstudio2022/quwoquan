# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/content-pool-workbench/spec.md#gwt-001.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/content-pool-workbench/spec.md#gwt-002.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/content-pool-workbench/spec.md#gwt-003.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/content-pool-workbench/spec.md#gwt-004.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/content-pool-workbench/spec.md#gwt-005.t1
"""spec_ref: content-pool-workbench GWT-001..005 API integration."""
import json
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "quwoquan_data/scripts"))
from governance.content_workbench.http_server import serve
from governance.content_workbench.service import WorkbenchError, WorkbenchService


def request_json(url, data=None):
    request = urllib.request.Request(
        url,
        data=json.dumps(data).encode() if data is not None else None,
        headers={"Content-Type": "application/json"},
        method="POST" if data is not None else "GET",
    )
    return json.load(urllib.request.urlopen(request))


def test_canonical_http_paths_filters_detail_media_review_and_stale(tmp_path):
    """spec_ref: GWT-001 GWT-002 GWT-003 GWT-004 GWT-005"""
    publish = tmp_path / "publish"
    item_dir = publish / "posts/custom/x/p0001/name/1"
    (item_dir / "media").mkdir(parents=True)
    (publish / "tags/Topic/A").mkdir(parents=True)
    (publish / "tags/Topic/_definition.json").write_text(json.dumps({"label": "Topic"}))
    (publish / "tags/Topic/A/_definition.json").write_text(json.dumps({"label": "A"}))
    (publish / "repository.json").write_text("{}")
    (item_dir / "manifest.json").write_text(json.dumps({"contentId": "id/with/slash", "contentFormId": "future-form", "title": "T", "tagRefs": ["Topic/A"], "sourceAttribution": {"platform": "declared", "sourcePostUrl": "https://host.example/x"}, "assets": [{"fileName": "x.bin", "mimeType": "application/octet-stream"}]}))
    (item_dir / "media/x.bin").write_bytes(b"abcdef")
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("UI")
    service = WorkbenchService(publish, tmp_path / "ledger")
    server = serve(service, static)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        overview = request_json(base + "/api/overview")
        assert overview["stale_read"] is False and overview["sources"] == [{"value": "declared", "count": 1}]
        facets = request_json(base + "/api/facets?tagRefs=Topic&tagMatch=subtree")
        assert facets["total"] == 1 and facets["taxonomy"][0]["count"] == 1
        listing = request_json(base + "/api/items?query=T&page=1&pageSize=1&sort=title_asc")
        assert listing["total"] == 1 and listing["pageSize"] == 1
        item = listing["items"][0]
        object_id = urllib.parse.quote(item["objectId"], safe="")
        detail = request_json(base + f"/api/items/{object_id}/R0")
        assert detail["item"]["objectRef"] and detail["media"][0]["url"].startswith(f"/api/media/{object_id}/R0/")
        review = request_json(base + "/api/reviews", {"objectId": item["objectId"], "versionId": "R0", "businessDigest": item["businessDigest"], "decision": "qualified", "changes": [], "targetState": ""})
        assert review["decision"] == "qualified"
        media_request = urllib.request.Request(base + detail["media"][0]["url"], headers={"Range": "bytes=1-3"})
        response = urllib.request.urlopen(media_request)
        assert response.status == 206 and response.read() == b"bcd"
        assert "app;dur=" in response.headers["Server-Timing"]
        refreshed = request_json(base + "/api/refresh", {})
        assert refreshed["refreshed"] is True and set(refreshed) == {"readToken", "stale_read", "refreshed"}
        stale = urllib.parse.quote("sha256:" + "0" * 64)
        with pytest_http_error(409) as error:
            urllib.request.urlopen(base + f"/api/items?readToken={stale}")
        payload = json.load(error.value)
        assert payload["error"]["code"] == "CONTENT_WORKBENCH.STALE_READ"
        with pytest_http_error(404):
            urllib.request.urlopen(base + "/api/workbench/items")
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


class pytest_http_error:
    def __init__(self, status):
        self.status = status
        self.value = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        assert isinstance(exc, urllib.error.HTTPError) and exc.code == self.status
        self.value = exc
        return True


def test_http_filter_schema_rejects_duplicate_values(tmp_path):
    publish = tmp_path / "publish"
    publish.mkdir()
    (publish / "repository.json").write_text("{}")
    static = tmp_path / "static"
    static.mkdir()
    server = serve(WorkbenchService(publish, tmp_path / "ledger"), static)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pytest_http_error(400) as error:
            urllib.request.urlopen(
                f"http://127.0.0.1:{server.server_port}/api/items?versions=R0&versions=R0"
            )
        payload = json.load(error.value)
        assert payload["error"]["code"] == "CONTENT_WORKBENCH.REQUEST_INVALID"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_non_loopback_is_rejected(tmp_path):
    """spec_ref: GWT-005"""
    publish = tmp_path / "p"
    publish.mkdir()
    static = tmp_path / "s"
    static.mkdir()
    service = WorkbenchService(publish, tmp_path / "w")
    try:
        serve(service, static, "0.0.0.0")
    except WorkbenchError as exc:
        assert exc.code == "CONTENT_WORKBENCH.NON_LOOPBACK"
    else:
        assert False


def test_source_evidence_http_route_and_timing(tmp_path):
    import hashlib
    publish = tmp_path / "publish"; item = publish / "posts/article/x/p0001/name/1"; source = item / "sources/s001"
    source.mkdir(parents=True); (publish / "repository.json").write_text("{}")
    body = b"# source"; (source / "evidence.md").write_bytes(body)
    (source / "source.json").write_text(json.dumps({"sourceId":"s001","sourceUrl":"https://example.test","sourceUseMode":"factual_reference_only","fetchedAt":"now","metadata":{},"assets":[],"evidence":[{"path":"evidence.md","sha256":"sha256:"+hashlib.sha256(body).hexdigest(),"bytes":len(body),"kind":"source_excerpt"}]}))
    (item / "manifest.json").write_text(json.dumps({"contentId":"id","contentFormId":"article","title":"T","tagRefs":[],"citedSourceRefs":["sources/s001/evidence.md"],"assets":[]}))
    static = tmp_path / "static"; static.mkdir(); (static / "index.html").write_text("UI")
    server = serve(WorkbenchService(publish, tmp_path / "ledger"), static); thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        response = urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/api/items/id/R0/sources/s001/evidence/e001")
        assert json.load(response)["content"] == "# source" and "app;dur=" in response.headers["Server-Timing"]
    finally:
        server.shutdown(); server.server_close(); thread.join()


def test_static_spa_history_fallback_preserves_assets_and_api_boundary(tmp_path):
    publish = tmp_path / "publish"; publish.mkdir(); (publish / "repository.json").write_text("{}")
    static = tmp_path / "static"; static.mkdir(); (static / "index.html").write_text("<main>WORKBENCH SPA</main>")
    assets = static / "assets"; assets.mkdir(); (assets / "app.js").write_text("window.app = true")
    server = serve(WorkbenchService(publish, tmp_path / "ledger"), static)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        direct = urllib.request.urlopen(base + "/works/object%2Fkey")
        assert direct.status == 200 and direct.read() == b"<main>WORKBENCH SPA</main>"
        asset = urllib.request.urlopen(base + "/assets/app.js")
        assert asset.status == 200 and asset.read() == b"window.app = true"
        with pytest_http_error(404) as missing_asset:
            urllib.request.urlopen(base + "/assets/missing.js")
        assert "text/html" in missing_asset.value.headers.get("Content-Type", "")
        with pytest_http_error(404) as missing_api:
            urllib.request.urlopen(base + "/api/not-a-route")
        assert missing_api.value.headers.get_content_type() == "application/json"
        assert json.load(missing_api.value)["error"]["code"] == "CONTENT_WORKBENCH.NOT_FOUND"
        with pytest_http_error(404):
            urllib.request.urlopen(base + "/%2e%2e/secret")
    finally:
        server.shutdown(); server.server_close(); thread.join()


def test_source_semantic_generated_validation_survives_http_projection(tmp_path):
    """同一 source.semantic fixture 经 Python generated validator 与 API 保持 kind/order/text/fingerprint。"""
    publish = tmp_path / "publish"; item = publish / "posts/article/x/p0001/name/1"; source = item / "sources/s001"
    source.mkdir(parents=True); (publish / "repository.json").write_text("{}")
    capabilities = ["parse.markdown", "parse.html", "serialize.markdown", "render.app", "render.web", "render.workbench", "author.editContent"]
    anchor = {"origin": "source-gfm", "start": 0, "end": 4, "selector": "p:1"}
    nodes = [
        {"nodeId": "n1", "kind": "heading", "disposition": "normalized", "policyVersion": "p1", "requiredCapabilities": capabilities + ["author.editStructure"], "losses": [], "semanticFingerprint": "heading-fp", "sourceAnchor": anchor, "attributes": {"plainText": "标题", "level": 2}, "inlines": []},
        {"nodeId": "n2", "kind": "paragraph", "disposition": "normalized", "policyVersion": "p1", "requiredCapabilities": capabilities, "losses": [], "semanticFingerprint": "paragraph-fp", "sourceAnchor": anchor, "attributes": {"plainText": "正文"}, "inlines": []},
    ]
    declared = sorted(set(capabilities + ["author.editStructure"]))
    semantic = {"schemaVersion": "1.0.0", "dialectVersion": "1.0.0", "canonicalizationVersion": "1.0.0", "offsetEncoding": "unicode_scalar_value", "nodes": nodes, "requiredCapabilities": declared, "assets": {}, "sourceMap": {node["nodeId"]: anchor for node in nodes}, "policyVersion": "p1", "losses": [], "semanticFingerprint": "document-fp", "canonicalDigest": "digest"}
    (source / "source.semantic.json").write_text(json.dumps(semantic)); (source / "source.json").write_text(json.dumps({"sourceId": "s001", "sourceUrl": "https://example.test", "sourceUseMode": "factual_reference_only", "evidence": []}))
    (item / "manifest.json").write_text(json.dumps({"contentId": "id", "contentFormId": "article", "title": "T", "tagRefs": [], "citedSourceRefs": ["sources/s001/source.json"], "assets": []}))
    static = tmp_path / "static"; static.mkdir(); (static / "index.html").write_text("UI")
    server = serve(WorkbenchService(publish, tmp_path / "ledger"), static); thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        detail = request_json(f"http://127.0.0.1:{server.server_port}/api/items/id/R0")
        assert detail["semanticValidation"] == {"code": "ok", "detail": "", "publishEligible": True}
        assert [(node["kind"], node["attributes"]["plainText"], node["semanticFingerprint"]) for node in detail["semanticTree"]["nodes"]] == [("heading", "标题", "heading-fp"), ("paragraph", "正文", "paragraph-fp")]
        assert detail["semanticTree"]["semanticFingerprint"] == "document-fp"
    finally:
        server.shutdown(); server.server_close(); thread.join()


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/content-pool-workbench/spec.md#gwt-003.t1
def test_detail_diagnostics_payload_and_operations_have_no_publish_commands(tmp_path):
    publish=tmp_path/'publish'; item=publish/'posts/article/x/p0001/name/1'; source=item/'sources/s1'; source.mkdir(parents=True); (publish/'repository.json').write_text('{}')
    capabilities=["parse.markdown","parse.html","serialize.markdown","render.app","render.web","render.workbench","author.editContent"] ; anchor={"origin":"source.wikitext","start":0,"end":4,"selector":"p:1"}; node={"nodeId":"n1","kind":"paragraph","disposition":"preserved","policyVersion":"p1","requiredCapabilities":capabilities,"losses":[],"semanticFingerprint":"fp","sourceAnchor":anchor,"attributes":{"plainText":"正文"},"inlines":[]}; semantic={"schemaVersion":"1.0.0","dialectVersion":"1.0.0","canonicalizationVersion":"1.0.0","offsetEncoding":"unicode_scalar_value","nodes":[node],"requiredCapabilities":capabilities,"assets":{},"sourceMap":{"n1":anchor},"policyVersion":"p1","losses":[],"semanticFingerprint":"doc-fp","canonicalDigest":"digest"}
    (source/'source.semantic.json').write_text(json.dumps(semantic)); (source/'source.json').write_text(json.dumps({"sourceId":"s1","sourceUrl":"https://example.test","sourceUseMode":"factual_reference_only","evidence":[]})); (item/'manifest.json').write_text(json.dumps({"contentId":"id","contentFormId":"article","title":"T","tagRefs":[],"citedSourceRefs":["sources/s1/source.json"],"assets":[]}))
    static=tmp_path/'static'; static.mkdir(); (static/'index.html').write_text('UI'); server=serve(WorkbenchService(publish,tmp_path/'ledger'),static); thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    try:
        detail=request_json(f'http://127.0.0.1:{server.server_port}/api/items/id/R0'); assert detail['nodeDiff'][0]['alignmentStatus']=='preserved'; assert detail['sourceSemanticTree']['semanticFingerprint']==detail['semanticTree']['semanticFingerprint']=='doc-fp'; assert detail['offlineSuggestion'] is None
        operations=json.loads((ROOT/'quwoquan_data/schema/governance/content_workbench/operations.json').read_text())['operations']; forbidden={'publish','promote','release','activate','import','deploy'}; assert not any(any(word in (row['operationId']+row['path']).lower() for word in forbidden) for row in operations)
    finally: server.shutdown(); server.server_close(); thread.join()
