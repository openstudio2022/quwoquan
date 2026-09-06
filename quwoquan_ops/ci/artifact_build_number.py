#!/usr/bin/env python3
"""Append-only hosted allocator contract for mobile artifact build numbers."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_REQUEST = re.compile(r"^sha256:[0-9a-f]{64}$")


class ArtifactBuildNumberError(ValueError):
    pass


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def digest(value: Mapping[str, Any] | Path) -> str:
    raw = value.read_bytes() if isinstance(value, Path) else _canonical(value)
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _write_once(path: Path, payload: Mapping[str, Any]) -> Path:
    data = _canonical(payload) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        fd = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except FileExistsError as exc:
        if path.is_symlink() or path.read_bytes() != data:
            raise ArtifactBuildNumberError("BUILD_NUMBER.CREATE_CONFLICT") from exc
        return path
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    return path


def _safe_path(root: Path, ref: str, field: str) -> Path:
    relative = PurePosixPath(ref)
    if (
        relative.is_absolute()
        or relative.as_posix() != ref
        or "\\" in ref
        or any(part in {"", ".", "..", "latest", "current"} for part in relative.parts)
    ):
        raise ArtifactBuildNumberError(f"BUILD_NUMBER.INVALID_{field}")
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ArtifactBuildNumberError(f"BUILD_NUMBER.INVALID_{field}")
    return current


def _load(
    root: Path, exact: Mapping[str, str] | None
) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    if exact is None:
        return None, None
    if set(exact) != {"ref", "digest"} or _DIGEST.fullmatch(
        str(exact.get("digest"))
    ) is None:
        raise ArtifactBuildNumberError("BUILD_NUMBER.INVALID_PREDECESSOR")
    ref = str(exact["ref"])
    path = _safe_path(root, ref, "PREDECESSOR")
    if not path.is_file() or digest(path) != exact["digest"]:
        raise ArtifactBuildNumberError("BUILD_NUMBER.STALE_PREDECESSOR")
    value = json.loads(path.read_bytes())
    if (
        not isinstance(value, dict)
        or value.get("schema")
        != "quwoquan_ops.artifact_build_number_allocation.v1"
    ):
        raise ArtifactBuildNumberError("BUILD_NUMBER.INVALID_PREDECESSOR")
    return value, dict(exact)


def _request(root: Path, exact: Mapping[str, str]) -> tuple[dict[str, Any], dict[str, str]]:
    if set(exact) != {"ref", "digest"} or _DIGEST.fullmatch(
        str(exact.get("digest"))
    ) is None:
        raise ArtifactBuildNumberError("BUILD_NUMBER.INVALID_REQUEST")
    ref = str(exact["ref"])
    path = _safe_path(root, ref, "REQUEST")
    if not path.is_file() or digest(path) != exact["digest"]:
        raise ArtifactBuildNumberError("BUILD_NUMBER.STALE_REQUEST")
    value = json.loads(path.read_bytes())
    request_id = value.get("requestId") if isinstance(value, dict) else None
    if (
        not isinstance(value, dict)
        or value.get("schema") != "quwoquan_ops.release_qualification_request.v1"
        or not isinstance(request_id, str)
        or _REQUEST.fullmatch(request_id) is None
    ):
        raise ArtifactBuildNumberError("BUILD_NUMBER.INVALID_REQUEST")
    return value, dict(exact)


def allocate(
    *,
    root: Path,
    request_id: str,
    predecessor_ref: Mapping[str, str] | None,
    allocated_at: str,
    request_ref: Mapping[str, str] | None = None,
) -> Path:
    """Allocate with create-once compare-and-swap over one hosted store."""

    root = root.resolve()
    predecessor, predecessor_exact = _load(root, predecessor_ref)
    request_exact = None
    if request_ref is not None:
        request, request_exact = _request(root, request_ref)
        if request.get("requestId") != request_id:
            raise ArtifactBuildNumberError("BUILD_NUMBER.REQUEST_DRIFT")
    if not request_id or request_id != request_id.strip():
        raise ArtifactBuildNumberError("BUILD_NUMBER.INVALID_REQUEST")
    number = 1 if predecessor is None else predecessor.get("artifactBuildNumber", 0) + 1
    if type(number) is not int or number < 1:
        raise ArtifactBuildNumberError("BUILD_NUMBER.INVALID_PREDECESSOR")

    directory = root / "build-number" / "allocations"
    observed: list[tuple[Path, dict[str, Any]]] = []
    for candidate in sorted(directory.glob("*.json")) if directory.exists() else []:
        if candidate.is_symlink() or not candidate.is_file():
            raise ArtifactBuildNumberError("BUILD_NUMBER.STORE_INVALID")
        item = json.loads(candidate.read_bytes())
        if not isinstance(item, dict):
            raise ArtifactBuildNumberError("BUILD_NUMBER.STORE_INVALID")
        observed.append((candidate, item))
        if item.get("requestId") == request_id:
            if (
                item.get("artifactBuildNumber") != number
                or item.get("qualificationRequest") != request_exact
            ):
                raise ArtifactBuildNumberError("BUILD_NUMBER.REQUEST_REUSED")
            return candidate
        if item.get("artifactBuildNumber") == number:
            raise ArtifactBuildNumberError("BUILD_NUMBER.CAS_CONFLICT")

    latest_exact = None
    if observed:
        latest_path, latest = max(
            observed,
            key=lambda pair: int(pair[1].get("artifactBuildNumber", 0)),
        )
        latest_exact = {
            "ref": latest_path.relative_to(root).as_posix(),
            "digest": digest(latest_path),
        }
    if latest_exact != predecessor_exact:
        raise ArtifactBuildNumberError("BUILD_NUMBER.CAS_CONFLICT")

    body: dict[str, Any] = {
        "schema": "quwoquan_ops.artifact_build_number_allocation.v1",
        "requestId": request_id,
        "qualificationRequest": request_exact,
        "artifactBuildNumber": number,
        "predecessor": predecessor_exact,
        "allocatedAt": allocated_at,
    }
    body["allocationId"] = digest(body)
    return _write_once(
        directory / f"{number:020d}-{body['allocationId']}.json", body
    )


def allocate_hosted_sequence(
    *,
    root: Path,
    request_ref: Mapping[str, str],
    hosted_run_number: int,
    hosted_run_id: str,
) -> Path:
    """Bind GitHub's repository-hosted monotonic workflow counter once."""

    root = root.resolve()
    request, request_exact = _request(root, request_ref)
    if type(hosted_run_number) is not int or hosted_run_number < 1:
        raise ArtifactBuildNumberError("BUILD_NUMBER.INVALID_HOSTED_SEQUENCE")
    if not hosted_run_id or hosted_run_id != hosted_run_id.strip():
        raise ArtifactBuildNumberError("BUILD_NUMBER.INVALID_HOSTED_SEQUENCE")
    request_id = str(request["requestId"])
    body: dict[str, Any] = {
        "schema": "quwoquan_ops.artifact_build_number_allocation.v1",
        "requestId": request_id,
        "qualificationRequest": request_exact,
        "artifactBuildNumber": hosted_run_number,
        "predecessor": None,
        "hostedAuthority": {
            "provider": "github_actions_workflow_run_number",
            "runId": hosted_run_id,
            "runNumber": hosted_run_number,
        },
    }
    body["allocationId"] = digest(body)
    directory = root / "build-number" / "allocations"
    if directory.exists():
        for candidate in sorted(directory.glob("*.json")):
            item = json.loads(candidate.read_bytes())
            if item.get("requestId") == request_id:
                if item != body:
                    raise ArtifactBuildNumberError("BUILD_NUMBER.REQUEST_REUSED")
                return candidate
            if item.get("artifactBuildNumber") == hosted_run_number:
                raise ArtifactBuildNumberError("BUILD_NUMBER.CAS_CONFLICT")
    return _write_once(
        directory / f"{hosted_run_number:020d}-{body['allocationId']}.json", body
    )


