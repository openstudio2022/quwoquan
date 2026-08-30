"""dev-session 测试共享 helper 与基类（自 test_stackctl_dev_session 拆分）。

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-001
spec_ref: specs/feature-tree/runtime/runtime-config/environment-ops-cli-and-skill/spec.md#gwt-001
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
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


def _mutable_unfinalized_runtime_plan(
    environment: str = "alpha",
    target: str = "alpha-local",
) -> dict[str, object]:
    return {
        "schema": "stackctl.mutable_test_live_runtime",
        "environment": environment,
        "target": target,
        "composeProject": f"quwoquan_{environment}_test_live",
        "composeDigest": "sha256:" + "1" * 64,
        "configurationDigest": "sha256:" + "2" * 64,
        "portProfile": target,
    }


def _mutable_compose_model(environment: str = "alpha") -> dict[str, object]:
    target = f"{environment}-local"
    ports = stackctl.profile_ports(stackctl.load_port_manifest(), target)
    return {
        "services": {
            "product-ops-service": {
                "ports": [
                    {
                        "target": 18086,
                        "published": str(ports["product-ops-service"]),
                        "protocol": "tcp",
                    }
                ]
            }
        }
    }


def _mutable_compose_config_json(environment: str = "alpha") -> str:
    return json.dumps(_mutable_compose_model(environment))


def _mutable_teardown_receipt(
    run_root: Path,
    *,
    status: str = "running",
) -> dict[str, object]:
    return {
        "schema": "stackctl.mutable_test_live_startup_attempt",
        "launchPolicy": "test_live",
        "nonPromotable": True,
        "contentBindingState": "unbound",
        "attemptId": "alpha-test-live-attempt-1",
        "environment": "alpha",
        "target": "alpha-local",
        "status": status,
        "workload": "full",
        "composeProject": "quwoquan_alpha_test_live",
        "composeDigest": "sha256:" + "1" * 64,
        "configurationDigest": "sha256:" + "2" * 64,
        "providerRuntimeDigest": "sha256:" + "3" * 64,
        "portProfile": "alpha-local",
        "portBlock": {"start": 17000, "end": 17999},
        "publishedPorts": [
            {"role": "api-edge", "hostPort": 17000, "protocol": "tcp"}
        ],
        "tlsProfile": "local-managed",
        "resolverHandoffDigest": "sha256:" + "4" * 64,
        "publicWebPackage": {
            "environment": "alpha",
            "packageVersion": "web-release-alpha",
            "manifestDigest": "sha256:" + "7" * 64,
            "contentDigest": "sha256:" + "8" * 64,
            "publicOrigin": "https://alpha.quwoquan.com:17000",
        },
        "sourceRevision": "a" * 40,
        "workspaceStatusDigest": "sha256:" + "5" * 64,
        "mutableStateDigest": "sha256:" + "6" * 64,
        "runRoot": str(run_root),
        "startedAt": "2026-08-10T12:00:00Z",
        "updatedAt": "2026-08-10T12:00:01Z",
        "failure": None,
    }


def _mutable_teardown_down_args(
    report_dir: Path,
    *,
    target: str = "alpha-local",
) -> argparse.Namespace:
    return argparse.Namespace(
        target=target,
        workload="full",
        formal_release=False,
        release_manifest="",
        purge_rebuildable_state=False,
        report_dir=str(report_dir),
    )


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
        "publishedPorts": [
            {
                "role": "product-ops-service",
                "hostPort": 17250,
                "protocol": "tcp",
            }
        ],
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




class StackctlMutableTeardownTestBase(unittest.TestCase):
    def setUp(self) -> None:
        isolated_output_root = tempfile.mkdtemp(prefix="qwq-teardown-test-output-")
        self.addCleanup(shutil.rmtree, isolated_output_root, ignore_errors=True)
        environment = mock.patch.dict(
            os.environ,
            {"QWQ_OUTPUT_ROOT": isolated_output_root},
        )
        environment.start()
        self.addCleanup(environment.stop)


class StackctlDevSessionTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self._mutable_receipt_loader = mock.patch.object(
            stackctl,
            "load_test_live_startup_attempt",
            return_value=None,
        )
        self._mutable_receipt_loader.start()
        self.addCleanup(self._mutable_receipt_loader.stop)
