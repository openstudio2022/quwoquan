"""spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-039
spec_ref: specs/feature-tree/runtime/runtime-data-engineering/image-commercial-scale-closure/spec.md#gwt-002
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

import pytest

from content.release.canonical.canonical_image_inventory import image_manifest_conflicts, readonly_image_inventory
from content.release.canonical.canonical_inventory import canonical_inventory_path, load_or_bootstrap_inventory
from content.release.canonical.content_pool_record import pool_payload_digest
from content.release.canonical.handler_cli import register_parser
from content.release.canonical.object_source_identity import source_identity_digest
from content.release.canonical.object_transaction_contract import ObjectTransactionError
from content.release.canonical.object_transaction_delta import apply_forward_delta
from content.release.canonical.pool_query import query_pool
from core.io import write_json


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _attribution() -> dict:
    return {"isOriginal": False, "originalCreatorName": "真实作者", "platform": "Wikimedia Commons",
        "sourcePostUrl": "https://example.test/work", "originalAssetUrl": "https://example.test/asset.jpg",
        "attributionText": "作者 / 来源", "rightsBasis": "CC BY-SA 4.0", "commercialAuthorizationStatus": "verified",
        "publicationAdmission": "production_release", "watermarkStatus": "absent", "watermarkKind": "none",
        "audioRightsStatus": "no_audio", "modelReleaseStatus": "not_required", "propertyReleaseStatus": "not_required",
        "collectedAt": "2026-09-09T00:00:00Z", "takedownPolicy": "remove_on_verified_rights_or_source_dispute",
        "derivedModifications": [], "termsUrl": "https://example.test/terms", "authorizationProofUrl": "https://example.test/proof"}


def _record(publish: Path, ref: str, manifest: dict) -> dict:
    root = publish / ref
    write_json(root / "manifest.json", manifest)
    write_json(root / "content_review.json", {"decision": "approved"})
    identity = {"executionId": "offline-execution", "sourceRevision": "sha256:" + "1" * 64,
        "sourceDigest": "sha256:" + "2" * 64, "entityCatalogDigest": "sha256:" + "3" * 64}
    digest = pool_payload_digest(root)
    record = {"schema": "quwoquan_data.pool_object_record", "objectType": "homepage" if ref.startswith("entities/") else "content",
        "objectId": manifest.get("entityId") or manifest["contentId"], "objectRef": ref.split("/", 1)[1],
        "recordSequence": 1, "contentVersion": manifest["version"], "status": "active", "processResult": "completed",
        "qualityResult": "passed", "eligibilityResult": "passed", "rightsResult": "passed",
        "rightsAuthorityRef": ref + "/content_review.json", "rightsAuthorityDigest": _digest(root / "content_review.json"),
        "usageScope": "production", "evidenceRef": "content_review.json", "evidenceDigest": _digest(root / "content_review.json"),
        "payloadDigest": digest, "canonicalObjectDigest": digest,
        "sourceIdentity": {**identity, "identityDigest": source_identity_digest(identity)}, "sourceAttribution": _attribution()}
    write_json(root / "_pool/versions/1.json", record)
    return record


def _homepage(publish: Path, name: str) -> str:
    ref = f"entities/地点/景区/{name}"
    source = "https://zh.wikipedia.org/wiki/" + name
    write_json(publish / ref / "_entity.json", {"label": name, "domain": "地点", "type": "景区",
        "executionId": "offline-execution", "entityRef": "/entity/地点/景区/" + name,
        "tagRefs": [], "geoTagRef": "Topic/地理/行政区/浙江省/杭州市/西湖区", "sourceUrls": [source],
        "primarySource": {"sourceKind": "wikipedia", "entityName": name, "extractor": "wikipedia_api",
            "canonicalUrl": source, "sourceUrl": source, "title": name, "fetchedAt": "2026-09-09T00:00:00Z",
            "snapshotHash": "sha256:" + "a" * 64, "policyRevision": "encyclopedia-primary", "sourceUseMode": "factual_reference_only"},
        "sourceAttribution": _attribution()})
    _record(publish, ref, {"entityId": "entity:stable:" + name, "entityRef": "/entity/地点/景区/" + name,
        "version": 1, "contentType": "homepage", "assets": []})
    return ref


def _post(publish: Path, index: int, entity: str) -> str:
    ref = f"posts/article/摄影/离线帖子{index}/1"
    _record(publish, ref, {"contentId": f"opaque-content-id-{index}", "version": 1, "contentIdentity": "work",
        "title": f"真实标题{index}", "contentType": "article", "authorId": "author", "creatorProfileId": "author", "generator": "agent",
        "variantPurpose": "original", "publishMediaMode": "text_only", "assets": [], "entityRefs": ["/entity/" + entity.removeprefix("entities/")]})
    return ref


def _snapshot(root: Path) -> dict[str, bytes]:
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_three_entities_eight_dependent_posts_keep_identity_and_deepest_errors(tmp_path: Path) -> None:
    publish = tmp_path / "publish"
    entities = [_homepage(publish, name) for name in ("实体甲", "实体乙", "实体丙")]
    write_json(publish / "creators/author/profile.json", {"authorId": "author", "version": 1, "status": "active",
        "admission": {"processResult": "completed", "qualityResult": "passed", "evidenceRef": "review.json", "evidenceDigest": "sha256:" + "f" * 64}})
    posts = [_post(publish, index, entities[index % 3]) for index in range(8)]
    # 三种实体事实：合法、缺记录、payload 漂移，真实 identity 不等于目录名。
    complete = query_pool(publish)
    assert complete["counts"] == {"homepage": 3, "article": 8, "image": 0, "video": 0}, complete["excluded"]
    (publish / entities[1] / "_pool/versions/1.json").unlink()
    (publish / entities[2] / "page.md").write_text("冻结后漂移", encoding="utf-8")
    before = _snapshot(tmp_path)
    result = query_pool(publish)
    rows = {row["objectRef"]: row for row in result["objects"]}
    assert len(rows) == 11
    assert result["counts"] == {"homepage": 1, "article": 3, "image": 0, "video": 0}, [(row["objectRef"], row["code"]) for row in result["excluded"]]
    assert rows[entities[1]]["occupied"] and rows[entities[1]]["state"] == "invalid"
    assert rows[entities[1]]["code"] == "DATA.POOL.EXPLICIT_ADMISSION_MISSING"
    assert rows[entities[2]]["code"] == "DATA.POOL.PAYLOAD_DIGEST_DRIFT"
    assert rows[posts[1]]["deepestCode"] == "DATA.POOL.EXPLICIT_ADMISSION_MISSING"
    assert rows[posts[2]]["deepestCode"] == "DATA.POOL.PAYLOAD_DIGEST_DRIFT"
    assert rows[posts[2]]["dependencyRefs"] == [entities[2]]
    assert rows[posts[0]]["objectId"] == "opaque-content-id-0"
    assert rows[posts[0]]["title"] == "真实标题0"
    assert rows[posts[0]]["recordIdentity"]["objectId"] == "opaque-content-id-0"
    assert _snapshot(tmp_path) == before
    assert not canonical_inventory_path(publish).exists()


def test_missing_manifest_and_invalid_record_still_reserve_real_id(tmp_path: Path) -> None:
    ref = _post(tmp_path, 1, "entities/地点/景区/未发布")
    manifest = tmp_path / ref / "manifest.json"
    manifest.unlink()
    result = query_pool(tmp_path, target_refs=[ref, "posts/image/摄影/不存在/1"])
    rows = {row["objectRef"]: row for row in result["objects"]}
    assert rows[ref]["occupied"] and rows[ref]["state"] == "invalid"
    assert rows[ref]["recordIdentity"]["objectId"] == "opaque-content-id-1"
    assert rows["posts/image/摄影/不存在/1"]["state"] == "absent"


def _image(index: int = 1) -> dict:
    return {"contentType": "image", "contentId": f"work-{index}", "version": 1,
        "assets": [{"assetId": f"asset-{index}", "kind": "image", "sha256": "sha256:" + hashlib.sha256(str(index).encode()).hexdigest(),
            "perceptualHash": hashlib.sha256(f"phash-{index}".encode()).hexdigest()[:16],
            "sourceUrl": f"https://example.test/works/{index}", "originalAssetUrl": f"https://example.test/assets/{index}.jpg"}]}


@pytest.mark.parametrize("carrier", ["article", "homepage"])
@pytest.mark.parametrize("hot", [False, True])
def test_readonly_stable_asset_reference_reuse_is_independent_positive(tmp_path: Path, carrier: str, hot: bool) -> None:
    publish = tmp_path / "publish"
    existing = _image()
    write_json(publish / "posts/image/摄影/已有作品/1/manifest.json", existing)
    if hot:
        load_or_bootstrap_inventory(publish)
    candidate = copy.deepcopy(existing)
    candidate.update(contentType=carrier, contentId="different-logical-reference")
    candidate["assets"][0]["role"] = "cover"
    if carrier == "article":
        candidate["assets"].append({**candidate["assets"][0], "role": "inline"})
    ref = "entities/地点/景区/新主页" if carrier == "homepage" else "posts/article/摄影/新文章/1"
    before = _snapshot(tmp_path)
    result = query_pool(publish, target_refs=[ref], candidates=[{"objectRef": ref, "manifest": candidate}])
    assert result["preflight"][0]["imageConflicts"] == []
    assert result["preflight"][0]["identity"]["state"] == "absent"
    assert _snapshot(tmp_path) == before
    run = tmp_path / "run"
    write_json(run / "manifest.json", candidate)
    entry = {"operation": "create", "destination": ref + "/manifest.json", "blobRef": "manifest.json", "sha256": _digest(run / "manifest.json")}
    assert apply_forward_delta(publish_root=publish, run_root=run, manifest={"entries": [entry]}) == [entry]
    assert json.loads((publish / ref / "manifest.json").read_text()) == candidate


@pytest.mark.parametrize("case, expected", [
    ("same_work_same_id", "IMAGE_SHA256_DUPLICATE"),
    ("new_id_same_sha", "IMAGE_SHA256_DUPLICATE"),
    ("same_id_new_bytes", "IMAGE_BINDING_DRIFT"),
    ("same_id_new_source", "IMAGE_BINDING_DRIFT"),
    ("near_phash", "IMAGE_PERCEPTUAL_DUPLICATE"),
    ("same_work_new_asset", "IMAGE_SOURCE_WORK_DUPLICATE"),
    ("same_post_duplicate", "IMAGE_SHA256_DUPLICATE"),
])
def test_readonly_and_publish_recheck_reject_image_identity_conflicts(tmp_path: Path, case: str, expected: str) -> None:
    publish = tmp_path / "publish"
    existing = _image()
    write_json(publish / "posts/image/摄影/已有作品/1/manifest.json", existing)
    candidate = copy.deepcopy(existing)
    candidate["contentId"] = "different-work"
    asset = candidate["assets"][0]
    if case == "new_id_same_sha":
        asset["assetId"] = "other-id"
    elif case == "same_id_new_bytes":
        asset.update(sha256="sha256:" + "f" * 64, perceptualHash="f" * 16)
    elif case == "same_id_new_source":
        candidate["contentType"] = "article"
        asset["sourceUrl"] = "https://other.test/work"
    elif case == "near_phash":
        asset.update(assetId="other-id", sha256="sha256:" + "f" * 64, perceptualHash=f"{int(asset['perceptualHash'], 16) ^ 31:016x}")
    elif case == "same_work_new_asset":
        candidate = _image(2)
        candidate["assets"][0]["sourceUrl"] = existing["assets"][0]["sourceUrl"]
    elif case == "same_post_duplicate":
        candidate = _image(2)
        candidate["assets"].append(dict(candidate["assets"][0]))
    ref = "posts/image/摄影/新作品/1"
    result = query_pool(publish, target_refs=[ref], candidates=[{"objectRef": ref, "manifest": candidate}])
    assert any(expected in issue["code"] for issue in result["preflight"][0]["imageConflicts"])
    run = tmp_path / "run"
    write_json(run / "manifest.json", candidate)
    entry = {"operation": "create", "destination": ref + "/manifest.json", "blobRef": "manifest.json", "sha256": _digest(run / "manifest.json")}
    before = _snapshot(publish)
    with pytest.raises(ObjectTransactionError, match=expected):
        apply_forward_delta(publish_root=publish, run_root=run, manifest={"entries": [entry]})
    assert _snapshot(publish) == before


def test_explicit_logical_version_update_not_path_only_exemption(tmp_path: Path) -> None:
    existing = _image()
    write_json(tmp_path / "posts/image/摄影/同作品/1/manifest.json", existing)
    with readonly_image_inventory(tmp_path) as connection:
        candidate = {**existing, "version": 2}
        assert not image_manifest_conflicts(connection, manifest=candidate, excluded_manifest_path="posts/image/摄影/同作品/2/manifest.json")
        candidate["contentId"] = "another-work"
        assert image_manifest_conflicts(connection, manifest=candidate, excluded_manifest_path="posts/image/摄影/同作品/2/manifest.json")


def test_one_native_work_keeps_distinct_assets_in_order(tmp_path: Path) -> None:
    candidate = _image()
    second = _image(2)["assets"][0]
    second["sourceUrl"] = candidate["assets"][0]["sourceUrl"]
    candidate["assets"].append(second)
    ref = "posts/image/摄影/有序多图作品/1"
    before = copy.deepcopy(candidate)
    result = query_pool(tmp_path, candidates=[{"objectRef": ref, "manifest": candidate}])
    assert result["preflight"][0]["imageConflicts"] == []
    assert candidate == before


def test_cli_preflight_is_readonly_and_does_not_auto_approve(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    request = tmp_path / "candidates.json"
    ref = "posts/image/摄影/新作品/1"
    write_json(request, {"candidates": [{"objectRef": ref, "manifest": _image()}]})
    parser = argparse.ArgumentParser()
    register_parser(parser.add_subparsers())
    args = parser.parse_args(["release", "pool-query", "--publish-root", str(tmp_path / "publish"), "--target-ref", ref, "--candidate-file", str(request)])
    args.handler(args)
    result = json.loads(capsys.readouterr().out)
    assert result["preflight"][0]["imageConflicts"] == []
    assert "approved" not in result and "decision" not in result
    assert not (tmp_path / "publish").exists()


def test_publish_rechecks_dependencies_after_successful_readonly_preflight(tmp_path: Path) -> None:
    publish = tmp_path / "publish"
    entity = _homepage(publish, "被引用实体")
    candidate = {**_image(), "entityRefs": ["/entity/" + entity.removeprefix("entities/")]}
    ref = "posts/image/摄影/待发布/1"
    result = query_pool(publish, candidates=[{"objectRef": ref, "manifest": candidate}])
    assert result["preflight"][0]["dependencyIssues"] == []
    (publish / entity / "_pool/versions/1.json").unlink()
    run = tmp_path / "run"
    write_json(run / "manifest.json", candidate)
    entry = {"operation": "create", "destination": ref + "/manifest.json", "blobRef": "manifest.json", "sha256": _digest(run / "manifest.json")}
    before = _snapshot(publish)
    with pytest.raises(ObjectTransactionError, match="DATA.POOL.REFERENCE_MISSING:.*DATA.POOL.EXPLICIT_ADMISSION_MISSING"):
        apply_forward_delta(publish_root=publish, run_root=run, manifest={"entries": [entry]})
    assert _snapshot(publish) == before


def test_candidates_detect_each_other_without_rescanning_pool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from content.release.canonical import pool_query as subject

    publish = tmp_path / "publish"
    load_or_bootstrap_inventory(publish)
    def reject_scan(*args, **kwargs):
        raise AssertionError("点名候选的热预检不得全池扫描")
    before = _snapshot(tmp_path)
    monkeypatch.setattr(subject, "_occupied_refs", reject_scan)
    candidates = [{"objectRef": f"posts/image/摄影/候选{index}/1", "manifest": _image()} for index in range(2)]
    original_rglob = Path.rglob
    monkeypatch.setattr(Path, "rglob", reject_scan)
    result = query_pool(publish, candidates=candidates)
    for index, row in enumerate(result["preflight"]):
        assert row["imageConflicts"][0]["code"] == "DATA.POOL.IMAGE_SHA256_DUPLICATE"
        assert row["imageConflicts"][0]["dependencyRefs"] == [candidates[1 - index]["objectRef"]]
    monkeypatch.setattr(Path, "rglob", original_rglob)
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize("change", ["bytes", "source", "logical_id"])
def test_same_path_does_not_hide_binding_or_logical_identity_drift(tmp_path: Path, change: str) -> None:
    ref = "posts/image/摄影/相同路径/1"
    existing = _image()
    write_json(tmp_path / ref / "manifest.json", existing)
    load_or_bootstrap_inventory(tmp_path)
    candidate = copy.deepcopy(existing)
    if change == "bytes":
        candidate["assets"][0]["sha256"] = "sha256:" + "f" * 64
    elif change == "source":
        candidate["assets"][0]["originalAssetUrl"] = "https://other.test/changed.jpg"
    else:
        candidate["contentId"] = "different-logical-id"
    result = query_pool(tmp_path, candidates=[{"objectRef": ref, "manifest": candidate}])
    assert result["preflight"][0]["imageConflicts"]


def test_invalid_latest_record_keeps_real_identity_without_admission(tmp_path: Path) -> None:
    ref = _homepage(tmp_path, "记录冲突")
    record_path = tmp_path / ref / "_pool/versions/1.json"
    record = json.loads(record_path.read_text())
    record.update(objectId="record-reserved-id", recordSequence=2, processResult="invalid")
    write_json(record_path.with_name("2.json"), record)
    row = query_pool(tmp_path, target_refs=[ref])["objects"][0]
    assert row["state"] == "invalid" and not row["eligible"]
    assert row["recordIdentity"]["objectId"] == "record-reserved-id"
    assert row["objectIds"] == ["entity:stable:记录冲突", "record-reserved-id"]


def test_cli_refuses_json_output_inside_publish(tmp_path: Path) -> None:
    parser = argparse.ArgumentParser()
    register_parser(parser.add_subparsers())
    publish = tmp_path / "publish"
    args = parser.parse_args(["release", "pool-query", "--publish-root", str(publish), "--json", str(publish / "result.json")])
    with pytest.raises(ValueError, match="must not mutate canonical publish"):
        args.handler(args)
    assert not publish.exists()


def test_cutover_snapshot_cli_only_reads_exact_occupied_objects(tmp_path, capsys):
    from content.release.canonical.pool_cutover import snapshot_pool
    parser = argparse.ArgumentParser()
    register_parser(parser.add_subparsers())
    publish = tmp_path / "publish"
    _homepage(publish, "盘点对象")
    before = _snapshot(tmp_path)
    args = parser.parse_args(["release", "pool-cutover", "snapshot", "--publish-root", str(publish)])
    args.handler(args)
    result = json.loads(capsys.readouterr().out)
    assert result == snapshot_pool(publish)
    assert result["objects"][0]["objectRef"] == "entities/地点/景区/盘点对象"
    assert _snapshot(tmp_path) == before


def test_snapshot_counts_only_occupied_while_query_includes_missing_dependencies(tmp_path):
    from content.release.canonical.pool_cutover import snapshot_pool

    publish = tmp_path / "publish"
    homepage = _homepage(publish, "已占位")
    missing = "entities/地点/景区/都江堰"
    post = _post(publish, 1, missing)
    creator = "creators/author"
    write_json(publish / creator / "profile.json", {"authorId": "author", "version": 1})
    before = _snapshot(tmp_path)
    snapshot = snapshot_pool(publish)
    query = query_pool(publish)
    snapshot_refs = {row["objectRef"] for row in snapshot["objects"]}
    occupied_refs = {row["objectRef"] for row in query["occupied"]}
    absent_refs = {row["objectRef"] for row in query["objects"] if row["state"] == "absent"}
    assert snapshot_refs == {homepage, post, creator}
    assert occupied_refs == snapshot_refs - {creator}
    assert absent_refs == {missing}
    assert len(query["objects"]) == len(occupied_refs) + len(absent_refs)
    assert next(row for row in query["objects"] if row["objectRef"] == post)["dependencyRefs"] == [missing]
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize("code", ["DATA.POOL.PAYLOAD_DIGEST_DRIFT", "DATA.CUTOVER.COMMIT_OUTCOME_REQUIRES_INSPECTION"])
def test_cutover_cli_preserves_lower_boundary_error_codes(tmp_path, capsys, monkeypatch, code):
    from content.release.canonical import handler_cli
    def blocked(args):
        raise ObjectTransactionError(f"{code}: exact evidence requires inspection")
    monkeypatch.setattr(handler_cli, "_cutover_result", blocked)
    with pytest.raises(SystemExit) as caught:
        handler_cli._load_pool_cutover(argparse.Namespace())
    assert caught.value.code == 1
    assert json.loads(capsys.readouterr().out)["code"] == code
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("action", ["dry-run", "activate", "cleanup"])
def test_cutover_cli_does_not_invent_authorization(action):
    parser = argparse.ArgumentParser()
    register_parser(parser.add_subparsers())
    with pytest.raises(SystemExit) as caught:
        parser.parse_args(["release", "pool-cutover", action, "--plan", "/plan.json", "--plan-digest", "sha256:" + "1" * 64])
    assert caught.value.code == 2


def test_cutover_cli_preserves_typed_blocker_without_writing(tmp_path, capsys):
    parser = argparse.ArgumentParser()
    register_parser(parser.add_subparsers())
    args = parser.parse_args(["release", "pool-cutover", "dry-run", "--plan", str(tmp_path / "missing.json"),
        "--plan-digest", "sha256:" + "1" * 64, "--authorization", str(tmp_path / "authorization.json"),
        "--authorization-digest", "sha256:" + "2" * 64, "--evidence-output", str(tmp_path / "evidence.json")])
    with pytest.raises(SystemExit) as caught:
        args.handler(args)
    assert caught.value.code == 1
    result = json.loads(capsys.readouterr().out)
    assert result["code"] == "DATA.CUTOVER.PATH_INVALID" and result["status"] == "blocked"
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("payload", [b"not json", b"[]"])
def test_cutover_cli_rejects_unreadable_snapshot_with_typed_diagnostic(tmp_path, capsys, payload):
    publish = tmp_path / "publish"
    root = publish / "entities/地点/景区/损坏对象"
    root.mkdir(parents=True)
    (root / "manifest.json").write_bytes(payload)
    before = _snapshot(tmp_path)
    parser = argparse.ArgumentParser()
    register_parser(parser.add_subparsers())
    args = parser.parse_args(["release", "pool-cutover", "snapshot", "--publish-root", str(publish)])
    with pytest.raises(SystemExit) as caught:
        args.handler(args)
    assert caught.value.code == 1
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "blocked" and result["code"] == "DATA.CUTOVER.INPUT_INVALID"
    assert "损坏对象/manifest.json" in result["message"]
    assert _snapshot(tmp_path) == before
