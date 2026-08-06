"""生成物路径纯度维度的合约：受版本控制的生成物不得嵌入 `.qwq_output` 路径。

四向断言，两个正向两个边界：
- 负例：git 跟踪的 `generated/` 文件里出现 `.qwq_output/` 必须被抓到
- 正例：去掉该路径后必须转绿
- 边界一：未被 git 跟踪的 `generated/` 文件不算生成物，不得误伤
- 边界二：`generated/` 之外的源文件引用 `.qwq_output/` 是合法的（Makefile 与脚本
  本来就要往那里写），不得误伤

用合成 git 树驱动真实 verifier，而不是在测试里另建一份路径判定。
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VERIFIER_PATH = ROOT / "quwoquan_ops/gate/verify_output_path_source_contract.py"

POLLUTED_ARTIFACT = textwrap.dedent(
    """
    {
      "sources": [
        {"path": ".qwq_output/travel-service-materialized/contracts/domain.yaml"}
      ]
    }
    """
).strip()

CLEAN_ARTIFACT = textwrap.dedent(
    """
    {
      "sources": [
        {"path": "quwoquan_service/services/user-service/contracts/domain.yaml"}
      ]
    }
    """
).strip()


def _load_verifier():
    spec = importlib.util.spec_from_file_location("verify_output_path_source_contract", VERIFIER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


class GeneratedArtifactPathPurityContract(unittest.TestCase):
    def setUp(self) -> None:
        self.module = _load_verifier()
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _git(self.root, "init", "-q")
        _git(self.root, "config", "user.email", "contract@test.local")
        _git(self.root, "config", "user.name", "contract test")
        self.artifact = self.root / "quwoquan_service" / "generated" / "contract_graph.json"
        self.artifact.parent.mkdir(parents=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _issues(self) -> list[str]:
        return self.module.generated_artifact_issues(self.root)

    def _track(self, path: Path) -> None:
        _git(self.root, "add", str(path.relative_to(self.root)))

    def test_tracked_generated_artifact_embedding_ephemeral_path_is_blocked(self) -> None:
        self.artifact.write_text(POLLUTED_ARTIFACT, encoding="utf-8")
        self._track(self.artifact)
        issues = self._issues()
        self.assertTrue(issues, "生成物嵌入 .qwq_output 路径必须被抓到")
        self.assertIn("quwoquan_service/generated/contract_graph.json", issues[0])

    def test_clean_generated_artifact_passes(self) -> None:
        self.artifact.write_text(CLEAN_ARTIFACT, encoding="utf-8")
        self._track(self.artifact)
        self.assertEqual([], self._issues())

    def test_untracked_generated_file_is_not_an_artifact(self) -> None:
        self.artifact.write_text(POLLUTED_ARTIFACT, encoding="utf-8")
        self.assertEqual([], self._issues(), "未被 git 跟踪的产物不在本维度内")

    def test_source_file_outside_generated_may_reference_output_root(self) -> None:
        # 用与生成物同后缀的源文件，确保被排除的原因是「不在 generated/ 下」
        # 而不是后缀过滤顺手挡掉。
        source = self.root / "quwoquan_service" / "scripts" / "build_view.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(
            'CONTRACT_VIEW = ".qwq_output/env/repo/local/service-contract-view"\n',
            encoding="utf-8",
        )
        self._track(source)
        self.assertEqual([], self._issues(), "源文件引用输出根是合法的，不得误伤")


if __name__ == "__main__":
    unittest.main()
