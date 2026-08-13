"""Live SendOtp → local_capture → protected read → LoginWithPhone journey.

spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/four-environment-commercial-login-maturity/spec.md#gwt-009
spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/four-environment-commercial-login-maturity/spec.md#gwt-011.t3
"""

from __future__ import annotations

import hashlib
import json
import os
import ssl
import sys
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[6]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.deployment_candidate_manifest import (  # noqa: E402
    load_candidate_manifest,
)
from quwoquan_ops.cli.lib.local_environment_auth import (  # noqa: E402
    close_test_data_acceptance_actor,
    open_test_data_acceptance_session,
)
from quwoquan_ops.cli.lib.output_paths import (  # noqa: E402
    active_deployment_candidate,
)
from quwoquan_ops.cli.lib.port_manifest import (  # noqa: E402
    load_port_manifest,
    profile_ports,
)
from quwoquan_ops.cli.lib.public_domain_tls import (  # noqa: E402
    root_certificate_path,
)
from quwoquan_ops.cli.lib.startup_attempt_receipt import (  # noqa: E402
    load_startup_attempt,
)


def _probe(
    url: str,
    *,
    timeout: float = 2.0,
    context: ssl.SSLContext | None = None,
) -> bool:
    try:
        with urllib.request.urlopen(
            url,
            timeout=timeout,
            context=context,
        ) as response:
            return 200 <= int(response.status) < 500
    except (urllib.error.URLError, TimeoutError, ValueError):
        return False


def _runtime_probes(
    *,
    api_base: str,
    user_health: str,
    integration_health: str,
    substitute_health: str,
    local_tls: ssl.SSLContext,
) -> tuple[tuple[str, str, ssl.SSLContext | None], ...]:
    return (
        ("api-edge", api_base + "/healthz" if api_base else "", local_tls),
        ("user-service", user_health, None),
        ("integration-service", integration_health, None),
        ("sms-provider-substitute", substitute_health, local_tls),
    )


def _gate_block(
    reason: str,
    *,
    target: str = "",
    missing: list[str] | None = None,
) -> int:
    payload: dict[str, Any] = {
        "schema": "otp-local-capture-live-journey",
        "status": "GATE_BLOCK",
        "reason": reason,
    }
    if target:
        payload["target"] = target
    if missing:
        payload["missing"] = missing
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 2


def _required_environment() -> str:
    values = {
        value
        for value in (
            os.environ.get("QWQ_PROVIDER_CONFORMANCE_ENVIRONMENT", "").strip(),
            os.environ.get("APP_RUNTIME_ENV", "").strip(),
        )
        if value
    }
    if len(values) != 1:
        raise ValueError(
            "exactly one consistent Provider/runtime environment is required"
        )
    environment = next(iter(values))
    if environment not in {"alpha", "beta", "gamma"}:
        raise ValueError(
            "local-capture live journey is limited to Alpha/Beta/Gamma"
        )
    return environment


