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
from quwoquan_ops.cli.commands import package_runtime
from quwoquan_ops.cli.lib import assistant_skill_package_artifact


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

            public_path.write_text(
                json.dumps(
                    {
                        KEY_ID: base64.b64encode(b"x" * 32).decode("ascii"),
                    },
                    separators=(",", ":"),
                ),
                encoding="utf-8",
            )
            public_path.chmod(0o600)
            with mock.patch.dict(
                os.environ,
                {"QWQ_DEPLOY_WORK_ROOT": str(deploy_root)},
                clear=False,
            ):
                matched = prepare_local_assistant_skill_package_keys(
                    "gamma",
                    "gamma-local",
                )
            self.assertNotEqual(
                json.loads(matched.public_keys_json)[KEY_ID],
                base64.b64encode(b"x" * 32).decode("ascii"),
            )

    def test_packaged_release_trust_is_environment_scoped_and_self_verifying(self) -> None:
        source_revision = "a" * 40
        source_digest = "sha256:" + "b" * 64
        alpha_keys = json.dumps(
            {KEY_ID: base64.b64encode(b"a" * 32).decode("ascii")},
            separators=(",", ":"),
        )
        beta_keys = json.dumps(
            {KEY_ID: base64.b64encode(b"b" * 32).decode("ascii")},
            separators=(",", ":"),
        )
        alpha = publication.derive_official_skill_package_release_identity(
            environment="alpha",
            target="alpha-local",
            source_digest=source_digest,
            source_revision=source_revision,
            public_keys_json=alpha_keys,
        )
        beta = publication.derive_official_skill_package_release_identity(
            environment="beta",
            target="beta-local",
            source_digest=source_digest,
            source_revision=source_revision,
            public_keys_json=beta_keys,
        )
        self.assertNotEqual(alpha["buildId"], beta["buildId"])
        self.assertNotEqual(
            alpha["trustedPublicKeysDigest"], beta["trustedPublicKeysDigest"]
        )
        prod = publication.derive_official_skill_package_release_identity(
            environment="prod",
            target="prod-hosted",
            source_digest=source_digest,
            source_revision=source_revision,
            public_keys_json=alpha_keys,
        )
        self.assertTrue(prod["buildId"].startswith("prod-"))
        with self.assertRaisesRegex(RuntimeError, "target identity"):
            publication.derive_official_skill_package_release_identity(
                environment="alpha",
                target="beta-local",
                source_digest=source_digest,
                source_revision=source_revision,
                public_keys_json=alpha_keys,
            )

    def test_prod_package_requires_external_signing_material(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "externally managed signing"):
            assistant_skill_package_artifact.build_official_skill_package_publication(
                "prod",
                "prod-hosted",
                package_source_root=ROOT,
                package_environment={"QWQ_PACKAGE_SOURCE_REVISION": "a" * 40},
                output_root=Path.home() / "unused-prod-skill-package",
            )

    def test_package_builder_uses_one_absolute_root_across_cwd_boundaries(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.home()) as temporary:
            root = Path(temporary)
            package_source_root = root / "repository"
            caller_cwd = root / "caller"
            package_source_root.mkdir()
            caller_cwd.mkdir()
            relative_output_root = Path("reports/managed/skill-packages/official")
            expected_output_root = package_source_root / relative_output_root
            expected_output_root.mkdir(parents=True)
            signing = assistant_skill_package_artifact.SigningMaterial(
                key_id="local-key",
                private_key_base64="private-key",
                public_keys_json='{"local-key":"public-key"}',
            )
            completed = mock.Mock(
                returncode=0,
                stdout=json.dumps({"buildId": "build-id"}),
                stderr="",
            )
            previous_cwd = Path.cwd()
            try:
                os.chdir(caller_cwd)
                with (
                    mock.patch.object(
                        assistant_skill_package_artifact,
                        "_signing_material",
                        return_value=signing,
                    ) as signing_material,
                    mock.patch.object(
                        assistant_skill_package_artifact,
                        "_source_digest",
                        return_value="sha256:" + "b" * 64,
                    ) as source_digest,
                    mock.patch.object(
                        assistant_skill_package_artifact,
                        "derive_official_skill_package_release_identity",
                        return_value={
                            "buildId": "build-id",
                            "commandId": "command-id",
                        },
                    ) as derive_identity,
                    mock.patch.object(
                        assistant_skill_package_artifact.shutil,
                        "rmtree",
                    ) as rmtree,
                    mock.patch.object(
                        assistant_skill_package_artifact.subprocess,
                        "run",
                        return_value=completed,
                    ) as run,
                    mock.patch.object(
                        assistant_skill_package_artifact,
                        "materialize_packaged_official_skill_release",
                        return_value={"buildId": "build-id"},
                    ) as materialize,
                ):
                    report = assistant_skill_package_artifact.build_official_skill_package_publication(
                        "alpha",
                        "alpha-local",
                        package_source_root=package_source_root,
                        package_environment={"QWQ_PACKAGE_SOURCE_REVISION": "a" * 40},
                        output_root=relative_output_root,
                    )
            finally:
                os.chdir(previous_cwd)

            rmtree.assert_called_once_with(expected_output_root)
            command = run.call_args.args[0]
            output_index = command.index("--output-root") + 1
            self.assertEqual(command[output_index], str(expected_output_root))
            self.assertEqual(report["argv"][output_index], str(expected_output_root))
            self.assertEqual(
                run.call_args.kwargs["cwd"],
                str(package_source_root / "quwoquan_service"),
            )
            self.assertEqual(
                materialize.call_args.kwargs["output_root"],
                expected_output_root,
            )
            signing_material.assert_called_once()
            source_digest.assert_called_once()
            derive_identity.assert_called_once()
            materialize.assert_called_once()

    def test_package_builder_rejects_symlinked_output_root_components(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.home()) as temporary:
            root = Path(temporary)
            package_source_root = root / "repository"
            outside = root / "outside"
            package_source_root.mkdir()
            outside.mkdir()
            (package_source_root / "linked-parent").symlink_to(
                outside,
                target_is_directory=True,
            )
            (package_source_root / "linked-target").symlink_to(
                outside,
                target_is_directory=True,
            )
            with (
                mock.patch.object(
                    assistant_skill_package_artifact,
                    "_signing_material",
                ) as signing_material,
                mock.patch.object(
                    assistant_skill_package_artifact,
                    "_source_digest",
                ) as source_digest,
                mock.patch.object(
                    assistant_skill_package_artifact,
                    "derive_official_skill_package_release_identity",
                ) as derive_identity,
                mock.patch.object(
                    assistant_skill_package_artifact.subprocess,
                    "run",
                ) as run,
                mock.patch.object(
                    assistant_skill_package_artifact,
                    "materialize_packaged_official_skill_release",
                ) as materialize,
            ):
                for unsafe_output_root in (
                    Path("linked-parent/official"),
                    Path("linked-target"),
                ):
                    with (
                        self.subTest(output_root=unsafe_output_root),
                        self.assertRaisesRegex(RuntimeError, "must not contain symlinks"),
                    ):
                        assistant_skill_package_artifact.build_official_skill_package_publication(
                            "alpha",
                            "alpha-local",
                            package_source_root=package_source_root,
                            package_environment={
                                "QWQ_PACKAGE_SOURCE_REVISION": "a" * 40
                            },
                            output_root=unsafe_output_root,
                        )

            signing_material.assert_not_called()
            source_digest.assert_not_called()
            derive_identity.assert_not_called()
            run.assert_not_called()
            materialize.assert_not_called()

    def test_package_builder_rejects_symlink_created_before_readback(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.home()) as temporary:
            root = Path(temporary)
            package_source_root = root / "repository"
            outside = root / "outside"
            package_source_root.mkdir()
            outside.mkdir()
            relative_output_root = Path("reports/managed/skill-packages/official")
            absolute_output_root = package_source_root / relative_output_root
            absolute_output_root.parent.mkdir(parents=True)
            signing = assistant_skill_package_artifact.SigningMaterial(
                key_id="local-key",
                private_key_base64="private-key",
                public_keys_json='{"local-key":"public-key"}',
            )

            def create_unsafe_output(*args: object, **kwargs: object) -> mock.Mock:
                absolute_output_root.symlink_to(outside, target_is_directory=True)
                return mock.Mock(
                    returncode=0,
                    stdout=json.dumps({"buildId": "build-id"}),
                    stderr="",
                )

            with (
                mock.patch.object(
                    assistant_skill_package_artifact,
                    "_signing_material",
                    return_value=signing,
                ),
                mock.patch.object(
                    assistant_skill_package_artifact,
                    "_source_digest",
                    return_value="sha256:" + "b" * 64,
                ),
                mock.patch.object(
                    assistant_skill_package_artifact,
                    "derive_official_skill_package_release_identity",
                    return_value={
                        "buildId": "build-id",
                        "commandId": "command-id",
                    },
                ),
                mock.patch.object(
                    assistant_skill_package_artifact.subprocess,
                    "run",
                    side_effect=create_unsafe_output,
                ) as run,
                mock.patch.object(
                    assistant_skill_package_artifact,
                    "materialize_packaged_official_skill_release",
                ) as materialize,
            ):
                report = assistant_skill_package_artifact.build_official_skill_package_publication(
                    "alpha",
                    "alpha-local",
                    package_source_root=package_source_root,
                    package_environment={"QWQ_PACKAGE_SOURCE_REVISION": "a" * 40},
                    output_root=relative_output_root,
                )

            command = run.call_args.args[0]
            output_index = command.index("--output-root") + 1
            self.assertEqual(command[output_index], str(absolute_output_root))
            self.assertEqual(report["exitCode"], 1)
            self.assertIn("must not contain symlinks", report["stderr"])
            materialize.assert_not_called()

    def test_package_builder_emits_release_identity_and_trust_material(self) -> None:
        source = (
            ROOT / "quwoquan_ops/cli/commands/package_runtime.py"
        ).read_text(encoding="utf-8")
        artifact_source = (
            ROOT / "quwoquan_ops/cli/lib/assistant_skill_package_artifact.py"
        ).read_text(encoding="utf-8")
        self.assertIn("build_official_skill_package_publication", source)
        self.assertIn("materialize_packaged_official_skill_release", artifact_source)
        publication_source = (
            ROOT
            / "quwoquan_ops/cli/lib/local_assistant_skill_package_publication.py"
        ).read_text(encoding="utf-8")
        self.assertIn('"trusted_public_keys.json"', publication_source)
        self.assertIn('"release.json"', publication_source)

    def test_service_core_compile_preflight_is_explicit(self) -> None:
        with mock.patch(
            "quwoquan_ops.cli.stackctl.run"
        ) as run:
            run.side_effect = [
                mock.Mock(returncode=0, stdout="", stderr=""),
                mock.Mock(returncode=0, stdout="", stderr=""),
                mock.Mock(returncode=0, stdout="", stderr=""),
            ]
            reports, error = package_runtime._run_runtime_compile_preflight(
                package_environment={},
                source_root=ROOT,
            )
        self.assertEqual(error, "")
        self.assertEqual(
            [report["name"] for report in reports],
            [
                "compile-entrypoints:go",
                "compile-entrypoint:service-core",
                "compile-entrypoints:recommendation-python",
            ],
        )
        service_core_argv = run.call_args_list[1].args[0]
        self.assertEqual(service_core_argv[-1], "./cmd/service-core")

    def test_assistant_compose_requires_trusted_keys_json(self) -> None:
        compose = (
            ROOT
            / "quwoquan_service/services/assistant-service/deploy/compose.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "ASSISTANT_SKILL_PACKAGE_TRUSTED_PUBLIC_KEYS_JSON:?ASSISTANT_SKILL_PACKAGE_TRUSTED_PUBLIC_KEYS_JSON is required}",
            compose,
        )

    def test_stackctl_binds_skill_keys_for_every_workload(self) -> None:
        """service-core 合并容器让这把 key 成为容器级前置。

        bounded content workload 在 `content-release` 分支提前返回,所以该分
        支之前的代码是所有 workload 的公共前缀。注入必须落在这段公共前缀
        里且不被 `workload == "full"` 守卫包裹,否则 bounded content 栈会在
        Compose 插值阶段就因缺值失败。
        """

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
        self.assertNotIn(
            'if workload == "full":',
            bind_fn[:content_return_index],
        )

    def test_service_core_closure_carries_the_assistant_module(self) -> None:
        """无条件注入的依据:assistant 模块在 service-core 闭包里。

        闭包一旦不再包含 assistant-service,注入就可以按 workload 重新收紧。
        """

        from quwoquan_ops.cli.lib.service_core_composition import (
            SERVICE_CORE_MODULE_SET,
        )

        self.assertIn("assistant-service", SERVICE_CORE_MODULE_SET)

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

    def test_immutable_up_loads_trust_from_fixed_candidate(self) -> None:
        binding = (
            ROOT / "quwoquan_ops/cli/commands/gamma_release_binding.py"
        ).read_text(encoding="utf-8")
        up = (ROOT / "quwoquan_ops/cli/commands/up_runtime.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("QWQ_FIXED_CANDIDATE_ROOT", up)
        self.assertIn("load_packaged_assistant_skill_package_trust", binding)
        self.assertIn("QWQ_FIXED_CANDIDATE_ROOT", binding)

    def test_secret_material_is_not_committed(self) -> None:
        tracked = list(
            (ROOT / "quwoquan_ops").rglob("trusted_public_keys.json")
        ) + list((ROOT / "quwoquan_ops").rglob("assistant-skill-package/**"))
        self.assertEqual(tracked, [])


if __name__ == "__main__":
    unittest.main()
