"""Transactional publication contract for ``stackctl app-dependency-sync``."""

# spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-004

from __future__ import annotations

import argparse
import json
import os
import stat
import subprocess
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace

import pytest

from quwoquan_ops.cli.commands import app_dependency_sync as sync
from quwoquan_ops.tests.support.app_dependency_sync_test_support import (
    android_failure_fixture,
)
from quwoquan_ops.tests.support.app_dependency_sync_test_support import (
    component_builder as _component_builder,
)
from quwoquan_ops.tests.support.app_dependency_sync_test_support import (
    digest as _digest,
)
from quwoquan_ops.tests.support.app_dependency_sync_test_support import (
    minimal_projection_source as _minimal_projection_source,
)
from quwoquan_ops.tests.support.app_dependency_sync_test_support import (
    source_identity as _source_identity,
)
from quwoquan_ops.tests.support.app_dependency_sync_test_support import (
    stub_sync as _stub_sync,
)


def test_active_pointer_is_final_commit_after_complete_prepared_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "output"
    _stub_sync(monkeypatch, output)
    writes: list[str] = []
    original = sync._atomic_json

    def recording_write(path: Path, value: dict[str, object], *, mode: int) -> None:
        writes.append(path.name)
        original(path, value, mode=mode)

    monkeypatch.setattr(sync, "_atomic_json", recording_write)
    result = sync.command_app_dependency_sync(
        argparse.Namespace(), component_builder=_component_builder()
    )

    assert result["exitCode"] == 0
    assert writes == ["report.json", "active.json"]
    assert result["receipt"]["schema"] == sync.APP_DEPENDENCY_BUNDLE_RECEIPT_SCHEMA
    assert result["receipt"]["claim"] == "PREPARED_NOT_ACTIVE"
    assert set(result["receipt"]["components"]) == set(sync.APP_DEPENDENCY_COMPONENTS)
    assert result["activation"]["status"] == "committed"
    attempt_id = result["activation"]["attemptId"]
    assert not (
        output / "env/repo/local/app-dependency-sync/cache/work" / attempt_id
    ).exists()
    active = json.loads(
        (output / result["activation"]["activeRef"]).read_text(encoding="utf-8")
    )
    assert active["schema"] == sync.APP_DEPENDENCY_BUNDLE_ACTIVE_SCHEMA
    assert active["attemptId"] == attempt_id


def test_injectable_publisher_receives_only_complete_bound_declarations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "output"
    _stub_sync(monkeypatch, output)
    calls: list[dict[str, object]] = []

    def publisher(**kwargs: object):
        calls.append(dict(kwargs))
        return sync.publish_dependency_bundle_activation(**kwargs)

    result = sync.command_app_dependency_sync(
        argparse.Namespace(),
        component_builder=_component_builder(),
        publisher=publisher,
    )

    assert result["exitCode"] == 0
    assert len(calls) == 1
    assert set(calls[0]["components"]) == set(sync.APP_DEPENDENCY_COMPONENTS)
    assert calls[0]["source_identity"] == _source_identity()


def test_successful_sync_replaces_stale_active_and_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "output"
    _stub_sync(monkeypatch, output)
    active_root = output / "env/repo/local/app-dependency-sync/cache"
    active_root.mkdir(parents=True)
    stale_attempt = "f" * 32
    (active_root / "active.json").write_text(
        json.dumps({"schema": sync.APP_DEPENDENCY_BUNDLE_ACTIVE_SCHEMA, "attemptId": stale_attempt}),
        encoding="utf-8",
    )
    stale_receipt = output / "env/repo/runs/app-dependency-sync/stale/report.json"
    stale_receipt.parent.mkdir(parents=True)
    stale_receipt.write_text('{"claim":"OLD"}', encoding="utf-8")
    result = sync.command_app_dependency_sync(
        argparse.Namespace(), component_builder=_component_builder()
    )

    assert result["exitCode"] == 0
    fresh_attempt = result["activation"]["attemptId"]
    assert fresh_attempt != stale_attempt
    active = json.loads((active_root / "active.json").read_text(encoding="utf-8"))
    assert active["attemptId"] == fresh_attempt
    assert active["receiptRef"] == (
        f"env/repo/runs/app-dependency-sync/{fresh_attempt}/report.json"
    )
    receipt = json.loads((output / active["receiptRef"]).read_text(encoding="utf-8"))
    assert receipt["attemptId"] == fresh_attempt
    assert receipt["claim"] == "PREPARED_NOT_ACTIVE"
    assert stale_receipt.read_text(encoding="utf-8") == '{"claim":"OLD"}'


