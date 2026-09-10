# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-039.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-039.t3
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-039.t4
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-039.t5
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-039.t6
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-039.t7
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-039.t8
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-040.t2
"""Skill 来源工具离线回放；真实 CLI 输入 schema，零生产数据与来源网络。"""
import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[4]
SKILL = ROOT / ".agents/skills/content-production"
sys.path.insert(0, str(SKILL / "scripts"))
_spec = importlib.util.spec_from_file_location("producer_inputs_test", SKILL / "scripts/inputs.py")
subject = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(subject)
sys.modules["inputs"] = subject
import producer


def jpeg():
    result = io.BytesIO()
    Image.new("RGB", (32, 24), "green").save(result, format="JPEG")
    return result.getvalue()


def work():
    body = {"postList": [{"post_id": "138766711", "url": "https://tuchong.com/26553952/138766711/", "title": "赏秋",
                         "site": {"site_id": 26553952, "name": "和风不语"}, "images": [
                             {"user_id": 1, "img_id": 1271483541, "width": 4096, "height": 3000},
                             {"user_id": 1, "img_id": 792611521, "width": 4096, "height": 3000}]}]}
    rows, _ = subject.load("image", "tuchong").parse(json.dumps(body).encode(), {})
    subject.validate(rows, SKILL / "carriers/image/schemas/candidate.schema.json")
    return rows[0]


def selection(row):
    return {"carrier": "image", "executionId": "20260908--travel-image-work--sichuan-r01--pilot-001", "targets": [{
        "target": {"carrier": "image", "entityType": "地点/自然景观", "name": "秋山", "entityId": "entity-qiushan-sichuan", "entityRef": "/entity/travel/sichuan/qiushan", "publishAngle": "风光", "publishTitle": "赏秋"},
        "sources": [{"candidateId": row["id"], "relevance": "作品页与山景一致", "license": "版权保留", "licenseUrl": "https://tuchong.com/agreement/",
                     "creator": "和风不语", "assets": [{"id": a["id"], "watermarkStatus": "unknown", "watermarkKind": "unknown"} for a in row["assets"]]}]}]}


class Fetch:
    def __init__(self):
        self.calls = []

    def get(self, url, **kw):
        self.calls.append(url)
        return jpeg()

    def chunks(self, url, **kw):
        body = self.get(url, **kw)
        for start in range(0, len(body), 37):
            yield body[start:start + 37]


def test_native_work_has_two_assets_and_one_real_ingest_target(tmp_path):
    row = work()
    assert len(row["assets"]) == 2
    choose = selection(row)
    fetch = Fetch()
    downloaded = producer.download(tmp_path, {"image": {row["id"]: row}}, [choose], fetch, 100000)
    outputs = subject.build(tmp_path, [choose], {"image": {row["id"]: row}}, downloaded)
    ingest = outputs["image/ingest.json"]
    assert len(ingest["targets"]) == 1
    assert [src["directUrl"] for src in ingest["targets"][0]["sources"]] == [a["directUrl"] for a in row["assets"]]
    assert len(outputs["round.json"]["targets"]) == 1
    assert all(d["width"] == 32 for d in downloaded["image"].values())
    producer.download(tmp_path, {"image": {row["id"]: row}}, [choose], fetch, 100000)
    assert len(fetch.calls) == 2


@pytest.mark.parametrize("carrier", ["homepage", "article", "image", "video"])
@pytest.mark.parametrize("missing", ["entityId", "entityRef"])
def test_selection_missing_explicit_identity_fails_before_sources_or_pool(tmp_path, carrier, missing):
    chosen = selection(work())
    chosen["carrier"] = carrier
    chosen["executionId"] = chosen["executionId"].replace("-image-", f"-{carrier}-")
    target = chosen["targets"][0]["target"]
    target.update(carrier=carrier, region="中国/四川省")
    del target[missing]
    subject.io.write(tmp_path / f"{carrier}/selection.json", subject.io.encode(chosen))
    with pytest.raises(subject.io.InputError, match=missing):
        subject.validate(chosen, SKILL / f"carriers/{carrier}/schemas/selection.schema.json")
    with pytest.raises(subject.io.InputError, match=missing):
        subject.execution_target_ref(target)
    with pytest.raises(subject.io.InputError, match=missing):
        subject.canonical_target_ref(target)
    with pytest.raises(subject.io.InputError, match=missing):
        subject.preflight_selection(tmp_path, f"{carrier}/selection.json")
    with pytest.raises(subject.io.InputError, match=missing):
        subject.build(tmp_path, [chosen], {carrier: {}}, {})


def test_same_name_different_regions_preserve_identity_in_round_ingest_and_preflight(tmp_path, monkeypatch):
    page = {"id": "wikipedia:1", "kind": "page", "source": "wikipedia", "sourceUrl": "https://zh.wikipedia.org/wiki/山",
            "title": "山", "sourceMarkdownPath": "homepage/sources/page.md"}
    subject.io.write(tmp_path / page["sourceMarkdownPath"], b"# source\n")
    chosen = {"carrier": "homepage", "executionId": "20260908--travel-homepage-work--local--pilot-001", "targets": []}
    refs = ["/entity/travel/stable-a/mountain", "/entity/travel/stable-b/mountain"]
    for index, (region, entity_ref) in enumerate(zip(("中国/四川省", "中国/浙江省"), refs)):
        target = {"carrier": "homepage", "entityType": "地点/自然景观", "name": "山", "region": region,
                  "entityId": f"explicit-entity-{index}", "entityRef": entity_ref}
        chosen["targets"].append({"target": target, "sources": [{"candidateId": page["id"], "role": "primary", "relevance": "显式身份对应的离线事实",
                                "license": "CC BY-SA 4.0", "licenseUrl": "https://creativecommons.org/licenses/by-sa/4.0/", "creator": "条目贡献者"}]})
    before = subject.io.encode(chosen)
    outputs = subject.build(tmp_path, [chosen], {"homepage": {page["id"]: page}}, {})
    expected = ["entities/" + ref.removeprefix("/entity/") for ref in refs]
    assert outputs["round.json"]["targets"] == [row["target"] for row in chosen["targets"]]
    from content.execution.task_init import execution_target_ref
    execution_refs = [execution_target_ref(row["target"], carrier="homepage") for row in chosen["targets"]]
    assert [row["targetRef"] for row in outputs["homepage/ingest.json"]["targets"]] == execution_refs
    assert len(set(execution_refs)) == 2 and set(execution_refs).isdisjoint(expected)
    subject.io.write(tmp_path / "homepage/selection.json", subject.io.encode(chosen))
    assert subject.preflight_selection(tmp_path, "homepage/selection.json") == (set(expected), set(expected))
    for index, row in enumerate(chosen["targets"]):
        post = selection(work())
        post["targets"][0]["target"].update({**row["target"], "carrier": "image", "publishTitle": f"山景-{index}"})
        relative = f"image/selection-{index}.json"
        subject.io.write(tmp_path / relative, subject.io.encode(post))
        post_ref = f"posts/image/风光/山景-{index}/1"
        dependencies, targets = subject.preflight_selection(tmp_path, relative)
        assert dependencies == {post_ref, expected[index]} and targets == {post_ref}
        renamed = {**row["target"], "name": "改名", "region": "中国/福建省"}
        assert subject.execution_target_ref(renamed) == execution_refs[index]
        assert subject.canonical_target_ref(renamed) == expected[index]
    assert subject.io.encode(chosen) == before
    from content.execution import task_init
    calls = []
    def data_locator(target, *, carrier):
        calls.append((target, carrier))
        return "entities/地点/自然景观/data-owned-locator"
    monkeypatch.setattr(task_init, "execution_target_ref", data_locator)
    target = chosen["targets"][0]["target"]
    assert subject.execution_target_ref(target) == "entities/地点/自然景观/data-owned-locator"
    assert calls == [(target, "homepage")]
    # canonical homepage 查询不经过过程 locator，避免 hash 目录泄漏进逻辑依赖。
    assert subject.preflight_selection(tmp_path, "homepage/selection.json") == (set(expected), set(expected))
    assert len(calls) == 1


