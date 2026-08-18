"""stackctl `app-content-uat` 域 test-live 运行时绑定、typed Actor 与证据判定。

从 commands/app_preflight_uat.py 逐字迁出(该模块保留 UAT dart 目标常量
家族与 `command_app_content_uat` 编排主干,绑定/证据家族随本职责聚合到
本模块):

- `_app_content_patrol_evidence`:Patrol 报告的证据投影与截图 digest;
- `_APP_CONTENT_TEST_LIVE_STARTUP_IDENTITY_FIELDS` /
  `_app_content_test_live_runtime_binding`:UAT target 到 running mutable
  runtime 与 Data run 的精确身份绑定;
- `_app_content_test_live_actor_context`:typed UAT Actor scope 到 mutable
  runtime 与 release 的绑定;
- `_ios_direct_flutter_log_reader_retryable`:iOS 日志读取器丢失后的
  fresh run 重试判定。

UAT dart 目标常量与 `_app_content_uat_requires_typed_actor` /
`_command_app_content_uat` 在 `commands/app_preflight_uat.py`。测试经
``mock.patch.object(stackctl, ...)`` patch 本模块符号与协作符号,因此
函数体内一律经函数内延迟导入 `_stackctl` 属性访问(含本模块符号互调),
保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

from quwoquan_ops.cli.lib.test_data.capabilities.chat_service import (
    DIRECT_CONVERSATION_WITH_MESSAGES,
    DirectConversationResult,
    DirectConversationWithMessagesParams,
)
from quwoquan_ops.cli.lib.test_data.capabilities.common import ActorRole
from quwoquan_ops.cli.lib.test_data.capabilities.user_service import (
    AUTHENTICATED_ACTORS,
    AuthenticatedActorsParams,
    MutualActorRelationship,
)
from quwoquan_ops.cli.lib.test_data.model import TestDataContext
from quwoquan_ops.cli.lib.test_data.operations import TestDataRuntime
from quwoquan_ops.cli.smoke.environment_patrol_smoke.constants import (
    TYPED_TEST_DATA_ACTOR_ENV,
    TYPED_TEST_DATA_CONVERSATION_ENV,
)


def _app_content_patrol_evidence(report_ref: str) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    report_path = Path(report_ref)
    if not report_path.is_absolute():
        report_path = _stackctl.ROOT / report_path
    report = _stackctl._read_json_object(str(report_path))
    report_runs = report.get("runs")
    if not isinstance(report_runs, list):
        report_runs = []
    selected = next(
        (
            item
            for item in report_runs
            if isinstance(item, dict) and int(item.get("exitCode", 1)) == 0
        ),
        {},
    )
    evidence = selected.get("evidence") if isinstance(selected, dict) else {}
    evidence = evidence if isinstance(evidence, dict) else {}
    screenshot = evidence.get("afterScreenshot")
    screenshot = screenshot if isinstance(screenshot, dict) else {}
    screenshot_marker = screenshot.get("marker")
    screenshot_marker = (
        screenshot_marker if isinstance(screenshot_marker, dict) else {}
    )
    screenshot_is_live_page = (
        screenshot.get("status") == "captured"
        and screenshot.get("capturedDuringPatrol") is True
        and all(
            str(screenshot_marker.get(field) or "").strip()
            for field in ("environment", "suite", "route", "terminalKey")
        )
    )
    screenshot_ref = str(screenshot.get("path") or "").strip()
    screenshot_path = Path(screenshot_ref)
    if screenshot_ref and not screenshot_path.is_absolute():
        screenshot_path = _stackctl.ROOT / screenshot_path
    screenshot_digest = (
        "sha256:" + hashlib.sha256(screenshot_path.read_bytes()).hexdigest()
        if screenshot_is_live_page and screenshot_ref and screenshot_path.is_file()
        else ""
    )
    return {
        "status": str(report.get("status") or ""),
        "device": selected.get("device", {}) if isinstance(selected, dict) else {},
        "testExecution": (
            selected.get("testExecution", {}) if isinstance(selected, dict) else {}
        ),
        "consumerLease": evidence.get("consumerLease", {}),
        "feedContent": evidence.get("feedContent", {}),
        "controlledEdgeFault": evidence.get("controlledEdgeFault", {}),
        "controlledEdgeFaultReceipt": evidence.get(
            "controlledEdgeFaultReceipt", {}
        ),
        "screenshotRef": screenshot_ref,
        "screenshotDigest": screenshot_digest,
        "screenshotMarker": screenshot_marker if screenshot_is_live_page else {},
        "remoteApi": report.get("remoteApiEvidence", {}),
    }



_APP_CONTENT_TEST_LIVE_STARTUP_IDENTITY_FIELDS = (
    "sourceRevision",
    "workspaceStatusDigest",
    "mutableStateDigest",
    "composeDigest",
    "configurationDigest",
    "providerRuntimeDigest",
    "resolverHandoffDigest",
)


def _app_content_test_live_runtime_binding(
    preflight: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind one UAT target to its exact running mutable runtime and Data run."""
    import quwoquan_ops.cli.stackctl as _stackctl

    target = str(preflight.get("target") or "").strip()
    environment = str(preflight.get("environment") or "").strip()
    if (
        preflight.get("launchPolicy") != "test_live"
        or target != f"{environment}-local"
        or environment not in {"alpha", "beta", "gamma"}
    ):
        raise ValueError("App content UAT requires canonical non-production test_live")
    if str(preflight.get("packageBaseline") or ""):
        raise ValueError("test_live App content UAT must not consume a package baseline")

    startup = _stackctl.load_test_live_startup_attempt(target)
    if (
        not isinstance(startup, dict)
        or startup.get("status") != "running"
        or startup.get("failure") not in {None, ""}
    ):
        raise ValueError("App content UAT requires the current running test_live receipt")
    content = _stackctl.load_test_live_content_binding(target)
    if not isinstance(content, dict):
        raise ValueError("App content UAT requires a run-bound content binding")
    if (
        content.get("launchPolicy") != "test_live"
        or content.get("nonPromotable") is not True
        or content.get("retentionClass") != "run_bound"
        or content.get("contentBindingState") != "bound"
        or content.get("environment") != environment
        or content.get("target") != target
        or content.get("startupAttemptId") != startup.get("attemptId")
    ):
        raise ValueError("App content UAT test_live binding identity drifted")

    startup_identity = content.get("startupIdentity")
    if not isinstance(startup_identity, Mapping):
        raise ValueError("App content UAT test_live startup identity is missing")
    for field in _stackctl._APP_CONTENT_TEST_LIVE_STARTUP_IDENTITY_FIELDS:
        if str(startup_identity.get(field) or "") != str(startup.get(field) or ""):
            raise ValueError(f"App content UAT test_live startup identity drifted: {field}")

    expected_preflight = {
        "contentBindingState": "bound",
        "configurationDigest": startup["configurationDigest"],
        "providerRuntimeDigest": startup["providerRuntimeDigest"],
        "sourceRevision": startup["sourceRevision"],
        "releaseId": content["releaseId"],
        "manifestDigest": content["manifestDigest"],
        "readinessReceiptRef": content["readinessReceiptRef"],
        "readinessReceiptDigest": content["readinessReceiptDigest"],
        "lifecycleExitRef": content["lifecycleExitRef"],
        "appUatEnvelope": content["appUatEnvelope"],
        "appUatPlan": content["appUatPlan"],
        "appUatPlanDigest": content["appUatPlanDigest"],
    }
    for field, expected in expected_preflight.items():
        if preflight.get(field) != expected:
            raise ValueError(f"App content UAT preflight/binding drifted: {field}")

    return {
        "launchPolicy": "test_live",
        "nonPromotable": True,
        "environment": environment,
        "target": target,
        "startupAttemptId": startup["attemptId"],
        "composeProject": startup["composeProject"],
        "runRoot": startup["runRoot"],
        "startupIdentity": {
            field: str(startup[field])
            for field in _stackctl._APP_CONTENT_TEST_LIVE_STARTUP_IDENTITY_FIELDS
        },
        "contentBindingState": "bound",
        "retentionClass": "run_bound",
        "releaseId": content["releaseId"],
        "verifyRunId": content["verifyRunId"],
        "manifestDigest": content["manifestDigest"],
        "readinessPhase": content["readinessPhase"],
        "readinessReceiptRef": content["readinessReceiptRef"],
        "readinessReceiptDigest": content["readinessReceiptDigest"],
        "lifecycleExitRef": content["lifecycleExitRef"],
        "appUatPlan": content["appUatPlan"],
        "appUatPlanDigest": content["appUatPlanDigest"],
    }


