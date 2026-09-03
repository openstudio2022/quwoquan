"""Process-result and live-source seal contracts for app-dependency-sync."""

# spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-004

from __future__ import annotations

import argparse
import json
import stat
from collections.abc import Mapping
from pathlib import Path

import pytest

from quwoquan_ops.cli.commands import app_dependency_sync as sync
from quwoquan_ops.tests.support.app_dependency_sync_test_support import (
    component_builder as _component_builder,
)
from quwoquan_ops.tests.support.app_dependency_sync_test_support import (
    stub_sync as _stub_sync,
)

def _process_result(output: Path, result: Mapping[str, object]) -> tuple[Path, dict[str, object]]:
    attempt_detail = next(
        str(item) for item in result["details"] if str(item).startswith("attemptId=")
    )
    attempt_id = attempt_detail.split("=", 1)[1]
    path = output / f"env/repo/local/app-dependency-sync/process/{attempt_id}/result.json"
    return path, json.loads(path.read_text(encoding="utf-8"))


def test_failure_process_result_is_private_closed_redacted_and_relative(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "output"
    _stub_sync(monkeypatch, output)
    secret = "fixture-secret-value"

    def fail(context: sync.DependencyComponentBuildContext) -> Mapping[str, Path]:
        context.progress.begin("android-resolution-replay")
        sync._builder._write_private_log(
            context.process_root / "android-gradle-failed.log",
            f"authorization=Bearer {secret}\nhttps://user:{secret}@example.invalid/repo",
            sensitive_values=(secret,),
        )
        raise ValueError(
            f"APP.DEPENDENCY.android_sync_failed: password={secret}"
        )

    result = sync.command_app_dependency_sync(
        argparse.Namespace(), component_builder=fail
    )

    path, process_result = _process_result(output, result)
    assert result["exitCode"] == 2
    assert set(process_result) == {
        "schema",
        "attemptId",
        "exitCode",
        "summary",
        "details",
        "failedPhase",
        "cause",
        "logRefs",
    }
    assert process_result["schema"] == sync._PROCESS_RESULT_SCHEMA
    assert process_result["exitCode"] == 2
    assert process_result["failedPhase"] == "android-resolution-replay"
    assert process_result["cause"] == "value_error"
    assert process_result["logRefs"] == [
        f"env/repo/local/app-dependency-sync/process/{process_result['attemptId']}/android-gradle-failed.log"
    ]
    assert all(not Path(ref).is_absolute() and ".." not in Path(ref).parts for ref in process_result["logRefs"])
    rendered = json.dumps(process_result, ensure_ascii=False)
    log = (path.parent / "android-gradle-failed.log").read_text(encoding="utf-8")
    assert secret not in rendered and secret not in log
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert path.stat().st_nlink == 1
    assert not (output / f"env/repo/runs/app-dependency-sync/{process_result['attemptId']}").exists()


def test_process_result_atomic_writer_rejects_linked_parent(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir(mode=0o700)
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)

    with pytest.raises((OSError, ValueError)):
        sync._atomic_process_result(
            alias / "result.json",
            {
                "schema": sync._PROCESS_RESULT_SCHEMA,
                "attemptId": "a" * 32,
                "exitCode": 2,
                "summary": "blocked",
                "details": [],
                "failedPhase": "initialization",
                "cause": "io_error",
                "logRefs": [],
            },
        )
    assert not (real / "result.json").exists()


def test_success_process_result_never_claims_publication_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "output"
    _stub_sync(monkeypatch, output)

    result = sync.command_app_dependency_sync(
        argparse.Namespace(), component_builder=_component_builder()
    )

    path, process_result = _process_result(output, result)
    assert process_result["exitCode"] == 0
    assert process_result["failedPhase"] == ""
    assert process_result["cause"] == ""
    assert set(process_result) == {
        "schema",
        "attemptId",
        "exitCode",
        "summary",
        "details",
        "failedPhase",
        "cause",
        "logRefs",
    }
    assert "claim" not in process_result and "receipt" not in process_result
    assert path != output / result["activation"]["activeRef"]
    publication = output / f"env/repo/runs/app-dependency-sync/{process_result['attemptId']}/report.json"
    assert publication.is_file()
    assert json.loads(publication.read_text(encoding="utf-8"))["claim"] == "PREPARED_NOT_ACTIVE"


@pytest.mark.parametrize(
    ("scenario", "expected_phase"),
    [
        ("success", ""),
        ("pub-online-failure", "pub-online-resolution"),
        ("pub-offline-failure", "pub-offline-replay"),
        ("pods-online-failure", "pods-online-resolution"),
        ("pods-offline-failure", "pods-offline-replay"),
        ("gradle-online-failure", "gradle-online-resolution"),
        ("gradle-offline-failure", "gradle-offline-replay"),
        ("publication-failure", "publication"),
    ],
)
def test_terminal_outcomes_preserve_exact_live_dependency_input_bytes_and_modes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
    expected_phase: str,
) -> None:
    output = tmp_path / "output"
    repo = tmp_path / "repo"
    inputs = {
        repo / "quwoquan_app/pubspec.yaml": (b"name: fixture\n", 0o640),
        repo / "quwoquan_app/pubspec.lock": (b"packages: {}\n", 0o600),
        repo / "quwoquan_app/test_host/patrol/pubspec.lock": (
            b"packages: {}\n",
            0o644,
        ),
        repo / "quwoquan_app/ios/Podfile.lock": (b"PODS: []\n", 0o640),
        repo / "quwoquan_app/test_host/patrol/ios/Podfile.lock": (
            b"PODS: []\n",
            0o600,
        ),
        repo / "quwoquan_app/android/gradle/runtime-config-assets.gradle.kts": (
            b"plugins {}\n",
            0o644,
        ),
    }
    for input_path, (content, mode) in inputs.items():
        input_path.parent.mkdir(parents=True, exist_ok=True)
        input_path.write_bytes(content)
        input_path.chmod(mode)
    _stub_sync(monkeypatch, output)
    monkeypatch.setattr(
        sync,
        "__file__",
        str(repo / "quwoquan_ops/cli/commands/app_dependency_sync.py"),
    )
    monkeypatch.setattr(
        sync._builder,
        "_resolution_input_paths",
        lambda _root: set(inputs),
    )
    before = sync._builder.resolution_seal(repo)
    active = output / "env/repo/local/app-dependency-sync/cache/active.json"
    active.parent.mkdir(parents=True)
    active.write_text("old-active\n", encoding="ascii")

    def builder(context: sync.DependencyComponentBuildContext) -> Mapping[str, Path]:
        assert sync._builder.resolution_seal(repo) == before
        if scenario not in {"success", "publication-failure"}:
            context.progress.begin(expected_phase)
            sync._builder._write_private_log(
                context.process_root / f"{expected_phase}.log",
                f"fixture {scenario}",
            )
            raise ValueError(f"APP.DEPENDENCY.sync_failed: {scenario}")
        return _component_builder()(context)

    def fail_publication(**_kwargs: object):
        raise OSError("fixture publication unavailable")

    result = sync.command_app_dependency_sync(
        argparse.Namespace(),
        component_builder=builder,
        publisher=fail_publication if scenario == "publication-failure" else None,
    )

    assert result["exitCode"] == (0 if scenario == "success" else 2)
    _path, process_result = _process_result(output, result)
    assert process_result["failedPhase"] == expected_phase
    assert sync._builder.resolution_seal(repo) == before
    for input_path, (content, mode) in inputs.items():
        assert input_path.read_bytes() == content
        assert stat.S_IMODE(input_path.stat().st_mode) == mode
    if scenario == "success":
        assert json.loads(active.read_text(encoding="utf-8"))["attemptId"] == result[
            "activation"
        ]["attemptId"]
    else:
        assert active.read_text(encoding="ascii") == "old-active\n"


