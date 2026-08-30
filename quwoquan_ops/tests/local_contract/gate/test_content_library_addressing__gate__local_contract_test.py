"""local_contract: 内容库自寻址门的读侧校验正负例。

入库两处 seam 只在写入时校验字节，读侧的 ``resolve_media_holding`` 只回答可达性，
所以一个被带外替换过字节的条目会照常解析、照常流进 release。本门禁就是那道缺失的
读侧校验，这里把它的三条实质判据钉住：地址即内容摘要、符号链接不是条目、
以及扫描面覆盖整个库而不只是 publish 当前引用到的那些条目。
"""

from __future__ import annotations

import contextlib
import functools
import hashlib
import importlib.util
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
MODULE_PATH = ROOT / "quwoquan_data/scripts/verify/verify_content_library_addressing.py"


def _load_module(sandbox: Path):
    """加载门禁，并把库根改绑到沙箱。

    门禁在 import 期就从 ``core.paths`` 冻结库根常量，因此先用临时根覆盖环境变量：
    本进程可能是第一个 import ``core.paths`` 的地方，不覆盖就会绑上开发机 HOME 下
    的真实内容库。环境变量只保证首次 import 安全——``core.paths`` 一旦进入
    ``sys.modules`` 就不再重读环境——真正决定本测试扫描位置的是随后对
    ``library_cas_root`` 的改绑，它把 kind → 根目录的映射整体挪进沙箱，
    kind 与目录名的对应关系仍由被测真相源自己给出。
    """

    overrides = {
        "QWQ_DATA_ROOT": str(sandbox / "isolated"),
        "QWQ_OUTPUT_ROOT": str(sandbox / "output"),
        "QWQ_PUBLISH_ROOT": str(sandbox / "publish"),
        "QWQ_LIBRARY_ROOT": str(sandbox / "library"),
    }
    previous = {key: os.environ.get(key) for key in overrides}
    os.environ.update(overrides)
    name = "verify_content_library_addressing"
    previous_module = sys.modules.get(name)
    try:
        spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
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
    module.library_cas_root = functools.partial(
        module.library_cas_root, library_root=sandbox / "library"
    )
    return module


def _admit(root: Path, body: bytes, *, address: str = "", suffix: str = "") -> Path:
    """按库的分片布局写入一个条目，``address`` 显式给出时即模拟带外替换。"""

    digest = address or hashlib.sha256(body).hexdigest()
    entry = root / digest[:2] / digest[2:4] / f"{digest}{suffix}"
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_bytes(body)
    return entry


def _run_main(module) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = module.main()
    return code, out.getvalue()


