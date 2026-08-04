from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from quwoquan_ops.cli.lib import provider_config
from quwoquan_ops.cli.lib.external_provider_governance import load_and_compile


class ProviderConfigSecurityContractTest(unittest.TestCase):
    def test_render_uses_external_capability_bundles_and_redacts_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            work_root = Path(temporary) / "deploy"
            material = self._alpha_material()
            secret_marker = "super-secret-provider-material"
            for key in list(material):
                material[key] = f"{secret_marker}-{key}"
            with mock.patch.dict(
                os.environ,
                {"QWQ_DEPLOY_WORK_ROOT": str(work_root)},
                clear=False,
            ):
                provider_config.project_provider_secret_bundles(
                    environment="alpha",
                    target="alpha-local",
                    source=material,
                )
                result = provider_config.compile_provider_config(
                    action="render",
                    environment="alpha",
                    target="alpha-local",
                )
                self.assertEqual(result["exitCode"], 0, result)
                self.assertNotIn(secret_marker, json.dumps(result, sort_keys=True))
                rendered = (
                    work_root
                    / "alpha-local"
                    / "provider-config"
                    / "material.json"
                )
                self.assertTrue(rendered.is_file())
                self.assertEqual(rendered.stat().st_mode & 0o077, 0)
                self.assertIn(secret_marker, rendered.read_text(encoding="utf-8"))
                diff = provider_config.compile_provider_config(
                    action="diff",
                    environment="alpha",
                    target="alpha-local",
                )
                self.assertEqual(diff["exitCode"], 0, diff)
                self.assertFalse(diff["changed"])

    def test_validate_reports_only_qualified_missing_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with mock.patch.dict(
                os.environ,
                {"QWQ_DEPLOY_WORK_ROOT": str(Path(temporary) / "deploy")},
                clear=False,
            ):
                result = provider_config.compile_provider_config(
                    action="validate",
                    environment="alpha",
                    target="alpha-local",
                )
            self.assertEqual(result["exitCode"], 2, result)
            self.assertTrue(result["missingKeys"])
            serialized = json.dumps(result, sort_keys=True)
            self.assertNotIn("endpoint=", serialized)
            self.assertNotIn("token=", serialized)

    def test_target_environment_mismatch_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "mismatch"):
            provider_config.compile_provider_config(
                action="validate",
                environment="alpha",
                target="beta-local",
            )

    @staticmethod
    def _alpha_material() -> dict[str, str]:
        values: dict[str, str] = {}
        compiled, issues = load_and_compile()
        if issues:
            raise AssertionError([issue.render() for issue in issues])
        for binding in compiled["selectedBindings"]["alpha"].values():
            for field in ("endpoint_envs", "secret_refs"):
                material = binding.get(field) or {}
                keys = material.values() if isinstance(material, dict) else material
                for key in keys:
                    values[str(key)] = "placeholder"
        return values


if __name__ == "__main__":
    unittest.main()
