"""Run the B10 two-device Remote journey for local-substitute Providers."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Any
import urllib.error
import urllib.request
import uuid


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.environment_topology import (  # noqa: E402
    get_target,
    load_environment_topology,
)


_TARGETS = {
    "alpha": "alpha-local",
    "beta": "beta-local",
}
_PATROL_TARGET = (
    "test/user_acceptance/patrol/rtc/"
    "b10_fixture_call_provider__user_acceptance_test.dart"
)


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _request_json(
    *,
    base_url: str,
    method: str,
    path: str,
    token: str,
    owner_id: str,
    persona_id: str,
    body: dict[str, Any] | None = None,
    idempotency_key: str = "",
) -> dict[str, Any]:
    payload = None
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "X-Client-Page-Id": "rtc.provider.b10.fixture_uat",
        "X-Client-User-Id": owner_id,
        "X-Client-Sub-Account-Id": persona_id,
        "X-Request-Id": f"B10.{uuid.uuid4().hex}",
        "X-Trace-Id": f"B10.{uuid.uuid4().hex}",
    }
    if body is not None:
        payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=payload,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        exc.read()
        raise ValueError(
            f"B10 fixture API request failed: {method} {path} HTTP {exc.code}"
        ) from exc
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"B10 fixture API response is not JSON: {method} {path}"
        ) from exc
    if not isinstance(decoded, dict):
        raise ValueError(f"B10 fixture API response is not an object: {path}")
    return decoded


def _find_string(value: object, keys: frozenset[str]) -> str:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in keys and isinstance(nested, str) and nested.strip():
                return nested.strip()
        for nested in value.values():
            found = _find_string(nested, keys)
            if found:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = _find_string(nested, keys)
            if found:
                return found
    return ""


def _role_environment(
    *,
    role: str,
    call_id: str,
    device_id: str,
    token: str,
    refresh_token: str,
    owner_id: str,
    persona_id: str,
    result_path: Path,
) -> dict[str, str]:
    environment = dict(os.environ)
    environment.update(
        {
            "QWQ_PROVIDER_CONFORMANCE_DEVICE_ID": device_id,
            "QWQ_PROVIDER_CONFORMANCE_RESULT_PATH": str(result_path),
            "QWQ_PROVIDER_UAT_B10_ROLE": role,
            "QWQ_PROVIDER_UAT_B10_CALL_ID": call_id,
            "TEST_AUTH_TOKEN": token,
            "TEST_REFRESH_TOKEN": refresh_token,
            "APP_CURRENT_OWNER_ID": owner_id,
            "APP_CURRENT_SUB_ACCOUNT_ID": persona_id,
        }
    )
    return environment


def _patrol_command(platform: str) -> list[str]:
    return [
        sys.executable,
        "quwoquan_ops/ci/provider_conformance/run_provider_patrol_uat.py",
        "--target",
        _PATROL_TARGET,
        "--platform",
        platform,
        "--define-key",
        "QWQ_PROVIDER_UAT_B10_ROLE",
        "--define-key",
        "QWQ_PROVIDER_UAT_B10_CALL_ID",
    ]


def _wait_process(
    process: subprocess.Popen[str],
    *,
    role: str,
    timeout_seconds: int,
) -> str:
    try:
        output, _ = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        process.terminate()
        output, _ = process.communicate(timeout=15)
        raise ValueError(f"B10 fixture {role} Patrol timed out") from exc
    if process.returncode != 0:
        raise ValueError(f"B10 fixture {role} Patrol failed")
    return output or ""


def main() -> int:
    environment = _required("QWQ_PROVIDER_CONFORMANCE_ENVIRONMENT")
    try:
        target_name = _TARGETS[environment]
    except KeyError as exc:
        raise ValueError(
            "B10 fixture UAT only supports Alpha/Beta substitutes"
        ) from exc
    target = get_target(load_environment_topology(), target_name)
    public_bases = target.get("publicBases")
    if not isinstance(public_bases, dict):
        raise ValueError(f"{target_name} publicBases are required")
    api_base = str(public_bases.get("api") or "").strip()
    if not api_base:
        raise ValueError(f"{target_name} publicBases.api is required")

    caller_token = _required("QWQ_B10_CALLER_AUTH_TOKEN")
    caller_refresh = _required("QWQ_B10_CALLER_REFRESH_TOKEN")
    caller_owner = _required("QWQ_B10_CALLER_OWNER_ID")
    caller_persona = _required("QWQ_B10_CALLER_PERSONA_ID")
    callee_token = _required("QWQ_B10_CALLEE_AUTH_TOKEN")
    callee_refresh = _required("QWQ_B10_CALLEE_REFRESH_TOKEN")
    callee_owner = _required("QWQ_B10_CALLEE_OWNER_ID")
    callee_persona = _required("QWQ_B10_CALLEE_PERSONA_ID")
    conversation_id = _required("QWQ_B10_CONVERSATION_ID")
    ios_device = _required("QWQ_B10_IOS_DEVICE_ID")
    android_device = _required("QWQ_B10_ANDROID_DEVICE_ID")

    initiated = _request_json(
        base_url=api_base,
        method="POST",
        path="/rtc/calls",
        token=caller_token,
        owner_id=caller_owner,
        persona_id=caller_persona,
        idempotency_key=f"b10-fixture-{uuid.uuid4().hex}",
        body={
            "callType": "video",
            "inviteeIds": [callee_persona],
            "conversationId": conversation_id,
            "maxParticipants": 2,
        },
    )
    call_id = _find_string(initiated, frozenset({"callId", "id"}))
    if not call_id:
        raise ValueError("B10 fixture initiation response omitted call id")

    started = time.monotonic()
    caller: subprocess.Popen[str] | None = None
    callee: subprocess.Popen[str] | None = None
    try:
        with tempfile.TemporaryDirectory(prefix="qwq-b10-fixture-") as temp_dir:
            temporary = Path(temp_dir)
            caller = subprocess.Popen(
                _patrol_command("ios"),
                cwd=ROOT,
                env=_role_environment(
                    role="caller",
                    call_id=call_id,
                    device_id=ios_device,
                    token=caller_token,
                    refresh_token=caller_refresh,
                    owner_id=caller_owner,
                    persona_id=caller_persona,
                    result_path=temporary / "caller.json",
                ),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            callee = subprocess.Popen(
                _patrol_command("android"),
                cwd=ROOT,
                env=_role_environment(
                    role="callee",
                    call_id=call_id,
                    device_id=android_device,
                    token=callee_token,
                    refresh_token=callee_refresh,
                    owner_id=callee_owner,
                    persona_id=callee_persona,
                    result_path=temporary / "callee.json",
                ),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            caller_output = _wait_process(
                caller,
                role="caller",
                timeout_seconds=900,
            )
            callee_output = _wait_process(
                callee,
                role="callee",
                timeout_seconds=900,
            )
            for role, output in (
                ("caller", caller_output),
                ("callee", callee_output),
            ):
                if (
                    f"QWQ_B10_FIXTURE_MEDIA_CONNECTED:{role}:{call_id}"
                    not in output
                    or f"QWQ_B10_FIXTURE_CALL_ENDED:{role}:{call_id}"
                    not in output
                ):
                    raise ValueError(
                        f"B10 fixture {role} Patrol omitted lifecycle evidence"
                    )
    finally:
        for process in (caller, callee):
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=15)
        try:
            _request_json(
                base_url=api_base,
                method="POST",
                path=f"/rtc/calls/{call_id}/hangup",
                token=caller_token,
                owner_id=caller_owner,
                persona_id=caller_persona,
                idempotency_key=f"b10-fixture-cleanup-{call_id}",
            )
        except (ValueError, urllib.error.URLError):
            pass

    final_call = _request_json(
        base_url=api_base,
        method="GET",
        path=f"/rtc/calls/{call_id}",
        token=caller_token,
        owner_id=caller_owner,
        persona_id=caller_persona,
    )
    if _find_string(final_call, frozenset({"status"})) != "ended":
        raise ValueError("B10 fixture call did not reach terminal ended state")
    if time.monotonic() - started <= 0:
        raise ValueError("B10 fixture execution duration is invalid")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(f"[b10-fixture-uat] {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
