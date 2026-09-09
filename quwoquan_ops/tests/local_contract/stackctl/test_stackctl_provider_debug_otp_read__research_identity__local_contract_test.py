"""退役白名单参数不得影响普通人工 OTP 的受保护读取。

spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md
spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-033
"""

from __future__ import annotations

import argparse
import io
import json
import unittest
import urllib.error
from types import SimpleNamespace
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.commands import provider_debug
from quwoquan_ops.cli.lib.local_sms_provider_debug import ProtectedDebugOTP

_PHONE_INPUT = "180 1234 5678"
_PHONE = "+8618012345678"
_OTP_CODE = "654321"


class _TtyCapture:
    """关闭上下文后仍可断言 TTY 内容，不接触真实终端。"""

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
        request_id="req-1", expires_at="2026-09-03T05:00:00Z", code=_OTP_CODE
    )


class ProviderDebugOtpReadContractTest(unittest.TestCase):
    def _run(
        self,
        *,
        read_side_effect: object,
        wait_seconds: object = None,
        interactive: bool = True,
    ) -> tuple[dict[str, object], _TtyCapture, mock.Mock, mock.Mock]:
        tty = _TtyCapture()
        read_otp = mock.Mock(side_effect=read_side_effect)
        getpass_prompt = mock.Mock(return_value=_PHONE_INPUT)
        fake_sys = SimpleNamespace(
            stdin=SimpleNamespace(isatty=lambda: interactive),
            stdout=SimpleNamespace(isatty=lambda: interactive),
        )
        args = argparse.Namespace(
            action="otp-read", target="alpha-local", wait_seconds=wait_seconds
        )
        with (
            mock.patch.object(stackctl, "load_environment_topology", return_value={}),
            mock.patch.object(stackctl, "get_target", return_value={"env": "alpha"}),
            mock.patch.object(stackctl, "read_latest_debug_otp", read_otp),
            mock.patch.object(provider_debug.getpass, "getpass", getpass_prompt),
            mock.patch.object(provider_debug, "sys", fake_sys),
            mock.patch.object(provider_debug, "open", tty, create=True),
            mock.patch.object(provider_debug.time, "sleep"),
        ):
            result = provider_debug.command_provider_debug(args)
        return result, tty, read_otp, getpass_prompt

    def test_parser_rejects_retired_identity_and_keeps_wait_budget(self) -> None:
        parser = argparse.ArgumentParser()
        provider_debug.register_parser(parser.add_subparsers(dest="command"))
        base_args = ["provider-debug", "otp-read", "--target", "beta-local"]
        args = parser.parse_args([*base_args, "--wait-seconds", "12.5"])
        self.assertEqual(args.wait_seconds, 12.5)
        self.assertIsNone(parser.parse_args(base_args).wait_seconds)
        with self.assertRaises(SystemExit):
            parser.parse_args([*base_args, "--research-identity"])
        with self.assertRaises(SystemExit):
            parser.parse_args(["provider-debug", "otp-read", "--target", "prod-hosted"])

    def test_wait_budget_is_bounded(self) -> None:
        self.assertEqual(
            provider_debug.resolve_wait_seconds(None), provider_debug.DEFAULT_WAIT_SECONDS
        )
        self.assertEqual(provider_debug.resolve_wait_seconds(45), 45.0)
        for invalid in (0, -1, "abc", True, provider_debug.MAX_WAIT_SECONDS + 1, float("nan")):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                provider_debug.resolve_wait_seconds(invalid)

    def test_default_keeps_hidden_phone_prompt_and_tty_only_otp(self) -> None:
        result, tty, read_otp, getpass_prompt = self._run(read_side_effect=[_otp()])
        self.assertEqual(result["exitCode"], 0, result)
        getpass_prompt.assert_called_once()
        read_otp.assert_called_once()
        self.assertEqual(read_otp.call_args.kwargs["recipient"], _PHONE)
        self.assertLessEqual(
            read_otp.call_args.kwargs["timeout_seconds"], provider_debug.DEFAULT_WAIT_SECONDS
        )
        self.assertIn(f"OTP: {_OTP_CODE}", tty.text)
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertNotIn(_OTP_CODE, serialized)
        self.assertNotIn(_PHONE, serialized)
        self.assertNotIn(_PHONE_INPUT, serialized)
        self.assertTrue(result["provider"]["nonPromotable"])

    def test_ordinary_otp_retries_transient_errors(self) -> None:
        result, tty, read_otp, _prompt = self._run(
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

    def test_timeout_does_not_leak_or_guess_otp(self) -> None:
        result, tty, read_otp, _prompt = self._run(
            wait_seconds=0.001, read_side_effect=_http_not_found()
        )
        self.assertEqual(result["exitCode"], 2, result)
        self.assertIn("no OTP was captured", " ".join(result["details"]))
        self.assertNotIn("OTP:", tty.text)
        self.assertNotIn(_PHONE, json.dumps(result))
        self.assertGreaterEqual(read_otp.call_count, 1)

    def test_non_not_found_http_errors_fail_closed(self) -> None:
        unauthorized = urllib.error.HTTPError(
            "https://127.0.0.1/v1/debug/sms/otp/latest", 401, "Unauthorized", {}, None
        )
        result, _tty, read_otp, _prompt = self._run(read_side_effect=[unauthorized, _otp()])
        self.assertEqual(result["exitCode"], 2, result)
        self.assertEqual(read_otp.call_count, 1)

    def test_non_tty_is_blocked_before_provider_or_input(self) -> None:
        result, tty, read_otp, prompt = self._run(
            interactive=False, read_side_effect=[_otp()]
        )
        self.assertEqual(result["exitCode"], 2, result)
        read_otp.assert_not_called()
        prompt.assert_not_called()
        self.assertEqual(tty.text, "")


if __name__ == "__main__":
    unittest.main()
