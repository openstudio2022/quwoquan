"""Package builds bind one fresh dependency expectation and post-command readback."""

# spec_ref: specs/feature-tree/runtime/runtime-config/design.md#dec-003

from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from quwoquan_ops.cli.commands import package_app_artifact as package
from quwoquan_ops.cli.commands.package_app_artifact_identity import (
    AppArtifactBuildError,
)

_EXPECTATION_DIGEST = "sha256:" + "1" * 64
_PREBUILD_DIGEST = "sha256:" + "2" * 64
_POSTBUILD_DIGEST = "sha256:" + "3" * 64


def _context(tmp_path: Path) -> tuple[Any, ...]:
    projection_root = tmp_path / "projection"
    source_manifest = tmp_path / "input-capsule/manifest.json"
    dependency_projection = object()
    ios_results = (("production", object()),)
    attempt_dir = tmp_path / "attempt"
    attempt_dir.mkdir()
    environment = {"PUB_CACHE": str(projection_root / "pub-cache")}
    return (
        projection_root,
        source_manifest,
        dependency_projection,
        ios_results,
        attempt_dir,
        projection_root / "quwoquan_app",
        environment,
        attempt_dir / "compile.log",
    )


def _install_stable_cas(
    monkeypatch: pytest.MonkeyPatch,
    *,
    context: tuple[Any, ...],
    events: list[str],
) -> dict[str, dict[str, Any]]:
    attempt_dir = context[4]
    expectation = SimpleNamespace(
        evidence_path=attempt_dir / "dependency-projection-expectation.json",
        evidence_digest=_EXPECTATION_DIGEST,
    )
    readback = SimpleNamespace(manifest={"schema": "readback"})
    calls: dict[str, dict[str, Any]] = {}

    def prepare(**kwargs: Any) -> Any:
        events.append("prepare")
        calls["prepare"] = kwargs
        return expectation

    def revalidate(**kwargs: Any) -> Any:
        events.append("revalidate")
        calls["revalidate"] = kwargs
        return readback

    def write(**kwargs: Any) -> Any:
        events.append("write")
        calls["write"] = kwargs
        digest = (
            _PREBUILD_DIGEST
            if "prebuild" in str(kwargs["evidence_path"])
            else _POSTBUILD_DIGEST
        )
        return SimpleNamespace(
            evidence_path=kwargs["evidence_path"], evidence_digest=digest
        )

    def load(**kwargs: Any) -> Any:
        events.append("load")
        calls["load"] = kwargs
        return SimpleNamespace(
            evidence_path=kwargs["evidence_path"],
            evidence_digest=kwargs["expected_digest"],
        )

    monkeypatch.setattr(
        package._dependency_cas,
        "prepare_dependency_projection_cas_evidence",
        prepare,
    )
    monkeypatch.setattr(
        package._dependency_cas,
        "revalidate_dependency_projection_cas",
        revalidate,
    )
    monkeypatch.setattr(
        package._dependency_cas,
        "write_dependency_projection_cas_readback",
        write,
    )
    monkeypatch.setattr(
        package._dependency_cas,
        "load_dependency_projection_cas_readback",
        load,
    )
    return calls


def test_build_writes_expectation_before_command_then_objectless_readback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    context = _context(tmp_path)
    calls = _install_stable_cas(monkeypatch, context=context, events=events)

    def run(*_args: Any, **_kwargs: Any) -> None:
        events.append("build")

    monkeypatch.setattr(package, "_run", run)
    evidence = package._run_build_with_dependency_cas(
        ["flutter", "build", "apk"], context=context
    )

    assert events == [
        "prepare",
        "revalidate",
        "write",
        "load",
        "build",
        "revalidate",
        "write",
        "load",
    ]
    assert calls["prepare"]["ios_install_results"] is context[3]
    assert calls["revalidate"] == {
        "projection_root": context[0],
        "evidence_path": context[4] / "dependency-projection-expectation.json",
        "expected_digest": _EXPECTATION_DIGEST,
        "command_environment_owner": "production",
        "command_environment": context[6],
    }
    assert calls["load"]["expected_expectation_digest"] == _EXPECTATION_DIGEST
    assert evidence == {
        "dependencyProjectionExpectationRef": str(
            context[4] / "dependency-projection-expectation.json"
        ),
        "dependencyProjectionExpectationDigest": _EXPECTATION_DIGEST,
        "dependencyProjectionPrebuildReadbackRef": str(
            context[4] / "dependency-projection-prebuild-readback.json"
        ),
        "dependencyProjectionPrebuildReadbackDigest": _PREBUILD_DIGEST,
        "dependencyProjectionPostbuildReadbackRef": str(
            context[4] / "dependency-projection-postbuild-readback.json"
        ),
        "dependencyProjectionPostbuildReadbackDigest": _POSTBUILD_DIGEST,
    }


