"""Gradle wrapper materialization contract for app dependency sync."""

# spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-004

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from quwoquan_ops.cli.commands import app_dependency_sync as sync
from quwoquan_ops.tests.support.app_dependency_sync_test_support import (
    android_failure_fixture,
)


def test_android_builder_materializes_pinned_flutter_identity_before_sync(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, projection, replays, digests, trust = android_failure_fixture(tmp_path)
    invocations = (
        SimpleNamespace(
            gradle_root=projection / "quwoquan_app/android",
            tasks=(
                ":app:assembleAlphaDebug",
                ":app:assembleAlphaDebugDebugAndroidTest",
            ),
        ),
    )
    calls: list[tuple[str, object]] = []
    monkeypatch.setattr(
        sync._builder,
        "canonical_android_dependency_bundle_invocations",
        lambda root: (
            invocations
            if root == projection
            else tuple(
                SimpleNamespace(
                    gradle_root=context.repo_root
                    / item.gradle_root.relative_to(projection)
                )
                for item in invocations
            )
        ),
    )

    def materialize(
        project_root: Path,
        gradle_roots: object,
        flutter_identity: object,
    ) -> tuple[object, ...]:
        calls.append(("materialize", flutter_identity))
        assert project_root == projection
        assert gradle_roots == [item.gradle_root for item in invocations]
        assert flutter_identity == context.flutter_identity
        return ()

    def synchronize(**kwargs: object) -> object:
        calls.append(("synchronize", None))
        assert kwargs["invocations"] == invocations
        assert kwargs["verified_seed"] is None
        assert kwargs["seed_wrapper_distribution"] is False
        assert kwargs["invocations"][0].tasks == (
            ":app:assembleAlphaDebug",
            ":app:assembleAlphaDebugDebugAndroidTest",
        )
        return SimpleNamespace(
            snapshot=SimpleNamespace(manifest={}),
            online_results=(),
            offline_results=(),
        )

    monkeypatch.setattr(
        sync._builder, "materialize_pinned_flutter_gradle_wrappers", materialize
    )
    monkeypatch.setattr(
        sync._builder, "synchronize_android_gradle_dependencies", synchronize
    )
    monkeypatch.setattr(
        sync._builder,
        "write_android_gradle_component",
        lambda **_kwargs: context.generation_root / "androidGradle",
    )

    result = sync._builder._build_android_component(
        context=context,
        projection_root=projection,
        pub_replays=replays,
        pub_digests=digests,
        trust_root=trust,
    )

    assert result == context.generation_root / "androidGradle"
    assert calls == [
        ("materialize", context.flutter_identity),
        ("synchronize", None),
    ]
    assert context.progress.current_phase == "gradle-offline-replay"


def test_valid_active_with_current_wrapper_drift_skips_seed_and_runs_fresh_online(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, projection, replays, digests, trust = android_failure_fixture(tmp_path)
    context = replace(
        context, android_gradle_seed_root=tmp_path / "active/androidGradle"
    )
    invocation = SimpleNamespace(
        gradle_root=projection / "quwoquan_app/android",
        tasks=(
            ":app:assembleAlphaDebug",
            ":app:assembleAlphaDebugDebugAndroidTest",
        ),
    )
    monkeypatch.setattr(
        sync._builder,
        "canonical_android_dependency_bundle_invocations",
        lambda _root: (invocation,),
    )
    monkeypatch.setattr(
        sync._builder, "materialize_pinned_flutter_gradle_wrappers", lambda *_args: ()
    )
    verified = SimpleNamespace(manifest={"wrappers": [{"root": "old"}]})
    monkeypatch.setattr(
        sync._builder, "load_android_gradle_component", lambda **_kwargs: verified
    )
    monkeypatch.setattr(
        sync._builder,
        "android_gradle_snapshot_matches_current_wrappers",
        lambda *_args, **_kwargs: False,
    )
    observed: dict[str, object] = {}

    def synchronize(**kwargs: object) -> object:
        observed.update(kwargs)
        return SimpleNamespace(
            snapshot=SimpleNamespace(manifest={}),
            online_results=(),
            offline_results=(),
        )

    monkeypatch.setattr(
        sync._builder, "synchronize_android_gradle_dependencies", synchronize
    )
    monkeypatch.setattr(
        sync._builder,
        "write_android_gradle_component",
        lambda **_kwargs: context.generation_root / "androidGradle",
    )
    sync._builder._build_android_component(
        context=context, projection_root=projection, pub_replays=replays,
        pub_digests=digests, trust_root=trust,
    )
    assert observed["verified_seed"] is verified
    assert observed["seed_wrapper_distribution"] is False
    diagnostic = context.process_root / "android-gradle-seed.log"
    assert diagnostic.stat().st_mode & 0o777 == 0o600
    detail = diagnostic.read_text()
    assert "Maven modules seeded" in detail
    assert "wrapper distribution skipped" in detail
