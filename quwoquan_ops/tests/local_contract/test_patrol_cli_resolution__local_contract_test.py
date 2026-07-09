from __future__ import annotations

import stat
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan")
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from quwoquan_ops.cli.gamma import run_gamma_patrol_matrix_ci as gamma_patrol
from quwoquan_ops.cli.lib.patrol_cli import resolve_patrol_cli
from quwoquan_ops.cli.smoke import run_environment_patrol_smoke as env_patrol


def _make_executable(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/usr/bin/env sh\nexit 0\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class PatrolCliResolutionTest(unittest.TestCase):
    def test_resolves_pub_cache_when_path_omits_patrol(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            patrol = root / "pub-cache" / "bin" / "patrol"
            _make_executable(patrol)

            result = resolve_patrol_cli(
                {
                    "PATH": str(root / "empty-bin"),
                    "PUB_CACHE": str(root / "pub-cache"),
                    "HOME": str(root / "home"),
                }
            )

        self.assertEqual(result.executable, str(patrol))
        self.assertEqual(result.source, "PUB_CACHE")
        self.assertEqual(result.error, "")

    def test_resolves_home_pub_cache_when_pub_cache_env_is_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            patrol = root / "home" / ".pub-cache" / "bin" / "patrol"
            _make_executable(patrol)

            result = resolve_patrol_cli(
                {
                    "PATH": str(root / "empty-bin"),
                    "HOME": str(root / "home"),
                }
            )

        self.assertEqual(result.executable, str(patrol))
        self.assertEqual(result.source, "HOME_PUB_CACHE")

    def test_invalid_explicit_patrol_cli_reports_gate_block_cause(self) -> None:
        result = resolve_patrol_cli({"PATROL_CLI": "/missing/patrol", "PATH": "", "HOME": "/tmp/no-home"})

        self.assertIsNone(result.executable)
        self.assertEqual(result.source, "PATROL_CLI")
        self.assertIn("PATROL_CLI", result.error)
        self.assertIn("dart pub global activate patrol_cli", result.error)

    def test_environment_smoke_command_uses_resolved_executable(self) -> None:
        args = SimpleNamespace(
            runtime_env="prod",
            api_contract_env="prod",
            data_source="mock",
            gateway_base_url="https://api.example.test",
            product_ops_base_url="https://ops.example.test",
            media_base_url="https://media.example.test",
            test_auth_token="token",
            target="test/patrol/environment/basic_viability_test.dart",
            env_name="prod-sim",
        )

        command = env_patrol.patrol_command({"id": "device-1"}, args, "/tmp/patrol")

        self.assertEqual(command[0], "/tmp/patrol")
        self.assertIn("--dart-define=APP_RUNTIME_ENV=prod", command)
        self.assertIn("--dart-define=APP_DATA_SOURCE=mock", command)

    def test_gamma_matrix_command_uses_resolved_executable(self) -> None:
        args = SimpleNamespace(
            gateway_base_url="https://api.example.test",
            product_ops_base_url="https://ops.example.test",
            test_auth_token="token",
            target="test/patrol/discovery/feed_load_test.dart",
        )

        command = gamma_patrol.patrol_command({"id": "device-1"}, args, "/tmp/patrol")

        self.assertEqual(command[0], "/tmp/patrol")
        self.assertIn("--dart-define=APP_RUNTIME_ENV=gamma", command)
        self.assertIn("--dart-define=APP_DATA_SOURCE=remote", command)


if __name__ == "__main__":
    unittest.main()
