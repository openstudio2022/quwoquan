from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "quwoquan_ops/gate/cleanup_deployment_test_workspace.py"
SPEC = importlib.util.spec_from_file_location("cleanup_deployment_test_workspace", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(MODULE.tempfile, "gettempdir", lambda: str(tmp_path))
    workspace = tmp_path / "quwoquan-deploy.abc123"
    workspace.mkdir()
    return workspace


def test_cleanup_removes_read_only_input_capsule(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    capsule = workspace / "candidate/input-capsule"
    capsule.mkdir(parents=True)
    manifest = capsule / "manifest.json"
    manifest.write_text("{}\n", encoding="utf-8")
    manifest.chmod(0o444)
    capsule.chmod(0o555)

    MODULE.cleanup_deployment_test_workspace(str(workspace))

    assert not workspace.exists()


@pytest.mark.parametrize(
    "unsafe_path",
    [
        ".qwq_output/quwoquan-deploy.abcdef",
        "/tmp/not-a-packaging-workspace",
        "/quwoquan-deploy.abcdef",
    ],
)
def test_cleanup_rejects_paths_outside_exact_temporary_workspace(
    unsafe_path: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(MODULE.tempfile, "gettempdir", lambda: str(tmp_path))
    with pytest.raises(ValueError):
        MODULE.cleanup_deployment_test_workspace(unsafe_path)


def test_cleanup_rejects_symlink_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(MODULE.tempfile, "gettempdir", lambda: str(tmp_path))
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "quwoquan-deploy.abc123"
    link.symlink_to(target, target_is_directory=True)

    with pytest.raises(ValueError, match="must not be a symlink"):
        MODULE.cleanup_deployment_test_workspace(str(link))


def test_cleanup_does_not_follow_internal_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    external = tmp_path / "external"
    external.mkdir()
    marker = external / "marker.txt"
    marker.write_text("preserve\n", encoding="utf-8")
    (workspace / "external-link").symlink_to(external, target_is_directory=True)

    MODULE.cleanup_deployment_test_workspace(str(workspace))

    assert marker.read_text(encoding="utf-8") == "preserve\n"
