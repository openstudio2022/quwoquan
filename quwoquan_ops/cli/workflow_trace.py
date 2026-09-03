#!/usr/bin/env python3
"""Fail-open runtime workflow trace and file-derived host capability matrix."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = REPO_ROOT / "quwoquan_ops/policies/workflow_trace_contract.yaml"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / ".qwq_output/env/repo/runs/workflow-trace"
SCHEMA_ID = "quwoquan.workflow-trace/v1"
MATRIX_SCHEMA_ID = "quwoquan.workflow-skill-capability-matrix/v1"
ADVISORY_SCHEMA_ID = "quwoquan.workflow-trace-advisory/v1"
REF_RE = re.compile(r"^workflow-trace-v1:sha256:([0-9a-f]{64})$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
ENTRY_KINDS = frozenset({"natural_language", "cursor_command", "skill_explicit", "host_event"})
HOSTS = frozenset({"cursor", "codex", "unknown"})
CAPABILITY_STATUSES = frozenset({"declared", "verified", "unsupported"})
VERIFIABLE_ENTRY_KINDS = frozenset({"cursor_command", "skill_explicit", "host_event"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _ref_for(raw: bytes) -> str:
    return "workflow-trace-v1:" + _digest(raw)


def _advisory(operation: str, code: str, detail: str) -> dict[str, object]:
    return {
        "schema_id": ADVISORY_SCHEMA_ID,
        "schema_version": 1,
        "code": code,
        "operation": operation,
        "detail": detail,
        "retryable": True,
        "blocking": False,
    }


def _result(operation: str, action: Callable[[], dict[str, object]]) -> dict[str, object]:
    try:
        return action()
    except Exception as error:  # noqa: BLE001 -- observational tracing is fail-open
        return _advisory(operation, f"WORKFLOW_TRACE_{operation.upper()}_FAILED", str(error))


def _output_root(override: Path | None) -> Path:
    if override is not None:
        return override
    configured = os.environ.get("QWQ_OUTPUT_ROOT", "").strip()
    if configured:
        return Path(configured) / "env/repo/runs/workflow-trace"
    return DEFAULT_OUTPUT_ROOT


def _objects_dir(root: Path) -> Path:
    return root / "objects/sha256"


def _path_for_ref(root: Path, ref: str) -> Path:
    match = REF_RE.fullmatch(ref)
    if match is None:
        raise ValueError("invalid workflow trace ref")
    return _objects_dir(root) / f"{match.group(1)}.json"


def _ensure_safe_directory(path: Path) -> None:
    current = Path(path.anchor) if path.is_absolute() else Path(".")
    parts = path.absolute().parts[1:]
    for part in parts:
        current /= part
        try:
            info = current.lstat()
        except FileNotFoundError:
            current.mkdir(mode=0o700)
            info = current.lstat()
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
            raise ValueError(f"unsafe trace output directory: {current}")


def _create_once(root: Path, payload: dict[str, object]) -> str:
    raw = _canonical_bytes(payload)
    ref = _ref_for(raw)
    destination = _path_for_ref(root, ref)
    _ensure_safe_directory(destination.parent)
    try:
        descriptor = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except FileExistsError:
        existing = destination.read_bytes()
        if existing != raw:
            raise ValueError("content-addressed trace object collision or tamper")
        return ref
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return ref


def _finish_binding_path(root: Path, start_ref: str) -> Path:
    start_digest = REF_RE.fullmatch(start_ref)
    if start_digest is None:
        raise ValueError("invalid workflow trace start ref")
    return root / "finish-by-start" / f"{start_digest.group(1)}.ref"


def _create_finish_once(
    root: Path, start_ref: str, payload: dict[str, object]
) -> str:
    raw = _canonical_bytes(payload)
    finish_ref = _ref_for(raw)
    binding = _finish_binding_path(root, start_ref)
    lock = root / "locks" / f"{binding.stem}.lock"
    _ensure_safe_directory(binding.parent)
    _ensure_safe_directory(lock.parent)
    try:
        lock.mkdir(mode=0o700)
    except FileExistsError as error:
        raise ValueError("finish creation is already in progress for exact start_ref") from error
    try:
        if binding.exists():
            if binding.is_symlink() or not binding.is_file():
                raise ValueError("finish binding is not a regular file")
            existing = binding.read_bytes()
            if existing != finish_ref.encode("ascii"):
                raise ValueError("finish already exists for exact start_ref")
            existing_trace = _read_exact(root, finish_ref)
            if existing_trace != payload:
                raise ValueError("finish binding payload mismatch")
            return finish_ref
        created_ref = _create_once(root, payload)
        descriptor = os.open(
            binding,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(created_ref.encode("ascii"))
            handle.flush()
            os.fsync(handle.fileno())
        return created_ref
    finally:
        lock.rmdir()


def _validate_finish_binding(root: Path, start_ref: str, finish_ref: str) -> None:
    binding = _finish_binding_path(root, start_ref)
    info = binding.lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise ValueError("finish binding is not a regular file")
    if binding.read_bytes() != finish_ref.encode("ascii"):
        raise ValueError("finish binding does not match exact start_ref")

def _read_exact(root: Path, ref: str) -> dict[str, Any]:
    path = _path_for_ref(root, ref)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise ValueError("trace ref is not a regular file")
    raw = path.read_bytes()
    if _ref_for(raw) != ref:
        raise ValueError("trace ref digest mismatch")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise TypeError("trace object must be a JSON object")
    return value


def _skill_paths(repo_root: Path) -> dict[str, Path]:
    skills_root = repo_root / ".agents/skills"
    inventory = {
        path.parent.name: path
        for path in skills_root.glob("*/SKILL.md")
        if path.is_file() and not path.is_symlink()
    }
    return dict(sorted(inventory.items()))


def _skill_digest(path: Path) -> str:
    return _digest(path.read_bytes())


def _validate_start_input(
    *,
    repo_root: Path,
    entry_kind: str,
    host: str,
    selected_skill: str,
    skill_body_digest: str | None,
    capability_status: str,
    actual_host_sample_ref: str | None,
    explicit_command_evidence_ref: str | None,
) -> str:
    if entry_kind not in ENTRY_KINDS:
        raise ValueError(f"unsupported entry_kind: {entry_kind}")
    if host not in HOSTS:
        raise ValueError(f"unsupported host: {host}")
    if capability_status not in CAPABILITY_STATUSES:
        raise ValueError(f"unsupported capability status: {capability_status}")
    skills = _skill_paths(repo_root)
    path = skills.get(selected_skill)
    if path is None:
        raise ValueError(f"selected_skill is not in current inventory: {selected_skill}")
    current_digest = _skill_digest(path)
    if skill_body_digest is not None:
        if not DIGEST_RE.fullmatch(skill_body_digest):
            raise ValueError("skill_body_digest must be sha256:<64-lowercase-hex>")
        if skill_body_digest != current_digest:
            raise ValueError("skill_body_digest does not match current SKILL.md bytes")
    if capability_status == "verified":
        if entry_kind not in VERIFIABLE_ENTRY_KINDS:
            raise ValueError("natural_language routing cannot be automatically verified")
        if not actual_host_sample_ref:
            raise ValueError("verified requires an actual host sample ref")
        if entry_kind in {"cursor_command", "skill_explicit"} and not explicit_command_evidence_ref:
            raise ValueError("verified explicit entry requires command evidence ref")
    return current_digest


def start_trace(
    *,
    repo_root: Path = REPO_ROOT,
    output_root: Path | None = None,
    entry_kind: str,
    host: str,
    selected_skill: str,
    capability_status: str,
    skill_body_digest: str | None = None,
    owner_identity_ref: str | None = None,
    actual_host_sample_ref: str | None = None,
    explicit_command_evidence_ref: str | None = None,
    started_at: str | None = None,
) -> dict[str, object]:
    root = _output_root(output_root)

    def action() -> dict[str, object]:
        digest = _validate_start_input(
            repo_root=repo_root,
            entry_kind=entry_kind,
            host=host,
            selected_skill=selected_skill,
            skill_body_digest=skill_body_digest,
            capability_status=capability_status,
            actual_host_sample_ref=actual_host_sample_ref,
            explicit_command_evidence_ref=explicit_command_evidence_ref,
        )
        payload: dict[str, object] = {
            "schema_id": SCHEMA_ID,
            "schema_version": 1,
            "phase": "start",
            "entry_kind": entry_kind,
            "host": host,
            "selected_skill": selected_skill,
            "skill_body_digest": digest,
            "owner_identity_ref": owner_identity_ref,
            "capability_status": capability_status,
            "actual_host_sample_ref": actual_host_sample_ref,
            "explicit_command_evidence_ref": explicit_command_evidence_ref,
            "started_at": started_at or _now(),
        }
        ref = _create_once(root, payload)
        return {"status": "recorded", "ref": ref, "trace": payload}

    return _result("start", action)


def finish_trace(
    *,
    output_root: Path | None = None,
    start_ref: str,
    terminal: str,
    capability_status: str,
    candidate_evidence_ref: str | None = None,
    actual_host_sample_ref: str | None = None,
    explicit_command_evidence_ref: str | None = None,
    finished_at: str | None = None,
) -> dict[str, object]:
    root = _output_root(output_root)

    def action() -> dict[str, object]:
        start = _read_exact(root, start_ref)
        if start.get("phase") != "start" or start.get("schema_id") != SCHEMA_ID:
            raise ValueError("start_ref does not reference a start trace")
        if not terminal:
            raise ValueError("terminal must be non-empty")
        if capability_status not in CAPABILITY_STATUSES:
            raise ValueError(f"unsupported capability status: {capability_status}")
        entry_kind = str(start.get("entry_kind"))
        if capability_status == "verified":
            if entry_kind not in VERIFIABLE_ENTRY_KINDS:
                raise ValueError("natural_language routing cannot be automatically verified")
            sample_ref = actual_host_sample_ref or start.get("actual_host_sample_ref")
            command_ref = explicit_command_evidence_ref or start.get("explicit_command_evidence_ref")
            if not sample_ref:
                raise ValueError("verified requires an actual host sample ref")
            if entry_kind in {"cursor_command", "skill_explicit"} and not command_ref:
                raise ValueError("verified explicit entry requires command evidence ref")
        payload: dict[str, object] = {
            "schema_id": SCHEMA_ID,
            "schema_version": 1,
            "phase": "finish",
            "start_ref": start_ref,
            "terminal": terminal,
            "candidate_evidence_ref": candidate_evidence_ref,
            "capability_status": capability_status,
            "actual_host_sample_ref": actual_host_sample_ref,
            "explicit_command_evidence_ref": explicit_command_evidence_ref,
            "finished_at": finished_at or _now(),
        }
        ref = _create_finish_once(root, start_ref, payload)
        return {"status": "recorded", "ref": ref, "trace": payload, "start": start}

    return _result("finish", action)


def readback_trace(*, output_root: Path | None = None, ref: str) -> dict[str, object]:
    root = _output_root(output_root)

    def action() -> dict[str, object]:
        trace = _read_exact(root, ref)
        result: dict[str, object] = {"status": "valid", "ref": ref, "trace": trace}
        if trace.get("phase") == "finish":
            start_ref = trace.get("start_ref")
            if not isinstance(start_ref, str):
                raise ValueError("finish trace has no exact start_ref")
            _validate_finish_binding(root, start_ref, ref)
            result["start"] = _read_exact(root, start_ref)
        return result

    return _result("readback", action)


def _cursor_commands(repo_root: Path, skills: dict[str, Path]) -> dict[str, str]:
    commands: dict[str, str] = {}
    command_root = repo_root / ".cursor/commands"
    for path in sorted(command_root.glob("*.md")):
        if not path.is_file() or path.is_symlink():
            continue
        body = path.read_text(encoding="utf-8")
        matches = re.findall(r"\.agents/skills/([a-z0-9-]+)/SKILL\.md", body)
        if len(matches) == 1 and matches[0] in skills:
            commands[matches[0]] = path.relative_to(repo_root).as_posix()
    return commands


def capability_matrix(*, repo_root: Path = REPO_ROOT, generated_at: str | None = None) -> dict[str, object]:
    skills = _skill_paths(repo_root)
    cursor_commands = _cursor_commands(repo_root, skills)
    skill_inventory = [
        {
            "skill": skill,
            "skill_body_ref": path.relative_to(repo_root).as_posix(),
            "skill_body_digest": _skill_digest(path),
        }
        for skill, path in skills.items()
    ]
    cursor_rows = []
    codex_rows = []
    for skill in skills:
        command_ref = cursor_commands.get(skill)
        cursor_rows.append(
            {
                "skill": skill,
                "explicit_entry_ref": command_ref,
                "explicit_entry_status": "declared" if command_ref else "unsupported",
                "skill_discovery_status": "declared",
                "verified": False,
                "reason": "file_fact_only_no_actual_host_sample",
            }
        )
        codex_rows.append(
            {
                "skill": skill,
                "explicit_entry_ref": None,
                "explicit_entry_status": "unsupported",
                "skill_discovery_status": "declared",
                "verified": False,
                "reason": "no_codex_command_stub_and_no_actual_host_sample",
            }
        )
    return {
        "schema_id": MATRIX_SCHEMA_ID,
        "schema_version": 1,
        "generated_at": generated_at or _now(),
        "source_contract": CONTRACT_PATH.relative_to(repo_root).as_posix(),
        "skill_inventory": skill_inventory,
        "hosts": {"cursor": cursor_rows, "codex": codex_rows},
        "summary": {
            "skill_count": len(skills),
            "cursor_explicit_entry_count": len(cursor_commands),
            "codex_explicit_entry_count": 0,
            "verified_count": 0,
        },
    }


def _print(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--output-root", type=Path)
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start")
    start.add_argument("--entry-kind", choices=sorted(ENTRY_KINDS), required=True)
    start.add_argument("--host", choices=sorted(HOSTS), required=True)
    start.add_argument("--selected-skill", required=True)
    start.add_argument("--skill-body-digest")
    start.add_argument("--owner-identity-ref")
    start.add_argument("--capability-status", choices=sorted(CAPABILITY_STATUSES), required=True)
    start.add_argument("--actual-host-sample-ref")
    start.add_argument("--explicit-command-evidence-ref")

    finish = subparsers.add_parser("finish")
    finish.add_argument("--start-ref", required=True)
    finish.add_argument("--terminal", required=True)
    finish.add_argument("--candidate-evidence-ref")
    finish.add_argument("--capability-status", choices=sorted(CAPABILITY_STATUSES), required=True)
    finish.add_argument("--actual-host-sample-ref")
    finish.add_argument("--explicit-command-evidence-ref")

    readback = subparsers.add_parser("readback")
    readback.add_argument("--ref", required=True)
    subparsers.add_parser("matrix")

    args = parser.parse_args(argv)
    common = {"output_root": args.output_root}
    if args.command == "start":
        result = start_trace(
            repo_root=args.repo_root,
            **common,
            entry_kind=args.entry_kind,
            host=args.host,
            selected_skill=args.selected_skill,
            skill_body_digest=args.skill_body_digest,
            owner_identity_ref=args.owner_identity_ref,
            capability_status=args.capability_status,
            actual_host_sample_ref=args.actual_host_sample_ref,
            explicit_command_evidence_ref=args.explicit_command_evidence_ref,
        )
    elif args.command == "finish":
        result = finish_trace(
            **common,
            start_ref=args.start_ref,
            terminal=args.terminal,
            candidate_evidence_ref=args.candidate_evidence_ref,
            capability_status=args.capability_status,
            actual_host_sample_ref=args.actual_host_sample_ref,
            explicit_command_evidence_ref=args.explicit_command_evidence_ref,
        )
    elif args.command == "readback":
        result = readback_trace(**common, ref=args.ref)
    else:
        result = capability_matrix(repo_root=args.repo_root)
    _print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
