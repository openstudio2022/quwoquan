"""stackctl `app-content-uat` immutable 运行时绑定、typed Actor 与证据判定。

从 commands/app_preflight_uat.py 逐字迁出(该模块保留 UAT dart 目标常量
家族与 `command_app_content_uat` 编排主干,绑定/证据家族随本职责聚合到
本模块):

- `_app_content_patrol_evidence`:Patrol 报告的证据投影与截图 digest;
- `_app_content_immutable_runtime_binding`:UAT target 到 active candidate、
  running startup attempt 与 Data release 的精确身份绑定;
- `_app_content_immutable_actor_context`:typed UAT Actor scope 到真实
  candidate manifest 与 release 的绑定;
- `_ios_direct_flutter_log_reader_retryable`:iOS 日志读取器丢失后的
  fresh run 重试判定。

UAT dart 目标常量与 `_app_content_uat_requires_typed_actor` /
`_command_app_content_uat` 在 `commands/app_preflight_uat.py`。测试经
``mock.patch.object(stackctl, ...)`` patch 本模块符号与协作符号,因此
函数体内一律经函数内延迟导入 `_stackctl` 属性访问(含本模块符号互调),
保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import json
import re
import subprocess
import uuid
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.commands.app_preflight_uat_binding_contract import (
    _APP_CONTENT_IMMUTABLE_STARTUP_IDENTITY_FIELDS,
    _APP_CONTENT_TEST_LIVE_STARTUP_IDENTITY_FIELDS,
    _DIGEST_RE,
)
from quwoquan_ops.cli.commands.app_preflight_uat_launch_binding import (
    _app_content_launch_binding,
    _launch_evidence_path,
    _verified_app_content_projection_build_seal,
)
from quwoquan_ops.cli.commands.app_preflight_uat_page_evidence import (
    _app_content_page_artifact_binding,
    _app_content_patrol_evidence,
    _controlled_edge_recovery_evidence_issue,
)
from quwoquan_ops.cli.lib.content_release_readiness import ReadinessPhase
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
from quwoquan_ops.cli.smoke.environment_patrol_smoke.artifact_binding import (
    APP_PAGE_ARTIFACT_BINDING_BLOCKER,
)
from quwoquan_ops.cli.smoke.environment_patrol_smoke.constants import (
    TYPED_TEST_DATA_ACTOR_ENV,
    TYPED_TEST_DATA_CONVERSATION_ENV,
)

__all__ = [
    "APP_PAGE_ARTIFACT_BINDING_BLOCKER",
    "_APP_CONTENT_TEST_LIVE_STARTUP_IDENTITY_FIELDS",
    "_app_content_launch_binding",
    "_app_content_page_artifact_binding",
    "_app_content_patrol_evidence",
    "_controlled_edge_recovery_evidence_issue",
    "_ios_direct_flutter_log_reader_retryable",
    "_launch_evidence_path",
    "_verified_app_content_projection_build_seal",
]



def _verified_app_content_readiness(
    preflight: Mapping[str, Any],
) -> tuple[dict[str, Any], Path]:
    """Load the exact canonical readiness bytes projected by debug preflight."""
    import quwoquan_ops.cli.stackctl as _stackctl

    environment = str(preflight.get("environment") or "").strip()
    release_id = str(preflight.get("releaseId") or "").strip()
    manifest_digest = str(preflight.get("manifestDigest") or "").strip()
    readiness_ref = str(preflight.get("readinessReceiptRef") or "").strip()
    if not readiness_ref:
        raise ValueError("App content UAT readiness receipt reference is missing")
    evidence_root = _stackctl.output_root().expanduser().resolve()
    candidate = Path(readiness_ref).expanduser()
    if candidate.is_absolute():
        readiness_path = candidate.resolve()
    else:
        repo_relative = (_stackctl.ROOT / candidate).resolve()
        readiness_path = (
            repo_relative
            if repo_relative.is_relative_to(evidence_root)
            else (evidence_root / candidate).resolve()
        )
    try:
        readiness_path.relative_to(evidence_root)
    except ValueError as exc:
        raise ValueError(
            "App content UAT readiness receipt escapes QWQ_OUTPUT_ROOT"
        ) from exc
    if readiness_path.is_symlink() or not readiness_path.is_file():
        raise ValueError("App content UAT readiness receipt is missing")
    readiness = _stackctl._read_json_object(str(readiness_path))
    if (
        _stackctl._canonical_document_checksum(readiness)
        != preflight.get("readinessReceiptDigest")
    ):
        raise ValueError("App content UAT readiness receipt digest drifted")
    try:
        readiness_phase = ReadinessPhase(str(readiness.get("readinessPhase") or ""))
    except ValueError as exc:
        raise ValueError("App content UAT readiness phase is invalid") from exc
    canonical, canonical_path = _stackctl._load_data_release_readiness(
        environment=environment,
        release_id=release_id,
        verify_run_id=str(readiness.get("verifyRunId") or ""),
        manifest_digest=manifest_digest,
        readiness_phase=readiness_phase,
    )
    if canonical_path.resolve() != readiness_path or canonical != readiness:
        raise ValueError("App content UAT readiness canonical identity drifted")
    expected = {
        "passed": True,
        "environment": environment,
        "releaseId": release_id,
        "manifestDigest": manifest_digest,
        "appUatEnvelope": preflight.get("appUatEnvelope"),
        "appUatEnvelopeDigest": preflight.get("appUatEnvelopeDigest"),
    }
    if any(readiness.get(field) != value for field, value in expected.items()):
        raise ValueError("App content UAT readiness/preflight identity drifted")
    return canonical, readiness_path


def _app_content_readiness_path(preflight: Mapping[str, Any]) -> Path:
    return _verified_app_content_readiness(preflight)[1]


def _candidate_runtime_identities(
    *,
    manifest: Mapping[str, Any],
    provider_binding: Mapping[str, Any],
    observability_binding: Mapping[str, Any],
) -> dict[str, str]:
    artifact = manifest.get("environmentArtifact")
    source_capsule = (
        artifact.get("sourceCapsule") if isinstance(artifact, Mapping) else None
    )
    configuration = (
        artifact.get("configuration") if isinstance(artifact, Mapping) else None
    )
    artifact_provider = (
        artifact.get("provider") if isinstance(artifact, Mapping) else None
    )
    provider_composition = provider_binding.get("composition")
    observability_composition = observability_binding.get("composition")
    if not all(
        isinstance(value, Mapping)
        for value in (
            artifact,
            source_capsule,
            configuration,
            artifact_provider,
            provider_composition,
            observability_composition,
        )
    ):
        raise ValueError("App content UAT immutable candidate identity is incomplete")
    return {
        "artifactBaseline": str(source_capsule.get("baselineId") or ""),
        "sourceRevision": str(source_capsule.get("sourceRevision") or ""),
        "sourceCapsuleDigest": str(source_capsule.get("digest") or ""),
        "sourceCapsuleWorkspaceStatusDigest": str(
            source_capsule.get("workspaceStatusDigest") or ""
        ),
        "releaseTrainId": str(artifact.get("releaseTrainId") or ""),
        "environmentArtifactDigest": str(
            artifact.get("environmentArtifactDigest") or ""
        ),
        "packageDigest": str(artifact.get("packageDigest") or ""),
        "configurationDigest": str(configuration.get("serviceDigest") or ""),
        "runtimeConfigDigest": str(configuration.get("appRuntimeDigest") or ""),
        "environmentRuntimeDigest": str(
            configuration.get("environmentRuntimeDigest") or ""
        ),
        "providerRuntimeDigest": str(
            provider_composition.get("runtimeCompositionDigest") or ""
        ),
        "artifactProviderRuntimeDigest": str(
            artifact_provider.get("runtimeCompositionDigest") or ""
        ),
        "observabilityLogSinkDigest": str(
            observability_composition.get("composeDigest") or ""
        ),
    }


def _app_content_immutable_runtime_binding(
    preflight: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind UAT to one fully validated immutable candidate/startup/release."""
    import quwoquan_ops.cli.stackctl as _stackctl

    target = str(preflight.get("target") or "").strip()
    environment = str(preflight.get("environment") or "").strip()
    expected_preflight_state = {
        "launchPolicy": "immutable_candidate",
        "purpose": "content_live",
        "nonPromotable": False,
        "contentBindingState": "bound",
        "contentLive": "passed",
        "status": "passed",
    }
    if (
        target != f"{environment}-local"
        or environment not in {"alpha", "beta", "gamma"}
        or any(
            preflight.get(field) != value
            for field, value in expected_preflight_state.items()
        )
    ):
        raise ValueError(
            "App content UAT requires canonical immutable content_live preflight"
        )

    snapshot = _stackctl.active_deployment_candidate_snapshot(target)
    if not isinstance(snapshot, Mapping):
        raise TypeError("App content UAT requires an active immutable candidate")
    baseline, candidate_root, manifest = _stackctl._fixed_candidate_identity(
        snapshot,
        environment_name=environment,
        target_name=target,
    )
    provider_binding, observability_binding = (
        _stackctl._candidate_bindings_from_snapshot(
            snapshot,
            environment_name=environment,
            target_name=target,
        )
    )
    identities = _candidate_runtime_identities(
        manifest=manifest,
        provider_binding=provider_binding,
        observability_binding=observability_binding,
    )
    if (
        provider_binding.get("baselineId") != baseline
        or observability_binding.get("baselineId") != baseline
    ):
        raise ValueError("App content UAT candidate runtime binding drifted")
    startup = _stackctl.load_startup_attempt(target)
    if (
        not isinstance(startup, Mapping)
        or startup.get("status") != "running"
        or startup.get("failure") not in {None, ""}
        or startup.get("env") != environment
        or startup.get("target") != target
        or startup.get("workload") != "full"
    ):
        raise ValueError(
            "App content UAT requires the current running immutable receipt"
        )
    readiness, _readiness_path = _verified_app_content_readiness(preflight)
    release = manifest.get("release")
    release_candidate = (
        release.get("candidate") if isinstance(release, Mapping) else None
    )
    artifact = manifest.get("environmentArtifact")
    if (
        not isinstance(release_candidate, Mapping)
        or not isinstance(artifact, Mapping)
        or artifact.get("environment") != environment
        or artifact.get("target") != target
    ):
        raise ValueError("App content UAT immutable release identity is incomplete")

    baselines = {
        baseline,
        str(manifest.get("baselineId") or ""),
        identities["artifactBaseline"],
        str(preflight.get("packageBaseline") or ""),
        str(startup.get("candidateDigest") or ""),
    }
    if len(baselines) != 1 or any(
        _DIGEST_RE.fullmatch(value) is None for value in baselines
    ):
        raise ValueError(
            "App content UAT package baseline does not match active manifest/startup"
        )
    for field in (
        "releaseTrainId",
        "environmentArtifactDigest",
        "sourceCapsuleDigest",
        "sourceCapsuleWorkspaceStatusDigest",
        "packageDigest",
        "configurationDigest",
        "runtimeConfigDigest",
        "environmentRuntimeDigest",
        "providerRuntimeDigest",
        "observabilityLogSinkDigest",
    ):
        if _DIGEST_RE.fullmatch(identities[field]) is None:
            raise ValueError(f"App content UAT immutable {field} is invalid")

    manifest_expected = {
        "sourceRevision": identities["sourceRevision"],
        "packageDigest": identities["packageDigest"],
        "configurationDigest": identities["configurationDigest"],
        "runtimeConfigDigest": identities["runtimeConfigDigest"],
        "environmentRuntimeDigest": identities["environmentRuntimeDigest"],
    }
    if any(
        manifest.get(field) != value
        for field, value in manifest_expected.items()
    ):
        raise ValueError("App content UAT environmentArtifact identity drifted")
    if (
        identities["artifactProviderRuntimeDigest"]
        != identities["providerRuntimeDigest"]
    ):
        raise ValueError("App content UAT Provider runtime identity drifted")
    startup_expected = {
        "candidateDigest": baseline,
        "configurationDigest": identities["configurationDigest"],
        "providerRuntimeDigest": identities["providerRuntimeDigest"],
        "observabilityLogSinkDigest": identities["observabilityLogSinkDigest"],
    }
    if any(
        startup.get(field) != value for field, value in startup_expected.items()
    ):
        raise ValueError("App content UAT immutable startup identity drifted")
    expected_preflight = {
        "packageBaseline": baseline,
        "sourceRevision": identities["sourceRevision"],
        "configurationDigest": identities["configurationDigest"],
        "providerRuntimeDigest": identities["providerRuntimeDigest"],
        "releaseId": release_candidate.get("releaseId"),
        "manifestDigest": release_candidate.get("releaseDigest"),
        "readinessReceiptDigest": _stackctl._canonical_document_checksum(readiness),
        "appUatEnvelope": readiness.get("appUatEnvelope"),
        "appUatEnvelopeDigest": readiness.get("appUatEnvelopeDigest"),
    }
    for field, expected in expected_preflight.items():
        if preflight.get(field) != expected:
            raise ValueError(f"App content UAT preflight/candidate drifted: {field}")
    app_uat_plan = preflight.get("appUatPlan")
    if (
        not isinstance(app_uat_plan, Mapping)
        or preflight.get("appUatPlanDigest")
        != _stackctl._canonical_document_checksum(dict(app_uat_plan))
    ):
        raise ValueError("App content UAT plan digest drifted")
    _stackctl.assert_active_deployment_candidate_snapshot(dict(snapshot))

    startup_identity = {
        field: str(startup.get(field) or "")
        for field in _APP_CONTENT_IMMUTABLE_STARTUP_IDENTITY_FIELDS
    }
    return {
        "launchPolicy": "immutable_candidate",
        "nonPromotable": False,
        "environment": environment,
        "target": target,
        "packageBaseline": baseline,
        "candidateDigest": baseline,
        "releaseTrainId": identities["releaseTrainId"],
        "environmentArtifactDigest": identities["environmentArtifactDigest"],
        "sourceCapsuleDigest": identities["sourceCapsuleDigest"],
        "sourceCapsuleWorkspaceStatusDigest": identities[
            "sourceCapsuleWorkspaceStatusDigest"
        ],
        "sourceCapsuleManifestRef": str(
            candidate_root
            / _stackctl.PACKAGE_INPUT_CAPSULE_DIRECTORY
            / "manifest.json"
        ),
        "sourceRevision": identities["sourceRevision"],
        "packageDigest": identities["packageDigest"],
        "runtimeConfigDigest": identities["runtimeConfigDigest"],
        "environmentRuntimeDigest": identities["environmentRuntimeDigest"],
        "startupAttemptId": str(startup.get("attemptId") or ""),
        "composeProject": str(startup.get("composeProject") or ""),
        "runRoot": str(startup.get("runRoot") or ""),
        "startupIdentity": startup_identity,
        "contentBindingState": "bound",
        "retentionClass": "immutable_candidate",
        "releaseId": str(release_candidate.get("releaseId") or ""),
        "verifyRunId": str(readiness.get("verifyRunId") or ""),
        "manifestDigest": str(release_candidate.get("releaseDigest") or ""),
        "readinessPhase": str(readiness.get("readinessPhase") or ""),
        "readinessReceiptRef": str(preflight.get("readinessReceiptRef") or ""),
        "readinessReceiptDigest": str(
            preflight.get("readinessReceiptDigest") or ""
        ),
        "lifecycleExitRef": str(preflight.get("lifecycleExitRef") or ""),
        "appUatEnvelope": dict(preflight.get("appUatEnvelope") or {}),
        "appUatEnvelopeDigest": str(preflight.get("appUatEnvelopeDigest") or ""),
        "appUatPlan": dict(app_uat_plan),
        "appUatPlanDigest": str(preflight.get("appUatPlanDigest") or ""),
    }


