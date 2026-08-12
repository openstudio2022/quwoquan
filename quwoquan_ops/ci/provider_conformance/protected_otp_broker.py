"""Ephemeral host/device bridge for one-time nonprod OTP Patrol input."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import ssl
import threading
import time
import urllib.error
from collections.abc import Callable
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from quwoquan_ops.cli.lib.local_provider_substitute_tls import (
    prepare_local_provider_substitute_tls,
)
from quwoquan_ops.cli.lib.local_sms_provider_debug import ProtectedDebugOTP


OTPReader = Callable[..., ProtectedDebugOTP]


@dataclass(frozen=True)
class ProtectedOTPBrokerBinding:
    url: str
    token: str
    ca_digest: str
    certificate_digest: str
    ca_certificate_base64: str = field(repr=False, default="")

    def __repr__(self) -> str:
        return (
            "ProtectedOTPBrokerBinding("
            f"url={self.url!r}, token=<redacted>, "
            f"ca_digest={self.ca_digest!r}, "
            f"certificate_digest={self.certificate_digest!r})"
        )


class ProtectedOTPBroker:
    """Bridge a captured OTP into one Patrol process without files or argv."""

    def __init__(
        self,
        *,
        environment: str,
        target_name: str,
        recipient: str,
        reader: OTPReader,
        read_timeout_seconds: float = 30.0,
        max_consumptions: int = 1,
    ) -> None:
        if environment not in {"alpha", "beta", "gamma"}:
            raise ValueError("protected OTP broker is limited to Alpha/Beta/Gamma")
        if target_name != f"{environment}-local":
            raise ValueError("protected OTP broker target/environment mismatch")
        if re.fullmatch(r"\+[1-9][0-9]{7,14}", recipient) is None:
            raise ValueError("protected OTP broker requires canonical E.164 recipient")
        if read_timeout_seconds <= 0:
            raise ValueError("protected OTP broker requires a positive timeout")
        if (
            isinstance(max_consumptions, bool)
            or max_consumptions < 1
            or max_consumptions > 2
        ):
            raise ValueError(
                "protected OTP broker supports one or two device consumptions"
            )
        self._environment = environment
        self._target_name = target_name
        self._recipient = recipient
        self._reader = reader
        self._read_timeout_seconds = read_timeout_seconds
        self._max_consumptions = max_consumptions
        self._token = secrets.token_urlsafe(32)
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._consumptions = 0

    def start(self) -> ProtectedOTPBrokerBinding:
        if self._server is not None:
            raise RuntimeError("protected OTP broker is already started")
        broker = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                broker._handle(self)

            def log_message(self, _format: str, *args: object) -> None:
                del args

        tls = prepare_local_provider_substitute_tls(
            self._target_name,
            role="protected-otp-broker",
        )
        ca_digest = _sha256_file(tls.ca_path)
        certificate_digest = _sha256_file(tls.certificate_path)
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        try:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version = ssl.TLSVersion.TLSv1_3
            context.load_cert_chain(
                certfile=str(tls.certificate_path),
                keyfile=str(tls.private_key_path),
            )
            self._server.socket = context.wrap_socket(
                self._server.socket,
                server_side=True,
            )
        except (OSError, ssl.SSLError):
            self._server.server_close()
            self._server = None
            raise
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="qwq-protected-otp-broker",
            daemon=True,
        )
        self._thread.start()
        port = int(self._server.server_address[1])
        return ProtectedOTPBrokerBinding(
            url=f"https://127.0.0.1:{port}/v1/otp",
            token=self._token,
            ca_digest=ca_digest,
            certificate_digest=certificate_digest,
            ca_certificate_base64=base64.b64encode(tls.ca_path.read_bytes()).decode(
                "ascii"
            ),
        )

    def close(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None

    def __enter__(self) -> ProtectedOTPBrokerBinding:
        return self.start()

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _handle(self, handler: BaseHTTPRequestHandler) -> None:
        authorization = handler.headers.get("Authorization", "")
        expected = "Bearer " + self._token
        if handler.path != "/v1/otp":
            self._write_json(handler, HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        if not hmac.compare_digest(authorization, expected):
            self._write_json(
                handler,
                HTTPStatus.UNAUTHORIZED,
                {"error": "unauthorized"},
            )
            return
        with self._lock:
            if self._consumptions >= self._max_consumptions:
                self._write_json(
                    handler,
                    HTTPStatus.NOT_FOUND,
                    {"error": "already_consumed"},
                )
                return
            try:
                protected = self._read_captured_otp()
            except (OSError, RuntimeError, ValueError, urllib.error.URLError):
                self._write_json(
                    handler,
                    HTTPStatus.GATEWAY_TIMEOUT,
                    {"error": "otp_unavailable"},
                )
                return
            self._consumptions += 1
        self._write_json(handler, HTTPStatus.OK, {"code": protected.code})

    def _read_captured_otp(self) -> ProtectedDebugOTP:
        deadline = time.monotonic() + self._read_timeout_seconds
        while True:
            try:
                return self._reader(
                    environment=self._environment,
                    target_name=self._target_name,
                    recipient=self._recipient,
                    timeout_seconds=min(3.0, self._read_timeout_seconds),
                )
            except (OSError, RuntimeError, urllib.error.URLError):
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.25)

    @staticmethod
    def _write_json(
        handler: BaseHTTPRequestHandler,
        status: HTTPStatus,
        payload: dict[str, str],
    ) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        handler.send_response(int(status))
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