def test_active_write_post_replace_failure_preserves_selected_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "output"
    _stub_sync(monkeypatch, output)
    original = sync._atomic_json

    def fail_after_active_replace(
        path: Path, value: dict[str, object], *, mode: int
    ) -> None:
        original(path, value, mode=mode)
        if path.name == "active.json":
            raise OSError("active parent fsync result unavailable")

    monkeypatch.setattr(sync, "_atomic_json", fail_after_active_replace)
    result = sync.command_app_dependency_sync(
        argparse.Namespace(), component_builder=_component_builder()
    )

    assert result["exitCode"] == 2
    assert result["details"][0].startswith("APP.DEPENDENCY.activation_commit_ambiguous")
    active_path = output / "env/repo/local/app-dependency-sync/cache/active.json"
    active = json.loads(active_path.read_text(encoding="utf-8"))
    attempt_id = active["attemptId"]
    generation = active_path.parent / "snapshots" / attempt_id
    assert generation.is_dir()
    assert {path.name for path in generation.iterdir()} == set(
        sync.APP_DEPENDENCY_COMPONENTS
    )


@pytest.mark.parametrize("readback_mode", ["unavailable", "invalid-json"])
def test_active_write_post_replace_unknown_readback_preserves_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    readback_mode: str,
) -> None:
    output = tmp_path / "output"
    _stub_sync(monkeypatch, output)
    original_atomic = sync._atomic_json
    original_read = sync.read_regular_nofollow

    def fail_after_active_replace(
        path: Path, value: dict[str, object], *, mode: int
    ) -> None:
        original_atomic(path, value, mode=mode)
        if path.name == "active.json":
            raise OSError("active parent fsync result unavailable")

    def unknown_active_readback(path: Path, *, label: str):
        if path.name != "active.json":
            return original_read(path, label=label)
        if readback_mode == "unavailable":
            raise OSError("fresh active readback unavailable")
        return b"{", 0o600

    monkeypatch.setattr(sync, "_atomic_json", fail_after_active_replace)
    monkeypatch.setattr(sync, "read_regular_nofollow", unknown_active_readback)
    result = sync.command_app_dependency_sync(
        argparse.Namespace(), component_builder=_component_builder()
    )

    assert result["exitCode"] == 2
    assert result["details"][0].startswith("APP.DEPENDENCY.activation_commit_ambiguous")
    assert "readback=unknown" in result["details"][0]
    active_path = output / "env/repo/local/app-dependency-sync/cache/active.json"
    active = json.loads(active_path.read_text(encoding="utf-8"))
    generation = active_path.parent / "snapshots" / active["attemptId"]
    assert generation.is_dir()
    assert {path.name for path in generation.iterdir()} == set(
        sync.APP_DEPENDENCY_COMPONENTS
    )


def test_successful_active_write_with_unavailable_fresh_readback_is_ambiguous(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "output"
    _stub_sync(monkeypatch, output)
    original_read = sync.read_regular_nofollow

    def unavailable_active(path: Path, *, label: str):
        if path.name == "active.json":
            raise OSError("fresh active readback unavailable")
        return original_read(path, label=label)

    monkeypatch.setattr(sync, "read_regular_nofollow", unavailable_active)
    result = sync.command_app_dependency_sync(
        argparse.Namespace(), component_builder=_component_builder()
    )

    assert result["exitCode"] == 2
    assert result["details"][0].startswith(
        "APP.DEPENDENCY.activation_commit_ambiguous"
    )
    active_path = output / "env/repo/local/app-dependency-sync/cache/active.json"
    active = json.loads(active_path.read_text(encoding="utf-8"))
    generation = active_path.parent / "snapshots" / active["attemptId"]
    assert generation.is_dir()
    assert {path.name for path in generation.iterdir()} == set(
        sync.APP_DEPENDENCY_COMPONENTS
    )


def test_active_write_failure_with_valid_other_pointer_cleans_new_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "output"
    _stub_sync(monkeypatch, output)
    first = sync.command_app_dependency_sync(
        argparse.Namespace(), component_builder=_component_builder()
    )
    assert first["exitCode"] == 0
    first_attempt = first["activation"]["attemptId"]
    original_atomic = sync._atomic_json

    def fail_before_active_replace(
        path: Path, value: dict[str, object], *, mode: int
    ) -> None:
        if path.name == "active.json":
            raise OSError("active replace unavailable")
        original_atomic(path, value, mode=mode)

    monkeypatch.setattr(sync, "_atomic_json", fail_before_active_replace)
    second = sync.command_app_dependency_sync(
        argparse.Namespace(), component_builder=_component_builder()
    )

    assert second["exitCode"] == 2
    assert second["details"][0] == "APP.DEPENDENCY.sync_blocked: cause=io_error; detail=active replace unavailable"
    active_path = output / "env/repo/local/app-dependency-sync/cache/active.json"
    active = json.loads(active_path.read_text(encoding="utf-8"))
    assert active["attemptId"] == first_attempt
    snapshots = active_path.parent / "snapshots"
    assert {path.name for path in snapshots.iterdir()} == {first_attempt}


@pytest.mark.parametrize("failure_mode", ["raise", "invalid-return"])
def test_injectable_publisher_post_commit_failure_preserves_selected_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_mode: str,
) -> None:
    output = tmp_path / "output"
    _stub_sync(monkeypatch, output)

    def publisher(**kwargs: object):
        published = sync.publish_dependency_bundle_activation(**kwargs)
        if failure_mode == "raise":
            raise RuntimeError("publisher lost its acknowledgement")
        receipt, active, receipt_path, active_path = published
        return {**receipt, "attemptId": "wrong-attempt"}, active, receipt_path, active_path

    result = sync.command_app_dependency_sync(
        argparse.Namespace(),
        component_builder=_component_builder(),
        publisher=publisher,
    )

    assert result["exitCode"] == 2
    assert result["details"][0].startswith("APP.DEPENDENCY.activation_commit_ambiguous")
    assert result["details"][1].startswith("cause=")
    active_path = output / "env/repo/local/app-dependency-sync/cache/active.json"
    active = json.loads(active_path.read_text(encoding="utf-8"))
    generation = active_path.parent / "snapshots" / active["attemptId"]
    assert generation.is_dir()
    assert {path.name for path in generation.iterdir()} == set(
        sync.APP_DEPENDENCY_COMPONENTS
    )


