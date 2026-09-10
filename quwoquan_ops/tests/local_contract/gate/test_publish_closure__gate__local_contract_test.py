"""local_contract: 独立发布仓的结构与随体媒体门禁。

verify_publish_closure 组合结构纯度与随体媒体/来源检查，不再拥有全包不变量或
creator 头像质量。后两者的负例直接调用现役 owner，避免把媒体 gate 的 PASS
当作发布准入。fixture 使用新版单 manifest、sources、media、records；所有
字节只落在测试临时目录，不读取真实 publish 树，也不依赖开发机 content library。
"""
# spec_ref: specs/feature-tree/platform-ops-governance/spec.md#req-001
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS_ROOT = ROOT / "quwoquan_data" / "scripts"
MODULE_PATH = SCRIPTS_ROOT / "verify" / "verify_publish_closure.py"

if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from content.release.canonical.content_pool_record import (  # noqa: E402
    append_pool_record,
    build_canonical_pool_record,
    latest_pool_record,
)
from content.release.canonical.creator_avatar_quality import (  # noqa: E402
    creator_avatar_quality_issues,
)
from content.release.canonical.object_source_identity import source_identity_digest  # noqa: E402
from core import content_library  # noqa: E402
from core.schema import assert_valid  # noqa: E402
from core.source_digest import content_source_revision  # noqa: E402
from verify.verify_publish_purity import publish_purity_issues  # noqa: E402

SOURCE_REF = "sources/fixture/source.json"
SOURCE_URL = "https://example.org/publish-closure-fixture"
POST_REF = "article/travel/sample/1"
TIMESTAMP = "2026-09-09T00:00:00Z"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "verify_publish_closure_companion", MODULE_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _digest(body: bytes) -> str:
    return "sha256:" + hashlib.sha256(body).hexdigest()


class PublishClosureGateTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        # macOS 的 /var 是 symlink；fixture 取物理根，不放宽仓身份检查。
        self.workspace = Path(temporary.name).resolve()
        self.publish = self.workspace / "publish"
        (self.publish / ".git").mkdir(parents=True)
        _write_json(self.publish / "repository.json", {
            "schema": "quwoquan_data.publish_repository.v2",
            "repositoryId": "publish-closure-test",
            "layoutVersion": 2,
        })
        self._isolate_content_library()
        self.gate = _load_module()
        self.gate.PUBLISH_ROOT = self.publish
        self.post_manifest = self.publish / "posts/article/travel/p0001/sample/1/manifest.json"

    def _isolate_content_library(self) -> None:
        library_root = self.workspace / "content-library"
        for name in ("QWQ_LIBRARY_ROOT", "QWQ_OUTPUT_ROOT"):
            original = os.environ.get(name)
            if original is None:
                self.addCleanup(os.environ.pop, name, None)
            else:
                self.addCleanup(os.environ.__setitem__, name, original)
            os.environ[name] = str(library_root)
        cas_roots = content_library.LIBRARY_CAS_ROOT_BY_KIND
        kind = content_library.MEDIA_KIND
        original = cas_roots[kind]
        self.addCleanup(cas_roots.__setitem__, kind, original)
        cas_roots[kind] = library_root / "_media_cas"

    def _seed_source(self, root: Path, assets: list[dict]) -> None:
        evidence = b"Local contract source evidence; not a production rights receipt.\n"
        source = root / SOURCE_REF
        source.parent.mkdir(parents=True, exist_ok=True)
        (source.parent / "evidence.html").write_bytes(evidence)
        document = {
            "schema": "quwoquan_data.publish_source",
            "sourceId": "fixture", "sourceUrl": SOURCE_URL,
            "sourceUseMode": "licensed_adaptation", "fetchedAt": TIMESTAMP,
            "metadata": {"sourceUrl": SOURCE_URL}, "assets": assets,
            "evidence": [{"path": "evidence.html", "sha256": _digest(evidence),
                          "bytes": len(evidence), "kind": "source_snapshot"}],
        }
        assert_valid(document, "publish", "source")
        _write_json(source, document)

    def _seed_media(self, root: Path, *, kind: str, asset_id: str) -> dict:
        body = f"local-contract-{asset_id}-body".encode("utf-8")
        path = root / "media" / f"{asset_id}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        return {"assetId": asset_id, "kind": kind, "sha256": _digest(body),
                "path": path.relative_to(root).as_posix(), "bytes": len(body),
                "mimeType": "image/png", "sourceRefs": [SOURCE_REF]}

    def _seed_creator(self, creator_ref: str) -> None:
        root = self.publish / "creators" / creator_ref
        asset = self._seed_media(root, kind="avatar", asset_id=f"{creator_ref}-avatar")
        self._seed_source(root, [asset])
        _write_json(root / "_creator.json", {
            "schema": "quwoquan_data.creator_object", "creatorId": creator_ref,
            "profileRef": "profile.json", "assetsRef": "assets.refs.json",
            "worksRefsRef": "works.refs.ndjson", "tagRefs": [], "entityRefs": [],
        })
        evidence_path = root / "admission.json"
        _write_json(evidence_path, {"authorIds": [creator_ref], "result": "passed"})
        _write_json(root / "profile.json", {
            "schema": "quwoquan_data.creator_profile", "creatorId": creator_ref,
            "authorId": creator_ref, "version": 1, "status": "active",
            "avatarAsset": {key: asset[key] for key in ("assetId", "kind", "sha256")},
            "assets": [asset], "sourceRefs": [SOURCE_REF],
            "admission": {"processResult": "completed", "qualityResult": "passed",
                          "evidenceRef": "admission.json",
                          "evidenceDigest": _digest(evidence_path.read_bytes())},
        })
        _write_json(root / "assets.refs.json", {"assets": [asset]})
        (root / "works.refs.ndjson").write_text("", encoding="utf-8")

    def _seed_closed_publish(self, *, admit_media: bool = True) -> None:
        self._seed_creator("creator-a")
        root = self.post_manifest.parent
        asset = self._seed_media(root, kind="image", asset_id="cover")
        body = (root / asset["path"]).read_bytes()
        digest_hex = asset["sha256"].removeprefix("sha256:")
        asset.update(
            fileName=asset["path"], role="cover",
            objectKey=f"media/objects/sha256/{digest_hex[:2]}/{digest_hex[2:4]}/{digest_hex}.png",
            sourceAssetRefs=["sources/fixture/assets/cover.png"],
            acquisitionReceiptRefs=["sources/fixture/evidence.html"],
        )
        # 全树 purity 的 CAS 引用检查仍由其 owner 拥有；媒体 gate 不消费 CAS。
        if admit_media:
            content_library.admit_library_bytes(body, kind=content_library.MEDIA_KIND)
        self._seed_source(root, [asset])
        (root / "article.md").write_text("# 测试作品\n\n本地合约正文。\n", encoding="utf-8")
        review_path = root / "content_review.json"
        _write_json(review_path, {
            "schema": "quwoquan_data.content_review", "stage": "5.review",
            "executionId": "20260909--publish-closure--local--pilot-001",
            "objectRef": f"posts/{POST_REF}", "decision": "approved",
            "draft": {"ref": "4.draft/article.md", "digest": _digest(b"fixture draft")},
            "dimensions": [{"name": "content", "decision": "approved", "issues": []}],
            "blockingIssues": [], "assetRights": [],
        })
        evidence_digest = _digest(review_path.read_bytes())
        identity = {"executionId": "20260909--publish-closure--local--pilot-001",
                    "sourceDigest": _digest(b"source"), "entityCatalogDigest": _digest(b"catalog")}
        identity["sourceRevision"] = content_source_revision(
            source_digest=identity["sourceDigest"], entity_catalog_digest=identity["entityCatalogDigest"],
        )
        identity["identityDigest"] = source_identity_digest(identity)
        document = {
            "schema": "quwoquan_data.post_object", "objectRef": POST_REF,
            "contentId": "publish-closure-post", "version": 1, "sourceType": "data",
            "sourceIdentity": identity, "payloadDigest": _digest(body),
            "variantPurpose": "original", "status": "active",
            "vertical": "travel", "topicId": "sample", "contentIdentity": "work",
            "contentType": "article", "creatorProfileId": "creator-a",
            "entityRefs": [], "tagRefs": [], "sourceUrls": [SOURCE_URL],
            "sourceRefs": [SOURCE_REF], "assets": [asset], "generator": "agent",
            "createdAt": TIMESTAMP, "updatedAt": TIMESTAMP,
            "executionId": identity["executionId"], "finalContentRef": "article.md",
            "publishMediaMode": "embedded_media",
            "sourceAttribution": {
                "isOriginal": False, "originalCreatorName": "测试作者",
                "platform": "fixture", "sourcePostUrl": SOURCE_URL,
                "originalAssetUrl": SOURCE_URL, "attributionText": "本地合约测试来源",
                "rightsBasis": "fixture", "commercialAuthorizationStatus": "unverified",
                "publicationAdmission": "research_release", "watermarkStatus": "absent",
                "audioRightsStatus": "no_audio", "modelReleaseStatus": "not_required",
                "propertyReleaseStatus": "not_required", "collectedAt": TIMESTAMP,
                "takedownPolicy": "quwoquan_standard_notice_and_takedown", "derivedModifications": [],
            },
            "admission": {
                "processResult": "completed", "qualityResult": "passed", "usageScope": "research",
                "rightsResult": "passed", "rightsAuthorityRef": f"posts/{POST_REF}/content_review.json",
                "rightsAuthorityDigest": evidence_digest, "evidenceRef": "content_review.json",
                "evidenceDigest": evidence_digest,
            },
        }
        assert_valid(document, "content", "post_manifest")
        _write_json(self.post_manifest, document)
        append_pool_record(object_root=root, record=build_canonical_pool_record(
            object_root=root, object_type="content", object_ref=POST_REF,
        ))
        self.assertIsNotNone(latest_pool_record(root, "content"))
        self.assertEqual(creator_avatar_quality_issues(self.publish), [])
        self.assertEqual(self.gate.carried_media_closure_issues(self.publish), [])
        if admit_media:
            self.assertEqual(publish_purity_issues(self.publish), [])

    def _seed_tag(self) -> Path:
        snapshot = self.publish / "tags/Topic/测试/_definition.json"
        document = {"label": "测试", "labelEn": "Test", "createdAt": TIMESTAMP, "updatedAt": TIMESTAMP}
        assert_valid(document, "governance", "_definition")
        _write_json(snapshot, document)
        return snapshot

    def _media_codes(self) -> list[str]:
        return [issue["code"] for issue in self.gate.carried_media_closure_issues(self.publish)]

    def _assert_purity_rejects(self, code: str) -> None:
        issues = publish_purity_issues(self.publish)
        self.assertTrue(any(item.startswith(code + ":") for item in issues), msg=issues)

    def test_absent_canonical_objects_are_not_a_violation(self) -> None:
        self.assertEqual(publish_purity_issues(self.publish), [])
        self.assertEqual(creator_avatar_quality_issues(self.publish), [])
        self.assertEqual(self._media_codes(), [])
        self.assertEqual(self.gate.main(), 0)

    def test_repository_identity_is_required(self) -> None:
        for entry, code in (("repository.json", "DATA.REPOSITORY.MISSING"),
                            (".git", "DATA.REPOSITORY.GIT_ROOT_REQUIRED")):
            with self.subTest(entry=entry):
                path = self.publish / entry
                hidden = self.workspace / entry
                path.rename(hidden)
                try:
                    self._assert_purity_rejects(code)
                    self.assertEqual(self.gate.main(), 1)
                finally:
                    hidden.rename(path)

    def test_closed_canonical_objects_are_accepted(self) -> None:
        self._seed_closed_publish()
        self.assertEqual(self.gate.main(), 0)

    def test_carried_media_does_not_require_library_holdings(self) -> None:
        self._seed_closed_publish(admit_media=False)
        self.assertEqual(self.gate.main(), 0)
        self.assertFalse((self.workspace / "content-library").exists())

    def test_referenced_tag_snapshot_closes(self) -> None:
        self._seed_closed_publish()
        snapshot = self._seed_tag()
        manifest = _read_json(self.post_manifest)
        manifest["tagRefs"] = ["Topic/测试"]
        _write_json(self.post_manifest, manifest)
        self.assertEqual(publish_purity_issues(self.publish), [])
        snapshot.unlink()
        self._assert_purity_rejects("dangling_tag_ref")
        self.assertEqual(self.gate.main(), 0)

    def test_unreferenced_tag_snapshot_is_rejected(self) -> None:
        self._seed_closed_publish()
        self._seed_tag()
        self._assert_purity_rejects("orphan_tag_snapshot")
        self.assertEqual(self.gate.main(), 0)

    def test_noncanonical_publish_root_is_rejected(self) -> None:
        self._seed_closed_publish()
        _write_json(self.publish / "sources/catalog.json", {"sources": []})
        self._assert_purity_rejects("DATA.REPOSITORY.ROOT_ENTRY_INVALID")
        self.assertEqual(self.gate.main(), 1)

    def test_media_outside_carried_directory_is_rejected(self) -> None:
        self._seed_closed_publish()
        body = self.post_manifest.parent / "assets/cover.jpg"
        body.parent.mkdir()
        body.write_bytes(b"unbound-cover")
        self.assertTrue(self.gate.publish_structure_issues(self.publish))
        self.assertEqual(self._media_codes(), [])
        self.assertEqual(self.gate.main(), 1)

    def test_runtime_log_and_unknown_file_are_rejected(self) -> None:
        self._seed_closed_publish()
        for name in ("import.log", "unknown.bin"):
            with self.subTest(name=name):
                path = self.post_manifest.parent / name
                path.write_bytes(b"runtime-or-unknown")
                try:
                    issues = self.gate.publish_structure_issues(self.publish)
                    self.assertTrue(any(name in issue for issue in issues), msg=issues)
                    self.assertEqual(self.gate.main(), 1)
                finally:
                    path.unlink()

    def test_root_summary_is_not_canonical_input(self) -> None:
        self._seed_closed_publish()
        _write_json(self.publish / "summary.json", {"status": "passed"})
        self._assert_purity_rejects("DATA.REPOSITORY.ROOT_ENTRY_INVALID")
        self.assertEqual(self.gate.main(), 1)

    def test_intermediate_stage_directory_is_rejected(self) -> None:
        self._seed_closed_publish()
        stage = self.post_manifest.parent / "5.review/notes.md"
        stage.parent.mkdir()
        stage.write_text("reviewer notes\n", encoding="utf-8")
        self.assertEqual(self._media_codes(), [])
        self._assert_purity_rejects("DATA.PUBLISH.RETIRED_SIDECAR")
        self.assertEqual(self.gate.main(), 1)

    def test_dangling_creator_reference_is_rejected(self) -> None:
        self._seed_closed_publish()
        manifest = _read_json(self.post_manifest)
        manifest["creatorProfileId"] = "creator-absent"
        _write_json(self.post_manifest, manifest)
        self._assert_purity_rejects("dangling_creator_ref")
        self.assertEqual(self.gate.main(), 0)

    def test_orphan_creator_is_rejected(self) -> None:
        self._seed_closed_publish()
        self._seed_creator("creator-unreferenced")
        self._assert_purity_rejects("orphan_creator")
        self.assertEqual(self.gate.main(), 0)

    def test_dangling_media_reference_is_rejected(self) -> None:
        self._seed_closed_publish()
        (self.post_manifest.parent / "media/cover.png").unlink()
        self.assertEqual(self.gate.publish_structure_issues(self.publish), [])
        self.assertEqual(self._media_codes(), ["DATA.PUBLISH.CARRIED_MEDIA_MISSING"])
        self.assertEqual(self.gate.main(), 1)
        self.assertFalse((self.post_manifest.parent / "media/cover.png").exists())

    def test_carried_media_digest_and_size_drift_are_rejected(self) -> None:
        self._seed_closed_publish()
        body = self.post_manifest.parent / "media/cover.png"
        original = body.read_bytes()
        for changed in (b"x" * len(original), original + b"extra"):
            with self.subTest(size=len(changed)):
                body.write_bytes(changed)
                self.assertEqual(self._media_codes(), ["DATA.PUBLISH.CARRIED_MEDIA_DRIFT"])
                self.assertEqual(self.gate.main(), 1)

    def test_non_cas_media_reference_is_rejected_by_purity_owner(self) -> None:
        self._seed_closed_publish()
        manifest = _read_json(self.post_manifest)
        manifest["assets"][0]["objectKey"] = "media/image/travel/sample/cover.png"
        _write_json(self.post_manifest, manifest)
        self._assert_purity_rejects("non_cas_asset_ref")
        self.assertEqual(self.gate.main(), 0)

    def test_carried_media_path_escape_is_rejected(self) -> None:
        self._seed_closed_publish()
        manifest = _read_json(self.post_manifest)
        manifest["assets"][0]["path"] = "../outside.png"
        _write_json(self.post_manifest, manifest)
        self.assertTrue(any("路径逃逸" in code for code in self._media_codes()))
        self.assertEqual(self.gate.main(), 1)

    def test_symlink_media_is_rejected(self) -> None:
        self._seed_closed_publish()
        body = self.post_manifest.parent / "media/cover.png"
        outside = self.workspace / "outside.png"
        body.rename(outside)
        body.symlink_to(outside)
        self._assert_purity_rejects("DATA.REPOSITORY.SYMLINK")
        self.assertEqual(self.gate.main(), 1)

    def test_source_evidence_missing_or_drift_is_rejected(self) -> None:
        self._seed_closed_publish()
        evidence = self.post_manifest.parent / "sources/fixture/evidence.html"
        evidence.write_bytes(b"drift")
        self.assertEqual(self._media_codes(), ["DATA.PUBLISH.SOURCE_EVIDENCE_DRIFT"])
        self.assertEqual(self.gate.main(), 1)
        evidence.unlink()
        self.assertEqual(self._media_codes(), ["DATA.PUBLISH.SOURCE_EVIDENCE_MISSING"])
        self.assertEqual(self.gate.main(), 1)

    def test_creator_without_avatar_projection_is_rejected_by_avatar_owner(self) -> None:
        self._seed_closed_publish()
        (self.publish / "creators/creator-a/profile.json").unlink()
        self.assertEqual(creator_avatar_quality_issues(self.publish), [
            {"code": "creator_avatar_missing", "ref": "creator-a"},
        ])
        self.assertEqual(self.gate.main(), 0)

    def test_creator_avatar_identity_must_match_its_asset_ref(self) -> None:
        self._seed_closed_publish()
        profile = self.publish / "creators/creator-a/profile.json"
        document = _read_json(profile)
        document["avatarAsset"]["sha256"] = "sha256:" + "0" * 64
        _write_json(profile, document)
        self.assertEqual(creator_avatar_quality_issues(self.publish), [
            {"code": "creator_avatar_asset_ref_missing", "ref": "creator-a"},
        ])
        self.assertEqual(self.gate.main(), 0)

    def test_creator_avatar_body_must_be_carried_by_the_package(self) -> None:
        self._seed_closed_publish()
        (self.publish / "creators/creator-a/media/creator-a-avatar.png").unlink()
        self.assertEqual(creator_avatar_quality_issues(self.publish), [
            {"code": "creator_avatar_cas_invalid", "ref": "creator-a"},
        ])
        self.assertEqual(self._media_codes(), ["DATA.PUBLISH.CARRIED_MEDIA_MISSING"])
        self.assertEqual(self.gate.main(), 1)


if __name__ == "__main__":
    unittest.main()
