#!/usr/bin/env python3
"""Canonical local CLI for Environment Ops scheduler execution facts."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.environment_scheduler import (  # noqa: E402
    EnvironmentSchedulerError,
    append_task_state,
    canonical_json_bytes,
    create_execution_request,
    exact_file_digest,
    issue_environment_acceptance_fact,
    load_execution_request,
    request_exact_ref,
    select_next_request,
    supersede_request,
)
from quwoquan_ops.ci.integration_qualification import (  # noqa: E402
    IntegrationQualificationError,
    issue_integration_qualification,
)
from quwoquan_ops.cli.lib.evidence_signing import (  # noqa: E402
    DEFAULT_KEYRING_PATH,
    EvidenceSigningError,
    assert_distinct_active_keys,
    ed25519_environment_verifier,
    ed25519_signer,
    key_root,
    load_keyring,
)

_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class EnvironmentExecutionError(ValueError):
    """Stable typed CLI-boundary failure."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _parser_error(message: str) -> None:
    raise EnvironmentExecutionError("ENVIRONMENT_EXECUTION.INVALID_ARGUMENT", message)


class _Parser(argparse.ArgumentParser):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("add_help", False)
        super().__init__(*args, **kwargs)

    def error(self, message: str) -> None:
        _parser_error(message)


def _exact(value: str) -> dict[str, str]:
    try:
        ref, digest = value.rsplit("=", 1)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "exact ref must be ref=sha256:<digest>"
        ) from exc
    posix = PurePosixPath(ref)
    if (
        not ref
        or posix.is_absolute()
        or posix.as_posix() != ref
        or any(part in {"", ".", ".."} for part in posix.parts)
        or "\\" in ref
        or ref.endswith("/latest")
        or "/latest/" in ref
        or posix.name.startswith("latest.")
    ):
        raise argparse.ArgumentTypeError("exact ref must be immutable and relative")
    if _DIGEST_RE.fullmatch(digest) is None:
        raise argparse.ArgumentTypeError(
            "exact digest must be sha256:<64 lowercase hex>"
        )
    return {"ref": ref, "digest": digest}


def _boolean(value: str) -> bool:
    if value == "true":
        return True
    if value == "false":
        return False
    raise argparse.ArgumentTypeError("boolean must be true or false")


def _add_exact(parser: argparse.ArgumentParser, flag: str, **kwargs: Any) -> None:
    parser.add_argument(flag, type=_exact, **kwargs)


