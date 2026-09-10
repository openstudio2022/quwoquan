"""local_contract: 对象体积预算门的逻辑闭包度量与拒绝判据正负例。

预算量的是「一个对象的逻辑字节闭包」：自身文档 + 它引用到的每个不同媒体体各算一次。
这里钉住的是最容易被悄悄改坏的三点：同一份内容在一个对象内被引用多次不得买到额外
预算、载体决定预算上限（video 与其余分档）、以及「单个素材过大」与「素材太多」必须
给出可分辨的拒绝原因——两者的修复动作完全不同。

MiB 级暂存媒体先用稀疏文件构造；publish fixture 携带真实媒体字节并重算 digest，
验证大小与内容寻址身份一致，不再依赖 publish 外的库反查。
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
MODULE_PATH = ROOT / "quwoquan_data/scripts/verify/verify_object_size_budget.py"
MEBIBYTE = 1024 * 1024


def _load_module(sandbox: Path):
    """加载门禁，并把 publish 根与媒体解析改绑到沙箱。

    门禁在 import 期就从 ``core.paths`` 冻结 ``PUBLISH_ROOT``，因此先用临时根覆盖
    环境变量：本进程可能是第一个 import ``core.paths`` 的地方，不覆盖就会绑上仓内
    真实 publish 树与开发机 HOME 下的真实内容库。环境变量只保证首次 import 安全，
    publish 根与暂存媒体库根随后都绑定沙箱；门禁只验证 publish 随体媒体，
    fixture 不匹配的 path、digest、bytes 仍交真实门禁拒绝。
    """

    overrides = {
        "QWQ_DATA_ROOT": str(sandbox / "isolated"),
        "QWQ_OUTPUT_ROOT": str(sandbox / "output"),
        "QWQ_PUBLISH_ROOT": str(sandbox / "publish"),
        "QWQ_LIBRARY_ROOT": str(sandbox / "library"),
    }
    previous = {key: os.environ.get(key) for key in overrides}
    os.environ.update(overrides)
    name = "verify_object_size_budget"
    previous_module = sys.modules.get(name)
    try:
        spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        # ``ObjectClosure`` 是 slots dataclass，构造期要经 ``sys.modules`` 反查
        # 定义模块解析注解；不先登记就会在 exec 期直接 AttributeError。
        sys.modules[name] = module
        spec.loader.exec_module(module)
    finally:
        if previous_module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous_module
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    module.PUBLISH_ROOT = sandbox / "publish"
    import core.content_library  # fixture 暂存媒体使用库的唯一 CAS 布局。

    return module


def _digest(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _object_key(digest: str, suffix: str = ".jpg") -> str:
    return f"media/objects/sha256/{digest[:2]}/{digest[2:4]}/{digest}{suffix}"


def _asset_row(digest: str, *, asset_id: str = "", suffix: str = ".jpg") -> dict:
    return {
        "assetId": asset_id or f"asset_{digest[:8]}",
        "sha256": f"sha256:{digest}",
        "objectKey": _object_key(digest, suffix),
        "kind": "video" if suffix == ".mp4" else "image",
    }


def _admit_media(sandbox: Path, digest: str, *, size: int) -> Path:
    """按内容库自己的分片布局落一个媒体体，布局由被测真相源给出而非本文件重述。"""

    entry = sys.modules["core.content_library"].library_cas_path(
        "media", digest, library_root=sandbox / "library"
    )
    entry.parent.mkdir(parents=True, exist_ok=True)
    with entry.open("wb") as handle:
        handle.truncate(size)
    return entry


def _manifest_identity(ref: str) -> dict:
    kind, logical = ref.split("/", 1)
    if kind == "creators":
        return {"creatorProfileId": logical}
    if kind == "entities":
        domain, entity_type, name = logical.split("/", 2)
        return {
            "entityId": "entity_" + _digest(logical)[:16], "version": 1,
            "entityRef": "/entity/" + logical, "domain": domain, "type": entity_type,
            "label": name, "geographyMode": "administrative",
            "geoTagRef": "Topic/地理/行政区/中国/四川省/乐山市",
        }
    carrier, angle, title, _sequence = logical.split("/")
    return {
        "contentId": "content_" + _digest(logical)[:16], "version": 1,
        "objectRef": logical, "contentType": carrier,
        "publishAngle": angle, "publishTitle": title,
    }


def _published_root(sandbox: Path, ref: str) -> Path:
    from core.publish_layout import allocate_object_path, load_layout_policy

    kind = ref.split("/", 1)[0]
    relative = ref if kind == "creators" else allocate_object_path(
        _manifest_identity(ref), kind, [], load_layout_policy()
    )
    return sandbox / "publish" / relative


def _publish_object(
    sandbox: Path,
    ref: str,
    *,
    documents: dict[str, str] | None = None,
    document_sizes: dict[str, int] | None = None,
    assets: list | None = None,
    refs_filename: str = "manifest.json",
) -> Path:
    object_root = _published_root(sandbox, ref)
    object_root.mkdir(parents=True, exist_ok=True)
    for name, body in (documents or {}).items():
        path = object_root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    for name, size in (document_sizes or {}).items():
        path = object_root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as handle:
            handle.truncate(size)
    carried_assets = []
    for row in assets or []:
        if not isinstance(row, dict):
            carried_assets.append(row)
            continue
        declared = str(row.get("sha256") or "").removeprefix("sha256:")
        source = sys.modules["core.content_library"].library_cas_path(
            "media", declared or "0" * 64, library_root=sandbox / "library"
        )
        carried = dict(row)
        if source.is_file():
            raw = source.read_bytes()
            actual = hashlib.sha256(raw).hexdigest()
            relative = f"media/{actual}.bin"
            destination = object_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
            carried.update(path=relative, bytes=len(raw), sha256="sha256:" + actual)
            # 负例显式覆写随体契约，正常 fixture 总是匹配真实 bytes。
            carried.update(row.get("invalidCarriedFields") or {})
            carried.pop("invalidCarriedFields", None)
        carried_assets.append(carried)
    document = {
        "schema": "quwoquan_data.entity_object" if ref.startswith("entities/") else "quwoquan_data.post_object",
        **_manifest_identity(ref),
        "assets": carried_assets,
    }
    (object_root / refs_filename).write_text(
        json.dumps(document, ensure_ascii=False), encoding="utf-8"
    )
    return object_root


def _run_main(module) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = module.main()
    return code, out.getvalue()


class ObjectSizeBudgetGateLocalContractTest(unittest.TestCase):
    @contextlib.contextmanager
    def _sandbox(self):
        with tempfile.TemporaryDirectory() as tmp:
            # macOS 的 /var 本身是 symlink，fixture 根必须与真实仓同样严格。
            sandbox = Path(tmp).resolve()
            root = sandbox / "publish"
            root.mkdir()
            (root / ".git").mkdir()
            (root / "repository.json").write_text(json.dumps({
                "schema": "quwoquan_data.publish_repository.v2",
                "repositoryId": "object-budget-test", "layoutVersion": 2,
            }), encoding="utf-8")
            yield _load_module(sandbox), sandbox

    def _closure(self, module, sandbox: Path, ref: str, kind: str = "posts"):
        relative = ref.removeprefix(f"{kind}/")
        return module.object_closure(
            _published_root(sandbox, ref),
            ref=ref,
            carrier=module.object_carrier(kind, relative),
        )

    def test_carrier_is_derived_from_object_identity(self) -> None:
        with self._sandbox() as (module, _sandbox):
            self.assertEqual(module.object_carrier("entities", "地点/景区/峨眉山"), "entity")
            self.assertEqual(module.object_carrier("posts", "video/体验/标题/1"), "video")
            self.assertEqual(module.object_carrier("posts", "/image/画报/标题/1"), "image")
            self.assertEqual(module.object_carrier("posts", "article/攻略/标题/1"), "article")

    def test_video_carrier_gets_the_larger_budget(self) -> None:
        """一个对象是一份消费者价值，编码轨道是 video 独有的成本，不能外溢到图文。

        取值本身不在这里声明：门禁只能经 ``object_storage_budget_bytes`` 从
        ``media_processing.policy.yaml`` 取值，本例钉的是「载体分档确实生效」，
        而不是把同一批数字在测试里再抄一遍变成第二真相源。
        """

        with self._sandbox() as (module, sandbox):
            self.assertEqual(module.MEBIBYTE, MEBIBYTE)
            declared_video = module.object_storage_budget_bytes("video")
            declared_default = module.object_storage_budget_bytes("default")
            self.assertGreater(declared_video, declared_default)
            _publish_object(sandbox, "posts/video/体验/标题/1", documents={"post.json": "{}"})
            _publish_object(sandbox, "posts/image/画报/标题/1", documents={"post.json": "{}"})
            _publish_object(sandbox, "entities/地点/景区/峨眉山", documents={"entity.json": "{}"})
            video, _ = self._closure(module, sandbox, "posts/video/体验/标题/1")
            image, _ = self._closure(module, sandbox, "posts/image/画报/标题/1")
            entity, _ = self._closure(
                module, sandbox, "entities/地点/景区/峨眉山", kind="entities"
            )
            self.assertEqual(video.budget_bytes, declared_video)
            self.assertEqual(image.budget_bytes, declared_default)
            self.assertEqual(entity.budget_bytes, declared_default)

    def test_duplicate_reference_to_one_body_is_counted_once(self) -> None:
        """同一份内容在一个对象内被引用两次是引用语义缺陷，不该在这里换来双倍预算。"""

        with self._sandbox() as (module, sandbox):
            shared = _digest("shared-body")
            _admit_media(sandbox, shared, size=700)
            _publish_object(
                sandbox,
                "posts/image/画报/重复引用/1",
                assets=[
                    _asset_row(shared, asset_id="cover"),
                    _asset_row(shared, asset_id="inline"),
                ],
            )
            closure, issues = self._closure(module, sandbox, "posts/image/画报/重复引用/1")
            self.assertEqual(issues, [])
            self.assertEqual(closure.media_bytes, 700)
            self.assertEqual(closure.largest_asset_bytes, 700)

    def test_distinct_bodies_are_summed(self) -> None:
        with self._sandbox() as (module, sandbox):
            first, second = _digest("first-body"), _digest("second-body")
            _admit_media(sandbox, first, size=700)
            _admit_media(sandbox, second, size=300)
            _publish_object(
                sandbox,
                "posts/image/画报/两个素材/1",
                assets=[_asset_row(first), _asset_row(second)],
            )
            closure, issues = self._closure(module, sandbox, "posts/image/画报/两个素材/1")
            self.assertEqual(issues, [])
            self.assertEqual(closure.media_bytes, 1000)
            self.assertEqual(closure.largest_asset_bytes, 700)

    def test_unresolvable_reference_is_not_free_bytes(self) -> None:
        """库拿不出的引用是闭包未解析，不是零字节；当成零字节等于给缺失素材放行。"""

        with self._sandbox() as (module, sandbox):
            missing = _digest("never-admitted")
            _publish_object(
                sandbox, "posts/image/画报/缺素材/1", assets=[_asset_row(missing)]
            )
            closure, issues = self._closure(module, sandbox, "posts/image/画报/缺素材/1")
            self.assertEqual(len(issues), 1)
            self.assertIn("referenced carried media entry is missing", issues[0])
            self.assertIn(_object_key(missing), issues[0])
            self.assertEqual(closure.media_bytes, 0)

    def test_reference_without_content_addressed_identity_is_refused(self) -> None:
        with self._sandbox() as (module, sandbox):
            digest = _digest("legacy-body")
            _admit_media(sandbox, digest, size=100)
            rows = [
                {**_asset_row(digest), "invalidCarriedFields": {"sha256": ""}},
                {**_asset_row(digest), "invalidCarriedFields": {"path": "../outside.bin"}},
                {**_asset_row(digest), "invalidCarriedFields": {"sha256": "sha256:" + "0" * 64}},
            ]
            _publish_object(sandbox, "posts/image/画报/非内容寻址/1", assets=rows)
            closure, issues = self._closure(
                module, sandbox, "posts/image/画报/非内容寻址/1"
            )
            self.assertEqual(len(issues), 3)
            self.assertIn("no content-addressed identity", issues[0])
            for issue in issues[1:]:
                self.assertIn("missing or corrupt", issue)
            self.assertEqual(closure.media_bytes, 0)

    def test_non_object_asset_row_is_refused(self) -> None:
        with self._sandbox() as (module, sandbox):
            _publish_object(
                sandbox, "posts/image/画报/坏行/1", assets=["media/objects/sha256/x"]
            )
            _closure, issues = self._closure(module, sandbox, "posts/image/画报/坏行/1")
            self.assertEqual(len(issues), 1)
            self.assertIn("asset refs row is not an object", issues[0])

    def test_invalid_manifest_is_an_unresolved_closure(self) -> None:
        for raw in ("[]", "{", "{}", '{"assets": null}', '{"assets": {}}'):
            with self.subTest(raw=raw), self._sandbox() as (module, sandbox):
                object_root = _publish_object(sandbox, "posts/image/画报/坏清单/1")
                (object_root / "manifest.json").write_text(raw, encoding="utf-8")
                closure, issues = self._closure(module, sandbox, "posts/image/画报/坏清单/1")
                self.assertEqual(closure.media_bytes, 0)
                self.assertEqual(len(issues), 1)
                code, output = _run_main(module)
                self.assertEqual(code, 1)
                self.assertIn("closure_unresolved", output)

    def test_homepage_and_post_assets_have_only_manifest_authority(self) -> None:
        for ref, kind in (("posts/image/画报/唯一清单/1", "posts"), ("entities/地点/景区/峨眉山", "entities")):
            with self.subTest(kind=kind), self._sandbox() as (module, sandbox):
                digest = _digest("manifest-body")
                _admit_media(sandbox, digest, size=10)
                object_root = _publish_object(sandbox, ref, assets=[_asset_row(digest)])
                for retired in ("asset.refs.json", "assets.refs.json"):
                    (object_root / retired).write_text("not JSON", encoding="utf-8")
                closure, issues = self._closure(module, sandbox, ref, kind=kind)
                self.assertEqual(issues, [])
                self.assertEqual(closure.media_bytes, 10)

    def test_sidecar_without_manifest_never_passes_as_zero_media(self) -> None:
        for ref, kind in (("posts/image/画报/旧资产/1", "posts"), ("entities/地点/景区/峨眉山", "entities")):
            with self.subTest(kind=kind), self._sandbox() as (module, sandbox):
                _publish_object(sandbox, ref, assets=[], refs_filename="asset.refs.json")
                closure, issues = self._closure(module, sandbox, ref, kind=kind)
                self.assertEqual(closure.media_bytes, 0)
                self.assertEqual(len(issues), 1)
                self.assertIn("manifest.json", issues[0])
                self.assertEqual(_run_main(module)[0], 1)

    def test_creator_keeps_independent_avatar_asset_contract(self) -> None:
        with self._sandbox() as (module, sandbox):
            digest = _digest("creator-avatar")
            _admit_media(sandbox, digest, size=100)
            ref = "creators/作者/1"
            root = _publish_object(
                sandbox, ref, documents={"assets.refs.json": "not JSON"},
                assets=[_asset_row(digest)], refs_filename="profile.json",
            )
            self.assertEqual(module._asset_refs_path(root), root / "profile.json")
            closure, issues = self._closure(module, sandbox, ref, kind="creators")
            self.assertEqual(issues, [])
            self.assertEqual(closure.media_bytes, 100)

    def test_object_without_media_has_no_media_bytes(self) -> None:
        with self._sandbox() as (module, sandbox):
            _publish_object(
                sandbox, "posts/article/攻略/纯文/1", documents={"post.json": "{}"}
            )
            closure, issues = self._closure(module, sandbox, "posts/article/攻略/纯文/1")
            self.assertEqual(issues, [])
            self.assertEqual(closure.media_bytes, 0)
            self.assertEqual(closure.largest_asset_bytes, 0)
            self.assertEqual(closure.closure_bytes, closure.document_bytes)

    def test_document_bytes_cover_the_whole_object_directory(self) -> None:
        """对象成本包含它随身携带的全部文档，漏算子目录会让预算长期虚低。"""

        with self._sandbox() as (module, sandbox):
            digest = _digest("cover-body")
            _admit_media(sandbox, digest, size=400)
            _publish_object(
                sandbox,
                "posts/article/攻略/多文档/1",
                documents={
                    "post.json": "x" * 120,
                    "rights_snapshots/cover.json": "y" * 80,
                },
                assets=[_asset_row(digest)],
            )
            object_root = _published_root(sandbox, "posts/article/攻略/多文档/1")
            expected_documents = sum(
                path.stat().st_size for path in object_root.rglob("*")
                if path.is_file() and path.relative_to(object_root).parts[0] != "media"
            )
            closure, issues = self._closure(module, sandbox, "posts/article/攻略/多文档/1")
            self.assertEqual(issues, [])
            self.assertEqual(closure.document_bytes, expected_documents)
            self.assertEqual(closure.closure_bytes, expected_documents + 400)

    def test_budget_verdict_separates_one_oversized_asset_from_too_many(self) -> None:
        """两种超预算的修复动作不同：换一个素材，还是拆一个对象。"""

        with self._sandbox() as (module, _sandbox):
            oversized_asset = module.ObjectClosure(
                ref="posts/image/画报/单个过大/1",
                carrier="image",
                budget_bytes=10 * MEBIBYTE,
                document_bytes=MEBIBYTE,
                media_bytes=11 * MEBIBYTE,
                largest_asset_bytes=11 * MEBIBYTE,
            )
            too_many_assets = module.ObjectClosure(
                ref="posts/image/画报/素材太多/1",
                carrier="image",
                budget_bytes=10 * MEBIBYTE,
                document_bytes=MEBIBYTE,
                media_bytes=11 * MEBIBYTE,
                largest_asset_bytes=4 * MEBIBYTE,
            )
            within = module.ObjectClosure(
                ref="posts/image/画报/正常/1",
                carrier="image",
                budget_bytes=10 * MEBIBYTE,
                document_bytes=MEBIBYTE,
                media_bytes=8 * MEBIBYTE,
                largest_asset_bytes=4 * MEBIBYTE,
            )
            self.assertEqual(
                module.budget_verdict(oversized_asset),
                module.ObjectBudgetVerdict.SINGLE_ASSET_OVER_BUDGET,
            )
            self.assertEqual(
                module.budget_verdict(too_many_assets),
                module.ObjectBudgetVerdict.CLOSURE_OVER_BUDGET,
            )
            self.assertEqual(
                module.budget_verdict(within),
                module.ObjectBudgetVerdict.WITHIN_BUDGET,
            )
            self.assertEqual(within.over_budget_bytes, 0)
            self.assertEqual(too_many_assets.over_budget_bytes, 2 * MEBIBYTE)
            self.assertEqual(
                module.budget_violations(
                    [within, too_many_assets, oversized_asset]
                ),
                [too_many_assets, oversized_asset],
            )

    def test_closure_bytes_are_documents_plus_distinct_media(self) -> None:
        with self._sandbox() as (module, _sandbox):
            closure = module.ObjectClosure(
                ref="posts/image/画报/正常/1",
                carrier="image",
                budget_bytes=10 * MEBIBYTE,
                document_bytes=1200,
                media_bytes=3400,
            )
            self.assertEqual(closure.closure_bytes, 4600)
            self.assertEqual(closure.over_budget_bytes, 0)

    # spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#req-019
    def test_object_closures_use_manifest_identity_under_partitioned_geography(self) -> None:
        """真实行政链与 p0001 是 locator；逻辑 ref、目录 seq 与版本彼此独立。"""

        with self._sandbox() as (module, sandbox):
            digest = _digest("partitioned-media")
            _admit_media(sandbox, digest, size=400)
            post = _publish_object(sandbox, "posts/image/画报/标题/1", assets=[
                _asset_row(digest, asset_id="cover"), _asset_row(digest, asset_id="inline"),
            ])
            entity = _publish_object(sandbox, "entities/地点/景区/峨眉山", documents={"page.md": "正文"})
            self.assertIn("p0001", post.parts)
            self.assertIn("中国/四川省/乐山市", entity.as_posix())
            self.assertNotEqual(post.relative_to(sandbox / "publish").as_posix(), "posts/image/画报/标题/1")
            # 所有未到条目层的空分区/同名组都不是对象。
            (post.parent.parent / "空同名组").mkdir()
            # 随体证据可能与对象 manifest 同名，不成为嵌套对象。
            (post / "sources/s001").mkdir(parents=True)
            (post / "sources/s001/manifest.json").write_text("{}", encoding="utf-8")
            document = json.loads((entity / "manifest.json").read_text(encoding="utf-8"))
            document["version"] = 7
            (entity / "manifest.json").write_text(json.dumps(document), encoding="utf-8")
            closures, issues = module.object_closures(publish_root=sandbox / "publish")
            self.assertEqual(issues, [])
            self.assertEqual(
                sorted(row.ref for row in closures),
                ["entities/地点/景区/峨眉山", "posts/image/画报/标题/1"],
            )
            measured = next(row for row in closures if row.carrier == "image")
            self.assertEqual(measured.media_bytes, 400)
            self.assertEqual(measured.closure_bytes, module._document_bytes(post) + 400)
            self.assertEqual(
                {row.ref: row.carrier for row in closures},
                {
                    "entities/地点/景区/峨眉山": "entity",
                    "posts/image/画报/标题/1": "image",
                },
            )

    def test_non_entry_manifest_is_typed_and_not_counted(self) -> None:
        for version in (None, 0, "1", True):
            with self.subTest(version=version), self._sandbox() as (module, sandbox):
                ref = "posts/image/画报/未到条目/1"
                parent = _published_root(sandbox, ref).parent
                parent.mkdir(parents=True)
                document = {**_manifest_identity(ref), "assets": [], "version": version}
                (parent / "manifest.json").write_text(json.dumps(document), encoding="utf-8")
                closures, issues = module.object_closures()
                self.assertEqual(closures, [])
                self.assertIn("DATA.OBJECT.MANIFEST_INVALID", issues[0])
                self.assertEqual(_run_main(module)[0], 1)
        with self._sandbox() as (module, sandbox):
            ref = "posts/image/画报/未到条目/1"
            parent = _published_root(sandbox, ref).parent
            parent.mkdir(parents=True)
            (parent / "manifest.json").write_text(json.dumps({**_manifest_identity(ref), "assets": []}), encoding="utf-8")
            closures, issues = module.object_closures()
            self.assertEqual(closures, [])
            self.assertIn("DATA.LAYOUT.COORDINATES_INVALID", issues[0])

    def test_missing_manifest_is_typed_without_falling_back_to_physical_identity(self) -> None:
        for ref in ("posts/image/画报/清单丢失/1", "entities/地点/景区/峨眉山"):
            with self.subTest(ref=ref), self._sandbox() as (module, sandbox):
                root = _publish_object(sandbox, ref, documents={"content_review.json": "{}"})
                (root / "manifest.json").unlink()
                closures, issues = module.object_closures()
                self.assertEqual(closures, [])
                self.assertIn("DATA.OBJECT.MANIFEST_MISSING", issues[0])
                self.assertEqual(_run_main(module)[0], 1)

    def test_non_object_roots_do_not_enter_budget_inventory(self) -> None:
        with self._sandbox() as (module, sandbox):
            for relative in ("creators/author/profile.json", "tags/topic/_definition.json",
                             "releases/release/manifest.json", ".git/manifest.json"):
                path = sandbox / "publish" / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("not JSON", encoding="utf-8")
            self.assertEqual(module.object_closures(), ([], []))
            self.assertEqual(_run_main(module)[0], 0)

    def test_repository_identity_and_symlinks_remain_fail_closed(self) -> None:
        for broken in ("missing-marker", "invalid-marker", "linked-worktree", "root-link", "media-link"):
            with self.subTest(broken=broken), self._sandbox() as (module, sandbox):
                root = sandbox / "publish"
                if broken == "missing-marker":
                    (root / "repository.json").unlink()
                elif broken == "invalid-marker":
                    (root / "repository.json").write_text("{}", encoding="utf-8")
                elif broken == "linked-worktree":
                    (root / ".git").rmdir()
                    (root / ".git").write_text("gitdir: elsewhere", encoding="utf-8")
                elif broken == "root-link":
                    alias = sandbox / "alias"
                    alias.symlink_to(root, target_is_directory=True)
                    module.PUBLISH_ROOT = alias
                else:
                    object_root = _publish_object(sandbox, "posts/image/画报/禁止链接/1")
                    (object_root / "media").symlink_to(sandbox / "library", target_is_directory=True)
                closures, issues = module.object_closures()
                self.assertEqual(closures, [])
                self.assertIn("DATA.PUBLISH.REPOSITORY_INVALID", issues[0])
                if broken.endswith("link"):
                    self.assertIn("DATA.REPOSITORY.SYMLINK", issues[0])
                self.assertEqual(_run_main(module)[0], 1)

    def test_video_may_hold_what_an_article_may_not(self) -> None:
        """同样体积在 video 下合法、在 article 下阻断，是载体分档的唯一可观测证据。"""

        with self._sandbox() as (module, sandbox):
            digest = _digest("same-sized-media")
            _admit_media(sandbox, digest, size=12 * MEBIBYTE)
            _publish_object(
                sandbox,
                "posts/video/体验/大视频/1",
                assets=[_asset_row(digest, suffix=".mp4")],
            )
            _publish_object(
                sandbox,
                "posts/article/攻略/大图文/1",
                assets=[_asset_row(digest)],
            )
            closures, issues = module.object_closures(publish_root=sandbox / "publish")
            self.assertEqual(issues, [])
            self.assertEqual(
                [row.ref for row in module.budget_violations(closures)],
                ["posts/article/攻略/大图文/1"],
            )

    def test_main_refuses_an_object_over_its_budget(self) -> None:
        with self._sandbox() as (module, sandbox):
            _publish_object(
                sandbox,
                "posts/article/攻略/超预算/1",
                document_sizes={"draft.article.md": 11 * MEBIBYTE},
            )
            code, out = _run_main(module)
            self.assertEqual(code, 1)
            self.assertIn("DATA.OBJECT.SIZE_BUDGET_EXCEEDED", out)
            self.assertIn("cause=closure_over_budget", out)
            self.assertIn("posts/article/攻略/超预算/1", out)

    def test_main_names_a_single_oversized_asset_as_its_own_cause(self) -> None:
        with self._sandbox() as (module, sandbox):
            digest = _digest("oversized-body")
            _admit_media(sandbox, digest, size=11 * MEBIBYTE)
            _publish_object(
                sandbox,
                "posts/image/画报/单素材过大/1",
                assets=[_asset_row(digest)],
            )
            code, out = _run_main(module)
            self.assertEqual(code, 1)
            self.assertIn("cause=single_asset_over_budget", out)

    def test_main_refuses_an_unresolved_closure(self) -> None:
        with self._sandbox() as (module, sandbox):
            _publish_object(
                sandbox,
                "posts/image/画报/缺素材/1",
                assets=[_asset_row(_digest("never-admitted"))],
            )
            code, out = _run_main(module)
            self.assertEqual(code, 1)
            self.assertIn("closure_unresolved", out)

    def test_main_accepts_objects_within_budget(self) -> None:
        with self._sandbox() as (module, sandbox):
            digest = _digest("small-body")
            _admit_media(sandbox, digest, size=2048)
            _publish_object(
                sandbox,
                "posts/image/画报/正常/1",
                documents={"post.json": "{}"},
                assets=[_asset_row(digest)],
            )
            _publish_object(sandbox, "entities/地点/景区/峨眉山", documents={"entity.json": "{}"})
            code, out = _run_main(module)
            self.assertEqual(code, 0)
            self.assertIn("OK objects=2", out)

    def test_describe_closure_names_carrier_budget_and_overrun(self) -> None:
        """拒绝信息要能直接指向修复动作，缺任一项运维就得回头猜。"""

        with self._sandbox() as (module, _sandbox):
            rendered = module.describe_closure(
                module.ObjectClosure(
                    ref="posts/image/画报/超预算/1",
                    carrier="image",
                    budget_bytes=10 * MEBIBYTE,
                    document_bytes=MEBIBYTE,
                    media_bytes=11 * MEBIBYTE,
                    largest_asset_bytes=4 * MEBIBYTE,
                )
            )
            self.assertIn("posts/image/画报/超预算/1", rendered)
            self.assertIn("carrier=image", rendered)
            self.assertIn("closure=12.00MiB", rendered)
            self.assertIn("largestAsset=4.00MiB", rendered)
            self.assertIn("budget=10MiB", rendered)
            self.assertIn("over=2.00MiB", rendered)


if __name__ == "__main__":
    unittest.main()
