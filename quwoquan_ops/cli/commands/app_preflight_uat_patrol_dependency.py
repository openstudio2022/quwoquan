"""Bind every strict page UAT command to the launch dependency projection."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.commands.app_preflight_uat_projection_path import (
    canonical_source_projection_root,
)
from quwoquan_ops.cli.lib.package_reuse.dependency_bundle_projection_verify import (
    load_dependency_projection_cas_evidence,
    revalidate_dependency_projection_cas,
)
from quwoquan_ops.cli.lib.package_reuse.patrol_command_envelope import (
    patrol_command_envelope_digest,
    rebuild_patrol_command_environment,
)

_EXPECTATION_BLOCKER = "APP.DEPENDENCY.projection_expectation_invalid"
_CAS_BLOCKER = "APP.DEPENDENCY.projection_cas_drift"
_COMMAND_BLOCKER = "APP.DEPENDENCY.projection_execution_failed"
_ERROR_CODES = frozenset({_EXPECTATION_BLOCKER, _CAS_BLOCKER, _COMMAND_BLOCKER})
_STAGES = frozenset(
    {
        "projection-root",
        "expectation",
        "pre-command-cas",
        "command",
        "post-command-cwd",
        "post-command-cas",
        "readback",
    }
)
_CAUSE_TYPES = frozenset(
    {
        "CompletedProcess",
        "Exception",
        "OSError",
        "RuntimeError",
        "TypeError",
        "ValueError",
    }
)
_REQUIRED_COMPONENTS = {
    "android": frozenset({"productionPub", "patrolPub", "androidGradle"}),
    "ios-simulator": frozenset(
        {
            "productionPub",
            "patrolPub",
            "productionIosPods",
            "patrolIosPods",
        }
    ),
}


def _diagnostic_digest(*values: object) -> str:
    digest = hashlib.sha256()
    for value in values:
        encoded = str(value).encode("utf-8", errors="backslashreplace")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return "sha256:" + digest.hexdigest()


def _cause_type(error: BaseException) -> str:
    for error_type, label in (
        (OSError, "OSError"),
        (RuntimeError, "RuntimeError"),
        (TypeError, "TypeError"),
        (ValueError, "ValueError"),
    ):
        if isinstance(error, error_type):
            return label
    return "Exception"


def _error_code(error: BaseException, fallback: str) -> str:
    if isinstance(error, PatrolDependencyFailure):
        return error.error_code
    candidate = str(error).partition(":")[0]
    return candidate if candidate in _ERROR_CODES else fallback


@dataclass(frozen=True)
class PatrolDependencyFailureDetail:
    error_code: str
    stage: str
    cause_type: str
    diagnostic_digest: str

    def __post_init__(self) -> None:
        if (
            self.error_code not in _ERROR_CODES
            or self.stage not in _STAGES
            or self.cause_type not in _CAUSE_TYPES
            or len(self.diagnostic_digest) != 71
            or not self.diagnostic_digest.startswith("sha256:")
            or any(
                character not in "0123456789abcdef"
                for character in self.diagnostic_digest[7:]
            )
        ):
            raise ValueError("Patrol dependency failure detail is invalid")

    def as_dict(self) -> dict[str, str]:
        return {
            "errorCode": self.error_code,
            "stage": self.stage,
            "causeType": self.cause_type,
            "diagnosticDigest": self.diagnostic_digest,
        }


class PatrolDependencyFailure(ValueError):
    """A persistence-safe typed failure with an ordered secondary failure set."""

    def __init__(
        self,
        primary: PatrolDependencyFailureDetail,
        secondary: Sequence[PatrolDependencyFailureDetail] = (),
    ) -> None:
        self.primary = primary
        self.secondary = tuple(secondary)
        super().__init__(
            json.dumps(
                self.as_dict(),
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            )
        )

    @property
    def error_code(self) -> str:
        return self.primary.error_code

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = self.primary.as_dict()
        if self.secondary:
            payload["secondaryFailures"] = [item.as_dict() for item in self.secondary]
        return payload

    def with_secondary(
        self,
        secondary: Sequence[PatrolDependencyFailureDetail],
    ) -> PatrolDependencyFailure:
        return PatrolDependencyFailure(
            self.primary,
            (*self.secondary, *secondary),
        )


def _failure(
    *,
    error_code: str,
    stage: str,
    cause_type: str,
    diagnostics: Sequence[object],
) -> PatrolDependencyFailure:
    return PatrolDependencyFailure(
        PatrolDependencyFailureDetail(
            error_code=error_code,
            stage=stage,
            cause_type=cause_type,
            diagnostic_digest=_diagnostic_digest(*diagnostics),
        )
    )


def patrol_dependency_failure(
    error: BaseException,
    *,
    stage: str,
    fallback_error_code: str = _COMMAND_BLOCKER,
) -> PatrolDependencyFailure:
    """Collapse an arbitrary exception into the closed persistence-safe contract."""

    if isinstance(error, PatrolDependencyFailure) and error.primary.stage == stage:
        return error
    return _failure(
        error_code=_error_code(error, fallback_error_code),
        stage=stage,
        cause_type=_cause_type(error),
        diagnostics=(type(error).__name__, str(error)),
    )


def _semantic_failure(*, stage: str, marker: str) -> PatrolDependencyFailure:
    return _failure(
        error_code=_EXPECTATION_BLOCKER,
        stage=stage,
        cause_type="ValueError",
        diagnostics=(marker,),
    )


def _readback_digest(readback: Any) -> str:
    encoded = getattr(readback, "encoded_manifest", None)
    if not isinstance(encoded, bytes):
        raise _semantic_failure(stage="readback", marker="invalid-readback-bytes")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _projection_root(launch_projection: Mapping[str, Any]) -> Path:
    try:
        return canonical_source_projection_root(
            launch_projection.get("sourceProjectionRoot")
        )
    except (OSError, TypeError, ValueError) as error:
        raise patrol_dependency_failure(
            error,
            stage="projection-root",
            fallback_error_code=_EXPECTATION_BLOCKER,
        ) from None


def _validated_patrol_environment(
    *,
    launch_projection: Mapping[str, Any],
    launch_binding: Mapping[str, Any],
    platform: str,
) -> tuple[
    Path,
    Path,
    str,
    dict[str, str],
    str,
    tuple[str, ...],
    Mapping[str, Any],
    str,
]:
    root = _projection_root(launch_projection)
    expectation_ref = launch_binding.get("dependencyProjectionExpectationRef")
    expectation_digest = launch_binding.get("dependencyProjectionExpectationDigest")
    if (
        not isinstance(expectation_ref, str)
        or not expectation_ref
        or not isinstance(expectation_digest, str)
        or not expectation_digest
    ):
        raise _semantic_failure(stage="expectation", marker="missing-binding")
    try:
        expectation = load_dependency_projection_cas_evidence(
            projection_root=root,
            evidence_path=Path(expectation_ref),
            expected_digest=expectation_digest,
        )
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise patrol_dependency_failure(
            error,
            stage="expectation",
            fallback_error_code=_EXPECTATION_BLOCKER,
        ) from None
    components = expectation.manifest.get("components")
    required = _REQUIRED_COMPONENTS.get(platform)
    if (
        required is None
        or not isinstance(components, Mapping)
        or set(components) != set(required)
    ):
        raise _semantic_failure(stage="expectation", marker="component-set")
    environments = expectation.manifest.get("environments")
    patrol = environments.get("patrol") if isinstance(environments, Mapping) else None
    values = patrol.get("values") if isinstance(patrol, Mapping) else None
    patrol_digest = str(patrol.get("digest") or "") if patrol is not None else ""
    if (
        not isinstance(values, Mapping)
        or not values
        or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in values.items()
        )
        or not patrol_digest
    ):
        raise _semantic_failure(stage="expectation", marker="environment")
    command_envelope = expectation.manifest.get("patrolCommandEnvelope")
    try:
        command_envelope_digest = patrol_command_envelope_digest(command_envelope)
    except (TypeError, ValueError):
        raise _semantic_failure(
            stage="expectation",
            marker="command-envelope",
        ) from None
    return (
        root,
        expectation.evidence_path,
        expectation.evidence_digest,
        dict(values),
        patrol_digest,
        tuple(sorted(str(name) for name in components)),
        command_envelope,
        command_envelope_digest,
    )


def _assert_candidate_cwd(
    command: Mapping[str, Any],
    expected: Path,
    *,
    stage: str,
) -> None:
    try:
        raw = command.get("cwd")
        actual = canonical_source_projection_root(
            str(raw) if isinstance(raw, (str, Path)) else raw
        )
    except (OSError, TypeError, ValueError) as error:
        raise patrol_dependency_failure(
            error,
            stage=stage,
            fallback_error_code=_EXPECTATION_BLOCKER,
        ) from None
    if actual != expected:
        raise _failure(
            error_code=_EXPECTATION_BLOCKER,
            stage=stage,
            cause_type="ValueError",
            diagnostics=(actual, expected),
        )


def _post_failure_details(
    error: BaseException,
    *,
    stage: str,
) -> tuple[PatrolDependencyFailureDetail, ...]:
    safe = patrol_dependency_failure(
        error,
        stage=stage,
        fallback_error_code=(
            _CAS_BLOCKER if stage == "post-command-cas" else _EXPECTATION_BLOCKER
        ),
    )
    return (safe.primary, *safe.secondary)


def execute_patrol_with_dependency_cas(
    *,
    stackctl: Any,
    profile_command: Mapping[str, Any],
    target_name: str,
    actor_context: Any,
    message_home: bool,
    launch_projection: Mapping[str, Any],
    launch_binding: Mapping[str, Any],
    platform: str,
) -> tuple[Any, dict[str, Any] | None, dict[str, Any]]:
    """Run one Patrol command from candidate bytes with adjacent CAS readbacks."""

    (
        root,
        expectation_path,
        expectation_digest,
        patrol_environment,
        patrol_environment_digest,
        components,
        patrol_command_envelope,
        patrol_command_envelope_digest_value,
    ) = _validated_patrol_environment(
        launch_projection=launch_projection,
        launch_binding=launch_binding,
        platform=platform,
    )
    try:
        effective_environment = rebuild_patrol_command_environment(
            envelope=patrol_command_envelope,
            ambient_environment=os.environ,
            dependency_environment=patrol_environment,
            command_environment=dict(profile_command.get("env") or {}),
        )
    except (OSError, TypeError, ValueError) as error:
        raise patrol_dependency_failure(
            error,
            stage="expectation",
            fallback_error_code=_EXPECTATION_BLOCKER,
        ) from None
    command = {
        **dict(profile_command),
        "cwd": root,
        "env": effective_environment,
    }
    _assert_candidate_cwd(command, root, stage="projection-root")
    try:
        precommand = revalidate_dependency_projection_cas(
            projection_root=root,
            evidence_path=expectation_path,
            expected_digest=expectation_digest,
            command_environment_owner="patrol",
            command_environment=effective_environment,
        )
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise patrol_dependency_failure(
            error,
            stage="pre-command-cas",
            fallback_error_code=_CAS_BLOCKER,
        ) from None

    result: Any = None
    test_data_scope: dict[str, Any] | None = None
    command_failure: PatrolDependencyFailure | None = None
    post_failures: list[PatrolDependencyFailureDetail] = []
    postcommand: Any = None
    command_executed = False
    try:
        command_executed = True
        if message_home:
            result, test_data_scope = stackctl._run_app_content_message_home_command(
                command,
                target_name=target_name,
                actor_context=actor_context,
            )
        else:
            result = stackctl._run_profile_command(
                command,
                target_name=target_name,
                actor_context=actor_context,
            )
        if isinstance(result, subprocess.CompletedProcess) and result.returncode != 0:
            command_failure = _failure(
                error_code=_COMMAND_BLOCKER,
                stage="command",
                cause_type="CompletedProcess",
                diagnostics=(result.returncode, result.stdout, result.stderr),
            )
    except Exception as error:  # noqa: BLE001 - closed safe projection below
        command_failure = patrol_dependency_failure(error, stage="command")
    finally:
        if command_executed:
            try:
                _assert_candidate_cwd(command, root, stage="post-command-cwd")
            except Exception as error:  # noqa: BLE001 - closed safe projection below
                post_failures.extend(
                    _post_failure_details(error, stage="post-command-cwd")
                )
            try:
                postcommand = revalidate_dependency_projection_cas(
                    projection_root=root,
                    evidence_path=expectation_path,
                    expected_digest=expectation_digest,
                    command_environment_owner="patrol",
                    command_environment=effective_environment,
                )
            except Exception as error:  # noqa: BLE001 - closed safe projection below
                post_failures.extend(
                    _post_failure_details(error, stage="post-command-cas")
                )

    if command_failure is not None:
        raise command_failure.with_secondary(post_failures) from None
    if post_failures:
        raise PatrolDependencyFailure(post_failures[0], post_failures[1:]) from None

    evidence = {
        "schema": "quwoquan_ops.app_content_uat_patrol_dependency_readback.v1",
        "expectationDigest": expectation_digest,
        "patrolEnvironmentDigest": patrol_environment_digest,
        "patrolCommandEnvelopeDigest": patrol_command_envelope_digest_value,
        "components": list(components),
        "preCommandReadbackDigest": _readback_digest(precommand),
        "postCommandReadbackDigest": _readback_digest(postcommand),
    }
    return result, test_data_scope, evidence
