# spec_ref: specs/feature-tree/platform-ops-governance/config-and-reliability-governance/reliability-policy-control/spec.md#gwt-002
from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli.prod import resolve_prod_release_state as resolver


class ResolveProdReleaseStateTransportTest(unittest.TestCase):
    def test_fetch_uses_only_the_hosted_release_ledger_authority(self) -> None:
        payload = {
            "schema": "prod-hosted-release-readback",
            "authority": "prod-hosted-service-plane",
            "state": {},
            "receipt": {},
            "receiptRef": "",
        }

        def write_readback(
            argv: list[str],
            **_: object,
        ) -> subprocess.CompletedProcess[str]:
            output = Path(argv[argv.index("--output-path") + 1])
            output.write_text(json.dumps(payload), encoding="utf-8")
            return subprocess.CompletedProcess(argv, 0, "", "")

        with mock.patch.object(
            resolver.subprocess,
            "run",
            side_effect=write_readback,
        ) as mocked_run:
            resolved = resolver._fetch_hosted_readback()

        self.assertEqual(resolved, payload)
        command = mocked_run.call_args.args[0]
        self.assertEqual(
            command[0:2],
            ["bash", "quwoquan_ops/cli/prod/sync_prod_plane_stack.sh"],
        )
        self.assertEqual(
            command[command.index("--operation") + 1],
            "release-ledger-fetch",
        )
        self.assertEqual(command[command.index("--service") + 1], "prod-stack")
        self.assertNotIn("ssh", command)

    def test_fetch_failure_is_gate_block(self) -> None:
        completed = subprocess.CompletedProcess(
            ["bash"],
            2,
            "",
            "authority unavailable",
        )
        with mock.patch.object(resolver.subprocess, "run", return_value=completed):
            with self.assertRaisesRegex(resolver.GateBlockError, "fetch failed"):
                resolver._fetch_hosted_readback()


if __name__ == "__main__":
    unittest.main()
