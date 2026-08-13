"""场景：verify profile 的生命周期 probe 注册——report-feedback / media
publication / chat group 三类 probe 的环境模式选择、不支持 profile 拒绝
与 gamma validation suites 注册。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib.content_release_readiness import VerificationProfile


class StackctlUpRuntimeTest(unittest.TestCase):
    def test_report_feedback_probe_profile_commands_use_real_environment_modes(
        self,
    ) -> None:
        cases = (
            (
                "beta",
                "beta-local",
                VerificationProfile.INTEGRATION,
                "https://api.beta.quwoquan.com:18000",
                "local",
                "lifecycle",
            ),
            (
                "gamma",
                "gamma-local",
                VerificationProfile.RELEASE,
                "https://api.gamma.quwoquan.com:19000",
                "local",
                "lifecycle",
            ),
            (
                "prod",
                "prod-hosted",
                VerificationProfile.RELEASE,
                "https://api.quwoquan.com",
                "ssh-hosted",
                "read-only",
            ),
        )
        for (
            env_name,
            target_name,
            profile,
            api_base_url,
            backend,
            expected_mode,
        ) in cases:
            with (
                self.subTest(target=target_name),
                tempfile.TemporaryDirectory() as tmp_dir,
                mock.patch.object(
                    stackctl,
                    "load_environment_topology",
                    return_value={},
                ),
                mock.patch.object(
                    stackctl,
                    "get_target",
                    return_value={
                        "env": env_name,
                        "backend": backend,
                        "publicBases": {"api": api_base_url},
                    },
                ),
            ):
                command = stackctl._report_feedback_lifecycle_profile_command(
                    env_name,
                    target_name,
                    profile,
                    Path(tmp_dir),
                )

            self.assertIsNotNone(command)
            assert command is not None
            self.assertEqual(
                command["name"],
                f"{target_name}-report-feedback-lifecycle",
            )
            self.assertIn("--mode", command["argv"])
            self.assertEqual(
                command["argv"][command["argv"].index("--mode") + 1],
                expected_mode,
            )
            self.assertNotIn("--resolve-host", command["argv"])
            self.assertTrue(command["stopOnFailure"])
            self.assertNotIn("AUTH_TOKEN", " ".join(command["argv"]))

    def test_report_feedback_probe_is_not_added_to_unsupported_profiles(self) -> None:
        self.assertIsNone(
            stackctl._report_feedback_lifecycle_profile_command(
                "beta",
                "beta-local",
                VerificationProfile.SMOKE,
                None,
            )
        )
        self.assertIsNone(
            stackctl._report_feedback_lifecycle_profile_command(
                "prod",
                "prod-sim",
                VerificationProfile.RELEASE,
                None,
            )
        )

    def test_media_publication_probe_profile_commands_use_real_environment_modes(
        self,
    ) -> None:
        cases = (
            (
                "beta",
                "beta-local",
                VerificationProfile.INTEGRATION,
                "https://api.beta.quwoquan.com:18000",
                "local",
                "lifecycle",
            ),
            (
                "gamma",
                "gamma-local",
                VerificationProfile.RELEASE,
                "https://api.gamma.quwoquan.com:19000",
                "local",
                "lifecycle",
            ),
            (
                "prod",
                "prod-sim",
                VerificationProfile.INTEGRATION,
                "https://api.sim.quwoquan.com:20000",
                "local",
                "lifecycle",
            ),
            (
                "prod",
                "prod-hosted",
                VerificationProfile.RELEASE,
                "https://api.quwoquan.example",
                "ssh-hosted",
                "read-only",
            ),
        )
        for (
            env_name,
            target_name,
            profile,
            api_base_url,
            backend,
            expected_mode,
        ) in cases:
            moderation_base_url = {
                "beta-local": "http://127.0.0.1:18220",
                "gamma-local": "http://127.0.0.1:19220",
                "prod-sim": "http://127.0.0.1:20220",
            }.get(target_name, "")
            with (
                self.subTest(target=target_name),
                tempfile.TemporaryDirectory() as tmp_dir,
                mock.patch.object(
                    stackctl,
                    "load_environment_topology",
                    return_value={},
                ),
                mock.patch.object(
                    stackctl,
                    "get_target",
                    return_value={
                        "env": env_name,
                        "backend": backend,
                        "publicBases": {"api": api_base_url},
                        "origins": {"contentService": moderation_base_url}
                        if moderation_base_url
                        else {},
                    },
                ),
            ):
                command = stackctl._media_publication_lifecycle_profile_command(
                    env_name,
                    target_name,
                    profile,
                    Path(tmp_dir),
                )

            self.assertIsNotNone(command)
            assert command is not None
            self.assertEqual(
                command["name"],
                f"{target_name}-media-publication-lifecycle",
            )
            self.assertTrue(
                any(
                    str(item).endswith("run_media_publication_lifecycle_probe.py")
                    for item in command["argv"]
                )
            )
            self.assertEqual(
                command["argv"][command["argv"].index("--mode") + 1],
                expected_mode,
            )
            self.assertEqual(
                command["argv"][command["argv"].index("--target-name") + 1],
                target_name,
            )
            self.assertNotIn("--resolve-host", command["argv"])
            self.assertEqual(
                "--moderation-base-url" in command["argv"],
                expected_mode == "lifecycle",
            )
            if moderation_base_url:
                self.assertEqual(
                    command["argv"][
                        command["argv"].index("--moderation-base-url") + 1
                    ],
                    moderation_base_url,
                )
            self.assertTrue(command["stopOnFailure"])
            self.assertNotIn("AUTH_TOKEN", " ".join(command["argv"]))

    def test_media_publication_probe_is_not_added_to_unsupported_profiles(
        self,
    ) -> None:
        self.assertIsNone(
            stackctl._media_publication_lifecycle_profile_command(
                "beta",
                "beta-local",
                VerificationProfile.SMOKE,
                None,
            )
        )
        self.assertIsNone(
            stackctl._media_publication_lifecycle_profile_command(
                "prod",
                "prod-hosted",
                VerificationProfile.INTEGRATION,
                None,
            )
        )

    def test_chat_group_lifecycle_profile_commands_use_safe_environment_modes(
        self,
    ) -> None:
        cases = (
            (
                "beta",
                "beta-local",
                VerificationProfile.INTEGRATION,
                "https://api.beta.quwoquan.com:18000",
                "local",
                True,
            ),
            (
                "gamma",
                "gamma-local",
                VerificationProfile.RELEASE,
                "https://api.gamma.quwoquan.com:19000",
                "local",
                True,
            ),
            (
                "prod",
                "prod-hosted",
                VerificationProfile.RELEASE,
                "https://api.quwoquan.com",
                "ssh-hosted",
                False,
            ),
        )
        for (
            env_name,
            target_name,
            profile,
            api_base_url,
            backend,
            expect_mutating,
        ) in cases:
            with (
                self.subTest(target=target_name),
                tempfile.TemporaryDirectory() as tmp_dir,
                mock.patch.object(
                    stackctl,
                    "load_environment_topology",
                    return_value={},
                ),
                mock.patch.object(
                    stackctl,
                    "get_target",
                    return_value={
                        "env": env_name,
                        "backend": backend,
                        "publicBases": {"api": api_base_url},
                    },
                ),
            ):
                command = stackctl._chat_group_lifecycle_profile_command(
                    env_name,
                    target_name,
                    profile,
                    Path(tmp_dir),
                )

            self.assertIsNotNone(command)
            assert command is not None
            self.assertEqual(command["name"], f"{target_name}-chat-group-lifecycle")
            self.assertTrue(
                any(
                    str(item).endswith("run_chat_group_lifecycle_probe.py")
                    for item in command["argv"]
                )
            )
            self.assertIn("--require-nonempty-sources", command["argv"])
            self.assertEqual("--mutating" in command["argv"], expect_mutating)
            self.assertNotIn("--resolve-host", command["argv"])
            self.assertTrue(command["stopOnFailure"])
            self.assertNotIn("AUTH_TOKEN", " ".join(command["argv"]))

    def test_chat_group_lifecycle_probe_is_not_added_to_unsupported_profiles(
        self,
    ) -> None:
        self.assertIsNone(
            stackctl._chat_group_lifecycle_profile_command(
                "beta",
                "beta-local",
                VerificationProfile.SMOKE,
                None,
            )
        )
        self.assertIsNone(
            stackctl._chat_group_lifecycle_profile_command(
                "prod",
                "prod-sim",
                VerificationProfile.RELEASE,
                None,
            )
        )

    def test_stackctl_selected_profile_includes_chat_group_lifecycle_probe(self) -> None:
        target = {
            "env": "beta",
            "backend": "local",
            "publicBases": {"api": "https://api.beta.quwoquan.com:18000"},
            "origins": {"contentService": "http://127.0.0.1:18220"},
        }
        with (
            mock.patch.object(
                stackctl,
                "load_environment_topology",
                return_value={},
            ),
            mock.patch.object(stackctl, "get_target", return_value=target),
            mock.patch.object(
                stackctl,
                "_current_runtime_health_scope",
                return_value="full",
            ),
        ):
            commands = stackctl._selected_profile_commands(
                "beta",
                "beta-local",
                VerificationProfile.INTEGRATION,
                Path("/tmp/chat-group-lifecycle"),
            )

        command = next(
            item
            for item in commands
            if item["name"] == "beta-local-chat-group-lifecycle"
        )
        self.assertIn("--mutating", command["argv"])
        self.assertIn("--require-nonempty-sources", command["argv"])

    def test_gamma_validation_profiles_register_media_publication_probe(self) -> None:
        registry_path = (
            stackctl.ROOT
            / "quwoquan_ops"
            / "environments"
            / "gamma"
            / "validation_suites.json"
        )
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        case_id = "media_publication_lifecycle_api_probe"
        case = registry["smokeCases"][case_id]

        self.assertTrue(
            (stackctl.ROOT / case["path"]).is_file(),
            "registered media publication probe must be runnable",
        )
        self.assertEqual(case["runner"], "python")
        for profile_name in (
            "manual_full",
            "nightly_full",
            "release_candidate",
        ):
            self.assertIn(
                case_id,
                registry["profiles"][profile_name]["smokeCases"],
            )


if __name__ == "__main__":
    unittest.main()
