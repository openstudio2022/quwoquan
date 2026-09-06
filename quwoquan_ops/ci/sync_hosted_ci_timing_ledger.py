#!/usr/bin/env python3
"""Append/query promotion timing evidence through the hosted SSH authority."""
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

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci import hosted_ci_timing_ledger as authority
from quwoquan_ops.ci import promotion_timing_ratchet as ratchet

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
    return host, account, secret_name, compose_root.rstrip("/") + "/promotion-timing-ledger"


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
    *,
    action: str,
    candidate_digest: str = "",
    workflow_run_id: str = "",
    observation_id: str = "",
    event_id: str = "",
    start_at: str = "",
    end_at: str = "",
    request: str = "",
) -> dict[str, Any]:
    host, account, secret_name, remote_root = _access()
    command = ["python3", "-", "--root", remote_root, "--action", action]
    for option, value in (
        ("--request-base64", request),
        ("--candidate-digest", candidate_digest),
        ("--workflow-run-id", workflow_run_id),
        ("--observation-id", observation_id),
        ("--event-id", event_id),
        ("--start-at", start_at),
        ("--end-at", end_at),
    ):
        if value:
            command.extend((option, value))
    remote_command = " ".join(shlex.quote(value) for value in command)
    authority_source = Path(authority.__file__).read_text(encoding="utf-8")
    ratchet_source = Path(ratchet.__file__).read_bytes()
    embedded = base64.b64encode(ratchet_source).decode("ascii")
    import_line = "from quwoquan_ops.ci import promotion_timing_ratchet as ratchet"
    bootstrap = (
        "import base64 as _ratchet_base64, types as _ratchet_types\n"
        "ratchet = _ratchet_types.ModuleType('promotion_timing_ratchet')\n"
        "ratchet.__file__ = '<embedded-promotion-timing-ratchet>'\n"
        f"exec(compile(_ratchet_base64.b64decode({embedded!r}), ratchet.__file__, 'exec'), ratchet.__dict__)"
    )
    if authority_source.count(import_line) != 1:
        raise RuntimeError("hosted timing authority embedding anchor drifted")
    source = authority_source.replace(import_line, bootstrap, 1)
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
            raise RuntimeError(f"hosted timing authority {action} timed out") from error
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


