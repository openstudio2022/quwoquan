"""Objective journal storage security and crash-boundary local contract.

# spec_ref: specs/feature-tree/runtime/development-workflow-governance/objective-execution/spec.md#gwt-001.t1
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/objective-execution/spec.md#gwt-001.t2
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/objective-execution/spec.md#gwt-001.t3
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/objective-execution/spec.md#gwt-001.t4
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/objective-execution/spec.md#gwt-001.t5
"""
from __future__ import annotations

import errno
import inspect
import json
import os
import stat
import subprocess
import signal
import sys
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.usefixtures("isolated_qwq_output_root")

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[4]
if str(ROOT / "quwoquan_ops/cli") not in sys.path:
    sys.path.insert(0, str(ROOT / "quwoquan_ops/cli"))

from lib.objective_execution.contract import ObjectiveExecutionError  # noqa: E402
from lib.objective_execution.journal import (  # noqa: E402
    _append_event_under_lease, _read_events_under_lease, append_event, payload_digest,
    read_events, readback, recover_materialization, writer_lease,
)
from lib.objective_execution.secure_storage import (  # noqa: E402
    StorageError, StorageLease, exclusive_publish_at, replace_regular_at,
)


class SimulatedCrash(RuntimeError):
    pass


def _claims(action: str) -> dict[str, Any]:
    return {
        "receipt_id": "authority-1", "decision_id": "authority-1",
        "decision_unit_id": "unit-1", "actor_id": "actor-1",
        "actor_authenticated": True, "role": "engineering_delivery_owner",
        "scope": {"objective": "objective-1"}, "expires_at": "2026-08-30T00:00:00Z",
        "evidence_fingerprint": "sha256:evidence", "decision_kind": "delivery_authorization",
        "actions": [action], "provider_kind": "test", "provider_version": "test",
        "provider_commit": "sha256:" + "0" * 64, "contract_version": "test",
        "issuer": "test", "receipt_state": "consumed",
        "receipt_previous_generation": 1, "receipt_generation": 2,
        "receipt_etag": '"test-consumed"', "chain_commit": "sha256:" + "1" * 64,
        "winner_idempotency_key": "key-1", "winner_command_digest": "sha256:" + "2" * 64,
    }


def _envelope(action: str = "create_objective") -> dict[str, Any]:
    claims = _claims(action)
    return {
        "schema_version": 2, "subject_kind": "objective", "subject_id": "objective-1",
        "source_state": None, "target_state": "draft", "authority_receipt_ref": "authority:test:1",
        "expected_scope": {"objective": "objective-1"},
        "expected_evidence_fingerprint": "sha256:evidence",
        "expected_decision_kind": "delivery_authorization", "action": action,
        "effect_id": "effect-key-1", "effect_idempotency_key": "key-1",
        "occurred_at": "2026-08-29T12:00:00Z", "payload": {"case": "key-1"},
        "authority_provider_kind": "test", "authority_provider_receipt_ref": "provider:test:1",
        "authority_claims_digest": payload_digest(claims),
        "authority_winner_idempotency_key": claims["winner_idempotency_key"],
        "authority_winner_command_digest": claims["winner_command_digest"],
        "authority_winner_previous_generation": claims["receipt_previous_generation"],
        "authority_winner_generation": claims["receipt_generation"],
        "authority_chain_commit": claims["chain_commit"],
    }


def _command() -> dict[str, Any]:
    envelope = _envelope()
    digest = payload_digest(envelope)
    return {
        "subject_kind": "objective", "subject_id": "objective-1",
        "event_kind": "human_decision_recorded", "reducer_version": 1,
        "action": "create_objective", "from_state": None, "to_state": None,
        "expected_head": "absent", "expected_generation": 0,
        "authority_receipt_ref": "authority:test:1", "effect_idempotency_key": "key-1",
        "command_envelope_digest": digest, "effect_id": "effect-key-1",
        "effect_readback": None, "occurred_at": "2026-08-29T12:00:00Z",
        "payload": {
            "command_envelope": envelope, "command_envelope_digest": digest,
            "authority_claims": _claims("create_objective"),
            "release_evidence_eligible": False, "provider_receipt_ref": "provider:test:1",
        },
    }


def _typed_failure(root: Path) -> str:
    result = readback(root, "objective", "objective-1")
    assert result.status == "failed"
    assert result.terminal in {"OEX.JOURNAL_TAMPERED", "OEX.JOURNAL_FAILED"}
    return str(result.terminal)