@pytest.mark.parametrize("drift_kind", ["bytes", "mode"])
def test_live_source_drift_blocks_before_publication_and_preserves_active(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    drift_kind: str,
) -> None:
    output = tmp_path / "output"
    repo = tmp_path / "repo"
    source = repo / "quwoquan_app/android/gradle/runtime-config-assets.gradle.kts"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"plugins {}\n")
    source.chmod(0o640)
    _stub_sync(monkeypatch, output)
    monkeypatch.setattr(sync, "__file__", str(repo / "quwoquan_ops/cli/commands/app_dependency_sync.py"))
    monkeypatch.setattr(sync._builder, "_resolution_input_paths", lambda _root: {source})
    active = output / "env/repo/local/app-dependency-sync/cache/active.json"
    active.parent.mkdir(parents=True)
    active.write_text("old-active\n", encoding="ascii")

    def drift(context: sync.DependencyComponentBuildContext) -> Mapping[str, Path]:
        roots = _component_builder()(context)
        if drift_kind == "bytes":
            source.write_bytes(b"plugins { id(\\\"drift\\\") }\n")
        else:
            source.chmod(0o600)
        return roots

    result = sync.command_app_dependency_sync(
        argparse.Namespace(), component_builder=drift
    )

    assert result["exitCode"] == 2
    assert result["details"][0].startswith("APP.DEPENDENCY.live_source_drift")
    assert active.read_text(encoding="ascii") == "old-active\n"
    assert not (output / "env/repo/runs/app-dependency-sync").exists()