def test_tuchong_work_through_real_acquire_seal_and_manifest(tmp_path, monkeypatch):
    from core import paths
    from content.execution import task_init, seal
    from content.source import acquire
    from content.release.canonical import final_surface_projection as projection
    from content.release.canonical.post_transaction_assets import source_assets
    monkeypatch.setattr(paths, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(paths, "DATA_LOCAL_ROOT", tmp_path / "local")
    monkeypatch.setattr(paths, "DATA_EXECUTIONS_ROOT", tmp_path / "tasks")
    monkeypatch.setenv("QWQ_LIBRARY_ROOT", str(tmp_path / "library"))
    row = work()
    choose = selection(row)
    class DifferentImages(Fetch):
        def get(self, url, **kw):
            self.calls.append(url)
            image = Image.new("RGB", (40, 30), (len(self.calls) * 50, 100, 20))
            stream = io.BytesIO()
            image.save(stream, format="JPEG")
            return stream.getvalue()
    pool = {"image": {row["id"]: row}}
    downloaded = producer.download(tmp_path, pool, [choose], DifferentImages(), 100000)
    outputs = subject.build(tmp_path, [choose], pool, downloaded)
    for relative, document in outputs.items():
        subject.io.write(subject.io.safe_path(tmp_path, relative), subject.io.encode(document))
    task_init.initialize_round(round_spec_path=tmp_path / "round.json")
    execution_id = choose["executionId"]
    acquired = acquire.acquire(execution_id=execution_id, request_path=tmp_path / "image/ingest.json")
    assert acquired["failed"] == 0
    root = paths.execution_root(execution_id)
    target = choose["targets"][0]["target"]
    ref = subject.execution_target_ref(target)
    assets = list(source_assets(root))
    assert len(assets) == 2
    subject.io.write(subject.io.safe_path(root, ref + "/4.draft/image_work.json"), subject.io.encode({"title": "赏秋", "caption": "同组作品", "assetRefs": assets, "assetCaptions": {assets[0]: "第一图", assets[1]: "第二图"}}))
    author = {"host": "cursor", "sessionId": "test-author", "modelFamily": "test", "invocation": {"provider": "test", "model": "test", "runId": "author"}}
    reviewer = {**author, "sessionId": "test-reviewer", "invocation": {**author["invocation"], "runId": "reviewer"}}
    for stage in ("1.download", "4.draft", "5.review"):
        document = {"actor": reviewer if stage == "5.review" else author, "verdict": "pass"}
        if stage == "5.review":
            document["reviews"] = {ref: {"decision": "approved", "blockingIssues": [], "advisories": []}}
        input_path = tmp_path / (stage + ".json")
        subject.io.write(input_path, subject.io.encode(document))
        seal.seal_stage(execution_id=execution_id, stage=stage, input_path=input_path)
    result = projection.project_publish_final_surface(execution_root=root, object_dir=root / ref, target_ref=ref, target=target, carrier="image")
    assert [asset["caption"] for asset in result["manifest"]["assets"]] == ["第一图", "第二图"]
    assert len({asset["fileName"] for asset in result["manifest"]["assets"]}) == 2


def test_round_write_is_create_or_same_and_does_not_overwrite(tmp_path):
    first = subject.io.safe_path(tmp_path, "rounds/r01/image/selection.json")
    second = subject.io.safe_path(tmp_path, "rounds/r02/image/selection.json")
    subject.io.write(first, b"one")
    subject.io.write(second, b"two")
    with pytest.raises(ValueError, match="已有文件"):
        subject.io.write(first, b"changed")
    assert first.read_bytes() == b"one" and second.read_bytes() == b"two"


def test_source_failure_does_not_import_another_carrier():
    before = set(sys.modules)
    subject.load("image", "tuchong")
    assert not any(name.startswith("content_production_video") for name in set(sys.modules) - before)
    with pytest.raises(ValueError, match="未实现"):
        subject.load("video", "missing")
    assert len(work()["assets"]) == 2
    with pytest.raises(ValueError):
        subject.load("../image", "tuchong")


def test_preview_reorder_keeps_asset_binding(tmp_path):
    import preview
    rows = work()["assets"]
    first = preview.make(tmp_path, "image", rows, Fetch(), discovery=True, max_bytes=100000)
    second = preview.make(tmp_path, "image", list(reversed(rows)), Fetch(), discovery=True, max_bytes=100000)
    assert second == list(reversed(first))


def test_wiki_response_preserves_raw_and_disambiguation():
    body = {"query": {"pages": {"1": {"pageid": 1, "title": "石钟山", "extract": "石钟山是一位作家。", "pageprops": {"disambiguation": ""},
                                       "revisions": [{"revid": 3, "slots": {"main": {"*": "{{Infobox|职业=作家}}"}}}]}}}}
    rows, texts = subject.load("homepage", "wikipedia").parse(json.dumps(body).encode(), {"title": "石钟山"})
    assert rows[0]["disambiguation"]
    assert "作家" in rows[0]["summary"]
    assert "{{Infobox" in next(iter(texts.values()))


def test_commons_query_url_does_not_drop_sha1():
    body = {"query": {"pages": {"1": {"title": "File:work.jpg", "imageinfo": [{"url": "https://upload.wikimedia.org/a.jpg?utm_source=x", "sha1": "a" * 40,
                 "size": 12, "width": 1600, "height": 900, "mime": "image/jpeg", "extmetadata": {"Artist": {"value": "作者"}}}]}}}}
    rows, _ = subject.load("image", "commons").parse(json.dumps(body).encode(), {})
    assert rows[0]["assets"][0]["sha1"] == "a" * 40
    assert rows[0]["assets"][0]["directUrl"].endswith("?utm_source=x")


def test_selection_rejects_null_watermark_and_duplicate_assets(tmp_path):
    row = work()
    chosen = selection(row)
    chosen["targets"][0]["sources"][0]["assets"][0]["watermarkKind"] = None
    with pytest.raises(ValueError):
        subject.validate(chosen, SKILL / "carriers/image/schemas/selection.schema.json")
    chosen = selection(row)
    chosen["targets"][0]["sources"][0]["assets"] *= 2
    with pytest.raises(ValueError, match="子集"):
        subject.load("image").check(chosen["targets"][0], {row["id"]: row})


def test_homepage_lint_is_advisory(tmp_path):
    draft = tmp_path / "page.md"
    draft.write_text("# 八达岭\n\n## 概览\n" + "细节" * 450 + "\n## 索道\n")
    assert subject.load("homepage").lint(draft)
    draft.write_text("# 八达岭\n\n## 概览\n长城的一段。\n\n## 看点\n城墙。\n")
    assert subject.load("homepage").lint(draft) == []
    assert producer.main(["--workspace", str(tmp_path / "round"), "lint", "homepage", "--draft", str(draft)]) == 0


def test_no_seal_publish_or_review_writer_in_skill_entry():
    for retired in ("recipes", "steps", "carriers", "rounds", "quality", "handoff"):
        assert not (SKILL / "references" / f"{retired}.md").exists()
    commands = producer.parser().format_help()
    assert "seal" not in commands.split("positional arguments:")[-1]
    assert not (SKILL / "scripts/cli.py").exists()


@pytest.mark.parametrize("carrier,source,body,query", [
    ("image", "pinterest", b'<rss><channel><item><title>Mountain</title><link>https://www.pinterest.com/pin/123/</link><description><![CDATA[<img src="https://i.pinimg.com/236x/a.jpg">]]></description></item></channel></rss>', {}),
    ("image", "flickr_openverse", json.dumps({"results": [{"id": "one", "url": "https://images.example/a.jpg", "foreign_landing_url": "https://www.flickr.com/photos/a/1", "title": "Mountain", "license": "by", "license_url": "https://creativecommons.org/licenses/by/4.0/"}]}).encode(), {}),
    ("image", "inaturalist", json.dumps({"results": [{"id": 2, "photos": [{"id": 1, "url": "https://static.inaturalist.org/photos/1/square.jpg"}, {"id": 2, "url": "https://static.inaturalist.org/photos/2/square.jpg"}]}]}).encode(), {}),
    ("article", "reference_page", b'<html><script>ignore()</script><p>Travel facts.</p></html>', {"title": "Travel", "url": "https://tourism.example/facts"}),
    ("homepage", "toutiao_baike", ('var __prefetch_doc_data__ = ' + json.dumps({"VersionContent": {"Title": "山", "Content": json.dumps([{"type": "paragraph", "text": "山位于此地。"}])}})).encode(), {"title": "山"}),
    ("video", "youtube", json.dumps({"id": "v", "title": "Mountain", "webpage_url": "https://www.youtube.com/watch?v=v", "url": "https://media.example/v.mp4", "license": "Creative Commons"}).encode(), {"url": "https://www.youtube.com/watch?v=v"}),
    ("video", "bilibili", json.dumps({"id": "v", "title": "Mountain", "webpage_url": "https://www.bilibili.com/video/v", "requested_formats": [{}, {}]}).encode(), {"url": "https://www.bilibili.com/video/v"}),
])
def test_all_source_parsers_offline(carrier, source, body, query):
    rows, texts = subject.load(carrier, source).parse(body, query)
    assert rows
    subject.validate(rows, SKILL / f"carriers/{carrier}/schemas/candidate.schema.json")
    if source == "inaturalist":
        assert len(rows[0]["assets"]) == 2
    if source == "pinterest":
        assert "creator" not in rows[0]
    if source == "reference_page":
        assert "ignore()" not in next(iter(texts.values()))


def test_cli_source_replay_records_response_binding(tmp_path):
    fixture = {"query": {"pages": {"1": {"pageid": 1, "title": "山", "extract": "山的原文"}}}}
    (tmp_path / "homepage").mkdir()
    (tmp_path / "homepage/request.json").write_text(json.dumps({"title": "山"}))
    (tmp_path / "homepage/response.json").write_text(json.dumps(fixture))
    command = ["--workspace", str(tmp_path), "source", "homepage", "wikipedia", "--request", "homepage/request.json", "--response", "homepage/response.json", "--output", "homepage/candidates.json"]
    assert producer.main(command) == 0
    rows = subject.io.read_json(tmp_path / "homepage/candidates.json")
    evidence = rows[0]["evidence"]
    assert subject.io.digest((tmp_path / evidence["responsePath"]).read_bytes()) == evidence["responseSha256"]
    assert producer.main(command) == 0


def test_page_candidates_with_same_identity_stay_carrier_local(tmp_path):
    page = {"id": "wikipedia:1", "kind": "page", "source": "wikipedia", "sourceUrl": "https://zh.wikipedia.org/wiki/山", "title": "山"}
    selections, pools = [], {}
    for carrier in ("homepage", "article"):
        local_path = f"{carrier}/sources/wiki/source.md"
        subject.io.write(subject.io.safe_path(tmp_path, local_path), b"# source\n")
        pools[carrier] = {page["id"]: {**page, "sourceMarkdownPath": local_path}}
        target = {"carrier": carrier, "entityType": "地点/景区", "name": "山", "entityId": "entity-shan-sichuan", "entityRef": "/entity/travel/sichuan/shan"}
        target.update({"region": "中国/四川省"} if carrier == "homepage" else {"publishAngle": "风光", "publishTitle": "山景"})
        selections.append({"carrier": carrier, "executionId": f"20260908--travel-{carrier}-work--sichuan-r01--pilot-001", "targets": [{"target": target, "sources": [{"candidateId": page["id"], "role": "primary", "relevance": "同实体", "license": "CC BY-SA 4.0", "licenseUrl": "https://creativecommons.org/licenses/by-sa/4.0/", "creator": "条目贡献者"}]}]})
    outputs = subject.build(tmp_path, selections, pools, {})
    for carrier in ("homepage", "article"):
        assert f"/{carrier}/sources/" in outputs[f"{carrier}/ingest.json"]["targets"][0]["sources"][0]["sourceMarkdownPath"]


def test_source_selection_cannot_rewrite_license(tmp_path):
    row = work()
    row["license"] = "原始声明"
    chosen = selection(row)
    with pytest.raises(ValueError, match="不能改写"):
        subject.build(tmp_path, [chosen], {"image": {row["id"]: row}}, {})


def test_transport_rejects_private_hosts_and_redirects(monkeypatch):
    for url in ("http://example.com/x", "https://127.0.0.1/x", "https://user:pass@example.com/x", "https://example.com:8443/x"):
        with pytest.raises(ValueError):
            subject.io.public_https(url)
    monkeypatch.setattr(subject.io.socket, "getaddrinfo", lambda *a, **kw: [(2, 1, 6, "", ("10.0.0.1", 443))])
    with pytest.raises(ValueError, match="DNS"):
        subject.io.public_target("https://example.com/x")


def test_same_asset_id_does_not_cross_carrier_download_roots(tmp_path):
    row = work()
    image_selection = selection(row)
    article_selection = json.loads(json.dumps(image_selection))
    article_selection["carrier"] = "article"
    article_selection["executionId"] = article_selection["executionId"].replace("-image-", "-article-")
    article_selection["targets"][0]["target"]["carrier"] = "article"
    page = {"id": "web:one", "kind": "page", "source": "reference_page", "sourceUrl": "https://example.com/text", "title": "文章", "sourceMarkdownPath": "article/sources/page.md"}
    subject.io.write(subject.io.safe_path(tmp_path, page["sourceMarkdownPath"]), b"# page\n")
    article_selection["targets"][0]["sources"].append({"candidateId": page["id"], "relevance": "事实参考", "license": "保留", "licenseUrl": "https://example.com/terms", "creator": "作者"})
    pools = {"image": {row["id"]: row}, "article": {row["id"]: row, page["id"]: page}}
    downloads = producer.download(tmp_path, pools, [image_selection, article_selection], Fetch(), 100000)
    for carrier, index in downloads.items():
        assert all(value["path"].startswith(carrier + "/") for value in index.values())
    outputs = subject.build(tmp_path, [image_selection, article_selection], pools, downloads)
    for carrier in ("image", "article"):
        media = [s for s in outputs[f"{carrier}/ingest.json"]["targets"][0]["sources"] if s["kind"] == "image"]
        assert all(f"/{carrier}/downloads/" in source["filePath"] for source in media)


def test_download_cache_drift_is_rejected(tmp_path):
    row = work()
    choose = selection(row)
    index = producer.download(tmp_path, {"image": {row["id"]: row}}, [choose], Fetch(), 100000)
    asset = next(iter(index["image"].values()))
    (tmp_path / asset["path"]).write_bytes(b"changed")
    with pytest.raises(ValueError, match="漂移"):
        producer.download(tmp_path, {"image": {row["id"]: row}}, [choose], Fetch(), 100000)


def test_paths_reject_escape_and_symlinks(tmp_path):
    with pytest.raises(ValueError):
        subject.io.safe_path(tmp_path, "../escape")
    (tmp_path / "linked").symlink_to(tmp_path)
    with pytest.raises(ValueError):
        subject.io.safe_path(tmp_path, "linked/file.json")


@pytest.mark.parametrize("sites", [{"7": {"site_id": 7, "name": "上传者"}}, [{"site_id": 7, "name": "上传者"}], None])
def test_tuchong_site_list_shapes_and_uploader_not_creator(sites):
    raw = {"siteList": sites, "postList": [{"post_id": 1, "site_id": 7, "url": "https://tuchong.com/7/1/", "images": [{"user_id": 7, "img_id": 8}]}]}
    rows, _ = subject.load("image", "tuchong").parse(subject.io.encode(raw), {})
    assert "creator" not in rows[0]
    if sites is not None:
        assert rows[0]["uploader"] == "上传者"
    with pytest.raises(ValueError, match="siteList"):
        subject.load("image", "tuchong").parse(subject.io.encode({**raw, "siteList": "unknown"}), {})


def test_cross_page_same_revision_ignores_evidence_but_rejects_conflict(tmp_path):
    row = {**work(), "revision": 1}
    snapshots = []
    for page in (1, 2):
        value = {**row, "evidence": {"responsePath": f"image/sources/{page}.raw", "responseSha256": str(page) * 64, "request": {"page": page}}}
        path = tmp_path / f"image/page-{page}.json"
        subject.io.write(path, subject.io.encode([value]))
        snapshots.append(path)
    assert len(subject.candidates(snapshots, tmp_path, "image")) == 1
    snapshots[1].write_bytes(subject.io.encode([{**row, "title": "冲突"}]))
    with pytest.raises(ValueError, match="身份内容冲突"):
        subject.candidates(snapshots, tmp_path, "image")
    snapshots[1].write_bytes(subject.io.encode([{**row, "revision": 2}]))
    with pytest.raises(ValueError, match="身份内容冲突"):
        subject.candidates(snapshots, tmp_path, "image")


@pytest.mark.parametrize("body", [b"<html>broken</html>", b"[]", b'{"query":{"pages":{"x":{}}}}'])
def test_raw_failure_is_saved_before_parse_or_schema(tmp_path, capsys, body):
    subject.io.write(tmp_path / "image/request.json", b'{"query":"mountain","limit":1}')
    subject.io.write(tmp_path / "image/fixture.raw", body)
    command = ["--workspace", str(tmp_path), "source", "image", "commons", "--request", "image/request.json", "--response", "image/fixture.raw", "--output", "image/candidates.json"]
    # 无 mime 的空对象不制造候选，但结构错误必有原件证据。
    result = producer.main(command)
    evidence = f"image/sources/responses/{subject.io.digest(body)}.raw"
    assert (tmp_path / evidence).read_bytes() == body
    output = capsys.readouterr().out
    assert evidence in output
    if result:
        assert not (tmp_path / "image/candidates.json").exists()


@pytest.mark.parametrize("carrier,source,query", [("image", "commons", {"query": "山", "limit": 1}), ("homepage", "wikipedia", {"title": "山"})])
@pytest.mark.parametrize("body", [{"error": {"code": "ratelimited"}}, {"errors": [{"code": "badvalue"}]}, {"query": {"pages": None}}, {"query": {"pages": [None]}}])
def test_mediawiki_api_error_never_becomes_successful_empty_candidates(tmp_path, capsys, carrier, source, query, body):
    payload = subject.io.encode(body)
    subject.io.write(tmp_path / f"{carrier}/request.json", subject.io.encode(query))
    subject.io.write(tmp_path / f"{carrier}/fixture.raw", payload)
    result = producer.main(["--workspace", str(tmp_path), "source", carrier, source, "--request", f"{carrier}/request.json", "--response", f"{carrier}/fixture.raw", "--output", f"{carrier}/candidates.json"])
    assert result == 1
    assert not (tmp_path / f"{carrier}/candidates.json").exists()
    assert (tmp_path / f"{carrier}/sources/responses/{subject.io.digest(payload)}.raw").read_bytes() == payload
    assert "SOURCE.RESPONSE_INVALID" in capsys.readouterr().out


def test_preview_uses_verified_original_and_cached_discovery_without_network(tmp_path):
    import preview
    row = work()
    for asset in row["assets"]:
        asset["previewUrl"] = "https://thumb.example/75.jpg"
    class Original(Fetch):
        def get(self, url, **kwargs):
            stream = io.BytesIO()
            Image.new("RGB", (2400, 1600), "green").save(stream, format="JPEG")
            return stream.getvalue()
    producer.download(tmp_path, {"image": {row["id"]: row}}, [selection(row)], Original(), 100000, 200000)
    class NoNetwork:
        def get(self, *args, **kwargs):
            raise AssertionError("原件或摘要缓存不可重新出网")
    paths = preview.make(tmp_path, "image", row["assets"], NoNetwork())
    index_path = tmp_path / f"image/preview/index-{subject.io.key('|'.join(paths))}.json"
    assert all(item["source"] == "original" and item["width"] == 2400 for item in subject.io.read_json(index_path))
    extra = {"id": "extra", "directUrl": "https://images.example/extra.jpg", "previewUrl": "https://thumb.example/extra.jpg", "sha1": "f" * 40}
    with pytest.raises(ValueError, match="discovery"):
        preview.make(tmp_path, "image", [extra], NoNetwork())
    preview.make(tmp_path, "image", [extra], Fetch(), discovery=True, max_bytes=100000)
    preview.make(tmp_path, "image", [extra], NoNetwork(), discovery=True, max_bytes=100000)


@pytest.mark.parametrize("failure", [404, 429, 503, "challenge", "bad_image"])
def test_download_good_bad_good_continues_and_stops_only_failed_site(tmp_path, failure):
    row = work()
    row["assets"] = [{"id": str(i), "directUrl": f"https://{host}.example/{i}.jpg"} for i, host in enumerate(["one", "one", "one", "other"])]
    class Mixed(Fetch):
        def chunks(self, url, **kwargs):
            self.calls.append(url)
            if url.endswith("/1.jpg"):
                if failure == "bad_image":
                    yield b"not image"
                    return
                raise subject.io.TransferError(str(failure), stop_site=failure in {429, 503, "challenge"})
            yield jpeg()
    fetch = Mixed()
    with pytest.raises(subject.io.PartialFailure) as caught:
        producer.download(tmp_path, {"image": {row["id"]: row}}, [selection(row)], fetch, 100000, 400000)
    index = subject.download_index(tmp_path, "image")
    expected = {"0", "3"} if failure in {429, 503, "challenge"} else {"0", "2", "3"}
    assert set(index) == expected
    assert "approved" not in json.dumps(caught.value.result)
    assert "3.jpg" in fetch.calls[-1]


def test_budget_precheck_and_bounded_stream_count_failed_bytes(tmp_path):
    row = work()
    row["assets"][0]["bytes"] = 100001
    fetch = Fetch()
    with pytest.raises(subject.io.PartialFailure) as caught:
        producer.download(tmp_path, {"image": {row["id"]: row}}, [selection(row)], fetch, 100000, 100000)
    assert len(fetch.calls) == 1 and caught.value.result["failures"][0]["code"] == "SOURCE.BUDGET_EXCEEDED"
    budget = subject.io.Budget(10)
    with pytest.raises(ValueError, match="预算"):
        subject.io.store_chunks(tmp_path / "image/oversize", [b"123456", b"123456"], budget, 10)
    assert budget.used == 12 and not (tmp_path / "image/oversize").exists()


def test_foreign_response_and_cache_rejected_before_read(tmp_path, monkeypatch):
    subject.io.write(tmp_path / "image/request.json", b'{"query":"mountain"}')
    touched = []
    original = Path.read_bytes
    def read(path):
        touched.append(path)
        if "article" in path.parts:
            raise AssertionError("不得先读另一个载体")
        return original(path)
    monkeypatch.setattr(Path, "read_bytes", read)
    command = ["--workspace", str(tmp_path), "source", "image", "commons", "--request", "image/request.json", "--response", "article/private.raw", "--output", "image/candidates.json"]
    assert producer.main(command) == 1
    row = work()
    subject.io.write(tmp_path / "image/downloads/index.json", subject.io.encode({row["assets"][0]["id"]: {"directUrl": row["assets"][0]["directUrl"], "path": "article/private.jpg", "sha256": "a" * 64, "bytes": 1}}))
    with pytest.raises(ValueError, match="载体"):
        producer.download(tmp_path, {"image": {row["id"]: row}}, [selection(row)], Fetch(), 100000)
    assert not any("article" in path.parts for path in touched)


def test_yt_entries_boundaries_and_missing_direct_retains_budget_facts():
    parser = subject.load("video", "youtube")
    raw = {"id": "v", "title": "标题", "uploader": "转载账号", "duration": 12, "filesize_approx": 2048, "requested_formats": [{}, {}]}
    request = {"url": "https://www.youtube.com/watch?v=v", "limit": 2}
    row = parser.parse(subject.io.encode({"entries": [None, raw]}), request)[0][0]
    assert row["uploader"] == "转载账号" and "creator" not in row
    assert row["assets"][0]["duration"] == 12 and row["assets"][0]["bytes"] == 2048
    assert "directUrl" not in row["assets"][0]
    for body in ({"entries": None}, {"entries": "unknown"}, {"_type": "playlist"}, {"entries": [42]}):
        with pytest.raises(ValueError, match="entries"):
            parser.parse(subject.io.encode(body), request)
    with pytest.raises(ValueError, match="limit"):
        parser.parse(subject.io.encode({"entries": [None, raw, raw]}), request)
    assert parser.parse(subject.io.encode(raw), request)[0]


def test_yt_host_explicit_limit_and_channel_command(monkeypatch):
    parser = subject.load("video", "bilibili")
    calls = []
    def run(command, **kwargs):
        from types import SimpleNamespace
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout=b'{"entries":[]}', stderr=b"")
    monkeypatch.setattr(parser.client.subprocess, "run", run)
    from types import SimpleNamespace
    transport = SimpleNamespace(user_agent="offline")
    parser.fetch({"url": "https://space.bilibili.com/7/video", "mode": "channel", "limit": 3}, transport)
    command = calls[0]
    assert command[command.index("--playlist-end") + 1] == "3"
    assert command[command.index("--max-downloads") + 1] == "3" and "--no-playlist" not in command
    for request in ({"url": "https://evil.example/7", "mode": "single", "limit": 1}, {"url": "https://b23.tv/7"}, {"url": "https://b23.tv/7", "mode": "single", "limit": 2}):
        with pytest.raises(ValueError):
            parser.fetch(request, transport)
    assert len(calls) == 1