def _build_parser() -> argparse.ArgumentParser:
    parser = _Parser(description=__doc__)
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--store-root", required=True, type=Path)
    commands = parser.add_subparsers(
        dest="command", required=True, parser_class=_Parser
    )

    request = commands.add_parser("request")
    _add_exact(request, "--candidate", required=True)
    request.add_argument(
        "--environment", required=True, choices=("alpha", "beta", "gamma")
    )
    request.add_argument("--impact-plan-digest", required=True)
    request.add_argument("--priority", required=True, type=int)
    request.add_argument("--created-at")
    request.add_argument("--expected-dev-head")
    request.add_argument("--expected-dev-tree")

    next_request = commands.add_parser("next")
    _add_exact(next_request, "--request", required=True, action="append")

    transition = commands.add_parser("transition")
    _add_exact(transition, "--request", required=True)
    transition.add_argument(
        "--state",
        required=True,
        choices=(
            "queued",
            "mutation_started",
            "cancelled",
            "safe_teardown_required",
            "acceptance_issued",
        ),
    )
    transition.add_argument("--occurred-at")
    transition.add_argument("--reason")
    _add_exact(transition, "--acceptance")

    supersede = commands.add_parser("supersede")
    _add_exact(supersede, "--request", required=True, action="append")
    supersede.add_argument("--expected-dev-head", required=True)
    supersede.add_argument("--expected-dev-tree", required=True)
    supersede.add_argument("--reason", required=True)
    supersede.add_argument("--occurred-at")

    issue = commands.add_parser("issue")
    _add_exact(issue, "--request", required=True)
    issue.add_argument("--profile", required=True)
    issue.add_argument("--status", required=True, choices=("passed", "not_required"))
    _add_exact(issue, "--case-result", required=True, action="append")
    for flag in (
        "runtime-identity",
        "data-lifecycle",
        "provider-readiness",
        "observability-readiness",
        "inspect-evidence",
        "doctor-evidence",
        "cleanup-evidence",
        "lease-closure-evidence",
    ):
        _add_exact(issue, f"--{flag}", required=True)
    _add_exact(issue, "--predecessor")
    issue.add_argument("--signer-identity", required=True)
    # 私钥来自仓外 QWQ_EVIDENCE_SIGNING_KEY_ROOT，公钥必须已登记在 keyring；无 secret env。
    issue.add_argument("--signing-keyring", type=Path, default=DEFAULT_KEYRING_PATH)
    issue.add_argument("--expires-at", required=True)
    issue.add_argument("--non-promotable", required=True, type=_boolean)
    issue.add_argument("--reason-code")
    issue.add_argument("--issued-at")

    qualify = commands.add_parser("qualify")
    _add_exact(qualify, "--publish-result", required=True)
    _add_exact(qualify, "--gamma-acceptance", required=True)
    qualify.add_argument("--expected-dev-head", required=True)
    qualify.add_argument("--expected-dev-tree", required=True)
    qualify.add_argument("--qualification-signer-identity", required=True)
    qualify.add_argument("--signing-keyring", type=Path, default=DEFAULT_KEYRING_PATH)
    for environment in ("alpha", "beta", "gamma"):
        qualify.add_argument(f"--expected-{environment}-signer-identity", required=True)
    qualify.add_argument("--issued-at", required=True)
    qualify.add_argument("--expires-at", required=True)
    return parser


def _git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repository,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise EnvironmentExecutionError(
            "ENVIRONMENT_EXECUTION.GIT_UNAVAILABLE",
            " ".join(completed.stderr.split()) or "git command failed",
        )
    return completed.stdout.strip()


def _current_dev_identity(
    repository: Path,
    *,
    dev_ref: str = "refs/heads/dev1.0",
) -> dict[str, str]:
    head = _git(repository, "rev-parse", dev_ref)
    tree = _git(repository, "show", "-s", "--format=%T", head)
    return {"ref": dev_ref, "head": head, "tree": tree}


def _assert_expected_dev(
    repository: Path,
    *,
    expected_head: str | None,
    expected_tree: str | None,
    dev_ref: str = "refs/heads/dev1.0",
) -> dict[str, str]:
    if (expected_head is None) != (expected_tree is None):
        raise EnvironmentExecutionError(
            "ENVIRONMENT_EXECUTION.INVALID_ARGUMENT",
            "expected dev head and tree must be provided together",
        )
    current = _current_dev_identity(repository, dev_ref=dev_ref)
    if expected_head is not None and (
        expected_head != current["head"] or expected_tree != current["tree"]
    ):
        raise EnvironmentExecutionError(
            "ENVIRONMENT_EXECUTION.DEV_HEAD_DRIFT",
            "expected dev identity differs from current refs/heads/dev1.0",
        )
    return current


def _exact_path(store_root: Path, exact: Mapping[str, str]) -> Path:
    expanded = store_root.expanduser()
    if expanded.is_symlink():
        raise EnvironmentExecutionError(
            "ENVIRONMENT_EXECUTION.UNSAFE_REF", "store root must not be a symlink"
        )
    root = expanded.resolve()
    current = root
    for part in PurePosixPath(exact["ref"]).parts:
        current = current / part
        if current.is_symlink():
            raise EnvironmentExecutionError(
                "ENVIRONMENT_EXECUTION.UNSAFE_REF",
                "exact ref must not traverse a symlink",
            )
    try:
        current.resolve().relative_to(root)
    except ValueError as exc:
        raise EnvironmentExecutionError(
            "ENVIRONMENT_EXECUTION.UNSAFE_REF", "exact ref leaves the store root"
        ) from exc
    return current


