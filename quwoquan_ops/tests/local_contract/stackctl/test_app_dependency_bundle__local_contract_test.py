"""All build/test dependency closures switch as one active generation."""

# spec_ref: specs/feature-tree/runtime/runtime-config/design.md#dec-003

from __future__ import annotations

import json
from pathlib import Path

import pytest

from quwoquan_ops.cli.lib.package_reuse import dependency_bundle as bundle
from quwoquan_ops.cli.lib.package_reuse.pub_cache_capsule import (
    _canonical_bytes,
    _digest_bytes,
)


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_bytes(value))


def _fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, dict[str, object]]:
    output = tmp_path / "output"
    root = output / "env/repo/local/app-dependency-sync/cache"
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(output))
    identity = {
        "flutterVersion": "3.47.0",
        "flutterCommandResolutionDigest": "sha256:" + "1" * 64,
        "productionPubResolutionInputDigest": "sha256:" + "2" * 64,
        "patrolPubResolutionInputDigest": "sha256:" + "3" * 64,
        "nativeResolutionInputDigest": "sha256:" + "4" * 64,
    }
    monkeypatch.setattr(bundle, "_current_source_identity", lambda _root: identity)
    components: dict[str, object] = {}
    for index, name in enumerate(bundle.APP_DEPENDENCY_COMPONENTS):
        manifest: dict[str, object] = {
            "schema": f"fixture-{name}.v1",
            "treeDigest": "sha256:" + str(index + 5) * 64,
            "entryCount": index + 1,
        }
        relative = Path("snapshots") / "abc" / name
        _write_json(root / relative / "manifest.json", manifest)
        components[name] = bundle.component_declaration(
            snapshot_ref=relative,
            manifest=manifest,
        )
    receipt_ref = Path("env/repo/runs/app-dependency-sync/abc/report.json")
    receipt = {
        "schema": bundle.APP_DEPENDENCY_BUNDLE_RECEIPT_SCHEMA,
        "claim": "PREPARED_NOT_ACTIVE",
        "attemptId": "abc",
        "components": components,
        "activationEvidence": {
            "requiredActiveRef": "env/repo/local/app-dependency-sync/cache/active.json",
            "requiredAttemptId": "abc",
        },
    }
    _write_json(output / receipt_ref, receipt)
    active = {
        "schema": bundle.APP_DEPENDENCY_BUNDLE_ACTIVE_SCHEMA,
        "attemptId": "abc",
        **identity,
        "components": components,
        "receiptRef": receipt_ref.as_posix(),
        "receiptDigest": _digest_bytes(_canonical_bytes(receipt)),
    }
    _write_json(root / "active.json", active)
    return repo, root, active


def test_active_bundle_selects_all_five_components_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, _root, active = _fixture(tmp_path, monkeypatch)

    loaded = bundle.load_active_dependency_bundle(repo_root=repo)

    assert loaded.active == active
    assert [name for name, _path in loaded.component_roots] == list(
        bundle.APP_DEPENDENCY_COMPONENTS
    )


