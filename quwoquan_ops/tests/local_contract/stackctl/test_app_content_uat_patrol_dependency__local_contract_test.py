"""Patrol page suites consume the exact immutable launch dependency projection.

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from quwoquan_ops.cli.commands import app_preflight_uat_patrol_dependency as subject
from quwoquan_ops.cli.lib.package_reuse import (
    patrol_command_envelope as envelope_contract,
)
from quwoquan_ops.cli.lib.package_reuse.dependency_projection_contract import (
    environment_identity,
)


def _digest(marker: str) -> str:
    return "sha256:" + marker * 64


def _fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    components: set[str] | None = None,
    post_error: Exception | None = None,
) -> tuple[dict[str, object], dict[str, str], list[dict[str, Any]]]:
    root = tmp_path / "source-projection"
    root.mkdir()
    expectation_path = root / "state/dependency-projection-expectation.json"
    expectation_path.parent.mkdir()
    patrol_values = {
        "PUB_CACHE": str(root / "patrol-pub"),
        "GRADLE_USER_HOME": str(root / "gradle"),
        "HOME": str(root / "patrol-home"),
        "FLUTTER_SWIFT_PACKAGE_MANAGER": "false",
    }
    component_names = components or {
        "productionPub",
        "patrolPub",
        "androidGradle",
    }
    flutter_identity = {
        "executable": str(root / "toolchain/flutter/bin/flutter"),
        "flutterVersion": "3.47.0",
        "commandResolutionDigest": _digest("f"),
    }
    command_envelope = envelope_contract.patrol_command_envelope(
        flutter_identity=flutter_identity,
        path=str(root / "toolchain/flutter/bin") + ":/usr/bin:/bin",
        dependency_environment=patrol_values,
    )
    monkeypatch.setattr(
        envelope_contract,
        "resolved_flutter_identity",
        lambda _environment: dict(flutter_identity),
    )
    expectation = SimpleNamespace(
        evidence_path=expectation_path,
        evidence_digest=_digest("a"),
        manifest={
            "components": {name: {"kind": name} for name in component_names},
            "environments": {"patrol": environment_identity(patrol_values)},
            "patrolCommandEnvelope": command_envelope,
        },
    )
    monkeypatch.setattr(
        subject,
        "load_dependency_projection_cas_evidence",
        lambda **_kwargs: expectation,
    )
    calls: list[dict[str, Any]] = []

    def revalidate(**kwargs: Any) -> SimpleNamespace:
        calls.append(kwargs)
        if len(calls) == 2 and post_error is not None:
            raise post_error
        return SimpleNamespace(encoded_manifest=f"readback-{len(calls)}".encode())

    monkeypatch.setattr(subject, "revalidate_dependency_projection_cas", revalidate)
    return (
        {"sourceProjectionRoot": str(root)},
        {
            "dependencyProjectionExpectationRef": str(expectation_path),
            "dependencyProjectionExpectationDigest": _digest("a"),
        },
        calls,
    )


class _Stackctl:
    def __init__(
        self,
        *,
        drift_cwd: bool = False,
        result: object = "passed",
        error: Exception | None = None,
    ) -> None:
        self.command: dict[str, Any] = {}
        self.drift_cwd = drift_cwd
        self.result = result
        self.error = error

    def _run_profile_command(
        self,
        command: dict[str, Any],
        **_kwargs: object,
    ) -> str:
        self.command = command
        if self.drift_cwd:
            command["cwd"] = Path("/tmp/workspace-drift")
        if self.error is not None:
            raise self.error
        return self.result  # type: ignore[return-value]

    def _run_app_content_message_home_command(
        self,
        _command: dict[str, Any],
        **_kwargs: object,
    ) -> tuple[str, dict[str, Any]]:
        raise AssertionError("message runner is not selected")


def test_patrol_runs_from_candidate_root_with_exact_overlay_and_adjacent_cas(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    projection, launch_binding, calls = _fixture(tmp_path, monkeypatch)
    stackctl = _Stackctl()

    result, scope, evidence = subject.execute_patrol_with_dependency_cas(
        stackctl=stackctl,
        profile_command={
            "argv": [
                "python3",
                "quwoquan_ops/cli/smoke/run_environment_patrol_smoke.py",
            ],
            "cwd": tmp_path / "workspace",
            "env": {"TEST_AUTH_TOKEN": "secret"},
        },
        target_name="alpha-local",
        actor_context=object(),
        message_home=False,
        launch_projection=projection,
        launch_binding=launch_binding,
        platform="android",
    )

    root = Path(str(projection["sourceProjectionRoot"]))
    assert result == "passed"
    assert scope is None
    assert stackctl.command["cwd"] == root
    assert stackctl.command["env"]["PUB_CACHE"] == str(root / "patrol-pub")
    assert stackctl.command["env"]["TEST_AUTH_TOKEN"] == "secret"
    assert len(calls) == 2
    assert all(call["projection_root"] == root for call in calls)
    assert all(call["command_environment_owner"] == "patrol" for call in calls)
    assert all(
        call["command_environment"]["PUB_CACHE"] == str(root / "patrol-pub")
        for call in calls
    )
    encoded_evidence = json.dumps(evidence, sort_keys=True)
    assert "secret" not in encoded_evidence
    assert str(root) not in encoded_evidence
    assert evidence["components"] == [
        "androidGradle",
        "patrolPub",
        "productionPub",
    ]


def test_patrol_blocks_missing_required_host_component_before_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    projection, launch_binding, calls = _fixture(
        tmp_path,
        monkeypatch,
        components={"productionPub", "androidGradle"},
    )
    stackctl = _Stackctl()

    with pytest.raises(subject.PatrolDependencyFailure) as caught:
        subject.execute_patrol_with_dependency_cas(
            stackctl=stackctl,
            profile_command={"argv": ["python3", "runner.py"]},
            target_name="alpha-local",
            actor_context=None,
            message_home=False,
            launch_projection=projection,
            launch_binding=launch_binding,
            platform="android",
        )

    assert calls == []
    assert stackctl.command == {}
    assert caught.value.as_dict()["errorCode"] == (
        "APP.DEPENDENCY.projection_expectation_invalid"
    )
    assert caught.value.as_dict()["stage"] == "expectation"


def test_patrol_blocks_candidate_cwd_drift_after_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    projection, launch_binding, calls = _fixture(tmp_path, monkeypatch)

    with pytest.raises(subject.PatrolDependencyFailure) as caught:
        subject.execute_patrol_with_dependency_cas(
            stackctl=_Stackctl(drift_cwd=True),
            profile_command={"argv": ["python3", "runner.py"]},
            target_name="alpha-local",
            actor_context=None,
            message_home=False,
            launch_projection=projection,
            launch_binding=launch_binding,
            platform="android",
        )

    assert len(calls) == 2
    assert caught.value.as_dict()["stage"] == "post-command-cwd"


def test_patrol_records_cwd_drift_before_secondary_post_cas_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    projection, launch_binding, calls = _fixture(
        tmp_path,
        monkeypatch,
        post_error=ValueError("APP.DEPENDENCY.projection_cas_drift: hidden"),
    )

    with pytest.raises(subject.PatrolDependencyFailure) as caught:
        subject.execute_patrol_with_dependency_cas(
            stackctl=_Stackctl(drift_cwd=True),
            profile_command={"argv": ["python3", "runner.py"]},
            target_name="alpha-local",
            actor_context=None,
            message_home=False,
            launch_projection=projection,
            launch_binding=launch_binding,
            platform="android",
        )

    assert len(calls) == 2
    payload = caught.value.as_dict()
    assert payload["stage"] == "post-command-cwd"
    assert payload["secondaryFailures"][0]["stage"] == "post-command-cas"


def test_patrol_post_command_dependency_drift_is_gate_block(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    projection, launch_binding, calls = _fixture(
        tmp_path,
        monkeypatch,
        post_error=ValueError(
            "APP.DEPENDENCY.projection_cas_drift: patrolPub tree drifted"
        ),
    )

    with pytest.raises(subject.PatrolDependencyFailure) as caught:
        subject.execute_patrol_with_dependency_cas(
            stackctl=_Stackctl(),
            profile_command={"argv": ["python3", "runner.py"]},
            target_name="alpha-local",
            actor_context=None,
            message_home=False,
            launch_projection=projection,
            launch_binding=launch_binding,
            platform="android",
        )

    assert len(calls) == 2
    assert caught.value.as_dict()["errorCode"] == (
        "APP.DEPENDENCY.projection_cas_drift"
    )
    assert caught.value.as_dict()["stage"] == "post-command-cas"


@pytest.mark.parametrize("raw_root", ("", "relative/source-projection"))
def test_patrol_rejects_nonliteral_absolute_projection_root_before_readback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    raw_root: str,
) -> None:
    projection, launch_binding, calls = _fixture(tmp_path, monkeypatch)
    projection["sourceProjectionRoot"] = raw_root

    with pytest.raises(subject.PatrolDependencyFailure) as caught:
        subject.execute_patrol_with_dependency_cas(
            stackctl=_Stackctl(),
            profile_command={"argv": ["python3", "runner.py"]},
            target_name="alpha-local",
            actor_context=None,
            message_home=False,
            launch_projection=projection,
            launch_binding=launch_binding,
            platform="android",
        )

    assert calls == []
    assert caught.value.as_dict()["stage"] == "projection-root"


def test_patrol_rejects_projection_root_with_ancestor_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    projection, launch_binding, calls = _fixture(tmp_path, monkeypatch)
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(tmp_path, target_is_directory=True)
    projection["sourceProjectionRoot"] = str(linked_parent / "source-projection")

    with pytest.raises(subject.PatrolDependencyFailure) as caught:
        subject.execute_patrol_with_dependency_cas(
            stackctl=_Stackctl(),
            profile_command={"argv": ["python3", "runner.py"]},
            target_name="alpha-local",
            actor_context=None,
            message_home=False,
            launch_projection=projection,
            launch_binding=launch_binding,
            platform="android",
        )

    assert calls == []
    assert caught.value.as_dict()["stage"] == "projection-root"


@pytest.mark.parametrize(
    "stackctl",
    (
        _Stackctl(
            error=ValueError(
                "APP.DEPENDENCY.projection_execution_failed: token=very-secret "
                "path=/private/command.log"
            )
        ),
        _Stackctl(
            result=subprocess.CompletedProcess(
                args=["python3", "/private/runner.py"],
                returncode=7,
                stdout="token=very-secret",
                stderr="failed at /private/command.log",
            )
        ),
    ),
)
def test_command_failure_stays_primary_when_post_cas_also_fails_without_leakage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stackctl: _Stackctl,
) -> None:
    projection, launch_binding, calls = _fixture(
        tmp_path,
        monkeypatch,
        post_error=ValueError(
            "APP.DEPENDENCY.projection_cas_drift: token=post-secret "
            "path=/private/post-cas.json"
        ),
    )

    with pytest.raises(subject.PatrolDependencyFailure) as caught:
        subject.execute_patrol_with_dependency_cas(
            stackctl=stackctl,
            profile_command={"argv": ["python3", "runner.py"]},
            target_name="alpha-local",
            actor_context=None,
            message_home=False,
            launch_projection=projection,
            launch_binding=launch_binding,
            platform="android",
        )

    assert len(calls) == 2
    payload = caught.value.as_dict()
    assert payload["errorCode"] == "APP.DEPENDENCY.projection_execution_failed"
    assert payload["stage"] == "command"
    assert payload["secondaryFailures"][0]["errorCode"] == (
        "APP.DEPENDENCY.projection_cas_drift"
    )
    encoded = json.dumps(payload, sort_keys=True) + str(caught.value)
    for forbidden in (
        "very-secret",
        "post-secret",
        "/private/runner.py",
        "/private/command.log",
        "/private/post-cas.json",
    ):
        assert forbidden not in encoded


def test_persistence_projection_contains_only_safe_failure_detail() -> None:
    secret = "token=caller-secret path=/private/caller-command.log"
    failure = subject.patrol_dependency_failure(
        RuntimeError(secret),
        stage="command",
    )
    error_code = failure.error_code
    receipt_detail = failure.as_dict()
    issue_detail = str(failure)

    assert error_code == "APP.DEPENDENCY.projection_execution_failed"
    assert receipt_detail["errorCode"] == error_code
    assert receipt_detail["stage"] == "command"
    assert receipt_detail["causeType"] == "RuntimeError"
    assert receipt_detail["diagnosticDigest"].startswith("sha256:")
    persisted = json.dumps(receipt_detail, sort_keys=True) + issue_detail
    assert "caller-secret" not in persisted
    assert "/private/caller-command.log" not in persisted


def test_ambient_proxy_and_foreign_flutter_selection_are_ignored(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    projection, launch_binding, calls = _fixture(tmp_path, monkeypatch)
    stackctl = _Stackctl()
    for key in envelope_contract.PROXY_ENVIRONMENT_KEYS:
        monkeypatch.setenv(key, f"http://ambient-{key}.invalid")
    monkeypatch.setenv("PATH", "/foreign/flutter/bin:/usr/bin")
    monkeypatch.setenv("QWQ_REAL_FLUTTER", "/foreign/flutter/bin/flutter")
    monkeypatch.setenv("JAVA_TOOL_OPTIONS", "-javaagent:/ambient/agent.jar")
    monkeypatch.setenv("GRADLE_OPTS", "-Dambient=true")
    monkeypatch.setenv("PUB_HOSTED_URL", "https://ambient-pub.invalid")
    monkeypatch.setenv(
        "FLUTTER_STORAGE_BASE_URL",
        "https://ambient-flutter.invalid",
    )
    monkeypatch.setenv("HOME", "/ambient/home")
    monkeypatch.setenv("TEST_AUTH_TOKEN", "ambient-auth-token")
    monkeypatch.setenv("QWQ_TEST_DATA_ACCESS_TOKEN", "ambient-actor-token")
    monkeypatch.setenv(
        "QWQ_EXTERNAL_AUT_CANONICAL_BINDING_B64",
        "ambient-aut-binding",
    )

    _result, _scope, evidence = subject.execute_patrol_with_dependency_cas(
        stackctl=stackctl,
        profile_command={"argv": ["python3", "runner.py"]},
        target_name="alpha-local",
        actor_context=None,
        message_home=False,
        launch_projection=projection,
        launch_binding=launch_binding,
        platform="android",
    )

    environment = stackctl.command["env"]
    assert all(
        key not in environment for key in envelope_contract.PROXY_ENVIRONMENT_KEYS
    )
    assert environment["PATH"].startswith(
        str(Path(str(projection["sourceProjectionRoot"])) / "toolchain/flutter/bin")
    )
    assert environment["QWQ_REAL_FLUTTER"].endswith("/toolchain/flutter/bin/flutter")
    assert environment["HOME"].endswith("/source-projection/patrol-home")
    assert environment["TEST_AUTH_TOKEN"] == ""
    assert environment["QWQ_TEST_DATA_ACCESS_TOKEN"] == ""
    assert environment["QWQ_EXTERNAL_AUT_CANONICAL_BINDING_B64"] == ""
    assert all(
        key not in environment
        for key in (
            "JAVA_TOOL_OPTIONS",
            "GRADLE_OPTS",
            "PUB_HOSTED_URL",
            "FLUTTER_STORAGE_BASE_URL",
        )
    )
    assert len(calls) == 2
    assert evidence["patrolCommandEnvelopeDigest"].startswith("sha256:")
    assert "/toolchain/flutter" not in json.dumps(evidence, sort_keys=True)


@pytest.mark.parametrize(
    ("key", "value"),
    (
        ("HTTP_PROXY", "http://explicit.invalid"),
        ("http_proxy", "http://explicit.invalid"),
        ("PATH", "/foreign/flutter/bin"),
        ("QWQ_REAL_FLUTTER", "/foreign/flutter/bin/flutter"),
        ("PUB_CACHE", "/foreign/pub-cache"),
        ("JAVA_TOOL_OPTIONS", "-javaagent:/foreign/agent.jar"),
        ("GRADLE_OPTS", "-Dforeign=true"),
        ("PUB_HOSTED_URL", "https://foreign-pub.invalid"),
        ("FLUTTER_STORAGE_BASE_URL", "https://foreign-flutter.invalid"),
    ),
)
def test_explicit_command_toolchain_or_proxy_conflict_fails_before_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    key: str,
    value: str,
) -> None:
    projection, launch_binding, calls = _fixture(tmp_path, monkeypatch)
    stackctl = _Stackctl()

    with pytest.raises(subject.PatrolDependencyFailure) as caught:
        subject.execute_patrol_with_dependency_cas(
            stackctl=stackctl,
            profile_command={
                "argv": ["python3", "runner.py"],
                "env": {key: value},
            },
            target_name="alpha-local",
            actor_context=None,
            message_home=False,
            launch_projection=projection,
            launch_binding=launch_binding,
            platform="android",
        )

    assert caught.value.as_dict()["stage"] == "expectation"
    assert calls == []
    assert stackctl.command == {}


@pytest.mark.parametrize(
    "actual_updates",
    (
        {"flutterVersion": "3.48.0"},
        {"commandResolutionDigest": _digest("e")},
    ),
    ids=("version", "resolution-digest"),
)
def test_actual_flutter_version_or_resolution_drift_fails_before_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    actual_updates: dict[str, str],
) -> None:
    projection, launch_binding, calls = _fixture(tmp_path, monkeypatch)
    root = Path(str(projection["sourceProjectionRoot"]))
    actual = {
        "executable": str(root / "toolchain/flutter/bin/flutter"),
        "flutterVersion": "3.47.0",
        "commandResolutionDigest": _digest("f"),
        **actual_updates,
    }
    monkeypatch.setattr(
        envelope_contract,
        "resolved_flutter_identity",
        lambda _environment: dict(actual),
    )

    with pytest.raises(subject.PatrolDependencyFailure) as caught:
        subject.execute_patrol_with_dependency_cas(
            stackctl=_Stackctl(),
            profile_command={"argv": ["python3", "runner.py"]},
            target_name="alpha-local",
            actor_context=None,
            message_home=False,
            launch_projection=projection,
            launch_binding=launch_binding,
            platform="android",
        )

    assert caught.value.as_dict()["stage"] == "expectation"
    assert calls == []


def test_ios_patrol_uses_the_same_sealed_command_envelope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    projection, launch_binding, calls = _fixture(
        tmp_path,
        monkeypatch,
        components={
            "productionPub",
            "patrolPub",
            "productionIosPods",
            "patrolIosPods",
        },
    )
    stackctl = _Stackctl()

    result, scope, evidence = subject.execute_patrol_with_dependency_cas(
        stackctl=stackctl,
        profile_command={"argv": ["python3", "runner.py"]},
        target_name="alpha-local",
        actor_context=None,
        message_home=False,
        launch_projection=projection,
        launch_binding=launch_binding,
        platform="ios-simulator",
    )

    assert result == "passed"
    assert scope is None
    assert len(calls) == 2
    assert stackctl.command["env"]["QWQ_PATROL_REAL_FLUTTER"].endswith(
        "/toolchain/flutter/bin/flutter"
    )
    assert evidence["components"] == [
        "patrolIosPods",
        "patrolPub",
        "productionIosPods",
        "productionPub",
    ]