def test_commons_article_imageinfo_and_bounded_continuation():
    parser = subject.load("image", "commons")
    fetch = Fetch()
    request = {"article": "九寨沟", "limit": 2, "continue": {"continue": "||", "gimcontinue": "12|x"}}
    parser.fetch(request, fetch)
    from urllib.parse import urlsplit, parse_qs
    url = urlsplit(fetch.calls[0])
    query = parse_qs(url.query)
    assert url.hostname == "zh.wikipedia.org" and query["generator"] == ["images"]
    assert query["gimlimit"] == ["2"] and query["gimcontinue"] == ["12|x"] and query["prop"] == ["imageinfo"]
    body = {"query": {"pages": {"1": {"title": "File:X.jpg", "imagerepository": "shared", "imageinfo": [{"url": "https://upload.wikimedia.org/x.jpg", "mime": "image/jpeg", "sha1": "A" * 40, "user": "上传者", "extmetadata": {"Artist": {"value": "作者"}}}]}}}}
    row = parser.parse(subject.io.encode(body), request)[0][0]
    assert row["assets"][0]["sha1"] == "a" * 40 and row["creator"] == "作者" and row["uploader"] == "上传者"
    with pytest.raises(ValueError, match="continuation"):
        parser.fetch({**request, "continue": {"titles": "别的条目"}}, fetch)


