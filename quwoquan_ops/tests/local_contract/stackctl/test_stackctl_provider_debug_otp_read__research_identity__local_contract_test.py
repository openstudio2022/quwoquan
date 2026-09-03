"""`stackctl provider-debug otp-read` 是唯一的人工 OTP 读取面。

spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md
spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/four-environment-commercial-login-maturity/spec.md#req-002

`--research-identity` 只替换手机号来源（Research 白名单绑定，而非交互隐藏
输入），手机号与 OTP 仍只写当前 TTY，不进入 argv、命令 JSON、日志或 receipt。
"""

from __future__ import annotations

import argparse
import io
import json
import re
import unittest
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.commands import provider_debug
from quwoquan_ops.cli.lib import local_environment_auth
from quwoquan_ops.cli.lib.local_sms_provider_debug import ProtectedDebugOTP

ROOT = Path(__file__).resolve().parents[4]
_RESEARCH_PHONE = "+8619912345000"
_OTP_CODE = "654321"
_BINDING = {
    "schema": "qwq.local_research_identity_binding.v1",
    "environment": "alpha",
    "target": "alpha-local",
    "phone": _RESEARCH_PHONE,
    "subjectHash": "sha256:" + "0" * 64,
    "accountId": "uo_01_ph_0000_research",
}


class _TtyCapture:
    """`with open("/dev/tty", "w")` 的替身；关闭后仍可读取写入内容。"""

    def __init__(self) -> None:
        self.buffer = io.StringIO()

    def __call__(self, path: str, mode: str = "r", **_kwargs: object) -> "_TtyCapture":
        if path != "/dev/tty" or mode != "w":
            raise AssertionError(f"unexpected open({path!r}, {mode!r})")
        return self

    def __enter__(self) -> io.StringIO:
        return self.buffer

    def __exit__(self, *_exc: object) -> None:
        return None

    @property
    def text(self) -> str:
        return self.buffer.getvalue()


def _http_not_found() -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://127.0.0.1/v1/debug/sms/otp/latest", 404, "Not Found", {}, None
    )


def _otp() -> ProtectedDebugOTP:
    return ProtectedDebugOTP(
        request_id="req-1",
        expires_at="2026-09-03T05:00:00Z",
        code=_OTP_CODE,
    )


