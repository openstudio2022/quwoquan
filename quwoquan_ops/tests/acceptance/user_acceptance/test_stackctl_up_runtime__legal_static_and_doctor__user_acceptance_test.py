"""场景：legal-static 包构建/校验（UTF-8、target 作用域、合同关键词、prod 身份）
与 doctor 对 legal-static 来源、prod release-state、beta 部署前提的诊断语义。"""

from __future__ import annotations

import builtins
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import legal_static
from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib.common import load_json_yaml
from quwoquan_ops.cli.lib.output_paths import (
    deployment_target_for_env,
    deployment_target_path,
    legal_static_deployment_package_dir,
)


class StackctlUpRuntimeTest(unittest.TestCase):
    def test_legal_static_packages_preserve_utf8_documents_and_current_pointers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            deploy_root = Path(tmp_dir) / "deploy"
            with mock.patch.dict(
                os.environ,
                {
                    "QWQ_OUTPUT_ROOT": str(Path(tmp_dir) / ".qwq_output"),
                    "QWQ_DEPLOY_WORK_ROOT": str(deploy_root),
                },
                clear=False,
            ):
                for env_name in ("alpha", "beta", "gamma"):
                    with self.subTest(env=env_name):
                        target_name = deployment_target_for_env(env_name)
                        output_root = legal_static_deployment_package_dir(env_name)
                        payload = legal_static.build_package(
                            env_name,
                            output_root=output_root,
                        )
                        self.assertEqual(payload["status"], "ok")
                        package_dir = deployment_target_path(
                            target_name,
                            "packages",
                            "legal-static",
                            "2026-07",
                        )
                        self.assertTrue((package_dir / "checksums.json").is_file())
                        self.assertTrue((output_root / "current").exists())

                        for document in payload["documents"]:
                            stable_document = (
                                package_dir / "public" / "legal" / document["slug"]
                            )
                            self.assertTrue(stable_document.is_file())
                            self.assertIn(
                                document["title"],
                                stable_document.read_text(encoding="utf-8"),
                            )

                        verified = legal_static.verify_package(
                            env_name,
                            output_root=output_root,
                        )
                        self.assertEqual(verified["status"], "ok")

    def test_legal_static_rejects_unscoped_package_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            rejected_output = Path(tmp_dir) / "outside-legal-package"
            with mock.patch.dict(
                os.environ,
                {
                    "QWQ_OUTPUT_ROOT": str(Path(tmp_dir) / ".qwq_output"),
                    "QWQ_DEPLOY_WORK_ROOT": str(Path(tmp_dir) / "deploy"),
                },
                clear=False,
            ):
                with self.assertRaisesRegex(ValueError, "target-scoped"):
                    legal_static.build_package(
                        "alpha",
                        output_root=rejected_output,
                    )
            self.assertFalse(rejected_output.exists())

    def test_legal_static_html_validation_requires_utf8_document_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            source = Path(tmp_dir) / "user-agreement.html"
            source.write_text(
                '<html lang="zh-CN"><head></head><body>用户协议</body></html>',
                encoding="utf-8",
            )

            issues = legal_static._validate_html(
                source,
                doc_slug="user-agreement",
                version="2026-07",
                allowlist=[],
                env_name="alpha",
            )

        self.assertTrue(
            any("UTF-8 charset meta" in issue for issue in issues),
            issues,
        )

    def test_legal_static_202607_contract_keywords(self) -> None:
        manifest, issues = legal_static.validate_manifest("alpha")
        self.assertEqual(issues, [])
        self.assertEqual(manifest["currentVersion"], "2026-07")

        legal_root = legal_static.DEFAULT_MANIFEST.parent / "versions" / "2026-07"
        user_agreement = (legal_root / "user-agreement.html").read_text(encoding="utf-8")
        privacy_policy = (legal_root / "privacy-policy.html").read_text(encoding="utf-8")
        permissions = (legal_root / "permissions.html").read_text(encoding="utf-8")
        sdk_list = (legal_root / "third-party-sdk-list.html").read_text(encoding="utf-8")

        for token in (
            "外部平台内容与授权边界",
            "图虫、微信、今日头条、微博、小红书",
            "robots",
            "反爬",
            "用户内容与权利保证",
            "AI 与记忆能力",
            "当前版本为免费社区服务",
        ):
            self.assertIn(token, user_agreement)

        for token in (
            "按功能收集和使用的信息",
            "敏感个人信息",
            "委托处理、共享、转让与公开披露",
            "自动化决策、个性化推荐与 AI",
            "当前免费社区版本默认不向境外提供个人信息",
        ):
            self.assertIn(token, privacy_policy)

        self.assertIn("当前版本未启用独立语音识别系统权限", permissions)
        for token in (
            "LiveKit 实时音视频能力",
            "微信登录 SDK",
            "QQ 登录/分享 SDK",
            "支付宝 SDK",
            "广告、归因、商业化追踪 SDK",
        ):
            self.assertIn(token, sdk_list)

    def test_legal_static_package_builds_when_pyyaml_is_unavailable(self) -> None:
        real_import = builtins.__import__

        def fake_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "yaml":
                raise ModuleNotFoundError(name)
            return real_import(name, *args, **kwargs)

        with (
            mock.patch("builtins.__import__", side_effect=fake_import),
            tempfile.TemporaryDirectory() as tmp_dir,
        ):
            manifest = load_json_yaml(legal_static.DEFAULT_MANIFEST)
            deploy_root = Path(tmp_dir) / "deploy"
            with mock.patch.dict(
                os.environ,
                {
                    "QWQ_OUTPUT_ROOT": str(Path(tmp_dir) / ".qwq_output"),
                    "QWQ_DEPLOY_WORK_ROOT": str(deploy_root),
                },
                clear=False,
            ):
                payload = legal_static.build_package(
                    "alpha",
                    output_root=legal_static_deployment_package_dir("alpha"),
                )

        self.assertEqual(manifest["schema"], "legal-static")
        self.assertEqual(manifest["owner"]["appName"], "趣我圈")
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(
            [doc["slug"] for doc in manifest["documents"]],
            [
                "user-agreement",
                "privacy-policy",
                "permissions",
                "third-party-sdk-list",
            ],
        )

    def test_legal_static_prod_requires_final_legal_identity(self) -> None:
        _, issues = legal_static.validate_manifest("prod")
        self.assertTrue(any("placeholder" in issue for issue in issues))

    def test_doctor_prod_hosted_missing_release_state_is_advisory(self) -> None:
        topology = {
            "targets": {
                "prod-hosted": {
                    "env": "prod",
                    "backend": "ssh-hosted",
                    "portProfile": None,
                    "publicBases": {
                        "api": "https://118.31.239.122:19000",
                        "productOps": "https://118.31.239.122:19010",
                    },
                }
            }
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            args = mock.Mock(
                target="prod-hosted",
                report_dir=tmp_dir,
                deployment_instance="prod",
                ssh_host="",
                host_id="",
            )
            health_payload = {
                "exitCode": 0,
                "summary": "stackctl health prod-hosted: 4/4 healthy",
                "details": [],
                "reportDir": "tmp",
            }
            with (
                mock.patch("quwoquan_ops.cli.stackctl.load_environment_topology", return_value=topology),
                mock.patch("quwoquan_ops.cli.stackctl.get_target", return_value=topology["targets"]["prod-hosted"]),
                mock.patch("quwoquan_ops.cli.stackctl.command_health", return_value=health_payload),
                mock.patch(
                    "quwoquan_ops.cli.stackctl._legal_static_command",
                    return_value=(
                        mock.Mock(returncode=0),
                        {"status": "ok", "issues": [], "exitCode": 0},
                    ),
                ),
                mock.patch("quwoquan_ops.cli.stackctl._load_release_state", return_value={}),
                mock.patch(
                    "quwoquan_ops.cli.stackctl._prod_instance_runtime_reports",
                    return_value=[{
                        "plane": "service",
                        "composeFileExists": True,
                        "envFileExists": True,
                        "containerCount": 1,
                        "unit": {"enabled": True, "active": True},
                        "containers": [
                            {
                                "name": "quwoquan-plane-service",
                                "running": True,
                                "health": "healthy",
                            }
                        ],
                    }],
                ),
            ):
                result = stackctl.command_doctor(args)
            self.assertEqual(result["exitCode"], 0)
            self.assertTrue(
                any("prod rollout release-state is missing" in item for item in result["details"])
            )

    def test_doctor_prod_target_blocks_invalid_legal_static_source(self) -> None:
        topology = {
            "targets": {
                "prod-sim": {
                    "env": "prod",
                    "backend": "local",
                    "portProfile": None,
                }
            }
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            args = mock.Mock(target="prod-sim", report_dir=tmp_dir)
            health_payload = {
                "exitCode": 0,
                "summary": "stackctl health prod-sim: healthy",
                "details": [],
                "reportDir": "tmp",
            }
            with (
                mock.patch(
                    "quwoquan_ops.cli.stackctl.load_environment_topology",
                    return_value=topology,
                ),
                mock.patch(
                    "quwoquan_ops.cli.stackctl.get_target",
                    return_value=topology["targets"]["prod-sim"],
                ),
                mock.patch(
                    "quwoquan_ops.cli.stackctl.command_health",
                    return_value=health_payload,
                ),
                mock.patch(
                    "quwoquan_ops.cli.stackctl._legal_static_command",
                    return_value=(
                        mock.Mock(returncode=1),
                        {
                            "status": "failed",
                            "issues": ["owner.operatorName contains placeholder text"],
                            "exitCode": 1,
                        },
                    ),
                ),
            ):
                result = stackctl.command_doctor(args)

            self.assertEqual(result["exitCode"], 1)
            self.assertTrue(
                any("prod legal-static source is invalid" in item for item in result["details"])
            )
            self.assertTrue(
                any("owner.operatorName" in item for item in result["details"])
            )
            repair_plan = json.loads(
                (Path(tmp_dir) / "repair_plan.json").read_text(encoding="utf-8")
            )
            self.assertTrue(any("approved legal facts" in item for item in repair_plan["actions"]))

    def test_doctor_reports_missing_beta_deployment_prerequisite(self) -> None:
        topology = {
            "targets": {
                "beta-local": {
                    "env": "beta",
                    "backend": "local",
                    "portProfile": None,
                }
            }
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            args = mock.Mock(target="beta-local", report_dir=tmp_dir)
            health_payload = {
                "exitCode": 1,
                "summary": "stackctl health beta-local: failed",
                "details": [],
                "reportDir": "tmp",
            }
            with (
                mock.patch(
                    "quwoquan_ops.cli.stackctl.load_environment_topology",
                    return_value=topology,
                ),
                mock.patch(
                    "quwoquan_ops.cli.stackctl.get_target",
                    return_value=topology["targets"]["beta-local"],
                ),
                mock.patch(
                    "quwoquan_ops.cli.stackctl._load_active_product_telemetry_log_sink",
                    side_effect=RuntimeError(
                        "local provider credentials must not be written into the repository or .qwq_output"
                    ),
                ),
                mock.patch(
                    "quwoquan_ops.cli.stackctl.command_health",
                    return_value=health_payload,
                ),
            ):
                result = stackctl.command_doctor(args)

            self.assertEqual(result["exitCode"], 1)
            self.assertTrue(
                any("deployment prerequisite failed" in item for item in result["details"])
            )
            repair_plan = json.loads(
                (Path(tmp_dir) / "repair_plan.json").read_text(encoding="utf-8")
            )
            self.assertTrue(
                any("QWQ_DEPLOY_WORK_ROOT" in item for item in repair_plan["actions"])
            )
            self.assertFalse(
                any("restart-stack" in item for item in repair_plan["actions"])
            )


if __name__ == "__main__":
    unittest.main()