def _secure_directory_fd(path: Path) -> int:
    path.mkdir(mode=0o700)
    path.chmod(0o700)
    return os.open(path, os.O_RDONLY | os.O_DIRECTORY)


def test_platform_rename_dispatch_preserves_darwin_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from lib.objective_execution import secure_storage

    calls: list[tuple[int, str, str, int]] = []
    monkeypatch.setattr(secure_storage.sys, "platform", "darwin")
    monkeypatch.setattr(
        secure_storage,
        "_darwin_renameatx_np",
        lambda parent_fd, source, destination, flags: calls.append(
            (parent_fd, source, destination, flags)
        ),
    )

    secure_storage._exclusive_rename_at(17, "source", "destination")
    secure_storage._exchange_rename_at(17, "source", "destination")

    assert calls == [
        (17, "source", "destination", secure_storage._DARWIN_RENAME_EXCL),
        (17, "source", "destination", secure_storage._DARWIN_RENAME_SWAP),
    ]


def test_platform_rename_dispatch_preserves_linux_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from lib.objective_execution import secure_storage

    calls: list[tuple[int, str, str, int]] = []
    monkeypatch.setattr(secure_storage.sys, "platform", "linux")
    monkeypatch.setattr(
        secure_storage,
        "_linux_renameat2",
        lambda parent_fd, source, destination, flags: calls.append(
            (parent_fd, source, destination, flags)
        ),
    )

    secure_storage._exclusive_rename_at(23, "source", "destination")
    secure_storage._exchange_rename_at(23, "source", "destination")

    assert calls == [
        (23, "source", "destination", secure_storage._LINUX_RENAME_NOREPLACE),
        (23, "source", "destination", secure_storage._LINUX_RENAME_EXCHANGE),
    ]


def test_unsupported_platform_rename_is_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from lib.objective_execution import secure_storage

    monkeypatch.setattr(secure_storage.sys, "platform", "win32")
    with pytest.raises(StorageError, match="lacks supported exclusive rename"):
        secure_storage._exclusive_rename_at(31, "source", "destination")
    with pytest.raises(StorageError, match="lacks supported exchange rename"):
        secure_storage._exchange_rename_at(31, "source", "destination")