def test_receipt_failure_never_switches_existing_active_pointer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "output"
    _stub_sync(monkeypatch, output)
    active = output / "env/repo/local/app-dependency-sync/cache/active.json"
    active.parent.mkdir(parents=True)
    active.write_text("old-active\n", encoding="ascii")
    original = sync._atomic_json

    def fail_receipt(path: Path, value: dict[str, object], *, mode: int) -> None:
        if path.name == "report.json":
            raise OSError("receipt unavailable")
        original(path, value, mode=mode)

    monkeypatch.setattr(sync, "_atomic_json", fail_receipt)
    result = sync.command_app_dependency_sync(
        argparse.Namespace(), component_builder=_component_builder()
    )

    assert result["exitCode"] == 2
    assert result["details"][0].startswith("APP.DEPENDENCY.sync_blocked")
    assert active.read_text(encoding="ascii") == "old-active\n"


def test_active_write_failure_preserves_existing_pointer_after_prepared_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "output"
    _stub_sync(monkeypatch, output)
    active = output / "env/repo/local/app-dependency-sync/cache/active.json"
    active.parent.mkdir(parents=True)
    active.write_text("old-active\n", encoding="ascii")
    original = sync._atomic_json

    def fail_active(path: Path, value: dict[str, object], *, mode: int) -> None:
        if path.name == "active.json":
            raise OSError("active unavailable")
        original(path, value, mode=mode)

    monkeypatch.setattr(sync, "_atomic_json", fail_active)
    result = sync.command_app_dependency_sync(
        argparse.Namespace(), component_builder=_component_builder()
    )

    assert result["exitCode"] == 2
    assert active.read_text(encoding="ascii") == "old-active\n"
    attempt_root = next((output / "env/repo/runs/app-dependency-sync").iterdir())
    receipt = json.loads((attempt_root / "report.json").read_text(encoding="utf-8"))
    assert receipt["claim"] == "PREPARED_NOT_ACTIVE"