def test_per_asset_creator_and_license_corrections_require_exact_evidence(tmp_path):
    row = work()
    row["creator"] = "误记作者"
    row["assets"][0].update(license="CC BY 4.0", licenseUrl="https://creativecommons.org/licenses/by/4.0/")
    row["assets"][1].update(license="CC BY-SA 4.0", licenseUrl="https://creativecommons.org/licenses/by-sa/4.0/")
    chosen = selection(row)
    original = subject.io.encode(row)
    body = "核实：和风不语为两图原作者。".encode()
    evidence = {"responsePath": "image/sources/correction.raw", "responseSha256": subject.io.digest(body), "quote": "和风不语", "sourceUrl": row["sourceUrl"]}
    subject.io.write(tmp_path / evidence["responsePath"], body)
    choice = chosen["targets"][0]["sources"][0]
    choice["factEvidence"] = {"creator": evidence}
    download = producer.download(tmp_path, {"image": {row["id"]: row}}, [chosen], Fetch(), 100000)
    sources = subject.build(tmp_path, [chosen], {"image": {row["id"]: row}}, download)["image/ingest.json"]["targets"][0]["sources"]
    assert [source["license"] for source in sources] == ["CC BY 4.0", "CC BY-SA 4.0"]
    assert all(source["creator"] == "和风不语" for source in sources)
    assert subject.io.encode(row) == original
    choice["assets"][0].update(creator="逐图作者", licenseUrl="https://example.com/verified-rights", factEvidence={"creator": evidence, "licenseUrl": evidence})
    corrected = subject.build(tmp_path, [chosen], {"image": {row["id"]: row}}, download)["image/ingest.json"]["targets"][0]["sources"]
    assert corrected[0]["creator"] == "逐图作者" and corrected[0]["licenseUrl"] == "https://example.com/verified-rights"
    assert corrected[1]["licenseUrl"] == "https://creativecommons.org/licenses/by-sa/4.0/"
    choice["assets"][0]["creator"] = "另一作者"
    choice["assets"][0]["factEvidence"]["creator"] = {**evidence, "quote": "不存在原文"}
    with pytest.raises(ValueError, match="quote"):
        subject.build(tmp_path, [chosen], {"image": {row["id"]: row}}, download)