def _bind_request(
    record_kind: str, raw_payload: bytes, evidence_ref: str, evidence_digest: str
) -> str:
    request = {
        "recordKind": record_kind,
        "payloadBase64": base64.b64encode(raw_payload).decode("ascii"),
        "evidenceRef": evidence_ref,
        "evidenceDigest": evidence_digest,
    }
    return base64.b64encode(
        json.dumps(
            request, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
    ).decode("ascii")


def bind_sample_and_readback(
    sample_path: Path, evidence_ref: str, evidence_digest: str
) -> dict[str, Any]:
    sample, raw_sample = authority._read_sample(sample_path)
    expected = authority.build_sample_record(
        sample, raw_sample, evidence_ref, evidence_digest
    )
    committed = _remote_action(
        action="bind",
        request=_bind_request(
            "promotion_sample", raw_sample, evidence_ref, evidence_digest
        ),
    )
    if committed != expected:
        raise RuntimeError("hosted timing authority sample bind readback does not match request")
    queried = _remote_action(
        action="query-sample", observation_id=str(sample["observationId"])
    )
    if queried != expected:
        raise RuntimeError("hosted timing authority sample query does not match exact OCI binding")
    return queried


def bind_and_readback(
    summary_path: Path, evidence_ref: str, evidence_digest: str
) -> dict[str, Any]:
    """Archive a generic diagnostic summary; it is never ratchet authority."""
    summary, raw_summary = authority._read_summary(summary_path)
    expected = authority.build_record(summary, raw_summary, evidence_ref, evidence_digest)
    committed = _remote_action(
        action="bind",
        request=_bind_request(
            "diagnostic_summary", raw_summary, evidence_ref, evidence_digest
        ),
    )
    if committed != expected:
        raise RuntimeError("hosted timing diagnostic bind readback does not match request")
    queried = _remote_action(
        action="query",
        candidate_digest=str(summary["candidateDigest"]),
        workflow_run_id=str(summary["workflowRunId"]),
    )
    if queried != expected:
        raise RuntimeError("hosted timing diagnostic query does not match exact OCI binding")
    return queried


def query(candidate_digest: str, workflow_run_id: str) -> dict[str, Any]:
    record = authority.validate_record(
        _remote_action(
            action="query",
            candidate_digest=candidate_digest,
            workflow_run_id=workflow_run_id,
        )
    )
    if record["recordKind"] != "diagnostic_summary":
        raise RuntimeError("hosted timing query returned a non-diagnostic record")
    payload = authority.validate_summary(record.get("payload"))
    if (
        payload["candidateDigest"] != candidate_digest
        or str(payload["workflowRunId"]) != workflow_run_id
    ):
        raise RuntimeError("hosted timing query returned a different diagnostic identity")
    return record


def query_sample(observation_id: str) -> dict[str, Any]:
    record = authority.validate_record(
        _remote_action(action="query-sample", observation_id=observation_id)
    )
    if record["recordKind"] != "promotion_sample" or record["observationId"] != observation_id:
        raise RuntimeError("hosted timing query returned a different sample identity")
    return record


def query_event(event_id: str) -> dict[str, Any]:
    payload = _remote_action(action="query-event", event_id=event_id)
    if payload.get("authority") != authority.AUTHORITY or payload.get("eventId") != event_id:
        raise RuntimeError("hosted timing event query returned a different identity")
    records = payload.get("records")
    if not isinstance(records, list):
        raise RuntimeError("hosted timing event query returned invalid records")
    for record in records:
        validated = authority.validate_record(record)
        if validated.get("eventId") != event_id:
            raise RuntimeError("hosted timing event query returned a foreign sample")
    return payload


def query_range(start_at: str, end_at: str) -> dict[str, Any]:
    payload = _remote_action(action="query-range", start_at=start_at, end_at=end_at)
    if payload.get("authority") != authority.AUTHORITY:
        raise RuntimeError("hosted timing range query returned a foreign authority")
    samples = payload.get("samples")
    if not isinstance(samples, list):
        raise RuntimeError("hosted timing range query returned invalid samples")
    for sample in samples:
        authority.validate_promotion_sample(sample)
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)

    bind_sample = subparsers.add_parser("append-sample")
    bind_sample.add_argument("--sample", required=True, type=Path)
    bind_sample.add_argument("--evidence-ref", required=True)
    bind_sample.add_argument("--evidence-digest", required=True)
    bind_sample.add_argument("--output", required=True, type=Path)

    bind_diagnostic = subparsers.add_parser("archive-diagnostic")
    bind_diagnostic.add_argument("--summary", required=True, type=Path)
    bind_diagnostic.add_argument("--evidence-ref", required=True)
    bind_diagnostic.add_argument("--evidence-digest", required=True)
    bind_diagnostic.add_argument("--output", required=True, type=Path)

    query_sample_parser = subparsers.add_parser("query-sample")
    query_sample_parser.add_argument("--observation-id", required=True)
    query_sample_parser.add_argument("--output", required=True, type=Path)

    query_event_parser = subparsers.add_parser("query-event")
    query_event_parser.add_argument("--event-id", required=True)
    query_event_parser.add_argument("--output", required=True, type=Path)

    query_range_parser = subparsers.add_parser("query-range")
    query_range_parser.add_argument("--start-at", required=True)
    query_range_parser.add_argument("--end-at", required=True)
    query_range_parser.add_argument("--output", required=True, type=Path)

    diagnostic_query = subparsers.add_parser("query-diagnostic")
    diagnostic_query.add_argument("--candidate-digest", required=True)
    diagnostic_query.add_argument("--workflow-run-id", required=True)
    diagnostic_query.add_argument("--output", required=True, type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.action == "append-sample":
            result = bind_sample_and_readback(
                args.sample, args.evidence_ref, args.evidence_digest
            )
        elif args.action == "archive-diagnostic":
            result = bind_and_readback(
                args.summary, args.evidence_ref, args.evidence_digest
            )
        elif args.action == "query-sample":
            result = query_sample(args.observation_id)
        elif args.action == "query-event":
            result = query_event(args.event_id)
        elif args.action == "query-range":
            result = query_range(args.start_at, args.end_at)
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
