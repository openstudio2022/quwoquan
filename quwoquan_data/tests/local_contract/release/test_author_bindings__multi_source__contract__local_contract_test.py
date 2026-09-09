# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-039.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-039.t2
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-039.t3
"""Data author 绑定最小切片：真实零网络 acquire、seal 与执行包投影，不访问真实 pool。"""
from __future__ import annotations

import hashlib
import json
import socket
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from content.execution import seal
from content.release.canonical import final_surface_projection as projection
from content.release.canonical.object_transaction_contract import ObjectTransactionError
from content.release.canonical.post_transaction_assets import source_assets
from content.source import acquire
from content.source.homepage_article_source_attribution import encyclopedia_source_attribution
from core import paths
from core.schema import assert_valid

EXECUTION_ID = "20260908--travel-image-bindings--local--pilot-001"
IMAGE_REF = "posts/image/风光/同一作品/1"
HOME_REF = "entities/地点/景区/西湖"
OTHER_REF = "entities/地点/景区/另一对象"
TARGET = {"name": "西湖", "entityType": "地点/景区", "region": "中国/浙江省/杭州市", "publishTitle": "同一作品", "publishAngle": "风光", "publishSeq": 1}
AUTHOR = {"host": "cursor", "modelFamily": "gpt", "sessionId": "author", "invocation": {"provider": "openai", "model": "gpt-5", "runId": "author-run"}}
REVIEWER = {**AUTHOR, "sessionId": "reviewer", "invocation": {**AUTHOR["invocation"], "runId": "reviewer-run"}}


def _write(path: Path, value: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, str):
        path.write_text(value, encoding="utf-8")
    else:
        path.write_bytes(seal.canonical_bytes(value))
    return path


@pytest.fixture(autouse=True)
def isolated_local_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(paths, "DATA_EXECUTIONS_ROOT", tmp_path / "tasks")
    monkeypatch.setenv("QWQ_LIBRARY_ROOT", str(tmp_path / "library"))

    def refuse(*_args, **_kwargs):
        raise AssertionError("本契约只允许本地输入，不得出网")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


def _execution(carrier: str, refs: list[str]) -> Path:
    root = paths.execution_root(EXECUTION_ID.replace("-image-", f"-{carrier}-"))
    _write(root / "execution_manifest.json", {"schema": "quwoquan_data.content_execution_manifest", "executionId": root.name})
    _write(root / "0.plan/target_set.json", {
        "schema": "quwoquan_data.target_set", "executionId": root.name, "carrier": carrier,
        "selectionPolicy": "frozen", "entityCatalogDigest": "sha256:" + "0" * 64,
        "candidateBinding": {"scope": "output", "ref": "fixture.json", "digest": "sha256:" + "1" * 64, "candidateCount": len(refs)},
        "targetCount": len(refs), "targetRefs": refs,
        "targets": [{"name": ref.rsplit("/", 1)[-1], "entityType": TARGET["entityType"], "region": TARGET["region"]} if carrier == "homepage" else TARGET for ref in refs],
    })
    return root


def _ingest(root: Path, targets: list[dict]) -> None:
    request = _write(root.parent / "ingest.json", {"schema": "quwoquan_data.ingest_manifest", "executionId": root.name, "targets": targets})
    result = acquire.acquire(execution_id=root.name, request_path=request)
    assert result["failed"] == 0 and result["ingested"] == len(targets), result


def _images(tmp_path: Path, *, collision: bool = False) -> tuple[Path, list[str]]:
    root = _execution("image", [IMAGE_REF])
    sources = []
    for index in range(2 if collision else 3):
        image = tmp_path / f"input-{index}.jpg"
        Image.new("RGB", (32, 24), (index * 90, 40, 70)).save(image, "JPEG")
        sources.append({
            "kind": "image", "sourceUrl": "https://photos.example/work/one", "directUrl": f"https://photos.example/original/{index}.jpg",
            "filePath": str(image), "sha1": hashlib.sha1(image.read_bytes()).hexdigest(),
            "license": "CC BY-NC 4.0", "licenseUrl": "https://creativecommons.org/licenses/by-nc/4.0/", "creator": "同一作者",
            "description": "same-work-description" if collision else f"work-photo-{index}", "relevance": "同作品不同视角",
            "watermarkStatus": "present", "watermarkKind": "author_signature", "watermarkNote": "作者署名",
        })
    _ingest(root, [{"targetRef": IMAGE_REF, "sources": sources}])
    return root, sorted(source_assets(root), reverse=True)


