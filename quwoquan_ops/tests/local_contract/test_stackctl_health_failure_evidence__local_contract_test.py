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
            Path(__file__).resolve().parents[3]
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
        stackctl_source = Path(stackctl.__file__).read_text(encoding="utf-8")
        self.assertIn(
            '"startupHealthFailure": startup_health_failure',
            stackctl_source,
        )


if __name__ == "__main__":
    unittest.main()