def test_selected_asset_authorization_facts_survive_real_ingest_schema(tmp_path):
    row = work()
    chosen = selection(row)
    facts = {"commercialAuthorizationStatus": "verified", "authorizationProof": "https://example.com/proof",
             "audioRightsStatus": "no_audio", "usageScope": "editorial", "modelReleaseStatus": "editorial_only", "propertyReleaseStatus": "unverified"}
    chosen["targets"][0]["sources"][0]["assets"][0].update(facts)
    downloads = producer.download(tmp_path, {"image": {row["id"]: row}}, [chosen], Fetch(), 100000)
    sources = subject.build(tmp_path, [chosen], {"image": {row["id"]: row}}, downloads)["image/ingest.json"]["targets"][0]["sources"]
    assert {field: sources[0][field] for field in facts} == facts
    assert all(field not in sources[1] for field in facts)
    chosen["targets"][0]["sources"][0]["assets"][0]["audioRightsStatus"] = "invented"
    with pytest.raises(ValueError):
        subject.build(tmp_path, [chosen], {"image": {row["id"]: row}}, downloads)


def test_local_ytdlp_result_mechanically_registered_without_fake_direct(tmp_path):
    from types import SimpleNamespace
    parser = subject.load("video", "youtube")
    metadata = {"id": "v", "title": "山", "webpage_url": "https://www.youtube.com/watch?v=v", "requested_formats": [{}, {}], "duration": 20}
    row = parser.parse(subject.io.encode(metadata), {"url": metadata["webpage_url"]})[0][0]
    subject.io.write(tmp_path / "video/host/v.mp4", b"local bytes")
    subject.io.write(tmp_path / "video/host/v.info.json", subject.io.encode(metadata))
    args = SimpleNamespace(carrier="video", candidate_id=row["id"], asset_id=row["assets"][0]["id"], file="video/host/v.mp4", metadata="video/host/v.info.json", max_bytes=100)
    result = subject.register_local(tmp_path, {row["id"]: row}, args)
    assert result["sha256"] == subject.io.digest(b"local bytes")
    stored = subject.download_index(tmp_path, "video")[args.asset_id]
    assert stored["acquisition"] == "ytdlp_local" and "directUrl" not in stored
    assert subject.io.cached_file(tmp_path, "video", {**row["assets"][0], "sourceUrl": row["sourceUrl"]}, stored).exists()


def test_documented_minimal_selection_runs_real_build(tmp_path):
    import re
    doc = (SKILL / "references/pipeline.md").read_text()
    section = doc.split("### 最小 selection 示例", 1)[1]
    chosen = json.loads(re.search(r"```json\n(.*?)\n```", section, re.S).group(1))
    row = work()
    downloaded = producer.download(tmp_path, {"image": {row["id"]: row}}, [chosen], Fetch(), 100000)
    outputs = subject.build(tmp_path, [chosen], {"image": {row["id"]: row}}, downloaded)
    assert len(outputs["image/ingest.json"]["targets"][0]["sources"]) == 1


def test_fetcher_streams_bounded_chunks_and_prechecks_length(monkeypatch):
    from contextlib import contextmanager
    requests = []
    class Response:
        headers = {"Content-Length": "150000"}
        def __init__(self):
            self.remaining = 150000
        def read(self, size):
            requests.append(size)
            chunk = b"x" * min(size, self.remaining)
            self.remaining -= len(chunk)
            return chunk
    @contextmanager
    def response(url, *, max_bytes):
        yield Response()
    fetch = subject.io.Fetcher("offline", 0)
    monkeypatch.setattr(fetch, "response", response)
    with pytest.raises(subject.io.TransferError, match="预算"):
        list(fetch.chunks("https://media.example/x", max_bytes=100))
    assert not requests
    chunks = list(fetch.chunks("https://media.example/x", max_bytes=150000))
    assert sum(map(len, chunks)) == 150000 and max(requests) <= subject.io.CHUNK_BYTES


def test_download_cli_partial_failure_is_nonzero(tmp_path, monkeypatch, capsys):
    row = work()
    row["assets"][0]["bytes"] = 100001
    subject.io.write(tmp_path / "image/candidates.json", subject.io.encode([row]))
    subject.io.write(tmp_path / "image/selection.json", subject.io.encode(selection(row)))
    monkeypatch.setattr(subject.io, "Fetcher", lambda *args: Fetch())
    result = producer.main(["--workspace", str(tmp_path), "download", "--candidates", "image/candidates.json", "--selection", "image/selection.json", "--max-bytes", "100000", "--total-bytes", "100000"])
    payload = json.loads(capsys.readouterr().out)
    assert result == 1 and payload["status"] == "partial_failure" and payload["downloaded"] == {"image": 1}
    assert "approved" not in payload and "verdict" not in payload


def test_preview_pages_close_tiles_before_next_page(tmp_path, monkeypatch):
    import preview
    row = work()
    row["assets"] = [{"id": str(i), "directUrl": f"https://images.example/{i}.jpg"} for i in range(9)]
    producer.download(tmp_path, {"image": {row["id"]: row}}, [selection(row)], Fetch(), 100000)
    groups = []
    original = preview.save_sheet
    def save(root, carrier, tiles):
        if groups:
            with pytest.raises(ValueError, match="closed"):
                groups[-1][0].getpixel((0, 0))
        groups.append(list(tiles))
        original(root, carrier, tiles)
    monkeypatch.setattr(preview, "save_sheet", save)
    preview.make(tmp_path, "image", row["assets"])
    assert list(map(len, groups)) == [8, 1]
    with pytest.raises(ValueError, match="closed"):
        groups[-1][0].getpixel((0, 0))


@pytest.mark.parametrize("code", [429, 503])
def test_http_rate_limit_response_is_typed_and_preserved(monkeypatch, code):
    import urllib.error
    from types import SimpleNamespace
    def open_request(*args, **kwargs):
        raise urllib.error.HTTPError("https://images.example/a", code, "limited", {}, io.BytesIO(b"rate limit"))
    monkeypatch.setattr(subject.io, "public_target", lambda url: None)
    monkeypatch.setattr(subject.io.urllib.request, "build_opener", lambda *args: SimpleNamespace(open=open_request))
    fetch = subject.io.Fetcher("offline", 0)
    with pytest.raises(subject.io.TransferError) as caught:
        list(fetch.chunks("https://images.example/a", max_bytes=100))
    assert caught.value.stop_site and caught.value.code == f"SOURCE.HTTP_{code}"
    assert caught.value.body == b"rate limit"