def _load_package_bound_runtime(
    environment: str,
) -> tuple[str, dict[str, Any], dict[str, Any], str, dict[str, Any]]:
    target_name = f"{environment}-local"
    active = active_deployment_candidate(target_name)
    if active is None:
        raise RuntimeError("active immutable deployment candidate is unavailable")
    baseline_id = str(active["baselineId"])
    candidate_root = Path(active["candidateDir"])
    manifest = load_candidate_manifest(
        environment,
        target_name,
        baseline_id,
        require_full=True,
    )
    runtime_path = candidate_root / "packages/app/environment_runtime.yaml"
    try:
        runtime_raw = runtime_path.read_bytes()
        runtime = json.loads(runtime_raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("packaged environment runtime is unreadable") from exc
    environment_runtime_digest = "sha256:" + hashlib.sha256(runtime_raw).hexdigest()
    if (
        not isinstance(runtime, dict)
        or runtime.get("environment") != environment
        or runtime.get("target") != target_name
        or not isinstance(runtime.get("publicBases"), dict)
        or manifest.get("environmentRuntimeDigest") != environment_runtime_digest
    ):
        raise RuntimeError("packaged environment runtime identity mismatch")
    composition = (manifest.get("providerRuntime") or {}).get("composition")
    bindings = (
        composition.get("bindings") if isinstance(composition, dict) else None
    )
    sms_binding = next(
        (
            binding
            for binding in bindings or []
            if isinstance(binding, dict)
            and binding.get("capabilityId") == "identity.sms.otp"
        ),
        None,
    )
    workloads = (
        composition.get("workloads") if isinstance(composition, dict) else None
    )
    sms_workload = next(
        (
            workload
            for workload in workloads or []
            if isinstance(workload, dict)
            and workload.get("role") == "sms-provider-substitute"
        ),
        None,
    )
    if (
        not isinstance(sms_binding, dict)
        or sms_binding.get("state") != "enabled"
        or sms_binding.get("adapterId") != "ext.sms.local_capture"
        or sms_binding.get("endpointRef")
        != "local_topology:sms-provider-substitute"
        or not isinstance(sms_workload, dict)
        or "identity.sms.otp" not in (sms_workload.get("capabilityIds") or [])
        or "ext.sms.local_capture" not in (sms_workload.get("adapterIds") or [])
    ):
        raise RuntimeError("packaged SMS local-capture composition is unavailable")
    startup = load_startup_attempt(target_name)
    if (
        not isinstance(startup, dict)
        or startup.get("status") != "running"
        or startup.get("workload") != "full"
        or startup.get("env") != environment
        or startup.get("target") != target_name
        or startup.get("candidateDigest") != baseline_id
        or startup.get("configurationDigest") != manifest.get("configurationDigest")
        or startup.get("providerRuntimeDigest")
        != composition.get("runtimeCompositionDigest")
        or not str(startup.get("attemptId") or "").strip()
        or startup.get("attemptId") == "unknown"
    ):
        raise RuntimeError("running full startup receipt is not candidate-bound")
    return target_name, runtime, manifest, baseline_id, startup


def main() -> int:
    try:
        environment = _required_environment()
        (
            target_name,
            runtime,
            manifest,
            baseline_id,
            startup,
        ) = _load_package_bound_runtime(environment)
    except (RuntimeError, ValueError) as exc:
        return _gate_block(str(exc))
    try:
        ports = profile_ports(load_port_manifest(), str(runtime["portProfile"]))
        public_bases = runtime["publicBases"]
    except (KeyError, TypeError, ValueError):
        return _gate_block(
            "packaged runtime topology cannot resolve the target port profile",
            target=target_name,
        )
    api_base = str(public_bases.get("api") or "").rstrip("/")
    substitute_health = f"https://127.0.0.1:{ports['sms-provider-substitute']}/healthz"
    user_health = f"http://127.0.0.1:{ports['user-service']}/healthz"
    integration_health = f"http://127.0.0.1:{ports['integration-service']}/healthz"
    try:
        local_tls = ssl.create_default_context(
            cafile=str(root_certificate_path(target_name))
        )
    except (OSError, RuntimeError, ssl.SSLError, ValueError):
        return _gate_block(
            "target local CA trust is unavailable",
            target=target_name,
        )

    probes = _runtime_probes(
        api_base=api_base,
        user_health=user_health,
        integration_health=integration_health,
        substitute_health=substitute_health,
        local_tls=local_tls,
    )
    missing = [
        name
        for name, url, context in probes
        if not url or not _probe(url, context=context)
    ]
    if missing:
        return _gate_block(
            "required OTP login runtime is unavailable",
            target=target_name,
            missing=missing,
        )
    instance_id = "otp-" + hashlib.sha256(
        f"{target_name}\0{baseline_id}\0{startup['attemptId']}".encode("utf-8")
    ).hexdigest()[:40]
    try:
        actor = open_test_data_acceptance_session(
            api_base,
            environment=environment,
            target_name=target_name,
            test_data_instance_id=instance_id,
            actor_role="primary",
            actor_index=0,
        )
    except (OSError, RuntimeError, ValueError):
        return _gate_block(
            "phone acceptance session could not be established",
            target=target_name,
        )
    if not actor.session.owner_id or not actor.session.access_token:
        return _gate_block(
            "phone acceptance session is missing canonical owner identity",
            target=target_name,
        )
    if actor.challenge_id == "":
        return _gate_block(
            "SendOtp response is missing challengeId",
            target=target_name,
        )
    receipt = {
                "schema": "otp-local-capture-live-journey",
                "status": "passed",
                "target": target_name,
                "baselineId": baseline_id,
                "sourceRevision": manifest["sourceRevision"],
                "runtimeConfigDigest": manifest["runtimeConfigDigest"],
                "configurationDigest": manifest["configurationDigest"],
                "providerRuntimeDigest": manifest["providerRuntime"][
                    "composition"
                ]["runtimeCompositionDigest"],
                "startupAttemptId": startup["attemptId"],
                "challengePresent": True,
                "sessionPresent": True,
                "nonPromotable": True,
    }
    try:
        close_test_data_acceptance_actor(
            api_base,
            actor=actor,
            test_data_instance_id=instance_id,
        )
    except (OSError, RuntimeError, ValueError):
        return _gate_block(
            "isolated OTP acceptance actor cleanup failed",
            target=target_name,
        )
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


class OtpLocalCaptureLiveJourneyTest(unittest.TestCase):
    """api_integration canonical 入口:在预制真实环境内完整旅程必须成功。

    环境外的 fail-closed 行为(结构化 GATE_BLOCK)由
    test_sms_local_capture_api_harness__contract__local_contract_test.py
    经模块加载单独合约化;这里只承载环境内的真实结果。
    """

    def test_live_otp_capture_journey_completes(self) -> None:
        self.assertEqual(main(), 0)


if __name__ == "__main__":
    raise SystemExit(main())
