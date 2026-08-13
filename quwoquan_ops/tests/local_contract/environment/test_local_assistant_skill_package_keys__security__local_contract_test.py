from __future__ import annotations

import base64
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli.lib.local_assistant_skill_package_keys import (
    KEY_ID,
    prepare_local_assistant_skill_package_keys,
)
from quwoquan_ops.cli.lib import local_assistant_skill_package_publication as publication


ROOT = Path(__file__).resolve().parents[4]


class LocalAssistantSkillPackageKeysSecurityTest(unittest.TestCase):
    def test_local_managed_publisher_cannot_target_prod_or_candidate(self) -> None:
        with self.assertRaisesRegex(ValueError, "limited to Alpha/Beta/Gamma"):
            prepare_local_assistant_skill_package_keys("prod", "prod-hosted")
        self.assertEqual(publication.TARGET, "alpha-local")
        self.assertEqual(publication.ENVIRONMENT, "alpha")
        self.assertIn("local-managed", publication.PUBLISHER)
        source = (
            ROOT
            / "quwoquan_ops/cli/lib/local_assistant_skill_package_publication.py"
        ).read_text(encoding="utf-8")
        self.assertIn('"nonPromotable": True', source)
        self.assertIn('"promotionEligibility": "GATE_BLOCK"', source)
        self.assertIn('"immutableCandidateAuthority": False', source)
        self.assertIn('"prodAuthority": False', source)

    def test_prepare_issues_valid_json_and_reuses_material(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            deploy_root = Path(temporary) / "deploy"
            with mock.patch.dict(
                os.environ,
                {"QWQ_DEPLOY_WORK_ROOT": str(deploy_root)},
                clear=False,
            ):
                material = prepare_local_assistant_skill_package_keys(
                    "gamma",
                    "gamma-local",
                )
                reused = prepare_local_assistant_skill_package_keys(
                    "gamma",
                    "gamma-local",
                )

            self.assertEqual(material.environment, reused.environment)
            raw = material.environment[
                "ASSISTANT_SKILL_PACKAGE_TRUSTED_PUBLIC_KEYS_JSON"
            ]
            self.assertTrue(raw)
            payload = json.loads(raw)
            self.assertIn(KEY_ID, payload)
            decoded = base64.b64decode(payload[KEY_ID], validate=True)
            self.assertEqual(len(decoded), 32)
            self.assertTrue(material.private_key_path.is_file())
            self.assertEqual(
                stat.S_IMODE(material.private_key_path.stat().st_mode),
                0o600,
            )
            self.assertNotIn(".qwq_output", str(material.private_key_path))
            self.assertIn(
                "/secrets/assistant-skill-package/",
                str(material.private_key_path),
            )

            # Empty public JSON must never be accepted as ready material.
            public_path = (
                material.private_key_path.parent / "trusted_public_keys.json"
            )
            public_path.write_text("{}", encoding="utf-8")
            public_path.chmod(0o600)
            with mock.patch.dict(
                os.environ,
                {"QWQ_DEPLOY_WORK_ROOT": str(deploy_root)},
                clear=False,
            ):
                repaired = prepare_local_assistant_skill_package_keys(
                    "gamma",
                    "gamma-local",
                )
            repaired_payload = json.loads(
                repaired.environment[
                    "ASSISTANT_SKILL_PACKAGE_TRUSTED_PUBLIC_KEYS_JSON"
                ]
            )
            self.assertIn(KEY_ID, repaired_payload)
            self.assertEqual(
                len(base64.b64decode(repaired_payload[KEY_ID], validate=True)),
                32,
            )

    def test_assistant_compose_requires_trusted_keys_json(self) -> None:
        compose = (
            ROOT
            / "quwoquan_service/services/assistant-service/deploy/compose.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "ASSISTANT_SKILL_PACKAGE_TRUSTED_PUBLIC_KEYS_JSON:?ASSISTANT_SKILL_PACKAGE_TRUSTED_PUBLIC_KEYS_JSON is required}",
            compose,
        )

    def test_stackctl_binds_skill_keys_for_full_workload(self) -> None:
        stackctl = (
            ROOT / "quwoquan_ops/cli/commands/gamma_release_binding.py"
        ).read_text(encoding="utf-8")
        self.assertIn("prepare_local_assistant_skill_package_keys", stackctl)
        bind_fn = stackctl.split(
            "def _bind_formal_local_release_provider_environment(",
            1,
        )[1]
        skill_index = bind_fn.index(
            "prepare_local_assistant_skill_package_keys"
        )
        content_return_index = bind_fn.index(
            'workload in {"content-release", "content-commercial"}'
        )
        self.assertLess(skill_index, content_return_index)
        self.assertIn('if workload == "full":', bind_fn[:content_return_index])

    def test_stackctl_down_parse_environment_includes_skill_keys(self) -> None:
        stackctl = (
            ROOT / "quwoquan_ops/cli/commands/gamma_release_binding.py"
        ).read_text(encoding="utf-8")
        down_fn = stackctl.split(
            "def _bind_gamma_down_parse_environment(",
            1,
        )[1]
        self.assertIn(
            "ASSISTANT_SKILL_PACKAGE_TRUSTED_PUBLIC_KEYS_JSON",
            down_fn.split("def ", 1)[0],
        )

    def test_secret_material_is_not_committed(self) -> None:
        tracked = list(
            (ROOT / "quwoquan_ops").rglob("trusted_public_keys.json")
        ) + list((ROOT / "quwoquan_ops").rglob("assistant-skill-package/**"))
        self.assertEqual(tracked, [])


if __name__ == "__main__":
    unittest.main()
