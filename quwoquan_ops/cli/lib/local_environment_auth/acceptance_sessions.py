"""OTP 真实登录会话的编排（逐字搬移）。

本模块内被测试 patch 的依赖（``request_local_environment_*`` /
``_test_data_actor_phone`` / ``_clear_local_otp_send_throttle`` /
``load_local_research_identity_binding`` / ``materialize_test_data_identity_set`` /
``open_local_phone_acceptance_session``）一律经 ``_pkg.`` 属性访问。
"""

from __future__ import annotations

import hashlib
import subprocess
import time

import quwoquan_ops.cli.lib.local_environment_auth as _pkg

from .guards import (
    _canonical_actor_role,
    _canonical_test_data_instance_id,
    _require_nonprod_target,
    _required_string,
)
from .models import LocalAcceptanceActor, LocalAcceptanceSession


def open_local_phone_acceptance_session(
    base_url: str,
    *,
    environment: str,
    target_name: str,
    test_data_instance_id: str,
    identity_set_id: str,
    actor_role: str,
    actor_index: int,
    timeout_seconds: float = 30.0,
) -> LocalAcceptanceActor:
    """Create or restore a real nonprod account via OTP and phone login.

    Phone numbers come from a target-scoped protected identity pool and the OTP
    is consumed once from the target-isolated capture control plane. Neither
    value is returned in receipts.
    Prod is rejected by ``_require_nonprod_target``.
    """

    _require_nonprod_target(environment, target_name)
    canonical_instance = _canonical_test_data_instance_id(test_data_instance_id)
    canonical_identity_set_id = _canonical_actor_role(identity_set_id)
    canonical_role = _canonical_actor_role(actor_role)
    if actor_index < 0 or actor_index > 999:
        raise ValueError("local acceptance actor index must be between 0 and 999")

    actor_digest = hashlib.sha256(
        f"{target_name}\0{canonical_instance}\0{canonical_role}\0{actor_index}".encode(
            "utf-8"
        )
    ).hexdigest()
    if canonical_identity_set_id == "research-identity" and actor_index == 0:
        research_identity = _pkg.load_local_research_identity_binding(
            environment=environment,
            target_name=target_name,
        )
        phone = research_identity["phone"]
        expected_owner_id = research_identity["accountId"]
    else:
        phone = _pkg._test_data_actor_phone(
            target_name=target_name,
            identity_set_id=canonical_identity_set_id,
            actor_index=actor_index,
        )
        expected_owner_id = ""
    _pkg._clear_local_otp_send_throttle(target_name=target_name, phone=phone)
    device_id = f"acceptance-{environment}-{actor_digest[:16]}"
    common = {
        "deviceId": device_id,
        "platform": "acceptance",
        "appVersion": "1.0.0",
    }
    # 幂等键作用域是「本次会话开启」而非 instance 终身：同一 instance id 复开
    # 会话必须触发新 OTP 下发；固定键会被服务端幂等重放旧 challenge，导致
    # sms substitute 无新 OTP 可读（readback 404 直至超时）。会话 nonce 用
    # 时间成分承载，同一进程内重试仍靠 sms 侧 latest 读取收敛。
    session_nonce = time.time_ns()
    send_otp_idempotency_key = hashlib.sha256(
        (
            target_name
            + "/"
            + canonical_instance
            + "/user.acceptance.authenticated_actors/"
            + canonical_role
            + "/user.authentication_challenge.SendOtp/send-otp-"
            + f"{actor_index:03d}"
            + f"/session-{session_nonce}"
        ).encode("utf-8")
    ).hexdigest()
    otp = _pkg.request_local_environment_public_json(
        base_url,
        path="/auth/otp/send",
        method="POST",
        headers={"Idempotency-Key": send_otp_idempotency_key},
        body={
            "phone": phone,
            **common,
            "sourceOperation": "TestDataActorProvision",
        },
        timeout_seconds=timeout_seconds,
    )
    challenge_id = _required_string(otp, "challengeId", "OTP response")
    # Lazy import avoids a module cycle: the capture client loads the target's
    # protected auth material only after this module is fully initialized.
    from ..local_sms_provider_debug import read_latest_debug_otp

    protected_otp = read_latest_debug_otp(
        environment=environment,
        target_name=target_name,
        recipient=phone,
        timeout_seconds=timeout_seconds,
    )
    otp_code = protected_otp.code
    login = _pkg.request_local_environment_public_json(
        base_url,
        path="/auth/login/phone",
        method="POST",
        body={
            "phone": phone,
            "otpCode": otp_code,
            **common,
            "agreementVersion": "2026-06",
            "privacyVersion": "2026-06",
        },
        timeout_seconds=timeout_seconds,
    )
    protected_otp = None
    active_persona = login.get("activePersona")
    if not isinstance(active_persona, dict):
        raise RuntimeError("phone login response missing activePersona")
    session = LocalAcceptanceSession(
        owner_id=_required_string(login, "ownerId", "phone login response"),
        persona_id=_required_string(
            active_persona, "personaId", "phone login activePersona"
        ),
        access_token=_required_string(login, "accessToken", "phone login response"),
        refresh_token=_required_string(
            login, "refreshToken", "phone login response"
        ),
    )
    if expected_owner_id and session.owner_id != expected_owner_id:
        raise RuntimeError(
            "phone login owner does not match managed acceptance identity"
        )
    me = _pkg.request_local_environment_json(
        base_url,
        path="/me",
        session=session,
        timeout_seconds=timeout_seconds,
    )
    me_owner = str(me.get("ownerId") or me.get("id") or "").strip()
    if me_owner and me_owner != session.owner_id:
        raise RuntimeError("authenticated /me owner does not match phone login")
    return LocalAcceptanceActor(
        role=canonical_role,
        session=session,
        challenge_id=challenge_id,
        account_state=str(login.get("accountState") or "").strip(),
        identity_origin=str(login.get("identityOrigin") or "").strip(),
    )