def test_linux_renameat2_uses_retained_fd_fsencode_and_ctypes_errno(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from lib.objective_execution import secure_storage

    class Renameat2Call:
        argtypes: list[object] = []
        restype: object = None

        def __init__(self) -> None:
            self.calls: list[tuple[object, ...]] = []
            self.result = 0

        def __call__(self, *arguments: object) -> int:
            self.calls.append(arguments)
            return self.result

    renameat2 = Renameat2Call()
    libc = type("Libc", (), {"renameat2": renameat2})()
    monkeypatch.setattr(secure_storage.sys, "platform", "linux")
    monkeypatch.setattr(
        secure_storage.ctypes, "CDLL", lambda *_arguments, **_keywords: libc,
    )

    secure_storage._linux_renameat2(
        37, "源文件", "目标文件", secure_storage._LINUX_RENAME_NOREPLACE,
    )
    assert renameat2.calls == [(
        37, os.fsencode("源文件"), 37, os.fsencode("目标文件"),
        secure_storage._LINUX_RENAME_NOREPLACE,
    )]

    renameat2.result = -1
    monkeypatch.setattr(secure_storage.ctypes, "get_errno", lambda: errno.EEXIST)
    with pytest.raises(FileExistsError):
        secure_storage._linux_renameat2(
            37, "源文件", "目标文件", secure_storage._LINUX_RENAME_NOREPLACE,
        )


def test_linux_unknown_architecture_without_symbol_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from lib.objective_execution import secure_storage

    class LibcWithoutRenameat2:
        syscall = None

    monkeypatch.setattr(secure_storage.sys, "platform", "linux")
    monkeypatch.setattr(secure_storage.platform, "machine", lambda: "mips64")
    monkeypatch.setattr(
        secure_storage.ctypes,
        "CDLL",
        lambda *_arguments, **_keywords: LibcWithoutRenameat2(),
    )
    with pytest.raises(StorageError, match="unavailable for this architecture"):
        secure_storage._linux_renameat2(
            41, "source", "destination", secure_storage._LINUX_RENAME_NOREPLACE,
        )


@pytest.mark.skipif(sys.platform != "linux", reason="requires Linux renameat2")
def test_linux_noreplace_does_not_overwrite_existing_destination(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "linux-noreplace"
    parent_fd = _secure_directory_fd(directory)
    try:
        (directory / "source").write_bytes(b"new")
        (directory / "destination").write_bytes(b"old")
        with pytest.raises(FileExistsError):
            exclusive_publish_at(parent_fd, "source", "destination")
        assert (directory / "source").read_bytes() == b"new"
        assert (directory / "destination").read_bytes() == b"old"
    finally:
        os.close(parent_fd)


@pytest.mark.skipif(sys.platform != "linux", reason="requires Linux renameat2")
def test_linux_exchange_leaves_old_destination_in_staging_before_unlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from lib.objective_execution import secure_storage

    journal = tmp_path / "linux-exchange"
    observed_old_content: list[bytes] = []
    with writer_lease(journal, "objective", "objective-1") as lease:
        original_unlink = secure_storage.os.unlink

        def inspect_then_unlink(name: str, *, dir_fd: int) -> None:
            if name.startswith(".snapshot.json.") and name.endswith(".staging"):
                staging_fd = os.open(name, os.O_RDONLY, dir_fd=dir_fd)
                try:
                    observed_old_content.append(os.read(staging_fd, 64))
                finally:
                    os.close(staging_fd)
            original_unlink(name, dir_fd=dir_fd)

        replace_regular_at(lease, "snapshot.json", b"old")
        monkeypatch.setattr(secure_storage.os, "unlink", inspect_then_unlink)
        replace_regular_at(lease, "snapshot.json", b"new")

    assert observed_old_content == [b"old"]
    assert (journal / "objective/objective-1/snapshot.json").read_bytes() == b"new"
    assert not list((journal / "objective/objective-1").glob(".snapshot.json.*.staging"))


@pytest.mark.skipif(sys.platform != "linux", reason="requires Linux renameat2")
def test_linux_concurrent_noreplace_has_exactly_one_winner(tmp_path: Path) -> None:
    directory = tmp_path / "linux-race"
    directory.mkdir(mode=0o700)
    sources = ["source-left", "source-right"]
    for index, source in enumerate(sources):
        (directory / source).write_bytes(f"winner-{index}".encode("utf-8"))
    script = """
import os, sys
sys.path.insert(0, sys.argv[1])
from lib.objective_execution.secure_storage import exclusive_publish_at
parent_fd = os.open(sys.argv[2], os.O_RDONLY | os.O_DIRECTORY)
try:
    exclusive_publish_at(parent_fd, sys.argv[3], "event.json")
except FileExistsError:
    raise SystemExit(23)
finally:
    os.close(parent_fd)
"""
    processes = [
        subprocess.Popen(
            [sys.executable, "-B", "-c", script,
             str(ROOT / "quwoquan_ops/cli"), str(directory), source],
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        for source in sources
    ]
    returncodes = [process.wait(timeout=5) for process in processes]

    assert sorted(returncodes) == [0, 23]
    assert (directory / "event.json").read_bytes() in {b"winner-0", b"winner-1"}
    assert sum((directory / source).exists() for source in sources) == 1


def test_authoritative_event_publish_source_has_no_overwrite_fallback() -> None:
    from lib.objective_execution import secure_storage

    source = inspect.getsource(secure_storage.publish_staged_event)
    source += inspect.getsource(secure_storage.exclusive_publish_at)
    source += inspect.getsource(secure_storage._exclusive_rename_at)
    assert "replace(" not in source


def test_public_api_has_no_lease_bypass_and_real_lease_conflicts(tmp_path: Path) -> None:
    for function in (append_event, read_events, recover_materialization):
        parameters = inspect.signature(function).parameters
        assert "lease_held" not in parameters
        assert "_lease" not in parameters
    journal = tmp_path / "journal"
    with writer_lease(journal, "objective", "objective-1"):
        with pytest.raises(ObjectiveExecutionError, match="OEX.WRITER_LEASE_CONFLICT"):
            append_event(journal, _command())
        with pytest.raises(ObjectiveExecutionError, match="OEX.WRITER_LEASE_CONFLICT"):
            recover_materialization(journal, "objective", "objective-1")


def test_private_lease_is_root_and_subject_inode_scoped(tmp_path: Path) -> None:
    left, right = tmp_path / "left", tmp_path / "right"
    with writer_lease(left, "objective", "objective-1") as lease:
        assert isinstance(lease, StorageLease)
        command = _command()
        command["subject_id"] = "objective-other"
        with pytest.raises(ObjectiveExecutionError, match="scope mismatch"):
            _append_event_under_lease(lease, command)
    with writer_lease(right, "objective", "objective-1") as other:
        with pytest.raises(ObjectiveExecutionError, match="scope mismatch"):
            _append_event_under_lease(other, {**_command(), "subject_id": "objective-other"})


@pytest.mark.parametrize("component", ["root", "kind", "subject", "events"])
def test_directory_and_broken_symlinks_fail_closed(tmp_path: Path, component: str) -> None:
    journal = tmp_path / component
    real = tmp_path / f"real-{component}"
    real.mkdir(mode=0o700)
    if component == "root":
        journal.symlink_to(real, target_is_directory=True)
    else:
        journal.mkdir(mode=0o700)
        if component == "kind":
            (journal / "objective").symlink_to(real, target_is_directory=True)
        else:
            kind = journal / "objective"; kind.mkdir(mode=0o700)
            if component == "subject":
                (kind / "objective-1").symlink_to(real, target_is_directory=True)
            else:
                subject = kind / "objective-1"; subject.mkdir(mode=0o700)
                (subject / "events").symlink_to(tmp_path / "missing", target_is_directory=True)
    assert _typed_failure(journal)


@pytest.mark.parametrize("node_kind", ["symlink", "fifo", "hardlink"])
def test_writer_lock_unsafe_nodes_fail_closed(tmp_path: Path, node_kind: str) -> None:
    journal = tmp_path / node_kind
    subject = journal / "objective/objective-1"
    events = subject / "events"
    events.mkdir(parents=True, mode=0o700)
    for directory in (journal, journal / "objective", subject, events):
        directory.chmod(0o700)
    lock = subject / "writer.lock"
    if node_kind == "symlink":
        lock.symlink_to(tmp_path / "missing")
    elif node_kind == "fifo":
        os.mkfifo(lock, 0o600)
    else:
        source = tmp_path / "lock-source"; source.write_bytes(b""); source.chmod(0o600)
        os.link(source, lock)
    assert _typed_failure(journal) == "OEX.JOURNAL_TAMPERED"
    with pytest.raises(ObjectiveExecutionError):
        append_event(journal, _command())
    assert not any(events.iterdir())


def test_event_directory_and_event_entry_types_fail_closed(tmp_path: Path) -> None:
    for node_kind in ("symlink", "broken_symlink", "fifo"):
        journal = tmp_path / node_kind
        subject = journal / "objective/objective-1"
        events = subject / "events"
        events.mkdir(parents=True, mode=0o700)
        for directory in (journal, journal / "objective", subject, events):
            directory.chmod(0o700)
        entry = events / "00000000000000000001.json"
        if node_kind == "symlink":
            target = tmp_path / f"{node_kind}-target"; target.write_bytes(b"{}")
            entry.symlink_to(target)
        elif node_kind == "broken_symlink":
            entry.symlink_to(tmp_path / "missing-event")
        else:
            os.mkfifo(entry, 0o600)
        assert _typed_failure(journal) == "OEX.JOURNAL_TAMPERED"


@pytest.mark.parametrize("component", ["root", "kind", "subject", "events"])
def test_every_trusted_directory_rejects_mode_0777(tmp_path: Path, component: str) -> None:
    journal = tmp_path / f"mode-{component}"
    append_event(journal, _command())
    paths = {
        "root": journal,
        "kind": journal / "objective",
        "subject": journal / "objective/objective-1",
        "events": journal / "objective/objective-1/events",
    }
    paths[component].chmod(0o777)
    assert _typed_failure(journal) == "OEX.JOURNAL_TAMPERED"


def test_unsafe_modes_and_hardlinked_event_fail_closed(tmp_path: Path) -> None:
    journal = tmp_path / "modes"
    append_event(journal, _command())
    (journal / "objective").chmod(0o777)
    assert _typed_failure(journal) == "OEX.JOURNAL_TAMPERED"
    (journal / "objective").chmod(0o700)
    event = journal / "objective/objective-1/events/00000000000000000001.json"
    event.chmod(0o644)
    assert _typed_failure(journal) == "OEX.JOURNAL_TAMPERED"
    event.chmod(0o600)
    os.link(event, tmp_path / "event-copy")
    assert _typed_failure(journal) == "OEX.JOURNAL_TAMPERED"


def test_subject_rename_recreate_rejected_without_replacement_write(tmp_path: Path) -> None:
    journal = tmp_path / "rename"
    with writer_lease(journal, "objective", "objective-1") as lease:
        subject = journal / "objective/objective-1"
        moved = journal / "objective/objective-old"
        subject.rename(moved)
        replacement_events = subject / "events"
        replacement_events.mkdir(parents=True, mode=0o700)
        for directory in (subject, replacement_events):
            directory.chmod(0o700)
        with pytest.raises(ObjectiveExecutionError, match="identity"):
            _append_event_under_lease(lease, _command())
        assert list(replacement_events.iterdir()) == []


def test_umask_zero_still_creates_0700_directories_and_0600_files(tmp_path: Path) -> None:
    journal = tmp_path / "umask"
    previous = os.umask(0)
    try:
        append_event(journal, _command())
    finally:
        os.umask(previous)
    subject = journal / "objective/objective-1"
    for directory in (journal, journal / "objective", subject, subject / "events"):
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    for file in (
        subject / "writer.lock", subject / "snapshot.json", subject / "head.json",
        subject / "events/00000000000000000001.json",
    ):
        assert stat.S_IMODE(file.stat().st_mode) == 0o600
        assert file.stat().st_nlink == 1


@pytest.mark.parametrize("failpoint", [
    "after_staging_create", "after_staging_partial_write", "after_staging_fsync",
    "before_event_publish", "after_event_publish_before_directory_fsync",
])
def test_staging_failpoints_never_expose_partial_authority(tmp_path: Path, failpoint: str) -> None:
    journal = tmp_path / failpoint
    trigger = lambda name: (_ for _ in ()).throw(SimulatedCrash(name)) if name == failpoint else None
    with pytest.raises(SimulatedCrash, match=failpoint):
        append_event(journal, _command(), failpoint=trigger)
    events = journal / "objective/objective-1/events"
    finals = list(events.glob("[0-9]*.json"))
    assert len(finals) in {0, 1}
    if finals:
        payload = json.loads(finals[0].read_text(encoding="utf-8"))
        assert payload["event_digest"] and payload["generation"] == 1
        assert readback(journal, "objective", "objective-1").terminal == "OEX.JOURNAL_RECOVERY_REQUIRED"
    else:
        assert readback(journal, "objective", "objective-1").status == "absent"
    recover_materialization(journal, "objective", "objective-1")
    assert not list(events.glob(".event.*.staging"))



def test_created_directory_syscall_order_fsyncs_parent_then_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from lib.objective_execution import secure_storage

    observed: list[str] = []
    actual = secure_storage._fsync

    def record(fd: int, label: str) -> None:
        observed.append(label)
        actual(fd, label)

    monkeypatch.setattr(secure_storage, "_fsync", record)
    append_event(tmp_path / "ordering" / "nested" / "journal", _command())
    created_pairs: list[tuple[str, str]] = []
    for index, label in enumerate(observed):
        if label.endswith(" parent") and index + 1 < len(observed):
            created_pairs.append((label, observed[index + 1]))
    assert len(created_pairs) >= 6
    assert all(child == parent.removesuffix(" parent") for parent, child in created_pairs)
    for expected in (
        "subject kind directory", "subject directory", "events directory",
    ):
        assert (f"{expected} parent", expected) in created_pairs


@pytest.mark.parametrize(
    ("failpoint", "expected_final_count", "expected_status", "expected_terminal"),
    [
        ("after_staging_partial_write", 0, "absent", None),
        (
            "after_event_publish_before_directory_fsync", 1, "failed",
            "OEX.JOURNAL_RECOVERY_REQUIRED",
        ),
    ],
)
def test_sigkill_subprocess_only_exposes_old_or_complete_new_chain(
    tmp_path: Path, failpoint: str, expected_final_count: int,
    expected_status: str, expected_terminal: str | None,
) -> None:
    journal = tmp_path / failpoint
    script = """
import json, os, signal, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from lib.objective_execution.journal import append_event
root = Path(sys.argv[2])
command = json.loads(sys.argv[3])
failpoint = sys.argv[4]
def kill(name):
    if name == failpoint:
        os.kill(os.getpid(), signal.SIGKILL)
append_event(root, command, failpoint=kill)
"""
    completed = subprocess.run(
        [sys.executable, "-B", "-c", script, str(ROOT / "quwoquan_ops/cli"),
         str(journal), json.dumps(_command()), failpoint],
        check=False, timeout=5, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert completed.returncode == -signal.SIGKILL
    events = journal / "objective/objective-1/events"
    finals = list(events.glob("[0-9]*.json"))
    assert len(finals) == expected_final_count
    for event in finals:
        document = json.loads(event.read_text(encoding="utf-8"))
        assert document["event_digest"] and document["generation"] == 1
    observed = readback(journal, "objective", "objective-1")
    assert observed.status == expected_status and observed.terminal == expected_terminal
    recover_materialization(journal, "objective", "objective-1")
    assert not list(events.glob(".event.*.staging"))
