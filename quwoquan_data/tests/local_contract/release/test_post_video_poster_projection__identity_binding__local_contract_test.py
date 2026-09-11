"""视频包只重命名已验证的资产路径，不重写原始封面身份或 producer 原件。"""
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-022
from __future__ import annotations

import copy
import hashlib
import subprocess
from pathlib import Path

import pytest
import yaml

from content.execution import seal, task_init
from content.release.canonical import creator_projection, post_asset_identity, post_transaction
from content.release.canonical.final_surface_projection import project_publish_final_surface
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError, _digest_file, _json_bytes, _read_json, canonical_transaction_id,
)
from content.source import acquire
from core import content_library, paths
from support.media_fixture import tiny_png_bytes


REF = "posts/video/风光/西湖封面绑定/1"
CREATOR = "qwq_creator_geo_editor_001"


def _write(path: Path, document: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_json_bytes(document))
    return path


def _creator_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """沿用准入 profile 的隔离副本，头像使用与本地真实字节相符的摘要。"""
    original_pool = paths.CONTROL_PLANE_CREATOR_POOL_ROOT
    profile_ref = "profiles/system_builtin/geo_editor.creator.yaml"
    profile = yaml.safe_load((original_pool / profile_ref).read_bytes())
    body = tiny_png_bytes()
    digest = hashlib.sha256(body).hexdigest()
    asset = profile["avatarAsset"]
    rights = _read_json(original_pool / asset["evidenceRef"])
    asset.update(sha256=f"sha256:{digest}", bytes=len(body), mimeType="image/png",
                 objectKey=f"media/objects/sha256/{digest[:2]}/{digest[2:4]}/{digest}.png")
    rights["manifestAsset"]["sha256"] = asset["sha256"]
    rights["commercialRights"]["asset"].update(sha256=asset["sha256"], bytes=len(body), mimeType="image/png")
    pool = tmp_path / "creator-pool"
    _write(pool / asset["evidenceRef"], rights)
    profile_path = pool / profile_ref
    profile_path.parent.mkdir(parents=True)
    profile_path.write_text(yaml.safe_dump(profile, allow_unicode=True), encoding="utf-8")
    content_library.admit_library_bytes(body, kind="media")
    monkeypatch.setattr(creator_projection, "CONTROL_PLANE_CREATOR_POOL_ROOT", pool)


@pytest.fixture
def video_execution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    library = tmp_path / "library"
    monkeypatch.setenv("QWQ_LIBRARY_ROOT", str(library))
    for module in (paths, content_library):
        monkeypatch.setattr(module, "LIBRARY_ROOT", library)
        monkeypatch.setattr(module, "LIBRARY_CAS_ROOT_BY_KIND", {
            "media": library / "_media_cas", "source": library / "_source_cas",
        })
    for name, value in {
        "LIBRARY_MEDIA_CAS_ROOT": library / "_media_cas",
        "LIBRARY_SOURCE_CAS_ROOT": library / "_source_cas",
        "OUTPUT_ROOT": tmp_path / "output",
        "DATA_EXECUTIONS_ROOT": tmp_path / "output/data/tasks",
        "DATA_LOCAL_ROOT": tmp_path / "output/data/local",
    }.items():
        monkeypatch.setattr(paths, name, value)
    monkeypatch.setattr(post_transaction, "OUTPUT_ROOT", tmp_path / "output")
    publish = tmp_path / "publish"
    (publish / ".git").mkdir(parents=True)
    _write(publish / "repository.json", {
        "schema": "quwoquan_data.publish_repository.v2", "repositoryId": "poster-projection-test",
        "layoutVersion": 2,
    })
    monkeypatch.setattr(post_transaction, "PUBLISH_ROOT", publish)
    execution_id = "20260909--travel-video-poster-binding--local--pilot-001"
    target = {"name": "西湖", "entityType": "地点/景区", "region": "中国/浙江省/杭州市",
              "entityRef": "/entity/地点/景区/西湖", "entityId": "entity:poster-binding-west-lake",
              "publishAngle": "风光", "publishTitle": "西湖封面绑定", "publishSeq": 1}
    task_init.initialize_execution(
        submitted_demand={"schema": "quwoquan_data.carrier_demand", "executionId": execution_id,
                          "carrier": "video", "familyRef": "content/travel/video/video"},
        submitted_bindings={"schema": "quwoquan_data.immutable_candidate_bindings", "executionId": execution_id,
                            "carrier": "video", "targets": [target]},
    )
    execution = paths.execution_root(execution_id)
    media = tmp_path / "local.mp4"
    subprocess.run([
        "ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=24:duration=1",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(media),
    ], check=True, capture_output=True)
    request = _write(tmp_path / "ingest.json", {
        "schema": "quwoquan_data.ingest_manifest", "executionId": execution_id,
        "targets": [{"targetRef": REF, "sources": [{
            "kind": "video", "sourceUrl": "https://commons.wikimedia.org/wiki/File:Local",
            "directUrl": "https://upload.wikimedia.org/local/local.mp4", "filePath": str(media),
            "license": "CC BY-SA 4.0", "licenseUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
            "creator": "测试摄影师", "description": "本地合成视频", "relevance": "封面绑定测试",
            "watermarkStatus": "absent", "watermarkKind": "none", "hasAudio": False,
        }]}],
    })
    result = acquire.acquire(execution_id=execution_id, request_path=request)
    assert result["failed"] == 0, result
    _creator_fixture(tmp_path, monkeypatch)
    _write(execution / REF / "4.draft/video_script.json", {
        "title": "西湖封面绑定", "caption": "本地视频包映射回归", "creatorProfileId": CREATOR,
        "tagRefs": ["Entity/地点/景区"], "scriptLines": ["本地合成视频脚本"],
    })
    for stage in ("1.download", "4.draft", "5.review"):
        role = "reviewer" if stage == "5.review" else "author"
        payload = {"actor": {"host": "cursor", "modelFamily": "gpt", "sessionId": f"poster-{role}",
                             "invocation": {"provider": "openai", "model": "test-model", "runId": f"poster-{role}-run"}},
                   "verdict": "pass"}
        if stage == "5.review":
            payload["reviews"] = {REF: {"decision": "approved", "blockingIssues": [], "advisories": []}}
        seal.seal_stage(execution_id=execution_id, stage=stage,
                        input_path=_write(tmp_path / f"{stage}.json", payload))
    project_publish_final_surface(execution_root=execution, object_dir=execution / REF,
                                  target_ref=REF, target=target, carrier="video")
    return execution, tmp_path / "package"


