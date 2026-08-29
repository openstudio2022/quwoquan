"""stackctl 环境就绪探测域: provider readiness preflight、受控 fetch
与环境集成 probe。

从 stackctl.py 逐字迁出（改写规则与 down_domain 相同）:
provider readiness 家族、`fetch_url` / `_fetch_local_managed_url` /
`_is_retryable_fetch_error`、启动健康失败报告、`_resolve_test_auth_token`、
`_run_script_probe` / `_run_environment_integration_probe`。

`_CanonicalLocalHTTPSConnection` 类仍留 stackctl.py（类体求值语义）。

测试经 ``mock.patch.object(stackctl, ...)`` patch 本模块符号与协作符号，
因此函数体内一律经函数内延迟导入 `_stackctl` 属性访问（含本模块符号互调），
保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import json
import os
import ssl
import time
import urllib
import urllib.error
import urllib.parse
import urllib.request

from collections.abc import Sequence
from pathlib import Path
from typing import Any
from typing import Mapping
from uuid import uuid4


def _provider_readiness_failure_categories(
    report: dict[str, Any] | None,
    *,
    report_is_valid: bool,
    required_capabilities_ready: bool,
    child_exit_code: int,
) -> list[str]:
    """Map Provider diagnostics to stable, non-sensitive remediation categories."""
    categories: set[str] = set()
    if not report_is_valid:
        categories.add("provider-readiness-report")
    if not required_capabilities_ready:
        categories.add("readiness")
    if child_exit_code != 0:
        categories.add("provider-readiness")
    issues = report.get("issues") if isinstance(report, dict) else []
    if not isinstance(issues, list):
        return sorted(categories | {"provider-readiness-report"})
    for issue in issues:
        if not isinstance(issue, str):
            categories.add("provider-readiness-report")
            continue
        normalized = issue.lower()
        if any(
            marker in normalized
            for marker in (
                "evidence",
                "artifactref",
                "nine-cell",
                "executedat",
                "24-hour",
            )
        ):
            categories.add("evidence")
        if any(marker in normalized for marker in ("config", "binding", "state")):
            categories.add("configuration")
        if any(
            marker in normalized
            for marker in ("adapter", "commit", "imagedigest", "adapterdigest")
        ):
            categories.add("adapter-continuity")
        if any(marker in normalized for marker in ("capability", "required", "ready")):
            categories.add("readiness")
    return sorted(categories or {"provider-readiness"})


def _sanitized_provider_readiness_report(
    environment: str,
    *,
    child_exit_code: int,
    child_stdout: str,
) -> tuple[dict[str, Any], bool]:
    """Keep Provider readiness evidence locatable without persisting child output."""
    import quwoquan_ops.cli.stackctl as _stackctl

    parsed: dict[str, Any] | None = None
    try:
        candidate = json.loads(child_stdout)
    except json.JSONDecodeError:
        candidate = None
    if isinstance(candidate, dict):
        parsed = candidate

    issues = parsed.get("issues") if parsed is not None else None
    readiness = parsed.get("readiness") if parsed is not None else None
    environment_readiness = (
        readiness.get(environment)
        if isinstance(readiness, dict)
        else None
    )
    report_is_valid = (
        parsed is not None
        and set(parsed)
        == {
            "schema",
            "evidenceCount",
            "executableSourceCount",
            "sourceCoverageIssues",
            "readiness",
            "issues",
        }
        and parsed.get("schema") == "provider-conformance-readiness"
        and isinstance(issues, list)
        and all(isinstance(issue, str) for issue in issues)
        and isinstance(parsed.get("sourceCoverageIssues"), list)
        and all(
            isinstance(issue, str) for issue in parsed["sourceCoverageIssues"]
        )
        and isinstance(parsed.get("executableSourceCount"), int)
        and parsed["executableSourceCount"] >= 0
        and isinstance(environment_readiness, dict)
        and isinstance(parsed.get("evidenceCount"), int)
        and parsed["evidenceCount"] >= 0
    )
    required_capabilities: list[dict[str, Any]] = []
    required_capabilities_ready = report_is_valid
    if isinstance(environment_readiness, dict):
        for capability_id, capability in sorted(environment_readiness.items()):
            if (
                not isinstance(capability_id, str)
                or not _stackctl._PROVIDER_CAPABILITY_ID_PATTERN.fullmatch(capability_id)
                or not isinstance(capability, dict)
                or not isinstance(capability.get("required"), bool)
                or not isinstance(capability.get("capability_ready"), bool)
            ):
                report_is_valid = False
                required_capabilities_ready = False
                continue
            if capability["required"]:
                ready = capability["capability_ready"]
                required_capabilities.append(
                    {
                        "capabilityId": capability_id,
                        "ready": ready,
                    }
                )
                required_capabilities_ready = required_capabilities_ready and ready
    else:
        required_capabilities_ready = False

    categories = _stackctl._provider_readiness_failure_categories(
        parsed,
        report_is_valid=report_is_valid,
        required_capabilities_ready=required_capabilities_ready,
        child_exit_code=child_exit_code,
    )
    passed = (
        child_exit_code == 0
        and report_is_valid
        and not issues
        and parsed is not None
        and parsed["evidenceCount"] > 0
        and required_capabilities_ready
    )
    return (
        {
            "schema": "stackctl-provider-readiness-preflight",
            "environment": environment,
            "status": "passed" if passed else "gate_block",
            "providerExitCode": child_exit_code,
            "evidenceCount": parsed["evidenceCount"] if report_is_valid else 0,
            "requiredCapabilities": required_capabilities,
            "failureCategories": [] if passed else categories,
        },
        passed,
    )


def _run_provider_readiness_preflight(
    environment: str,
    report_dir: Path,
) -> dict[str, Any]:
    """Run the single Provider readiness CLI and persist only its safe projection."""
    import quwoquan_ops.cli.stackctl as _stackctl

    command = [
        "python3",
        _stackctl.PROVIDER_CONFORMANCE_SCRIPT,
        "--require-ready",
        environment,
    ]
    try:
        result = _stackctl.run(
            command,
            # Provider readiness is environment-scoped. Neutralize any shell
            # target instead of incorrectly selecting one of prod's targets.
            env=_stackctl._verify_child_environment(""),
        )
        child_exit_code = result.returncode
        child_stdout = str(result.stdout or "")
    except OSError:
        child_exit_code = 127
        child_stdout = ""
    report, passed = _stackctl._sanitized_provider_readiness_report(
        environment,
        child_exit_code=child_exit_code,
        child_stdout=child_stdout,
    )
    report_path = report_dir / "provider-readiness.json"
    _stackctl.write_json(report_path, report)
    failure_categories = report["failureCategories"]
    details = (
        []
        if passed
        else [
            "provider readiness preflight is GATE_BLOCK "
            f"({', '.join(failure_categories)}); inspect {_stackctl.relpath(report_path)}"
        ]
    )
    return {
        "kind": "provider-readiness",
        "environment": environment,
        "argv": command,
        "exitCode": 0 if passed else 2,
        "reportPath": _stackctl.relpath(report_path),
        "details": details,
        "report": report,
    }


def _verify_child_environment(
    target_name: str,
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    """Bind every verify child to its selected target, never the parent shell."""
    import quwoquan_ops.cli.stackctl as _stackctl


    environment = dict(extra or {})
    environment[_stackctl.PACKAGE_ROOT_OVERRIDE_ENV] = ""
    environment[_stackctl.RUNTIME_CANDIDATE_ROOT_ENV] = ""
    if target_name in _stackctl.TARGETS:
        target = _stackctl.get_target(_stackctl.load_environment_topology(), target_name)
        runtime_environment = str(target.get("env") or "").strip()
        environment["QWQ_DEPLOY_TARGET"] = target_name
        environment["QWQ_APP_RUNTIME_ENV"] = runtime_environment
    else:
        environment["QWQ_DEPLOY_TARGET"] = ""
        environment["QWQ_APP_RUNTIME_ENV"] = ""
    return environment


def _read_json_object(path_value: str) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    path = Path(path_value)
    if not path.is_absolute():
        path = _stackctl.ROOT / path
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def fetch_url(
    url: str,
    timeout: float = 6.0,
    *,
    retry_attempts: int = 2,
    retry_sleep_seconds: float = 2.0,
    headers: dict[str, str] | None = None,
    ca_file: str = "",
    body_limit: int = 500,
) -> tuple[bool, int | None, str, str]:
    import quwoquan_ops.cli.stackctl as _stackctl

    retry_markers = (
        "timed out",
        "Remote end closed connection without response",
        "Connection reset",
        "Connection closed",
        "UNEXPECTED_EOF_WHILE_READING",
        "EOF occurred in violation of protocol",
    )
    total_attempts = max(1, retry_attempts)
    for attempt in range(1, total_attempts + 1):
        try:
            parsed = urllib.parse.urlsplit(url)
            local_target = _stackctl.target_for_hostname(parsed.hostname or "")
            if parsed.scheme == "https" and local_target is not None:
                return _stackctl._fetch_local_managed_url(
                    parsed,
                    local_target,
                    timeout=timeout,
                    headers=headers,
                    body_limit=body_limit,
                )
            request = urllib.request.Request(url, headers=headers or {})
            context = (
                ssl.create_default_context(cafile=ca_file)
                if parsed.scheme == "https" and ca_file
                else None
            )
            response = urllib.request.urlopen(
                request,
                timeout=timeout,
                context=context,
            )
            with response:
                body = response.read().decode("utf-8", errors="replace")
                return (
                    True,
                    int(response.status),
                    body[:body_limit],
                    str(response.headers.get("Content-Type") or ""),
                )
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            return False, int(exc.code), body[:body_limit], str(exc.headers.get("Content-Type") or "")
        except Exception as exc:
            if attempt >= total_attempts or not _stackctl._is_retryable_fetch_error(
                exc, retry_markers
            ):
                return False, None, str(exc), ""
            time.sleep(max(0.0, retry_sleep_seconds) * attempt)
    return False, None, "unknown fetch failure", ""


def _fetch_local_managed_url(
    parsed: urllib.parse.SplitResult,
    target: str,
    *,
    timeout: float,
    headers: dict[str, str] | None,
    body_limit: int,
) -> tuple[bool, int | None, str, str]:
    import quwoquan_ops.cli.stackctl as _stackctl

    from quwoquan_ops.cli.lib.public_domain_tls import root_certificate_path

    root = root_certificate_path(target)
    context = ssl.create_default_context(cafile=str(root))
    connection = _stackctl._CanonicalLocalHTTPSConnection(
        parsed.hostname or "",
        port=parsed.port or 443,
        timeout=timeout,
        context=context,
    )
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    try:
        connection.request("GET", path, headers=headers or {})
        response = connection.getresponse()
        body = response.read().decode("utf-8", errors="replace")
        content_type = str(response.headers.get("Content-Type") or "")
        status = int(response.status)
        return status < 400, status, body[:body_limit], content_type
    finally:
        connection.close()


def _is_retryable_fetch_error(exc: Exception, retry_markers: tuple[str, ...]) -> bool:
    if isinstance(
        exc,
        (
            TimeoutError,
            ConnectionAbortedError,
            ConnectionRefusedError,
            ConnectionResetError,
        ),
    ):
        return True
    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        if isinstance(
            reason,
            (
                TimeoutError,
                ConnectionAbortedError,
                ConnectionRefusedError,
                ConnectionResetError,
            ),
        ):
            return True
    return any(marker in str(exc) for marker in retry_markers)


def _startup_health_failure_for_report(
    report_dir: Path,
    *,
    target: str,
    candidate_digest: str,
    startup_exit_code: int,
) -> tuple[dict[str, Any], str]:
    import quwoquan_ops.cli.stackctl as _stackctl

    if startup_exit_code == 0:
        return {}, ""
    path = report_dir / "startup-health-failure.json"
    if not path.exists():
        return {}, ""
    try:
        evidence = _stackctl.startup_health_failure_evidence.load(
            path,
            target=target,
            candidate_digest=candidate_digest,
            service="content-service",
        )
    except _stackctl.startup_health_failure_evidence.StartupHealthFailureEvidenceError as exc:
        return {}, str(exc)
    return evidence, ""


def _content_release_public_ready_attempts(target: dict[str, Any]) -> int:
    data_release = target.get("dataRelease")
    if not isinstance(data_release, dict):
        raise RuntimeError("GATE_BLOCK: content release target has no dataRelease policy")
    value = data_release.get("publicReadyTimeoutSeconds")
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise RuntimeError(
            "GATE_BLOCK: dataRelease.publicReadyTimeoutSeconds must be a positive integer"
        )
    return value


def _read_json_payload(path: Path) -> Any | None:
    import quwoquan_ops.cli.stackctl as _stackctl

    if not path.exists():
        return None
    try:
        return _stackctl.load_json_yaml(path)
    except Exception:  # noqa: BLE001
        return None


def _resolve_test_auth_token(env_name: str) -> str:
    token_envs = {
        "alpha": ("ALPHA_TEST_AUTH_TOKEN", "TEST_AUTH_TOKEN"),
        "beta": ("BETA_TEST_AUTH_TOKEN", "TEST_AUTH_TOKEN"),
        "gamma": ("GAMMA_TEST_AUTH_TOKEN", "TEST_AUTH_TOKEN"),
        "prod": ("PROD_TEST_AUTH_TOKEN", "TEST_AUTH_TOKEN"),
    }
    for key in token_envs.get(env_name, ("TEST_AUTH_TOKEN",)):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return ""


def _run_script_probe(
    *,
    name: str,
    scope: str,
    argv: list[str],
    report_file: Path | None = None,
    env: dict[str, str] | None = None,
    timeout_seconds: float | None = None,
) -> tuple[dict[str, Any], str, list[str]]:
    import quwoquan_ops.cli.stackctl as _stackctl

    result = _stackctl.run(argv, env=env, timeout_seconds=timeout_seconds)
    output = "\n".join(filter(None, [result.stdout, result.stderr])).strip()
    report_payload = _stackctl._read_json_payload(report_file) if report_file else None
    report_status = ""
    report_findings: list[str] = []
    preview = output[:500]
    if isinstance(report_payload, dict):
        report_status = str(report_payload.get("status", "")).strip().lower()
        preview = str(
            report_payload.get("blockingReason")
            or report_payload.get("summary")
            or report_payload.get("status")
            or preview
        )[:500]
        for item in _stackctl.ensure_list(report_payload.get("findings")):
            if isinstance(item, str) and item.strip():
                report_findings.append(item.strip())
        blocking_reason = str(report_payload.get("blockingReason", "")).strip()
        if blocking_reason:
            report_findings.append(blocking_reason)
    ok = result.returncode == 0 and report_status not in {"failed", "gate_block", "error"}
    if not ok and not report_findings:
        report_findings.append(
            f"{scope}/{name} failed: exit={result.returncode} {argv[-1] if argv else name}"
        )
    payload = {
        "name": name,
        "scope": scope,
        "type": "script",
        "argv": argv,
        "ok": ok,
        "statusCode": result.returncode,
        "bodyPreview": preview,
        "skipped": False,
        "reportPath": _stackctl.relpath(report_file) if report_file else "",
    }
    return payload, output, report_findings


def _run_environment_integration_probe(
    topology: dict[str, Any],
    target_name: str,
    report_dir: Path,
    *,
    require_non_empty_content_feed: bool = False,
    research_anonymous_convergence: bool = False,
    research_consumer_token: str = "",
    release_post_expectations: dict[str, set[str]] | None = None,
    release_search_canaries: Sequence[Mapping[str, str]] = (),
    release_samples: Sequence[Mapping[str, Any]] = (),
    release_readiness_path: Path | None = None,
    video_page_size: int = 1,
    only_checks: tuple[str, ...] = (),
    probe_name: str = "integration-readonly",
    timeout_seconds: float | None = None,
) -> tuple[dict[str, Any], str, list[str]]:
    import quwoquan_ops.cli.stackctl as _stackctl

    target = _stackctl.get_target(topology, target_name)
    env_name = str(target["env"])
    public_bases = target.get("publicBases") or {}
    report_file = report_dir / "integration-probe.json"
    argv = [
        "python3",
        "quwoquan_ops/cli/probes/run_environment_integration_probe.py",
        "--env",
        env_name,
        "--base-url",
        str(public_bases["api"]),
        "--report",
        str(report_file),
    ]
    if require_non_empty_content_feed:
        argv.append("--require-non-empty-content-feed")
    if research_anonymous_convergence:
        argv.append("--research-anonymous-convergence")
    if research_consumer_token:
        # research consumer 凭证只经环境变量注入探针子进程，不落 argv。
        argv.append("--research-consumer-readback")
    for check_name in only_checks:
        argv.extend(["--only-check", check_name])
    expectation_flags = {
        "content_feed": "--expected-discovery-post-id",
        "video_book_feed": "--expected-video-post-id",
        "premium_feed": "--expected-premium-video-post-id",
    }
    for check_name, post_ids in (release_post_expectations or {}).items():
        flag = expectation_flags.get(check_name)
        if flag is None:
            raise ValueError(f"unsupported release feed expectation: {check_name}")
        for post_id in sorted(post_ids):
            argv.extend([flag, post_id])
    if release_search_canaries:
        for canary in release_search_canaries:
            argv.extend(
                [
                    "--release-search-canary",
                    json.dumps(
                        dict(canary),
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                ]
            )
    for sample in release_samples:
        argv.extend(
            [
                "--release-sample",
                json.dumps(
                    dict(sample),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            ]
        )
    if video_page_size != 1:
        argv.extend(["--video-page-size", str(video_page_size)])
    if target_name == "prod-hosted":
        request_timeout = 20
        retry_attempts = 3
        retry_sleep_seconds = 3
        if timeout_seconds is not None:
            request_timeout = max(1, min(request_timeout, int(timeout_seconds)))
            retry_attempts = 1
            retry_sleep_seconds = 0
        argv.extend(
            [
                "--mode",
                "post-deploy",
                "--request-timeout-seconds",
                str(request_timeout),
                "--retry-attempts",
                str(retry_attempts),
                "--retry-sleep-seconds",
                str(retry_sleep_seconds),
            ]
        )
    product_ops = str(public_bases.get("productOps") or "").strip()
    if product_ops:
        argv.extend(["--product-ops-base-url", product_ops])
    media_image = str(public_bases.get("mediaImage") or "").strip()
    if release_readiness_path is not None:
        argv.extend(["--release-readiness", str(release_readiness_path)])
    if media_image and release_readiness_path is not None:
        argv.extend(
            [
                "--media-image-base-url",
                media_image,
            ]
        )
    token = research_consumer_token or _stackctl._resolve_test_auth_token(env_name)
    temporary_actor: Any | None = None
    temporary_actor_instance_id = ""
    public_release_checks = {
        "content_feed",
        "video_book_feed",
        "premium_feed",
        "media_sample",
    }
    requires_reference_identity = not only_checks or any(
        check_name not in public_release_checks for check_name in only_checks
    )
    if (
        env_name in {"beta", "gamma"}
        and not token
        and requires_reference_identity
    ):
        # Health/probe callers never reuse a retained mutable account. One
        # isolated actor lives exactly for this script body and is then closed.
        previous_ssl_cert_file = os.environ.get("SSL_CERT_FILE")
        os.environ["SSL_CERT_FILE"] = str(_stackctl.root_certificate_path(target_name))
        try:
            temporary_actor_instance_id = "probe-" + uuid4().hex
            temporary_actor = _stackctl.open_test_data_acceptance_session(
                str(public_bases["api"]),
                environment=env_name,
                target_name=target_name,
                test_data_instance_id=temporary_actor_instance_id,
                actor_role="primary",
                actor_index=0,
            )
            token = temporary_actor.session.access_token
        except (OSError, RuntimeError, ValueError) as exc:
            finding = f"{target_name} integration auth failed: {exc}"
            return (
                {
                    "name": probe_name,
                    "scope": "full",
                    "type": "script",
                    "argv": argv,
                    "ok": False,
                    "statusCode": 1,
                    "bodyPreview": finding,
                    "skipped": False,
                    "reportPath": _stackctl.relpath(report_file),
                },
                finding,
                [finding],
            )
        finally:
            if previous_ssl_cert_file is None:
                os.environ.pop("SSL_CERT_FILE", None)
            else:
                os.environ["SSL_CERT_FILE"] = previous_ssl_cert_file
    probe_env: dict[str, str] = {}
    if target_name in {"alpha-local", "beta-local", "gamma-local"}:
        probe_env["SSL_CERT_FILE"] = str(_stackctl.root_certificate_path(target_name))
    if token:
        probe_env["TEST_AUTH_TOKEN"] = token
        if env_name == "gamma":
            probe_env["GAMMA_TEST_AUTH_TOKEN"] = token
        elif env_name == "beta":
            probe_env["BETA_TEST_AUTH_TOKEN"] = token
        elif env_name == "prod":
            probe_env["PROD_TEST_AUTH_TOKEN"] = token
    probe_result = _stackctl._run_script_probe(
        name=probe_name,
        scope="full",
        argv=argv,
        report_file=report_file,
        env=probe_env or None,
        timeout_seconds=timeout_seconds,
    )
    if temporary_actor is not None:
        try:
            _stackctl.close_test_data_acceptance_actor(
                str(public_bases["api"]),
                actor=temporary_actor,
                test_data_instance_id=temporary_actor_instance_id,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            finding = f"{target_name} integration actor cleanup failed: {exc}"
            return (
                {
                    "name": probe_name,
                    "scope": "full",
                    "type": "script",
                    "argv": argv,
                    "ok": False,
                    "statusCode": 2,
                    "bodyPreview": finding,
                    "skipped": False,
                    "reportPath": _stackctl.relpath(report_file),
                },
                finding,
                [finding],
            )
    return probe_result