def test_incomplete_component_generation_never_writes_receipt_or_active(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "output"
    _stub_sync(monkeypatch, output)
    complete = _component_builder()

    def incomplete(context: sync.DependencyComponentBuildContext):
        roots = dict(complete(context))
        roots.pop("patrolIosPods")
        return roots

    result = sync.command_app_dependency_sync(
        argparse.Namespace(), component_builder=incomplete
    )

    assert result["exitCode"] == 2
    assert result["details"][0] == "APP.DEPENDENCY.component_set_incomplete"
    assert not (output / "env/repo/runs/app-dependency-sync").exists()
    assert not (
        output / "env/repo/local/app-dependency-sync/cache/active.json"
    ).exists()


def test_cross_attempt_component_is_rejected_before_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "output"
    _stub_sync(monkeypatch, output)
    complete = _component_builder()

    def cross_attempt(context: sync.DependencyComponentBuildContext):
        roots = dict(complete(context))
        roots["androidGradle"] = (
            context.generation_root.parent / "another-attempt/androidGradle"
        )
        return roots

    result = sync.command_app_dependency_sync(
        argparse.Namespace(), component_builder=cross_attempt
    )

    assert result["exitCode"] == 2
    assert result["details"][0] == (
        "APP.DEPENDENCY.component_cross_attempt: androidGradle"
    )
    assert not (output / "env/repo/runs/app-dependency-sync").exists()


def test_pub_to_native_upstream_mismatch_is_rejected_before_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "output"
    _stub_sync(monkeypatch, output)

    def drift(manifests: dict[str, dict[str, object]]) -> None:
        manifests["productionIosPods"]["upstreamDependencyDigest"] = _digest("9")

    result = sync.command_app_dependency_sync(
        argparse.Namespace(), component_builder=_component_builder(drift)
    )

    assert result["exitCode"] == 2
    assert result["details"][0] == (
        "APP.DEPENDENCY.component_binding_invalid: productionIosPods upstream"
    )
    assert not (output / "env/repo/runs/app-dependency-sync").exists()


def test_source_drift_after_component_build_blocks_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "output"
    _stub_sync(monkeypatch, output)
    identities = [_source_identity(), {**_source_identity(), "flutterVersion": "9.9.9"}]
    monkeypatch.setattr(sync, "_source_identity", lambda **_kwargs: identities.pop(0))

    result = sync.command_app_dependency_sync(
        argparse.Namespace(), component_builder=_component_builder()
    )

    assert result["exitCode"] == 2
    assert result["details"][0] == ("APP.DEPENDENCY.source_identity_drift_during_sync")
    assert not (output / "env/repo/runs/app-dependency-sync").exists()


@pytest.mark.parametrize("poisoned", [False, True])
def test_default_sync_owns_private_trust_and_ignores_caller_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    poisoned: bool,
) -> None:
    output = tmp_path / "output"
    _stub_sync(monkeypatch, output)
    poison = str(tmp_path / "caller-owned-trust")
    if poisoned:
        monkeypatch.setenv("QWQ_ANDROID_RUNTIME_CONFIG_ASSET_ROOT", poison)
    else:
        monkeypatch.delenv("QWQ_ANDROID_RUNTIME_CONFIG_ASSET_ROOT", raising=False)
    observed: dict[str, object] = {}

    def build(
        context: sync.DependencyComponentBuildContext, *, trust_root: Path
    ) -> Mapping[str, Path]:
        trust_path = trust_root / "qwq_runtime/runtime-config-trust.json"
        payload = json.loads(trust_path.read_text(encoding="utf-8"))
        observed.update(
            root=trust_root,
            keys=tuple(payload["trustedPublicKeys"].values()),
        )
        assert context.attempt_id in trust_root.name
        assert not trust_root.is_relative_to(context.repo_root.resolve())
        assert not trust_root.is_relative_to(output.resolve())
        assert trust_root.stat().st_mode & 0o777 == 0o700
        assert trust_path.parent.stat().st_mode & 0o777 == 0o700
        assert trust_path.stat().st_mode & 0o777 == 0o600
        assert payload["buildProfile"] == "nonprod"
        return _component_builder()(context)

    monkeypatch.setattr(sync._builder, "build_dependency_components", build)
    result = sync.command_app_dependency_sync(argparse.Namespace())

    assert result["exitCode"] == 0
    assert set(result["receipt"]["components"]) == set(sync.APP_DEPENDENCY_COMPONENTS)
    trust_root = Path(observed["root"])
    assert not trust_root.exists()
    receipt = json.dumps(result["receipt"], ensure_ascii=False, sort_keys=True)
    assert str(trust_root) not in receipt
    assert "trustedPublicKeys" not in receipt
    assert all(str(key) not in receipt for key in observed["keys"])
    assert (
        sync.os.environ.get("QWQ_ANDROID_RUNTIME_CONFIG_ASSET_ROOT")
        == (poison if poisoned else None)
    )