def _snapshot(root: Path) -> dict[str, bytes]:
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def _build(execution: Path, package: Path):
    return post_transaction.build_post_object_transaction_package(
        execution_root=execution, object_ref=REF.removeprefix("posts/"), package_root=package,
        transaction_id=canonical_transaction_id(execution_id=execution.name, object_kind="posts",
                                                 object_ref=REF.removeprefix("posts/")),
    )


def test_video_package_rebinds_exact_poster_path_without_source_mutation(video_execution):
    execution, package = video_execution
    before = _snapshot(execution)
    source = _read_json(execution / REF / "manifest.json")
    transaction = _build(execution, package)
    canonical = _read_json(package / "object/manifest.json")
    by_id = {row["assetId"]: row for row in canonical["assets"]}
    video = next(row for row in canonical["assets"] if row["kind"] == "video")
    poster = by_id[video["posterAssetId"]]
    original_video = next(row for row in source["assets"] if row["kind"] == "video")
    assert original_video["posterFileName"].startswith("assets/")
    assert video["posterFileName"] == poster["path"] == poster["fileName"]
    assert video["posterFileName"].startswith("media/")
    assert (video["posterAssetId"], video["posterSha256"]) == (
        original_video["posterAssetId"], original_video["posterSha256"],
    )
    for original, projected in zip(source["assets"], canonical["assets"], strict=True):
        assert (projected["assetId"], projected["sha256"]) == (original["assetId"], original["sha256"])
        assert _digest_file(package / "object" / projected["path"]) == original["sha256"]
        assert projected["sourceAssetRefs"] == original.get("sourceAssetRefs", [original.get("sourceAssetRef")])
    assert {row["sourceRef"] for row in transaction["closure"]["casRefs"]} == {
        "object/" + row["path"] for row in canonical["assets"]
    }
    assert (package / "object/content_review.json").read_bytes() == before[f"{REF}/5.review/content_review.json"]
    assert _snapshot(execution) == before


@pytest.mark.parametrize("field,value,error", [
    ("posterFileName", "assets/not-the-selected-poster.jpg", "posterFileName drift"),
    ("posterFileName", "media/02.jpg", "posterFileName drift"),
    ("posterSha256", "sha256:" + "0" * 64, "posterSha256 drift"),
    ("posterAssetId", "missing-poster", "exact poster asset binding"),
    ("sha256", "sha256:" + "0" * 64, "asset sha256 drift"),
])
def test_original_video_claim_drift_is_not_erased_by_mapping(video_execution, field, value, error):
    execution, package = video_execution
    manifest_path = execution / REF / "manifest.json"
    manifest = _read_json(manifest_path)
    video = next(row for row in manifest["assets"] if row["kind"] == "video")
    video[field] = value
    _write(manifest_path, manifest)
    before = _snapshot(execution)
    with pytest.raises(ObjectTransactionError, match=error):
        _build(execution, package)
    assert not package.exists()
    assert _snapshot(execution) == before


def test_source_poster_digest_drift_is_not_recomputed_away(video_execution):
    execution, package = video_execution
    manifest_path = execution / REF / "manifest.json"
    manifest = _read_json(manifest_path)
    poster = next(row for row in manifest["assets"] if row["kind"] == "image")
    poster["sha256"] = "sha256:" + "0" * 64
    _write(manifest_path, manifest)
    before = _snapshot(execution)
    with pytest.raises(ObjectTransactionError, match="asset sha256 drift"):
        _build(execution, package)
    assert not package.exists()
    assert _snapshot(execution) == before


def test_projection_preserves_source_rows_and_pairs_by_id_not_position():
    assets = [
        {"assetId": "poster", "kind": "image", "fileName": "assets/poster.jpg", "sha256": "sha256:" + "1" * 64},
        {"assetId": "video", "kind": "video", "fileName": "assets/video.mp4", "sha256": "sha256:" + "2" * 64,
         "posterAssetId": "poster", "posterFileName": "assets/poster.jpg", "posterSha256": "sha256:" + "1" * 64},
    ]
    before = copy.deepcopy(assets)
    projected = post_asset_identity.project_canonical_post_asset_paths(
        assets, destination_paths={"video": "media/02.mp4", "poster": "media/01.jpg"},
    )
    assert assets == before
    assert projected[1]["posterFileName"] == projected[0]["fileName"] == "media/01.jpg"
    assert projected[1]["posterAssetId"] == "poster"
    assert projected[1]["posterSha256"] == before[1]["posterSha256"]