class ContentLibraryAddressingGateLocalContractTest(unittest.TestCase):
    @contextlib.contextmanager
    def _library(self):
        with tempfile.TemporaryDirectory() as tmp:
            sandbox = Path(tmp)
            module = _load_module(sandbox)
            roots = {
                kind: module.library_cas_root(kind)
                for kind in module.LIBRARY_CAS_ROOT_BY_KIND
            }
            for root in roots.values():
                root.mkdir(parents=True, exist_ok=True)
            yield module, roots, sandbox

    def test_entries_holding_their_own_bytes_are_accepted(self) -> None:
        with self._library() as (module, roots, _sandbox):
            _admit(roots["media"], b"\x89PNG honest body")
            _admit(roots["media"], b"another honest body", suffix=".jpg")
            _admit(roots["source"], b"honest capsule bytes")
            self.assertEqual(module.library_addressing_issues(), [])

    def test_out_of_band_replacement_is_detected(self) -> None:
        """写侧 seam 只在入库时校验一次，替换后的字节此前一路静默流进 release。"""

        with self._library() as (module, roots, _sandbox):
            address = hashlib.sha256(b"declared body").hexdigest()
            _admit(roots["media"], b"replaced body", address=address)
            issues = module.library_addressing_issues()
            self.assertEqual(len(issues), 1)
            self.assertEqual(issues[0]["code"], "library_entry_address_drift")
            self.assertEqual(issues[0]["kind"], "media")
            self.assertIn(address, issues[0]["ref"])
            self.assertIn(hashlib.sha256(b"replaced body").hexdigest(), issues[0]["ref"])

    def test_single_byte_drift_is_enough(self) -> None:
        """摘要判据不能被「几乎相同」蒙混，否则等于没有校验。"""

        with self._library() as (module, roots, _sandbox):
            body = b"a" * 4096
            _admit(
                roots["media"],
                body[:-1] + b"b",
                address=hashlib.sha256(body).hexdigest(),
            )
            self.assertEqual(
                [issue["code"] for issue in module.library_addressing_issues()],
                ["library_entry_address_drift"],
            )

    def test_suffix_is_not_part_of_the_address(self) -> None:
        """条目按内容摘要寻址，扩展名只是投递提示；把它算进地址会全库误报。"""

        with self._library() as (module, roots, _sandbox):
            body = b"video body"
            _admit(roots["media"], body, suffix=".mp4")
            self.assertEqual(module.library_addressing_issues(), [])
            _admit(
                roots["media"],
                b"other body",
                address=hashlib.sha256(b"declared").hexdigest(),
                suffix=".mp4",
            )
            self.assertEqual(len(module.library_addressing_issues()), 1)

    def test_symlink_is_refused_and_not_digested_as_content(self) -> None:
        """条目必须自持字节：符号链接的目标可在库外被改写，摘要校验管不到。"""

        with self._library() as (module, roots, sandbox):
            outside = sandbox / "outside.bin"
            outside.write_bytes(b"body owned by nobody")
            digest = hashlib.sha256(b"body owned by nobody").hexdigest()
            link = roots["media"] / digest[:2] / digest[2:4] / digest
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(outside)
            issues = module.library_addressing_issues()
            self.assertEqual(len(issues), 1)
            self.assertEqual(issues[0]["code"], "library_entry_symlink")
            self.assertEqual(issues[0]["kind"], "media")
            self.assertEqual(issues[0]["ref"], f"{digest[:2]}/{digest[2:4]}/{digest}")

    def test_every_library_kind_is_scanned(self) -> None:
        """条目按摘要共享，只查 media 会放过被引用的受治理输入字节。"""

        with self._library() as (module, roots, _sandbox):
            self.assertEqual(
                sorted(module.LIBRARY_CAS_ROOT_BY_KIND), ["media", "source"]
            )
            _admit(
                roots["source"],
                b"tampered capsule",
                address=hashlib.sha256(b"declared capsule").hexdigest(),
            )
            issues = module.library_addressing_issues()
            self.assertEqual([issue["kind"] for issue in issues], ["source"])

    def test_scan_is_whole_library_not_publish_scoped(self) -> None:
        """一个损坏条目危及未来每一次引用，不只是今天引用它的对象。"""

        with self._library() as (module, roots, _sandbox):
            for index in range(3):
                _admit(
                    roots["media"],
                    f"tampered-{index}".encode(),
                    address=hashlib.sha256(f"declared-{index}".encode()).hexdigest(),
                )
            self.assertEqual(len(module.library_addressing_issues()), 3)

    def test_absent_library_root_is_not_a_finding(self) -> None:
        """库尚未建立时报错只会制造一盏与内容质量无关的红灯。"""

        with tempfile.TemporaryDirectory() as tmp:
            module = _load_module(Path(tmp))
            self.assertEqual(module.library_addressing_issues(), [])

    def test_shard_directories_are_not_entries(self) -> None:
        with self._library() as (module, roots, _sandbox):
            (roots["media"] / "ab" / "cd").mkdir(parents=True, exist_ok=True)
            self.assertEqual(module.library_addressing_issues(), [])

    def test_body_larger_than_one_read_chunk_is_digested_whole(self) -> None:
        """分块读取一旦只消费首块，超过一块的媒体体就再也测不出替换。"""

        with self._library() as (module, roots, _sandbox):
            module._READ_CHUNK = 16
            body = bytes(range(256)) * 4
            tail_changed = body[:-1] + bytes([(body[-1] + 1) % 256])
            address = hashlib.sha256(body).hexdigest()
            # 两个条目共用同一地址、共用同一首块：只读首块的实现会把两者都判为诚实。
            _admit(roots["media"], body, address=address)
            _admit(roots["media"], tail_changed, address=address, suffix=".bin")
            issues = module.library_addressing_issues()
            self.assertEqual(len(issues), 1)
            self.assertIn(hashlib.sha256(tail_changed).hexdigest(), issues[0]["ref"])

    def test_main_refuses_a_library_that_lost_an_address(self) -> None:
        with self._library() as (module, roots, _sandbox):
            _admit(roots["media"], b"honest body")
            _admit(
                roots["media"],
                b"replaced body",
                address=hashlib.sha256(b"declared body").hexdigest(),
            )
            code, out = _run_main(module)
            self.assertEqual(code, 1)
            self.assertIn("FAIL", out)
            self.assertIn("library_entry_address_drift", out)

    def test_main_accepts_and_counts_an_intact_library(self) -> None:
        with self._library() as (module, roots, _sandbox):
            _admit(roots["media"], b"first body")
            _admit(roots["media"], b"second body", suffix=".webp")
            _admit(roots["source"], b"third body")
            code, out = _run_main(module)
            self.assertEqual(code, 0)
            self.assertIn("OK entries=3", out)


if __name__ == "__main__":
    unittest.main()
