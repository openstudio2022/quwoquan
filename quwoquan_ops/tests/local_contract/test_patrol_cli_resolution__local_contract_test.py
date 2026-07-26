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

from quwoquan_ops.cli.lib.patrol_cli import (
    INSTALL_HINT,
    REQUIRED_PATROL_CLI_VERSION,
    resolve_patrol_cli,
)
from quwoquan_ops.cli.smoke import run_environment_patrol_smoke as env_patrol


INCOMPATIBLE_PATROL_CLI_VERSION = "4.5.1"


def _make_executable(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "#!/usr/bin/env sh\n"
        f"echo 'patrol_cli v{REQUIRED_PATROL_CLI_VERSION}'\n",
        encoding="utf-8",
    )
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
        self.assertEqual(result.version, REQUIRED_PATROL_CLI_VERSION)

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

    def test_incompatible_patrol_cli_is_a_gate_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            patrol = root / "pub-cache" / "bin" / "patrol"
            patrol.parent.mkdir(parents=True, exist_ok=True)
            patrol.write_text(
                "#!/usr/bin/env sh\n"
                f"echo 'patrol_cli v{INCOMPATIBLE_PATROL_CLI_VERSION}'\n",
                encoding="utf-8",
            )
            patrol.chmod(patrol.stat().st_mode | stat.S_IXUSR)

            result = resolve_patrol_cli(
                {
                    "PATH": str(root / "empty-bin"),
                    "PUB_CACHE": str(root / "pub-cache"),
                    "HOME": str(root / "home"),
                }
            )

        self.assertIsNone(result.executable)
        self.assertIn(REQUIRED_PATROL_CLI_VERSION, result.error)

    def test_invalid_explicit_patrol_cli_reports_gate_block_cause(self) -> None:
        result = resolve_patrol_cli({"PATROL_CLI": "/missing/patrol", "PATH": "", "HOME": "/tmp/no-home"})

        self.assertIsNone(result.executable)
        self.assertEqual(result.source, "PATROL_CLI")
        self.assertIn("PATROL_CLI", result.error)
        self.assertIn(INSTALL_HINT, result.error)

    def test_environment_smoke_command_uses_resolved_executable(self) -> None:
        args = SimpleNamespace(
            runtime_env="prod",
            api_contract_env="prod",
            data_source="remote",
            gateway_base_url="https://api.example.test",
            product_ops_base_url="https://ops.example.test",
            media_base_url="",
            media_avatar_base_url="https://avatar.example.test",
            media_image_base_url="https://media.example.test",
            media_video_base_url="https://video.example.test",
            media_upload_base_url="https://upload.example.test",
            rtc_media_connection_url="wss://rtc.example.test",
            test_auth_token="access-token",
            test_refresh_token="refresh-token",
            current_owner_id="owner-1",
            current_sub_account_id="persona-1",
            target="test/user_acceptance/patrol/environment/basic_viability__user_acceptance_test.dart",
            env_name="prod-sim",
        )

        command = env_patrol.patrol_command(
            {"id": "device-1"},
            args,
            "/tmp/patrol",
            dart_define_file=Path("/tmp/patrol-secrets.json"),
        )

        self.assertEqual(command[0], "/tmp/patrol")
        self.assertIn("--dart-define=APP_RUNTIME_ENV=prod", command)
        self.assertIn("--dart-define=APP_DATA_SOURCE=remote", command)
        self.assertIn(
            "--dart-define-from-file=/tmp/patrol-secrets.json",
            command,
        )
        self.assertNotIn("access-token", "\n".join(command))
        self.assertNotIn("refresh-token", "\n".join(command))
        self.assertNotIn("owner-1", "\n".join(command))
        self.assertNotIn("persona-1", "\n".join(command))

if __name__ == "__main__":
    unittest.main()
