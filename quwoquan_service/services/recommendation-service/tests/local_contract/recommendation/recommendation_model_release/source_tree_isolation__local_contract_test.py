"""recommendation-service 测试树不得把可重建产物写回源码树。

根 AGENTS.md：`.qwq_output/` 只存可删除、可重建的运行输出；源码树不得保留
`__pycache__/`、`*.pyc`、`*.pyo`、`.pytest_cache/`，缓存必须重定向到
`.qwq_output/env/repo/local/**`。

本套件用真实的污染路径取证：执行本服务测试树使用的 importlib 加载器、回读源码树，
并检查 session 级字节码出口与 pytest / 运行期配置的落点。任何一处退回源码树都会让
这里变红，从而阻断「recommendation-service 单跑绿、与 Ops 架构治理测试串跑必红」
的顺序依赖回归。

spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-003
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tomllib
import unittest
from pathlib import Path

from support.path_setup import recommendation_service_root


SERVICE_ROOT = recommendation_service_root()
REPO_ROOT = SERVICE_ROOT.parents[2]
SERVICE_SCRIPTS_ROOT = (
    REPO_ROOT / "quwoquan_service" / "scripts" / "recommendation-service"
)
CANONICAL_OUTPUT_PREFIX = REPO_ROOT / ".qwq_output" / "env" / "repo" / "local"

FORBIDDEN_DIRECTORIES = ("__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache")
FORBIDDEN_SUFFIXES = (".pyc", ".pyo")


def rebuildable_artifacts_in(*roots: Path) -> set[str]:
    found: set[str] = set()
    for root in roots:
        for path in root.rglob("*"):
            if path.is_dir() and path.name in FORBIDDEN_DIRECTORIES:
                found.add(str(path.relative_to(REPO_ROOT)))
            elif path.is_file() and path.suffix in FORBIDDEN_SUFFIXES:
                found.add(str(path.relative_to(REPO_ROOT)))
    return found


def load_module_without_bytecode(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


class SourceTreeIsolationTest(unittest.TestCase):
    def test_module_loaders_used_by_this_suite_write_no_bytecode(self) -> None:
        subjects = {
            "isolation_probe_intersection_kind_registry": SERVICE_SCRIPTS_ROOT
            / "recommendation"
            / "recommendation_model_release"
            / "verify_intersection_kind_registry.py",
            "isolation_probe_feature_consistency": SERVICE_ROOT
            / "internal"
            / "recommendation"
            / "recommendation_model_release"
            / "infrastructure"
            / "model_runtime"
            / "scripts"
            / "verify_feature_consistency.py",
        }
        before = rebuildable_artifacts_in(SERVICE_ROOT, SERVICE_SCRIPTS_ROOT)
        for name, path in subjects.items():
            self.assertTrue(path.is_file(), f"loader subject is missing: {path}")
            load_module_without_bytecode(name, path)
        after = rebuildable_artifacts_in(SERVICE_ROOT, SERVICE_SCRIPTS_ROOT)

        self.assertEqual(
            sorted(after - before),
            [],
            "recommendation-service test loaders wrote rebuildable artifacts back "
            "into the source tree",
        )

    def test_bytecode_is_redirected_before_any_subject_package_is_imported(
        self,
    ) -> None:
        # 本服务的测试通过 pyproject.toml 的 pythonpath import 自己的
        # generated/**、internal/** 与 cmd/api。CPython 默认把 .pyc 写回这些源码
        # 目录，Ops 服务架构治理随后会把 generated/** 下的每个 .pyc 判成「缺少
        # generated output marker」——这就是「单跑绿、串跑红」的顺序依赖来源。
        # 服务架构契约只允许 tests/ 下存在 local_contract/api_integration/support，
        # 所以隔离靠 `-p support.bytecode_isolation`：它在任何被测包被 import 之前
        # 生效，因此不依赖调用方是否传了 -B / PYTHONDONTWRITEBYTECODE。
        configuration = tomllib.loads(
            (SERVICE_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )
        addopts = configuration["tool"]["pytest"]["ini_options"]["addopts"]
        self.assertIn("-p support.bytecode_isolation", addopts)

        prefix = Path(sys.pycache_prefix or "").resolve()
        self.assertTrue(
            prefix.is_relative_to(CANONICAL_OUTPUT_PREFIX),
            f"session bytecode prefix {prefix} escapes {CANONICAL_OUTPUT_PREFIX}",
        )

        for subject_tree in ("generated", "internal", "cmd"):
            self.assertEqual(
                sorted(rebuildable_artifacts_in(SERVICE_ROOT / subject_tree)),
                [],
                f"{subject_tree}/ retains interpreter cache written by this suite",
            )

    def test_pytest_cache_is_redirected_to_the_canonical_output_root(self) -> None:
        configuration = tomllib.loads(
            (SERVICE_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )
        cache_dir = configuration["tool"]["pytest"]["ini_options"]["cache_dir"]
        resolved = (SERVICE_ROOT / cache_dir).resolve()

        self.assertTrue(
            resolved.is_relative_to(CANONICAL_OUTPUT_PREFIX),
            f"pytest cache_dir {resolved} escapes {CANONICAL_OUTPUT_PREFIX}",
        )

    def test_service_identity_composition_writes_only_under_the_output_root(
        self,
    ) -> None:
        from support.service_token import configure_test_auth_environment

        configure_test_auth_environment()
        config_root = Path(os.environ["CONFIG_ROOT"]).resolve()

        self.assertTrue(
            config_root.is_relative_to(CANONICAL_OUTPUT_PREFIX),
            f"test runtime config root {config_root} escapes {CANONICAL_OUTPUT_PREFIX}",
        )
        self.assertFalse(
            config_root.is_relative_to(SERVICE_ROOT),
            "test runtime config must not be written into the service root",
        )


if __name__ == "__main__":
    unittest.main()