@pytest.mark.parametrize("primary", ["materialize", "build"])
def test_primary_trust_failure_precedes_cleanup_failure_without_leakage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    primary: str,
) -> None:
    output = tmp_path / "output"
    _stub_sync(monkeypatch, output)
    roots: list[Path] = []
    secret = "fixturePrivateKeyMaterial"
    original_materializer = sync.materialize_runtime_config_trust_envelope
    original_remove = sync.remove_private_tree
    def materialize(envelope: object, raw: str, contract: object) -> None:
        roots.append(Path(raw).parent.parent)
        if primary == "materialize":
            raise OSError(f"{raw} trustedPublicKeys={secret}")
        original_materializer(envelope, raw, contract)
    def build(
        context: sync.DependencyComponentBuildContext, *, trust_root: Path
    ) -> Mapping[str, Path]:
        if primary == "build":
            raise OSError(f"{trust_root} privateKey={secret}")
        return _component_builder()(context)
    def cleanup(path: Path) -> None:
        if roots and path == roots[0]:
            raise OSError(f"{path} keyring={secret}")
        original_remove(path)
    monkeypatch.setattr(sync, "materialize_runtime_config_trust_envelope", materialize)
    monkeypatch.setattr(sync._builder, "build_dependency_components", build)
    monkeypatch.setattr(sync, "remove_private_tree", cleanup)
    result = sync.command_app_dependency_sync(argparse.Namespace())
    rendered = json.dumps(result, ensure_ascii=False, sort_keys=True)
    original_remove(roots[0])
    assert result["exitCode"] == 2
    if primary == "materialize":
        assert result["details"][0] == (
            "APP.DEPENDENCY.android_runtime_trust_materialization_failed: cause=io_error"
        )
    else:
        assert result["details"][0].startswith(
            "APP.DEPENDENCY.sync_blocked: cause=io_error; detail="
        )
    assert result["details"][1] == (
        "APP.DEPENDENCY.android_runtime_trust_cleanup_warning: cause=io_error"
    )
    assert str(roots[0]) not in rendered and secret not in rendered
    assert "trustedPublicKeys" not in rendered and "privateKey" not in rendered
    assert not roots[0].exists()
    assert not (output / "env/repo/runs/app-dependency-sync").exists()


@pytest.mark.parametrize("failure_mode", ["build", "ambiguous"])
def test_default_sync_cleans_trust_on_build_and_ambiguous_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_mode: str,
) -> None:
    output = tmp_path / "output"
    _stub_sync(monkeypatch, output)
    roots: list[Path] = []
    secret = "fixturePrivateKeyMaterial"
    def build(
        context: sync.DependencyComponentBuildContext, *, trust_root: Path
    ) -> Mapping[str, Path]:
        roots.append(trust_root)
        if failure_mode == "build":
            raise OSError(f"{trust_root} privateKey={secret}")
        return _component_builder()(context)
    def publisher(**kwargs: object):
        sync.publish_dependency_bundle_activation(**kwargs)
        raise RuntimeError(f"{roots[0]} keyring={secret}")

    monkeypatch.setattr(sync._builder, "build_dependency_components", build)
    result = sync.command_app_dependency_sync(
        argparse.Namespace(),
        publisher=publisher if failure_mode == "ambiguous" else None,
    )
    assert result["exitCode"] == 2
    assert len(roots) == 1 and not roots[0].exists()
    if failure_mode == "build":
        assert result["details"][0].startswith(
            "APP.DEPENDENCY.sync_blocked: cause=io_error; detail="
        )
        work = output / "env/repo/local/app-dependency-sync/cache/work"
        snapshots = output / "env/repo/local/app-dependency-sync/cache/snapshots"
        assert not work.exists() or not any(work.iterdir())
        assert not snapshots.exists() or not any(snapshots.iterdir())
    else:
        assert result["details"][0].startswith(
            "APP.DEPENDENCY.activation_commit_ambiguous"
        )
        assert result["details"][1] == "cause=runtime_error"
    rendered = json.dumps(result, ensure_ascii=False, sort_keys=True)
    assert str(roots[0]) not in rendered and secret not in rendered