def _result_ref(store_root: Path, path: Path) -> dict[str, str]:
    expanded = store_root.expanduser()
    if expanded.is_symlink():
        raise EnvironmentExecutionError(
            "ENVIRONMENT_EXECUTION.UNSAFE_RESULT", "store root must not be a symlink"
        )
    root = expanded.resolve()
    resolved = path.resolve()
    try:
        ref = resolved.relative_to(root).as_posix()
    except ValueError as exc:
        raise EnvironmentExecutionError(
            "ENVIRONMENT_EXECUTION.UNSAFE_RESULT",
            "scheduler result leaves the explicit store root",
        ) from exc
    return {"ref": ref, "digest": exact_file_digest(resolved)}


def _candidate_identity(
    store_root: Path, request: Mapping[str, object]
) -> dict[str, str]:
    binding = request.get("candidate")
    if not isinstance(binding, Mapping):
        raise EnvironmentExecutionError(
            "ENVIRONMENT_EXECUTION.INVALID_REQUEST",
            "request candidate binding is missing",
        )
    return {key: str(binding[key]) for key in ("candidateId", "commit", "tree")}


def _load_json_exact(store_root: Path, exact: Mapping[str, str]) -> dict[str, Any]:
    path = _exact_path(store_root, exact)
    if not path.is_file() or path.is_symlink():
        raise EnvironmentExecutionError(
            "ENVIRONMENT_EXECUTION.MISSING",
            "exact ref does not identify a regular file",
        )
    if exact_file_digest(path) != exact["digest"]:
        raise EnvironmentExecutionError(
            "ENVIRONMENT_EXECUTION.STALE", "exact ref bytes drifted"
        )
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EnvironmentExecutionError(
            "ENVIRONMENT_EXECUTION.INVALID_JSON", "exact ref is not readable JSON"
        ) from exc
    if not isinstance(value, dict) or raw != canonical_json_bytes(value) + b"\n":
        raise EnvironmentExecutionError(
            "ENVIRONMENT_EXECUTION.NON_CANONICAL", "exact ref is not canonical JSON"
        )
    return value


def _signer(identity: str, *, keyring_path: Path, unavailable_code: str):
    try:
        return ed25519_signer(identity, root=key_root(), keyring=load_keyring(keyring_path))
    except EvidenceSigningError as exc:
        raise EnvironmentExecutionError(unavailable_code, exc.detail) from exc


def _handle_request(args: argparse.Namespace) -> dict[str, object]:
    if args.environment == "gamma":
        if args.expected_dev_head is None or args.expected_dev_tree is None:
            raise EnvironmentExecutionError(
                "ENVIRONMENT_EXECUTION.INVALID_ARGUMENT",
                "Gamma request requires explicit expected dev head and tree",
            )
        current = _assert_expected_dev(
            args.repository,
            expected_head=args.expected_dev_head,
            expected_tree=args.expected_dev_tree,
        )
        candidate = _load_json_exact(args.store_root, args.candidate)
        if (
            candidate.get("commit") != current["head"]
            or candidate.get("tree") != current["tree"]
        ):
            raise EnvironmentExecutionError(
                "ENVIRONMENT_EXECUTION.GAMMA_IDENTITY_DRIFT",
                "Gamma candidate is not current exact dev1.0 identity",
            )
    elif args.expected_dev_head is not None or args.expected_dev_tree is not None:
        raise EnvironmentExecutionError(
            "ENVIRONMENT_EXECUTION.INVALID_ARGUMENT",
            "expected dev identity is only valid for Gamma requests",
        )
    path = create_execution_request(
        store_root=args.store_root,
        candidate_ref=args.candidate,
        environment=args.environment,
        impact_plan_digest=args.impact_plan_digest,
        priority=args.priority,
        created_at=args.created_at,
    )
    return {
        "terminal": "requested",
        "request": request_exact_ref(args.store_root, path),
    }


