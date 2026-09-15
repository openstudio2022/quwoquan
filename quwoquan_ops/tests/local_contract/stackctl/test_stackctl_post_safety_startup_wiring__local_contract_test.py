# spec_ref: specs/feature-tree/platform-ops-governance/config-and-reliability-governance/spec.md#req-002
"""Gamma full startup 的 Post safety 前置与重复启动合同。"""
from __future__ import annotations

from pathlib import Path

import pytest
from types import SimpleNamespace

from quwoquan_ops.cli.commands import post_safety_runtime as command
from quwoquan_ops.cli.commands.managed_python import (
    bind_managed_stackctl_python,
    managed_stackctl_python_executable,
)


class _Client:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _Authority:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def verify_authorization(self, expected, evidence) -> None:
        self.calls.append("authorization")

    def account_closure(self, expected, evidence) -> None:
        self.calls.append("account_closure")


class _Evidence:
    def __init__(self, ref: str) -> None:
        self.ref = ref


class _Current:
    ref = "current.json"


def _arrange(monkeypatch, tmp_path: Path, *, current):
    root = (tmp_path / "post-safety" / "generation-1").absolute()
    startup = SimpleNamespace(
        postSafetyCurrent=current,
        runtimeGeneration="generation-1",
        authorization=object(),
        accountClosureAuthority=SimpleNamespace(
            accountClosureEvidence=object(),
            materialRoot=SimpleNamespace(path=str((tmp_path / "account").absolute())),
            subjectHmacKey=SimpleNamespace(secretRef="subject.key"),
        ),
    )
    context = {"postSafetyMaterialRoot": str(root)}
    client, authority = _Client(), _Authority()
    calls: list[str] = []
    dependencies = {
        "create_new_runtime": lambda **kwargs: (
            calls.append("create") or SimpleNamespace(
                postSafetyCurrent=_Current(), runtimeGeneration="generation-1",
                accountClosureAuthority=startup.accountClosureAuthority,
            )
        ),
        "verify_current": lambda **kwargs: calls.append("verify"),
        "read_once": lambda *args: b"current",
        "PostSafetyRuntimeCurrentBinding": SimpleNamespace(
            model_validate_json=lambda raw: SimpleNamespace(fact=_Evidence("fact.json"))
        ),
    }
    factory = SimpleNamespace(
        mongo=lambda ref, database: (client, object()),
        relative_secret=lambda root, ref: b"k" * 32,
    )
    monkeypatch.setattr(command, "_runtime_dependencies", lambda: dependencies)
    monkeypatch.setattr(command, "_connection_factory", lambda target, deps: factory)
    monkeypatch.setattr(
        command,
        "_candidate_context",
        lambda target, deps: (context, object(), object(), {}, startup, b"startup", object()),
    )
    monkeypatch.setattr(command, "_composition", lambda *args: authority)
    monkeypatch.setattr(command, "_database", lambda *args: (client, object()))
    return root, client, authority, calls


def test_gamma_cold_start_creates_after_predecessor_verification(monkeypatch, tmp_path: Path) -> None:
    root, client, authority, calls = _arrange(monkeypatch, tmp_path, current=None)

    projection = command.ensure_post_safety_runtime_for_locked_up("gamma-local")

    assert authority.calls == ["authorization", "account_closure"]
    assert calls == ["create"]
    assert root.is_dir()
    assert projection == {
        "hostMaterialRoot": str(root),
        "containerMaterialRoot": "/run/quwoquan/post-safety",
        "hmacSecretRef": "post-safety.key",
        "recoveryEvidenceRef": "fact.json",
        "currentBindingRef": "current.json",
        "runtimeGeneration": "generation-1",
        "accountSubjectHmacSecret": (b"k" * 32).hex(),
    }
    assert client.closed


def test_gamma_repeat_start_only_verifies_current(monkeypatch, tmp_path: Path) -> None:
    root, client, authority, calls = _arrange(monkeypatch, tmp_path, current=_Current())

    projection = command.ensure_post_safety_runtime_for_locked_up("gamma-local")

    assert authority.calls == []
    assert calls == ["verify"]
    assert not root.exists()
    assert projection["currentBindingRef"] == "current.json"
    assert client.closed


def test_stackctl_preserves_symlinked_managed_venv_python(tmp_path: Path) -> None:
    base_python = tmp_path / "base-python"
    base_python.write_text("#!/bin/sh\nexit 0\n")
    base_python.chmod(0o755)
    venv_bin = tmp_path / "managed-venv" / "bin"
    venv_bin.mkdir(parents=True)
    managed_python = venv_bin / "python"
    managed_python.symlink_to(base_python)

    assert managed_stackctl_python_executable(str(managed_python)) == str(managed_python)