def test_android_gradle_failure_log_and_detail_redact_trust_material(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, projection, replays, digests, trust = android_failure_fixture(tmp_path)
    secret = "fixturePrivateKeyMaterial"
    leaked = f"{trust} {secret} /private/key"
    monkeypatch.setattr(
        sync._builder, "canonical_android_uat_gradle_invocations", lambda _root: ()
    )
    def fail(**_kwargs: object) -> object:
        raise subprocess.CalledProcessError(7, ["gradle"], output=leaked)
    monkeypatch.setattr(sync._builder, "synchronize_android_gradle_dependencies", fail)
    with pytest.raises(ValueError) as raised:
        sync._builder._build_android_component(
            context=context,
            projection_root=projection,
            pub_replays=replays,
            pub_digests=digests,
            trust_root=trust,
            trust_sensitive_values=(str(trust), secret, "/private/key"),
        )
    log = (context.process_root / "android-gradle-failed.log").read_text()
    assert str(raised.value).startswith(
        "APP.DEPENDENCY.android_sync_failed: cause=subprocess_nonzero"
    )
    assert log == "[REDACTED dependency trust material]"
    assert all(value not in f"{raised.value}\n{log}" for value in (str(trust), secret, "/private/key"))


@pytest.mark.parametrize("offline", [False, True])
def test_flutter_pub_commands_use_private_home_cache_spm_false_and_exact_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    offline: bool,
) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setenv("HTTP_PROXY", "http://must-not-leak.invalid")
    monkeypatch.setenv("COCOAPODS_HOME", str(tmp_path / "global-pods"))
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "must-not-reach-child")

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append({"command": command, **kwargs})
        return subprocess.CompletedProcess(command, 0, stdout="ok\n")

    monkeypatch.setattr(sync._builder, "run_managed_subprocess", run)
    app = tmp_path / "project/app"
    app.mkdir(parents=True)
    pub = tmp_path / "private-pub"
    sync._run_pub_get(
        flutter="/fixture/flutter",
        app_dir=app,
        pub_cache=pub,
        hosted_url="https://pub.dev",
        offline=offline,
        log_path=tmp_path / "sync.log",
    )

    assert len(calls) == 1
    command = calls[0]["command"]
    environment = calls[0]["env"]
    assert command[:3] == ["/fixture/flutter", "pub", "get"]
    assert "--enforce-lockfile" in command
    assert ("--offline" in command) is offline
    assert "upgrade" not in command
    assert environment["PUB_CACHE"] == str(pub)
    assert environment["HOME"] == str(app.parent / "flutter-home")
    assert environment["FLUTTER_SWIFT_PACKAGE_MANAGER"] == "false"
    assert environment["XDG_CONFIG_HOME"].startswith(environment["HOME"])
    assert environment["XDG_CACHE_HOME"].startswith(environment["HOME"])
    assert "HTTP_PROXY" not in environment
    assert environment["GIT_CONFIG_GLOBAL"] == "/dev/null"
    assert "COCOAPODS_HOME" not in environment
    assert "AWS_SECRET_ACCESS_KEY" not in environment


def test_pub_command_timeout_is_typed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def timeout(*_args: object, **_kwargs: object) -> object:
        raise subprocess.TimeoutExpired(["flutter", "pub", "get"], 900)

    monkeypatch.setattr(sync._builder, "run_managed_subprocess", timeout)
    app = tmp_path / "app"
    app.mkdir()
    with pytest.raises(ValueError, match="APP.DEPENDENCY.sync_timeout"):
        sync._run_pub_get(
            flutter="flutter",
            app_dir=app,
            pub_cache=tmp_path / "pub",
            hosted_url="https://pub.dev",
            offline=False,
            log_path=tmp_path / "sync.log",
        )


def test_concurrent_sync_lock_fails_with_bounded_typed_blocker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path / "output"))
    monkeypatch.setattr(sync, "_LOCK_TIMEOUT_SECONDS", 0)
    with (
        sync._sync_lock(),
        pytest.raises(ValueError, match="APP.DEPENDENCY.sync_lock_timeout"),
        sync._sync_lock(),
    ):
        raise AssertionError("unreachable")


def test_builder_error_returns_typed_result_and_cleans_attempt_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "output"
    _stub_sync(monkeypatch, output)

    def fail(context: sync.DependencyComponentBuildContext) -> Mapping[str, Path]:
        (context.work_root / "temporary").write_text("work", encoding="ascii")
        raise OSError("projection denied")

    result = sync.command_app_dependency_sync(
        argparse.Namespace(), component_builder=fail
    )

    assert result["exitCode"] == 2
    assert result["details"][0] == "APP.DEPENDENCY.sync_blocked: cause=io_error; detail=projection denied"
    work = output / "env/repo/local/app-dependency-sync/cache/work"
    snapshots = output / "env/repo/local/app-dependency-sync/cache/snapshots"
    assert not work.exists() or not any(work.iterdir())
    assert not snapshots.exists() or not any(snapshots.iterdir())