def _handle_next(args: argparse.Namespace) -> dict[str, object]:
    selected = select_next_request(
        store_root=args.store_root, request_refs=args.request
    )
    if selected is None:
        return {"terminal": "idle", "request": None, "requestRef": None}
    selected_ref = next(
        exact
        for exact in args.request
        if load_execution_request(args.store_root, exact)["requestId"]
        == selected["requestId"]
    )
    return {"terminal": "selected", "request": selected, "requestRef": selected_ref}


def _handle_transition(args: argparse.Namespace) -> dict[str, object]:
    path = append_task_state(
        store_root=args.store_root,
        request_ref=args.request,
        state=args.state,
        occurred_at=args.occurred_at,
        reason=args.reason,
        acceptance_ref=args.acceptance,
    )
    return {
        "terminal": "transitioned",
        "state": args.state,
        "event": _result_ref(args.store_root, path),
    }


def _handle_supersede(args: argparse.Namespace) -> dict[str, object]:
    current = _assert_expected_dev(
        args.repository,
        expected_head=args.expected_dev_head,
        expected_tree=args.expected_dev_tree,
    )
    stale: list[tuple[dict[str, str], dict[str, Any]]] = []
    for exact in args.request:
        request = load_execution_request(args.store_root, exact)
        if request["environment"] != "gamma":
            raise EnvironmentExecutionError(
                "ENVIRONMENT_EXECUTION.NOT_GAMMA",
                "supersede only accepts Gamma requests",
            )
        candidate = _candidate_identity(args.store_root, request)
        if (
            candidate["commit"] != current["head"]
            or candidate["tree"] != current["tree"]
        ):
            stale.append((exact, request))

    results: list[dict[str, object]] = []
    for exact, _request in stale:
        path = supersede_request(
            store_root=args.store_root,
            request_ref=exact,
            reason=args.reason,
            occurred_at=args.occurred_at,
        )
        event = _load_json_exact(args.store_root, _result_ref(args.store_root, path))
        results.append(
            {
                "request": exact,
                "event": _result_ref(args.store_root, path),
                "state": event["state"],
            }
        )
    return {
        "terminal": "superseded" if results else "current",
        "dev": current,
        "requests": results,
    }


def _handle_issue(args: argparse.Namespace) -> dict[str, object]:
    request = load_execution_request(args.store_root, args.request)
    if request["environment"] == "gamma":
        current = _current_dev_identity(args.repository)
        candidate = _candidate_identity(args.store_root, request)
        if (
            candidate["commit"] != current["head"]
            or candidate["tree"] != current["tree"]
        ):
            raise EnvironmentExecutionError(
                "ENVIRONMENT_EXECUTION.GAMMA_IDENTITY_DRIFT",
                "Gamma acceptance request is not current exact dev1.0 identity",
            )
    signer = _signer(
        args.signer_identity,
        keyring_path=args.signing_keyring,
        unavailable_code="ENVIRONMENT_EXECUTION.ACCEPTANCE_SIGNER_UNAVAILABLE",
    )
    path = issue_environment_acceptance_fact(
        store_root=args.store_root,
        request_ref=args.request,
        profile=args.profile,
        status=args.status,
        case_result_refs=args.case_result,
        runtime_identity=args.runtime_identity,
        data_lifecycle=args.data_lifecycle,
        provider_readiness=args.provider_readiness,
        observability_readiness=args.observability_readiness,
        inspect_evidence=args.inspect_evidence,
        doctor_evidence=args.doctor_evidence,
        cleanup_evidence=args.cleanup_evidence,
        lease_closure_evidence=args.lease_closure_evidence,
        predecessor=args.predecessor,
        signer_identity=args.signer_identity,
        signer=signer,
        expires_at=args.expires_at,
        non_promotable=args.non_promotable,
        reason_code=args.reason_code,
        issued_at=args.issued_at,
    )
    return {
        "terminal": "acceptance_issued",
        "acceptance": _result_ref(args.store_root, path),
    }