def test_image_preview_uses_data_pixel_policy(tmp_path, monkeypatch):
    import preview
    from core import image_decode
    row = work()
    producer.download(tmp_path, {"image": {row["id"]: row}}, [selection(row)], Fetch(), 100000)
    monkeypatch.setattr(image_decode, "MAX_SOURCE_PIXELS", 10)
    with pytest.raises(ValueError, match="pixel_limit_exceeded"):
        preview.make(tmp_path, "image", row["assets"])


def test_original_evidence_cross_carrier_refused_before_read(tmp_path, monkeypatch):
    row = work()
    row["evidence"] = {"responsePath": "article/private.raw", "responseSha256": "a" * 64, "request": {}}
    def no_read(path):
        raise AssertionError("拒绝前不读私有响应")
    monkeypatch.setattr(Path, "read_bytes", no_read)
    with pytest.raises(ValueError, match="载体"):
        subject.build(tmp_path, [selection(row)], {"image": {row["id"]: row}}, {})


def test_commons_uploader_next_page_is_explicit_and_bounded():
    parser = subject.load("image", "commons")
    fetch = Fetch()
    parser.fetch({"uploader": "Photographer", "limit": 3, "continue": {"gaicontinue": "next", "continue": "||"}}, fetch)
    from urllib.parse import urlsplit, parse_qs
    query = parse_qs(urlsplit(fetch.calls[0]).query)
    assert query["gaiuser"] == ["Photographer"] and query["gailimit"] == ["3"] and query["gaicontinue"] == ["next"]
    assert len(fetch.calls) == 1


def test_fetch_error_body_respects_remaining_transfer_budget(monkeypatch):
    import urllib.error
    from types import SimpleNamespace
    reads = []
    class ErrorBody(io.BytesIO):
        def read(self, size=-1):
            reads.append(size)
            return super().read(size)
    def open_request(*args, **kwargs):
        raise urllib.error.HTTPError("https://images.example/a", 404, "missing", {}, ErrorBody(b"x" * 1000))
    monkeypatch.setattr(subject.io, "public_target", lambda url: None)
    monkeypatch.setattr(subject.io.urllib.request, "build_opener", lambda *args: SimpleNamespace(open=open_request))
    with pytest.raises(subject.io.TransferError) as caught:
        list(subject.io.Fetcher("offline", 0).chunks("https://images.example/a", max_bytes=7))
    assert reads == [7] and len(caught.value.body) == 7


def test_download_repeated_work_does_not_count_challenge_body_twice(tmp_path):
    row = work()
    row["assets"][0]["bytes"] = 100
    row["assets"][1]["directUrl"] = "https://other.example/b.jpg"
    class Challenged(Fetch):
        def chunks(self, url, **kwargs):
            self.calls.append(url)
            if "other.example" not in url:
                raise subject.io.TransferError("challenge", code="SOURCE.CHALLENGE", stop_site=True, body=b"captcha")
            yield jpeg()
    fetch = Challenged()
    with pytest.raises(subject.io.PartialFailure) as caught:
        producer.download(tmp_path, {"image": {row["id"]: row}}, [selection(row)], fetch, 100000, 100000)
    assert caught.value.result["transferredBytes"] == len(b"captcha") + len(jpeg())
    assert caught.value.result["downloaded"] == {"image": 1}


def test_same_asset_identity_conflict_rejected_before_network(tmp_path):
    first = work()
    second = {**first, "id": "tuchong:other", "assets": [dict(first["assets"][0], directUrl="https://other.example/conflict.jpg")]}
    chosen = selection(first)
    chosen["targets"].append(selection(second)["targets"][0])
    fetch = Fetch()
    with pytest.raises(ValueError, match="资产身份冲突"):
        producer.download(tmp_path, {"image": {first["id"]: first, second["id"]: second}}, [chosen], fetch, 100000)
    assert not fetch.calls


@pytest.fixture
def publish_repository(tmp_path):
    # 仅构造临时仓身份 fixture；不初始化或写真实内容仓。
    root = tmp_path / "publish"
    (root / ".git").mkdir(parents=True)
    subject.io.write(root / "repository.json", subject.io.encode({
        "schema": "quwoquan_data.publish_repository.v2", "repositoryId": "skill-offline",
        "layoutVersion": 2,
    }))
    return root


