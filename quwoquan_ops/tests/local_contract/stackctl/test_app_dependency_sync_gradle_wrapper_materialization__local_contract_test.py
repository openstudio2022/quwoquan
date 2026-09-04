"""Gradle wrapper materialization contract for app dependency sync."""

# spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-004

from __future__ import annotations

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
        SimpleNamespace(gradle_root=projection / "quwoquan_app/android"),
        SimpleNamespace(
            gradle_root=projection / "quwoquan_app/test_host/patrol/android"
        ),
    )
    calls: list[tuple[str, object]] = []
    monkeypatch.setattr(
        sync._builder,
        "canonical_android_uat_gradle_invocations",
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

    def synchronize(**_kwargs: object) -> object:
        calls.append(("synchronize", None))
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
