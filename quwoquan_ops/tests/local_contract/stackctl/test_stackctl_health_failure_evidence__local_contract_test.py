from __future__ import annotations

# spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-002.t3
# spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-002.t4

import argparse
import hashlib
import io
import json
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.commands import up_runtime
from quwoquan_ops.cli.lib import startup_health_failure_evidence


class StackctlHealthFailureEvidenceLocalContractTest(unittest.TestCase):
    def test_health_preserves_full_failed_check_evidence_and_bounded_preview(self) -> None:
        detail = "relay rejected legacy payload " + ("x" * 700)
        body = json.dumps(
            {
                "status": "degraded",
                "failedChecks": [
                    "content-post-deletion-reaction-lifecycle",
                ],
                "checks": {
                    "content-post-deletion-reaction-lifecycle": detail,
                    "mongo": "ok",
                },
            },
            separators=(",", ":"),
        )
        with tempfile.TemporaryDirectory() as temp:
            report_dir = Path(temp) / "health"
            args = argparse.Namespace(
                target="alpha-local",
                scope="full",
                request_timeout_seconds=1,
                retry_attempts=1,
                retry_sleep_seconds=0,
                read_only=True,
                deadline_epoch=0,
            )

            def fetch(_url: str, **kwargs: object) -> tuple[bool, int, str, str]:
                self.assertEqual(kwargs["body_limit"], 65_536)
                return False, 503, body, "application/json"

            with (
                mock.patch.object(
                    stackctl,
                    "resolve_report_dir",
                    return_value=report_dir,
                ),
                mock.patch.object(
                    stackctl,
                    "_health_checks_for_target",
                    return_value=[
                        {
                            "name": "content-health",
                            "scope": "service",
                            "url": "https://content.alpha.invalid/healthz",
                        }
                    ],
                ),
                mock.patch.object(stackctl, "fetch_url", side_effect=fetch),
                mock.patch.object(stackctl, "_write_summary_bundle"),
                mock.patch.object(stackctl, "_write_stdout_markdown"),
                mock.patch.object(stackctl, "relpath", side_effect=str),
            ):
                result = stackctl.command_health(args)

            self.assertEqual(result["exitCode"], 1)
            report = json.loads((report_dir / "report.json").read_text())
            check = report["checks"][0]
            self.assertEqual(len(check["bodyPreview"]), 500)
            self.assertEqual(
                check["bodySha256"],
                "sha256:" + hashlib.sha256(body.encode()).hexdigest(),
            )
            self.assertEqual(
                check["failedChecks"],
                ["content-post-deletion-reaction-lifecycle"],
            )
            self.assertEqual(
                check["failureDetails"],
                {"content-post-deletion-reaction-lifecycle": detail},
            )

    def test_startup_failure_capture_is_candidate_bound_and_full_fidelity(self) -> None:
        detail = "legacy payload rejected before lifecycle convergence"
        body = json.dumps(
            {
                "status": "degraded",
                "failedChecks": [
                    "content-post-deletion-reaction-lifecycle",
                ],
                "checks": {
                    "content-post-deletion-reaction-lifecycle": detail,
                    "mongodb": "ok",
                },
            },
            separators=(",", ":"),
        ).encode()
        candidate = "sha256:" + ("a" * 64)

        def opener(
            request: urllib.request.Request,
            *,
            timeout: float,
        ) -> object:
            self.assertEqual(request.full_url, "http://127.0.0.1:19220/healthz")
            self.assertEqual(timeout, 5.0)
            raise urllib.error.HTTPError(
                request.full_url,
                503,
                "Service Unavailable",
                {},
                io.BytesIO(body),
            )

        with tempfile.TemporaryDirectory() as temp:
            report_dir = Path(temp)
            artifact = report_dir / "startup-health-failure.json"
            captured = startup_health_failure_evidence.capture(
                target="alpha-local",
                candidate_digest=candidate,
                service="content-service",
                url="http://127.0.0.1:19220/healthz",
                output=artifact,
                opener=opener,
            )
            loaded, issue = stackctl._startup_health_failure_for_report(
                report_dir,
                target="alpha-local",
                candidate_digest=candidate,
                startup_exit_code=1,
            )

            self.assertEqual(issue, "")
            self.assertEqual(loaded["failedChecks"], captured["failedChecks"])
            self.assertEqual(loaded["failureDetails"], captured["failureDetails"])
            self.assertEqual(loaded["bodyByteLength"], len(body))
            self.assertEqual(
                loaded["bodySha256"],
                "sha256:" + hashlib.sha256(body).hexdigest(),
            )
            self.assertEqual(loaded["artifactPath"], str(artifact.resolve()))
            self.assertRegex(loaded["artifactSha256"], r"^sha256:[0-9a-f]{64}$")

            with self.assertRaises(
                startup_health_failure_evidence.StartupHealthFailureEvidenceError
            ):
                startup_health_failure_evidence.capture(
                    target="alpha-local",
                    candidate_digest=candidate,
                    service="content-service",
                    url="http://127.0.0.1:19220/healthz",
                    output=artifact,
                    opener=opener,
                )

    def test_startup_failure_artifact_rejects_candidate_drift(self) -> None:
        candidate = "sha256:" + ("b" * 64)
        with tempfile.TemporaryDirectory() as temp:
            report_dir = Path(temp)
            artifact = report_dir / "startup-health-failure.json"
            artifact.write_text(
                json.dumps(
                    {
                        "schema": startup_health_failure_evidence.SCHEMA,
                        "target": "alpha-local",
                        "candidateDigest": candidate,
                        "service": "content-service",
                        "statusCode": 503,
                        "bodyByteLength": 12,
                        "bodySha256": "sha256:" + ("c" * 64),
                        "failedChecks": ["relay"],
                        "failureDetails": {"relay": "failed"},
                    }
                )
            )

            evidence, issue = stackctl._startup_health_failure_for_report(
                report_dir,
                target="alpha-local",
                candidate_digest="sha256:" + ("d" * 64),
                startup_exit_code=1,
            )

            self.assertEqual(evidence, {})
            self.assertIn("identity mismatch", issue)

    def test_startup_script_captures_before_transactional_teardown(self) -> None:
        script = (
            Path(__file__).resolve().parents[4]
            / "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"
        ).read_text(encoding="utf-8")
        cleanup = script.split("cleanup_active_child() {", 1)[1].split(
            "trap cleanup_active_child", 1
        )[0]
        self.assertLess(
            cleanup.index("capture_content_startup_health_failure"),
            cleanup.index("stop_colima_tunnels"),
        )
        self.assertLess(
            cleanup.index("capture_content_startup_health_failure"),
            cleanup.index('down --remove-orphans'),
        )
        self.assertIn(
            'startup-health-failure.json',
            script,
        )
        # up 编排主干已迁往 commands/up_runtime.py;
        # 源码 token 契约随定义位置迁移(_command_up_impl)。
        up_runtime_source = Path(up_runtime.__file__).read_text(encoding="utf-8")
        self.assertIn(
            '"startupHealthFailure": startup_health_failure',
            up_runtime_source,
        )