def _image_draft(root: Path, refs: list[str], captions: dict | None = None) -> dict:
    draft = {"title": "同一作品", "caption": "整组总说明", "assetRefs": refs}
    if captions is not None:
        draft["assetCaptions"] = captions
    _write(root / IMAGE_REF / "4.draft/image_work.json", draft)
    return draft


def _seal(root: Path, stage: str, *, reviews: dict | None = None) -> dict:
    payload = {"actor": REVIEWER if stage == "5.review" else AUTHOR, "verdict": "pass"}
    if reviews is not None:
        payload["reviews"] = reviews
    request = _write(root.parent / f"{stage}.json", payload)
    return seal.seal_stage(execution_id=root.name, stage=stage, input_path=request)


def _intent(root: Path, target_ref: str, carrier: str) -> dict:
    return projection._author_intent(
        object_dir=root / target_ref, carrier=carrier, target=TARGET,
        source_rows=projection._source_rows(root, root / target_ref), asset_index=source_assets(root),
    )


@pytest.mark.parametrize("caption_mode", ["different", "partial", "work_caption"])
def test_ordered_image_captions_survive_seal_review_and_full_manifest(tmp_path: Path, caption_mode: str) -> None:
    root, all_refs = _images(tmp_path)
    refs = all_refs[:2]
    captions = {Path(refs[0]).name: "第一张细节", refs[1]: "第二张远景"} if caption_mode == "different" else {"assets/" + Path(refs[0]).name: "第一张细节"} if caption_mode == "partial" else None
    _image_draft(root, refs, captions)
    _seal(root, "1.download")
    _seal(root, "4.draft")
    _seal(root, "5.review", reviews={IMAGE_REF: {"decision": "approved", "blockingIssues": [], "advisories": []}})
    draft = json.loads((root / IMAGE_REF / "4.draft/image_work.json").read_bytes())
    assert draft["assetRefs"] == refs
    result = projection.project_publish_final_surface(execution_root=root, object_dir=root / IMAGE_REF, target_ref=IMAGE_REF, target=TARGET, carrier="image")
    assets = result["manifest"]["assets"]
    expected = ["第一张细节", "第二张远景"] if caption_mode == "different" else ["第一张细节", "整组总说明"] if caption_mode == "partial" else ["整组总说明"] * 2
    assert [row["sourceAssetRef"] for row in assets] == refs
    assert [row["caption"] for row in assets] == expected
    assert result["manifest"]["caption"] == "整组总说明"
    assert result["manifest"]["sourceAttribution"]["publicationAdmission"] == "production_release"
    assert result["manifest"]["sourceAttribution"]["commercialAuthorizationStatus"] == "unverified"
    assert [row["fileName"] for row in assets] == ["assets/" + Path(ref).name for ref in refs]
    index = source_assets(root)
    review = json.loads((root / IMAGE_REF / "5.review/content_review.json").read_bytes())
    assert {row["assetRef"] for row in review["assetRights"]} == set(refs)
    for row in assets:
        original = index[row["sourceAssetRef"]]
        assert row["sha256"] == original["sha256"]
        assert row["license"] == original["license"]
        assert row["rightsAuditStatus"] == "unverified"
        assert row["watermarkStatus"] == "present"
        assert row["distributionDecision"] == original["distributionDecision"]
    assert projection.project_publish_final_surface(execution_root=root, object_dir=root / IMAGE_REF, target_ref=IMAGE_REF, target=TARGET, carrier="image")["replayed"] is True


