"""canonical storage view 必须区分 go 工具链噪声与被调用程序的真实诊断。

`go run` 在 module cache 未预热时把下载进度写到 stderr。把这些行当违规会让
首次运行、新克隆与冷 CI 产出假失败，从而污染所有消费该视图的门禁基线。
"""

from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

from quwoquan_ops.cli.lib import storage_contract_view


ROOT = Path(__file__).resolve().parents[4]
STORAGE_PATH = (
    ROOT
    / "quwoquan_service"
    / "services"
    / "content-service"
    / "contracts"
    / "content"
    / "post"
    / "storage.yaml"
)


def _runner(stdout: str, stderr: str, returncode: int = 0):
    def run(*_args, **_kwargs) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=("go", "run"), returncode=returncode, stdout=stdout, stderr=stderr
        )

    return run


class StorageContractViewStderrLocalContractTest(unittest.TestCase):
    def test_the_probe_input_exists(self) -> None:
        self.assertTrue(STORAGE_PATH.is_file(), STORAGE_PATH)

    def test_toolchain_progress_lines_are_not_program_diagnostics(self) -> None:
        self.assertEqual(
            storage_contract_view._program_diagnostics(
                "go: downloading gopkg.in/yaml.v3 v3.0.1\n"
                "go: extracting gopkg.in/yaml.v3 v3.0.1\n"
            ),
            "",
        )

    def test_real_diagnostics_survive_the_toolchain_filter(self) -> None:
        self.assertEqual(
            storage_contract_view._program_diagnostics(
                "go: downloading gopkg.in/yaml.v3 v3.0.1\n"
                "storage.yaml: unknown backend\n"
            ),
            "storage.yaml: unknown backend",
        )

    def test_cold_module_cache_does_not_fail_a_healthy_view(self) -> None:
        document = storage_contract_view.load_storage_contract_view(
            STORAGE_PATH,
            runner=_runner(
                json.dumps({"backend": "mongodb", "role": "primary"}),
                "go: downloading gopkg.in/yaml.v3 v3.0.1\n",
            ),
        )
        self.assertEqual(document["backend"], "mongodb")

    def test_program_stderr_still_fails_closed(self) -> None:
        with self.assertRaisesRegex(
            storage_contract_view.StorageContractViewError, "unknown backend"
        ):
            storage_contract_view.load_storage_contract_view(
                STORAGE_PATH,
                runner=_runner(
                    json.dumps({"backend": "mongodb", "role": "primary"}),
                    "go: downloading gopkg.in/yaml.v3 v3.0.1\n"
                    "storage.yaml: unknown backend\n",
                ),
            )

    def test_nonzero_exit_keeps_the_full_stderr_for_diagnosis(self) -> None:
        with self.assertRaisesRegex(
            storage_contract_view.StorageContractViewError, "exited 2"
        ):
            storage_contract_view.load_storage_contract_view(
                STORAGE_PATH,
                runner=_runner("", "go: downloading x\n", returncode=2),
            )


if __name__ == "__main__":
    unittest.main()