def _app_content_test_live_actor_context(
    *,
    preflight: Mapping[str, Any],
    runtime_binding: Mapping[str, Any],
    readiness_path: Path,
    report_dir: Path,
) -> TestDataContext:
    """Bind one typed UAT Actor scope to the exact mutable runtime and release."""
    import quwoquan_ops.cli.stackctl as _stackctl

    target = str(runtime_binding.get("target") or "").strip()
    environment = str(runtime_binding.get("environment") or "").strip()
    startup = runtime_binding.get("startupIdentity")
    if not isinstance(startup, Mapping):
        raise ValueError("App content UAT typed Actor startup identity is missing")
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    if not isinstance(readiness, Mapping):
        raise ValueError("App content UAT typed Actor readiness is invalid")
    expected_readiness = {
        "passed": True,
        "environment": environment,
        "releaseId": runtime_binding.get("releaseId"),
        "verifyRunId": runtime_binding.get("verifyRunId"),
        "manifestDigest": runtime_binding.get("manifestDigest"),
        "readinessPhase": runtime_binding.get("readinessPhase"),
    }
    if any(readiness.get(field) != value for field, value in expected_readiness.items()):
        raise ValueError("App content UAT typed Actor readiness identity drifted")
    candidate = _stackctl.build_candidate_binding(
        environment=environment,
        target=target,
        manifest={
            "sourceRevision": str(startup.get("sourceRevision") or ""),
            "baselineId": str(startup.get("mutableStateDigest") or ""),
            "packageDigest": str(startup.get("composeDigest") or ""),
            "runtimeConfigDigest": str(startup.get("configurationDigest") or ""),
            "release": {
                "candidate": {
                    "releaseId": str(runtime_binding.get("releaseId") or ""),
                    "releaseDigest": str(
                        runtime_binding.get("manifestDigest") or ""
                    ),
                }
            },
        },
        readiness=readiness,
        allow_consumer=True,
    )
    provider = preflight.get("provider")
    login = preflight.get("loginJourney")
    if not isinstance(provider, Mapping) or not isinstance(login, Mapping):
        raise ValueError("App content UAT typed Actor Provider evidence is missing")
    provider_expected = {
        "adapterId": "ext.sms.local_capture",
        "environment": environment,
        "configurationDigest": startup.get("configurationDigest"),
        "nonPromotable": True,
        "ready": True,
    }
    if any(provider.get(field) != value for field, value in provider_expected.items()):
        raise ValueError("App content UAT typed Actor Provider identity drifted")
    if (
        login.get("status") != "passed"
        or login.get("challengePresent") is not True
        or login.get("sessionPresent") is not True
        or login.get("startupAttemptId") != runtime_binding.get("startupAttemptId")
        or login.get("nonPromotable") is not True
        or not str(login.get("receiptRef") or "").strip()
        or re.fullmatch(r"sha256:[0-9a-f]{64}", str(login.get("receiptDigest") or ""))
        is None
    ):
        raise ValueError("App content UAT typed Actor OTP evidence drifted")
    identity_provider_capability = (
        AUTHENTICATED_ACTORS.required_provider_capabilities[0].value
    )
    provider_evidence = {
        identity_provider_capability: {
            "status": "passed",
            "candidateBindingDigest": candidate.digest,
            "adapterId": provider["adapterId"],
            "receiptRef": login["receiptRef"],
            "receiptDigest": login["receiptDigest"],
        }
    }
    topology_target = _stackctl.get_target(_stackctl.load_environment_topology(), target)
    base_url = str(
        ((topology_target.get("publicBases") or {}).get("api") or "")
    ).rstrip("/")
    return TestDataContext(
        candidate=candidate,
        base_url=base_url,
        output_root=report_dir / target / "test-data",
        provider_evidence=provider_evidence,
        runtime=TestDataRuntime(),
    )


