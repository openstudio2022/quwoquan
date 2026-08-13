"""`--write-baseline` 不得违背基线自称的「只减不增」。

spec_ref: specs/feature-tree/runtime/runtime-client-foundation/spec.md#sit-001

这条门禁的过渡期基线写着 "Counts may only decrease"，但写入路径原先无条件重写文件，
等于给那句话开了后门：新增一处直连图片 API 再跑一次 `--write-baseline` 就能转绿。
债务清零后基线文件已被删除，上限因此为空，任何重建都应被挡下。
"""

from __future__ import annotations

import importlib.util
import io
import contextlib
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[4]
GATE_PATH = (
    ROOT
    / "quwoquan_app"
    / "scripts"
    / "runtime"
    / "media"
    / "verify_app_network_image_surface.py"
)


def _load_gate():
    spec = importlib.util.spec_from_file_location(
        "verify_app_network_image_surface", GATE_PATH
    )
    if spec is None or spec.loader is None:
        raise AssertionError(f"无法加载门禁: {GATE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NetworkImageBaselineMonotonicityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module = _load_gate()
        self.temporary = __import__("tempfile").TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.app_lib = root / "lib"
        self.app_lib.mkdir(parents=True)
        self.allowlist = root / "app_network_image_policy_allowlist.yaml"
        self.module.APP_LIB = self.app_lib
        self.module.ALLOWLIST = self.allowlist

    def _run(self, *args: str) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            mock.patch.object(sys, "argv", [str(GATE_PATH), *args]),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            result = self.module.main()
        return result, stdout.getvalue(), stderr.getvalue()

    def _write_direct_usage(self, relative_path: str) -> None:
        path = self.app_lib / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "Widget build() => Image.network('https://example.test/a.png');\n",
            encoding="utf-8",
        )

    def test_a_retired_baseline_cannot_be_rebuilt_to_excuse_a_new_violation(
        self,
    ) -> None:
        self._write_direct_usage("service/content_service/content/post/card.dart")

        result, _, stderr = self._run("--write-baseline")

        self.assertEqual(result, 2)
        self.assertIn("只减不增", stderr)
        self.assertFalse(self.allowlist.exists())

    def test_writing_a_lower_count_than_the_existing_ceiling_is_allowed(self) -> None:
        relative = "service/content_service/content/post/card.dart"
        self.allowlist.write_text(
            "version: 1\nallowed:\n"
            f"  - path: {relative}\n"
            "    maxCount: 4\n",
            encoding="utf-8",
        )
        self._write_direct_usage(relative)

        result, stdout, _ = self._run("--write-baseline")

        self.assertEqual(result, 0)
        self.assertIn("entries=1", stdout)
        self.assertIn("maxCount: 1", self.allowlist.read_text(encoding="utf-8"))

    def test_zero_debt_removes_the_stale_baseline_file(self) -> None:
        self.allowlist.write_text(
            "version: 1\nallowed:\n  - path: stale.dart\n    maxCount: 2\n",
            encoding="utf-8",
        )

        result, stdout, _ = self._run("--write-baseline")

        self.assertEqual(result, 0)
        self.assertIn("entries=0", stdout)
        self.assertFalse(self.allowlist.exists())


if __name__ == "__main__":
    unittest.main()
