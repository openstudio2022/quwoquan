"""stackctl `app-debug-preflight` 命令执行体与真实 OTP 登录旅程。

从 commands/app_preflight.py 逐字迁出(该模块保留三命令主干与 argparse 表面,
Debug 预检执行体随本职责聚合到本模块):

- `command_app_debug_preflight`:Flutter Debug 启动前 runtime / TLS / SMS
  substitute 只读验证与 content-live 组件门;
- `_execute_otp_login_journey`:secret-free、runtime-bound 的
  SendOtp/Login/session readback 真实登录旅程。

`register_parser` 与 `command_app_content_preflight` /
`command_app_domain_api_integration` 在 `commands/app_preflight.py`;内容
证据解析家族在 `commands/app_preflight_evidence.py`。测试经
``mock.patch.object(stackctl, ...)`` patch 本模块符号与协作符号,因此
函数体内一律经函数内延迟导入 `_stackctl` 属性访问(含本模块符号互调),
保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any, Mapping


def _execute_otp_login_journey(
    *,
    environment: str,
    target_name: str,
    runtime_mode: str,
    startup: Mapping[str, Any],
    provider_runtime: Mapping[str, Any],
    api_base_url: str,
    report_dir: Path,
) -> dict[str, Any]:
    """Execute one secret-free, runtime-bound SendOtp/Login/session readback."""
    import quwoquan_ops.cli.stackctl as _stackctl

    receipt_path = report_dir / "otp-login-journey.json"
    if runtime_mode == "immutable_candidate":
        result = _stackctl.run(
            [
                sys.executable,
                str(
                    _stackctl.ROOT
                    / "quwoquan_ops/tests/acceptance/api_integration/service_ops/"
                    "user-service/test_otp_local_capture_live_journey__api_integration_test.py"
                ),
            ],
            cwd=_stackctl.ROOT,
            env={
                "QWQ_PROVIDER_CONFORMANCE_ENVIRONMENT": environment,
                "APP_RUNTIME_ENV": environment,
            },
            timeout_seconds=120,
        )
        try:
            journey = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "candidate-bound OTP login journey returned no machine receipt"
            ) from exc
        if not isinstance(journey, dict):
            raise RuntimeError("candidate-bound OTP login journey receipt is invalid")
        if result.returncode != 0 or journey.get("status") != "passed":
            reason = str(journey.get("reason") or "live journey failed").strip()
            raise RuntimeError(
                "candidate-bound OTP login journey GATE_BLOCK: " + reason
            )
        baseline_id = str(provider_runtime.get("baselineId") or "")
        manifest = _stackctl.load_candidate_manifest(
            environment,
            target_name,
            baseline_id,
            require_full=True,
        )
        expected = {
            "schema": "otp-local-capture-live-journey",
            "status": "passed",
            "target": target_name,
            "baselineId": baseline_id,
            "sourceRevision": str(manifest.get("sourceRevision") or ""),
            "runtimeConfigDigest": str(manifest.get("runtimeConfigDigest") or ""),
            "configurationDigest": str(manifest.get("configurationDigest") or ""),
            "providerRuntimeDigest": str(
                provider_runtime.get("composition", {}).get(
                    "runtimeCompositionDigest"
                )
                or ""
            ),
            "startupAttemptId": str(startup.get("attemptId") or ""),
            "challengePresent": True,
            "sessionPresent": True,
            "nonPromotable": True,
        }
        if any(journey.get(field) != value for field, value in expected.items()):
            raise RuntimeError(
                "candidate-bound OTP login journey receipt identity mismatch"
            )
        receipt = dict(journey)
        receipt["launchPolicy"] = "immutable_candidate"
    else:
        before_identity = {
            field: str(startup.get(field) or "")
            for field in (
                "attemptId",
                "sourceRevision",
                "configurationDigest",
                "providerRuntimeDigest",
            )
        }
        if not api_base_url:
            raise RuntimeError("test_live OTP login journey has no API base URL")
        # The runtime attempt binds the journey to the selected deployment, but
        # it is not the identity of an acceptance run.  Reusing only the
        # attempt/configuration tuple makes a later app-debug-preflight replay
        # the already-consumed SendOtp challenge while the protected capture is
        # intentionally one-shot.  Bind the typed actor to this append-only
        # preflight run as well, so a command retry gets a fresh Case actor and
        # its own idempotency key without weakening SendOtp idempotency.
        instance_id = "otp-" + hashlib.sha256(
            (
                target_name
                + "\0"
                + before_identity["attemptId"]
                + "\0"
                + before_identity["configurationDigest"]
                + "\0"
                + str(report_dir.expanduser().resolve())
            ).encode("utf-8")
        ).hexdigest()[:40]
        actor = _stackctl.open_test_data_acceptance_session(
            api_base_url,
            environment=environment,
            target_name=target_name,
            test_data_instance_id=instance_id,
            actor_role="primary",
            actor_index=0,
        )
        try:
            current = _stackctl.load_test_live_startup_attempt(target_name)
            after_identity = {
                field: str((current or {}).get(field) or "")
                for field in before_identity
            }
            if before_identity != after_identity:
                raise RuntimeError("test_live runtime changed during OTP login journey")
            if not actor.challenge_id or not actor.session.owner_id:
                raise RuntimeError("test_live OTP login journey receipt is incomplete")
        finally:
            _stackctl.close_test_data_acceptance_actor(
                api_base_url,
                actor=actor,
                test_data_instance_id=instance_id,
            )
        receipt = {
            "schema": "otp-local-capture-live-journey",
            "status": "passed",
            "target": target_name,
            "launchPolicy": "test_live",
            "baselineId": "",
            "sourceRevision": before_identity["sourceRevision"],
            "configurationDigest": before_identity["configurationDigest"],
            "providerRuntimeDigest": before_identity["providerRuntimeDigest"],
            "startupAttemptId": before_identity["attemptId"],
            "challengePresent": True,
            "sessionPresent": True,
            "nonPromotable": True,
        }

    _stackctl.write_json(receipt_path, receipt)
    receipt_digest = "sha256:" + hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    return {
        **receipt,
        "receiptRef": _stackctl.relpath(receipt_path),
        "receiptDigest": receipt_digest,
    }


def command_app_debug_preflight(args: argparse.Namespace) -> dict[str, Any]:
    """Validate runtime health plus a real SendOtp/Login/session journey."""
    import quwoquan_ops.cli.stackctl as _stackctl

    target_name = str(args.target)
    topology = _stackctl.load_environment_topology()
    target = _stackctl.get_target(topology, target_name)
    environment = str(target["env"])
    runtime_mode = str(getattr(args, "runtime_mode", "") or "")
    purpose = str(getattr(args, "purpose", "runtime") or "runtime")
    report_dir = (
        Path(args.report_dir)
        if getattr(args, "report_dir", "")
        else _stackctl.repo_run_dir("app-debug-preflight", target=target_name)
    )
    details: list[str] = []
    warnings: list[str] = []
    mutable_workspace_warnings: list[str] = []
    startup: dict[str, Any] = {}
    content_binding: dict[str, Any] = {}
    content_preflight: dict[str, Any] = {}
    provider_runtime_binding: dict[str, Any] | None = None
    login_journey: dict[str, Any] = {}

    def record_readiness_finding(message: str) -> None:
        if runtime_mode == "test_live" and purpose == "runtime":
            warnings.append(message)
        else:
            details.append(message)

    if environment not in {"alpha", "beta", "gamma"}:
        details.append("app-debug-preflight only supports non-production targets")
    if runtime_mode not in {"immutable_candidate", "test_live"}:
        details.append("app-debug-preflight runtime mode is invalid")
    if purpose not in {"runtime", "content_live"}:
        details.append("app-debug-preflight purpose is invalid")
    public_bases = target.get("publicBases") or {}
    expected_host = f"{environment}.quwoquan.com"
    for role, raw_url in sorted(public_bases.items()):
        parsed = urllib.parse.urlparse(str(raw_url))
        hostname = str(parsed.hostname or "").lower()
        if hostname != expected_host and not hostname.endswith(f".{expected_host}"):
            details.append(
                f"{runtime_mode or 'unknown'} {role} endpoint escapes the selected "
                f"{environment} namespace"
            )

    try:
        if runtime_mode == "immutable_candidate":
            provider_runtime_binding = _stackctl._active_provider_runtime(
                environment,
                target_name,
            )
        else:
            provider_runtime_binding = {
                "baselineId": "",
                "composition": _stackctl.compile_provider_runtime_composition(
                    environment=environment,
                    target=target_name,
                ),
            }
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        record_readiness_finding(f"selected Provider runtime is invalid: {exc}")
    try:
        if runtime_mode == "immutable_candidate":
            startup = _stackctl.load_startup_attempt(target_name) or {}
        else:
            startup = _stackctl.load_test_live_startup_attempt(target_name) or {}
    except (OSError, ValueError) as exc:
        record_readiness_finding(f"selected startup receipt is unreadable: {exc}")
    if not startup:
        record_readiness_finding("target has no selected runtime startup receipt")
    else:
        if startup.get("status") != "running":
            record_readiness_finding(
                "target startup status is not running: "
                + str(startup.get("status") or "missing")
            )
        if (
            startup.get(
                "env" if runtime_mode == "immutable_candidate" else "environment"
            )
            != environment
            or startup.get("target") != target_name
        ):
            record_readiness_finding("startup receipt target/environment mismatch")
        if startup.get("workload") != "full":
            record_readiness_finding("full runtime is not running")
        if re.fullmatch(
            r"sha256:[0-9a-f]{64}",
            str(startup.get("configurationDigest") or ""),
        ) is None:
            record_readiness_finding(
                "startup receipt has no canonical configuration digest"
            )
        expected_provider_digest = str(
            (provider_runtime_binding or {}).get("composition", {}).get(
                "runtimeCompositionDigest"
            )
            or ""
        )
        if (
            not expected_provider_digest
            or startup.get("providerRuntimeDigest") != expected_provider_digest
        ):
            record_readiness_finding(
                "startup receipt Provider runtime differs from selected runtime"
            )
        if runtime_mode == "immutable_candidate" and (
            startup.get("candidateDigest")
            != (provider_runtime_binding or {}).get("baselineId")
        ):
            details.append("startup receipt does not bind the active candidate")

    try:
        tls_evidence = _stackctl.verify_certificate(target_name)
    except (
        OSError,
        _stackctl.PublicDomainTlsError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as exc:
        tls_evidence = {"status": "gate_block"}
        record_readiness_finding(f"target TLS is not ready: {exc}")

    profile_name = str(target.get("portProfile") or "")
    try:
        ports = (
            _stackctl.profile_ports(_stackctl.load_port_manifest(), profile_name)
            if profile_name
            else {}
        )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        ports = {}
        record_readiness_finding(
            f"target local port topology is unavailable: {exc}"
        )
    public_bases = target.get("publicBases") or {}
    checks = [
        ("api-edge", f"{str(public_bases.get('api') or '').rstrip('/')}/healthz", ""),
        ("user-service", f"http://127.0.0.1:{ports.get('user-service', 0)}/healthz", ""),
        ("integration-service", f"http://127.0.0.1:{ports.get('integration-service', 0)}/healthz", ""),
    ]
    provider_roles: list[str] = []
    sms_capture_roles: set[str] = set()
    if provider_runtime_binding is not None:
        try:
            composition = provider_runtime_binding.get("composition")
            if not isinstance(composition, Mapping):
                raise ValueError("Provider runtime composition is missing")
            workloads = composition.get("workloads")
            if not isinstance(workloads, list):
                raise ValueError("Provider runtime workloads are missing")
            provider_roles = [
                str(item["role"])
                for item in workloads
                if isinstance(item, Mapping)
            ]
            sms_capture_roles = {
                str(item["role"])
                for item in workloads
                if isinstance(item, Mapping)
                and "ext.sms.local_capture" in item.get("adapterIds", [])
            }
            provider_ca_file = str(
                _stackctl.root_certificate_path(target_name, require_ready=False)
            )
            checks.extend(
                (
                    role,
                    f"https://127.0.0.1:{ports.get(role, 0)}/healthz",
                    provider_ca_file,
                )
                for role in provider_roles
            )
        except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
            record_readiness_finding(
                f"selected Provider runtime diagnostics are unavailable: {exc}"
            )
    provider_readback: dict[str, Any] = {}
    check_receipts: list[dict[str, Any]] = []
    for name, url, ca_file in checks:
        if url.endswith(":0/healthz") or url == "/healthz":
            check_receipts.append(
                {"name": name, "ready": False, "statusCode": None}
            )
            record_readiness_finding(f"{name} topology is incomplete")
            continue
        probe_failed = False
        try:
            ok, status_code, body, _ = _stackctl.fetch_url(
                url,
                timeout=2.0,
                retry_attempts=3,
                retry_sleep_seconds=0.5,
                ca_file=ca_file,
            )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            ok, status_code, body = False, None, ""
            probe_failed = True
            record_readiness_finding(
                f"{name} readiness probe failed: {exc}"
            )
        check_receipts.append(
            {"name": name, "ready": ok, "statusCode": status_code}
        )
        if not ok and not probe_failed:
            record_readiness_finding(
                f"{name} is not ready: {status_code or 'network_error'}"
            )
        if not ok:
            continue
        if name in sms_capture_roles:
            try:
                decoded = json.loads(body)
            except json.JSONDecodeError:
                record_readiness_finding(
                    "SMS substitute health readback is not JSON"
                )
                continue
            if not isinstance(decoded, dict):
                record_readiness_finding("SMS substitute health readback is invalid")
                continue
            provider_readback = {
                "adapterId": str(decoded.get("adapterId") or ""),
                "environment": str(decoded.get("environment") or ""),
                "configurationDigest": str(
                    decoded.get("configurationDigest") or ""
                ),
                "profile": str(decoded.get("profile") or ""),
                "nonPromotable": decoded.get("nonPromotable") is True,
                "ready": decoded.get("status") == "ready",
            }
            if provider_readback != {
                "adapterId": "ext.sms.local_capture",
                "environment": environment,
                "configurationDigest": str(
                    startup.get("configurationDigest") or ""
                ),
                "profile": provider_readback["profile"],
                "nonPromotable": True,
                "ready": True,
            } or provider_readback["profile"] not in {
                "success",
                "rate_limit",
                "failure",
                "timeout",
            }:
                record_readiness_finding(
                    "SMS substitute adapter/environment/readiness mismatch"
                )

    if not details and not warnings and provider_runtime_binding is not None:
        try:
            login_journey = _stackctl._execute_otp_login_journey(
                environment=environment,
                target_name=target_name,
                runtime_mode=runtime_mode,
                startup=startup,
                provider_runtime=provider_runtime_binding,
                api_base_url=str(public_bases.get("api") or "").rstrip("/"),
                report_dir=report_dir,
            )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            record_readiness_finding(str(exc))

    runtime_ready = (
        not details
        and not warnings
        and provider_runtime_binding is not None
        and bool(startup)
        and startup.get("status") == "running"
        and str(tls_evidence.get("status") or "") == "ready"
        and bool(check_receipts)
        and all(item.get("ready") is True for item in check_receipts)
        and login_journey.get("status") == "passed"
    )
    if runtime_mode == "test_live":
        try:
            content_binding = _stackctl.load_test_live_content_binding(target_name) or {}
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            content_binding = {}
            record_readiness_finding(
                f"test-live content binding is invalid and was ignored: {exc}"
            )
        if not content_binding:
            record_readiness_finding(
                "test_live content is unbound; no explicit release identity was selected"
            )

    content_live_components: dict[str, bool | None] = {
        "runtime": None,
        "binding": None,
        "api": None,
        "media": None,
        "search": None,
        "recommendation": None,
        "readiness": None,
    }
    blocked_content_components: list[str] = []
    if purpose == "content_live":
        try:
            content_preflight = _stackctl.command_app_content_preflight(
                argparse.Namespace(
                    target=target_name,
                    purpose="content_live",
                    runtime_mode=runtime_mode,
                    content_binding=content_binding,
                    report_dir=str(report_dir / "content-live"),
                )
            )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            content_preflight = {
                "exitCode": 2,
                "status": "gate_block",
                "details": [str(exc)],
            }

        readback = content_preflight.get("contentReadback")
        readback = readback if isinstance(readback, Mapping) else {}
        raw_queries = readback.get("feedQueries")
        feed_queries = (
            [item for item in raw_queries if isinstance(item, Mapping)]
            if isinstance(raw_queries, list)
            else []
        )

        def matched_query(name: str) -> bool:
            return any(
                item.get("name") == name and bool(item.get("matchedPostIds"))
                for item in feed_queries
            )

        app_uat_plan = content_preflight.get("appUatPlan")
        app_uat_plan = app_uat_plan if isinstance(app_uat_plan, Mapping) else {}
        release_probe = content_preflight.get("releaseProbe")
        release_probe = release_probe if isinstance(release_probe, Mapping) else {}
        probed_media = release_probe.get("mediaChecks")
        probed_media = probed_media if isinstance(probed_media, Mapping) else {}
        probed_search = release_probe.get("searchCanaries")
        binding_ready = (
            (
                bool(content_binding)
                and all(
                    str(content_preflight.get(field) or "")
                    == str(content_binding.get(field) or "")
                    for field in (
                        "releaseId",
                        "manifestDigest",
                        "readinessReceiptRef",
                        "readinessReceiptDigest",
                    )
                )
            )
            if runtime_mode == "test_live"
            else (
                bool((provider_runtime_binding or {}).get("baselineId"))
                and content_preflight.get("packageBaseline")
                == (provider_runtime_binding or {}).get("baselineId")
            )
        )
        content_live_components = {
            "runtime": runtime_ready,
            "binding": binding_ready,
            "api": bool(readback.get("postIds")) and bool(feed_queries),
            "media": release_probe.get("exitCode") == 0
            and probed_media.get("automatic") is True
            and matched_query("typed_video"),
            "search": release_probe.get("exitCode") == 0
            and isinstance(probed_search, list)
            and len(probed_search) == 3,
            "recommendation": release_probe.get("exitCode") == 0
            and matched_query("homepage_recommend"),
            "readiness": int(content_preflight.get("exitCode", 2)) == 0
            and content_preflight.get("status") == "passed"
            and bool(content_preflight.get("readinessReceiptRef"))
            and bool(content_preflight.get("readinessReceiptDigest")),
        }
        blocked_content_components = sorted(
            name
            for name, ready in content_live_components.items()
            if ready is not True
        )
        if blocked_content_components:
            details.append(
                "content-live components are GATE_BLOCK: "
                + ", ".join(blocked_content_components)
            )
    content_state = "bound" if content_binding else "unbound"
    status = "gate_block" if details else "warning" if warnings else "passed"
    content_live_status = (
        "gate_block"
        if purpose == "content_live" and blocked_content_components
        else "passed"
        if purpose == "content_live"
        else "not_requested"
    )
    first_blocker = (
        "APP.CONTENT_LIVE."
        + blocked_content_components[0].upper()
        + "_BLOCKED"
        if blocked_content_components
        else ("APP.RUNTIME.PREFLIGHT_BLOCKED" if details else "")
    )
    recovery_command = (
        "python3 quwoquan_ops/cli/stackctl.py --output-format json "
        f"app-debug-preflight --purpose {purpose} --target {target_name} "
        f"--runtime-mode {runtime_mode}"
    )
    payload = {
        "schema": "quwoquan_ops.app_debug_preflight",
        "target": target_name,
        "environment": environment,
        "purpose": purpose,
        "launchPolicy": runtime_mode,
        "nonPromotable": runtime_mode == "test_live",
        "contentLive": content_live_status,
        "contentLiveChecks": {
            "status": content_live_status,
            "nonPromotable": runtime_mode == "test_live",
            "components": content_live_components,
            "blockedComponents": blocked_content_components,
        },
        "firstBlocker": first_blocker,
        "recoveryCommand": recovery_command,
        "contentBindingState": content_state,
        "status": status,
        "configurationDigest": str(startup.get("configurationDigest") or ""),
        "providerRuntimeDigest": str(
            startup.get("providerRuntimeDigest") or ""
        ),
        "runtimeChecks": check_receipts,
        "tls": {
            "profile": str(tls_evidence.get("profile") or ""),
            "status": str(tls_evidence.get("status") or ""),
        },
        "provider": provider_readback,
        "loginJourney": login_journey,
        "loginJourneyReceiptRef": login_journey.get("receiptRef", ""),
        "loginJourneyReceiptDigest": login_journey.get("receiptDigest", ""),
        "details": details,
        "warnings": warnings,
        "mutableWorkspaceWarnings": mutable_workspace_warnings,
        "contentAvailability": (
            {
                "state": "bound",
                "readinessPhase": content_binding.get("readinessPhase", ""),
            }
            if content_binding
            else (
                {"state": "unbound", "emptyReason": "no_active_release"}
                if runtime_mode == "test_live"
                else {
                    "state": "not_evaluated",
                    "packageBaseline": str(
                        (provider_runtime_binding or {}).get("baselineId") or ""
                    ),
                }
            )
        ),
        "contentBinding": content_binding,
        "packageBaseline": (
            str((provider_runtime_binding or {}).get("baselineId") or "")
            if runtime_mode == "immutable_candidate"
            else ""
        ),
        "sourceRevision": str(
            login_journey.get("sourceRevision")
            or (
                (content_binding.get("startupIdentity") or {}).get("sourceRevision")
                if isinstance(content_binding.get("startupIdentity"), Mapping)
                else ""
            )
        ),
        "releaseId": content_binding.get("releaseId", ""),
        "manifestDigest": content_binding.get("manifestDigest", ""),
        "readinessReceiptRef": content_binding.get("readinessReceiptRef", ""),
        "readinessReceiptDigest": content_binding.get("readinessReceiptDigest", ""),
        "lifecycleExitRef": content_binding.get("lifecycleExitRef", ""),
        "appUatEnvelope": content_binding.get("appUatEnvelope", {}),
        "appUatPlan": (
            content_preflight.get("appUatPlan", {})
            if purpose == "content_live"
            else content_binding.get("appUatPlan", {})
        ),
        "appUatPlanDigest": (
            content_preflight.get("appUatPlanDigest", "")
            if purpose == "content_live"
            else content_binding.get("appUatPlanDigest", "")
        ),
        "contentReadback": (
            content_preflight.get("contentReadback", {})
            if purpose == "content_live"
            else {}
        ),
        "contentReadinessReportRef": (
            content_preflight.get("contentReadinessReportRef", "")
            if purpose == "content_live"
            else ""
        ),
    }
    _stackctl.write_json(report_dir / "report.json", payload)
    _stackctl.write_json(
        report_dir / "findings.json",
        {"issues": details, "warnings": warnings},
    )
    return {
        **payload,
        "exitCode": 2 if details else 0,
        "summary": (
            f"App Debug preflight is GATE_BLOCK for {target_name}"
            if details
            else f"App Debug preflight is {status.upper()} for {target_name}"
        ),
        "reportDir": _stackctl.relpath(report_dir),
    }