def _run_app_content_message_home_command(
    profile_command: Mapping[str, Any],
    *,
    target_name: str,
    actor_context: TestDataContext | None,
) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    """Run Message Home P0 inside one typed provision/Patrol/cleanup scope."""
    import quwoquan_ops.cli.stackctl as _stackctl

    if actor_context is None:
        raise RuntimeError("message page UAT typed test-data context is unavailable")
    runtime = actor_context.runtime
    if not isinstance(runtime, TestDataRuntime):
        raise TypeError("message page UAT typed test-data runtime is unavailable")

    test_data_instance_id = str(uuid.uuid4())
    scoped_context = replace(
        actor_context,
        output_root=actor_context.output_root / "message-home",
        test_data_instance_id=test_data_instance_id,
    )
    actors = AUTHENTICATED_ACTORS.bind(
        AuthenticatedActorsParams(
            roles=(ActorRole.SENDER, ActorRole.RECEIVER),
            mutual_relationships=(
                MutualActorRelationship(
                    source_role=ActorRole.SENDER,
                    target_role=ActorRole.RECEIVER,
                ),
            ),
        )
    )
    request = DIRECT_CONVERSATION_WITH_MESSAGES.bind(
        DirectConversationWithMessagesParams(
            actors=actors.output.whole(),
            sender_role=ActorRole.SENDER,
            receiver_role=ActorRole.RECEIVER,
            message_count=2,
        )
    )
    session = _stackctl.TestDataSession.for_case(
        _stackctl.ProfileActorCaseId.APP_CONTENT_UAT,
        context=scoped_context,
    )
    command_environment = dict(profile_command.get("env") or {})
    # `_stackctl.run` merges the parent process environment; explicit blanks
    # prevent stale ambient credentials/handles from crossing into this child.
    for key in (
        "TEST_AUTH_TOKEN",
        "TEST_REFRESH_TOKEN",
        "APP_CURRENT_OWNER_ID",
        "APP_CURRENT_PERSONA_ID",
        *TYPED_TEST_DATA_ACTOR_ENV.values(),
        *TYPED_TEST_DATA_CONVERSATION_ENV.values(),
    ):
        command_environment[key] = ""

    root_provision_receipt = None
    with session.provision(request) as provisioned:
        if not isinstance(provisioned.value, DirectConversationResult):
            raise TypeError("message page UAT typed conversation result is invalid")
        receiver_handle = runtime.actor_for(
            test_data_instance_id=test_data_instance_id,
            role=ActorRole.RECEIVER,
        )
        receiver = runtime.actor(receiver_handle)
        command_environment.update(
            {
                TYPED_TEST_DATA_ACTOR_ENV["access_token"]: receiver.session.access_token,
                TYPED_TEST_DATA_ACTOR_ENV["refresh_token"]: receiver.session.refresh_token,
                TYPED_TEST_DATA_ACTOR_ENV["owner_id"]: receiver.session.owner_id,
                TYPED_TEST_DATA_ACTOR_ENV["persona_id"]: receiver.session.persona_id,
                TYPED_TEST_DATA_CONVERSATION_ENV["conversation_id"]: provisioned.value.conversation.object_id,
                TYPED_TEST_DATA_CONVERSATION_ENV["message_ids_json"]: json.dumps(
                    [
                        message.message.object_id
                        for message in provisioned.value.messages
                    ],
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            }
        )
        root_provision_receipt = provisioned.receipt
        result = _stackctl.run(
            list(profile_command["argv"]),
            cwd=profile_command.get("cwd"),
            env=_stackctl._verify_child_environment(
                target_name,
                command_environment,
            ),
        )

    if root_provision_receipt is None:
        raise RuntimeError("message page UAT preparation receipt is unavailable")
    scope_evidence = _stackctl._link_profile_preparation_to_page_report(
        profile_command,
        root_provision_receipt,
    )
    return result, scope_evidence


def _ios_direct_flutter_log_reader_retryable(
    evidence: Mapping[str, Any],
) -> bool:
    """Return whether a fresh run is required after Flutter lost its log reader.

    The prior run must still prove one healthy cold terminal.  This never turns
    that failed report into evidence; it only permits one new, fully validated
    direct run so the three required hot restarts can be observed.
    """

    if evidence.get("status") != "failed":
        return False
    issues = evidence.get("issues")
    if issues != ["expected 3 hot-restart Dart startup attempts, got 0"]:
        return False
    attempts = evidence.get("attempts")
    if not isinstance(attempts, list) or len(attempts) != 1:
        return False
    cold = attempts[0]
    if (
        not isinstance(cold, Mapping)
        or cold.get("hotRestart") is not False
        or cold.get("canonicalTerminal") != "routerShell"
        or cold.get("configurationState") != "complete"
        or cold.get("bootstrapFailure") is not False
        or cold.get("terminalEventCount") != 1
    ):
        return False
    for field in ("reportedSafeTerminalMs", "nativeReceivedSafeTerminalMs"):
        value = cold.get(field)
        if not isinstance(value, int) or value > 6000:
            return False
    log_ref = str(evidence.get("flutterRunLog") or "").strip()
    if not log_ref:
        return False
    try:
        log_text = Path(log_ref).read_text(encoding="utf-8")
    except OSError:
        return False
    return (
        "Error waiting for a debug connection: "
        "The log reader failed unexpectedly" in log_text
    )
