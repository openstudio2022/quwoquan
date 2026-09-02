from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib import release_video_delivery
from quwoquan_ops.cli.probes import run_environment_integration_probe as probe

ROOT = Path(__file__).resolve().parents[4]
INTERSECTION_SMOKE_RUNNER = (
    ROOT / "quwoquan_app" / "scripts" / "tools" / "gamma" / "intersection_remote_smoke.py"
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
            "open_test_data_acceptance_session",
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


def test_health_probe_binds_local_managed_ca_before_reference_auth(
    tmp_path: Path,
) -> None:
    ca_path = tmp_path / "gamma-local-root.crt"
    ca_path.write_text("dummy-ca\n", encoding="utf-8")
    seen_ssl_cert_file: list[str] = []

    def _capture_session(*_args, **_kwargs):
        seen_ssl_cert_file.append(os.environ.get("SSL_CERT_FILE", ""))
        raise RuntimeError("stop after CA capture")

    with (
        mock.patch.object(stackctl, "_resolve_test_auth_token", return_value=""),
        mock.patch.object(
            stackctl,
            "open_test_data_acceptance_session",
            side_effect=_capture_session,
        ),
        mock.patch.object(
            stackctl,
            "root_certificate_path",
            return_value=ca_path,
        ),
    ):
        status, output, findings = stackctl._run_environment_integration_probe(
            stackctl.load_environment_topology(),
            "gamma-local",
            tmp_path,
        )

    assert seen_ssl_cert_file == [str(ca_path)]
    assert status["ok"] is False
    assert "integration auth failed" in output
    assert findings == [output]
    assert "SSL_CERT_FILE" not in os.environ


def test_public_release_readback_does_not_require_candidate_identity(
    tmp_path: Path,
) -> None:
    completed = ({"ok": True}, "passed", [])
    with (
        mock.patch.object(stackctl, "_resolve_test_auth_token", return_value=""),
        mock.patch.object(
            stackctl,
            "open_test_data_acceptance_session",
            side_effect=AssertionError("public release checks must not open identity"),
        ),
        mock.patch.object(
            stackctl,
            "_run_script_probe",
            return_value=completed,
        ) as run_probe,
        mock.patch(
            "quwoquan_ops.cli.lib.public_domain_tls.root_certificate_path",
            return_value=Path("/tmp/gamma-local-root.crt"),
        ),
    ):
        status, output, findings = stackctl._run_environment_integration_probe(
            stackctl.load_environment_topology(),
            "gamma-local",
            tmp_path,
            require_non_empty_content_feed=True,
            only_checks=("content_feed", "video_book_feed", "media_sample"),
        )

    assert status == {"ok": True}
    assert output == "passed"
    assert findings == []
    assert "TEST_AUTH_TOKEN" not in run_probe.call_args.kwargs["env"]


def test_research_consumer_secrets_use_env_not_argv_or_probe_report(
    tmp_path: Path,
) -> None:
    bearer = "research-bearer-secret"
    attestation = "research-attestation-secret"
    completed = ({"ok": True}, "passed", [])
    with (
        mock.patch.object(stackctl, "_resolve_test_auth_token", return_value="ambient"),
        mock.patch.object(stackctl, "_run_script_probe", return_value=completed) as run_probe,
        mock.patch.object(
            stackctl,
            "root_certificate_path",
            return_value=Path("/tmp/alpha-local-root.crt"),
        ),
    ):
        result = stackctl._run_environment_integration_probe(
            stackctl.load_environment_topology(),
            "alpha-local",
            tmp_path,
            research_consumer_token=bearer,
            research_consumer_attestation=attestation,
            release_post_expectations={"content_feed": {"post-a"}},
            only_checks=("content_feed",),
        )

    assert result == completed
    kwargs = run_probe.call_args.kwargs
    rendered_argv = " ".join(kwargs["argv"])
    assert bearer not in rendered_argv
    assert attestation not in rendered_argv
    assert "--test-auth-token" not in kwargs["argv"]
    assert kwargs["env"]["TEST_AUTH_TOKEN"] == bearer
    assert kwargs["env"]["RESEARCH_CONSUMER_ATTESTATION"] == attestation


def test_intersection_smoke_keeps_acceptance_token_out_of_process_argv() -> None:
    module = runpy.run_path(str(INTERSECTION_SMOKE_RUNNER))
    completed = SimpleNamespace(returncode=0)

    with (
        mock.patch.dict(
            os.environ,
            {
                "QWQ_TEST_DATA_ACCESS_TOKEN": "secret-acceptance-token",
                "QWQ_TEST_DATA_OWNER_ID": "typed-owner",
                "QWQ_TEST_DATA_PERSONA_ID": "typed-persona",
            },
            clear=False,
        ),
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
                "intersection_remote_smoke.py",
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

    assert all(
        "secret-acceptance-token" not in argument
        for call in run.call_args_list
        for argument in call.args[0]
    )
    assert all("secret-acceptance-token" not in argument for argument in smoke_command)
    assert child_environment["LOCAL_GAMMA_ACCEPTANCE_TOKEN"] == "secret-acceptance-token"
