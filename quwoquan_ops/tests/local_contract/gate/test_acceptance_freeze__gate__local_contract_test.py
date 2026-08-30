"""local_contract: 分级验收冻结门的引擎不可变判据与失败归类正负例。

门禁本身是「跑一次 → 改引擎 → 下一批全是新阻断」这个循环的唯一打断机制，
所以它的判据一旦静默失效，验收窗口就退回口头承诺。这里把三条真正承载语义的
判据钉住：G0 是唯一允许改引擎的窗口、行数增长独立于内容漂移单独阻断、
engine_defect 必须先有可复现失败测试才解锁引擎。
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
MODULE_PATH = ROOT / "quwoquan_data/scripts/verify/verify_acceptance_freeze.py"

# 一棵形状与真实引擎同构的最小树：scripts/*.py 与 schema/*.json 是被冻结面，
# 同目录下的 .md/.json 噪声文件用来证明冻结范围没有外溢到非引擎文件。
_ENGINE_FIXTURE = {
    "scripts/cli.py": "def main() -> int:\n    return 0\n",
    "scripts/core/paths.py": "PUBLISH = 'publish'\n",
    "scripts/notes.md": "运行手册，不属于引擎冻结面\n",
    "scripts/local_cache.json": '{"cache": true}\n',
    "schema/post.json": '{"type": "object"}\n',
}


def _load_module(sandbox: Path):
    """加载门禁并把它的两个根常量改绑到沙箱。

    门禁在 import 期就从 ``core.paths`` 冻结 ``OUTPUT_ROOT``，因此先用临时根覆盖
    环境变量——本进程可能是第一个 import ``core.paths`` 的地方，不覆盖就会把常量
    绑死在开发机的真实输出根上。环境变量只保证首次 import 安全，真正决定本测试
    读写位置的是随后对模块全局量的改绑：``core.paths`` 一旦进入 ``sys.modules``，
    后续任何 import 都不会再读环境变量。
    """

    overrides = {
        "QWQ_DATA_ROOT": str(sandbox / "isolated"),
        "QWQ_OUTPUT_ROOT": str(sandbox / "output"),
        "QWQ_PUBLISH_ROOT": str(sandbox / "publish"),
        "QWQ_LIBRARY_ROOT": str(sandbox / "library"),
    }
    previous = {key: os.environ.get(key) for key in overrides}
    os.environ.update(overrides)
    name = "verify_acceptance_freeze"
    previous_module = sys.modules.get(name)
    try:
        spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        # ``TreeSnapshot`` 是 slots dataclass，构造期要经 ``sys.modules`` 反查
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
    module.DATA_ROOT = sandbox / "engine"
    module.OUTPUT_ROOT = sandbox / "output"
    return module


def _write_engine(root: Path, files: dict[str, str]) -> None:
    for relative, body in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")


def _run(module, argv: list[str]) -> tuple[int, str, str]:
    """经 ``main`` 驱动，顺带把 argparse 子命令接线一起纳入判据。"""

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = module.main(argv)
    return code, out.getvalue(), err.getvalue()


def _baseline_document(module, stage: str) -> dict:
    return json.loads(module._baseline_path(stage).read_text(encoding="utf-8"))


def _write_baseline(module, stage: str, document: dict) -> None:
    module._baseline_path(stage).write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


class AcceptanceFreezeGateLocalContractTest(unittest.TestCase):
    @contextlib.contextmanager
    def _engine(self, files: dict[str, str] | None = None):
        with tempfile.TemporaryDirectory() as tmp:
            sandbox = Path(tmp)
            _write_engine(sandbox / "engine", files or _ENGINE_FIXTURE)
            yield _load_module(sandbox), sandbox / "engine"

    def test_frozen_engine_passes_check(self) -> None:
        with self._engine() as (module, _engine_root):
            self.assertEqual(_run(module, ["record", "--stage", "g1"])[0], 0)
            code, out, err = _run(module, ["check", "--stage", "g1"])
            self.assertEqual(code, 0)
            self.assertIn("PASSED", out)
            self.assertEqual(err, "")

    def test_modified_engine_blocks_from_g1_onwards(self) -> None:
        """验收窗口内改引擎必须让该级作废，否则冻结门只是装饰。"""

        with self._engine() as (module, engine_root):
            _run(module, ["record", "--stage", "g2"])
            (engine_root / "scripts/cli.py").write_text(
                "def main() -> int:\n    return 1\n", encoding="utf-8"
            )
            code, _out, err = _run(module, ["check", "--stage", "g2"])
            self.assertEqual(code, 1)
            self.assertIn("GATE_BLOCK", err)
            self.assertIn("modified scripts/cli.py", err)
            self.assertIn("restarting from G0", err)

    def test_g0_reports_engine_change_without_blocking(self) -> None:
        """G0 的产出目标就是第一个 release，必然暴露真实缺陷，此时改引擎合法。"""

        with self._engine() as (module, engine_root):
            _run(module, ["record", "--stage", "g0"])
            (engine_root / "schema/post.json").write_text(
                '{"type": "array"}\n', encoding="utf-8"
            )
            code, out, err = _run(module, ["check", "--stage", "g0"])
            self.assertEqual(code, 0)
            self.assertIn("ADVISORY", out)
            self.assertIn("modified schema/post.json", out)
            self.assertEqual(err, "")

    def test_engine_change_window_is_g0_only(self) -> None:
        with self._engine() as (module, _engine_root):
            self.assertEqual(module.STAGES, ("g0", "g1", "g2", "g3"))
            self.assertEqual(module.ENGINE_CHANGE_ALLOWED_STAGES, frozenset({"g0"}))
            for stage in ("g1", "g2", "g3"):
                self.assertNotIn(stage, module.ENGINE_CHANGE_ALLOWED_STAGES)

    def test_added_and_removed_engine_files_are_named(self) -> None:
        with self._engine() as (module, engine_root):
            _run(module, ["record", "--stage", "g1"])
            (engine_root / "scripts/core/paths.py").unlink()
            (engine_root / "scripts/extra_stage.py").write_text(
                "VALUE = 1\n", encoding="utf-8"
            )
            code, _out, err = _run(module, ["check", "--stage", "g1"])
            self.assertEqual(code, 1)
            self.assertIn("removed scripts/core/paths.py", err)
            self.assertIn("added scripts/extra_stage.py", err)

    def test_line_growth_blocks_without_content_drift(self) -> None:
        """验收期靠加代码解决问题与「跑产能」目标相反，所以行数是独立阻断项。

        基线内容摘要保持一致、只把行数下调，是唯一能把增长判据与漂移判据分开
        观测的形状：漂移判据此时完全不触发，仍必须阻断。
        """

        with self._engine() as (module, _engine_root):
            _run(module, ["record", "--stage", "g3"])
            document = _baseline_document(module, "g3")
            for tree in document["trees"]:
                if tree["name"] == "scripts":
                    tree["lineCount"] = tree["lineCount"] - 2
            _write_baseline(module, "g3", document)
            code, _out, err = _run(module, ["check", "--stage", "g3"])
            self.assertEqual(code, 1)
            self.assertIn("grew", err)
            self.assertNotIn("modified", err)

    def test_line_shrink_is_not_a_violation(self) -> None:
        """删代码不是「靠加代码绕过验收」，增长判据必须是单向的。"""

        with self._engine() as (module, _engine_root):
            _run(module, ["record", "--stage", "g1"])
            document = _baseline_document(module, "g1")
            for tree in document["trees"]:
                tree["lineCount"] = tree["lineCount"] + 50
            _write_baseline(module, "g1", document)
            code, out, _err = _run(module, ["check", "--stage", "g1"])
            self.assertEqual(code, 0)
            self.assertIn("PASSED", out)

    def test_missing_baseline_blocks_check(self) -> None:
        """没有基线就没有冻结对象；静默放行等于整级验收无判据。"""

        with self._engine() as (module, _engine_root):
            _run(module, ["record", "--stage", "g1"])
            code, _out, err = _run(module, ["check", "--stage", "g2"])
            self.assertEqual(code, 1)
            self.assertIn("baseline is missing", err)

    def test_missing_baseline_tree_is_drift(self) -> None:
        """基线少记一棵树等于把该树移出冻结面，必须与内容漂移同等对待。"""

        with self._engine() as (module, _engine_root):
            _run(module, ["record", "--stage", "g1"])
            document = _baseline_document(module, "g1")
            document["trees"] = [
                tree for tree in document["trees"] if tree["name"] != "schema"
            ]
            _write_baseline(module, "g1", document)
            code, _out, err = _run(module, ["check", "--stage", "g1"])
            self.assertEqual(code, 1)
            self.assertIn("missing baseline tree schema", err)

    def test_freeze_scope_is_engine_code_only(self) -> None:
        """冻结面外溢会让运行手册、本地缓存这类正常改动误伤验收窗口。"""

        with self._engine() as (module, engine_root):
            self.assertEqual(
                module.ENGINE_TREES, (("scripts", "*.py"), ("schema", "*.json"))
            )
            _run(module, ["record", "--stage", "g2"])
            (engine_root / "scripts/notes.md").write_text(
                "改写运行手册\n", encoding="utf-8"
            )
            (engine_root / "scripts/local_cache.json").write_text(
                '{"cache": false}\n', encoding="utf-8"
            )
            code, out, _err = _run(module, ["check", "--stage", "g2"])
            self.assertEqual(code, 0)
            self.assertIn("PASSED", out)

    def test_bytecode_caches_do_not_enter_the_baseline(self) -> None:
        """缓存目录随运行产生，纳入冻结面会让每次跑完都自动作废下一级。"""

        with self._engine() as (module, engine_root):
            before = module._snapshot_tree("scripts", "*.py")
            _write_engine(
                engine_root,
                {
                    "scripts/__pycache__/cli.cpython-313.pyc.py": "cached\n",
                    "scripts/.pytest_cache/probe.py": "cached\n",
                },
            )
            after = module._snapshot_tree("scripts", "*.py")
            self.assertEqual(before.digest, after.digest)
            self.assertEqual(before.file_count, after.file_count)
            self.assertEqual(before.line_count, after.line_count)

    def test_recorded_baseline_carries_per_file_digests(self) -> None:
        """漂移要能指到具体文件，基线就必须逐文件留摘要而不是只留树摘要。"""

        with self._engine() as (module, _engine_root):
            _run(module, ["record", "--stage", "g1"])
            document = _baseline_document(module, "g1")
            self.assertEqual(
                document["schema"], "quwoquan_data.acceptance_freeze_baseline"
            )
            self.assertEqual(document["stage"], "g1")
            self.assertFalse(document["engineChangeAllowed"])
            by_name = {tree["name"]: tree for tree in document["trees"]}
            self.assertEqual(sorted(by_name), ["schema", "scripts"])
            self.assertEqual(sorted(by_name["scripts"]["files"]), ["cli.py", "core/paths.py"])
            self.assertTrue(by_name["scripts"]["digest"].startswith("sha256:"))

    def test_g0_baseline_records_its_open_window(self) -> None:
        with self._engine() as (module, _engine_root):
            _run(module, ["record", "--stage", "g0"])
            self.assertTrue(_baseline_document(module, "g0")["engineChangeAllowed"])

    def test_input_failure_classes_never_unlock_the_engine(self) -> None:
        """把输入问题归类成引擎缺陷，正是两个月循环的起点。"""

        with self._engine() as (module, _engine_root):
            self.assertEqual(
                module.INPUT_FAILURE_CLASSES,
                (
                    "source_exhausted",
                    "credential_missing",
                    "catalog_unavailable",
                    "provider_5xx",
                    "object_quality_discard",
                ),
            )
            for failure_class in module.INPUT_FAILURE_CLASSES:
                code, out, err = _run(
                    module,
                    ["classify", "--stage", "g2", "--failure-class", failure_class],
                )
                self.assertEqual(code, 0)
                self.assertIn("engineChangeAllowed=false", out)
                self.assertIn("do not touch the engine", out)
                self.assertEqual(err, "")

    def test_engine_defect_requires_a_reproducible_failing_test(self) -> None:
        with self._engine() as (module, _engine_root):
            self.assertEqual(module.ENGINE_FAILURE_CLASSES, ("engine_defect",))
            code, _out, err = _run(
                module,
                ["classify", "--stage", "g1", "--failure-class", "engine_defect"],
            )
            self.assertEqual(code, 1)
            self.assertIn("GATE_BLOCK", err)
            self.assertIn("reproducible failing test", err)

    def test_classified_engine_defect_restarts_from_g0(self) -> None:
        """允许动引擎的代价是整轮验收重来，否则「允许」就等于无成本。"""

        with self._engine() as (module, _engine_root):
            code, out, err = _run(
                module,
                [
                    "classify",
                    "--stage",
                    "g1",
                    "--failure-class",
                    "engine_defect",
                    "--failing-test",
                ],
            )
            self.assertEqual(code, 0)
            self.assertIn("engineChangeAllowed=true", out)
            self.assertIn("Restart acceptance from G0", out)
            self.assertEqual(err, "")

    def test_failure_classes_are_the_union_of_both_tracks(self) -> None:
        with self._engine() as (module, _engine_root):
            self.assertEqual(
                module.FAILURE_CLASSES,
                module.INPUT_FAILURE_CLASSES + module.ENGINE_FAILURE_CLASSES,
            )
            self.assertEqual(
                set(module.INPUT_FAILURE_CLASSES) & set(module.ENGINE_FAILURE_CLASSES),
                set(),
            )

    def test_unknown_stage_and_failure_class_are_refused(self) -> None:
        """阶段与归类是闭集；拼错就放行会让冻结记录挂到不存在的级上。"""

        with self._engine() as (module, _engine_root):
            for argv in (
                ["check", "--stage", "g9"],
                ["classify", "--stage", "g1", "--failure-class", "operator_tired"],
            ):
                with contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit):
                        module.main(argv)

    def test_tree_drift_separates_added_removed_and_modified(self) -> None:
        with self._engine() as (module, _engine_root):
            # _tree_drift 只读 files，digest 取值与判据无关；但摘要字面量必须写满
            # 规范长度，缩写成人类可读的占位词会被 single-track T1 判为非规范
            # 摘要残留——注释里也不能出现，门禁是按行扫源码的。
            current = module.TreeSnapshot(
                name="scripts",
                digest="sha256:" + "c" * 64,
                file_count=2,
                line_count=4,
                files={"kept.py": "aa", "added.py": "bb"},
            )
            drift = module._tree_drift(
                {"files": {"kept.py": "zz", "removed.py": "cc"}}, current
            )
            self.assertEqual(
                drift,
                [
                    "added scripts/added.py",
                    "removed scripts/removed.py",
                    "modified scripts/kept.py",
                ],
            )


if __name__ == "__main__":
    unittest.main()
