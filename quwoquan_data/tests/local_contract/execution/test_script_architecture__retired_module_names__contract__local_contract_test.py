"""The data script gate rejects retired ambiguous orchestration modules."""
from pathlib import Path

from verify import verify_script_architecture


def _minimal_scripts_root(root: Path) -> Path:
    scripts = root / "scripts"
    for relative in (
        "core",
        "content/post/article",
        "content/post/image",
        "content/post/video",
        "content/execution/controller",
        "governance",
        "verify",
    ):
        (scripts / relative).mkdir(parents=True, exist_ok=True)
    (scripts / "cli.py").write_text("", encoding="utf-8")
    (scripts / "__init__.py").write_text("", encoding="utf-8")
    return scripts


def test_script_architecture_rejects_retired_workflow_and_controller_run(
    tmp_path: Path,
    monkeypatch,
) -> None:
    scripts = _minimal_scripts_root(tmp_path)
    retired = (
        scripts / "content/post/video/workflow.py",
        scripts / "content/execution/controller/run.py",
    )
    for path in retired:
        path.write_text("", encoding="utf-8")
    monkeypatch.setattr(verify_script_architecture, "SCRIPTS_ROOT", scripts)
    monkeypatch.setattr(verify_script_architecture, "REPO_ROOT", tmp_path)

    issues = verify_script_architecture.script_architecture_issues()

    assert sum("retired ambiguous module" in issue for issue in issues) == 2


def test_script_architecture_rejects_weak_types_in_control_modules(
    tmp_path: Path,
    monkeypatch,
) -> None:
    scripts = _minimal_scripts_root(tmp_path)
    (scripts / "content/post/video/authoring.py").write_text(
        "from typing import Any, Mapping\n"
        "def author(payload: Mapping[str, Any]) -> None:\n"
        "    return None\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(verify_script_architecture, "SCRIPTS_ROOT", scripts)
    monkeypatch.setattr(verify_script_architecture, "REPO_ROOT", tmp_path)

    issues = verify_script_architecture.script_architecture_issues()

    assert any("strong control module" in issue for issue in issues)


def test_script_architecture_rejects_weak_types_in_release_control_module(
    tmp_path: Path,
    monkeypatch,
) -> None:
    scripts = _minimal_scripts_root(tmp_path)
    release = scripts / "content/release/canonical/release_attestation.py"
    release.parent.mkdir(parents=True, exist_ok=True)
    release.write_text(
        "from typing import Mapping\n"
        "class Receipt:\n"
        "    @classmethod\n"
        "    def from_document(cls, payload: Mapping[str, object]):\n"
        "        return cls()\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(verify_script_architecture, "SCRIPTS_ROOT", scripts)
    monkeypatch.setattr(verify_script_architecture, "REPO_ROOT", tmp_path)

    issues = verify_script_architecture.script_architecture_issues()

    assert any("release_attestation.py is a strong control module" in issue for issue in issues)
