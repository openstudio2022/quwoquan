#!/usr/bin/env python3
"""Bind and query CiTimingSummary records through the hosted SSH authority."""

from __future__ import annotations

import argparse
import base64
import contextlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
from typing import Any, Iterator

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci import hosted_ci_timing_ledger as authority


ACCESS_MANIFEST = ROOT / "quwoquan_ops/environments/prod/access-isolation.yaml"
HOST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.:-]{0,254}$")
ACCOUNT_RE = re.compile(r"^[a-z][a-z0-9-]{1,62}$")


def _access() -> tuple[str, str, str, str]:
    payload = yaml.safe_load(ACCESS_MANIFEST.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise RuntimeError("Prod access isolation manifest is invalid")
    plane = next(
        (
            item
            for item in payload.get("planes") or []
            if isinstance(item, dict) and item.get("plane") == "service"
        ),
        None,
    )
    if plane is None:
        raise RuntimeError("Prod service plane access is missing")
    host = str(os.environ.get("PROD_SSH_HOST") or "").strip()
    if not host:
        management = payload.get("management") or {}
        host = str(management.get("sshHost") or "").strip()
    account = str(plane.get("account") or "").strip()
    secret_name = str(plane.get("sshKeySecret") or "").strip()
    compose_root = str(plane.get("composeProjectRoot") or "").strip()
    if HOST_RE.fullmatch(host) is None:
        raise RuntimeError("Prod hosted timing authority host is invalid")
    if ACCOUNT_RE.fullmatch(account) is None or not secret_name:
        raise RuntimeError("Prod hosted timing authority account is invalid")
    if not compose_root.startswith("/") or ".." in Path(compose_root).parts:
        raise RuntimeError("Prod hosted timing authority root is invalid")
    return host, account, secret_name, compose_root.rstrip("/") + "/ci-timing-ledger"


@contextlib.contextmanager
def _ssh_key(secret_name: str, account: str) -> Iterator[Path]:
    explicit_path = str(
        os.environ.get(secret_name + "_FILE")
        or os.environ.get(secret_name + "_PATH")
        or ""
    ).strip()
    direct = str(os.environ.get(secret_name) or "").strip()
    if explicit_path:
        path = Path(explicit_path).expanduser()
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"SSH credential file is missing for {secret_name}")
        yield path
        return
    if direct and "\n" not in direct and Path(direct).expanduser().is_file():
        path = Path(direct).expanduser()
        if path.is_symlink():
            raise RuntimeError(f"SSH credential file is unsafe for {secret_name}")
        yield path
        return
    if not direct:
        fallback = Path.home() / ".ssh" / "quwoquan-prod" / account
        if fallback.is_symlink() or not fallback.is_file():
            raise RuntimeError(f"SSH credential is missing for {secret_name}")
        yield fallback
        return
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(direct + "\n")
    try:
        temporary.chmod(0o600)
        yield temporary
    finally:
        temporary.unlink(missing_ok=True)


def _remote_action(
    *, action: str, candidate_digest: str = "", workflow_run_id: str = "", request: str = ""
) -> dict[str, Any]:
    host, account, secret_name, remote_root = _access()
    command = [
        "python3",
        "-",
        "--root",
        remote_root,
        "--action",
        action,
    ]
    if request:
        command.extend(("--request-base64", request))
    if candidate_digest:
        command.extend(("--candidate-digest", candidate_digest))
    if workflow_run_id:
        command.extend(("--workflow-run-id", workflow_run_id))
    remote_command = " ".join(shlex.quote(value) for value in command)
    source = Path(authority.__file__).read_text(encoding="utf-8")
    with _ssh_key(secret_name, account) as key_path:
        try:
            completed = subprocess.run(
                [
                    "ssh",
                    "-i",
                    str(key_path),
                    "-o",
                    "StrictHostKeyChecking=accept-new",
                    "-o",
                    "BatchMode=yes",
                    "-o",
                    "ConnectTimeout=15",
                    "-o",
                    "ServerAliveInterval=10",
                    "-o",
                    "ServerAliveCountMax=3",
                    f"{account}@{host}",
                    remote_command,
                ],
                input=source,
                text=True,
                capture_output=True,
                check=False,
                timeout=60,
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(
                f"hosted timing authority {action} timed out"
            ) from error
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"hosted timing authority {action} failed: {detail}")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("hosted timing authority returned invalid JSON") from error
    if not isinstance(payload, dict):
        raise RuntimeError("hosted timing authority returned an invalid record")
    return payload


def bind_and_readback(
    summary_path: Path, evidence_ref: str, evidence_digest: str
) -> dict[str, Any]:
    summary, raw_summary = authority._read_summary(summary_path)
    expected = authority.build_record(summary, raw_summary, evidence_ref, evidence_digest)
    request = base64.b64encode(
        json.dumps(
            {
                "summaryBase64": base64.b64encode(raw_summary).decode("ascii"),
                "timingEvidenceRef": evidence_ref,
                "timingEvidenceDigest": evidence_digest,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).decode("ascii")
    committed = _remote_action(action="bind", request=request)
    if committed != expected:
        raise RuntimeError("hosted timing authority bind readback does not match request")
    queried = _remote_action(
        action="query",
        candidate_digest=str(summary["candidateDigest"]),
        workflow_run_id=str(summary["workflowRunId"]),
    )
    if queried != expected:
        raise RuntimeError("hosted timing authority query does not match exact OCI binding")
    return queried


def query(candidate_digest: str, workflow_run_id: str) -> dict[str, Any]:
    record = authority.validate_record(
        _remote_action(
            action="query",
            candidate_digest=candidate_digest,
            workflow_run_id=workflow_run_id,
        )
    )
    summary = authority.validate_summary(record.get("timingSummary"))
    authority._validate_exact_oci(
        str(record.get("timingEvidenceRef") or ""),
        str(record.get("timingEvidenceDigest") or ""),
    )
    if (
        summary["candidateDigest"] != candidate_digest
        or str(summary["workflowRunId"]) != workflow_run_id
    ):
        raise RuntimeError("hosted timing query returned a different release identity")
    return record


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    bind_parser = subparsers.add_parser("bind")
    bind_parser.add_argument("--summary", required=True, type=Path)
    bind_parser.add_argument("--timing-evidence-ref", required=True)
    bind_parser.add_argument("--timing-evidence-digest", required=True)
    bind_parser.add_argument("--output", required=True, type=Path)
    query_parser = subparsers.add_parser("query")
    query_parser.add_argument("--candidate-digest", required=True)
    query_parser.add_argument("--workflow-run-id", required=True)
    query_parser.add_argument("--output", required=True, type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.action == "bind":
            result = bind_and_readback(
                args.summary,
                args.timing_evidence_ref,
                args.timing_evidence_digest,
            )
        else:
            result = query(args.candidate_digest, args.workflow_run_id)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"GATE_BLOCK: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
