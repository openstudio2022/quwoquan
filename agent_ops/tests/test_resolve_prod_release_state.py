from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "agent_ops" / "deploy" / "prod" / "resolve_prod_release_state.py"

_SPEC = importlib.util.spec_from_file_location("resolve_prod_release_state", SCRIPT)
assert _SPEC and _SPEC.loader
resolve_prod_release_state = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = resolve_prod_release_state
_SPEC.loader.exec_module(resolve_prod_release_state)


class ResolveProdReleaseStateTest(unittest.TestCase):
    def test_resolve_prod_host_prefers_env(self) -> None:
        topology = {"targets": {"prod-hosted": {"publicBases": {"api": "http://198.51.100.10:19000"}}}}
        with mock.patch.dict(os.environ, {"PROD_SSH_HOST": "203.0.113.20"}, clear=False):
            host = resolve_prod_release_state._resolve_prod_host(topology)
        self.assertEqual(host, "203.0.113.20")

    def test_run_remote_probe_parses_success_payload(self) -> None:
        access = resolve_prod_release_state.ServicePlaneAccess(
            host="203.0.113.20",
            account="prod-service-svc",
            ssh_key_secret="PROD_SERVICE_SSH_KEY",
            instance_suffix="prod",
        )
        payload = {"container": "quwoquan-service-prod_seed-box_1", "from_image": "img-v1", "from_config": "cfg-v1"}
        completed = subprocess.CompletedProcess(
            args=["ssh"],
            returncode=0,
            stdout=json.dumps(payload),
            stderr="",
        )
        with (
            mock.patch.dict(
                os.environ,
                {"PROD_SERVICE_SSH_KEY": "-----BEGIN OPENSSH PRIVATE KEY-----\nfake\n-----END OPENSSH PRIVATE KEY-----"},
                clear=False,
            ),
            mock.patch.object(resolve_prod_release_state.subprocess, "run", return_value=completed) as mocked_run,
        ):
            resolved = resolve_prod_release_state._run_remote_probe(access)
        self.assertEqual(resolved["from_image"], "img-v1")
        self.assertEqual(resolved["from_config"], "cfg-v1")
        self.assertEqual(resolved["source_host"], "203.0.113.20")
        self.assertEqual(resolved["source_account"], "prod-service-svc")
        mocked_run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
