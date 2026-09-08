# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#req-004
#
# integrate 的 Data release 输入按 DEC-041 单一 production 类别：attestation 只接受
# releaseClass=productLifecycleState=production；进入环境只经现役 `qwq-data ship`
# 的 handoff-ref 准入（apply → activate → verify --readiness-phase production），
# 不再以 release id 隐式选择、也不接受 research/commercial。

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli import integration_run  # noqa: E402
from quwoquan_ops.cli.lib.deployment_candidate_manifest import (  # noqa: E402
    RELEASE_INPUT_CLASSIFICATIONS,
    release_input_classification,
)

VALID_REF = "handoff-ref-v1:sha256:" + "a" * 64 + ":sha256:" + "b" * 64


def _attestation(root: Path, release_id: str, release_class: str) -> Path:
    payload = {
        "schema": "quwoquan_data.release_attestation",
        "releaseId": release_id,
        "releaseClass": release_class,
        "productLifecycleState": release_class,
        "payloadSha256": "sha256:" + "c" * 64,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    local = root / "data/releases" / release_id / "attestations/release.json"
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_bytes(encoded)
    given = root / f"{release_id}.json"
    given.write_bytes(encoded)
    return given


class IntegrationRunProductionReleaseContractTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="qwq-integrate-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        patcher = mock.patch.object(integration_run, "OUTPUT_ROOT", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_release_id_accepts_only_production_attestations(self) -> None:
        production = _attestation(self.root, "rel-production", "production")
        self.assertEqual(integration_run._release_id(production), ("rel-production", "production"))
        for retired in ("research", "commercial"):
            with self.subTest(retired=retired), self.assertRaises(integration_run.IntegrationRunError) as blocked:
                integration_run._release_id(_attestation(self.root, f"rel-{retired}", retired))
            self.assertEqual(blocked.exception.code, "INTEGRATION_RUN.INPUT_INVALID")
            self.assertIn("production", blocked.exception.detail)

    def test_handoff_ref_must_be_canonical_v1(self) -> None:
        self.assertEqual(integration_run._handoff_ref(VALID_REF, label="--release-handoff-ref"), VALID_REF)
        for bad in ("", "rel-production", "handoff-ref-v1:sha256:abc", "sha256:" + "a" * 64):
            with self.subTest(bad=bad), self.assertRaises(integration_run.IntegrationRunError) as blocked:
                integration_run._handoff_ref(bad, label="--release-handoff-ref")
            self.assertEqual(blocked.exception.code, "INTEGRATION_RUN.INPUT_INVALID")

    def test_apply_data_release_drives_current_ship_cli_with_handoff_ref(self) -> None:
        attestation = _attestation(self.root, "rel-production", "production")
        calls: list[tuple[str, ...]] = []

        def fake_ship(*args: str, log_dir: Path, label: str) -> None:
            calls.append(tuple(args))
            if args[0] == "verify":
                readiness = self.root / "env/alpha/runs/data-release/rel-production/run-1-verify/release-readiness.json"
                readiness.parent.mkdir(parents=True, exist_ok=True)
                readiness.write_text("{}", encoding="utf-8")

        args = SimpleNamespace(release_attestation=attestation, release_handoff_ref=VALID_REF)
        with mock.patch.object(integration_run, "_data_ship", side_effect=fake_ship):
            readiness = integration_run._apply_data_release(
                environment="alpha", run_id="run-1", args=args, log_dir=self.root / "logs", previous_readiness=None,
            )
        self.assertTrue(readiness.is_file())
        self.assertEqual([call[0] for call in calls], ["apply", "activate", "verify"])
        for call in calls:
            self.assertIn("--handoff-ref", call)
            self.assertIn(VALID_REF, call)
            self.assertNotIn("--release-id", call)
        self.assertIn("--full-sync", calls[0])
        self.assertIn("--import", calls[0])
        verify = calls[2]
        self.assertEqual(verify[verify.index("--readiness-phase") + 1], "production")
        self.assertEqual(verify[verify.index("--import-run-id") + 1], "run-1-import")

    def test_parser_requires_candidate_handoff_ref_only(self) -> None:
        # integrate 只对 candidate 执行 ship apply/activate/verify；rollback release 只参与
        # stackctl package 的候选绑定，因此不需要 rollback handoff-ref。
        parser = integration_run._parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["--release-attestation", "a", "--rollback-release-attestation", "b"])
        parsed = parser.parse_args([
            "--release-attestation", "a", "--rollback-release-attestation", "b",
            "--release-handoff-ref", VALID_REF,
        ])
        self.assertEqual(parsed.release_handoff_ref, VALID_REF)
        self.assertFalse(hasattr(parsed, "rollback_handoff_ref"))
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn("RELEASE_HANDOFF_REF", makefile)
        self.assertNotIn("ROLLBACK_HANDOFF_REF", makefile)
        self.assertIn('--release-handoff-ref "$(RELEASE_HANDOFF_REF)"', makefile)

    def test_production_pair_classifies_as_production_inputs(self) -> None:
        def binding(release_class: str) -> dict[str, str]:
            return {
                "releaseId": f"rel-{release_class}", "releaseDigest": "sha256:" + "1" * 64,
                "attestationRef": "x", "attestationDigest": "sha256:" + "2" * 64,
                "releaseClass": release_class, "productLifecycleState": release_class,
            }

        self.assertIn("production_inputs", RELEASE_INPUT_CLASSIFICATIONS)
        self.assertEqual(
            release_input_classification({"candidate": binding("production"), "rollback": binding("production")}),
            "production_inputs",
        )
        self.assertEqual(
            release_input_classification({"candidate": binding("production"), "rollback": binding("research")}),
            "mixed_inputs",
        )


if __name__ == "__main__":
    unittest.main()
