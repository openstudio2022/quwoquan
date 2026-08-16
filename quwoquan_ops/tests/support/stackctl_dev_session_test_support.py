"""dev-session 测试共享 helper 与基类（自 test_stackctl_dev_session 拆分）。

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-001
spec_ref: specs/feature-tree/runtime/runtime-config/environment-ops-cli-and-skill/spec.md#gwt-001
"""
from __future__ import annotations

import argparse
import contextlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import stackctl


def _ok(summary: str) -> dict[str, object]:
    return {"exitCode": 0, "summary": summary, "details": [], "reportDir": summary}


def _handoff_completed() -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["build_launcher_handoff.py"],
        returncode=0,
        stdout=json.dumps(
            {
                "launchPolicy": "test_live",
                "contentBindingState": "unbound",
            }
        ),
        stderr="",
    )


def _runtime_started(
    environment: str = "alpha",
    target: str = "alpha-local",
) -> dict[str, object]:
    return {
        "exitCode": 0,
        "blockerKind": "",
        "details": [],
        "runtime": {
            "environment": environment,
            "target": target,
            "composeProject": f"quwoquan_{environment}_test_live",
        },
        "phases": [
            {"name": "mutable-materialize", "exitCode": 0},
            {"name": "compose-render", "exitCode": 0},
            {"name": "compose-up", "exitCode": 0},
        ],
    }


def _runtime_started_with_identity(report_dir: Path) -> dict[str, object]:
    plan: dict[str, object] = {
        "schema": "stackctl.mutable_test_live_runtime",
        "environment": "alpha",
        "target": "alpha-local",
        "composeProject": "quwoquan_alpha_test_live",
        "composeDigest": "sha256:" + "1" * 64,
        "configurationDigest": "sha256:" + "2" * 64,
        "providerRuntimeDigest": "sha256:" + "3" * 64,
        "portProfile": "alpha-local",
        "portBlock": {"start": 17000, "end": 17999},
        "publishedPorts": {"api-edge": 17000},
        "tlsProfile": "local-managed",
        "resolverHandoffDigest": "sha256:" + "4" * 64,
        "publicWebPackage": {
            "environment": "alpha",
            "packageVersion": "web-release-alpha",
            "manifestDigest": "sha256:" + "7" * 64,
            "contentDigest": "sha256:" + "8" * 64,
            "publicOrigin": "https://alpha.quwoquan.com",
        },
        "serviceCoreModules": sorted(stackctl.SERVICE_CORE_MODULE_SET),
        "workspaceIdentity": {
            "sourceRevision": "a" * 40,
            "workspaceStatusDigest": "sha256:" + "5" * 64,
            "mutableStateDigest": "sha256:" + "6" * 64,
        },
    }
    receipt = {
        "schema": "stackctl.mutable_test_live_startup_attempt",
        "launchPolicy": "test_live",
        "nonPromotable": True,
        "contentBindingState": "unbound",
        "attemptId": "alpha-test-live-attempt-1",
        "status": "running",
        "runRoot": str(report_dir),
        **{
            field: plan[field]
            for field in (
                "environment",
                "target",
                "composeProject",
                "composeDigest",
                "configurationDigest",
                "providerRuntimeDigest",
                "portProfile",
                "portBlock",
                "publishedPorts",
                "tlsProfile",
                "resolverHandoffDigest",
                "publicWebPackage",
            )
        },
        "sourceRevision": "a" * 40,
        "workspaceStatusDigest": "sha256:" + "5" * 64,
        "mutableStateDigest": "sha256:" + "6" * 64,
    }
    return {
        "exitCode": 0,
        "blockerKind": "",
        "details": [],
        "runtime": plan,
        "startupAttempt": receipt,
        "phases": [
            {"name": "mutable-materialize", "exitCode": 0},
            {"name": "compose-render", "exitCode": 0},
            {"name": "compose-up", "exitCode": 0},
            {"name": "mutable-startup-running", "exitCode": 0},
        ],
    }




class StackctlDevSessionTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self._mutable_receipt_loader = mock.patch.object(
            stackctl,
            "load_test_live_startup_attempt",
            return_value=None,
        )
        self._mutable_receipt_loader.start()
        self.addCleanup(self._mutable_receipt_loader.stop)