def test_active_bundle_rejects_cross_generation_component(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, root, active = _fixture(tmp_path, monkeypatch)
    declaration = dict(active["components"]["androidGradle"])
    declaration["snapshotRef"] = "snapshots/other/androidGradle"
    active["components"]["androidGradle"] = declaration
    source_manifest = root / "snapshots/abc/androidGradle/manifest.json"
    foreign_manifest = root / "snapshots/other/androidGradle/manifest.json"
    foreign_manifest.parent.mkdir(parents=True)
    foreign_manifest.write_bytes(source_manifest.read_bytes())
    receipt = Path(tmp_path / "output" / active["receiptRef"])
    receipt_payload = json.loads(receipt.read_text(encoding="utf-8"))
    receipt_payload["components"] = active["components"]
    _write_json(receipt, receipt_payload)
    active["receiptDigest"] = _digest_bytes(_canonical_bytes(receipt_payload))
    _write_json(root / "active.json", active)

    with pytest.raises(ValueError, match="not bound to active attempt"):
        bundle.load_active_dependency_bundle(repo_root=repo)


def test_active_bundle_rejects_component_manifest_tamper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, root, _active = _fixture(tmp_path, monkeypatch)
    path = root / "snapshots/abc/productionIosPods/manifest.json"
    path.write_text('{"schema":"tampered","treeDigest":"sha256:x","entryCount":1}')

    with pytest.raises(ValueError, match="manifest digest"):
        bundle.load_active_dependency_bundle(repo_root=repo)


def test_active_bundle_rejects_source_or_toolchain_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, _root, _active = _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(
        bundle,
        "_current_source_identity",
        lambda _root: {
            "flutterVersion": "3.47.1",
            "flutterCommandResolutionDigest": "sha256:" + "1" * 64,
            "productionPubResolutionInputDigest": "sha256:" + "2" * 64,
            "patrolPubResolutionInputDigest": "sha256:" + "3" * 64,
            "nativeResolutionInputDigest": "sha256:" + "4" * 64,
        },
    )

    with pytest.raises(ValueError, match="stale for flutterVersion"):
        bundle.load_active_dependency_bundle(repo_root=repo)


@pytest.mark.parametrize("field", bundle.APP_DEPENDENCY_BUNDLE_STALE_FIELDS)
def test_stale_identity_field_raises_typed_bundle_stale_error(
    field: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, _root, _active = _fixture(tmp_path, monkeypatch)
    drifted = {
        "flutterVersion": "3.47.0",
        "flutterCommandResolutionDigest": "sha256:" + "1" * 64,
        "productionPubResolutionInputDigest": "sha256:" + "2" * 64,
        "patrolPubResolutionInputDigest": "sha256:" + "3" * 64,
        "nativeResolutionInputDigest": "sha256:" + "4" * 64,
    }
    drifted[field] = (
        "3.99.9" if field == "flutterVersion" else "sha256:" + "f" * 64
    )
    monkeypatch.setattr(bundle, "_current_source_identity", lambda _root: drifted)

    with pytest.raises(bundle.AppDependencyBundleStaleError) as excinfo:
        bundle.load_active_dependency_bundle(repo_root=repo)

    error = excinfo.value
    assert isinstance(error, ValueError)
    assert error.code == "APP.DEPENDENCY.bundle_stale"
    assert error.field == field
    assert str(error) == f"App dependency bundle is stale for {field}"


def test_stale_error_rejects_unknown_identity_field() -> None:
    with pytest.raises(ValueError, match="stale field is unknown"):
        bundle.AppDependencyBundleStaleError("receiptDigest")


def test_missing_active_pointer_is_not_classified_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, root, _active = _fixture(tmp_path, monkeypatch)
    (root / "active.json").unlink()

    with pytest.raises(ValueError) as excinfo:
        bundle.load_active_dependency_bundle(repo_root=repo)

    assert not isinstance(excinfo.value, bundle.AppDependencyBundleStaleError)
    assert "is stale for" not in str(excinfo.value)


def test_corrupt_active_pointer_is_not_classified_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, root, _active = _fixture(tmp_path, monkeypatch)
    (root / "active.json").write_text("{not json", encoding="utf-8")

    with pytest.raises(ValueError) as excinfo:
        bundle.load_active_dependency_bundle(repo_root=repo)

    assert not isinstance(excinfo.value, bundle.AppDependencyBundleStaleError)
    assert "is stale for" not in str(excinfo.value)


def test_receipt_drift_is_not_classified_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, _root, active = _fixture(tmp_path, monkeypatch)
    receipt = Path(tmp_path / "output" / active["receiptRef"])
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    payload["attemptId"] = "def"
    _write_json(receipt, payload)

    with pytest.raises(ValueError) as excinfo:
        bundle.load_active_dependency_bundle(repo_root=repo)

    assert not isinstance(excinfo.value, bundle.AppDependencyBundleStaleError)


def test_active_bundle_rejects_receipt_rebinding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, _root, active = _fixture(tmp_path, monkeypatch)
    receipt = Path(tmp_path / "output" / active["receiptRef"])
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    payload["attemptId"] = "def"
    _write_json(receipt, payload)

    with pytest.raises(ValueError, match="receipt binding"):
        bundle.load_active_dependency_bundle(repo_root=repo)


def test_active_bundle_rejects_unsafe_component_ref(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, root, active = _fixture(tmp_path, monkeypatch)
    declaration = dict(active["components"]["productionPub"])
    declaration["snapshotRef"] = "../outside"
    active["components"]["productionPub"] = declaration
    _write_json(root / "active.json", active)

    with pytest.raises(ValueError, match="snapshotRef is unsafe"):
        bundle.load_active_dependency_bundle(repo_root=repo)