def open_test_data_acceptance_session(
    base_url: str,
    *,
    environment: str,
    target_name: str,
    test_data_instance_id: str,
    actor_role: str,
    actor_index: int,
    timeout_seconds: float = 30.0,
) -> LocalAcceptanceActor:
    """Open an isolated typed test-data actor without exposing protected identity terms.

    The protected identity-set adapter derives a deterministic internal
    identity scope, while request graphs and receipts use only
    ``testDataInstanceId``.  This adapter can therefore be retired together
    with the test-live path without coupling typed capabilities to its schema.
    """

    canonical_instance = str(test_data_instance_id).strip()
    if not canonical_instance or "/" in canonical_instance:
        raise ValueError("testDataInstanceId must be non-empty and slash-free")
    identity_scope = hashlib.sha256(canonical_instance.encode("utf-8")).hexdigest()
    # Bind the protected phone identities to the test-data instance as well as
    # the bearer/session derivation.  Reopening the same instance therefore
    # remains idempotent, while a new CaseResult cannot silently reuse another
    # case's UserAccount or Persona through a fixed pool slot.
    identity_set_id = f"typed-{identity_scope[:40]}"
    _pkg.materialize_test_data_identity_set(
        environment=environment,
        target_name=target_name,
        identity_set_id=identity_set_id,
        actor_count=actor_index + 1,
    )
    return _pkg.open_local_phone_acceptance_session(
        base_url,
        environment=environment,
        target_name=target_name,
        test_data_instance_id=identity_scope,
        identity_set_id=identity_set_id,
        actor_role=actor_role,
        actor_index=actor_index,
        timeout_seconds=timeout_seconds,
    )


def close_test_data_acceptance_actor(
    base_url: str,
    *,
    actor: LocalAcceptanceActor,
    test_data_instance_id: str,
    timeout_seconds: float = 30.0,
) -> None:
    """Close one isolated test-data account through its public contract.

    This narrow harness helper is for runtime preflights that exercise the real
    OTP path outside a full ``TestDataSession``. Business acceptance cases use
    the User Provider, which records the same operation in its receipt journal.
    """

    canonical_instance = str(test_data_instance_id).strip()
    if not canonical_instance or "/" in canonical_instance:
        raise ValueError("testDataInstanceId must be non-empty and slash-free")
    # Lazy import avoids the local_environment_auth -> operations module cycle.
    from ..test_data.operations import ContractOperationCatalog

    operation = ContractOperationCatalog().require(
        "user.user_account.CloseAccount"
    )
    close_request_id = hashlib.sha256(
        (canonical_instance + "\0close-account").encode("utf-8")
    ).hexdigest()[:32]
    _pkg.request_local_environment_json(
        base_url,
        path=operation.path(),
        session=actor.session,
        method=operation.method,
        body={"clientRequestId": close_request_id},
        # CloseAccount is an idempotent write command.  The operation guard
        # enforces the canonical header before the handler can consume the
        # equivalent body replay identity.
        headers={"Idempotency-Key": close_request_id},
        timeout_seconds=timeout_seconds,
    )


def _clear_local_otp_send_throttle(*, target_name: str, phone: str) -> None:
    """Best-effort clear of local Redis OTP cooldown/quota for retained restore.

    Retained candidate-bound identity already proved account creation. Health and
    debug-preflight only need one live session; leftover otp:resend / otp:quota
    keys must not force GATE_BLOCK via HTTP 429.
    """

    if not phone.startswith("+") or not phone[1:].isdigit():
        return
    try:
        from ..environment_topology import get_target, load_environment_topology
        from ..port_manifest import load_port_manifest, profile_ports

        target = get_target(load_environment_topology(), target_name)
        profile = str(target.get("portProfile") or "").strip()
        if not profile:
            return
        redis_port = profile_ports(load_port_manifest(), profile).get("redis")
        if not isinstance(redis_port, int) or redis_port <= 0:
            return
        phone_digest = hashlib.sha256(phone.strip().encode("utf-8")).hexdigest()
        _pkg.subprocess.run(
            [
                "redis-cli",
                "-p",
                str(redis_port),
                "DEL",
                f"otp:resend:{phone_digest}",
                f"otp:quota:{phone_digest}",
                f"otp:quota-deadline:{phone_digest}",
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired):
        return
