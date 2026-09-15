# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-051
from __future__ import annotations

import argparse
import importlib.util
import os
import plistlib
import stat
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
MODULE_PATH = ROOT / "quwoquan_ops/cli/grok_bot_instances.py"
spec = importlib.util.spec_from_file_location("grok_bot_instances", MODULE_PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _app(tmp_path: Path) -> Path:
    app = tmp_path / "Grok Bot.app"
    (app / "Contents/MacOS").mkdir(parents=True)
    (app / "Contents/Resources").mkdir(parents=True)
    with (app / "Contents/Info.plist").open("wb") as handle:
        plistlib.dump({"CFBundleIdentifier": "com.anysphere.sand", "CFBundleShortVersionString": "0.test"}, handle)
    executable = app / "Contents/MacOS/Grok Bot"
    executable.write_text("#!/bin/sh\nsleep 30\n", encoding="utf-8")
    executable.chmod(0o755)
    (app / "Contents/Resources/app.asar").write_bytes(b"test-asar")
    return app


def _args(tmp_path: Path, app: Path) -> argparse.Namespace:
    volume = tmp_path / "volume"; volume.mkdir()
    return argparse.Namespace(
        instance_id="account-a", app=str(app), state_root=str(tmp_path / "state"),
        profile_root=str(tmp_path / "profile-a"), data_root=str(tmp_path / "data-a"),
        output_root=str(volume / "output-a"), workspace_root=str(volume / "workspace-a"),
        library_root=str(volume / "library-a"), carried_media_root=str(volume / "golden-a"),
        volume_root=str(volume), expected_volume_uuid="UUID-A",
        publish_root=str(volume / "publish"), coordination_db=str(volume / "coordination.sqlite"),
    )


def test_prepare_is_secret_free_disjoint_and_create_or_same(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "_volume_uuid", lambda _path: "UUID-A")
    args = _args(tmp_path, _app(tmp_path))
    first = module.prepare(args)
    assert first["status"] == "created"
    assert module.prepare(args)["status"] == "replayed"
    document = __import__("json").loads(Path(first["manifest"]).read_text())
    assert set(document) == {"schema", "instanceId", "appIdentity", "paths", "volume", "publishRoot", "coordinationDb", "lifecycle"}
    assert not ({"token", "cookie", "secret", "credential", "accountIdentityRef"} & set(document))
    assert stat.S_IMODE(Path(args.profile_root).stat().st_mode) == 0o700


def test_prepare_rejects_path_overlap_symlink_and_volume_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "_volume_uuid", lambda _path: "UUID-A")
    args = _args(tmp_path, _app(tmp_path))
    args.workspace_root = str(Path(args.output_root) / "child")
    with pytest.raises(module.InstanceError, match="PATH_OVERLAP"):
        module.prepare(args)
    args = _args(tmp_path / "second", _app(tmp_path / "second"))
    Path(args.profile_root).parent.mkdir(parents=True, exist_ok=True)
    Path(args.profile_root).symlink_to(Path(args.data_root), target_is_directory=True)
    with pytest.raises(module.InstanceError, match="SYMLINK_FORBIDDEN"):
        module.prepare(args)
    args = _args(tmp_path / "third", _app(tmp_path / "third")); args.expected_volume_uuid = "OTHER"
    with pytest.raises(module.InstanceError, match="VOLUME_UUID_MISMATCH"):
        module.prepare(args)


def test_start_inspect_stop_only_manifest_bound_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "_volume_uuid", lambda _path: "UUID-A")
    args = _args(tmp_path, _app(tmp_path)); module.prepare(args)
    start_args = argparse.Namespace(state_root=args.state_root, instance_id=args.instance_id)
    started = module.start(start_args)
    try:
        viewed = module.inspect(start_args)
        assert viewed["state"] == "running" and viewed["pid"] == started["pid"]
        assert set(viewed) == {"schema", "instanceId", "state", "pid", "profileRoot", "dataRoot", "appIdentity", "singletonLockPresent", "signedIn"}
    finally:
        stopped = module.stop(argparse.Namespace(**vars(start_args), timeout=5.0))
    assert stopped["status"] == "stopped"
    assert module.inspect(start_args)["signedIn"] is None
    assert module.stop(argparse.Namespace(**vars(start_args), timeout=0.1))["status"] == "already-stopped"


def test_version_change_requires_revalidation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "_volume_uuid", lambda _path: "UUID-A")
    args = _args(tmp_path, _app(tmp_path)); module.prepare(args)
    (Path(args.app) / "Contents/Resources/app.asar").write_bytes(b"changed")
    with pytest.raises(module.InstanceError, match="PROFILE_REVALIDATION_REQUIRED"):
        module.start(argparse.Namespace(state_root=args.state_root, instance_id=args.instance_id))


def test_exact_stop_captures_descendants_before_parent_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    signals: list[int] = []
    monkeypatch.setattr(module, "_descendants", lambda _pid: {102, 103})
    alive = {101, 102, 103}
    monkeypatch.setattr(module, "_pid_command", lambda pid: "process" if pid in alive else None)
    def terminate(pid: int, _signal: int) -> None:
        signals.append(pid); alive.discard(pid)
    monkeypatch.setattr(module.os, "kill", terminate)
    module._terminate_exact_process_tree({}, 101, 0.1)
    assert signals == [103, 102, 101]