@pytest.mark.parametrize("carrier", ["image", "video"])
@pytest.mark.parametrize("authorization", ["verified", "unverified"])
def test_publication_does_not_derive_commercial_authorization(carrier: str, authorization: str) -> None:
    asset = {
        "creator": "原作者", "collectionPageUrl": "https://photos.example/work/one",
        "license": "许可原文", "termsUrl": "https://photos.example/terms",
        "authorizationProof": "https://photos.example/authorization",
        "commercialAuthorizationStatus": authorization,
        "distributionDecision": "production_allowed", "rightsAuditStatus": "verified",
    }
    result = projection.media_attribution([asset], carrier=carrier, collected_at="2026-09-09T00:00:00Z")
    assert result["publicationAdmission"] == "production_release"
    assert result["commercialAuthorizationStatus"] == authorization
    mixed = projection.media_attribution([asset, {**asset, "commercialAuthorizationStatus": "unverified"}], carrier=carrier, collected_at="2026-09-09T00:00:00Z")
    assert mixed["commercialAuthorizationStatus"] == "unverified"


@pytest.mark.parametrize("bad_case", ["unknown_caption", "unselected_caption", "caption_alias", "asset_alias", "unknown_asset", "blank_caption", "ambiguous_caption"])
def test_author_seal_rejects_bad_image_bindings_before_publish(tmp_path: Path, bad_case: str) -> None:
    root, all_refs = _images(tmp_path, collision=bad_case == "ambiguous_caption")
    refs = all_refs[:2]
    captions = {
        "unknown_caption": {"missing.jpg": "未知"},
        "unselected_caption": {all_refs[-1]: "未选图"},
        "ambiguous_caption": {Path(refs[0]).name: "无法判定是哪一图"},
        "caption_alias": {refs[0]: "同一图", Path(refs[0]).name: "别名重复"},
        "blank_caption": {refs[0]: "  "},
    }.get(bad_case)
    if bad_case == "asset_alias":
        refs = [refs[0], "assets/" + Path(refs[0]).name]
    elif bad_case == "unknown_asset":
        refs = ["missing.jpg"]
    _image_draft(root, refs, captions)
    _seal(root, "1.download")
    with pytest.raises(seal.SealError, match="4.draft pass 必须至少有一个合规产物"):
        _seal(root, "4.draft")
    results, issues = seal._seal_author(root, EXECUTION_ID, [IMAGE_REF])
    assert results == [] and issues[0]["code"] == "DATA.SEAL.DRAFT_INVALID"
    assert not (root / IMAGE_REF / "manifest.json").exists()
    with pytest.raises(ObjectTransactionError):
        _intent(root, IMAGE_REF, "image")


@pytest.mark.parametrize("stable_ids", [True, False])
def test_real_project_assets_disambiguates_same_description_without_reordering(tmp_path: Path, stable_ids: bool) -> None:
    root, all_refs = _images(tmp_path, collision=True)
    refs = all_refs[:2]
    assert len(refs) == 2 and len({Path(ref).name for ref in refs}) == 1
    assert Path(refs[0]).name == "001_same-work-description.jpg"
    if not stable_ids:
            # 来源未声明可选稳定 ID 时，以完整来源 ref 摘要消歧，不依赖文件顺序。
        for ref in refs:
            index_path = (root / ref).parent / "index.json"
            index = json.loads(index_path.read_bytes())
            index["assets"][0].pop("sourceAssetId")
            _write(index_path, index)
    _image_draft(root, refs, {refs[0]: "近景", refs[1]: "远景"})
    intent = _intent(root, IMAGE_REF, "image")
    assets, files = projection._project_assets(execution_root=root, object_dir=root / IMAGE_REF, carrier="image", compose=intent, draft=intent["draft"])
    assert [row["sourceAssetRef"] for row in assets] == refs
    assert [row["caption"] for row in assets] == ["近景", "远景"]
    assert len(files) == len({row["assetId"] for row in assets}) == 2
    for row in assets:
        assert files[Path(row["fileName"])] == root / row["sourceAssetRef"]
        assert row["sha256"] == seal.sha256(files[Path(row["fileName"])].read_bytes())
    _image_draft(root, list(reversed(refs)), {refs[0]: "近景", refs[1]: "远景"})
    reversed_intent = _intent(root, IMAGE_REF, "image")
    reversed_assets, reversed_files = projection._project_assets(execution_root=root, object_dir=root / IMAGE_REF, carrier="image", compose=reversed_intent, draft=reversed_intent["draft"])
    assert {row["sourceAssetRef"]: row for row in assets} == {row["sourceAssetRef"]: row for row in reversed_assets}
    assert files == reversed_files
    # 仍调用完整 manifest 投影，不能仅靠 helper 的路径字符串断言。
    _write(root / "_shared/receipts/002-4.draft.json", {"actor": AUTHOR})
    surface = projection._post_surface(execution_root=root, object_dir=root / IMAGE_REF, target_ref=IMAGE_REF, target=TARGET, carrier="image", compose=intent, source_rows=projection._source_rows(root, root / IMAGE_REF))
    manifest = json.loads(surface[Path("manifest.json")])
    assert manifest["assets"] == assets
    with pytest.raises(ObjectTransactionError, match="collide"):
        projection._project_assets(execution_root=root, object_dir=root / IMAGE_REF, carrier="article", compose=intent, draft=intent["draft"])