def _app_content_test_live_runtime_binding(
    preflight: Mapping[str, Any],
) -> dict[str, Any]:
    """Compatibility surface for stackctl; test-live input is rejected."""
    return _app_content_immutable_runtime_binding(preflight)


def _app_content_immutable_actor_context(
    *,
    preflight: Mapping[str, Any],
    runtime_binding: Mapping[str, Any],
    readiness_path: Path,
    report_dir: Path,
) -> TestDataContext:
    """Bind typed UAT Actors to the real active candidate manifest."""
    import quwoquan_ops.cli.stackctl as _stackctl

    target = str(runtime_binding.get("target") or "").strip()
    environment = str(runtime_binding.get("environment") or "").strip()
    startup = runtime_binding.get("startupIdentity")
    if not isinstance(startup, Mapping):
        raise TypeError("App content UAT typed Actor startup identity is missing")
    readiness, canonical_readiness_path = _verified_app_content_readiness(preflight)
    if canonical_readiness_path.resolve() != readiness_path.resolve():
        raise ValueError("App content UAT typed Actor readiness path drifted")
    snapshot = _stackctl.active_deployment_candidate_snapshot(target)
    if not isinstance(snapshot, Mapping):
        raise TypeError("App content UAT typed Actor candidate is missing")
    baseline, _candidate_root, manifest = _stackctl._fixed_candidate_identity(
        snapshot,
        environment_name=environment,
        target_name=target,
    )
    artifact = manifest.get("environmentArtifact")
    source_capsule = (
        artifact.get("sourceCapsule") if isinstance(artifact, Mapping) else None
    )
    if not isinstance(artifact, Mapping) or not isinstance(source_capsule, Mapping):
        raise TypeError("App content UAT typed Actor candidate identity is incomplete")
    expected_runtime = {
        "candidateDigest": baseline,
        "packageBaseline": baseline,
        "releaseTrainId": artifact.get("releaseTrainId"),
        "environmentArtifactDigest": artifact.get("environmentArtifactDigest"),
        "sourceRevision": manifest.get("sourceRevision"),
        "sourceCapsuleDigest": source_capsule.get("digest"),
        "packageDigest": manifest.get("packageDigest"),
        "runtimeConfigDigest": manifest.get("runtimeConfigDigest"),
        "releaseId": readiness.get("releaseId"),
        "manifestDigest": readiness.get("manifestDigest"),
        "verifyRunId": readiness.get("verifyRunId"),
        "readinessPhase": readiness.get("readinessPhase"),
    }
    if any(
        runtime_binding.get(field) != value
        for field, value in expected_runtime.items()
    ):
        raise ValueError("App content UAT typed Actor candidate identity drifted")
    candidate = _stackctl.build_candidate_binding(
        environment=environment,
        target=target,
        manifest=manifest,
        readiness=readiness,
    )
    if candidate.baseline_id != baseline:
        raise ValueError("App content UAT typed Actor baseline identity drifted")
    context = _app_content_actor_context_from_candidate(
        preflight=preflight,
        runtime_binding=runtime_binding,
        candidate=candidate,
        report_dir=report_dir,
    )
    _stackctl.assert_active_deployment_candidate_snapshot(dict(snapshot))
    return context


