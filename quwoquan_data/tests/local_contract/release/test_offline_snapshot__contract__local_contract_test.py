# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#req-008
"""受控离线派生合同：版本化 JSON 仅作 metadata 模板，媒体和证据在 tmp 自建。

这些合成输入和 receipt 是测试 double，不代表真实创作、独立评审、版权许可或生产准入；
生产 operator selection 只验证工程 authority，真实现役 publish/export 由独立验收负责。
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "quwoquan_data/scripts"))

from content.release.canonical.offline_snapshot import build_bundle, export_bundle, write_dart_identity
from content.release.canonical.offline_snapshot_contract import OfflineSnapshotError, canonical_bytes, digest, validate_selection
from content.release.canonical.offline_snapshot_projection import runtime_post_id, runtime_homepage_id
from content.release.canonical.offline_snapshot_source import _read_media
from content.release.canonical.offline_snapshot_contract import PublicContractValidator, validate_bundle
from core.content_library import library_cas_path
from core.schema import assert_valid
from support.media_fixture import tiny_png_bytes
from support.post_object_transaction_fixture import _source_attribution
from content.release.canonical.offline_snapshot_contract import digest_bytes
from content.release.canonical.offline_snapshot_source import CanonicalSource

SELECTION = ROOT / "quwoquan_app/assets/content/alpha/operator_selection.json"
REVISION = "b0164eae05dab590209997d27356b372a0634bdc"
# 只使用已版本化 JSON 的字段形状，不从此旧树消费媒体、execution 或生产选择。
METADATA_ROOT = ROOT / "quwoquan_data/publish"
TEMPLATES = (
    "posts/article/文化/西湖十景漫读/1",
    "posts/image/摄影/西湖晴日与雷峰塔/1",
    "posts/video/风光/西湖灯光秀/1",
)
POST_REFS = (
    "posts/article/文化/离线合约文章/1",
    "posts/image/摄影/离线合约图片/1",
    "posts/video/风光/离线合约视频/1",
)
HOME_REF = "entities/地点/景区/测试湖"
CREATOR_ID = "offline_fixture_creator"
TAG_REFS = ("Entity/地点/景区", "Topic/地理/行政区/中国/浙江省/杭州市")
STAMP = "2026-09-10T00:00:00Z"
ARTICLE_BYTES = "# 离线合约文章\n\n只验证离线正文完整性，不构成生产内容。\n".encode()
# 自生成的 16×16、1 秒无声 H.264/yuv420p 红色视频；内嵌字节避免 CI 依赖 ffmpeg。
# ffmpeg color=c=red:s=16x16:r=1:d=1 / libx264 / filter_units=remove_types=6。
TINY_MP4 = base64.b64decode(
    "AAAAJGZ0eXBpc29tAAACAGlzb21pc282aXNvMmF2YzFtcDQxAAAC7W1vb3YAAABsbXZoZAAAAAAAAAAAAAAAAAAAA+gAAAAAAAEAAAEAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAAAAAAAAQAAAAAAAAAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAIAAAHvdHJhawAAAFx0a2hkAAAAAwAAAAAAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAAAAAAAAQAAAAAAAAAAAAAAAAAAQAAAAAAQAAAAEAAAAAABi21kaWEAAAAgbWRoZAAAAAAAAAAAAAAAAAAAQAAAAAAAVcQAAAAAAC1oZGxyAAAAAAAAAAB2aWRlAAAAAAAAAAAAAAAAVmlkZW9IYW5kbGVyAAAAATZtaW5mAAAAFHZtaGQAAAABAAAAAAAAAAAAAAAkZGluZgAAABxkcmVmAAAAAAAAAAEAAAAMdXJsIAAAAAEAAAD2c3RibAAAAKpzdHNkAAAAAAAAAAEAAACaYXZjMQAAAAAAAAABAAAAAAAAAAAAAAAAAAAAAAAQABAASAAAAEgAAAAAAAAAARVMYXZjNjIuMjguMTAyIGxpYngyNjQAAAAAAAAAAAAAABj//wAAADRhdmNDAWQACv/hABdnZAAKrNlewEQAAAMABAAAAwAIPEiWWAEABmjr48siwP34+AAAAAAQcGFzcAAAAAEAAAABAAAAEHN0dHMAAAAAAAAAAAAAABBzdHNjAAAAAAAAAAAAAAAUc3RzegAAAAAAAAAAAAAAAAAAABBzdGNvAAAAAAAAAAAAAAAobXZleAAAACB0cmV4AAAAAAAAAAEAAAABAAAAAAAAAAAAAAAAAAAAYnVkdGEAAABabWV0YQAAAAAAAAAhaGRscgAAAAAAAAAAbWRpcmFwcGwAAAAAAAAAAAAAAAAtaWxzdAAAACWpdG9vAAAAHWRhdGEAAAABAAAAAExhdmY2Mi4xMi4xMDIAAABwbW9vZgAAABBtZmhkAAAAAAAAAAEAAABYdHJhZgAAACR0ZmhkAAAAOQAAAAEAAAAAAAADEQAAQAAAAAAaAQEAAAAAABR0ZmR0AQAAAAAAAAAAAAAAAAAAGHRydW4AAAAFAAAAAQAAAHgCAAAAAAAAIm1kYXQAAAAWZYiEABX//uzPfgU2aOYvw/FFc459gQAAAENtZnJhAAAAK3RmcmEBAAAAAAAAAQAAAAAAAAABAAAAAAAAAAAAAAAAAAADEQEBAQAAABBtZnJvAAAAAAAAAEM="
)


def selection():
    return {"schema": "quwoquan.offline_operator_selection", "version": 1,
            "purpose": "alpha_offline_engineering", "selectedAt": STAMP,
            "authority": {"kind": "explicit_user_selection", "evidence": "TEST DOUBLE ONLY: no production admission or real rights authority",
                          "grantsProductionPremium": False, "changesRightsFacts": False},
            "objectRefs": list(POST_REFS),
            "channels": [{"channelId": "recommend", "orderedObjectRefs": list(POST_REFS)},
                         {"channelId": "premium", "orderedObjectRefs": [POST_REFS[2]]}]}


def _put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value if isinstance(value, bytes) else canonical_bytes(value) + b"\n")
    return path


def _json(path):
    return json.loads(path.read_bytes())


def _fixture_review(ref, execution_id, draft_ref, raw):
    return {"schema": "quwoquan_data.content_review", "stage": "5.review", "executionId": execution_id,
            "objectRef": ref, "decision": "approved", "draft": {"ref": draft_ref, "digest": digest_bytes(raw)},
            "dimensions": [{"name": "TEST DOUBLE, NOT REAL REVIEW", "decision": "approved", "issues": []}],
            "blockingIssues": [], "assetRights": []}


def _bind_review(manifest, ref, review_raw):
    manifest["admission"] = {"evidenceDigest": digest_bytes(review_raw), "evidenceRef": "content_review.json",
                             "processResult": "completed", "qualityResult": "passed", "rightsResult": "passed",
                             "rightsAuthorityDigest": digest_bytes(review_raw), "rightsAuthorityRef": ref + "/content_review.json",
                             "usageScope": "research"}


def _media_asset(root, asset_id, kind):
    raw = TINY_MP4 if kind == "video" else tiny_png_bytes()
    suffix, mime = (".mp4", "video/mp4") if kind == "video" else (".png", "image/png")
    relative = "media/" + asset_id + suffix
    sha = digest_bytes(raw)
    _put(root / relative, raw)
    asset = {"assetId": asset_id, "kind": kind, "path": relative, "fileName": relative,
             "sha256": sha, "bytes": len(raw), "mimeType": mime,
             "objectKey": f"media/objects/sha256/{sha[7:9]}/{sha[9:11]}/{sha[7:]}{suffix}",
             "sourceRefs": ["sources/fixture/source.json"], "sourceAssetRefs": ["sources/fixture/assets/" + asset_id + suffix],
             "acquisitionReceiptRefs": ["sources/fixture/evidence.json"], "caption": "本地合成测试媒体",
             "width": 16 if kind == "video" else 1, "height": 16 if kind == "video" else 1}
    if kind == "video":
        asset.update(durationMs=1000, container="mp4", codec="h264", pixelFormat="yuv420p",
                     rightsRefs=["sources/fixture/evidence.json"])
    return asset


def _fixture_sources(root, assets):
    evidence = canonical_bytes({"testDouble": True, "productionAdmission": False,
                                "assets": [{key: row[key] for key in ("assetId", "sha256", "bytes", "mimeType")} for row in assets]})
    _put(root / "sources/fixture/evidence.json", evidence)
    document = {"schema": "quwoquan_data.publish_source", "sourceId": "fixture",
                "sourceUrl": "https://example.org/offline-test-double", "sourceUseMode": "factual_reference_only",
                "fetchedAt": STAMP, "metadata": {"testDouble": True, "productionAdmission": False},
                "assets": [{**{key: row[key] for key in ("assetId", "sha256", "bytes", "mimeType")},
                            "attribution": "合成测试媒体，不代表第三方版权许可", "distributionDecision": "research_allowed"} for row in assets],
                "evidence": [{"path": "evidence.json", "sha256": digest_bytes(evidence), "bytes": len(evidence), "kind": "source_excerpt"}]}
    assert_valid(document, "publish", "source")
    _put(root / "sources/fixture/source.json", document)
    return ["sources/fixture/source.json"]


@pytest.fixture
def current_source(tmp_path):
    """现役单格式的合成闭包；不访问 library、golden media 或宿主 execution。"""
    from core.publish_layout import allocate_object_path, load_layout_policy
    stage = tmp_path / "current-schema-fixture"
    for ref, template in zip(POST_REFS, TEMPLATES):
        manifest = _json(METADATA_ROOT / template / "manifest.json")
        carrier = ref.split("/")[1]
        for key in ("assetRefsRef", "creatorRefsRef", "tagRefsRef", "sourceCatalogRef", "rightsRef"):
            manifest.pop(key, None)
        manifest.update(objectRef=ref.removeprefix("posts/"), title=Path(ref).parent.name,
                        publishTitle=Path(ref).parent.name, caption="合成离线媒体", contentId="offline_fixture_" + carrier,
                        entityRefs=["/entity/" + HOME_REF.removeprefix("entities/")], tagRefs=list(TAG_REFS),
                        creatorProfileId=CREATOR_ID, authorId=CREATOR_ID, sourceAttribution=_source_attribution(),
                        finalContentRef="article.md" if carrier == "article" else "manifest.json")
        target = stage / allocate_object_path(manifest, "posts", [], load_layout_policy())
        assets = [] if carrier == "article" else [_media_asset(target, "fixture-" + carrier, carrier)]
        if carrier == "video":
            poster = _media_asset(target, "fixture-poster", "image")
            assets[0].update(posterAssetId=poster["assetId"], posterFileName=poster["fileName"], posterSha256=poster["sha256"])
            assets.append(poster)
            manifest["videoBindings"] = [{"assetId": assets[0]["assetId"], "role": "shortVideo"}]
            manifest["sourceAttribution"]["derivedModifications"] = ["format_conversion", "video_frame_extraction"]
        manifest["assets"] = assets
        manifest["sourceRefs"] = _fixture_sources(target, assets)
        review = _fixture_review(ref, manifest["executionId"], "4.draft/draft.article.md", ARTICLE_BYTES)
        review_path = _put(target / "content_review.json", review)
        _bind_review(manifest, ref, review_path.read_bytes())
        if carrier == "article":
            _put(target / "article.md", ARTICLE_BYTES)
        assert_valid(manifest, "content", "post_manifest")
        _put(target / "manifest.json", manifest)
    old_home = METADATA_ROOT / "entities/地点/景区/西湖"
    home = {**_json(old_home / "_entity.json"), **_json(old_home / "manifest.json"),
            "geographyMode": "administrative", "label": "测试湖", "entityRef": "/entity/地点/景区/测试湖",
            "entityId": "offline_fixture_homepage", "creatorProfileId": CREATOR_ID, "authorId": CREATOR_ID,
            "tagRefs": list(TAG_REFS), "sourceAttribution": _source_attribution()}
    for key in ("assetRefsRef", "creatorRefsRef", "tagRefsRef", "sourceCatalogRef", "rightsRef"):
        home.pop(key, None)
    target = stage / allocate_object_path(home, "entities", [], load_layout_policy())
    home["assets"] = [{**_media_asset(target, "fixture-home-cover", "image"), "role": "cover"}]
    home["sourceRefs"] = _fixture_sources(target, home["assets"])
    _put(target / "page.md", "# 测试湖\n\n本地合成主页。\n".encode())
    review_path = _put(target / "content_review.json", _fixture_review(HOME_REF, home["executionId"], "4.draft/page.md", (target / "page.md").read_bytes()))
    _bind_review(home, HOME_REF, review_path.read_bytes())
    assert_valid(home, "publish", "entity")
    _put(target / "manifest.json", home)
    target = stage / "creators" / CREATOR_ID
    profile = _json(METADATA_ROOT / "creators/qwq_creator_geo_editor_001/profile.json")
    profile.update(creatorId=CREATOR_ID, authorId=CREATOR_ID, userId=CREATOR_ID, personaId=CREATOR_ID,
                   displayName="离线测试作者", userHandle=CREATOR_ID, publicProfileTagRefs=list(TAG_REFS))
    avatar = _media_asset(target, "fixture-avatar", "avatar")
    profile["assets"] = [avatar]
    profile["avatarAsset"] = {key: avatar[key] for key in ("assetId", "kind", "sha256")}
    profile["sourceRefs"] = _fixture_sources(target, [avatar])
    _put(target / "profile.json", profile)
    _put(target / "_creator.json", {"creatorId": CREATOR_ID, "tagRefs": list(TAG_REFS)})
    for ref in TAG_REFS:
        _put(stage / f"tags/{ref}/_definition.json", (METADATA_ROOT / f"tags/{ref}/_definition.json").read_bytes())
    return stage


def _legacy_payload_digest(root):
    # 旧 _pool 算法的独立 oracle；不用当前排除 records/ 的 pool_payload_digest。
    rows = [{"path": path.relative_to(root).as_posix(), "sha256": digest_bytes(path.read_bytes()), "bytes": path.stat().st_size}
            for path in sorted(root.rglob("*")) if path.is_file() and path.relative_to(root).parts[0] != "_pool"]
    return digest_bytes(canonical_bytes(rows) + b"\n")


@pytest.fixture
def legacy_source(tmp_path, current_source):
    """仅迁移合同使用的旧输入与 exact-byte receipt double；绝不签发生产资格。"""
    import shutil
    from content.release.canonical.object_source_identity import source_identity_digest
    from content.release.canonical.pool_cutover_inventory import _inspect_content
    from core.source_digest import content_source_revision

    publish = tmp_path / "legacy-fixture"
    source = CanonicalSource(current_source)
    for ref in (*POST_REFS, HOME_REF, "creators/" + CREATOR_ID):
        shutil.copytree(source.object_path(ref), publish / ref)
    shutil.copytree(current_source / "tags", publish / "tags")
    _put(publish / HOME_REF / "_entity.json", _json(publish / HOME_REF / "manifest.json"))
    ref = POST_REFS[0]
    root = publish / ref
    execution_id = "20260910--offline-article-fixture--local--pilot-001"
    execution = tmp_path / "tasks" / execution_id
    original = _json(root / "manifest.json")
    original.update(executionId=execution_id, sourceTaskId=execution_id, assetRefsRef="asset.refs.json",
                    creatorRefsRef="creator.refs.json", tagRefsRef="tag.refs.json",
                    sourceCatalogRef="source_catalog.json", rightsRef="rights.json")
    original.pop("sourceRefs")
    original.pop("objectRef")
    shutil.rmtree(root / "sources")
    draft_ref = "4.draft/draft.article.md"
    review = _fixture_review(ref, execution_id, draft_ref, ARTICLE_BYTES)
    review_path = _put(root / "content_review.json", review)
    _bind_review(original, ref, review_path.read_bytes())
    _put(execution / ref / "5.review/content_review.json", review_path.read_bytes())
    _put(execution / ref / draft_ref, ARTICLE_BYTES)
    source_raw = b"Fixture source excerpt; not a real source or rights authority.\n"
    _put(execution / "sources/fixture/source.md", source_raw)
    plan = _put(execution / "sources/plans/fixture.json", {"testDouble": True, "productionAdmission": False})
    candidate_digest = digest({"fixture": "article-source"})
    _put(execution / "sources/fixture/meta.json", {
        "executionId": execution_id, "chosenCandidateDigest": candidate_digest,
        "sourceMarkdownSha256": digest_bytes(source_raw), "sourceUseMode": "factual_reference_only",
        "fetchedAt": STAMP, "canonicalUrl": "https://example.org/offline-test-double", "testDouble": True,
    })
    source_refs_ref = ref + "/1.download/source_refs.json"
    _put(execution / source_refs_ref, {"executionId": execution_id, "objectRef": ref, "sources": [{
        "metaRef": "sources/fixture/meta.json", "sourceRef": "sources/fixture/source.md",
        "sourcePlanRef": "sources/plans/fixture.json", "sourcePlanDigest": digest_bytes(plan.read_bytes()),
        "chosenCandidateDigest": candidate_digest, "sourceUrl": "https://example.org/offline-test-double",
    }]})
    identity = {"executionId": execution_id, "sourceDigest": digest_bytes(source_raw), "entityCatalogDigest": digest(list(TAG_REFS))}
    identity["sourceRevision"] = content_source_revision(source_digest=identity["sourceDigest"], entity_catalog_digest=identity["entityCatalogDigest"])
    identity["identityDigest"] = source_identity_digest(identity)
    original["sourceIdentity"] = identity
    _put(root / "manifest.json", original)
    _put(root / "asset.refs.json", {"assets": []})
    _put(root / "creator.refs.json", {"creatorRefs": [CREATOR_ID]})
    _put(root / "tag.refs.json", {"tagRefs": list(TAG_REFS)})
    _put(root / "rights.json", {"schema": "quwoquan_data.asset_rights_closure", "publishMediaMode": "text_only", "assets": []})
    _put(root / "source_catalog.json", {"schema": "quwoquan_data.source_catalog", "sources": [{
        "sourceUrl": "https://example.org/offline-test-double", "sourceUseMode": "factual_reference_only"}]})
    predecessor = None
    stage_refs = ([source_refs_ref, "sources/fixture/meta.json", "sources/fixture/source.md", "sources/plans/fixture.json"],
                  [ref + "/" + draft_ref], [ref + "/5.review/content_review.json"])
    for ordinal, (stage, refs) in enumerate(zip(("1.download", "4.draft", "5.review"), stage_refs), 1):
        actor_id = "test-reviewer" if stage == "5.review" else "test-author"
        receipt = {"schema": "quwoquan_data.stage_receipt", "executionId": execution_id, "stage": stage,
                   "sequence": ordinal, "predecessor": predecessor, "sealInput": {"digest": digest({"testDouble": stage})},
                   "actor": {"host": "cursor", "modelFamily": "gpt", "sessionId": actor_id,
                             "invocation": {"provider": "openai", "model": "test-double", "runId": actor_id}},
                   "verdict": "pass", "typedIssues": [], "resultRefs": [
                       {"scope": "execution", "ref": path, "digest": digest_bytes((execution / path).read_bytes())} for path in refs]}
        assert_valid(receipt, "execution", "stage_receipt")
        receipt_ref = f"_shared/receipts/{ordinal:03d}-{stage}.json"
        path = _put(execution / receipt_ref, receipt)
        predecessor = {"scope": "execution", "ref": receipt_ref, "digest": digest_bytes(path.read_bytes())}
    record = _json(METADATA_ROOT / TEMPLATES[0] / "_pool/versions/1.json")
    record.update(objectId=original["contentId"], objectRef=ref.removeprefix("posts/"),
                  sourceIdentity=original["sourceIdentity"], sourceAttribution=original["sourceAttribution"],
                  payloadDigest=_legacy_payload_digest(root), canonicalObjectDigest=_legacy_payload_digest(root),
                  **original["admission"])
    assert_valid(record, "release", "pool_object_record")
    _put(root / "_pool/versions/1.json", record)
    authority = _put(tmp_path / "test-author-authority.json", {
        "schema": "quwoquan_data.author_admission_evidence", "authorIds": [CREATOR_ID],
        "processResult": "completed", "qualityResult": "passed", "recordedAt": STAMP,
        "checks": {"profile": "passed", "disclosure": "passed", "avatarQuality": "passed"},
    })
    # 在做负例之前证明原链、review、来源与旧 payload 确实通过真实 validator。
    _inspect_content(root, execution, ref, original, {})
    return {"publish": publish, "root": root, "execution": execution, "authority": authority, "ref": ref}


def test_operator_selection_is_engineering_only_and_explicit():
    value = _json(SELECTION)
    validate_selection(value)
    assert value["purpose"] == "alpha_offline_engineering"
    assert value["authority"]["kind"] == "explicit_user_selection"
    assert value["authority"]["evidence"].strip()
    assert value["authority"]["grantsProductionPremium"] is False
    assert value["authority"]["changesRightsFacts"] is False
    value["qualityScore"] = 0.85
    with pytest.raises(ValueError):
        validate_selection(value)


def test_selection_rejects_outside_cohort_and_duplicate_channels():
    value = selection()
    value["channels"][1]["orderedObjectRefs"] = ["posts/video/outside/1"]
    with pytest.raises(OfflineSnapshotError, match="OUTSIDE_COHORT"):
        validate_selection(value)
    value = selection()
    value["channels"].append(copy.deepcopy(value["channels"][0]))
    with pytest.raises(OfflineSnapshotError, match="CHANNEL_SELECTION"):
        validate_selection(value)


def test_runtime_post_id_executes_current_go_function_for_parity(tmp_path):
    source = (ROOT / "quwoquan_service/services/content-service/internal/content/post/infrastructure/releaseimport/runtime.go").read_text()
    function = re.search(r"func RuntimePostID\(contentID string\) string \{.*?\n\}", source, re.S).group()
    ids = ["qwq_data_faaf0b1d1dfe1a7fb1524e66", "qwq_data_c38c8eb7aa343f94e3a54ffa", "qwq_data_2140521c2de8b435c8c72db7"]
    program = 'package main\nimport("crypto/sha256";"encoding/hex";"strings";"fmt")\n' + function
    program += '\nfunc main(){' + ''.join('fmt.Println(RuntimePostID(' + json.dumps(v) + '));' for v in ids) + '}\n'
    path = tmp_path / "identity.go"
    path.write_text(program)
    env = {**os.environ, "GOCACHE": str(ROOT / ".qwq_output/env/repo/local/offline-go-cache"), "GOTOOLCHAIN": "local", "GOPROXY": "off"}
    result = subprocess.run(["go", "run", str(path)], capture_output=True, text=True, check=True, env=env)
    assert result.stdout.splitlines() == [runtime_post_id(v) for v in ids]
    assert runtime_post_id("") == ""


def test_current_schema_cohort_complete_and_deterministic(tmp_path, current_source):
    first = build_bundle(repo=ROOT, publish_root=current_source, selection=selection(), source_revision=REVISION, library_root=current_source / "absent-library", carried_root=current_source / "absent-carried")
    import shutil
    relocated = tmp_path / "relocated-current-source"
    shutil.copytree(current_source, relocated)
    second = build_bundle(repo=ROOT, publish_root=relocated, selection=selection(), source_revision=REVISION,
                          library_root=tmp_path / "also-absent-library", carried_root=tmp_path / "also-absent-carried")
    assert canonical_bytes(first.manifest) == canonical_bytes(second.manifest)
    assert first.media_bytes == second.media_bytes
    bundle = first.manifest
    assert bundle["counts"] == {"posts": 3, "article": 1, "image": 1, "video": 1, "creators": 1, "homepages": 1,
                                "tags": len(TAG_REFS), "media": 2, "mediaBytes": len(tiny_png_bytes()) + len(TINY_MP4)}
    assert [row["sourceObjectRef"] for row in bundle["posts"]] == list(POST_REFS)
    assert bundle["provenance"]["operatorSelection"] == selection()
    assert "home_channels" not in bundle["configuration"]["content"]
    assert "sourceReleaseId" not in bundle and "sourceManifestDigest" not in bundle
    assert "releaseClass" not in bundle["provenance"]
    article = bundle["posts"][0]["detail"]
    assert article["articleMarkdown"] == ARTICLE_BYTES.decode()
    assert article["articleAssetManifest"]["assets"] == []
    assert "coverUrl" not in article
    for source_attribution in bundle["provenance"]["sourceAttributions"]:
        ref = source_attribution["sourceObjectRef"]
        assert source_attribution["document"] == _json(CanonicalSource(current_source).object_path(ref) / "manifest.json")["sourceAttribution"]
    video = bundle["posts"][2]["detail"]
    assert video["sourceAttribution"]["commercialAuthorizationStatus"] == "unverified"
    assert video["sourceAttribution"]["publicationAdmission"] == "research_release"
    assert all(m["canonicalReference"].startswith("media/") and "://" not in m["canonicalReference"] for m in bundle["media"])
    result = export_bundle(first, tmp_path / "alpha")
    assert export_bundle(first, tmp_path / "alpha", check=True) == result
    pin = tmp_path / "pin.g.dart"
    write_dart_identity(result, pin)
    write_dart_identity(result, pin, check=True)
    assert result["manifestDigest"] in pin.read_text()
    pin.write_text(pin.read_text().replace(result["manifestDigest"], "sha256:" + "0" * 64))
    with pytest.raises(OfflineSnapshotError, match="IDENTITY_OUTPUT_DRIFT"):
        write_dart_identity(result, pin, check=True)
    raw = (tmp_path / "alpha/manifest.json").read_bytes()
    assert result["manifestDigest"] == "sha256:" + hashlib.sha256(raw).hexdigest()
    for m in bundle["media"]:
        path = tmp_path / "alpha/media" / Path(m["assetPath"]).name
        assert path.stat().st_size == m["byteLength"]
        assert "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() == m["sha256"]
    assert export_bundle(first, tmp_path / "alpha") == result
    print("TEST_DOUBLE_OFFLINE_EXPORT_IDENTITY=" + json.dumps(result, ensure_ascii=False, sort_keys=True))


@pytest.mark.parametrize("fault", ["missing", "corrupt"])
def test_missing_or_corrupt_media_does_not_publish_manifest(tmp_path, current_source, fault):
    first = build_bundle(repo=ROOT, publish_root=current_source, selection=selection(), source_revision=REVISION, library_root=current_source / "absent-library", carried_root=current_source / "absent-carried")
    asset = next(iter(first.media_bytes))
    if fault == "missing":
        del first.media_bytes[asset]
    else:
        first.media_bytes[asset] = b"corrupted"
    with pytest.raises(OfflineSnapshotError, match="MEDIA"):
        export_bundle(first, tmp_path / "alpha")
    assert not (tmp_path / "alpha/manifest.json").exists()


def test_symlink_output_rejected(tmp_path, current_source):
    target = tmp_path / "outside"
    target.mkdir()
    (tmp_path / "alpha").symlink_to(target, target_is_directory=True)
    first = build_bundle(repo=ROOT, publish_root=current_source, selection=selection(), source_revision=REVISION, library_root=current_source / "absent-library", carried_root=current_source / "absent-carried")
    with pytest.raises(OfflineSnapshotError, match="SYMLINK"):
        export_bundle(first, tmp_path / "alpha")
    assert not list(target.iterdir())


def test_holding_backup_missing_corrupt_and_symlink_are_distinct(tmp_path):
    library, carried = tmp_path / "library", tmp_path / "carried"
    raw = b"exact-test-image-body"
    sha = "sha256:" + hashlib.sha256(raw).hexdigest()
    with pytest.raises(OfflineSnapshotError, match="HOLDING_MISSING"):
        _read_media(sha, len(raw), ".jpg", library=library, carried=carried)
    carried.mkdir()
    backup = carried / (sha[7:] + ".jpg")
    backup.write_bytes(raw)
    assert _read_media(sha, len(raw), ".jpg", library=library, carried=carried) == raw
    primary = library_cas_path("media", sha, library_root=library)
    primary.parent.mkdir(parents=True)
    primary.write_bytes(b"corrupt")
    with pytest.raises(OfflineSnapshotError, match="HASH_OR_SIZE_DRIFT"):
        _read_media(sha, len(raw), ".jpg", library=library, carried=carried)
    primary.unlink()
    primary.symlink_to(backup)
    with pytest.raises(OfflineSnapshotError, match="SYMLINK"):
        _read_media(sha, len(raw), ".jpg", library=library, carried=carried)


def test_strict_public_projection_rejects_internal_and_unknown_fields():
    validator = PublicContractValidator(ROOT)
    view = {"postId": "post", "contentType": "article", "likeCount": 0, "commentCount": 0, "shareCount": 0}
    validator.validate_projection(view, "content_post_projection")
    for key in ("payloadDigest", "qualityScore", "releaseClass", "unexpected"):
        with pytest.raises(OfflineSnapshotError, match="PUBLIC_PROJECTION_INVALID"):
            validator.validate_projection({**view, key: "forbidden"}, "content_post_projection")


def test_current_homepage_identity_parity(tmp_path):
    source = (ROOT / "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/domain/model/homepage.go").read_text()
    functions = [re.search(r"func " + name + r"\(.*?\n\}", source, re.S).group() for name in ("StableID", "CanonicalEntityID", "canonicalSlug")]
    program = 'package main\nimport("crypto/sha256";"encoding/hex";"strings";"unicode";"fmt")\n' + '\n'.join(functions)
    program += '\nfunc main(){fmt.Println(StableID("", "qwq_data", "地点/景区/西湖", "sight", "西湖"))}\n'
    path = tmp_path / "homepage_identity.go"
    path.write_text(program)
    env = {**os.environ, "GOCACHE": str(ROOT / ".qwq_output/env/repo/local/offline-go-cache"), "GOTOOLCHAIN": "local", "GOPROXY": "off"}
    result = subprocess.run(["go", "run", str(path)], capture_output=True, text=True, check=True, env=env)
    assert result.stdout.strip() == runtime_homepage_id("/entity/地点/景区/西湖")


def test_bundle_mutation_never_writes_a_manifest(tmp_path, current_source):
    bundle = build_bundle(repo=ROOT, publish_root=current_source, selection=selection(), source_revision=REVISION, library_root=current_source / "absent-library", carried_root=current_source / "absent-carried")
    bundle.manifest["posts"][0]["projection"]["title"] = "changed"
    with pytest.raises(OfflineSnapshotError, match="BUNDLE_IDENTITY_DRIFT"):
        export_bundle(bundle, tmp_path / "alpha")
    assert not (tmp_path / "alpha/manifest.json").exists()


def test_nonprod_only_asset_registration():
    import yaml
    pubspec = yaml.safe_load((ROOT / "quwoquan_app/pubspec.yaml").read_text())
    registrations = [r for r in pubspec["flutter"]["assets"] if isinstance(r, dict) and r["path"].startswith("assets/content/alpha/")]
    assert {r["path"] for r in registrations} == {
        "assets/content/alpha/manifest.json", "assets/content/alpha/bundle_identity.json", "assets/content/alpha/media/",
    }
    assert all(r["flavors"] == ["nonprod"] for r in registrations)


def test_cli_registers_downstream_export_without_producer_fields():
    import argparse
    from content.release.canonical.handler_cli import register_parser
    parser = argparse.ArgumentParser()
    register_parser(parser.add_subparsers())
    args = parser.parse_args(["release", "export-offline", "--selection-file", "selection.json", "--source-revision", REVISION,
                              "--publish-root", "publish", "--output-dir", "alpha"])
    assert args.handler.__name__ == "handle_export_offline"
    assert not hasattr(args, "release_class") and not hasattr(args, "milestone")
    migration = parser.parse_args(["release", "migrate-offline-source", "--selection-file", "selection.json", "--source-revision", REVISION,
                                   "--publish-root", "old", "--executions-root", "tasks", "--author-authority", "original.json", "--output-dir", "independent"])
    assert migration.handler.__name__ == "handle_migrate_offline_source"
    assert not hasattr(migration, "activate")


def test_array_enum_transcribes_required_modifications_without_default(current_source):
    validator = PublicContractValidator(ROOT)
    manifest = _json(CanonicalSource(current_source).object_path(POST_REFS[2]) / "manifest.json")
    attribution = manifest["sourceAttribution"]
    validator.validate_type(attribution, "SourceAttribution")
    assert attribution["derivedModifications"] == ["format_conversion", "video_frame_extraction"]
    for wrong in (None, ["invented_edit"]):
        with pytest.raises(OfflineSnapshotError, match="PUBLIC_PROJECTION_INVALID"):
            validator.validate_type({**attribution, "derivedModifications": wrong}, "SourceAttribution")
    del attribution["derivedModifications"]
    with pytest.raises(OfflineSnapshotError, match="PUBLIC_PROJECTION_INVALID"):
        validator.validate_type(attribution, "SourceAttribution")


def test_layout_two_resolution_records_physical_refs_and_rejects_collision(current_source):
    from content.release.canonical.offline_snapshot_source import CanonicalSource
    source = CanonicalSource(current_source)
    ref = selection()["objectRefs"][0]
    source.capture_object(ref)
    assert "/p0001/" in source.object_path(ref).as_posix()
    assert source.json(ref + "/manifest.json")["objectRef"] == ref.removeprefix("posts/")
    assert all("/p0001/" in fact["ref"] for fact in source.file_facts())
    import shutil
    shutil.copytree(source.object_path(ref), current_source / "posts/article/文化/p0002/collision/1")
    with pytest.raises(ValueError, match="IDENTITY_CONFLICT"):
        CanonicalSource(current_source).capture_object(ref)


@pytest.mark.parametrize("fault,code", [
    ("media_corrupt", "HASH_OR_SIZE_DRIFT"), ("media_missing", "OFFLINE.MEDIA_MISSING"),
    ("evidence_corrupt", "SOURCE_EVIDENCE_DRIFT"), ("evidence_missing", "SOURCE_EVIDENCE_MISSING"),
    ("rights_digest", "RIGHTS_DIGEST_DRIFT"), ("rights_missing", "RIGHTS_EVIDENCE_MISSING"),
    ("attribution_missing", "ATTRIBUTION_MISSING_OR_CONFLICTING"),
])
def test_current_source_media_and_evidence_never_fallback_to_holders(tmp_path, current_source, monkeypatch, fault, code):
    from content.release.canonical import offline_snapshot_source
    from content.release.canonical.object_transaction_contract import ObjectTransactionError
    root = CanonicalSource(current_source).object_path(POST_REFS[1])
    asset = _json(root / "manifest.json")["assets"][0]
    library, carried = tmp_path / "valid-library", tmp_path / "valid-carried"
    raw = (root / asset["path"]).read_bytes()
    _put(library_cas_path("media", asset["sha256"], library_root=library), raw)
    _put(carried / (asset["sha256"][7:] + ".png"), raw)

    def forbidden_holder_read(*args, **kwargs):
        pytest.fail("current canonical 消费不得访问 holder 或恢复缺失证据")

    monkeypatch.setattr(offline_snapshot_source, "_read_media", forbidden_holder_read)
    if fault.startswith("media_"):
        path = root / asset["path"]
        path.unlink() if fault.endswith("missing") else path.write_bytes(b"corrupt")
    elif fault.startswith("evidence_"):
        path = root / "sources/fixture/evidence.json"
        path.unlink() if fault.endswith("missing") else path.write_bytes(b"corrupt")
    else:
        path = root / "sources/fixture/source.json"
        document = _json(path)
        if fault == "rights_digest":
            document["assets"][0]["sha256"] = "sha256:" + "0" * 64
        elif fault == "rights_missing":
            document["assets"] = []
        else:
            del document["assets"][0]["attribution"]
        _put(path, document)
    # 媒体缺失和损坏分别 typed 阻断；来源证据保持对象事务的错误身份。
    expected_error = ObjectTransactionError if fault.startswith("evidence_") else OfflineSnapshotError
    with pytest.raises(expected_error, match=code):
        build_bundle(repo=ROOT, publish_root=current_source, selection=selection(), source_revision=REVISION,
                     library_root=library, carried_root=carried)


@pytest.mark.parametrize("field", ["assetId", "kind", "sha256"])
def test_creator_avatar_identity_must_match_the_single_current_asset(current_source, field):
    path = current_source / "creators" / CREATOR_ID / "profile.json"
    profile = _json(path)
    assert set(profile["avatarAsset"]) == {"assetId", "kind", "sha256"}
    assert len(profile["assets"]) == 1
    profile["avatarAsset"][field] = "sha256:" + "0" * 64 if field == "sha256" else "wrong-identity"
    _put(path, profile)
    with pytest.raises(OfflineSnapshotError, match="CREATOR_AVATAR_BINDING_DRIFT"):
        build_bundle(repo=ROOT, publish_root=current_source, selection=selection(), source_revision=REVISION)


@pytest.mark.parametrize("ref", ["../outside", "/outside", "media/../../outside", r"media\outside", "media//outside"])
def test_input_paths_cannot_escape_or_normalize_silently(tmp_path, ref):
    from content.release.canonical.offline_snapshot_contract import safe_path
    with pytest.raises(OfflineSnapshotError, match="INPUT_PATH_INVALID"):
        safe_path(tmp_path, ref)


def test_legacy_records_use_original_digest_algorithm_and_reject_drift(legacy_source):
    from content.release.canonical.pool_cutover_inventory import _records
    ref, root = legacy_source["ref"], legacy_source["root"]
    manifest = json.loads((root / "manifest.json").read_bytes())
    review = json.loads((root / "content_review.json").read_bytes())
    record = _records(root, ref, manifest, review)
    assert record["sourceAttribution"] == manifest["sourceAttribution"]
    (root / "source_catalog.json").write_bytes(b"{}")
    with pytest.raises(ValueError, match="ORIGINAL_PAYLOAD_DRIFT"):
        _records(root, ref, manifest, review)


def test_article_conversion_preserves_original_review_rights_and_record(tmp_path, legacy_source):
    from content.release.canonical.offline_snapshot_migration import _convert_content, _capture
    ref, root, execution = (legacy_source[key] for key in ("ref", "root", "execution"))
    original = _json(root / "manifest.json")
    before = _capture(root)
    before_execution = _capture(execution)
    target = tmp_path / "converted"
    manifest = _convert_content(root, execution, ref, target, library=tmp_path / "library", carried=tmp_path / "carried")
    assert_valid(manifest, "content", "post_manifest")
    assert manifest["version"] == original["version"] + 1
    assert manifest["sourceAttribution"] == original["sourceAttribution"]
    assert manifest["sourceIdentity"] == original["sourceIdentity"]
    assert manifest["admission"] == original["admission"]
    assert manifest["contentId"] == original["contentId"]
    assert (target / "content_review.json").read_bytes() == before["content_review.json"]
    assert (target / "article.md").read_bytes() == before["article.md"]
    assert not any((target / name).exists() for name in ("asset.refs.json", "creator.refs.json", "tag.refs.json", "rights.json", "_pool"))
    assert manifest["sourceRefs"]
    assert json.loads((target / "records/1.json").read_bytes())["rightsAuthorityDigest"] == original["admission"]["rightsAuthorityDigest"]
    assert _capture(root) == before
    assert _capture(execution) == before_execution


@pytest.mark.parametrize("fault,code", [
    ("draft", "ORIGINAL_CHAIN_INVALID"), ("source", "ORIGINAL_CHAIN_INVALID"),
    ("same_actor", "ORIGINAL_CHAIN_INVALID"), ("rights", "ORIGINAL_RECORD_AUTHORITY_INVALID"),
])
def test_article_conversion_rejects_changed_original_authority_before_staging(tmp_path, legacy_source, fault, code):
    from content.release.canonical.offline_snapshot_migration import _convert_content, _capture
    root, execution, ref = (legacy_source[key] for key in ("root", "execution", "ref"))
    if fault == "draft":
        (execution / ref / "4.draft/draft.article.md").write_bytes(b"not the reviewed draft")
    elif fault == "source":
        (execution / "sources/fixture/source.md").write_bytes(b"not the frozen source")
    elif fault == "same_actor":
        path = execution / "_shared/receipts/003-5.review.json"
        review_receipt = _json(path)
        review_receipt["actor"] = _json(execution / "_shared/receipts/002-4.draft.json")["actor"]
        _put(path, review_receipt)
    else:
        path = root / "_pool/versions/1.json"
        record = _json(path)
        record["rightsAuthorityDigest"] = "sha256:" + "0" * 64
        _put(path, record)
    before, before_execution = _capture(root), _capture(execution)
    target = tmp_path / "must-not-stage"
    with pytest.raises(ValueError, match=code):
        _convert_content(root, execution, ref, target, library=tmp_path / "library", carried=tmp_path / "carried")
    assert not target.exists()
    assert _capture(root) == before
    assert _capture(execution) == before_execution


def test_creator_conversion_keeps_identity_only_avatar_and_full_assets(tmp_path, current_source):
    from content.release.canonical.offline_snapshot_migration import _convert_creator, _capture
    source_root = tmp_path / "old-creator"
    current = current_source / "creators" / CREATOR_ID
    profile = _json(current / "profile.json")
    asset = profile.pop("assets")[0]
    profile.pop("sourceRefs")
    authority = _put(tmp_path / "fixture-authority.json", {
        "schema": "quwoquan_data.author_admission_evidence", "authorIds": [CREATOR_ID],
        "processResult": "completed", "qualityResult": "passed", "recordedAt": STAMP,
        "checks": {"profile": "passed", "disclosure": "passed", "avatarQuality": "passed"},
    })
    profile["admission"]["evidenceDigest"] = digest_bytes(authority.read_bytes())
    _put(source_root / "profile.json", profile)
    _put(source_root / "_creator.json", (current / "_creator.json").read_bytes())
    _put(source_root / "assets.refs.json", {"assets": [asset]})
    rights = {"canonicalFilePage": "https://example.org/test-avatar", "sourceUseMode": "factual_reference_only",
              "fetchedAt": STAMP, "attribution": "仅合成头像测试，不是许可凭证",
              "asset": {key: asset[key] for key in ("sha256", "bytes", "mimeType")}}
    snapshot_path = _put(source_root / "rights_snapshots/avatar.json", {
        "testDouble": True, "productionAdmission": False, "assetId": asset["assetId"], "commercialRights": rights,
    })
    library, carried = tmp_path / "library", tmp_path / "carried"
    _put(carried / (asset["sha256"][7:] + ".png"), tiny_png_bytes())
    before = _capture(source_root)
    target = tmp_path / "converted-creator"
    converted = _convert_creator(source_root, target, authority, library=library, carried=carried)
    assert converted["version"] == profile["version"] + 1
    assert converted["avatarAsset"] == profile["avatarAsset"]
    assert set(converted["avatarAsset"]) == {"assetId", "kind", "sha256"}
    assert len(converted["assets"]) == 1
    current_asset = converted["assets"][0]
    assert (target / current_asset["path"]).read_bytes() == tiny_png_bytes()
    assert current_asset["sha256"] == digest_bytes(tiny_png_bytes())
    assert current_asset["sourceRefs"] == converted["sourceRefs"]
    assert (target / "sources/avatar/evidence.json").read_bytes() == snapshot_path.read_bytes()
    assert _capture(source_root) == before
    source = CanonicalSource(tmp_path / "converted")
    import shutil
    shutil.copytree(target, source.root / "creators" / CREATOR_ID)
    from content.release.canonical.offline_snapshot_source import capture_media
    media, bodies = capture_media(source, ["creators/" + CREATOR_ID])
    assert media[0]["assetId"] == asset["assetId"]
    assert list(bodies.values()) == [tiny_png_bytes()]
    snapshot = _json(snapshot_path)
    snapshot["commercialRights"]["asset"]["sha256"] = "sha256:" + "0" * 64
    _put(snapshot_path, snapshot)
    with pytest.raises(OfflineSnapshotError, match="MIGRATION_AVATAR_EVIDENCE_DRIFT"):
        _convert_creator(source_root, tmp_path / "must-not-convert-creator", authority, library=library, carried=carried)
    assert not (tmp_path / "must-not-convert-creator").exists()


def test_missing_original_receipts_stop_before_any_staging(tmp_path, legacy_source):
    from content.release.canonical.offline_snapshot_migration import migrate_source, _capture
    # fixture 已先通过原链核验；显式删除测试 receipt，不把 approved 当重审许可。
    (legacy_source["execution"] / "_shared/receipts/003-5.review.json").unlink()
    output = tmp_path / "must-not-exist" / "stage"
    before = _capture(legacy_source["publish"])
    before_execution = _capture(legacy_source["execution"])
    with pytest.raises(ValueError, match="ORIGINAL_CHAIN_INVALID"):
        migrate_source(publish_root=legacy_source["publish"], executions_root=legacy_source["execution"].parent,
                       author_authority=legacy_source["authority"], output_dir=output, selection=selection(), source_revision=REVISION,
                       library_root=tmp_path / "library", carried_root=tmp_path / "carried")
    assert not output.parent.exists()
    assert _capture(legacy_source["publish"]) == before
    assert _capture(legacy_source["execution"]) == before_execution


def test_partial_media_binding_and_wrong_detail_identity_fail_closed(current_source):
    built = build_bundle(repo=ROOT, publish_root=current_source, selection=selection(), source_revision=REVISION, library_root=current_source / "absent-library", carried_root=current_source / "absent-carried")
    validator = PublicContractValidator(ROOT)
    value = copy.deepcopy(built.manifest)
    value["posts"][2]["detail"]["mediaItems"][0]["coverUrl"] = "media/not-selected"
    with pytest.raises(OfflineSnapshotError, match="POSTER_BINDING_INVALID"):
        validate_bundle(value, validator)
    value = copy.deepcopy(built.manifest)
    value["posts"][0]["detail"]["postId"] = "another-post"
    with pytest.raises(OfflineSnapshotError, match="POST_DETAIL_IDENTITY_DRIFT"):
        validate_bundle(value, validator)