def _qualification_crypto(
    args: argparse.Namespace,
) -> tuple[object, object, dict[str, str]]:
    expected_signers = {
        environment: getattr(args, f"expected_{environment}_signer_identity")
        for environment in ("alpha", "beta", "gamma")
    }
    try:
        keyring = load_keyring(args.signing_keyring)
        for identity in expected_signers.values():
            assert_distinct_active_keys(keyring, args.qualification_signer_identity, identity)
        environment_verifier = ed25519_environment_verifier(keyring, expected_signers.values())
    except EvidenceSigningError as exc:
        raise EnvironmentExecutionError(
            "ENVIRONMENT_EXECUTION.KEY_PURPOSE_CONFLICT"
            if exc.code == "EVIDENCE_SIGNING.KEY_PURPOSE_CONFLICT"
            else "ENVIRONMENT_EXECUTION.ENVIRONMENT_VERIFIER_UNAVAILABLE",
            exc.detail,
        ) from exc
    return (
        _signer(
            args.qualification_signer_identity,
            keyring_path=args.signing_keyring,
            unavailable_code="ENVIRONMENT_EXECUTION.QUALIFICATION_SIGNER_UNAVAILABLE",
        ),
        environment_verifier,
        expected_signers,
    )


def _handle_qualify(args: argparse.Namespace) -> dict[str, object]:
    current = _assert_expected_dev(
        args.repository,
        expected_head=args.expected_dev_head,
        expected_tree=args.expected_dev_tree,
    )
    gamma = _load_json_exact(args.store_root, args.gamma_acceptance)
    candidate = gamma.get("candidate")
    if (
        gamma.get("environment") != "gamma"
        or gamma.get("status") != "passed"
        or not isinstance(candidate, Mapping)
        or candidate.get("commit") != current["head"]
        or candidate.get("tree") != current["tree"]
    ):
        raise EnvironmentExecutionError(
            "ENVIRONMENT_EXECUTION.GAMMA_IDENTITY_DRIFT",
            "Gamma acceptance is not for current exact dev1.0 identity",
        )
    signer, environment_verifier, expected_environment_signers = _qualification_crypto(
        args
    )
    path = issue_integration_qualification(
        repository=args.repository,
        store_root=args.store_root,
        publish_result_ref=args.publish_result,
        gamma_acceptance_ref=args.gamma_acceptance,
        signer_identity=args.qualification_signer_identity,
        signer=signer,
        environment_signature_verifier=environment_verifier,
        expected_environment_signer_identities=expected_environment_signers,
        issued_at=args.issued_at,
        expires_at=args.expires_at,
    )
    return {
        "terminal": "qualified",
        "qualification": _result_ref(args.store_root, path),
    }


def _dispatch(args: argparse.Namespace) -> dict[str, object]:
    handlers = {
        "request": _handle_request,
        "next": _handle_next,
        "transition": _handle_transition,
        "supersede": _handle_supersede,
        "issue": _handle_issue,
        "qualify": _handle_qualify,
    }
    return handlers[args.command](args)


def _emit(value: Mapping[str, object]) -> None:
    sys.stdout.buffer.write(canonical_json_bytes(dict(value)) + b"\n")


def main(argv: list[str] | None = None) -> int:
    try:
        args = _build_parser().parse_args(argv)
        args.repository = args.repository.resolve()
        args.store_root = args.store_root.expanduser()
        _emit(_dispatch(args))
        return 0
    except (
        EnvironmentExecutionError,
        EnvironmentSchedulerError,
        IntegrationQualificationError,
    ) as exc:
        _emit({"terminal": "GATE_BLOCK", "code": exc.code, "detail": exc.detail})
        return 2
    except OSError as exc:
        _emit(
            {
                "terminal": "GATE_BLOCK",
                "code": "ENVIRONMENT_EXECUTION.IO_ERROR",
                "detail": str(exc) or type(exc).__name__,
            }
        )
        return 2
    except Exception as exc:  # pragma: no cover - final JSON boundary
        _emit(
            {
                "terminal": "GATE_BLOCK",
                "code": "ENVIRONMENT_EXECUTION.INTERNAL",
                "detail": f"unexpected {type(exc).__name__}",
            }
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