def test_hosted_health_does_not_read_local_identity_and_preserves_probe_failure(tmp_path):
    from quwoquan_ops.cli.lib import read_only_user_availability as availability
    blocked = {
        "firstBlockerClass": "startup_identity", "firstBlocker": "candidate missing",
        "userAvailability": [{"name": name, "status": "blocked", "issues": ["missing"]} for name in availability.LAYERS],
        "metrics": [], "evidence": {},
    }
    with (
        mock.patch.object(stackctl, "resolve_report_dir", return_value=tmp_path),
        mock.patch.object(stackctl, "_current_runtime_health_scope", side_effect=AssertionError("local scope forbidden")),
        mock.patch.object(stackctl, "read_startup_attempt", side_effect=AssertionError("local receipt forbidden")),
        mock.patch.object(stackctl, "active_deployment_candidate_snapshot", side_effect=AssertionError("local candidate forbidden")),
        mock.patch.object(stackctl, "_read_only_user_availability_report", return_value=blocked) as aggregate,
        mock.patch.object(stackctl, "_health_checks_for_target", return_value=[{"name": "api-health", "scope": "edge", "url": "https://hosted.invalid/healthz"}]),
        mock.patch.object(stackctl, "fetch_url", return_value=(False, 503, "runtime unavailable", "text/plain")) as fetch,
    ):
        result = stackctl.command_health(argparse.Namespace(target="prod-hosted", read_only=True, deployment_instance="prevalidate", candidate_digest="sha256:" + "a" * 64, host_id="selected", ssh_host="hosted.invalid"))
    assert fetch.call_count == 1
    assert aggregate.call_args.kwargs["deployment_instance"] == "prevalidate"
    assert aggregate.call_args.kwargs["host_id"] == "selected"
    assert result["firstBlockerClass"] == "health_probe"
    assert "503" in result["firstBlocker"]
    assert result["availabilityFirstBlockerClass"] == "startup_identity"
    assert result["evidenceEnvelope"]["startupAttemptId"]["status"] == "not_applicable"
    persisted = json.loads((tmp_path / "report.json").read_text())
    assert persisted["checks"][0]["statusCode"] == 503


def test_health_empty_or_entirely_skipped_probe_set_never_passes(tmp_path):
    from quwoquan_ops.cli.lib import read_only_user_availability as availability
    ready = {"firstBlockerClass": "none", "firstBlocker": "", "metrics": [], "evidence": {}, "userAvailability": [{"name": name, "status": "ready", "issues": []} for name in availability.LAYERS]}
    for checks in ([], [{"name": "skip", "scope": "service", "url": "", "skip": True}]):
        with (
            mock.patch.object(stackctl, "resolve_report_dir", return_value=tmp_path),
            mock.patch.object(stackctl, "_health_checks_for_target", return_value=checks),
            mock.patch.object(stackctl, "_read_only_user_availability_report", return_value=ready),
            mock.patch.object(stackctl, "active_deployment_candidate_snapshot", return_value=None),
            mock.patch.object(stackctl, "read_startup_attempt", return_value=None),
            mock.patch.object(stackctl, "fetch_url", side_effect=AssertionError("no real probe selected")),
        ):
            result = stackctl.command_health(argparse.Namespace(target="gamma-local", scope="service", read_only=True))
        assert result["exitCode"] == 1
        assert "probe evidence is empty" in result["firstBlocker"]


if __name__ == "__main__":
    unittest.main()