def test_source_projection_excludes_generated_flutter_native_and_build_state(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _minimal_projection_source(repo)

    app = sync._project(repo, tmp_path / "projection")

    assert (app / "lib/main.dart").is_file()
    assert (app / "test_host/patrol/test/canonical").resolve() == (
        app / "test"
    ).resolve()
    assert not (app / ".dart_tool").exists()
    assert not (app / ".flutter-plugins-dependencies").exists()
    assert not (app / "build").exists()
    assert not (app / "ios/Pods").exists()
    assert not (app / "ios/Flutter/Generated.xcconfig").exists()
    assert not (app / "ios/Flutter/Flutter.podspec").exists()
    assert (
        tmp_path / "projection/quwoquan_service/contracts/runtime_errors/packages/dart/"
        "quwoquan_runtime_errors/pubspec.yaml"
    ).is_file()


def test_source_projection_rejects_symlink_escape(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    app = _minimal_projection_source(repo)
    outside = tmp_path / "outside"
    outside.mkdir()
    (app / "escape").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="source_projection_link_escape"):
        sync._project(repo, tmp_path / "projection")


def test_real_builder_orchestrates_five_components_and_final_domain_readback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    work, process, generation = (
        tmp_path / "work",
        tmp_path / "process",
        tmp_path / "generation",
    )
    for path in (work, process, generation):
        path.mkdir()
    context = sync.DependencyComponentBuildContext(
        repo_root=tmp_path / "repo",
        attempt_id="a" * 32,
        work_root=work,
        process_root=process,
        generation_root=generation,
        flutter_identity={"executable": "/flutter"},
        source_identity=_source_identity(),
    )
    calls: list[object] = []
    pub_roots = {
        "productionPub": generation / "productionPub",
        "patrolPub": generation / "patrolPub",
    }
    pub_replays = {name: work / f"{name}-replay" for name in pub_roots}
    pub_digests = {"productionPub": _digest("1"), "patrolPub": _digest("2")}
    trust = tmp_path / "trust"
    trust_directory = trust / "qwq_runtime"
    trust_directory.mkdir(parents=True, mode=0o700)
    trust.chmod(0o700)
    trust_directory.chmod(0o700)
    (trust_directory / "runtime-config-trust.json").write_text("{}", encoding="utf-8")
    (trust_directory / "runtime-config-trust.json").chmod(0o600)
    poison = str(tmp_path / "poisoned-caller-root")
    monkeypatch.setenv("QWQ_ANDROID_RUNTIME_CONFIG_ASSET_ROOT", poison)
    monkeypatch.setattr(
        sync._builder, "resolve_cocoapods_executable", lambda _raw: "/pod"
    )
    monkeypatch.setattr(sync._builder, "_resolution_seal", lambda _root: {})

    def project(_repo: Path, target: Path) -> Path:
        target.mkdir()
        return target / "quwoquan_app"

    monkeypatch.setattr(sync._builder, "project", project)
    monkeypatch.setattr(
        sync._builder,
        "_assert_resolution_seal",
        lambda **kwargs: calls.append(("seal", kwargs["projection_root"])),
    )
    monkeypatch.setattr(
        sync._builder,
        "_build_pub_components",
        lambda **_kwargs: (dict(pub_roots), pub_replays, pub_digests),
    )

    def ios(**kwargs: object) -> Path:
        host = str(kwargs["host"])
        calls.append(("ios", host, kwargs["upstream_digest"]))
        name = "productionIosPods" if host == "production" else "patrolIosPods"
        return generation / name

    monkeypatch.setattr(sync._builder, "_build_ios_component", ios)
    monkeypatch.setattr(
        sync._builder,
        "_build_android_component",
        lambda **kwargs: (
            calls.append(("android", kwargs["pub_digests"], kwargs["trust_root"]))
            or generation / "androidGradle"
        ),
    )
    monkeypatch.setattr(
        sync._builder,
        "_verify_components",
        lambda **kwargs: calls.append(("verify", set(kwargs["roots"]))),
    )

    roots = sync._builder.build_dependency_components(context, trust_root=trust)

    assert set(roots) == set(sync.APP_DEPENDENCY_COMPONENTS)
    assert ("ios", "production", _digest("1")) in calls
    assert ("ios", "patrol", _digest("2")) in calls
    assert ("android", pub_digests, trust) in calls
    assert calls[-1] == ("verify", set(sync.APP_DEPENDENCY_COMPONENTS))
    assert sync.os.environ["QWQ_ANDROID_RUNTIME_CONFIG_ASSET_ROOT"] == poison


@pytest.mark.parametrize(
    ("host", "has_flavor"),
    [(sync.IOS_POD_PRODUCTION_HOST, True), (sync.IOS_POD_PATROL_HOST, False)],
)
def test_ios_builder_refreshes_config_in_private_spm_false_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    host: str,
    has_flavor: bool,
) -> None:
    projection = tmp_path / "projection"
    app = (
        projection / "quwoquan_app"
        if host == sync.IOS_POD_PRODUCTION_HOST
        else projection / "quwoquan_app/test_host/patrol"
    )
    ios = app / "ios"
    ios.mkdir(parents=True)
    process, generation, work = (
        tmp_path / "process",
        tmp_path / "generation",
        tmp_path / "work",
    )
    for path in (process, generation, work):
        path.mkdir()
    flutter = tmp_path / "toolchain/flutter/bin/flutter"
    flutter.parent.mkdir(parents=True)
    flutter.write_text("#!/bin/sh\n", encoding="utf-8")
    flutter.chmod(0o755)
    context = sync.DependencyComponentBuildContext(
        repo_root=tmp_path / "repo",
        attempt_id="a" * 32,
        work_root=work,
        process_root=process,
        generation_root=generation,
        flutter_identity={"executable": str(flutter)},
        source_identity=_source_identity(),
    )
    commands: list[dict[str, object]] = []
    pod_home, pod_cache = tmp_path / "pod-home", tmp_path / "pod-cache"
    pod_home.mkdir()
    pod_cache.mkdir()
    monkeypatch.setattr(sync._builder, "_locked_host", lambda _lock: "https://pub.dev")
    monkeypatch.setattr(
        sync._builder,
        "_pod_environment",
        lambda **_kwargs: (
            {"FLUTTER_SWIFT_PACKAGE_MANAGER": "false"},
            pod_home,
            pod_cache,
        ),
    )

    def run_checked(**kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(dict(kwargs))
        if kwargs["command"][0] == "/pod":
            (ios / "Pods").mkdir()
        return subprocess.CompletedProcess(kwargs["command"], 0, stdout="ok")

    monkeypatch.setattr(sync._builder, "_run_checked", run_checked)
    monkeypatch.setattr(
        sync._builder, "_assert_ios_generated_metadata", lambda _app: None
    )
    monkeypatch.setattr(
        sync._builder, "ios_pod_resolution_inputs", lambda **_kwargs: {}
    )
    monkeypatch.setattr(
        sync._builder, "build_verified_ios_pod_snapshot", lambda **_kwargs: object()
    )

    def write_capsule(_snapshot: object, target: Path) -> Path:
        target.mkdir()
        return target

    monkeypatch.setattr(sync._builder, "write_ios_pod_capsule", write_capsule)
    monkeypatch.setattr(
        sync._builder, "materialize_ios_pod_projection", lambda **_kwargs: object()
    )
    monkeypatch.setattr(
        sync._builder,
        "run_offline_cocoapods_install",
        lambda **_kwargs: SimpleNamespace(
            evidence_manifest={"schema": "fixture.v1"},
            stdout="one",
            stderr="",
            second_stdout="two",
            second_stderr="",
        ),
    )

    sync._builder._build_ios_component(
        context=context,
        projection_root=projection,
        pod="/pod",
        host=host,
        pub_cache=tmp_path / "pub",
        upstream_digest=_digest("1"),
    )

    flutter_call, pod_call = commands
    flutter_command = flutter_call["command"]
    environment = flutter_call["environment"]
    assert isinstance(flutter_command, list)
    assert isinstance(environment, Mapping)
    assert flutter_command[:3] == [str(flutter), "build", "ios"]
    assert {"--config-only", "--no-codesign", "--no-pub", "-t"}.issubset(
        flutter_command
    )
    assert ("--flavor" in flutter_command) is has_flavor
    assert environment["FLUTTER_SWIFT_PACKAGE_MANAGER"] == "false"
    assert environment["QWQ_REAL_FLUTTER"] == str(flutter)
    assert environment["FLUTTER_ROOT"] == str(flutter.parent.parent)
    assert flutter_call["retry_transient_network"] is True
    assert pod_call["command"] == ["/pod", "install", "--deployment"]
    assert pod_call["retry_transient_network"] is True


def test_ios_generated_metadata_must_bind_projection_and_remove_spm(
    tmp_path: Path,
) -> None:
    app = tmp_path / "projection/quwoquan_app"
    flutter = app / "ios/Flutter"
    project = app / "ios/Runner.xcodeproj/project.pbxproj"
    flutter.mkdir(parents=True)
    project.parent.mkdir(parents=True)
    (flutter / "Generated.xcconfig").write_text(
        f"FLUTTER_APPLICATION_PATH={app}\n", encoding="utf-8"
    )
    (flutter / "Flutter.podspec").write_text("Pod::Spec.new\n", encoding="utf-8")
    project.write_text("// CocoaPods only\n", encoding="utf-8")

    sync._builder._assert_ios_generated_metadata(app)

    project.write_text("FlutterGeneratedPluginSwiftPackage\n", encoding="utf-8")
    with pytest.raises(ValueError, match="flutter_spm_residue_forbidden"):
        sync._builder._assert_ios_generated_metadata(app)
