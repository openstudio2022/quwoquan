from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate import verify_media_delivery_contract as gate


class PublicFixtureSliceIdentityTest(unittest.TestCase):
    def validate_value(self, value: str, field_key: str = "objectKey") -> list[str]:
        issues: list[str] = []
        gate._validate_media_field_value(
            rel_path="fixture.json",
            field_key=field_key,
            value=value,
            manifest_keys=set(),
            force_mock_seed_ban=False,
            issues=issues,
            seen=set(),
        )
        return issues

    def test_path_versioned_query_free_public_slice_passes(self) -> None:
        self.assertEqual(
            self.validate_value(
                "media/image/s/archived-image/post/fixture/v1/cover.png"
            ),
            [],
        )

    def test_noncanonical_fixture_version_is_rejected(self) -> None:
        issues = self.validate_value(
            "media/image/s/archived-image/post/fixture/v2/cover.png"
        )
        self.assertTrue(any("唯一 canonical 版本" in issue for issue in issues))

    def test_unversioned_public_slice_is_rejected(self) -> None:
        issues = self.validate_value(
            "media/image/s/archived-image/post/fixture/cover.png"
        )
        self.assertTrue(any("恰有一个 /vN/" in issue for issue in issues))

    def test_redundant_query_version_is_rejected(self) -> None:
        issues = self.validate_value(
            "media/image/s/archived-image/post/fixture/v1/cover.png?v=1"
        )
        self.assertTrue(any("query-free" in issue for issue in issues))

    def test_multiple_path_version_segments_are_rejected(self) -> None:
        issues = self.validate_value(
            "media/image/s/v1/archived-image/post/fixture/v2/cover.png"
        )
        self.assertTrue(any("恰有一个 /vN/" in issue for issue in issues))

    def test_private_object_key_is_outside_public_slice_gate(self) -> None:
        issues: list[str] = []
        gate._walk_json_media_fields(
            {"objectKey": "media/objects/sha256/ab/abcdef/source.png"},
            rel_path="fixture.json",
            field_key=None,
            manifest_keys=set(),
            force_mock_seed_ban=False,
            issues=issues,
            seen=set(),
        )
        self.assertEqual(issues, [])

    def test_walker_checks_public_slice_inside_arbitrary_object_key_list(self) -> None:
        issues: list[str] = []
        gate._walk_json_media_fields(
            {"mediaObjectKeys": ["media/image/s/asset/fixture/cover.png"]},
            rel_path="fixture.json",
            field_key=None,
            manifest_keys=set(),
            force_mock_seed_ban=False,
            issues=issues,
            seen=set(),
        )
        self.assertTrue(any("恰有一个 /vN/" in issue for issue in issues))

    def test_record_version_and_source_hash_must_match_physical_slice(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            media_root = Path(temp_dir)
            path = media_root / "media/image/s/asset/fixture/v2/cover.png"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"fixture-v2")
            issues: list[str] = []
            with mock.patch.object(gate, "MEDIA_ROOT", media_root):
                gate._validate_public_slice_record(
                    {
                        "objectKey": "media/image/s/asset/fixture/v2/cover.png",
                        "version": 1,
                        "sourceHash": f"sha256:{hashlib.sha256(b'wrong').hexdigest()}",
                    },
                    rel_path="fixture.json",
                    issues=issues,
                    seen=set(),
                )
        self.assertTrue(any("路径 v2 不一致" in issue for issue in issues))
        self.assertTrue(any("实体摘要" in issue for issue in issues))

    def test_physical_fixture_gate_rejects_unversioned_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            media_root = Path(temp_dir)
            path = media_root / "media/avatar/s/asset/fixture/avatar.png"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"avatar")
            issues: list[str] = []
            with mock.patch.object(gate, "MEDIA_ROOT", media_root):
                gate._validate_fixture_public_slice_files(issues)
        self.assertEqual(len(issues), 1)
        self.assertIn("恰有一个 /vN/", issues[0])

    def test_physical_fixture_gate_rejects_mock_seed_namespace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            media_root = Path(temp_dir)
            path = media_root / "media/avatar/s/mock/seed/user-1/v1/avatar.jpg"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"avatar")
            issues: list[str] = []
            with mock.patch.object(gate, "MEDIA_ROOT", media_root):
                gate._validate_fixture_public_slice_files(issues)
        self.assertEqual(len(issues), 1)
        self.assertIn("禁止使用 mock/seed", issues[0])

    def test_fixture_scan_excludes_retired_user_pool_dump(self) -> None:
        paths = gate._fixture_media_scan_paths()
        self.assertFalse(
            any(
                "services/user-service/tests/support/contract_fixtures/user_pool.json"
                in path.as_posix()
                for path in paths
            )
        )

    def test_runtime_config_parity_uses_each_environment_target(self) -> None:
        topology = gate.load_environment_topology()

        def resolve_defines(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            env_name = command[command.index("--env") + 1]
            target_name = command[command.index("--target") + 1]
            self.assertEqual(
                target_name,
                gate.DEFAULT_DEPLOY_TARGET_BY_ENV[env_name],
            )
            self.assertEqual(
                command[command.index("--launch-policy") + 1],
                "test_live",
            )
            public_bases = topology["environments"][env_name]["publicBases"]
            defines = {
                define_key: public_bases[topology_field]
                for topology_field, define_key in gate.APP_RUNTIME_CONFIG_MEDIA_FIELDS.values()
            }
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(defines),
                stderr="",
            )

        issues: list[str] = []
        with mock.patch.dict(os.environ, {"QWQ_DEPLOY_TARGET": "alpha-local"}), mock.patch.object(
            gate.subprocess,
            "run",
            side_effect=resolve_defines,
        ):
            gate._validate_runtime_config_authority_parity(
                issues,
                ("alpha", "beta", "gamma"),
                launch_policy="test_live",
            )
        self.assertEqual(issues, [])

    def test_release_runtime_config_parity_keeps_prod_release_policy(self) -> None:
        topology = gate.load_environment_topology()

        def resolve_defines(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            self.assertEqual(
                command[command.index("--launch-policy") + 1],
                "prod_release",
            )
            env_name = command[command.index("--env") + 1]
            public_bases = topology["environments"][env_name]["publicBases"]
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(
                    {
                        define_key: public_bases[topology_field]
                        for topology_field, define_key in gate.APP_RUNTIME_CONFIG_MEDIA_FIELDS.values()
                    }
                ),
                stderr="",
            )

        issues: list[str] = []
        with mock.patch.object(gate.subprocess, "run", side_effect=resolve_defines):
            gate._validate_runtime_config_authority_parity(
                issues,
                ("prod",),
                launch_policy="prod_release",
            )
        self.assertEqual(issues, [])

if __name__ == "__main__":
    unittest.main()
