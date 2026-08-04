"""Protected in-process OTP readback for local Debug UAT only."""

from __future__ import annotations

import hashlib
import json
import re
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from .environment_topology import get_target, load_environment_topology
from .local_environment_auth import load_local_environment_auth
from .port_manifest import load_port_manifest, profile_ports
from .public_domain_tls import root_certificate_path


@dataclass(frozen=True)
class ProtectedDebugOTP:
    request_id: str
    expires_at: str
    code: str = field(repr=False)


def read_latest_debug_otp(
    *,
    environment: str,
    target_name: str,
    recipient: str,
    timeout_seconds: float = 3.0,
) -> ProtectedDebugOTP:
    """Return one OTP in process memory without writing it to receipts or logs.

    SMS delivery is async through integration-service, so this polls the
    protected capture endpoint until the OTP appears or the budget expires.
    """

    if environment not in {"alpha", "beta", "gamma"}:
        raise ValueError("protected Debug OTP read is limited to Alpha/Beta/Gamma")
    if target_name != f"{environment}-local":
        raise ValueError("protected Debug OTP target/environment mismatch")
    if re.fullmatch(r"\+[1-9][0-9]{7,14}", recipient) is None:
        raise ValueError("protected Debug OTP recipient must be canonical E.164")

    target = get_target(load_environment_topology(), target_name)
    auth = load_local_environment_auth(environment, target_name)
    port = profile_ports(
        load_port_manifest(),
        str(target["portProfile"]),
    )["sms-provider-substitute"]
    recipient_digest = "sha256:" + hashlib.sha256(
        recipient.encode("utf-8")
    ).hexdigest()
    body = json.dumps(
        {
            "environment": environment,
            "recipientDigest": recipient_digest,
        },
        separators=(",", ":"),
    ).encode("utf-8")
    context = ssl.create_default_context(
        cafile=str(root_certificate_path(target_name))
    )
    deadline = time.monotonic() + max(1.0, timeout_seconds)
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        request = urllib.request.Request(
            f"https://127.0.0.1:{port}/v1/debug/sms/otp/latest",
            data=body,
            method="POST",
            headers={
                "Authorization": "Bearer "
                + auth.environment["SMS_SUBSTITUTE_OPERATOR_TOKEN"],
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=min(5.0, max(0.5, deadline - time.monotonic())),
                context=context,
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code != 404:
                raise
            time.sleep(0.25)
            continue
        code = str(payload.get("code") or "")
        request_id = str(payload.get("requestId") or "").strip()
        expires_at = str(payload.get("expiresAt") or "").strip()
        if re.fullmatch(r"[0-9]{6}", code) is None or not request_id or not expires_at:
            raise RuntimeError("protected OTP readback is invalid")
        return ProtectedDebugOTP(
            request_id=request_id,
            expires_at=expires_at,
            code=code,
        )
    if last_error is not None:
        raise last_error
    raise RuntimeError("protected OTP readback timed out")
