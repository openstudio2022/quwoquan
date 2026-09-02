"""GWT-034 canonical verify-all receipt writer contract."""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

DATA_ROOT = next(
    parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data"
)
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from core import paths  # noqa: E402
from verify import handler as verify_handler  # noqa: E402
from verify import verify_all_receipt as subject  # noqa: E402


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _output_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    local = tmp_path / ".qwq_output/data/local"
    monkeypatch.setattr(paths, "DATA_LOCAL_ROOT", local)
    return local / "runs"


def _invoke(
    output: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    *,
    run: object,
) -> tuple[BaseException | None, str, str]:
    monkeypatch.setattr(verify_handler, "handle_all", run)
    error: BaseException | None = None
    try:
        verify_handler.handle_verify(
            type("Args", (), {"verify_command": "all", "verify_all_output": str(output)})()
        )
    except BaseException as exc:  # test the CLI SystemExit boundary.
        error = exc
    captured = capfd.readouterr()
    return error, captured.out, captured.err


def test_verify_all_receipt_success_is_schema_bound_idempotent_and_visible(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    runs = _output_root(tmp_path, monkeypatch)
    output = runs / "verify-all/pass.json"
    fingerprint = "sha256:" + "a" * 64
    monkeypatch.setattr(subject, "operational_fingerprint", lambda **_kwargs: fingerprint)

    def passing() -> list[str]:
        print("visible stdout")
        print("visible stderr", file=sys.stderr)
        return ["gate-b", "gate-a"]

    error, stdout, stderr = _invoke(output, monkeypatch, capfd, run=passing)
    assert error is None
    assert "visible stdout" in stdout
    assert "visible stderr" in stderr
    first = output.read_bytes()
    receipt = json.loads(first)
    schema = json.loads(
        (DATA_ROOT / "schema/execution/verify_all_receipt.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(receipt)
    assert receipt["sourceFingerprint"] == fingerprint
    assert receipt["command"] == {
        "commandId": "data.verify.all",
        "entrypoint": "quwoquan_data/scripts/cli.py",
        "arguments": ["verify", "all"],
    }
    assert receipt["closedModules"] == ["gate-b", "gate-a"]
    assert receipt["capturedOutput"] == {
        "stdoutDigest": _sha256(b"visible stdout\n"),
        "stderrDigest": _sha256(b"visible stderr\n"),
    }

    error, replay_stdout, replay_stderr = _invoke(
        output, monkeypatch, capfd, run=passing
    )
    assert error is None
    assert "visible stdout" in replay_stdout
    assert "visible stderr" in replay_stderr
    assert output.read_bytes() == first


def test_verify_all_help_exposes_only_optional_output() -> None:
    import argparse

    parser = argparse.ArgumentParser(prog="qwq-data")
    subparsers = parser.add_subparsers(dest="command", required=True)
    verify_handler.register_parser(subparsers)
    args = parser.parse_args(["verify", "all", "--output", "receipt.json"])
    assert args.verify_command == "all"
    assert args.verify_all_output == "receipt.json"


def test_verify_all_failure_writes_no_passing_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    output = _output_root(tmp_path, monkeypatch) / "verify-all/fail.json"
    monkeypatch.setattr(
        subject, "operational_fingerprint", lambda **_kwargs: "sha256:" + "b" * 64
    )

    def failing() -> list[str]:
        print("failed gate output")
        raise SystemExit("gate failed")

    error, stdout, _stderr = _invoke(output, monkeypatch, capfd, run=failing)
    assert isinstance(error, SystemExit)
    assert str(error) == "gate failed"
    assert "failed gate output" in stdout
    assert not output.exists()


def test_verify_all_receipt_collision_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    output = _output_root(tmp_path, monkeypatch) / "verify-all/collision.json"
    output.parent.mkdir(parents=True)
    output.write_text("different bytes\n", encoding="utf-8")
    monkeypatch.setattr(
        subject, "operational_fingerprint", lambda **_kwargs: "sha256:" + "c" * 64
    )

    error, stdout, _stderr = _invoke(
        output, monkeypatch, capfd, run=lambda: (print("still visible"), ["gate"])[1]
    )
    assert isinstance(error, SystemExit)
    assert "DATA.VERIFY_ALL.RECEIPT_WRITE_FAILED" in str(error)
    assert "create-once collision" in str(error)
    assert "still visible" in stdout
    assert output.read_text(encoding="utf-8") == "different bytes\n"


def test_verify_all_receipt_rejects_unsafe_and_symlink_paths_before_gates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    runs = _output_root(tmp_path, monkeypatch)
    invoked = False

    def must_not_run() -> list[str]:
        nonlocal invoked
        invoked = True
        return ["gate"]

    unsafe = tmp_path / "outside.json"
    error, _stdout, _stderr = _invoke(unsafe, monkeypatch, capfd, run=must_not_run)
    assert isinstance(error, SystemExit)
    assert "must be under local run evidence root" in str(error)
    assert invoked is False and not unsafe.exists()

    real = runs / "real"
    real.mkdir(parents=True)
    linked = runs / "linked"
    linked.symlink_to(real, target_is_directory=True)
    error, _stdout, _stderr = _invoke(
        linked / "receipt.json", monkeypatch, capfd, run=must_not_run
    )
    assert isinstance(error, SystemExit)
    assert "symbolic link" in str(error)
    assert invoked is False and not (real / "receipt.json").exists()
