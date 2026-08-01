from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib import local_environment_auth
from quwoquan_ops.cli.lib import release_video_delivery
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


def test_health_probe_records_unreadable_local_auth_as_gate_block(
    tmp_path: Path,
) -> None:
    with (
        mock.patch.object(stackctl, "_resolve_test_auth_token", return_value=""),
        mock.patch.object(
            stackctl,
            "open_reference_acceptance_session",
            side_effect=PermissionError("auth directory is not readable"),
        ),
    ):
        status, output, findings = stackctl._run_environment_integration_probe(
            stackctl.load_environment_topology(),
            "beta-local",
            tmp_path,
        )

    assert status["ok"] is False
    assert status["statusCode"] == 1
    assert "integration auth failed" in output
    assert findings == [output]


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
            "open_reference_acceptance_session",
            return_value=session,
        ) as open_session,
        mock.patch.object(
            release_video_delivery,
            "resolve_readiness_path",
            return_value=Path("/tmp/release-readiness.json"),
        ),
        mock.patch.object(
            release_video_delivery,
            "load_release_content_identity",
            return_value={
                "releaseId": "release-a",
                "importRunId": "import-gamma-a",
                "receipt": {
                    "feedQueries": [
                        {
                            "name": "discovery_work",
                            "matchedPostIds": ["post-a"],
                        },
                    ],
                },
                "postBindings": [
                    {
                        "postId": "post-a",
                        "authorId": "release-author-a",
                    },
                ],
            },
        ),
        mock.patch.object(module["subprocess"], "run", return_value=completed) as run,
        mock.patch.object(
            sys,
            "argv",
            [
                "run_intersection_remote_smoke.py",
                "--base-url",
                "http://127.0.0.1:19220",
                "--release-readiness",
                "env/gamma/runs/data-release/release-a/verify-a/release-readiness.json",
            ],
        ),
    ):
        assert module["main"]() == 0

    assert len(run.call_args_list) == 1
    smoke_call = run.call_args_list[0]
    smoke_command = smoke_call.args[0]
    child_environment = smoke_call.kwargs["env"]

    assert open_session.call_args.kwargs == {
        "environment": "gamma",
        "target_name": "gamma-local",
    }
    assert all(
        "secret-acceptance-token" not in argument
        for call in run.call_args_list
        for argument in call.args[0]
    )
    assert all("secret-acceptance-token" not in argument for argument in smoke_command)
    assert child_environment["LOCAL_GAMMA_ACCEPTANCE_TOKEN"] == "secret-acceptance-token"
