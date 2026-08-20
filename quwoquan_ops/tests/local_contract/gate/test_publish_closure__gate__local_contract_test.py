"""local_contract: canonical publish closure 门禁的正负例。

门禁本身只是 `main()`：它把 canonical 树同时交给结构纯度、全树闭包和 creator
头像质量三条判定，任一有话说就 BLOCK。三条判定各自另有单元覆盖，这里要钉的是
**组合**——历史上真正会悄悄丢失的是其中一条调用被删掉，而剩下两条仍然全绿。
因此每条判定都配一个"只有它会报"的负例：谁被摘掉，谁的负例立刻变绿。

`PUBLISH_ROOT` 是 module 级常量，测试把它指向临时树；媒体字节属于 content
library 而不属于 publish 树，所以 CAS 根同样被换成临时库，判定不依赖开发机上
已有的 holdings。
"""

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
REPO_TAG_SNAPSHOT_ROOT = ROOT / "quwoquan_data" / "publish" / "tags"

if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from core import content_library  # noqa: E402


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "verify_publish_closure_companion",
        MODULE_PATH,
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


class PublishClosureGateTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name)
        self.publish = self.workspace / "publish"
        self.publish.mkdir()
        self._isolate_content_library()
        self.gate = _load_module()
        self.gate.PUBLISH_ROOT = self.publish
        self.post_manifest = (
            self.publish / "posts/article/travel/sample/1/manifest.json"
        )

    def _isolate_content_library(self) -> None:
        library_root = self.workspace / "content-library"
        # 常量在 import 期就已解析，env 只对运行期再读它的调用方生效；CAS 根因此
        # 由测试直接替换，env 只是防止任何按需重解析的路径回到开发机的库上。
        for name in ("QWQ_LIBRARY_ROOT", "QWQ_OUTPUT_ROOT"):
            self._set_environment(name, str(library_root))
        cas_roots = content_library.LIBRARY_CAS_ROOT_BY_KIND
        kind = content_library.MEDIA_KIND
        original = cas_roots[kind]
        self.addCleanup(cas_roots.__setitem__, kind, original)
        cas_roots[kind] = library_root / "_media_cas"

    def _set_environment(self, name: str, value: str) -> None:
        original = os.environ.get(name)
        if original is None:
            self.addCleanup(os.environ.pop, name, None)
        else:
            self.addCleanup(os.environ.__setitem__, name, original)
        os.environ[name] = value

    def _seed_creator(self, creator_ref: str, *, admit_body: bool = True) -> None:
        """落一个完整的 creator 对象：身份、CAS 头像与权利证据齐备。"""
        body = f"creator-avatar-body-{creator_ref}".encode("utf-8")
        digest_hex = hashlib.sha256(body).hexdigest()
        digest = f"sha256:{digest_hex}"
        if admit_body:
            content_library.admit_library_bytes(
                body, kind=content_library.MEDIA_KIND
            )
        asset_id = f"{creator_ref}-avatar"
        root = self.publish / "creators" / creator_ref
        _write_json(root / "_creator.json", {"creatorId": creator_ref})
        _write_json(
            root / "profile.json",
            {
                "creatorId": creator_ref,
                "avatarAsset": {
                    "assetId": asset_id,
                    "kind": "avatar",
                    "sha256": digest,
                },
            },
        )
        _write_json(
            root / "assets.refs.json",
            {
                "assets": [
                    {
                        "assetId": asset_id,
                        "kind": "avatar",
                        "sha256": digest,
                        "objectKey": (
                            f"media/objects/sha256/{digest_hex[:2]}/"
                            f"{digest_hex[2:4]}/{digest_hex}.png"
                        ),
                        "bytes": len(body),
                        "mimeType": "image/png",
                    }
                ]
            },
        )
        _write_json(
            root / "rights_snapshots" / f"{asset_id}.json",
            {"manifestAsset": {"assetId": asset_id, "sha256": digest}},
        )

    def _seed_closed_publish(self) -> None:
        self._seed_creator("creator-a")
        _write_json(
            self.post_manifest,
            {
                "contentIdentity": "work",
                "contentType": "article",
                "creatorId": "creator-a",
            },
        )

    def _repo_tag_snapshot(self) -> tuple[str, str]:
        """取一份真实 taxonomy consumer snapshot 作为可通过 schema 的正例输入。"""
        candidates = sorted(REPO_TAG_SNAPSHOT_ROOT.rglob("_definition.json"))
        self.assertTrue(
            candidates,
            msg=f"canonical publish 缺少 tag snapshot: {REPO_TAG_SNAPSHOT_ROOT}",
        )
        snapshot = candidates[0]
        tag_ref = snapshot.parent.relative_to(REPO_TAG_SNAPSHOT_ROOT).as_posix()
        return tag_ref, snapshot.read_text(encoding="utf-8")

    def _closure_codes(self) -> list[str]:
        report = self.gate.validate_publish_invariants(self.publish)
        return [issue["code"] for issue in report["issues"]]

    def test_absent_canonical_objects_are_not_a_violation(self) -> None:
        self.assertEqual(self.gate.publish_structure_issues(self.publish), [])
        self.assertEqual(self.gate.creator_avatar_quality_issues(self.publish), [])
        self.assertEqual(self._closure_codes(), [])
        self.assertEqual(self.gate.main(), 0)

    def test_closed_canonical_objects_are_accepted(self) -> None:
        self._seed_closed_publish()
        self.assertEqual(self.gate.main(), 0)

    def test_referenced_tag_snapshot_closes(self) -> None:
        self._seed_closed_publish()
        tag_ref, definition = self._repo_tag_snapshot()
        manifest = _read_json(self.post_manifest)
        manifest["tagRefs"] = [tag_ref]
        _write_json(self.post_manifest, manifest)
        snapshot = self.publish / "tags" / tag_ref / "_definition.json"
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_text(definition, encoding="utf-8")

        self.assertEqual(self.gate.main(), 0)

        snapshot.unlink()
        self.assertIn("dangling_tag_ref", self._closure_codes())
        self.assertEqual(self.gate.main(), 1)

    def test_unreferenced_tag_snapshot_is_rejected(self) -> None:
        # publish 只承载被消费者引用的 taxonomy 叶子；多余快照会让 release 携带
        # 无人引用的标签定义，因此它是缺口而不是无害冗余。
        self._seed_closed_publish()
        tag_ref, definition = self._repo_tag_snapshot()
        snapshot = self.publish / "tags" / tag_ref / "_definition.json"
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_text(definition, encoding="utf-8")

        self.assertIn("orphan_tag_snapshot", self._closure_codes())
        self.assertEqual(self.gate.main(), 1)

    def test_noncanonical_publish_root_is_rejected(self) -> None:
        self._seed_closed_publish()
        _write_json(self.publish / "sources/catalog.json", {"sources": []})

        self.assertIn("noncanonical_root", self._closure_codes())
        self.assertEqual(self.gate.main(), 1)

    def test_media_body_in_publish_is_rejected(self) -> None:
        # 媒体字节由 content library 单一持有；一旦落进受版本控制的 canonical
        # 树，同一份字节就有了第二个所有者。
        self._seed_closed_publish()
        body = self.post_manifest.parent / "assets" / "cover.jpg"
        body.parent.mkdir(parents=True, exist_ok=True)
        body.write_bytes(b"cover-bytes")

        self.assertIn("media_body_in_publish", self._closure_codes())
        self.assertEqual(self.gate.main(), 1)

    def test_runtime_log_in_publish_is_rejected(self) -> None:
        self._seed_closed_publish()
        (self.post_manifest.parent / "import.log").write_text("ok\n", encoding="utf-8")

        issues = self.gate.publish_structure_issues(self.publish)
        self.assertTrue(
            any("logs are runtime evidence" in item for item in issues),
            msg=issues,
        )
        self.assertEqual(self.gate.main(), 1)

    def test_intermediate_stage_directory_is_rejected(self) -> None:
        # 只有结构判定会拦这一条：`.md` 是合法 canonical 文档后缀，闭包判定看不见
        # 它落在 review/ 过程目录里。摘掉 publish_structure_issues 这条就会变绿。
        self._seed_closed_publish()
        stage = self.post_manifest.parent / "review" / "notes.md"
        stage.parent.mkdir(parents=True, exist_ok=True)
        stage.write_text("reviewer notes\n", encoding="utf-8")

        self.assertEqual(self._closure_codes(), [])
        self.assertEqual(self.gate.creator_avatar_quality_issues(self.publish), [])
        issues = self.gate.publish_structure_issues(self.publish)
        self.assertTrue(
            any("must not enter publish" in item for item in issues),
            msg=issues,
        )
        self.assertEqual(self.gate.main(), 1)

    def test_dangling_creator_reference_is_rejected(self) -> None:
        self._seed_closed_publish()
        manifest = _read_json(self.post_manifest)
        manifest["creatorId"] = "creator-absent"
        _write_json(self.post_manifest, manifest)

        self.assertIn("dangling_creator_ref", self._closure_codes())
        self.assertEqual(self.gate.main(), 1)

    def test_orphan_creator_is_rejected(self) -> None:
        self._seed_closed_publish()
        self._seed_creator("creator-unreferenced")

        self.assertIn("orphan_creator", self._closure_codes())
        self.assertEqual(self.gate.main(), 1)

    def test_dangling_media_reference_is_rejected(self) -> None:
        # objectKey 形态合法但 library 没有这份字节：App 会拿到一条解析不出
        # 字节的引用，而 canonical 文档本身看不出任何异常。
        self._seed_closed_publish()
        digest_hex = hashlib.sha256(b"never-admitted-body").hexdigest()
        manifest = _read_json(self.post_manifest)
        manifest["assets"] = [
            {
                "assetId": "cover",
                "kind": "image",
                "role": "cover",
                "objectKey": (
                    f"media/objects/sha256/{digest_hex[:2]}/"
                    f"{digest_hex[2:4]}/{digest_hex}.jpg"
                ),
            }
        ]
        _write_json(self.post_manifest, manifest)

        self.assertIn("dangling_asset_ref", self._closure_codes())
        self.assertEqual(self.gate.main(), 1)

    def test_non_cas_media_reference_is_rejected(self) -> None:
        self._seed_closed_publish()
        manifest = _read_json(self.post_manifest)
        manifest["assets"] = [
            {
                "assetId": "cover",
                "kind": "image",
                "role": "cover",
                "objectKey": "media/image/travel/sample/cover.jpg",
            }
        ]
        _write_json(self.post_manifest, manifest)

        self.assertIn("non_cas_asset_ref", self._closure_codes())
        self.assertEqual(self.gate.main(), 1)

    def test_creator_without_avatar_projection_is_rejected(self) -> None:
        # 只有头像质量判定会拦这一条：creator 身份文档仍在、引用仍然闭合，
        # 结构与闭包都无话可说。摘掉 creator_avatar_quality_issues 就会变绿。
        self._seed_closed_publish()
        (self.publish / "creators/creator-a/profile.json").unlink()

        self.assertEqual(self._closure_codes(), [])
        self.assertEqual(self.gate.publish_structure_issues(self.publish), [])
        self.assertEqual(
            self.gate.creator_avatar_quality_issues(self.publish),
            [{"code": "creator_avatar_missing", "ref": "creator-a"}],
        )
        self.assertEqual(self.gate.main(), 1)

    def test_creator_avatar_identity_must_match_its_asset_ref(self) -> None:
        self._seed_closed_publish()
        profile = self.publish / "creators/creator-a/profile.json"
        document = _read_json(profile)
        document["avatarAsset"]["sha256"] = "sha256:" + "0" * 64
        _write_json(profile, document)

        self.assertEqual(
            self.gate.creator_avatar_quality_issues(self.publish),
            [{"code": "creator_avatar_asset_ref_missing", "ref": "creator-a"}],
        )
        self.assertEqual(self.gate.main(), 1)

    def test_creator_avatar_body_must_be_held_by_the_library(self) -> None:
        # 文档之间完全自洽，缺的只是字节：头像是 App 首屏就会请求的资源，
        # 「引用齐全但库里没有」正是只有向 library 提问才能发现的形态。
        self._seed_creator("creator-b", admit_body=False)
        _write_json(
            self.post_manifest,
            {
                "contentIdentity": "work",
                "contentType": "article",
                "creatorId": "creator-b",
            },
        )

        self.assertEqual(
            self.gate.creator_avatar_quality_issues(self.publish),
            [{"code": "creator_avatar_cas_invalid", "ref": "creator-b"}],
        )
        self.assertEqual(self.gate.main(), 1)


if __name__ == "__main__":
    unittest.main()