@pytest.mark.parametrize("kind", ["relative", "missing", "non_executable", "unsafe_symlink_target"])
def test_stackctl_rejects_untrusted_managed_python(tmp_path: Path, kind: str) -> None:
    candidate = tmp_path / "python"
    if kind == "relative":
        value = "managed-venv/bin/python"
    elif kind == "missing":
        value = str(candidate)
    elif kind == "non_executable":
        candidate.write_text("#!/bin/sh\n")
        candidate.chmod(0o644)
        value = str(candidate)
    else:
        unsafe_root = tmp_path / "writable-target-root"
        unsafe_root.mkdir()
        target = unsafe_root / "base-python"
        target.write_text("#!/bin/sh\nexit 0\n")
        target.chmod(0o777)
        candidate.symlink_to(target)
        value = str(candidate)

    with pytest.raises(RuntimeError, match="STACKCTL_MANAGED_PYTHON_"):
        managed_stackctl_python_executable(value)


def test_managed_python_binding_overwrites_ambient_spoof(monkeypatch) -> None:
    environment = {"QWQ_STACKCTL_PYTHON": "/ambient/spoof"}
    monkeypatch.setattr(
        "quwoquan_ops.cli.commands.managed_python.managed_stackctl_python_executable",
        lambda: "/managed/venv/bin/python",
    )

    bind_managed_stackctl_python(environment)

    assert environment["QWQ_STACKCTL_PYTHON"] == "/managed/venv/bin/python"


def test_stackctl_up_and_all_down_modes_share_managed_python_binding():
    root=Path(__file__).resolve().parents[4]
    up=(root/"quwoquan_ops/cli/commands/up_runtime.py").read_text()
    down=(root/"quwoquan_ops/cli/commands/down_domain.py").read_text()
    script=(root/"quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh").read_text()
    assert "bind_managed_stackctl_python(env)" in up
    assert down.count("bind_managed_stackctl_python(env)") == 1
    bind_index = down.index("bind_managed_stackctl_python(env)")
    run_index = down.index("runtime_result = _stackctl.run(cmd, env=env)")
    assert bind_index < run_index
    assert 'cmd.append("--purge-rebuildable-state")' in down[:bind_index]
    assert "prepared_attempt_only" in down[:bind_index]
    post=script[script.index("from quwoquan_ops.cli.commands.post_safety_runtime"):]
    prefix=script[:script.index("from quwoquan_ops.cli.commands.post_safety_runtime")]
    assert '"$QWQ_STACKCTL_PYTHON" -B -' in prefix[-300:]
    assert "stackctl-validated managed Python executable" in script
    assert '|| -L "$QWQ_STACKCTL_PYTHON"' not in script


def test_gamma_composition_and_database_share_managed_factory(monkeypatch):
    factory = object()
    dependencies = {
        "ManagedAuthorityConnectionFactory": lambda values=None: factory,
        "ProductionAccountClosureAuthority": lambda **kwargs: kwargs,
    }
    monkeypatch.setattr(
        command, "_gamma_local_managed_connection_values",
        lambda: {"QWQ_CONTENT_MONGO_ADMIN_URI": "mongodb://managed"},
    )
    expected = SimpleNamespace(target="gamma-local")
    startup = SimpleNamespace(
        accountClosureAuthority=SimpleNamespace(
            contentMongo=SimpleNamespace(admin=SimpleNamespace(secretRef="QWQ_CONTENT_MONGO_ADMIN_URI"), database="content"),
        )
    )
    assert command._connection_factory("gamma-local", dependencies) is factory
    composition = command._composition(expected, object(), {}, startup, dependencies, factory)
    assert composition["connection_factory"] is factory


def test_gamma_projection_reuses_deployment_owned_account_subject_key(monkeypatch, tmp_path):
    root, client, authority, calls = _arrange(monkeypatch, tmp_path, current=_Current())
    account_root = (tmp_path / "account").absolute(); account_root.mkdir(mode=0o700)
    key = b"k" * 32
    key_path = account_root / "account-closure-subject.key"; key_path.write_bytes(key); key_path.chmod(0o600)
    startup = SimpleNamespace(
        postSafetyCurrent=_Current(), runtimeGeneration="generation-1", authorization=object(),
        accountClosureAuthority=SimpleNamespace(
            accountClosureEvidence=object(), materialRoot=SimpleNamespace(path=str(account_root)),
            subjectHmacKey=SimpleNamespace(secretRef=key_path.name),
        ),
    )
    monkeypatch.setattr(command, "_candidate_context", lambda target, deps: (
        {"postSafetyMaterialRoot": str(root)}, object(), object(), {}, startup, b"startup", object(),
    ))
    projection = command.ensure_post_safety_runtime_for_locked_up("gamma-local")
    assert projection["accountSubjectHmacSecret"] == key.hex()