def _homepages(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    root = _execution("homepage", [HOME_REF, OTHER_REF])
    sources = []
    for source_id, url in [("wiki", "https://zh.wikipedia.org/wiki/西湖"), ("toutiao", "https://www.baike.com/wiki/西湖"), ("web", "https://example.org/西湖")]:
        page = _write(tmp_path / f"{source_id}.md", "# 西湖\n\n本地已取得事实。\n")
        sources.append({"kind": "page", "sourceUrl": url, "title": "西湖", "sourceMarkdownPath": str(page), "license": "CC BY-SA 4.0", "licenseUrl": "https://creativecommons.org/licenses/by-sa/4.0/", "creator": "词条编辑", "relevance": "实体事实"})
    other = {**sources[0], "sourceUrl": "https://zh.wikipedia.org/wiki/另一对象", "title": "另一对象"}
    _ingest(root, [{"targetRef": HOME_REF, "sources": sources}, {"targetRef": OTHER_REF, "sources": [other]}])
    rows = projection._source_rows(root, root / HOME_REF)
    refs = {"wiki" if "wikipedia" in row["sourceId"] else "toutiao" if "toutiao" in row["sourceId"] else "web": row["sourceRef"] for row in rows}
    refs["other"] = projection._source_rows(root, root / OTHER_REF)[0]["sourceRef"]
    return root, refs


def _homepage_draft(root: Path, primary: str | None) -> Path:
    frontmatter = "title: 西湖\ntagRefs: [Entity/地点/景区]\ncreatorProfileId: 'qwq_creator_geo_editor_001'\n"
    if primary is not None:
        frontmatter += f"primarySourceRef: '{primary}'\n"
    return _write(root / HOME_REF / "4.draft/page.md", f"---\n{frontmatter}---\n# 西湖\n\n正文。\n")


@pytest.mark.parametrize("selected", ["wiki", "toutiao"])
@pytest.mark.parametrize("explicit_attributions", [False, True])
def test_explicit_homepage_primary_is_shared_by_all_surfaces_after_source_permutation(tmp_path: Path, selected: str, explicit_attributions: bool) -> None:
    root, refs = _homepages(tmp_path)
    draft = _homepage_draft(root, refs[selected])
    original_bytes = draft.read_bytes()
    _seal(root, "1.download")
    assert _seal(root, "4.draft")["resultRefs"] == 1
    rows = projection._source_rows(root, root / HOME_REF)
    if explicit_attributions:
        for row in rows:
            if row["sourceRef"] in (refs["wiki"], refs["toutiao"]):
                row["sourceAttribution"] = encyclopedia_source_attribution(source_kind="wikipedia" if row["sourceRef"] == refs["wiki"] else "toutiao_baike", source_url=row["sourceUrl"], captured_at=row["fetchedAt"])
    # 故意把非选中的百科放在前面，两种声明都不应受列表顺序影响。
    rows.sort(key=lambda row: row["sourceRef"] == refs[selected])
    primary_views = []
    for ordered in (rows, list(reversed(rows))):
        intent = projection._author_intent(object_dir=root / HOME_REF, carrier="homepage", target=TARGET, source_rows=ordered, asset_index={})
        surface = projection._homepage_surface(execution_root=root, object_dir=root / HOME_REF, target_ref=HOME_REF, target=TARGET, compose=intent, source_rows=ordered)
        catalog = json.loads(surface[Path("evidence/source_catalog.json")])
        entity = json.loads(surface[Path("_entity.json")])
        manifest = json.loads(surface[Path("manifest.json")])
        selected_row = next(row for row in rows if row["sourceRef"] == refs[selected])
        assert catalog["primarySource"]["sourceUrl"] == selected_row["sourceUrl"]
        assert catalog["primaryEvidenceRef"] == f"evidence/sources/{Path(refs[selected]).parts[1]}/meta.json"
        assert entity["primarySource"]["sourceUrl"] == selected_row["sourceUrl"]
        assert entity["sourceAttribution"] == manifest["sourceAttribution"]
        assert entity["sourceAttribution"]["sourcePostUrl"] == selected_row["sourceUrl"]
        assert len(catalog["sources"]) == len(entity["sourceRefs"]) == 3
        primary_views.append((catalog["primarySource"], entity["primarySource"], entity["sourceAttribution"]))
    assert primary_views[0] == primary_views[1]
    assert draft.read_bytes() == original_bytes
    assert sorted(path.name for path in draft.parent.iterdir()) == ["page.md"]


@pytest.mark.parametrize("selected", ["web", "other", "missing", "empty"])
def test_author_seal_rejects_non_encyclopedia_or_foreign_homepage_primary(tmp_path: Path, selected: str) -> None:
    root, refs = _homepages(tmp_path)
    _homepage_draft(root, refs.get(selected, "" if selected == "empty" else "sources/missing/source.md"))
    with pytest.raises(seal.SealError, match="primarySourceRef"):
        seal._validate_author_artifact(root, root.name, HOME_REF)
    with pytest.raises(ObjectTransactionError, match="primarySourceRef"):
        _intent(root, HOME_REF, "homepage")


def test_multiple_encyclopedias_require_explicit_primary_without_rewriting_draft(tmp_path: Path) -> None:
    root, _refs = _homepages(tmp_path)
    draft = _homepage_draft(root, None)
    before = draft.read_bytes()
    with pytest.raises(seal.SealError, match="primarySourceRef"):
        seal._validate_author_artifact(root, root.name, HOME_REF)
    rows = projection._source_rows(root, root / HOME_REF)
    for ordered in (rows, list(reversed(rows))):
        with pytest.raises(ObjectTransactionError, match="primarySourceRef"):
            projection._author_intent(object_dir=root / HOME_REF, carrier="homepage", target=TARGET, source_rows=ordered, asset_index={})
    assert draft.read_bytes() == before


def test_single_encyclopedia_needs_no_ambiguous_primary_selection(tmp_path: Path) -> None:
    root, refs = _homepages(tmp_path)
    _homepage_draft(root, None)
    rows = [row for row in projection._source_rows(root, root / HOME_REF) if row["sourceRef"] == refs["wiki"]]
    intent = projection._author_intent(object_dir=root / HOME_REF, carrier="homepage", target=TARGET, source_rows=rows, asset_index={})
    surface = projection._homepage_surface(execution_root=root, object_dir=root / HOME_REF, target_ref=HOME_REF, target=TARGET, compose=intent, source_rows=rows)
    entity = json.loads(surface[Path("_entity.json")])
    assert entity["primarySource"]["sourceUrl"] == rows[0]["sourceUrl"]
    assert_valid({}, "content", "homepage_author")


def test_homepage_author_metadata_has_no_image_schema_dependency() -> None:
    schema_path = Path(__file__).resolve().parents[3] / "schema/content/homepage_author.schema.json"
    from jsonschema import Draft202012Validator

    validator = Draft202012Validator(json.loads(schema_path.read_bytes()))
    validator.validate({"title": "西湖", "tagRefs": ["Entity/地点/景区"], "creatorProfileId": "editor"})
    assert list(validator.iter_errors({"tagRefs": [42]}))