def _exact(value: str, field: str) -> dict[str, str]:
    try:
        ref, exact_digest = value.split("=", 1)
    except ValueError as exc:
        raise ArtifactBuildNumberError(
            f"BUILD_NUMBER.INVALID_{field.upper()}"
        ) from exc
    return {"ref": ref, "digest": exact_digest}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store-root", required=True, type=Path)
    parser.add_argument("--request", required=True, help="exact ref=digest")
    parser.add_argument("--predecessor", help="exact ref=digest")
    parser.add_argument("--allocated-at")
    parser.add_argument("--hosted-run-number", type=int)
    parser.add_argument("--hosted-run-id")
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args(argv)
    try:
        request_exact = _exact(args.request, "request")
        request, _ = _request(args.store_root.resolve(), request_exact)
        if args.hosted_run_number is not None or args.hosted_run_id is not None:
            if args.hosted_run_number is None or not args.hosted_run_id or args.predecessor or args.allocated_at:
                raise ArtifactBuildNumberError("BUILD_NUMBER.INVALID_HOSTED_SEQUENCE")
            path = allocate_hosted_sequence(
                root=args.store_root,
                request_ref=request_exact,
                hosted_run_number=args.hosted_run_number,
                hosted_run_id=args.hosted_run_id,
            )
        else:
            if not args.allocated_at:
                raise ArtifactBuildNumberError("BUILD_NUMBER.ALLOCATED_AT_REQUIRED")
            path = allocate(
                root=args.store_root,
                request_id=str(request["requestId"]),
                request_ref=request_exact,
                predecessor_ref=(
                    _exact(args.predecessor, "predecessor")
                    if args.predecessor
                    else None
                ),
                allocated_at=args.allocated_at,
            )
        payload = json.loads(path.read_text(encoding="utf-8"))
        result = {
            "ref": path.relative_to(args.store_root.resolve()).as_posix(),
            "digest": digest(path),
            "artifactBuildNumber": payload["artifactBuildNumber"],
        }
        if args.github_output:
            args.github_output.write_text(
                f"allocation_ref={result['ref']}\n"
                f"allocation_digest={result['digest']}\n"
                f"artifact_build_number={result['artifactBuildNumber']}\n",
                encoding="utf-8",
            )
    except (ArtifactBuildNumberError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"terminal": "GATE_BLOCK", "detail": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
