from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib import local_environment_auth
from quwoquan_ops.cli.probes import run_environment_integration_probe as probe

ROOT = Path(__file__).resolve().parents[3]
INTERSECTION_SMOKE_RUNNER = (
    ROOT / "quwoquan_app" / "scripts" / "gamma" / "run_intersection_remote_smoke.py"
)


def test_stackctl_does_not_reuse_gamma_token_for_alpha_or_beta() -> None:
    with mock.patch.dict(
        os.environ,
        {"GAMMA_TEST_AUTH_TOKEN": "gamma-secret"},
        clear=True,
    ):
        assert stackctl._resolve_test_auth_token("alpha") == ""
        assert stackctl._resolve_test_auth_token("beta") == ""


def test_integration_probe_does_not_reuse_gamma_token_for_alpha_or_beta() -> None:
    with mock.patch.dict(
        os.environ,
        {"GAMMA_TEST_AUTH_TOKEN": "gamma-secret"},
        clear=True,
    ):
        assert probe._resolve_test_auth_token("alpha", "") == ""
        assert probe._resolve_test_auth_token("beta", "") == ""


def test_environment_specific_token_still_takes_precedence() -> None:
    with mock.patch.dict(
        os.environ,
        {
            "ALPHA_TEST_AUTH_TOKEN": "alpha-secret",
            "BETA_TEST_AUTH_TOKEN": "beta-secret",
            "GAMMA_TEST_AUTH_TOKEN": "gamma-secret",
            "TEST_AUTH_TOKEN": "shared-secret",
        },
        clear=True,
    ):
        assert stackctl._resolve_test_auth_token("alpha") == "alpha-secret"
        assert stackctl._resolve_test_auth_token("beta") == "beta-secret"
        assert stackctl._resolve_test_auth_token("gamma") == "gamma-secret"


def test_intersection_smoke_keeps_acceptance_token_out_of_process_argv() -> None:
    module = runpy.run_path(str(INTERSECTION_SMOKE_RUNNER))
    session = SimpleNamespace(
        owner_id="fixture_user_current",
        persona_id="fixture_user_current",
        access_token="secret-acceptance-token",
    )
    completed = SimpleNamespace(returncode=0)

    with (
        mock.patch.object(
            local_environment_auth,
            "open_local_acceptance_session",
            return_value=session,
        ),
        mock.patch.object(module["subprocess"], "run", return_value=completed) as run,
        mock.patch.object(sys, "argv", ["run_intersection_remote_smoke.py"]),
    ):
        assert module["main"]() == 0

    assert len(run.call_args_list) == 2
    seed_call, smoke_call = run.call_args_list
    seed_command = seed_call.args[0]
    smoke_command = smoke_call.args[0]
    child_environment = smoke_call.kwargs["env"]

    assert any(
        argument.endswith("apply_content_moment_channel_seed.py")
        for argument in seed_command
    )
    assert "--report" in seed_command
    assert "--viewer-id" in seed_command
    assert all(
        "secret-acceptance-token" not in argument
        for call in run.call_args_list
        for argument in call.args[0]
    )
    assert all("secret-acceptance-token" not in argument for argument in smoke_command)
    assert child_environment["LOCAL_GAMMA_ACCEPTANCE_TOKEN"] == "secret-acceptance-token"
