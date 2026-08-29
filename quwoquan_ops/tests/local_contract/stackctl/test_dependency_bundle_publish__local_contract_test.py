"""The complete dependency generation becomes active only at the final write."""

# spec_ref: specs/feature-tree/runtime/runtime-config/design.md#dec-003

from __future__ import annotations

import json
from pathlib import Path

import pytest

from quwoquan_ops.cli.lib.package_reuse.dependency_bundle import (
    APP_DEPENDENCY_COMPONENTS,
)
from quwoquan_ops.cli.lib.package_reuse.dependency_bundle_publish import (
    publish_dependency_bundle_activation,
)


def _inputs() -> tuple[dict[str, str], dict[str, dict[str, object]]]:
    source = {
        "flutterVersion": "3.47.0",
        "flutterCommandResolutionDigest": "sha256:" + "a" * 64,
        "productionPubResolutionInputDigest": "sha256:" + "b" * 64,
        "patrolPubResolutionInputDigest": "sha256:" + "c" * 64,
        "nativeResolutionInputDigest": "sha256:" + "d" * 64,
    }
    components = {
        name: {
            "snapshotRef": f"snapshots/{name}",
            "manifestDigest": "sha256:" + "e" * 64,
            "manifestSchema": f"fixture-{name}.v1",
            "treeDigest": "sha256:" + "f" * 64,
            "entryCount": 1,
        }
        for name in APP_DEPENDENCY_COMPONENTS
    }
    return source, components


def _writer(path: Path, value: dict[str, object]) -> None:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def test_receipt_is_written_before_active_pointer(tmp_path: Path) -> None:
    output = tmp_path / "output"
    active_root = output / "env/repo/local/app-dependency-sync/cache"
    source, components = _inputs()
    writes: list[str] = []

    def writer(path: Path, value: dict[str, object]) -> None:
        writes.append(path.name)
        _writer(path, value)

    receipt, active, receipt_path, active_path = publish_dependency_bundle_activation(
        output_root=output,
        active_root=active_root,
        attempt_id="abc123",
        source_identity=source,
        components=components,
        atomic_json=writer,
    )

    assert writes == ["report.json", "active.json"]
    assert receipt["claim"] == "PREPARED_NOT_ACTIVE"
    assert active["attemptId"] == "abc123"
    assert receipt_path.is_file() and active_path.is_file()


def test_receipt_failure_preserves_old_active_pointer(tmp_path: Path) -> None:
    output = tmp_path / "output"
    active_root = output / "env/repo/local/app-dependency-sync/cache"
    active_root.mkdir(parents=True)
    active_path = active_root / "active.json"
    active_path.write_text("old\n", encoding="ascii")
    source, components = _inputs()

    def fail_receipt(path: Path, _value: dict[str, object]) -> None:
        raise OSError(f"unavailable: {path.name}")

    with pytest.raises(OSError, match="report.json"):
        publish_dependency_bundle_activation(
            output_root=output,
            active_root=active_root,
            attempt_id="abc123",
            source_identity=source,
            components=components,
            atomic_json=fail_receipt,
        )
    assert active_path.read_text(encoding="ascii") == "old\n"


def test_incomplete_generation_never_writes_receipt_or_active(tmp_path: Path) -> None:
    output = tmp_path / "output"
    source, components = _inputs()
    components.pop("patrolIosPods")

    with pytest.raises(ValueError, match="component_set_incomplete"):
        publish_dependency_bundle_activation(
            output_root=output,
            active_root=output / "env/repo/local/app-dependency-sync/cache",
            attempt_id="abc123",
            source_identity=source,
            components=components,
            atomic_json=_writer,
        )
    assert not output.exists()