def test_preflight_selection_keeps_invalid_occupied_and_absent_distinct(tmp_path, capsys, publish_repository):
    chosen = selection(work())
    subject.io.write(tmp_path / "image/selection.json", subject.io.encode(chosen))
    publish = tmp_path / "publish"
    # 无有效 record 的主页仍占用身份，selection 中的计划不能使其 eligible。
    homepage = "entities/travel/sichuan/qiushan"
    target = chosen["targets"][0]["target"]
    subject.io.write(publish / homepage / "manifest.json", subject.io.encode({
        "entityRef": target["entityRef"], "entityId": target["entityId"], "version": 1,
    }))
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    command = ["--workspace", str(tmp_path), "preflight", "--selection", "image/selection.json", "--publish-root", str(publish)]
    assert producer.main(command) == 0
    result = json.loads(capsys.readouterr().out)
    rows = {row["objectRef"]: row for row in result["poolQuery"]["objects"]}
    ref = subject.canonical_target_ref(chosen["targets"][0]["target"])
    assert rows[ref]["state"] == "absent" and not rows[ref]["occupied"]
    assert rows[homepage]["state"] == "invalid" and rows[homepage]["occupied"] and not rows[homepage]["eligible"]
    assert rows[homepage]["objectId"] == target["entityId"]
    assert rows[homepage]["code"] == "DATA.POOL.EXPLICIT_ADMISSION_MISSING"
    assert result["coverage"]["selectedWithoutManifestRefs"] == [ref]
    assert result["poolQuery"]["preflight"] == []
    assert {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before


def preflight_candidate(tmp_path, ref, asset_id):
    from content.release.canonical.image_identity import canonical_asset_manifest_row
    path = tmp_path / "image/acquired.jpg"
    subject.io.write(path, jpeg())
    asset = canonical_asset_manifest_row({"assetId": asset_id, "sha256": subject.io.digest(jpeg()), "sourceUrl": "https://source.example/work", "originalAssetUrl": "https://source.example/a.jpg"}, asset_source=path, mime_type="image/jpeg", object_key="assets/a.jpg")
    return {"objectRef": ref, "manifest": {"contentType": "image", "entityRefs": ["/entity/地点/自然景观/秋山"], "assets": [asset]}}


def test_preflight_batches_real_data_query_once_and_preserves_conflict_refs(tmp_path, capsys, monkeypatch, publish_repository):
    from content.release.canonical import pool_query
    from contextlib import contextmanager
    refs = [f"posts/image/风光/候选{i}/1" for i in (1, 2)]
    candidates = [preflight_candidate(tmp_path, ref, f"asset-{index}") for index, ref in enumerate(refs)]
    for index, candidate in enumerate(candidates):
        subject.io.write(tmp_path / f"image/preflight{index}.json", subject.io.encode({"candidates": [candidate]}))
    calls, indexes = [], []
    original_query, original_inventory = pool_query.query_pool, pool_query.readonly_image_inventory
    def query(root, **kwargs):
        calls.append(kwargs)
        return original_query(root, **kwargs)
    @contextmanager
    def inventory(root):
        indexes.append(root)
        with original_inventory(root) as connection:
            yield connection
    monkeypatch.setattr(pool_query, "query_pool", query)
    monkeypatch.setattr(pool_query, "readonly_image_inventory", inventory)
    monkeypatch.setattr(pool_query, "_occupied_refs", lambda *args: pytest.fail("点名查询不能枚举整池身份"))
    publish = publish_repository
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert producer.main(["--workspace", str(tmp_path), "preflight", "--candidate-file", "image/preflight0.json", "image/preflight1.json", "--publish-root", str(publish)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert len(calls) == 1 and len(indexes) == 1 and len(calls[0]["candidates"]) == 2
    for index, row in enumerate(result["poolQuery"]["preflight"]):
        assert row["dependencyIssues"][0]["code"] == "DATA.POOL.OBJECT_ABSENT"
        conflict = row["imageConflicts"][0]
        assert conflict["code"] == "DATA.POOL.IMAGE_SHA256_DUPLICATE"
        assert conflict["dependencyRefs"] == [refs[1 - index]]
    assert result["coverage"]["candidateManifestRefs"] == refs
    assert {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before
    assert "approved" not in result and "verdict" not in result


def test_homepage_preflight_consumes_entity_manifest_not_invented_content_type(tmp_path, monkeypatch, capsys, publish_repository):
    from content.release.canonical import pool_query
    calls = []
    real_query = pool_query.query_pool
    def query(*args, **kwargs):
        calls.append(kwargs["candidates"])
        return real_query(*args, **kwargs)
    monkeypatch.setattr(pool_query, "query_pool", query)
    ref = "entities/地点/自然景观/秋山"
    manifest = {"schema": "quwoquan_data.entity_object", "contentType": "article", "entityRef": "/entity/地点/自然景观/秋山", "assets": []}
    subject.io.write(tmp_path / "homepage/preflight.json", subject.io.encode({"candidates": [{"objectRef": ref, "manifest": manifest}]}))
    assert producer.main(["--workspace", str(tmp_path), "preflight", "--candidate-file", "homepage/preflight.json", "--publish-root", str(tmp_path / "publish")]) == 0
    result = json.loads(capsys.readouterr().out)
    assert calls == [[{"objectRef": ref, "manifest": manifest}]]
    assert result["poolQuery"]["preflight"][0]["objectRef"] == ref
    assert not result["poolQuery"]["preflight"][0]["occupied"]
    with pytest.raises(ValueError, match="entityRef"):
        subject.preflight_manifest({"objectRef": ref, "manifest": {**manifest, "entityRef": "/entity/地点/自然景观/同名"}}, "homepage")
    with pytest.raises(ValueError, match="contentType"):
        subject.preflight_manifest({"objectRef": ref, "manifest": {**manifest, "contentType": "homepage"}}, "homepage")


def test_preflight_missing_image_facts_does_not_run_query_or_projection(tmp_path, monkeypatch, capsys):
    from content.release.canonical import pool_query
    candidate = preflight_candidate(tmp_path, "posts/image/风光/候选/1", "one")
    del candidate["manifest"]["assets"][0]["perceptualHash"]
    subject.io.write(tmp_path / "image/preflight.json", subject.io.encode({"candidates": [candidate]}))
    monkeypatch.setattr(pool_query, "query_pool", lambda *args, **kwargs: pytest.fail("缺事实不能查询假成功"))
    command = ["--workspace", str(tmp_path), "preflight", "--candidate-file", "image/preflight.json", "--publish-root", str(tmp_path / "publish")]
    assert producer.main(command) == 1
    assert "SOURCE.PREFLIGHT_IMAGE_FACTS_REQUIRED" in capsys.readouterr().out
    assert not (tmp_path / "publish").exists()


def test_preflight_empty_input_rejected_before_pool_scan(tmp_path, capsys):
    assert producer.main(["--workspace", str(tmp_path), "preflight"]) == 1
    assert "不隐式扫描全池" in capsys.readouterr().out


@pytest.mark.parametrize("option", ["--selection", "--candidate-file", "--acquired-selection"])
@pytest.mark.parametrize("relative", ["", ".", "image"])
def test_preflight_invalid_input_path_is_rejected_before_reads(tmp_path, monkeypatch, capsys, option, relative):
    from content.release.canonical import pool_query
    monkeypatch.setattr(subject.io, "read_json", lambda *a: pytest.fail("无效路径不得读取缓存或证据"))
    monkeypatch.setattr(pool_query, "query_pool", lambda *a, **kw: pytest.fail("无效路径不得扫描池"))
    assert producer.main(["--workspace", str(tmp_path), "preflight", option, relative]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["error"] == "InputError" and "载体" in result["message"]
    assert not list(tmp_path.iterdir())


def test_preflight_carrier_and_duplicate_candidate_identity_fail_closed(tmp_path, capsys):
    candidate = preflight_candidate(tmp_path, "posts/image/风光/候选/1", "one")
    path = tmp_path / "article/preflight.json"
    subject.io.write(path, subject.io.encode({"candidates": [candidate]}))
    command = ["--workspace", str(tmp_path), "preflight", "--candidate-file", "article/preflight.json"]
    assert producer.main(command) == 1
    assert "另一个载体" in capsys.readouterr().out
    subject.io.write(tmp_path / "image/preflight.json", subject.io.encode({"candidates": [candidate, candidate]}))
    command[-1] = "image/preflight.json"
    assert producer.main(command) == 1
    assert "候选身份重复" in capsys.readouterr().out


def acquired_source_fixture(tmp_path, monkeypatch):
    from core import paths
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path))
    import importlib
    importlib.reload(paths)
    monkeypatch.setenv("QWQ_LIBRARY_ROOT", str(tmp_path / "library"))
    fixture = subject.module(
        ROOT / "quwoquan_data/tests/local_contract/release/test_author_bindings__multi_source__contract__local_contract_test.py",
        "acquired_preflight_fixture",
    )
    # 同一 helper 的 sources/ingest 保持真实；过程路径与 init 复用 Data 唯一公开实现。
    from content.execution.task_init import initialize_round, execution_target_ref
    homepage_targets = {}
    for constant, name, entity_id, entity_ref in (
        ("HOME_REF", "西湖", "fixture-xihu", "/entity/travel/stable/xihu"),
        ("OTHER_REF", "另一对象", "fixture-other", "/entity/travel/stable/other"),
    ):
        target = {"carrier": "homepage", "entityType": fixture.TARGET["entityType"], "region": fixture.TARGET["region"],
                  "name": name, "entityId": entity_id, "entityRef": entity_ref}
        locator = execution_target_ref(target, carrier="homepage")
        homepage_targets[locator] = target
        monkeypatch.setattr(fixture, constant, locator)
    def initialize(carrier, refs):
        execution_id = fixture.EXECUTION_ID.replace("-image-", f"-{carrier}-")
        round_path = tmp_path / "round.json"
        targets = [{"carrier": carrier, **fixture.TARGET, "entityId": "fixture-xihu", "entityRef": "/entity/travel/stable/xihu"}]
        if carrier == "homepage":
            targets = [homepage_targets[ref] for ref in refs]
        round_path.write_bytes(subject.io.encode({"schema": "quwoquan_data.round_spec", "executions": {carrier: execution_id}, "targets": targets}))
        initialize_round(round_spec_path=round_path)
        return paths.execution_root(execution_id)
    monkeypatch.setattr(fixture, "_execution", initialize)
    return fixture


def acquired_fixture(tmp_path, monkeypatch):
    fixture = acquired_source_fixture(tmp_path, monkeypatch)
    execution, refs = fixture._images(tmp_path, collision=True)
    fixture._seal(execution, "1.download")
    selected = {"executionId": execution.name, "targets": [{"objectRef": fixture.IMAGE_REF, "assetRefs": refs}]}
    subject.io.write(tmp_path / "image/acquired.json", subject.io.encode(selected))
    return fixture, execution, refs, selected


def test_acquired_preflight_uses_real_ingest_hashes_without_draft_or_writes(tmp_path, monkeypatch, capsys, publish_repository):
    from content.release.canonical import pool_query, final_surface_projection as projection
    from content.release.canonical.image_identity import canonical_asset_manifest_row
    fixture, execution, refs, selected = acquired_fixture(tmp_path, monkeypatch)
    calls, original = [], pool_query.query_pool
    def query(root, **kwargs):
        calls.append(kwargs["candidates"])
        return original(root, **kwargs)
    monkeypatch.setattr(pool_query, "query_pool", query)
    monkeypatch.setattr(projection, "project_publish_final_surface", lambda **kw: pytest.fail("author 前禁止生成发布投影"))
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    command = ["--workspace", str(tmp_path), "preflight", "--acquired-selection", "image/acquired.json", "--publish-root", str(tmp_path / "publish")]
    assert producer.main(command) == 0
    result = json.loads(capsys.readouterr().out)
    assert len(calls) == 1
    assert calls[0][0]["manifest"]["entityRefs"] == ["/entity/travel/stable/xihu"]
    assets = calls[0][0]["manifest"]["assets"]
    index = fixture.source_assets(execution)
    expected = []
    for ref in refs:
        row, _, path = projection._asset_projection(execution_root=execution, source_ref=ref, source=index[ref], caption="")
        expected.append(canonical_asset_manifest_row(row, asset_source=path, mime_type=row["mimeType"], object_key=row["objectKey"]))
    for actual, final in zip(assets, expected):
        for field in ("assetId", "sha256", "mimeType", "kind", "perceptualHash", "collectionPageUrl", "originalAssetUrl"):
            assert actual[field] == final[field]
    assert result["coverage"]["candidateManifestRefs"] == [fixture.IMAGE_REF]
    assert result["poolQuery"]["preflight"][0]["dependencyIssues"][0]["code"] == "DATA.POOL.OBJECT_ABSENT"
    assert not (execution / fixture.IMAGE_REF / "4.draft").exists()
    assert {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before


def test_acquired_homepage_preflight_accepts_explicit_empty_assets_without_draft(tmp_path, monkeypatch, capsys, publish_repository):
    fixture = acquired_source_fixture(tmp_path, monkeypatch)
    execution, _ = fixture._homepages(tmp_path)
    fixture._seal(execution, "1.download")
    selected = {"executionId": execution.name, "targets": [{"objectRef": fixture.HOME_REF, "assetRefs": []}]}
    subject.io.write(tmp_path / "homepage/acquired.json", subject.io.encode(selected))
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert producer.main(["--workspace", str(tmp_path), "preflight", "--acquired-selection", "homepage/acquired.json",
                          "--publish-root", str(tmp_path / "publish")]) == 0
    result = json.loads(capsys.readouterr().out)
    canonical_ref = "entities/travel/stable/xihu"
    assert fixture.HOME_REF != canonical_ref
    assert result["coverage"]["candidateManifestRefs"] == [canonical_ref]
    assert result["poolQuery"]["preflight"][0]["objectRef"] == canonical_ref
    from content.release.canonical.image_identity import acquired_asset_identity_view
    candidate = acquired_asset_identity_view(execution_root=execution, selections=selected["targets"], carrier="homepage")[0]
    assert candidate["manifest"]["entityRef"] == "/entity/travel/stable/xihu"
    assert candidate["manifest"]["entityId"] == "fixture-xihu"
    assert not (execution / fixture.HOME_REF / "4.draft").exists()
    assert {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before


def acquired_video_fixture(tmp_path, monkeypatch):
    import shutil
    import subprocess
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("ffmpeg/ffprobe not on PATH")
    fixture = acquired_source_fixture(tmp_path, monkeypatch)
    ref = fixture.IMAGE_REF.replace("/image/", "/video/")
    execution = fixture._execution("video", [ref])
    video = tmp_path / "source.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=24:duration=1",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)], check=True, capture_output=True)
    source = {"kind": "video", "sourceUrl": "https://media.example/work/video", "directUrl": "https://media.example/source.mp4",
              "filePath": str(video), "license": "CC BY-SA 4.0", "licenseUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
              "creator": "测试原作者", "relevance": "离线合成画面，不是真实生产证据", "hasAudio": False,
              "watermarkStatus": "absent", "watermarkKind": "none"}
    fixture._ingest(execution, [{"targetRef": ref, "sources": [source, {**source, "sourceUrl": "https://media.example/work/other"}]}])
    fixture._seal(execution, "1.download")
    return fixture, execution, ref, fixture.source_assets(execution)


def test_acquired_video_preflight_binds_exact_poster_without_draft(tmp_path, monkeypatch, capsys, publish_repository):
    from content.release.canonical import pool_query
    fixture, execution, ref, index = acquired_video_fixture(tmp_path, monkeypatch)
    videos = sorted(asset_ref for asset_ref, row in index.items() if row["assetRole"] == "video")
    video_ref = videos[0]
    poster_ref = next(asset_ref for asset_ref, row in index.items() if row.get("derivedFromSourceAssetId") == index[video_ref]["sourceAssetId"])
    other_poster = next(asset_ref for asset_ref, row in index.items() if row["assetRole"] == "poster" and asset_ref != poster_ref)
    real_query, calls = pool_query.query_pool, []
    def query(*args, **kwargs):
        calls.append(kwargs["candidates"])
        return real_query(*args, **kwargs)
    monkeypatch.setattr(pool_query, "query_pool", query)
    selection_path = tmp_path / "video/acquired.json"
    chosen = {"objectRef": ref, "assetRefs": [video_ref, poster_ref]}
    subject.io.write(selection_path, subject.io.encode({"executionId": execution.name, "targets": [chosen]}))
    command = ["--workspace", str(tmp_path), "preflight", "--acquired-selection", "video/acquired.json", "--publish-root", str(tmp_path / "publish")]
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert producer.main(command) == 0
    capsys.readouterr()
    assert len(calls) == 1
    assert [(r["kind"], r["sha256"]) for r in calls[0][0]["manifest"]["assets"]] == [("video", index[video_ref]["sha256"]), ("image", index[poster_ref]["sha256"])]
    assert calls[0][0]["manifest"]["assets"][1]["perceptualHash"]
    assert {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before
    chosen["assetRefs"] = [video_ref, other_poster]
    selection_path.write_bytes(subject.io.encode({"executionId": execution.name, "targets": [chosen]}))
    assert producer.main(command) == 1
    assert "DATA.PREFLIGHT.VIDEO_POSTER_BINDING_INVALID" in capsys.readouterr().out
    assert len(calls) == 1


@pytest.mark.parametrize("invalid", ["asset_id", "source_url", "plan_bytes", "meta_plan", "acquire_receipt"])
def test_acquired_preflight_rejects_source_identity_drift_before_pool_read(tmp_path, monkeypatch, capsys, invalid):
    from content.release.canonical import pool_query
    _, execution, refs, _ = acquired_fixture(tmp_path, monkeypatch)
    unit = (execution / refs[0]).parent.parent
    meta_path = unit / "meta.json"
    meta = json.loads(meta_path.read_bytes())
    if invalid in {"asset_id", "source_url"}:
        path = unit / "assets/index.json"
        index = json.loads(path.read_bytes())
        index["assets"][0]["sourceAssetId" if invalid == "asset_id" else "collectionPageUrl"] = "invented-id" if invalid == "asset_id" else "https://photos.example/another-work"
        path.write_bytes(subject.io.encode(index))
    elif invalid == "plan_bytes":
        path = execution / meta["sourcePlanRef"]
        path.write_bytes(path.read_bytes() + b" ")
    elif invalid == "meta_plan":
        meta["chosenCandidateDigest"] = "sha256:" + "0" * 64
        meta_path.write_bytes(subject.io.encode(meta))
    else:
        (execution / "sources" / meta["acquisition"]["receiptRef"]).unlink()
    monkeypatch.setattr(pool_query, "query_pool", lambda *a, **kw: pytest.fail("来源身份漂移不能查询池"))
    assert producer.main(["--workspace", str(tmp_path), "preflight", "--acquired-selection", "image/acquired.json"]) == 1
    assert json.loads(capsys.readouterr().out)["error"]


@pytest.mark.parametrize("invalid", ["bytes", "receipt", "target", "target_digest", "foreign_asset", "alias", "duplicate", "symlink"])
def test_acquired_preflight_rejects_drift_and_unacquired_assets(tmp_path, monkeypatch, capsys, invalid):
    from content.release.canonical import pool_query
    fixture, execution, refs, selected = acquired_fixture(tmp_path, monkeypatch)
    if invalid == "bytes":
        # CAS 引用是只读 hardlink；只替换临时 execution 引用，不篡改 holder。
        (execution / refs[0]).unlink()
        (execution / refs[0]).write_bytes(b"changed")
    elif invalid == "receipt":
        path = execution / "_shared/receipts/001-1.download.json"
        path.write_bytes(path.read_bytes() + b" ")
    elif invalid == "target":
        selected["targets"][0]["objectRef"] = "posts/image/风光/未取得作品/1"
    elif invalid == "target_digest":
        path = execution / "0.plan/target_set.json"
        document = json.loads(path.read_bytes())
        document["targets"][0]["name"] = "另一实体"
        path.write_bytes(subject.io.encode(document))
    elif invalid == "foreign_asset":
        selected["targets"][0]["assetRefs"] = ["sources/another/assets/a.jpg"]
    elif invalid == "alias":
        selected["targets"][0]["assetRefs"] = [Path(refs[0]).name]
    elif invalid == "duplicate":
        selected["targets"].append(selected["targets"][0])
    else:
        path = execution / refs[0]
        copied = tmp_path / "foreign.jpg"
        copied.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(copied)
    (tmp_path / "image/acquired.json").write_bytes(subject.io.encode(selected))
    monkeypatch.setattr(pool_query, "query_pool", lambda *a, **kw: pytest.fail("输入漂移时不能运行池查询"))
    assert producer.main(["--workspace", str(tmp_path), "preflight", "--acquired-selection", "image/acquired.json"]) == 1
    assert json.loads(capsys.readouterr().out)["error"]


@pytest.mark.parametrize("invalid", ["carrier_path", "execution_carrier", "object_carrier"])
def test_acquired_preflight_isolates_carrier_before_execution_reads(tmp_path, monkeypatch, capsys, invalid):
    from content.release.canonical import image_identity
    fixture, execution, refs, selected = acquired_fixture(tmp_path, monkeypatch)
    relative = "image/acquired.json"
    if invalid == "carrier_path":
        relative = "article/acquired.json"
    elif invalid == "execution_carrier":
        selected["executionId"] = execution.name.replace("-image-", "-video-")
    else:
        selected["targets"][0]["objectRef"] = "posts/article/人文/文章/1"
    path = tmp_path / relative
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(subject.io.encode(selected))
    monkeypatch.setattr(image_identity, "_acquired_path", lambda *a: pytest.fail("跨载体不得读取 execution"))
    assert producer.main(["--workspace", str(tmp_path), "preflight", "--acquired-selection", relative]) == 1
    assert "载体" in capsys.readouterr().out
