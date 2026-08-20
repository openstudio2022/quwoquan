"""local_contract: 对象体积预算门的逻辑闭包度量与拒绝判据正负例。

预算量的是「一个对象的逻辑字节闭包」：自身文档 + 它引用到的每个不同媒体体各算一次。
这里钉住的是最容易被悄悄改坏的三点：同一份内容在一个对象内被引用多次不得买到额外
预算、载体决定预算上限（video 与其余分档）、以及「单个素材过大」与「素材太多」必须
给出可分辨的拒绝原因——两者的修复动作完全不同。

MiB 级体积用稀疏文件表达：判据读的是 ``st_size``，写真实字节只会让本套件变慢，
不会让判据更真。
"""

from __future__ import annotations

import contextlib
import functools
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
    随后的两处改绑才是本测试实际的读写边界——``resolve_media_holding`` 仍是被测
    真相源本身，只是把库根参数预绑到沙箱，缺失条目照样抛真实的 MediaHoldingError。
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
    module.resolve_media_holding = functools.partial(
        module.resolve_media_holding, library_root=sandbox / "library"
    )
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
        "kind": "image",
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


def _publish_object(
    sandbox: Path,
    ref: str,
    *,
    documents: dict[str, str] | None = None,
    document_sizes: dict[str, int] | None = None,
    assets: list | None = None,
    refs_filename: str = "asset.refs.json",
) -> Path:
    object_root = sandbox / "publish" / ref
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
    if assets is not None:
        (object_root / refs_filename).write_text(
            json.dumps({"assets": assets}, ensure_ascii=False), encoding="utf-8"
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
            sandbox = Path(tmp)
            yield _load_module(sandbox), sandbox

    def _closure(self, module, sandbox: Path, ref: str, kind: str = "posts"):
        relative = ref.removeprefix(f"{kind}/")
        return module.object_closure(
            sandbox / "publish" / ref,
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
        """一个对象是一份消费者价值，编码轨道是 video 独有的成本，不能外溢到图文。"""

        with self._sandbox() as (module, sandbox):
            self.assertEqual(module.MEBIBYTE, MEBIBYTE)
            self.assertEqual(module.VIDEO_OBJECT_BUDGET_BYTES, 50 * MEBIBYTE)
            self.assertEqual(module.DEFAULT_OBJECT_BUDGET_BYTES, 10 * MEBIBYTE)
            _publish_object(sandbox, "posts/video/体验/标题/1", documents={"post.json": "{}"})
            _publish_object(sandbox, "posts/image/画报/标题/1", documents={"post.json": "{}"})
            _publish_object(sandbox, "entities/地点/景区/峨眉山", documents={"entity.json": "{}"})
            video, _ = self._closure(module, sandbox, "posts/video/体验/标题/1")
            image, _ = self._closure(module, sandbox, "posts/image/画报/标题/1")
            entity, _ = self._closure(
                module, sandbox, "entities/地点/景区/峨眉山", kind="entities"
            )
            self.assertEqual(video.budget_bytes, 50 * MEBIBYTE)
            self.assertEqual(image.budget_bytes, 10 * MEBIBYTE)
            self.assertEqual(entity.budget_bytes, 10 * MEBIBYTE)

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
            self.assertIn("referenced media entry is missing", issues[0])
            self.assertIn(_object_key(missing), issues[0])
            self.assertEqual(closure.media_bytes, 0)

    def test_reference_without_content_addressed_identity_is_refused(self) -> None:
        with self._sandbox() as (module, sandbox):
            digest = _digest("legacy-body")
            _admit_media(sandbox, digest, size=100)
            rows = [
                {**_asset_row(digest), "objectKey": "media/objects/legacy/photo.jpg"},
                {**_asset_row(digest), "sha256": ""},
                # 分片目录与摘要不一致：路径与内容不再互相印证。
                {
                    **_asset_row(digest),
                    "objectKey": f"media/objects/sha256/ff/ff/{digest}.jpg",
                },
            ]
            _publish_object(sandbox, "posts/image/画报/非内容寻址/1", assets=rows)
            closure, issues = self._closure(
                module, sandbox, "posts/image/画报/非内容寻址/1"
            )
            self.assertEqual(len(issues), 3)
            for issue in issues:
                self.assertIn("no content-addressed identity", issue)
            self.assertEqual(closure.media_bytes, 0)

    def test_non_object_asset_row_is_refused(self) -> None:
        with self._sandbox() as (module, sandbox):
            _publish_object(
                sandbox, "posts/image/画报/坏行/1", assets=["media/objects/sha256/x"]
            )
            _closure, issues = self._closure(module, sandbox, "posts/image/画报/坏行/1")
            self.assertEqual(len(issues), 1)
            self.assertIn("asset refs row is not an object", issues[0])

    def test_asset_refs_document_must_be_an_object(self) -> None:
        with self._sandbox() as (module, sandbox):
            object_root = _publish_object(sandbox, "posts/image/画报/顶层数组/1")
            (object_root / "asset.refs.json").write_text("[]", encoding="utf-8")
            with self.assertRaises(TypeError):
                self._closure(module, sandbox, "posts/image/画报/顶层数组/1")

    def test_object_owns_exactly_one_asset_refs_document(self) -> None:
        """两份 refs 文档意味着两个真相源；先选一个再谈体积，而不是各算一半。"""

        with self._sandbox() as (module, sandbox):
            self.assertEqual(
                module._ASSET_REFS_FILENAMES, ("asset.refs.json", "assets.refs.json")
            )
            digest = _digest("body")
            _admit_media(sandbox, digest, size=10)
            _publish_object(sandbox, "posts/image/画报/双份/1", assets=[_asset_row(digest)])
            _publish_object(
                sandbox,
                "posts/image/画报/双份/1",
                assets=[_asset_row(digest)],
                refs_filename="assets.refs.json",
            )
            with self.assertRaises(ValueError):
                self._closure(module, sandbox, "posts/image/画报/双份/1")

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
            object_root = sandbox / "publish/posts/article/攻略/多文档/1"
            expected_documents = sum(
                path.stat().st_size for path in object_root.rglob("*") if path.is_file()
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

    def test_object_closures_walk_posts_and_entities_at_their_own_depth(self) -> None:
        """post 与 entity 的目录身份深度不同；用同一深度扫会漏掉或误认对象。"""

        with self._sandbox() as (module, sandbox):
            _publish_object(sandbox, "posts/image/画报/标题/1", documents={"post.json": "{}"})
            _publish_object(sandbox, "entities/地点/景区/峨眉山", documents={"entity.json": "{}"})
            # 恰好差一层的中间目录不是对象，不能被当成对象计入预算。
            (sandbox / "publish/entities/地点/景区/峨眉山/媒体").mkdir(parents=True)
            closures, issues = module.object_closures(publish_root=sandbox / "publish")
            self.assertEqual(issues, [])
            self.assertEqual(
                sorted(row.ref for row in closures),
                ["entities/地点/景区/峨眉山", "posts/image/画报/标题/1"],
            )
            self.assertEqual(
                {row.ref: row.carrier for row in closures},
                {
                    "entities/地点/景区/峨眉山": "entity",
                    "posts/image/画报/标题/1": "image",
                },
            )

    def test_video_may_hold_what_an_article_may_not(self) -> None:
        """同样体积在 video 下合法、在 article 下阻断，是载体分档的唯一可观测证据。"""

        with self._sandbox() as (module, sandbox):
            _publish_object(
                sandbox,
                "posts/video/体验/大视频/1",
                document_sizes={"source.mp4": 12 * MEBIBYTE},
            )
            _publish_object(
                sandbox,
                "posts/article/攻略/大图文/1",
                document_sizes={"inline.bin": 12 * MEBIBYTE},
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
                document_sizes={"inline.bin": 11 * MEBIBYTE},
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