def test_failed_build_still_persists_fresh_readback_and_keeps_first_blocker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    context = _context(tmp_path)
    _install_stable_cas(monkeypatch, context=context, events=events)

    def fail(*_args: Any, **_kwargs: Any) -> None:
        events.append("build")
        raise AppArtifactBuildError("APP.PACKAGE.compile_failed: compiler stopped")

    monkeypatch.setattr(package, "_run", fail)
    with pytest.raises(AppArtifactBuildError, match="^APP.PACKAGE.compile_failed"):
        package._run_build_with_dependency_cas(
            ["flutter", "build", "ios"], context=context
        )
    assert events == [
        "prepare",
        "revalidate",
        "write",
        "load",
        "build",
        "revalidate",
        "write",
        "load",
    ]


def test_successful_build_fails_closed_when_dependency_domain_drifts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    context = _context(tmp_path)
    calls = _install_stable_cas(monkeypatch, context=context, events=events)
    monkeypatch.setattr(
        package, "_run", lambda *_args, **_kwargs: events.append("build")
    )

    revalidations = 0

    def drift(**kwargs: Any) -> Any:
        nonlocal revalidations
        revalidations += 1
        calls["revalidate"] = kwargs
        events.append("revalidate")
        if revalidations == 2:
            raise ValueError("APP.DEPENDENCY.projection_cas_drift: Pub bytes changed")
        return SimpleNamespace(manifest={"schema": "readback"})

    monkeypatch.setattr(
        package._dependency_cas, "revalidate_dependency_projection_cas", drift
    )
    with pytest.raises(ValueError, match="APP.DEPENDENCY.projection_cas_drift"):
        package._run_build_with_dependency_cas(
            ["flutter", "build", "web"], context=context
        )
    assert events == [
        "prepare",
        "revalidate",
        "write",
        "load",
        "build",
        "revalidate",
    ]


def test_compile_blocker_precedes_post_command_cas_blocker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    context = _context(tmp_path)
    _install_stable_cas(monkeypatch, context=context, events=events)

    def fail(*_args: Any, **_kwargs: Any) -> None:
        events.append("build")
        raise AppArtifactBuildError("APP.PACKAGE.compile_failed: compiler stopped")

    revalidations = 0

    def drift(**_kwargs: Any) -> Any:
        nonlocal revalidations
        revalidations += 1
        events.append("revalidate")
        if revalidations == 2:
            raise ValueError(
                "APP.DEPENDENCY.projection_cas_drift: Gradle bytes changed"
            )
        return SimpleNamespace(manifest={"schema": "readback"})

    monkeypatch.setattr(package, "_run", fail)
    monkeypatch.setattr(
        package._dependency_cas, "revalidate_dependency_projection_cas", drift
    )
    with pytest.raises(AppArtifactBuildError) as raised:
        package._run_build_with_dependency_cas(
            ["flutter", "build", "apk"], context=context
        )
    detail = str(raised.value)
    assert detail.startswith("APP.PACKAGE.compile_failed")
    assert detail.index("APP.PACKAGE.compile_failed") < detail.index(
        "APP.DEPENDENCY.projection_cas_drift"
    )
    assert events == [
        "prepare",
        "revalidate",
        "write",
        "load",
        "build",
        "revalidate",
    ]


def test_package_cleans_projection_before_historical_evidence_validation() -> None:
    source = inspect.getsource(package._build_from_capsule)
    cleanup = source.index("temporary_workspace.cleanup()")
    historical_validation = source.index(
        "_validate_persisted_dependency_evidence(", cleanup
    )
    completed_return = source.index("return build", historical_validation)

    assert cleanup < historical_validation < completed_return
    validator = inspect.getsource(package._validate_persisted_dependency_evidence)
    assert "load_historical_dependency_projection_cas_evidence(" in validator
    assert validator.count("load_dependency_projection_cas_readback(") == 2
    assert "deleted_projection_root.exists()" in validator
