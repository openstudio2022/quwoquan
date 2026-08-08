#!/usr/bin/env python3
"""端侧内聚度棘轮门禁的 local_contract。

棘轮门禁最危险的失效方式不是「漏报一条违规」，而是**在输入不可信时假装通过**：
扫描根写错、目录被搬空、glob 失配时如果返回 0 违规，棘轮就永久失效且没人发现。
本套件因此把负例放在第一位：

- 扫描根不存在 → 必须 FAIL（非 0 退出），不得当成 0 违规。
- 扫描到 0 个 App 对象 → 必须 FAIL，同上。
- 任一指标超过棘轮上限 → 必须 FAIL。
- 真实仓库当前状态 → 必须 PASS（证明基线是实测值而不是随手写的数字）。
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT_PATH = (
    REPO_ROOT
    / "quwoquan_app"
    / "scripts"
    / "runtime"
    / "architecture"
    / "verify_app_cohesion_ratchet.py"
)


def load_verifier():
    spec = importlib.util.spec_from_file_location(
        "verify_app_cohesion_ratchet", SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # `@dataclass` 解析注解时要回查 sys.modules[cls.__module__]，动态加载必须先注册。
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_object(app_root: Path, object_id: str, layers: dict[str, int]) -> None:
    """在 fixture app root 下造出一个 App 对象的物理形状。"""
    for layer, count in layers.items():
        if count == 0:
            continue
        layer_dir = app_root / "lib" / "service" / object_id / layer
        layer_dir.mkdir(parents=True, exist_ok=True)
        for index in range(count):
            (layer_dir / f"file_{index}.dart").write_text("// fixture\n", encoding="utf-8")


class VerifyAppCohesionRatchetNegativeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.verifier = load_verifier()

    def test_missing_app_root_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            absent = Path(directory) / "no-such-app"
            exit_code = self.verifier.main(["--app-root", str(absent)])
        self.assertEqual(exit_code, 1, "扫描根不存在必须 FAIL，不得当成 0 违规")

    def test_missing_service_root_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            app_root = Path(directory) / "app"
            (app_root / "lib").mkdir(parents=True)
            exit_code = self.verifier.main(["--app-root", str(app_root)])
        self.assertEqual(exit_code, 1, "缺少 lib/service 必须 FAIL")

    def test_zero_scanned_objects_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            app_root = Path(directory) / "app"
            # service 根存在但没有任何对象：典型的「搬迁搬空 / glob 失配」形态。
            (app_root / "lib" / "service").mkdir(parents=True)
            exit_code = self.verifier.main(["--app-root", str(app_root)])
        self.assertEqual(exit_code, 1, "扫描对象数为 0 必须 FAIL，不得当成 0 违规")

    def test_context_only_directories_do_not_count_as_objects(self) -> None:
        """只有 context 级空目录（四层全空）时仍视为 0 个对象 → FAIL。"""
        with tempfile.TemporaryDirectory() as directory:
            app_root = Path(directory) / "app"
            (app_root / "lib" / "service" / "foo_service" / "ctx" / "obj").mkdir(
                parents=True
            )
            exit_code = self.verifier.main(["--app-root", str(app_root)])
        self.assertEqual(exit_code, 1)

    def test_exceeding_ceiling_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            app_root = Path(directory) / "app"
            ceiling = self.verifier.RATCHET_CEILINGS[
                "objects_presentation_without_domain"
            ]
            # 造出比棘轮上限多一个的「presentation 有、domain 无」对象。
            for index in range(ceiling + 1):
                _write_object(
                    app_root,
                    f"foo_service/ctx/object_{index}",
                    {"application": 1, "adapters": 1, "presentation": 1},
                )
            exit_code = self.verifier.main(["--app-root", str(app_root)])
        self.assertEqual(exit_code, 1, "超过棘轮上限必须 FAIL")

    def test_within_ceiling_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            app_root = Path(directory) / "app"
            _write_object(
                app_root,
                "foo_service/ctx/fully_layered",
                {"domain": 1, "application": 1, "adapters": 1, "presentation": 1},
            )
            exit_code = self.verifier.main(["--app-root", str(app_root)])
        self.assertEqual(exit_code, 0, "四层齐备的对象不应触发棘轮")


class VerifyAppCohesionRatchetBaselineTest(unittest.TestCase):
    """基线必须是实测值：真实仓库当前状态必须刚好通过。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.verifier = load_verifier()
        cls.report = cls.verifier.build_report(REPO_ROOT / "quwoquan_app")

    def test_repository_state_passes_ratchet(self) -> None:
        self.assertEqual(self.verifier.evaluate(self.report), [])

    def test_every_ceiling_has_a_measured_metric(self) -> None:
        self.assertEqual(
            sorted(self.verifier.RATCHET_CEILINGS),
            sorted(self.report.metrics),
            "棘轮上限与实测指标必须一一对应，不允许存在无人测量的上限",
        )

    def test_ceilings_are_not_slack(self) -> None:
        """上限不得远高于实测值，否则棘轮形同虚设。"""
        for metric, ceiling in self.verifier.RATCHET_CEILINGS.items():
            actual = self.report.metrics[metric]
            self.assertLessEqual(actual, ceiling)
            self.assertEqual(
                actual,
                ceiling,
                f"{metric} 上限 {ceiling} 高于实测 {actual}，请把上限收到实测值",
            )


if __name__ == "__main__":
    unittest.main()
