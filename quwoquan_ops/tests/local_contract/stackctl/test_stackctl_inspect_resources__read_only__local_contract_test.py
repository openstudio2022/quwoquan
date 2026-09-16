from __future__ import annotations

import contextlib
import json
import os
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.commands import inspect_surface
from quwoquan_ops.cli.lib.orphan_compose_teardown import inventory

# spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-003
# spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-003.t7


class ResourcesInspectTest(unittest.TestCase):
    def invoke(self, containers=(), networks=(), failure=None, environment=None):
        calls = []
        rows = {"container": list(containers), "network": list(networks)}

        def runner(argv, **kwargs):
            calls.append(argv)
            self.assertEqual(kwargs["timeout_seconds"], 15)
            self.assertNotIn("--filter", argv)
            if argv[1:3] == ["context", "inspect"]:
                return subprocess.CompletedProcess(argv, 0, '"unix:///local/docker.sock"', "")
            self.assertEqual(argv[1:3], ["--host", "unix:///local/docker.sock"])
            command = argv[3:]
            key = "container" if command[0] == "ps" else command[0]
            if failure and failure(command):
                return subprocess.CompletedProcess(argv, 1, "SECRET", "SECRET")
            if "inspect" in command:
                output = "\n".join(json.dumps(row) for row in rows[key])
            else:
                output = "\n".join(row["id"] for row in rows[key])
            return subprocess.CompletedProcess(argv, 0, output, "")

        with TemporaryDirectory() as directory, contextlib.ExitStack() as scope:
            scope.enter_context(mock.patch.dict(os.environ, environment or {}, clear=True))
            scope.enter_context(mock.patch.object(stackctl, "run", side_effect=runner))
            scope.enter_context(mock.patch.object(stackctl, "resolve_report_dir", return_value=Path(directory)))
            for name in ("load_startup_attempt", "_candidate_workspace_report", "_read_only_user_availability_report",
                         "_local_stack_operation_lock", "acquire_local_runtime_use_lock", "command_repair", "command_up", "command_down"):
                scope.enter_context(mock.patch.object(stackctl, name, side_effect=AssertionError(name)))
            args = stackctl.build_parser().parse_args(["inspect", "--target", "alpha-local", "--scope", "resources"])
            result = inspect_surface.command_inspect(args)
            report = json.loads((Path(directory) / "report.json").read_text()) if (Path(directory) / "report.json").exists() else result
            self.assertNotIn("SECRET", json.dumps(report))
        return result, report, calls

    def test_empty_without_startup_is_observation_not_admission(self):
        result, report, calls = self.invoke()
        self.assertEqual(result["exitCode"], 0)
        resources = report["inspection"]["resources"]
        self.assertTrue(resources["complete"])
        self.assertFalse(resources["admissionEligible"])
        self.assertEqual(resources["containers"], [])
        self.assertEqual(resources["networks"], [])
        self.assertTrue(calls)

    def test_multiple_projects_unknown_owner_and_states_are_preserved(self):
        containers = [
            {"id": "a" * 64, "name": "/one", "state": "running", "project": "project-one", "service": "api", "worktree": "/work/one", "Env": ["SECRET"]},
            {"id": "b" * 64, "name": "/two", "state": "exited", "project": "project-two", "service": "db", "worktree": ""},
            {"id": "c" * 64, "name": "/unknown", "state": "running", "project": "", "service": "", "worktree": ""},
        ]
        networks = [{"id": "d" * 64, "name": "shared", "project": "project-one", "network": "default", "attachments": {"b" * 64: {"Name": "SECRET"}}}]
        result, report, _ = self.invoke(containers, networks)
        self.assertEqual(result["exitCode"], 0)
        resources = report["inspection"]["resources"]
        self.assertEqual([row["state"] for row in resources["containers"]], ["running", "exited", "running"])
        self.assertEqual(resources["containers"][2]["ownerStatus"], "unknown")
        self.assertEqual(resources["networks"][0]["attachedContainerIds"], ["b" * 64])
        self.assertEqual(len(resources["containers"]), 3)

    def test_partial_failure_is_not_empty_success(self):
        result, report, _ = self.invoke(failure=lambda command: command[0] == "network")
        self.assertNotEqual(result["exitCode"], 0)
        self.assertFalse(report["inspection"]["resources"]["complete"])
        self.assertEqual(report["inspection"]["resources"]["status"], "blocked")

    def test_malformed_json_and_unavailable_daemon_block(self):
        for output, code in (("not-json SECRET", 0), ("SECRET", 1)):
            with self.subTest(code=code), mock.patch.dict(os.environ, {}, clear=True):
                runner = mock.Mock(return_value=subprocess.CompletedProcess([], code, output, "SECRET"))
                report = inventory.observe_host_resources(run_command=runner)
                self.assertEqual(report["status"], "blocked")
                self.assertNotIn("SECRET", json.dumps(report))

    def test_inspect_malformed_partial_and_remote_context_fail_closed(self):
        identity = "a" * 64
        cases = [
            ['"ssh://foreign"'],
            ['"unix:///local/docker.sock"', identity, 'malformed SECRET'],
            ['"unix:///local/docker.sock"', identity, ''],
            ['"unix:///local/docker.sock"', identity, json.dumps({"id": identity, "name": "one", "state": "running"}), ""],
        ]
        for outputs in cases:
            with self.subTest(outputs=len(outputs)), mock.patch.dict(os.environ, {}, clear=True):
                runner = mock.Mock(side_effect=[subprocess.CompletedProcess([], 0, output, "") for output in outputs])
                report = inventory.observe_host_resources(run_command=runner)
                self.assertFalse(report["complete"])
                self.assertEqual(report["status"], "blocked")
                self.assertNotIn("SECRET", json.dumps(report))

    def test_query_templates_never_request_raw_config_or_env(self):
        result, _, calls = self.invoke([
            {"id": "a" * 64, "name": "one", "state": "running", "project": "", "service": "", "worktree": ""}
        ])
        self.assertEqual(result["exitCode"], 0)
        for argv in calls:
            self.assertFalse({"up", "down", "rm", "kill", "stop", "prune", "start"}.intersection(argv))
            self.assertNotIn(".Env", " ".join(argv))
            if "inspect" in argv:
                self.assertIn("--format", argv)
                self.assertNotIn("{{json .}}", argv)

    def test_authority_overrides_rejected_before_queries(self):
        for key, value in (("QWQ_OUTPUT_ROOT", "/foreign"), ("QWQ_HOST_LOCK_ROOT", "/foreign"),
                           ("QWQ_DEPLOY_WORK_ROOT", "/foreign"), ("DOCKER_HOST", "tcp://remote"),
                           ("DOCKER_CONTEXT", "remote"), ("DOCKER_CONFIG", "/foreign"), ("CONTAINER_HOST", "tcp://remote")):
            with self.subTest(key=key):
                result, _, calls = self.invoke(environment={key: value})
                self.assertNotEqual(result["exitCode"], 0)
                self.assertEqual(calls, [])

    def test_hosted_rejected_and_kind_alias(self):
        args = stackctl.build_parser().parse_args(["inspect", "--target", "prod-hosted", "--kind", "resources"])
        self.assertEqual(args.scope, "resources")
        with mock.patch.object(stackctl, "run", side_effect=AssertionError("no query")):
            self.assertNotEqual(inspect_surface.command_inspect(args)["exitCode"], 0)


if __name__ == "__main__":
    unittest.main()
