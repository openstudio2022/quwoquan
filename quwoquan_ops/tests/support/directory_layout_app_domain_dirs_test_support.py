"""app domain 目录名册派生契约套件的共享常量、加载器与 helper 基类。

由 1000 行硬顶拆分自
quwoquan_ops/tests/local_contract/gate/test_directory_layout__app_domain_dirs_from_roster__local_contract_test.py，
供 gate concern 下 from_roster / verify_app_behavior 两个拆分套件共用；
常量与方法体逐字保留原实现（REPO_ROOT 深度已按 support 目录位置调整）。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[3]
VERIFIER_PATH = REPO_ROOT / "quwoquan_ops/gate/scaffold/verify_test_directory_layout.py"
# 端侧目录常量的实现单轨在包内 constants 模块；ast 源码断言指向该模块而非薄入口。
VERIFIER_CONSTANTS_PATH = (
    REPO_ROOT / "quwoquan_ops/gate/scaffold/test_directory_layout/constants.py"
)
CONTRACT_GRAPH_PATH = REPO_ROOT / "quwoquan_service/generated/contract_graph.json"
GATE_REPO_PATH = REPO_ROOT / "quwoquan_ops/gate/gate_repo.sh"
MAKEFILE_PATH = REPO_ROOT / "Makefile"


def _load_verifier():
    scaffold_dir = str(VERIFIER_PATH.parent)
    if scaffold_dir not in sys.path:
        sys.path.insert(0, scaffold_dir)
    spec = importlib.util.spec_from_file_location(
        "verify_test_directory_layout_for_roster_contract_test",
        VERIFIER_PATH,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _contract_graph_objects() -> set[tuple[str, str, str]]:
    """独立于门禁再读一次名册，避免用被测代码证明被测代码。"""
    graph = json.loads(CONTRACT_GRAPH_PATH.read_text(encoding="utf-8"))
    objects: set[tuple[str, str, str]] = set()
    for entry in graph.get("objects") or []:
        source_path = str(entry.get("sourcePath") or "")
        parts = source_path.split("/")
        if len(parts) < 3:
            continue
        objects.add((str(entry.get("domain") or parts[0]), parts[1], parts[2]))
    return objects


class AppDomainTestDirsFromRosterCaseBase(unittest.TestCase):
    """共享 setUp 与构造 helper；不含 test_ 方法，不会被收集为用例。"""

    def setUp(self) -> None:
        self.verifier = _load_verifier()
        self.objects = _contract_graph_objects()
        self.domains = {domain for domain, _context, _object in self.objects}
        self.assertTrue(self.domains, "ContractGraph roster 为空，测试前提不成立")

    def _owner_parts(
        self, domain: str, context: str, object_name: str
    ) -> tuple[str, str, str, str]:
        service = self.verifier.opm.app_service_for_context(domain, context)
        return ("service", service, context, object_name)

    def _verify_app(
        self,
        build,
        *,
        allowances: dict[str, set[str]] | None = None,
    ) -> list[str]:
        verifier = self.verifier
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app_test_root = root / "quwoquan_app/test"
            (app_test_root / "support").mkdir(parents=True)
            for layer in ("local_contract", "api_integration", "user_acceptance"):
                (app_test_root / layer).mkdir()
            build(app_test_root)
            previous_root = verifier.ROOT
            previous_app_root = verifier.APP_ROOT
            previous_app_packages_root = verifier.APP_PACKAGES_ROOT
            previous_allowances = verifier.APP_UNMIGRATED_LAYER_DIRS
            verifier.ROOT = root
            verifier.APP_ROOT = app_test_root
            verifier.APP_PACKAGES_ROOT = root / "quwoquan_app/packages"
            verifier.APP_UNMIGRATED_LAYER_DIRS = {
                layer: set(names) for layer, names in (allowances or {}).items()
            }
            try:
                failures = verifier.Failures()
                verifier.verify_app(failures)
                return failures.items
            finally:
                verifier.ROOT = previous_root
                verifier.APP_ROOT = previous_app_root
                verifier.APP_PACKAGES_ROOT = previous_app_packages_root
                verifier.APP_UNMIGRATED_LAYER_DIRS = previous_allowances

