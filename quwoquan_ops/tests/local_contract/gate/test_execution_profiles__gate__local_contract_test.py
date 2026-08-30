"""local_contract: 退役 tier/gate 入口与 prod-gray 环境别名门禁的正负例。"""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
MODULE_PATH = ROOT / "quwoquan_ops/gate/verify_execution_profiles.py"

#: 退役字面量一律拼接构造，理由与门禁自身一致：这份夹具不应该成为下一次
#: 全仓退役词扫描的命中点，否则「测试里写了退役名」会被当成真实回归。
PROD_GRAY_ENV_FLAG = "--env-name " + "prod-" + "gray"
PROD_GRAY_SMOKE_TARGET = "environment-smoke-" + "prod-" + "gray"

CLEAN_MAKEFILE = """\
.PHONY: environment-smoke-prod
environment-smoke-prod:
\tpython3 quwoquan_ops/cli/stackctl.py verify --env prod --profile smoke
"""
CLEAN_GUIDE = "生产灰度是 prod 的 rollout stage，不是独立环境。\n"


def _load_module():
    spec = importlib.util.spec_from_file_location("verify_execution_profiles", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _run_against(module, files: dict[str, str]) -> int:
    """把门禁的扫描面整体重指向一棵合成树。

    门禁只有 `main()`，判据全部绑在模块级 `ACTIVE_PATHS` 上；`ROOT` 必须一起改写，
    否则 `path.relative_to(ROOT)` 会在报错路径上先抛 ValueError，正例反而看不出
    门禁是不是真的判到了。
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        active: list[Path] = []
        for relative, text in files.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            active.append(path)
        module.ROOT = root
        module.ACTIVE_PATHS = tuple(active)
        return module.main()


class ExecutionProfilesGateTest(unittest.TestCase):
    def test_clean_active_paths_are_accepted(self) -> None:
        module = _load_module()
        self.assertEqual(
            _run_against(
                module,
                {"Makefile": CLEAN_MAKEFILE, "AGENTS.md": CLEAN_GUIDE},
            ),
            0,
        )

    def test_retired_token_set_is_the_pinned_pair(self) -> None:
        """判据是封闭的两条退役入口；名单被悄悄清空时门禁会静默恒绿。"""
        module = _load_module()
        self.assertEqual(
            set(module.RETIRED_TOKENS),
            {"gate" + "-full", "--" + "tier"},
        )

    def test_every_retired_entrypoint_token_is_rejected(self) -> None:
        module = _load_module()
        tokens = tuple(module.RETIRED_TOKENS)
        self.assertTrue(tokens)
        for token in tokens:
            recipe = f".PHONY: check\ncheck:\n\tmake {token}\n"
            self.assertEqual(
                _run_against(module, {"Makefile": recipe, "AGENTS.md": CLEAN_GUIDE}),
                1,
                msg=token,
            )

    def test_retired_token_is_rejected_outside_the_makefile(self) -> None:
        """退役入口是全 ACTIVE_PATHS 判据：文档里留一条可复制的命令同样会被跟着用。"""
        module = _load_module()
        token = module.RETIRED_TOKENS[0]
        self.assertEqual(
            _run_against(
                module,
                {
                    "Makefile": CLEAN_MAKEFILE,
                    "AGENTS.md": f"收口命令：`make {token}`。\n",
                },
            ),
            1,
        )

    def test_prod_gray_environment_flag_is_rejected(self) -> None:
        module = _load_module()
        recipe = (
            ".PHONY: uat-prod\nuat-prod:\n"
            f"\tpython3 quwoquan_ops/cli/stackctl.py verify {PROD_GRAY_ENV_FLAG}\n"
        )
        self.assertEqual(
            _run_against(module, {"Makefile": recipe, "AGENTS.md": CLEAN_GUIDE}),
            1,
        )

    def test_prod_gray_smoke_target_is_rejected(self) -> None:
        module = _load_module()
        recipe = f".PHONY: {PROD_GRAY_SMOKE_TARGET}\n{PROD_GRAY_SMOKE_TARGET}:\n\t@true\n"
        self.assertEqual(
            _run_against(module, {"Makefile": recipe, "AGENTS.md": CLEAN_GUIDE}),
            1,
        )

    def test_prod_gray_prose_outside_the_makefile_is_accepted(self) -> None:
        """判据被刻意收在 Makefile：真正会被执行的是 target，散文里解释退役由来必须允许。

        判据一旦扩散到全部 ACTIVE_PATHS，任何一份说明「不存在 prod-gray」的规格
        都会把自己判红，最后只能靠删说明来消红。
        """
        module = _load_module()
        self.assertEqual(
            _run_against(
                module,
                {
                    "Makefile": CLEAN_MAKEFILE,
                    "AGENTS.md": f"不存在 {PROD_GRAY_SMOKE_TARGET}，生产灰度只是 rollout stage。\n",
                },
            ),
            0,
        )

    def test_prod_gray_patterns_require_the_governed_flag_shape(self) -> None:
        """`--env-name prod-gray` 是命令行形态判定，不是裸词匹配。"""
        module = _load_module()
        flag_pattern, target_pattern = module.RETIRED_PROD_ENVIRONMENT_PATTERNS
        self.assertIsNotNone(flag_pattern.search(f"stackctl verify {PROD_GRAY_ENV_FLAG}"))
        self.assertIsNone(flag_pattern.search("stackctl verify --env prod"))
        self.assertIsNotNone(target_pattern.search(f"make {PROD_GRAY_SMOKE_TARGET}"))
        self.assertIsNone(target_pattern.search("make environment-smoke-prod"))

    def test_real_active_paths_are_present_repository_files(self) -> None:
        """扫描面必须逐条命中真实文件；文件被搬走时门禁应当立刻暴露，而不是扫描空集。"""
        module = _load_module()
        self.assertEqual(module.ROOT, ROOT)
        missing = [
            path.as_posix()
            for path in module.ACTIVE_PATHS
            if not path.is_file()
        ]
        self.assertEqual(missing, [])

    def test_real_repository_execution_profiles_hold(self) -> None:
        module = _load_module()
        self.assertEqual(module.main(), 0)


if __name__ == "__main__":
    unittest.main()
