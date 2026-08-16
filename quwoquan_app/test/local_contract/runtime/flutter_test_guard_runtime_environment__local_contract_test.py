"""Flutter local_contract runner must consume the selected stackctl environment.

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "scripts"
    / "env"
    / "run_flutter_test_guarded.py"
)


def _load_subject():
    spec = importlib.util.spec_from_file_location("run_flutter_test_guarded", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FlutterTestGuardRuntimeEnvironmentContractTest(unittest.TestCase):
    def test_stackctl_environment_selects_the_packaged_runtime(self) -> None:
        subject = _load_subject()
        completed = subprocess.CompletedProcess(
            ["print-app-env"],
            0,
            "--dart-define=APP_RUNTIME_ENV=beta\n",
            "",
        )
        with mock.patch.dict(
            os.environ,
            {"QWQ_APP_RUNTIME_ENV": "beta", "QWQ_DEPLOY_TARGET": "beta-local"},
            clear=False,
        ), mock.patch.object(subject.subprocess, "run", return_value=completed) as run:
            args = subject._with_runtime_environment_defines([])

        self.assertIn("--dart-define=APP_RUNTIME_ENV=beta", args)
        self.assertEqual(run.call_args.args[0][2:4], ["--env", "beta"])
        self.assertEqual(
            run.call_args.args[0][run.call_args.args[0].index("--launch-policy") + 1],
            "test_live",
        )

    def test_explicit_dart_define_overrides_the_process_environment(self) -> None:
        subject = _load_subject()
        completed = subprocess.CompletedProcess(
            ["print-app-env"],
            0,
            "--dart-define=APP_RUNTIME_ENV=gamma\n",
            "",
        )
        with mock.patch.dict(
            os.environ,
            {"QWQ_APP_RUNTIME_ENV": "beta", "QWQ_DEPLOY_TARGET": "gamma-local"},
            clear=False,
        ), mock.patch.object(subject.subprocess, "run", return_value=completed) as run:
            args = subject._with_runtime_environment_defines(
                ["--dart-define=APP_RUNTIME_ENV=gamma"]
            )

        self.assertEqual(args.count("--dart-define=APP_RUNTIME_ENV=gamma"), 1)
        self.assertEqual(run.call_args.args[0][2:4], ["--env", "gamma"])
        self.assertEqual(
            run.call_args.args[0][run.call_args.args[0].index("--launch-policy") + 1],
            "test_live",
        )


if __name__ == "__main__":
    unittest.main()
