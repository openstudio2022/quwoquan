from __future__ import annotations

import argparse
import json
import os
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib import provider_config
from quwoquan_ops.cli.lib.external_provider_governance import load_and_compile
from quwoquan_ops.cli.lib.provider_runtime_composition import (
    compile_provider_runtime_composition,
)


class ProviderConfigSecurityContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        compiled, issues = load_and_compile()
        if issues:
            raise AssertionError([issue.render() for issue in issues])
        cls.alpha_composition = compile_provider_runtime_composition(
            environment="alpha",
            target="alpha-local",
            compiled=compiled,
        )

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
                    runtime_composition=self.alpha_composition,
                )
                result = provider_config.compile_provider_config(
                    action="render",
                    environment="alpha",
                    target="alpha-local",
                    runtime_composition=self.alpha_composition,
                )
                self.assertEqual(result["exitCode"], 0, result)
                for digest_field in (
                    "configurationDigest",
                    "bindingDigest",
                    "runtimeCompositionDigest",
                    "materialDigest",
                ):
                    self.assertRegex(
                        result[digest_field],
                        r"^sha256:[0-9a-f]{64}$",
                    )
                self.assertNotEqual(
                    result["configurationDigest"],
                    result["materialDigest"],
                )
                self.assertEqual(
                    {workload["role"] for workload in result["runtimeWorkloads"]},
                    {
                        "provider-protocol-substitute",
                        "sms-provider-substitute",
                    },
                )
                self.assertNotIn(secret_marker, json.dumps(result, sort_keys=True))
                rendered = (
                    work_root / "alpha-local" / "provider-config" / "material.json"
                )
                self.assertTrue(rendered.is_file())
                self.assertEqual(rendered.stat().st_mode & 0o077, 0)
                self.assertIn(secret_marker, rendered.read_text(encoding="utf-8"))
                active = json.loads(
                    (
                        work_root / "alpha-local" / "provider-config" / "active.json"
                    ).read_text(encoding="utf-8")
                )
                self.assertEqual(
                    active["bindingDigest"],
                    result["bindingDigest"],
                )
                self.assertEqual(
                    active["runtimeCompositionDigest"],
                    result["runtimeCompositionDigest"],
                )
                diff = provider_config.compile_provider_config(
                    action="diff",
                    environment="alpha",
                    target="alpha-local",
                    runtime_composition=self.alpha_composition,
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
                    runtime_composition=self.alpha_composition,
                )
            self.assertEqual(result["exitCode"], 2, result)
            self.assertTrue(result["missingKeys"])
            serialized = json.dumps(result, sort_keys=True)
            self.assertNotIn("endpoint=", serialized)
            self.assertNotIn("token=", serialized)

    def test_secret_projection_rejects_capability_directory_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            work_root = root / "deploy"
            capability_id, _key = self._first_material_identity()
            secrets = work_root / "alpha-local/secrets"
            secrets.mkdir(parents=True)
            external = root / "external-capability"
            external.mkdir()
            (secrets / capability_id).symlink_to(external, target_is_directory=True)
            with mock.patch.dict(
                os.environ,
                {"QWQ_DEPLOY_WORK_ROOT": str(work_root)},
                clear=False,
            ):
                with self.assertRaisesRegex(ValueError, "symlink|unsafe"):
                    provider_config.project_provider_secret_bundles(
                        environment="alpha",
                        target="alpha-local",
                        source=self._alpha_material(),
                        runtime_composition=self.alpha_composition,
                    )
            self.assertEqual(list(external.iterdir()), [])

    def test_secret_projection_rejects_parent_directory_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            work_root = root / "deploy"
            target_root = work_root / "alpha-local"
            target_root.mkdir(parents=True)
            external = root / "external-secrets"
            external.mkdir()
            (target_root / "secrets").symlink_to(external, target_is_directory=True)
            with mock.patch.dict(
                os.environ,
                {"QWQ_DEPLOY_WORK_ROOT": str(work_root)},
                clear=False,
            ):
                with self.assertRaisesRegex(ValueError, "symlink|unsafe"):
                    provider_config.project_provider_secret_bundles(
                        environment="alpha",
                        target="alpha-local",
                        source=self._alpha_material(),
                        runtime_composition=self.alpha_composition,
                    )
            self.assertEqual(list(external.iterdir()), [])

    def test_secret_projection_rejects_final_file_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            work_root = root / "deploy"
            capability_id, key = self._first_material_identity()
            capability_root = work_root / "alpha-local/secrets" / capability_id
            capability_root.mkdir(parents=True)
            external = root / "external-secret"
            external.write_text("outside-sentinel", encoding="utf-8")
            (capability_root / key).symlink_to(external)
            with mock.patch.dict(
                os.environ,
                {"QWQ_DEPLOY_WORK_ROOT": str(work_root)},
                clear=False,
            ):
                with self.assertRaisesRegex(ValueError, "symlink|non-regular"):
                    provider_config.project_provider_secret_bundles(
                        environment="alpha",
                        target="alpha-local",
                        source=self._alpha_material(),
                        runtime_composition=self.alpha_composition,
                    )
            self.assertEqual(external.read_text(encoding="utf-8"), "outside-sentinel")

    def test_secret_projection_uses_private_atomic_regular_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            work_root = Path(temporary) / "deploy"
            material = self._alpha_material()
            capability_id, key = self._first_material_identity()
            with mock.patch.dict(
                os.environ,
                {"QWQ_DEPLOY_WORK_ROOT": str(work_root)},
                clear=False,
            ):
                projected = provider_config.project_provider_secret_bundles(
                    environment="alpha",
                    target="alpha-local",
                    source=material,
                    runtime_composition=self.alpha_composition,
                )
                secret = work_root / "alpha-local/secrets" / capability_id / key
                first_inode = secret.stat().st_ino
                material[key] = "rotated-provider-material"
                provider_config.project_provider_secret_bundles(
                    environment="alpha",
                    target="alpha-local",
                    source=material,
                    runtime_composition=self.alpha_composition,
                )
            self.assertIn(f"{capability_id}:{key}", projected)
            self.assertTrue(secret.is_file())
            self.assertFalse(secret.is_symlink())
            self.assertEqual(secret.stat().st_mode & 0o777, 0o600)
            self.assertEqual(secret.parent.stat().st_mode & 0o777, 0o700)
            self.assertEqual(secret.read_text(encoding="utf-8"), material[key])
            self.assertNotEqual(secret.stat().st_ino, first_inode)
            self.assertEqual(list(secret.parent.glob(f".{key}.*.tmp")), [])

    def test_target_environment_mismatch_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "mismatch"):
            provider_config.compile_provider_config(
                action="validate",
                environment="alpha",
                target="beta-local",
                runtime_composition=self.alpha_composition,
            )

    def test_packaged_runtime_path_has_no_workspace_selector_fallback(self) -> None:
        compiled, issues = load_and_compile()
        self.assertFalse(issues)
        composition = compile_provider_runtime_composition(
            environment="alpha",
            target="alpha-local",
            compiled=compiled,
        )
        material = self._alpha_material()
        self.assertFalse(hasattr(provider_config, "compile_provider_runtime_composition"))
        self.assertFalse(hasattr(provider_config, "_owner_bindings"))
        with tempfile.TemporaryDirectory() as temporary, mock.patch.dict(
            os.environ,
            {"QWQ_DEPLOY_WORK_ROOT": str(Path(temporary) / "deploy")},
            clear=False,
        ):
            provider_config.project_provider_secret_bundles(
                environment="alpha",
                target="alpha-local",
                source=material,
                runtime_composition=composition,
            )
            result = provider_config.compile_provider_config(
                action="validate",
                environment="alpha",
                target="alpha-local",
                runtime_composition=composition,
            )
        self.assertEqual(result["exitCode"], 0, result)
        self.assertEqual(
            result["runtimeCompositionDigest"],
            composition["runtimeCompositionDigest"],
        )

        tampered = deepcopy(composition)
        tampered["bindings"][0]["adapterId"] = "ext.tampered.adapter"
        with self.assertRaisesRegex(
            ValueError,
            "canonical environment Bindings|bindingDigest mismatch|"
            "non-production third-party Provider must select a local substitute",
        ):
            provider_config.compile_provider_config(
                action="validate",
                environment="alpha",
                target="alpha-local",
                runtime_composition=tampered,
            )

    def test_stackctl_provider_config_consumes_only_active_candidate(self) -> None:
        compiler = mock.Mock(
            compile_provider_config=mock.Mock(return_value={"exitCode": 0})
        )
        args = argparse.Namespace(
            provider_config_action="validate",
            env="alpha",
            target="alpha-local",
        )
        with (
            mock.patch.object(
                stackctl,
                "_active_provider_runtime",
                return_value={"composition": self.alpha_composition},
            ),
            mock.patch.object(stackctl, "_provider_config", return_value=compiler),
        ):
            result = stackctl.command_provider_config(args)
        self.assertEqual(result["exitCode"], 0)
        compiler.compile_provider_config.assert_called_once_with(
            action="validate",
            environment="alpha",
            target="alpha-local",
            runtime_composition=self.alpha_composition,
        )

        with mock.patch.object(
            stackctl,
            "_active_provider_runtime",
            side_effect=ValueError("active candidate missing"),
        ):
            blocked = stackctl.command_provider_config(args)
        self.assertEqual(blocked["exitCode"], 2)
        self.assertIn("active candidate missing", blocked["details"])

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

    def _first_material_identity(self) -> tuple[str, str]:
        identities: list[tuple[str, str]] = []
        for binding in self.alpha_composition["bindings"]:
            capability_id = str(binding["capabilityId"])
            keys = [
                *dict(binding["endpointEnvironmentKeys"]).values(),
                *list(binding["secretEnvironmentKeys"]),
            ]
            identities.extend((capability_id, str(key)) for key in keys)
        self.assertTrue(identities)
        return sorted(identities)[0]


if __name__ == "__main__":
    unittest.main()
