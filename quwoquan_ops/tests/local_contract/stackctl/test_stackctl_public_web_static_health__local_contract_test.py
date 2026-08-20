from __future__ import annotations

# spec_ref: specs/feature-tree/runtime/runtime-client-foundation/public-content-web-entry/spec.md#gwt-005

import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.commands.diagnostics_shared import (
    PUBLIC_WEB_STATIC_SCOPE,
    _public_web_static_health_checks,
)

_ORIGIN = "https://alpha.quwoquan.com:17000"


def _api_check() -> dict[str, object]:
    return {
        "name": "api-health",
        "scope": "edge",
        "url": "https://api.alpha.quwoquan.com/healthz",
    }


class PublicWebStaticHealthLocalContractTest(unittest.TestCase):
    def test_static_probes_cover_shell_script_worker_and_chinese_font(self) -> None:
        checks = _public_web_static_health_checks({"publicWeb": _ORIGIN + "/"})

        self.assertEqual(
            [item["url"] for item in checks],
            [
                _ORIGIN + "/index.html",
                _ORIGIN + "/main.dart.js",
                _ORIGIN + "/flutter_service_worker.js",
                _ORIGIN
                + "/assets/assets/fonts/noto_sans_sc/NotoSansSC%5Bwght%5D.ttf",
            ],
        )
        self.assertEqual(
            {item["scope"] for item in checks},
            {PUBLIC_WEB_STATIC_SCOPE},
        )
        self.assertTrue(all(item["expectedStatus"] == 200 for item in checks))
        by_name = {str(item["name"]): item for item in checks}
        self.assertEqual(
            by_name["public-web-shell"]["expectedContentTypePrefix"],
            "text/html",
        )
        self.assertEqual(
            by_name["public-web-font"]["expectedContentTypePrefix"],
            "font/ttf",
        )
        # 缺少 publicWeb 是缺席，不是失败：不合成假探针。
        self.assertEqual(_public_web_static_health_checks({}), [])

    def test_static_surface_stays_ok_when_the_whole_api_plane_is_down(self) -> None:
        report = self._run_health(
            checks=[_api_check(), *_public_web_static_health_checks({"publicWeb": _ORIGIN})],
            failing_urls={"https://api.alpha.quwoquan.com/healthz"},
        )

        self.assertEqual(report["surfaces"]["api"]["status"], "failed")
        self.assertEqual(report["surfaces"]["api"]["firstBlocker"], "edge/api-health")
        self.assertEqual(report["surfaces"]["publicWeb"]["status"], "ok")
        self.assertEqual(report["surfaces"]["publicWeb"]["firstBlocker"], "")
        self.assertEqual(
            report["surfaces"]["publicWeb"]["checks"],
            [
                "public-web-shell",
                "public-web-main",
                "public-web-service-worker",
                "public-web-font",
            ],
        )

    def test_missing_recovery_web_reports_the_typed_blocker(self) -> None:
        report = self._run_health(
            checks=[_api_check(), *_public_web_static_health_checks({"publicWeb": _ORIGIN})],
            failing_urls={_ORIGIN + "/index.html"},
        )

        self.assertEqual(report["surfaces"]["api"]["status"], "ok")
        self.assertEqual(report["surfaces"]["publicWeb"]["status"], "failed")
        self.assertEqual(
            report["surfaces"]["publicWeb"]["firstBlocker"],
            "APP.WEB.recovery_unavailable",
        )

    def test_unobserved_surface_is_absent_not_healthy(self) -> None:
        report = self._run_health(checks=[_api_check()], failing_urls=set())

        self.assertEqual(report["surfaces"]["publicWeb"]["status"], "not_observed")
        self.assertEqual(report["surfaces"]["publicWeb"]["checks"], [])

    def _run_health(
        self,
        *,
        checks: list[dict[str, object]],
        failing_urls: set[str],
    ) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as temporary:
            report_dir = Path(temporary) / "health"
            args = argparse.Namespace(
                target="alpha-local",
                scope="edge",
                request_timeout_seconds=1,
                retry_attempts=1,
                retry_sleep_seconds=0,
                read_only=True,
                deadline_epoch=0,
            )

            def fetch(url: str, **_kwargs: object) -> tuple[bool, int, str, str]:
                if url in failing_urls:
                    return False, 503, "unavailable", "text/plain"
                if url.endswith(".ttf"):
                    return True, 200, "font-bytes", "font/ttf"
                if url.endswith(".html"):
                    return True, 200, "<html lang=\"zh-CN\">", "text/html; charset=utf-8"
                return True, 200, "ok", "application/javascript"

            with (
                mock.patch.object(
                    stackctl,
                    "resolve_report_dir",
                    return_value=report_dir,
                ),
                mock.patch.object(
                    stackctl,
                    "_health_checks_for_target",
                    return_value=checks,
                ),
                mock.patch.object(stackctl, "fetch_url", side_effect=fetch),
                mock.patch.object(stackctl, "_write_summary_bundle"),
                mock.patch.object(stackctl, "_write_stdout_markdown"),
                mock.patch.object(stackctl, "relpath", side_effect=str),
            ):
                stackctl.command_health(args)
            return json.loads((report_dir / "report.json").read_text())


if __name__ == "__main__":
    unittest.main()
