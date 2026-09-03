"""Public CLI adapters for AI-authored source plans and one-source I/O."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.paths import execution_root
from core.schema import assert_valid
from content.execution.identity import parse_execution_id, validate_execution_id
from content.source.atomic_source_io import materialize_source_candidate

_PLAN_DIRECTORY = ("sources", "plans")
_TARGET_SET_REF = ("0.plan", "target_set.json")


def _canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            dict(payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _open_directory_path(path: Path) -> int:
    absolute = Path(os.path.abspath(path.expanduser()))
    flags = (
        os.O_RDONLY
        | os.O_DIRECTORY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(absolute.parts[0], flags)
    try:
        for part in absolute.parts[1:]:
            next_descriptor = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _open_child_directory(parent_fd: int, name: str) -> int:
    return os.open(
        name,
        os.O_RDONLY
        | os.O_DIRECTORY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0),
        dir_fd=parent_fd,
    )


def _read_regular_at(parent_fd: int, name: str) -> bytes:
    descriptor = os.open(
        name,
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
        dir_fd=parent_fd,
    )
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError(f"must be one regular file: {name}")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
    finally:
        os.close(descriptor)


def _read_json_path(path: Path, *, label: str) -> dict[str, Any]:
    absolute = Path(os.path.abspath(path.expanduser()))
    parent_fd = _open_directory_path(absolute.parent)
    try:
        raw = _read_regular_at(parent_fd, absolute.name)
    finally:
        os.close(parent_fd)
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} must be valid JSON") from exc
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be an object")
    return value


def _load_target_set(root_fd: int) -> dict[str, Any]:
    plan_fd = _open_child_directory(root_fd, _TARGET_SET_REF[0])
    try:
        raw = _read_regular_at(plan_fd, _TARGET_SET_REF[1])
    finally:
        os.close(plan_fd)
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("0.plan/target_set.json must be valid JSON") from exc
    if not isinstance(value, dict):
        raise TypeError("0.plan/target_set.json must be an object")
    assert_valid(value, "execution", "target_set", label="write-source-plan target_set")
    return value


def _ensure_child_directory(parent_fd: int, name: str) -> int:
    try:
        os.mkdir(name, mode=0o755, dir_fd=parent_fd)
        os.fsync(parent_fd)
    except FileExistsError:
        pass
    return _open_child_directory(parent_fd, name)


def _write_all(descriptor: int, body: bytes) -> None:
    remaining = memoryview(body)
    while remaining:
        written = os.write(descriptor, remaining)
        if written <= 0:
            raise OSError("source plan write made no progress")
        remaining = remaining[written:]


def _create_once_json_at(parent_fd: int, name: str, payload: Mapping[str, Any]) -> None:
    body = _canonical_bytes(payload)
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(name, flags, 0o644, dir_fd=parent_fd)
    except FileExistsError:
        if _read_regular_at(parent_fd, name) != body:
            ref = "/".join((*_PLAN_DIRECTORY, name))
            raise ValueError(f"create-once collision: {ref}") from None
        return
    try:
        _write_all(descriptor, body)
        os.fsync(descriptor)
    except BaseException:
        os.close(descriptor)
        try:
            os.unlink(name, dir_fd=parent_fd)
            os.fsync(parent_fd)
        except OSError:
            pass
        raise
    else:
        os.close(descriptor)
    os.fsync(parent_fd)


def _plan_ref(target_ref: str) -> str:
    digest = hashlib.sha256(target_ref.encode("utf-8")).hexdigest()
    return f"{'/'.join(_PLAN_DIRECTORY)}/{digest}.json"


def _write_source_plan(plan: Mapping[str, Any]) -> str:
    execution_id = validate_execution_id(str(plan["executionId"]))
    root_fd = _open_directory_path(execution_root(execution_id))
    try:
        target_set = _load_target_set(root_fd)
        expected_carrier = parse_execution_id(execution_id).content_type.value
        if target_set.get("executionId") != execution_id:
            raise ValueError("target_set executionId does not match the execution root")
        if target_set.get("carrier") != expected_carrier:
            raise ValueError("target_set carrier does not match executionId")
        if plan.get("executionId") != target_set.get("executionId"):
            raise ValueError("source plan executionId does not match target_set")
        if plan.get("carrier") != target_set.get("carrier"):
            raise ValueError("source plan carrier does not match target_set")
        target_ref = str(plan.get("targetRef") or "")
        if target_ref not in target_set.get("targetRefs", []):
            raise ValueError("source plan targetRef is not declared by target_set")

        sources_fd = _ensure_child_directory(root_fd, _PLAN_DIRECTORY[0])
        try:
            plans_fd = _ensure_child_directory(sources_fd, _PLAN_DIRECTORY[1])
            try:
                ref = _plan_ref(target_ref)
                _create_once_json_at(plans_fd, Path(ref).name, plan)
            finally:
                os.close(plans_fd)
        finally:
            os.close(sources_fd)
    finally:
        os.close(root_fd)
    return ref


def handle_write_source_plan(args: argparse.Namespace) -> None:
    try:
        path = Path(args.input)
        plan = _read_json_path(path, label="source plan")
        assert_valid(plan, "source", "source_plan", label=str(path))
        ref = _write_source_plan(plan)
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise SystemExit(f"[task write-source-plan] GATE_BLOCK {exc}") from exc
    print(json.dumps({"sourcePlanRef": ref}, ensure_ascii=False))


def handle_materialize_source(args: argparse.Namespace) -> None:
    try:
        meta, unit = materialize_source_candidate(
            Path(args.candidate),
            execution_id=args.execution_id,
            target_ref=args.target_ref,
            manual_root=Path(args.manual_root) if args.manual_root else None,
            receipt_path=Path(args.acquisition_receipt) if args.acquisition_receipt else None,
            receipt_asset_id=str(args.receipt_asset_id or ""),
            acquisition_root=Path(args.acquisition_root) if args.acquisition_root else None,
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise SystemExit(f"[task materialize-source] GATE_BLOCK {exc}") from exc
    print(
        json.dumps(
            {
                **meta,
                "sourceUnitRef": unit.relative_to(
                    execution_root(args.execution_id)
                ).as_posix(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def register_atomic_source_parsers(sub: argparse._SubParsersAction) -> None:
    plan = sub.add_parser(
        "write-source-plan",
        help="create-once 写一个 AI 提交的 per-target source plan",
    )
    plan.add_argument("--input", required=True)
    plan.set_defaults(handler=handle_write_source_plan)
    source = sub.add_parser(
        "materialize-source",
        help="物化一个显式 source candidate 并绑定一个 target",
    )
    source.add_argument("--candidate", required=True)
    source.add_argument("--execution-id", required=True)
    source.add_argument("--target-ref", required=True)
    source.add_argument("--manual-root")
    source.add_argument("--acquisition-receipt")
    source.add_argument("--receipt-asset-id")
    source.add_argument("--acquisition-root")
    source.set_defaults(handler=handle_materialize_source)


__all__ = ["register_atomic_source_parsers"]