class ProviderDebugOtpReadResearchIdentityContractTest(unittest.TestCase):
    def _run(
        self,
        *,
        research_identity: bool,
        wait_seconds: object = None,
        interactive: bool = True,
        read_side_effect: object,
        phone_input: str = "",
    ) -> tuple[dict[str, object], _TtyCapture, mock.Mock, mock.Mock, mock.Mock]:
        tty = _TtyCapture()
        read_otp = mock.Mock(side_effect=read_side_effect)
        load_binding = mock.Mock(return_value=dict(_BINDING))
        getpass_prompt = mock.Mock(return_value=phone_input)
        fake_sys = SimpleNamespace(
            stdin=SimpleNamespace(isatty=lambda: interactive),
            stdout=SimpleNamespace(isatty=lambda: interactive),
        )
        args = argparse.Namespace(
            action="otp-read",
            target="alpha-local",
            research_identity=research_identity,
            wait_seconds=wait_seconds,
        )
        with (
            mock.patch.object(stackctl, "load_environment_topology", return_value={}),
            mock.patch.object(stackctl, "get_target", return_value={"env": "alpha"}),
            mock.patch.object(stackctl, "read_latest_debug_otp", read_otp),
            mock.patch.object(
                local_environment_auth,
                "load_local_research_identity_binding",
                load_binding,
            ),
            mock.patch.object(provider_debug.getpass, "getpass", getpass_prompt),
            mock.patch.object(provider_debug, "sys", fake_sys),
            mock.patch.object(provider_debug, "open", tty, create=True),
            mock.patch.object(provider_debug.time, "sleep"),
        ):
            result = provider_debug.command_provider_debug(args)
        return result, tty, read_otp, load_binding, getpass_prompt

    def test_parser_registers_research_identity_and_wait_budget(self) -> None:
        parser = argparse.ArgumentParser()
        provider_debug.register_parser(parser.add_subparsers(dest="command"))
        args = parser.parse_args(
            [
                "provider-debug",
                "otp-read",
                "--target",
                "beta-local",
                "--research-identity",
                "--wait-seconds",
                "12.5",
            ]
        )
        self.assertTrue(args.research_identity)
        self.assertEqual(args.wait_seconds, 12.5)
        defaults = parser.parse_args(["provider-debug", "otp-read", "--target", "beta-local"])
        self.assertFalse(defaults.research_identity)
        self.assertIsNone(defaults.wait_seconds)
        with self.assertRaises(SystemExit):
            parser.parse_args(["provider-debug", "otp-read", "--target", "prod-hosted"])

    def test_wait_budget_defaults_by_mode_and_is_bounded(self) -> None:
        self.assertEqual(
            provider_debug.resolve_wait_seconds(None, research_identity=False),
            provider_debug.DEFAULT_WAIT_SECONDS,
        )
        self.assertEqual(
            provider_debug.resolve_wait_seconds(None, research_identity=True),
            provider_debug.RESEARCH_IDENTITY_DEFAULT_WAIT_SECONDS,
        )
        self.assertEqual(provider_debug.resolve_wait_seconds(45, research_identity=True), 45.0)
        for invalid in (0, -1, "abc", True, provider_debug.MAX_WAIT_SECONDS + 1, float("nan")):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                provider_debug.resolve_wait_seconds(invalid, research_identity=True)

    def test_research_identity_displays_phone_and_otp_only_on_tty(self) -> None:
        result, tty, read_otp, load_binding, getpass_prompt = self._run(
            research_identity=True,
            read_side_effect=[_otp()],
        )
        self.assertEqual(result["exitCode"], 0, result)
        getpass_prompt.assert_not_called()
        load_binding.assert_called_once_with(environment="alpha", target_name="alpha-local")
        read_otp.assert_called_once()
        self.assertEqual(read_otp.call_args.kwargs["recipient"], _RESEARCH_PHONE)
        self.assertEqual(read_otp.call_args.kwargs["environment"], "alpha")
        self.assertEqual(read_otp.call_args.kwargs["target_name"], "alpha-local")
        self.assertIn(f"Research phone (alpha-local): {_RESEARCH_PHONE}", tty.text)
        self.assertIn(f"OTP: {_OTP_CODE}", tty.text)
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertNotIn(_OTP_CODE, serialized)
        self.assertNotIn(_RESEARCH_PHONE, serialized)
        self.assertNotIn(_RESEARCH_PHONE.removeprefix("+86"), serialized)
        self.assertIn("recipient=research_identity_binding", " ".join(result["details"]))
        self.assertEqual(result["provider"]["nonPromotable"], True)

    def test_research_identity_polls_through_not_found_and_transient_errors(self) -> None:
        result, tty, read_otp, _load_binding, _getpass_prompt = self._run(
            research_identity=True,
            wait_seconds=30,
            read_side_effect=[
                _http_not_found(),
                urllib.error.URLError("handshake operation timed out"),
                RuntimeError("protected OTP readback timed out"),
                _otp(),
            ],
        )
        self.assertEqual(result["exitCode"], 0, result)
        self.assertEqual(read_otp.call_count, 4)
        self.assertIn(f"OTP: {_OTP_CODE}", tty.text)

    def test_research_identity_times_out_without_leaking_or_guessing(self) -> None:
        result, tty, read_otp, _load_binding, _getpass_prompt = self._run(
            research_identity=True,
            wait_seconds=0.001,
            read_side_effect=_http_not_found(),
        )
        self.assertEqual(result["exitCode"], 2, result)
        self.assertIn("no OTP was captured", " ".join(result["details"]))
        self.assertNotIn("OTP:", tty.text)
        self.assertIn(_RESEARCH_PHONE, tty.text)
        self.assertNotIn(_RESEARCH_PHONE, json.dumps(result))
        self.assertGreaterEqual(read_otp.call_count, 1)

    def test_non_not_found_http_errors_fail_closed_immediately(self) -> None:
        unauthorized = urllib.error.HTTPError(
            "https://127.0.0.1/v1/debug/sms/otp/latest", 401, "Unauthorized", {}, None
        )
        result, _tty, read_otp, _load_binding, _getpass_prompt = self._run(
            research_identity=True,
            wait_seconds=30,
            read_side_effect=[unauthorized, _otp()],
        )
        self.assertEqual(result["exitCode"], 2, result)
        self.assertEqual(read_otp.call_count, 1)

    def test_non_tty_is_blocked_before_touching_binding_or_provider(self) -> None:
        result, tty, read_otp, load_binding, getpass_prompt = self._run(
            research_identity=True,
            interactive=False,
            read_side_effect=[_otp()],
        )
        self.assertEqual(result["exitCode"], 2, result)
        self.assertIn("interactive TTY", " ".join(result["details"]))
        load_binding.assert_not_called()
        read_otp.assert_not_called()
        getpass_prompt.assert_not_called()
        self.assertEqual(tty.text, "")

    def test_default_mode_keeps_hidden_phone_prompt_and_short_budget(self) -> None:
        result, tty, read_otp, load_binding, getpass_prompt = self._run(
            research_identity=False,
            read_side_effect=[_otp()],
            phone_input="180 1234 5678",
        )
        self.assertEqual(result["exitCode"], 0, result)
        getpass_prompt.assert_called_once()
        load_binding.assert_not_called()
        self.assertEqual(read_otp.call_args.kwargs["recipient"], "+8618012345678")
        self.assertLessEqual(
            read_otp.call_args.kwargs["timeout_seconds"],
            provider_debug.DEFAULT_WAIT_SECONDS,
        )
        self.assertNotIn("Research phone", tty.text)
        self.assertIn(f"OTP: {_OTP_CODE}", tty.text)
        self.assertNotIn(_OTP_CODE, json.dumps(result))

    def test_make_shortcut_forwards_research_identity_and_wait_budget(self) -> None:
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        recipe_start = makefile.index("\nstackctl-otp-read:")
        recipe = makefile[recipe_start : makefile.index("\nstackctl-deploy:")]
        self.assertIn(
            'provider-debug otp-read --target "$(TARGET)"',
            recipe,
        )
        self.assertIn("$(if $(RESEARCH_IDENTITY),--research-identity,)", recipe)
        self.assertIn('$(if $(WAIT_SECONDS),--wait-seconds "$(WAIT_SECONDS)",)', recipe)
        # Make 只做薄转发，不得自持手机号、OTP 或第二套读取逻辑。
        self.assertIsNone(re.search(r"\+?86?1[0-9]{10}", recipe))
        self.assertNotIn("debug/sms/otp", recipe)


if __name__ == "__main__":
    unittest.main()