def test_live_source_drift_during_receipt_publication_blocks_active_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "output"
    repo = tmp_path / "repo"
    source = repo / "quwoquan_app/ios/Podfile.lock"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"PODS:\n")
    source.chmod(0o640)
    _stub_sync(monkeypatch, output)
    monkeypatch.setattr(
        sync,
        "__file__",
        str(repo / "quwoquan_ops/cli/commands/app_dependency_sync.py"),
    )
    monkeypatch.setattr(sync._builder, "_resolution_input_paths", lambda _root: {source})
    active = output / "env/repo/local/app-dependency-sync/cache/active.json"
    active.parent.mkdir(parents=True)
    active.write_text("old-active\n", encoding="ascii")
    original_atomic = sync._atomic_json

    def mutate_after_receipt(
        path: Path, value: dict[str, object], *, mode: int
    ) -> None:
        original_atomic(path, value, mode=mode)
        if path.name == "report.json":
            source.write_bytes(b"PODS:\n  Drifted: 1\n")

    monkeypatch.setattr(sync, "_atomic_json", mutate_after_receipt)
    result = sync.command_app_dependency_sync(
        argparse.Namespace(), component_builder=_component_builder()
    )

    assert result["exitCode"] == 2
    assert result["details"][0].startswith("APP.DEPENDENCY.live_source_drift")
    assert active.read_text(encoding="ascii") == "old-active\n"
    attempt_id = next(
        item.split("=", 1)[1]
        for item in result["details"]
        if item.startswith("attemptId=")
    )
    receipt = output / f"env/repo/runs/app-dependency-sync/{attempt_id}/report.json"
    assert receipt.is_file()
    assert json.loads(receipt.read_text(encoding="utf-8"))["claim"] == "PREPARED_NOT_ACTIVE"
    snapshots = active.parent / "snapshots"
    assert not snapshots.exists() or not any(snapshots.iterdir())



def test_lock_failure_still_persists_process_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "output"
    repo = tmp_path / "repo"
    source_path = repo / "quwoquan_app/pubspec.lock"
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(b"packages: {}\n")
    source_path.chmod(0o600)
    _stub_sync(monkeypatch, output)
    monkeypatch.setattr(
        sync,
        "__file__",
        str(repo / "quwoquan_ops/cli/commands/app_dependency_sync.py"),
    )
    monkeypatch.setattr(
        sync._builder,
        "_resolution_input_paths",
        lambda _root: {source_path},
    )

    class DeniedLock:
        def __enter__(self) -> None:
            raise ValueError("APP.DEPENDENCY.sync_lock_timeout: fixture")

        def __exit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(sync, "_sync_lock", DeniedLock)

    result = sync.command_app_dependency_sync(argparse.Namespace())

    path, process_result = _process_result(output, result)
    assert result["exitCode"] == 2
    assert process_result["failedPhase"] == "live-source-seal"
    assert process_result["cause"] == "value_error"
    assert process_result["details"][0].startswith(
        "APP.DEPENDENCY.sync_lock_timeout"
    )
    assert path.is_file()
    assert source_path.read_bytes() == b"packages: {}\n"
    assert stat.S_IMODE(source_path.stat().st_mode) == 0o600
