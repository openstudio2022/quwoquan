"""Web hosting runtime 文档必须跟随 content_source_policy，不能给 Alpha 签发 Remote 包。

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
APP = ROOT / "quwoquan_app"
sys.path[:0] = [
    str(ROOT),
    str(APP / "scripts/env"),
    str(APP / "test/support/runtime/launcher"),
]

from launcher_package_fixture import _issue_test_signing_material  # noqa: E402
from quwoquan_ops.cli.lib.app_launch_manifest_contract import (  # noqa: E402
    load_launch_manifest_contract,
    runtime_document_content_source,
)
from quwoquan_ops.cli.lib.dev_session_web_runtime_config import (  # noqa: E402
    _hosting_runtime_document,
    _load_runtime_package_builder,
)


class DevSessionWebRuntimeConfigContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="qwq-web-runtime-")
        self.addCleanup(self.temp.cleanup)
        self.signing = _issue_test_signing_material(Path(self.temp.name))
        self.builder = _load_runtime_package_builder(ROOT)
        self.contract = load_launch_manifest_contract()
        self.identity = {
            "source_revision": "a" * 40,
            "source_tree_digest": "sha1:" + "b" * 40,
            "signing": self.signing,
        }

    def test_alpha_hosting_issues_offline_bootstrap_not_remote_package(self) -> None:
        document = _hosting_runtime_document(
            builder=self.builder,
            environment="alpha",
            target="alpha-local",
            **self.identity,
        )
        self.assertEqual(
            document["schema"],
            self.contract["schemas"]["offline_bootstrap_document"]["schema_value"],
        )
        self.assertEqual(document["contentSource"], "bundled_snapshot")
        self.assertEqual(
            runtime_document_content_source(document, self.contract),
            "bundled_snapshot",
        )
        self.assertEqual(document["runtime"], {"appRuntimeEnv": "alpha"})
        self.assertNotIn("gatewayBaseUrl", document.get("runtime", {}))

    def test_beta_hosting_keeps_remote_runtime_package(self) -> None:
        document = _hosting_runtime_document(
            builder=self.builder,
            environment="beta",
            target="beta-local",
            **self.identity,
        )
        self.assertEqual(
            document["schema"],
            self.contract["schemas"]["runtime_config_package"]["schema_value"],
        )
        self.assertNotIn("contentSource", document)
        self.assertEqual(
            runtime_document_content_source(document, self.contract),
            "remote",
        )
        self.assertIn("gatewayBaseUrl", document.get("runtime", {}))

    def test_alpha_remote_package_is_policy_mismatch(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "runtime document content source policy mismatch",
        ):
            self.builder.build_runtime_config_package(
                environment="alpha",
                target="alpha-local",
                launch_policy="test_live",
                values=self.builder.test_live_runtime_values("alpha", "alpha-local"),
                source_git_sha=self.identity["source_revision"],
                source_tree_digest=self.identity["source_tree_digest"],
                signing=self.signing,
            )


if __name__ == "__main__":
    unittest.main()