def _app_content_test_live_actor_context(
    *,
    preflight: Mapping[str, Any],
    runtime_binding: Mapping[str, Any],
    readiness_path: Path,
    report_dir: Path,
) -> TestDataContext:
    """Compatibility surface for stackctl; always uses immutable identity."""
    return _app_content_immutable_actor_context(
        preflight=preflight,
        runtime_binding=runtime_binding,
        readiness_path=readiness_path,
        report_dir=report_dir,
    )


def _app_content_actor_context_from_candidate(
    *,
    preflight: Mapping[str, Any],
    runtime_binding: Mapping[str, Any],
    candidate: Any,
    report_dir: Path,
) -> TestDataContext:
    """Project verified Provider/login evidence into a typed Actor context."""
    import quwoquan_ops.cli.stackctl as _stackctl

    target = str(runtime_binding.get("target") or "").strip()
    environment = str(runtime_binding.get("environment") or "").strip()
    startup = runtime_binding.get("startupIdentity")
    if not isinstance(startup, Mapping):
        raise TypeError("App content UAT typed Actor startup identity is missing")
    provider = preflight.get("provider")
    login = preflight.get("loginJourney")
    if not isinstance(provider, Mapping) or not isinstance(login, Mapping):
        raise TypeError("App content UAT typed Actor Provider evidence is missing")
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
        or login.get("launchPolicy") != "immutable_candidate"
        or login.get("baselineId") != runtime_binding.get("candidateDigest")
        or login.get("sourceRevision") != runtime_binding.get("sourceRevision")
        or login.get("runtimeConfigDigest")
        != runtime_binding.get("runtimeConfigDigest")
        or login.get("configurationDigest")
        != startup.get("configurationDigest")
        or login.get("providerRuntimeDigest")
        != startup.get("providerRuntimeDigest")
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
        (topology_target.get("publicBases") or {}).get("api") or ""
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
    if (
        evidence.get("flutterProcessGroupStoppedBySigint") is not True
        or not isinstance(evidence.get("flutterRunExitCode"), int)
    ):
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
