"""prod-sim local rehearsal Web hosting contracts.

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-001
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib import dev_session_web_runtime_config as runtime_config
from quwoquan_ops.cli.lib import local_release_web_hosting as hosting
from quwoquan_ops.cli.lib.output_paths import (
    app_deployment_package_dir,
    deployment_target_path,
    web_deployment_package_dir,
)


PROD_SIM = ("prod", "prod-sim")
PUBLIC_BASES = {
    "gatewayBaseUrl": "https://api.sim.quwoquan.com:20000",
    "legalBaseUrl": "https://sim.quwoquan.com:20000/legal",
    "publicWebBaseUrl": "https://sim.quwoquan.com:20000",
    "appDownloadBaseUrl": "https://cdn.sim.quwoquan.com:20100/download",
    "realtimeBaseUrl": "wss://api.sim.quwoquan.com:20000",
    "mediaAvatarCdnBaseUrl": "https://cdn.sim.quwoquan.com:20100/media/avatar",
    "mediaImageCdnBaseUrl": "https://cdn.sim.quwoquan.com:20100/media/image",
    "mediaVideoCdnBaseUrl": "https://cdn.sim.quwoquan.com:20100/media/video",
    "mediaUploadBaseUrl": "https://upload.sim.quwoquan.com:20100",
    "rtcMediaConnectionUrl": "wss://rtc.sim.quwoquan.com:20000",
}


def _git_command(*_args: object, **_kwargs: object) -> SimpleNamespace:
    return SimpleNamespace(returncode=0, stdout="a" * 40 + "\n")


class LocalReleaseWebHostingContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="qwq-prod-sim-web-hosting-")
        self.deploy_root = Path(self.temporary.name) / "deploy"
        self.environment = mock.patch.dict(
            os.environ,
            {
                "QWQ_DEPLOY_WORK_ROOT": str(self.deploy_root),
                "PYTHONDONTWRITEBYTECODE": "1",
            },
            clear=False,
        )
        self.environment.start()

    def tearDown(self) -> None:
        self.environment.stop()
        self.temporary.cleanup()

    def _write_prod_sim_app_runtime_package(self) -> None:
        package_root = app_deployment_package_dir("prod", target="prod-sim")
        package_root.mkdir(parents=True)
        package_root.joinpath("app_runtime.yaml").write_text(
            "\n".join(
                [
                    "schema: app-runtime-config",
                    "runtime:",
                    "  appRuntimeEnv: prod",
                    *[
                        f"  {key}: {value}"
                        for key, value in PUBLIC_BASES.items()
                    ],
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        package_root.joinpath("report.json").write_text(
            json.dumps({"status": "packaged", "env": "prod", "target": "prod-sim"}),
            encoding="utf-8",
        )

    def _write_prod_sim_web_package(self) -> tuple[Path, str]:
        package_root = web_deployment_package_dir("prod", target="prod-sim")
        release_id = "release-for-prod-sim"
        current = package_root / "current"
        (current / "public").mkdir(parents=True)
        (current / "manifest.json").write_text(
            json.dumps(
                {
                    "schema": "client-app.web.official-release",
                    "environment": "prod",
                    "publicOrigin": PUBLIC_BASES["publicWebBaseUrl"],
                    "releaseId": release_id,
                    "contentSHA256": "f" * 64,
                }
            ),
            encoding="utf-8",
        )
        return package_root, release_id

    def test_prod_sim_rehearsal_runtime_config_is_signed_nonpromotable_and_never_test_live(
        self,
    ) -> None:
        self._write_prod_sim_app_runtime_package()
        artifact_root = self.deploy_root / "immutable-web"
        artifact_root.mkdir(parents=True)
        hosting_root = self.deploy_root / "hosting"
        builder = runtime_config._load_runtime_package_builder(ROOT)

        def test_live_must_not_run(*_args: object, **_kwargs: object) -> dict[str, str]:
            raise AssertionError("prod-sim must not use the test_live runtime helper")

        with (
            mock.patch.object(
                runtime_config,
                "_load_runtime_package_builder",
                return_value=builder,
            ),
            mock.patch.object(builder, "test_live_runtime_values", test_live_must_not_run),
        ):
            materialized = (
                runtime_config.materialize_prod_sim_local_rehearsal_web_runtime_config(
                    repo_root=ROOT,
                    environment="prod",
                    target="prod-sim",
                    artifact_root=artifact_root,
                    hosting_root=hosting_root,
                    source_revision="b" * 40,
                    run_command=_git_command,
                )
            )

        package = json.loads(
            hosting_root.joinpath("runtime-config-package.json").read_text(encoding="utf-8")
        )
        trust = json.loads(
            hosting_root.joinpath("runtime-config-trust.json").read_text(encoding="utf-8")
        )
        self.assertTrue(materialized["nonPromotable"])
        self.assertEqual(materialized["runtimeScope"], "local_rehearsal")
        self.assertEqual(package["environment"], "prod")
        self.assertEqual(package["target"], "prod-sim")
        self.assertEqual(package["buildProfile"], "prod")
        self.assertEqual(package["launchPolicy"], "prod_release")
        self.assertEqual(package["signatureKeyId"], "local-prod-sim-rehearsal-ed25519")
        self.assertEqual(trust["buildProfile"], "prod")
        self.assertEqual(package["runtime"], {"appRuntimeEnv": "prod", **PUBLIC_BASES})
        self.assertNotIn("prod-hosted", json.dumps({"package": package, "trust": trust}))
        for endpoint in PUBLIC_BASES.values():
            hostname = urlparse(endpoint).hostname
            self.assertTrue(
                hostname == "sim.quwoquan.com" or hostname.endswith(".sim.quwoquan.com"),
                endpoint,
            )
            self.assertNotEqual(hostname, "quwoquan.com")

    def test_prod_sim_hosting_reads_exact_standalone_writer_path_and_dispatches_rehearsal(
        self,
    ) -> None:
        package_root, release_id = self._write_prod_sim_web_package()
        rehearsal = mock.Mock(return_value={"nonPromotable": True, "runtimeScope": "local_rehearsal"})
        test_live = mock.Mock(
            side_effect=AssertionError("prod-sim must not reach test_live")
        )
        with (
            mock.patch.object(
                hosting,
                "materialize_prod_sim_local_rehearsal_web_runtime_config",
                rehearsal,
            ),
            mock.patch.object(
                hosting,
                "materialize_dev_session_web_runtime_config",
                test_live,
            ),
            mock.patch.object(hosting, "_run", _git_command),
        ):
            hosting_root, digest = hosting.materialize_local_release_web_hosting(
                repo_root=ROOT,
                environment="prod",
                target="prod-sim",
            )

        self.assertEqual(
            package_root,
            web_deployment_package_dir("prod", target="prod-sim"),
        )
        writer_source = (
            ROOT / "quwoquan_ops/cli/commands/package_runtime.py"
        ).read_text(encoding="utf-8")
        self.assertIn("package_root=_stackctl.web_deployment_package_dir(", writer_source)
        self.assertEqual(
            hosting_root,
            deployment_target_path(
                "prod-sim", "standalone-packages", "web", "hosting", release_id
            ),
        )
        self.assertEqual(digest, "sha256:" + "f" * 64)
        rehearsal.assert_called_once()
        self.assertEqual(
            rehearsal.call_args.kwargs["artifact_root"],
            package_root / "current" / "public",
        )
        test_live.assert_not_called()

    def test_prod_sim_rehearsal_entrypoints_reject_prod_hosted(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires environment=prod and target=prod-sim"):
            runtime_config.prepare_local_prod_sim_rehearsal_runtime_config_signing(
                ROOT, environment="prod", target="prod-hosted"
            )
        with self.assertRaisesRegex(ValueError, "only supports prod/prod-sim"):
            runtime_config.materialize_prod_sim_local_rehearsal_web_runtime_config(
                repo_root=ROOT,
                environment="prod",
                target="prod-hosted",
                artifact_root=self.deploy_root / "immutable-web",
                hosting_root=self.deploy_root / "hosting",
                source_revision="b" * 40,
                run_command=_git_command,
            )

    def test_prod_sim_mirror_uses_target_scoped_runtime_package_readers(self) -> None:
        source = (ROOT / "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "runtime_shared_deployment_package_dir(sys.argv[1], target=sys.argv[2])",
            source,
        )
        self.assertIn(
            "deployment_package_root(sys.argv[1], target=sys.argv[2])",
            source,
        )
        self.assertNotIn(
            "deployment_package_root(sys.argv[1]) / \"runtime-shared\"",
            source,
        )

    def test_local_release_hosting_rejects_prod_hosted_before_local_materialization(
        self,
    ) -> None:
        with self.assertRaisesRegex(ValueError, "only supports prod/prod-sim"):
            hosting.materialize_local_release_web_hosting(
                repo_root=ROOT,
                environment="prod",
                target="prod-hosted",
            )


if __name__ == "__main__":
    unittest.main()
