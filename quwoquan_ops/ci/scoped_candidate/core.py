"""Exact path claim、私有 Git index 与 ref CAS 的单轨实现。"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from quwoquan_ops.ci import integration_qualification as qualification
from quwoquan_ops.cli.lib.evidence_signing import (
    ENVIRONMENT_OPS_IDENTITY, KEYRING_RELATIVE_PATH, EvidenceSigningError,
    ed25519_environment_verifier, load_keyring,
)

_SHA_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SCHEMA = "quwoquan_ops.exact_integration_candidate.v1"
_ADMISSION_SCHEMA = "quwoquan_ops.integration_publish_admission.v1"
_PUBLISH_RESULT_SCHEMA = "quwoquan_ops.integration_publish_result.v1"


class ScopedCandidateError(ValueError):
    """带稳定 code 的 scoped candidate 阻断。"""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def canonical_bytes(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ScopedCandidateError("SCOPED_CANDIDATE.INVALID", "payload is not canonical JSON") from exc


def exact_digest(value: bytes | Mapping[str, Any] | Path) -> str:
    if isinstance(value, Path):
        raw = value.read_bytes()
    elif isinstance(value, bytes):
        raw = value
    else:
        raw = canonical_bytes(value)
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or "\x00" in value:
        raise ScopedCandidateError("SCOPED_CANDIDATE.INVALID", f"{field} must be non-empty canonical text")
    return value


def _sha(value: object, field: str) -> str:
    text = _text(value, field)
    if _SHA_RE.fullmatch(text) is None:
        raise ScopedCandidateError("SCOPED_CANDIDATE.INVALID", f"{field} must be an exact Git object id")
    return text


def _digest(value: object, field: str) -> str:
    text = _text(value, field)
    if _DIGEST_RE.fullmatch(text) is None:
        raise ScopedCandidateError("SCOPED_CANDIDATE.INVALID", f"{field} must be sha256:<64 lowercase hex>")
    return text


def _load_policy(policy_path: Path) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ScopedCandidateError("SCOPED_CANDIDATE.INVALID", "scoped candidate policy is unavailable") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ScopedCandidateError("SCOPED_CANDIDATE.INVALID", "scoped candidate policy schema is invalid")
    return payload


def _repo_root(repository: Path) -> Path:
    completed = _git(repository, "rev-parse", "--show-toplevel")
    root = Path(completed.stdout.strip()).resolve()
    if root != repository.resolve():
        raise ScopedCandidateError("SCOPED_CANDIDATE.INVALID", "repository must be the Git worktree root")
    return root


def _git(repository: Path, *args: str, env: Mapping[str, str] | None = None, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    process_env = dict(os.environ)
    process_env["PYTHONDONTWRITEBYTECODE"] = "1"
    if env:
        process_env.update(env)
    completed = subprocess.run(
        ["git", *args], cwd=repository, env=process_env, input=input_text,
        text=True, capture_output=True, check=False,
    )
    if completed.returncode != 0:
        detail = " ".join((completed.stderr or completed.stdout).split())
        raise ScopedCandidateError("SCOPED_CANDIDATE.INVALID", f"git {' '.join(args)} failed: {detail}")
    return completed


def _normalize_path(repository: Path, value: object) -> str:
    text = _text(value, "path")
    path = PurePosixPath(text)
    if path.is_absolute() or path.as_posix() != text or any(part in {"", ".", ".."} for part in path.parts) or "\\" in text:
        raise ScopedCandidateError("SCOPED_CANDIDATE.INVALID", f"path {text!r} is not repository-relative canonical POSIX")
    current = repository
    for part in path.parts:
        current = current / part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(metadata.st_mode):
            raise ScopedCandidateError("SCOPED_CANDIDATE.INVALID", f"path {text!r} traverses a symlink")
    if current.exists() and current.is_dir():
        raise ScopedCandidateError("SCOPED_CANDIDATE.INVALID", f"path {text!r} must identify one file")
    return text


def _normalize_paths(repository: Path, paths: Sequence[str]) -> tuple[str, ...]:
    if isinstance(paths, (str, bytes)) or not paths:
        raise ScopedCandidateError("SCOPED_CANDIDATE.INVALID", "paths must be a non-empty sequence")
    normalized = tuple(sorted(_normalize_path(repository, value) for value in paths))
    if len(normalized) != len(set(normalized)):
        raise ScopedCandidateError("SCOPED_CANDIDATE.INVALID", "paths must be duplicate-free")
    for index, left in enumerate(normalized):
        for right in normalized[index + 1 :]:
            if _paths_conflict(left, right):
                raise ScopedCandidateError("SCOPED_CANDIDATE.INVALID", f"claim contains overlapping paths {left!r} and {right!r}")
    return normalized


def _paths_conflict(left: str, right: str) -> bool:
    a, b = PurePosixPath(left), PurePosixPath(right)
    return a == b or a in b.parents or b in a.parents


def _claim_root(repository: Path, policy_path: Path) -> Path:
    policy = _load_policy(policy_path)
    root_text = policy.get("claim", {}).get("storage_root") if isinstance(policy.get("claim"), dict) else None
    root = repository / _text(root_text, "claim.storage_root")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    for name in ("claims", "releases", "candidates", "source-facts", "admissions", "publish-results", "private-index"):
        child = root / name
        child.mkdir(exist_ok=True, mode=0o700)
        os.chmod(child, 0o700)
    return root


def store_root(*, repository: Path, policy_path: Path) -> Path:
    """本地 exact candidate 证据链的唯一 store root；链内所有 ref 都相对它解析。"""
    return _claim_root(_repo_root(repository), policy_path)


def store_ref(*, repository: Path, policy_path: Path, path: Path) -> dict[str, str]:
    root = store_root(repository=repository, policy_path=policy_path)
    return {"ref": path.resolve().relative_to(root).as_posix(), "digest": exact_digest(path)}


@contextmanager
def _coordinator_lock(root: Path) -> Iterator[None]:
    lock_path = root / "coordinator.lock"
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _write_create_once(path: Path, payload: Mapping[str, Any]) -> Path:
    encoded = canonical_bytes(payload) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    except FileExistsError:
        if path.read_bytes() != encoded:
            raise ScopedCandidateError("SCOPED_CANDIDATE.CREATE_CONFLICT", f"create-once slot differs: {path.name}")
        return path
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    return path


def _read_json(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        payload = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ScopedCandidateError("SCOPED_CANDIDATE.INVALID", f"invalid evidence file {path}") from exc
    if not isinstance(payload, dict):
        raise ScopedCandidateError("SCOPED_CANDIDATE.INVALID", f"evidence file {path} is not an object")
    return payload


def inspect_claims(*, repository: Path, policy_path: Path) -> list[dict[str, Any]]:
    repository = _repo_root(repository)
    root = _claim_root(repository, policy_path)
    releases = {path.stem for path in (root / "releases").glob("*.json")}
    claims: list[dict[str, Any]] = []
    for path in sorted((root / "claims").glob("*.json")):
        payload = _read_json(path)
        payload["active"] = path.stem not in releases
        claims.append(payload)
    return claims


def acquire_claim(
    *, repository: Path, policy_path: Path, writer_id: str, owner_identity_ref: str,
    expected_parent: str, paths: Sequence[str], expires_at: str,
) -> Path:
    repository = _repo_root(repository)
    normalized = _normalize_paths(repository, paths)
    expected_parent = _sha(expected_parent, "expectedParent")
    _git(repository, "cat-file", "-e", f"{expected_parent}^{{commit}}")
    writer_id = _text(writer_id, "writerId")
    owner_identity_ref = _text(owner_identity_ref, "ownerIdentityRef")
    expires_at = _text(expires_at, "expiresAt")
    datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    root = _claim_root(repository, policy_path)
    with _coordinator_lock(root):
        active = [claim for claim in inspect_claims(repository=repository, policy_path=policy_path) if claim["active"]]
        for claim in active:
            for requested in normalized:
                for existing in claim.get("paths", []):
                    if _paths_conflict(requested, existing):
                        raise ScopedCandidateError(
                            "SCOPED_CANDIDATE.CLAIM_CONFLICT",
                            f"path {requested!r} conflicts with active claim {claim.get('claimId')}",
                        )
        generation = 1 + max((int(claim.get("generation", 0)) for claim in active), default=0)
        body: dict[str, Any] = {
            "schema": "quwoquan_ops.scoped_path_claim.v1", "writerId": writer_id,
            "ownerIdentityRef": owner_identity_ref, "worktree": str(repository),
            "expectedParent": expected_parent, "paths": list(normalized),
            "pathsDigest": exact_digest({"paths": list(normalized)}),
            "generation": generation, "acquiredAt": _utc_now(), "expiresAt": expires_at,
        }
        body["claimId"] = exact_digest(body)
        return _write_create_once(root / "claims" / f"{body['claimId']}.json", body)


def release_claim(*, repository: Path, policy_path: Path, claim_ref: Path, reason: str) -> Path:
    repository = _repo_root(repository)
    root = _claim_root(repository, policy_path)
    claim = _read_json(claim_ref)
    claim_id = _digest(claim.get("claimId"), "claimId")
    payload = {
        "schema": "quwoquan_ops.scoped_path_claim_release.v1", "claimId": claim_id,
        "claimDigest": exact_digest(claim_ref), "reason": _text(reason, "reason"), "releasedAt": _utc_now(),
    }
    with _coordinator_lock(root):
        return _write_create_once(root / "releases" / f"{claim_id}.json", payload)


def _index_digest(repository: Path) -> str:
    path_text = _git(repository, "rev-parse", "--git-path", "index").stdout.strip()
    path = Path(path_text)
    if not path.is_absolute():
        path = repository / path
    return exact_digest(path) if path.exists() else "absent"


def _changed_paths(repository: Path, parent: str, tree: str) -> tuple[str, ...]:
    output = _git(repository, "diff-tree", "--no-commit-id", "--name-only", "-r", "-z", parent, tree).stdout
    return tuple(sorted(value for value in output.split("\0") if value))


def build_candidate(
    *, repository: Path, policy_path: Path, claim_ref: Path, owner_identity_ref: str,
    impact_plan_digest: str, message: str, author_name: str, author_email: str,
) -> Path:
    repository = _repo_root(repository)
    root = _claim_root(repository, policy_path)
    claim = _read_json(claim_ref)
    claim_id = _digest(claim.get("claimId"), "claimId")
    if (root / "releases" / f"{claim_id}.json").exists():
        raise ScopedCandidateError("SCOPED_CANDIDATE.STALE", "claim was released")
    if claim.get("ownerIdentityRef") != owner_identity_ref:
        raise ScopedCandidateError("SCOPED_CANDIDATE.STALE", "owner identity drifted")
    parent = _sha(claim.get("expectedParent"), "expectedParent")
    paths = _normalize_paths(repository, claim.get("paths", []))
    impact_plan_digest = _digest(impact_plan_digest, "impactPlanDigest")
    head_before = _git(repository, "rev-parse", "HEAD").stdout.strip()
    index_before = _index_digest(repository)
    fd, private_index = tempfile.mkstemp(prefix="index-", dir=root / "private-index")
    os.close(fd)
    os.unlink(private_index)
    private_env = {"GIT_INDEX_FILE": private_index}
    try:
        _git(repository, "read-tree", parent, env=private_env)
        _git(repository, "add", "-A", "--", *paths, env=private_env)
        tree = _sha(_git(repository, "write-tree", env=private_env).stdout.strip(), "tree")
        changed = _changed_paths(repository, parent, tree)
        if changed != paths:
            raise ScopedCandidateError(
                "SCOPED_CANDIDATE.SCOPE_DRIFT",
                f"candidate changed paths {changed!r} do not equal claimed paths {paths!r}",
            )
        commit_env = {
            **private_env,
            "GIT_AUTHOR_NAME": _text(author_name, "authorName"),
            "GIT_AUTHOR_EMAIL": _text(author_email, "authorEmail"),
            "GIT_COMMITTER_NAME": _text(author_name, "authorName"),
            "GIT_COMMITTER_EMAIL": _text(author_email, "authorEmail"),
        }
        commit = _sha(
            _git(repository, "commit-tree", tree, "-p", parent, env=commit_env, input_text=_text(message, "message") + "\n").stdout.strip(),
            "commit",
        )
    finally:
        try:
            os.unlink(private_index)
        except FileNotFoundError:
            pass
    if _git(repository, "rev-parse", "HEAD").stdout.strip() != head_before or _index_digest(repository) != index_before:
        raise ScopedCandidateError("SCOPED_CANDIDATE.SCOPE_DRIFT", "default HEAD or index changed during candidate construction")
    body: dict[str, Any] = {
        "schema": _SCHEMA, "claimRef": claim_ref.relative_to(root).as_posix(),
        "claimDigest": exact_digest(claim_ref), "ownerIdentityRef": owner_identity_ref,
        "expectedParent": parent, "commit": commit, "tree": tree,
        "paths": list(paths), "pathsDigest": exact_digest({"paths": list(paths)}),
        "impactPlanDigest": impact_plan_digest, "createdAt": _utc_now(),
    }
    body["candidateId"] = exact_digest(body)
    return _write_create_once(root / "candidates" / f"{body['candidateId']}.json", body)


def build_head_candidate(
    *, repository: Path, policy_path: Path, commit: str, expected_parent: str,
    owner_identity_ref: str, impact_plan_digest: str, writer_id: str, expires_at: str,
) -> Path:
    """把一个已存在的 exact commit（integration HEAD 或 lane head）构造为 exact candidate。

    candidate 的 scope 就是相对 expected parent 的全部 changed paths；claim 仍经同一
    append-only generation 取得，因此与并行 scoped writer 的路径冲突照常被拒绝。
    commit 必须以 expected parent 为祖先，否则不是 fast-forward 候选。
    """
    repository = _repo_root(repository)
    root = _claim_root(repository, policy_path)
    commit = _sha(_git(repository, "rev-parse", f"{_sha(commit, 'commit')}^{{commit}}").stdout.strip(), "commit")
    parent = _sha(_git(repository, "rev-parse", f"{_sha(expected_parent, 'expectedParent')}^{{commit}}").stdout.strip(), "expectedParent")
    if commit == parent:
        raise ScopedCandidateError("SCOPED_CANDIDATE.INVALID", "candidate commit equals expected parent")
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", parent, commit], cwd=repository, text=True, capture_output=True, check=False,
    )
    if ancestry.returncode != 0:
        raise ScopedCandidateError("SCOPED_CANDIDATE.CAS_CONFLICT", "expected parent is not an ancestor of the candidate commit")
    tree = _sha(_git(repository, "show", "-s", "--format=%T", commit).stdout.strip(), "tree")
    changed = _changed_paths(repository, parent, tree)
    if not changed:
        raise ScopedCandidateError("SCOPED_CANDIDATE.INVALID", "candidate has no changed paths relative to expected parent")
    impact_plan_digest = _digest(impact_plan_digest, "impactPlanDigest")
    claim_path = acquire_claim(
        repository=repository, policy_path=policy_path, writer_id=writer_id,
        owner_identity_ref=owner_identity_ref, expected_parent=parent, paths=list(changed), expires_at=expires_at,
    )
    body: dict[str, Any] = {
        "schema": _SCHEMA, "claimRef": claim_path.relative_to(root).as_posix(),
        "claimDigest": exact_digest(claim_path), "ownerIdentityRef": _text(owner_identity_ref, "ownerIdentityRef"),
        "expectedParent": parent, "commit": commit, "tree": tree,
        "paths": list(changed), "pathsDigest": exact_digest({"paths": list(changed)}),
        "impactPlanDigest": impact_plan_digest, "createdAt": _utc_now(),
    }
    body["candidateId"] = exact_digest(body)
    return _write_create_once(root / "candidates" / f"{body['candidateId']}.json", body)


_SOURCE_FACT_SCHEMA = "quwoquan_ops.integration_source_fact.v1"
_SOURCE_FACT_KINDS = ("local_readiness_fast", "local_readiness_scope", "commit_gate")


def _validate_source_receipt(repository: Path, candidate: dict[str, Any], kind: str, receipt: dict[str, Any], status: str) -> None:
    """只消费真实终态与 exact push 证据，不把调用方 wrapper 当成结论。"""
    def require(condition: bool, detail: str) -> None:
        if not condition:
            raise ScopedCandidateError("SCOPED_CANDIDATE.SOURCE_RECEIPT", detail)

    require(kind.startswith("local_readiness_"), "commit_gate has no candidate-bound receipt contract")
    level = kind.removeprefix("local_readiness_")
    require(receipt.get("schema") == "local-readiness-receipt-v2" and receipt.get("level") == level, "readiness schema/level mismatch")
    require(receipt.get("status") == {"passed": "PASS", "failed": "FAIL"}[status], "source receipt terminal differs from wrapper")
    expected = {"base": candidate["expectedParent"], "head": candidate["commit"],
                "tree": candidate["tree"], "paths": candidate["paths"], "mode": "push"}
    require(receipt.get("source_identity") == expected and receipt.get("mode") == "push", "source receipt candidate identity mismatch")
    require(receipt.get("paths") == candidate["paths"], "source receipt range mismatch")
    require(_git(repository, "rev-parse", f"{candidate['commit']}^{{tree}}").stdout.strip() == candidate["tree"], "candidate tree mismatch")
    require(list(_changed_paths(repository, candidate["expectedParent"], candidate["tree"])) == candidate["paths"], "candidate changed paths mismatch")
    from quwoquan_ops.cli.lib.evidence_fingerprint import validate_evidence_fingerprint, EvidenceFingerprintError
    try:
        fingerprint = validate_evidence_fingerprint(receipt.get("fingerprint"))
    except EvidenceFingerprintError as exc:
        raise ScopedCandidateError("SCOPED_CANDIDATE.SOURCE_RECEIPT", "invalid readiness fingerprint") from exc
    require(fingerprint["digest_payload"]["git"] == {"head_sha": candidate["commit"], "merge_base_sha": candidate["expectedParent"]}, "readiness fingerprint candidate mismatch")
    if status == "failed":
        return
    require(receipt.get("input_stable") is True and receipt.get("source_execution") == "immutable_capsule", "source receipt is not stable immutable execution")
    checks = _validate_source_checks(repository, candidate, receipt, level)
    _validate_source_health(repository, candidate, checks, fingerprint)


def _validate_source_checks(repository: Path, candidate: dict[str, Any], receipt: dict[str, Any], level: str) -> list[dict[str, Any]]:
    def require(condition: bool, detail: str) -> None:
        if not condition:
            raise ScopedCandidateError("SCOPED_CANDIDATE.SOURCE_RECEIPT", detail)
    plan = receipt.get("plan")
    require(isinstance(plan, dict), "source receipt missing plan")
    require(plan.get("paths") == candidate["paths"] and plan.get("mode") == "push" and plan.get("level") == level, "source plan identity mismatch")
    from quwoquan_ops.cli.lib.local_readiness.core import canonicalize_plan, LocalReadinessError
    updates = [{"local_ref": candidate["commit"], "local_sha": candidate["commit"],
                "remote_ref": "refs/heads/dev1.0", "remote_sha": candidate["expectedParent"]}]
    try:
        canonicalize_plan(plan, repo_root=repository, push_updates=updates)
    except (LocalReadinessError, ValueError) as exc:
        raise ScopedCandidateError("SCOPED_CANDIDATE.SOURCE_RECEIPT", "source receipt canonical checks drifted") from exc
    checks = receipt.get("checks")
    planned = plan.get("checks")
    require(isinstance(checks, list) and isinstance(planned, list) and bool(planned), "source receipt missing required checks")
    require(all(isinstance(item, dict) for item in checks + planned), "source receipt invalid check")
    require([item.get("id") for item in checks] == [item.get("id") for item in planned], "source receipt required checks incomplete")
    require(all(item.get("status") == "PASS" and item.get("exit_code") == 0 for item in checks), "source receipt contains failed check")
    require(level == "fast" or receipt.get("deferred") == plan.get("deferred") == [], "source receipt still deferred")
    return checks


def _validate_source_health(repository: Path, candidate: dict[str, Any], checks: list[dict[str, Any]], fingerprint: dict[str, Any]) -> None:
    from quwoquan_ops.cli.lib.evidence_fingerprint import validate_evidence_fingerprint, EvidenceFingerprintError
    def require(condition: bool, detail: str) -> None:
        if not condition:
            raise ScopedCandidateError("SCOPED_CANDIDATE.SOURCE_RECEIPT", detail)
    health = [item for item in checks if item.get("code_health") is not None]
    require(len(health) == 1, "source receipt requires one full code health report")
    evidence = health[0]["code_health"]
    require(isinstance(evidence, dict) and isinstance(evidence.get("report"), dict), "invalid code health evidence")
    report = evidence["report"]
    # 健康报告使用 canonical JSON digest（含浮点数），不另造阈值或扫描器。
    from quwoquan_ops.ci.impact_planner_core import canonical_digest
    from quwoquan_ops.gate.code_health_delta.git_delta import changes
    require(evidence.get("digest") == canonical_digest(report), "code health report digest mismatch")
    require(report.get("schema") == "quwoquan.code-health-delta" and report.get("terminal") in {"PASS", "PR_WARN"}, "code health terminal is not admissible")
    require(report.get("baseSha") == candidate["expectedParent"] and report.get("headSha") == candidate["commit"], "code health range mismatch")
    require(report.get("mode") == "full" and report.get("candidateSource") == "commit" and report.get("mergeParents") == [], "code health must measure full actual push delta")
    changed = [item.path for item in changes(repository, candidate["expectedParent"], candidate["commit"])]
    require(report.get("changedPaths") == changed and bool(changed), "code health empty or incomplete scan")
    require(report.get("changedPathsDigest") == canonical_digest(changed), "code health paths digest mismatch")
    try:
        health_fingerprint = validate_evidence_fingerprint(report.get("evidenceFingerprint"))
    except EvidenceFingerprintError as exc:
        raise ScopedCandidateError("SCOPED_CANDIDATE.SOURCE_RECEIPT", "invalid code health fingerprint") from exc
    require(health_fingerprint["digest_payload"]["git"] == fingerprint["digest_payload"]["git"], "code health fingerprint candidate mismatch")
    require(not any(item.get("terminal") == "GATE_BLOCK" for item in report.get("findings", [])), "code health contains blocker finding")


def create_source_fact(
    *, repository: Path, policy_path: Path, candidate_ref: Mapping[str, str], kind: str,
    receipt_path: Path, status: str,
) -> Path:
    """把一份本地 readiness/gate 回执绑定到 candidateId，形成 publisher 需要的 source fact。

    status 只能是回执自身的终态；这里不解释、不放宽回执结论。
    """
    repository = _repo_root(repository)
    root = _claim_root(repository, policy_path)
    candidate, candidate_digest = _load_exact_ref(root, candidate_ref, "candidate")
    if candidate.get("schema") != _SCHEMA:
        raise ScopedCandidateError("SCOPED_CANDIDATE.INVALID", "candidate schema is invalid")
    if kind not in _SOURCE_FACT_KINDS:
        raise ScopedCandidateError("SCOPED_CANDIDATE.INVALID", f"source fact kind must be one of {_SOURCE_FACT_KINDS}")
    if status not in {"passed", "failed"}:
        raise ScopedCandidateError("SCOPED_CANDIDATE.INVALID", "source fact status must be passed or failed")
    receipt = receipt_path.resolve()
    if not receipt.is_file() or receipt_path.is_symlink():
        raise ScopedCandidateError("SCOPED_CANDIDATE.INVALID", "source receipt must be a regular file")
    try:
        receipt_ref = receipt.relative_to(repository).as_posix()
    except ValueError as exc:
        raise ScopedCandidateError("SCOPED_CANDIDATE.INVALID", "source receipt must live inside the repository output root") from exc
    _validate_source_receipt(repository, candidate, kind, _read_json(receipt), status)
    body: dict[str, Any] = {
        "schema": _SOURCE_FACT_SCHEMA, "kind": kind, "status": status,
        "expectedParent": candidate["expectedParent"], "pathsDigest": candidate["pathsDigest"],
        "candidateId": _digest(candidate.get("candidateId"), "candidateId"),
        "candidate": {"ref": candidate_ref["ref"], "digest": candidate_digest},
        "commit": candidate["commit"], "tree": candidate["tree"],
        "receipt": {"ref": receipt_ref, "digest": exact_digest(receipt)},
        "createdAt": _utc_now(),
    }
    body["sourceFactId"] = exact_digest(body)
    return _write_create_once(root / "source-facts" / f"{body['sourceFactId']}.json", body)


def _load_exact_ref(root: Path, value: Mapping[str, str], label: str) -> tuple[dict[str, Any], str]:
    """在唯一 store root 下解析 exact ref；ref 一律相对 store root，不相对 worktree。"""
    if not isinstance(value, Mapping) or set(value) != {"ref", "digest"}:
        raise ScopedCandidateError("SCOPED_CANDIDATE.INVALID", f"{label} must contain ref and digest")
    ref = _normalize_path(root, value.get("ref"))
    expected = _digest(value.get("digest"), f"{label}.digest")
    path = root / ref
    if not path.is_file():
        raise ScopedCandidateError("SCOPED_CANDIDATE.STALE", f"{label} is not present in the candidate store")
    actual = exact_digest(path)
    if actual != expected:
        raise ScopedCandidateError("SCOPED_CANDIDATE.STALE", f"{label} exact bytes drifted")
    return _read_json(path), actual


def create_publish_admission(
    *, repository: Path, policy_path: Path, candidate_ref: Mapping[str, str],
    source_fact_refs: Sequence[Mapping[str, str]], alpha_fact_ref: Mapping[str, str],
    beta_fact_ref: Mapping[str, str], expected_remote_oid: str,
) -> Path:
    repository = _repo_root(repository)
    root = _claim_root(repository, policy_path)
    body = _publish_admission_body(
        root, candidate_ref, source_fact_refs, alpha_fact_ref, beta_fact_ref, expected_remote_oid,
    )
    _validate_admission_chain(repository, root, body)
    return _write_create_once(root / "admissions" / f"{body['admissionId']}.json", body)


def _publish_admission_body(
    root: Path, candidate_ref: Mapping[str, str], source_fact_refs: Sequence[Mapping[str, str]],
    alpha_fact_ref: Mapping[str, str], beta_fact_ref: Mapping[str, str], expected_remote_oid: str,
) -> dict[str, Any]:
    """预检和正式签发共用候选绑定；构造内存对象不签发资格。"""
    candidate, candidate_exact = qualification._exact_ref(root, candidate_ref, "candidate")
    candidate_id = _digest(candidate.get("candidateId"), "candidateId")
    expected_remote_oid = _sha(expected_remote_oid, "expectedRemoteOid")
    normalized_sources = list(source_fact_refs)
    normalized_environment = {"alpha": dict(alpha_fact_ref), "beta": dict(beta_fact_ref)}
    body: dict[str, Any] = {
        "schema": _ADMISSION_SCHEMA, "candidate": candidate_exact,
        "candidateId": candidate_id, "expectedRemoteOid": expected_remote_oid,
        "targetRef": "refs/heads/dev1.0", "commit": candidate["commit"], "tree": candidate["tree"],
        "sourceFacts": normalized_sources, "environmentFacts": normalized_environment,
        "decision": "admitted", "createdAt": _utc_now(),
    }
    body["admissionId"] = exact_digest(body)
    return body


def validate_publish_inputs(
    *, repository: Path, store_root: Path, candidate_ref: Mapping[str, str],
    source_fact_refs: Sequence[Mapping[str, str]], alpha_fact_ref: Mapping[str, str],
    beta_fact_ref: Mapping[str, str], expected_remote_oid: str, receipt_root: Path | None = None,
) -> None:
    """只读验证 portable bundle 的完整发布前驱；不导入、不落 admission、不移动 ref。

    Git 与 keyring 仍取真实 repository；receipt_root 仅指定传输包内的原始回执根，
    不改变 candidate 的源码身份，也不允许回退到另一个回执位置。
    """
    repository = _repo_root(repository)
    body = _publish_admission_body(
        store_root, candidate_ref, source_fact_refs, alpha_fact_ref, beta_fact_ref, expected_remote_oid,
    )
    _validate_admission_chain(repository, store_root, body, receipt_root=receipt_root)


def _identity_digest(payload: Mapping[str, Any], field: str) -> None:
    body = dict(payload)
    identity = body.pop(field, None)
    if identity != exact_digest(body):
        raise ScopedCandidateError("SCOPED_CANDIDATE.STALE", f"{field} self digest drifted")


def _validate_candidate_binding(repository: Path, root: Path, admission: dict[str, Any]) -> dict[str, Any]:
    candidate, _ = qualification._exact_ref(root, admission.get("candidate"), "candidate")
    _identity_digest(candidate, "candidateId")
    if candidate.get("schema") != _SCHEMA or any(
        candidate.get(key) != admission.get(key) for key in ("candidateId", "commit", "tree")
    ) or candidate.get("expectedParent") != admission.get("expectedRemoteOid"):
        raise ScopedCandidateError("SCOPED_CANDIDATE.STALE", "candidate identity differs from admission")
    before = _sha(admission.get("expectedRemoteOid"), "expectedRemoteOid")
    after = _sha(admission.get("commit"), "commit")
    if before == after:
        raise ScopedCandidateError("SCOPED_CANDIDATE.CAS_CONFLICT", "candidate must advance remote-before")
    _git(repository, "merge-base", "--is-ancestor", before, after)
    if _git(repository, "rev-parse", f"{after}^{{tree}}").stdout.strip() != candidate.get("tree"):
        raise ScopedCandidateError("SCOPED_CANDIDATE.STALE", "candidate Git tree drifted")
    paths = list(_changed_paths(repository, before, candidate["tree"]))
    if not paths or paths != candidate.get("paths") or exact_digest({"paths": paths}) != candidate.get("pathsDigest"):
        raise ScopedCandidateError("SCOPED_CANDIDATE.SCOPE_DRIFT", "candidate Git paths drifted")
    claim, _ = qualification._exact_ref(root, {"ref": candidate.get("claimRef"), "digest": candidate.get("claimDigest")}, "claim")
    _identity_digest(claim, "claimId")
    if claim.get("schema") != "quwoquan_ops.scoped_path_claim.v1" or any(
        claim.get(key) != candidate.get(key) for key in ("expectedParent", "ownerIdentityRef", "paths", "pathsDigest")
    ):
        raise ScopedCandidateError("SCOPED_CANDIDATE.STALE", "claim candidate binding drifted")
    # claim 是构造期互斥证据；accept 终态可释放，不把 release 错当 EAF 失效。
    return candidate


def _validate_admission_sources(repository: Path, root: Path, admission: dict[str, Any], candidate: dict[str, Any],
                                *, receipt_root: Path | None = None) -> None:
    refs = admission.get("sourceFacts")
    if not isinstance(refs, list) or not refs:
        raise ScopedCandidateError("SCOPED_CANDIDATE.SOURCE_RECEIPT", "source facts are required")
    receipt_base = repository if receipt_root is None else receipt_root
    kinds: set[str] = set()
    for exact in refs:
        fact, _ = qualification._exact_ref(root, exact, "sourceFact")
        _identity_digest(fact, "sourceFactId")
        kind = fact.get("kind")
        if fact.get("schema") != _SOURCE_FACT_SCHEMA or fact.get("status") != "passed" or kind not in _SOURCE_FACT_KINDS or kind in kinds:
            raise ScopedCandidateError("SCOPED_CANDIDATE.SOURCE_RECEIPT", "source fact schema/status/kind drifted")
        kinds.add(kind)
        if fact.get("candidate") != admission["candidate"] or any(
            fact.get(key) != candidate.get(key) for key in ("candidateId", "commit", "tree", "expectedParent", "pathsDigest")
        ):
            raise ScopedCandidateError("SCOPED_CANDIDATE.STALE", "source fact candidate binding drifted")
        receipt_ref = fact.get("receipt")
        receipt_path = repository / _normalize_path(repository, receipt_ref.get("ref") if isinstance(receipt_ref, Mapping) else None)
        if not receipt_path.is_relative_to(repository / ".qwq_output"):
            raise ScopedCandidateError("SCOPED_CANDIDATE.SOURCE_RECEIPT", "source receipt must be repository output")
        receipt, _ = qualification._exact_ref(
            receipt_base, receipt_ref, "sourceReceipt",
        )
        _validate_source_receipt(repository, candidate, kind, receipt, "passed")
    if "local_readiness_scope" not in kinds:
        raise ScopedCandidateError("SCOPED_CANDIDATE.SOURCE_RECEIPT", "complete scope readiness is required")


def _validate_admission_chain(repository: Path, root: Path, admission: dict[str, Any],
                              *, receipt_root: Path | None = None) -> None:
    try:
        _identity_digest(admission, "admissionId")
        if admission.get("schema") != _ADMISSION_SCHEMA or admission.get("decision") != "admitted" or admission.get("targetRef") != "refs/heads/dev1.0":
            raise ScopedCandidateError("SCOPED_CANDIDATE.INVALID", "publish admission schema/decision/ref drifted")
        candidate = _validate_candidate_binding(repository, root, admission)
        _validate_admission_sources(repository, root, admission, candidate, receipt_root=receipt_root)
        _validate_admission_environments(repository, root, admission, candidate)
    except (qualification.IntegrationQualificationError, EvidenceSigningError) as exc:
        raise ScopedCandidateError("SCOPED_CANDIDATE.STALE", str(exc)) from exc


def _validate_admission_environments(repository: Path, root: Path, admission: dict[str, Any], candidate: dict[str, Any]) -> None:
    refs = admission.get("environmentFacts")
    if not isinstance(refs, Mapping) or set(refs) != {"alpha", "beta"}:
        raise ScopedCandidateError("SCOPED_CANDIDATE.INVALID", "Alpha/Beta chain is required")
    verifier = ed25519_environment_verifier(load_keyring(repository / KEYRING_RELATIVE_PATH), [ENVIRONMENT_OPS_IDENTITY])
    now = datetime.now(timezone.utc)
    for environment in ("alpha", "beta"):
        fact, _ = qualification._load_acceptance(root, refs[environment], environment, accepted_at=now,
            signature_verifier=verifier, expected_signer_identity=ENVIRONMENT_OPS_IDENTITY)
        if qualification._timestamp(fact.get("issuedAt"), "issuedAt")[1] > now:
            raise ScopedCandidateError("SCOPED_CANDIDATE.STALE", f"{environment} fact is not yet valid")
        expected = {"candidate": {key: candidate[key] for key in ("candidateId", "commit", "tree")},
                    "impactPlanDigest": candidate.get("impactPlanDigest"), "nonPromotable": False,
                    "predecessor": None if environment == "alpha" else refs["alpha"]}
        if any(fact.get(key) != value for key, value in expected.items()):
            raise ScopedCandidateError("SCOPED_CANDIDATE.STALE", f"{environment} candidate/impact/predecessor drifted")
        if environment == "alpha":
            from quwoquan_ops.cli.lib.environment_acceptance_fact_contract import source_admitted_alpha

            if not source_admitted_alpha(fact):
                raise ScopedCandidateError(
                    "SCOPED_CANDIDATE.STALE",
                    "Alpha must be passed or typed ACCEPTANCE.ALPHA_LIVE_DEFERRED_TO_PUBLISHED_DEV",
                )


def _validated_admission(repository: Path, admission_ref: Path, policy_path: Path | None = None,
                         expected_digest: str | None = None) -> dict[str, Any]:
    policy_path = policy_path or Path(__file__).resolve().parents[2] / "policies/scoped_candidate_policy.yaml"
    root = _claim_root(repository, policy_path)
    try:
        relative = admission_ref.absolute().relative_to(root).as_posix()
        admission, _ = qualification._exact_ref(root, {"ref": relative, "digest": expected_digest or exact_digest(admission_ref)}, "admission")
    except (ValueError, OSError) as exc:
        raise ScopedCandidateError("SCOPED_CANDIDATE.STALE", f"admission exact reference invalid: {exc}") from exc
    _validate_admission_chain(repository, root, admission)
    return admission


def validate_integration_publish_origin(repository: Path, remote: str, remote_url: str | None = None) -> None:
    """本地 source 检查不替代 hosted 身份保护；禁止非规范 worktree/remote。"""
    from quwoquan_ops.cli.lib.local_worktree_inventory import load_policy, resolve_project_root
    policy = load_policy()
    project = resolve_project_root(repository, policy)
    hub = project / policy.bare_hub_directory
    common = Path(_git(repository, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip()).resolve()
    if repository != project / policy.integration_directory or common != hub.resolve() or remote != "origin":
        raise ScopedCandidateError("SCOPED_CANDIDATE.INVALID", "publisher requires canonical integration worktree and origin")
    urls = _git(repository, "remote", "get-url", "--push", "--all", "origin").stdout.splitlines()
    authority = _git(repository, "--git-dir", str(hub), "config", "--get-all", "remote.origin.url").stdout.splitlines()
    if len(urls) != 1 or urls != authority or (remote_url is not None and remote_url != urls[0]):
        raise ScopedCandidateError("SCOPED_CANDIDATE.INVALID", "origin push identity differs from canonical hub origin")


def validate_publish_update(*, repository: Path, policy_path: Path, admission_ref: Mapping[str, str],
                            before: str, after: str, ref: str, remote: str, remote_url: str) -> dict[str, Any]:
    """hook 与 publisher 的 exact update 校验边界；不接受 env boolean。"""
    repository = _repo_root(repository)
    validate_integration_publish_origin(repository, remote, remote_url)
    root = _claim_root(repository, policy_path)
    relative = _normalize_path(root, admission_ref.get("ref"))
    digest = _digest(admission_ref.get("digest"), "admission.digest")
    admission = _validated_admission(repository, root / relative, policy_path, digest)
    if (admission["expectedRemoteOid"], admission["commit"], admission["targetRef"]) != (before, after, ref):
        raise ScopedCandidateError("SCOPED_CANDIDATE.STALE", "admission before/after/ref differs from push update")
    return admission


def _terminal_readback(*, before: str, after: str, readback: str) -> str:
    return "before" if readback == before else ("after" if readback == after else "other")


def local_ref_cas_publish(
    *, repository: Path, admission_ref: Path, ref: str = "refs/heads/dev1.0",
    allow_test_adapter: bool = False,
) -> dict[str, str]:
    """仅供 local contract 的 update-ref CAS adapter；生产必须使用 authenticated broker。"""
    if not allow_test_adapter:
        raise ScopedCandidateError("SCOPED_CANDIDATE.PUBLISHER_UNAVAILABLE", "hosted authenticated publisher is required")
    repository = _repo_root(repository)
    admission = _validated_admission(repository, admission_ref)
    if admission["targetRef"] != ref:
        raise ScopedCandidateError("SCOPED_CANDIDATE.INVALID", "publish ref drifted")
    before = str(admission["expectedRemoteOid"])
    after = str(admission["commit"])
    current = _git(repository, "rev-parse", ref).stdout.strip()
    if current != before:
        raise ScopedCandidateError(
            "SCOPED_CANDIDATE.CAS_CONFLICT",
            f"ref readback is {_terminal_readback(before=before, after=after, readback=current)}",
        )
    _git(repository, "merge-base", "--is-ancestor", before, after)
    completed = subprocess.run(
        ["git", "update-ref", ref, after, before], cwd=repository,
        text=True, capture_output=True, check=False,
    )
    readback = _git(repository, "rev-parse", ref).stdout.strip()
    if completed.returncode != 0 or readback != after:
        raise ScopedCandidateError(
            "SCOPED_CANDIDATE.CAS_CONFLICT",
            f"CAS terminal readback is {_terminal_readback(before=before, after=after, readback=readback)}",
        )
    return {"before": before, "after": after, "readback": readback, "terminal": "published"}


def _validate_publisher_readback_identity(readback: Mapping[str, Any], admission: Mapping[str, Any]) -> None:
    expected = {"admissionId": admission["admissionId"], "targetRef": admission["targetRef"],
                "beforeOid": admission["expectedRemoteOid"], "afterOid": admission["commit"]}
    if any(readback.get(key) != value for key, value in expected.items()):
        raise ScopedCandidateError("SCOPED_CANDIDATE.PUBLISHER_UNAVAILABLE", "publisher readback identity drifted")


def hosted_broker_cas_publish(
    *, repository: Path, policy_path: Path, admission_ref: Path,
    broker_url: str, token_provider: Callable[[], str],
    opener: Callable[..., object] = urllib.request.urlopen,
    timeout_seconds: float = 15.0,
) -> Path:
    """调用受信 publisher 一次，并用精确 readback 收敛未知网络结果。"""
    repository = _repo_root(repository)
    root = _claim_root(repository, policy_path)
    admission = _validated_admission(repository, admission_ref, policy_path)
    url = broker_url.strip()
    if not url.startswith("https://") or "?" in url or "#" in url:
        raise ScopedCandidateError("SCOPED_CANDIDATE.PUBLISHER_UNAVAILABLE", "broker URL must be exact HTTPS")
    try:
        token = token_provider().strip()
    except Exception as exc:
        raise ScopedCandidateError("SCOPED_CANDIDATE.PUBLISHER_UNAVAILABLE", "publisher token provider failed") from exc
    if not token:
        raise ScopedCandidateError("SCOPED_CANDIDATE.PUBLISHER_UNAVAILABLE", "publisher token is missing")
    admission_digest = exact_digest(admission_ref)
    admission_store_ref = admission_ref.resolve().relative_to(root).as_posix()
    request_body = canonical_bytes(
        {
            "schema": _ADMISSION_SCHEMA,
            "admission": {"ref": admission_store_ref, "digest": admission_digest},
            "payload": admission,
        }
    )
    request = urllib.request.Request(
        url,
        data=request_body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Idempotency-Key": str(admission["admissionId"]),
        },
    )
    response_payload: dict[str, Any] | None = None
    mutation_error: Exception | None = None
    try:
        with opener(request, timeout=timeout_seconds) as response:
            response_payload = json.load(response)
    except (OSError, TimeoutError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TypeError, ValueError) as exc:
        mutation_error = exc
    readback_request = urllib.request.Request(
        url.rstrip("/") + "/" + str(admission["admissionId"]),
        method="GET",
        headers={"Accept": "application/json", "Authorization": f"Bearer {token}"},
    )
    try:
        with opener(readback_request, timeout=timeout_seconds) as response:
            readback_payload = json.load(response)
    except (OSError, TimeoutError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TypeError, ValueError) as exc:
        detail = "publisher mutation outcome is unknown" if mutation_error is not None else "publisher readback is unavailable"
        raise ScopedCandidateError("SCOPED_CANDIDATE.PUBLISHER_UNAVAILABLE", detail) from exc
    if not isinstance(readback_payload, dict):
        raise ScopedCandidateError("SCOPED_CANDIDATE.PUBLISHER_UNAVAILABLE", "publisher readback is invalid")
    before = str(admission["expectedRemoteOid"])
    after = str(admission["commit"])
    observed = _sha(readback_payload.get("readbackOid"), "readbackOid")
    state = _terminal_readback(before=before, after=after, readback=observed)
    if state != "after":
        code = "SCOPED_CANDIDATE.CAS_CONFLICT" if state == "other" else "SCOPED_CANDIDATE.PUBLISHER_UNAVAILABLE"
        raise ScopedCandidateError(code, f"publisher terminal readback is {state}")
    _validate_publisher_readback_identity(readback_payload, admission)
    if response_payload is not None and (
        not isinstance(response_payload, dict)
        or response_payload.get("admissionId") != admission["admissionId"]
        or response_payload.get("readbackOid") != after
    ):
        raise ScopedCandidateError("SCOPED_CANDIDATE.PUBLISHER_UNAVAILABLE", "publisher mutation response drifted")
    result: dict[str, Any] = {
        "schema": _PUBLISH_RESULT_SCHEMA,
        "admission": {"ref": admission_store_ref, "digest": admission_digest},
        "admissionId": admission["admissionId"],
        "targetRef": admission["targetRef"],
        "beforeOid": before,
        "afterOid": after,
        "readbackOid": observed,
        "publisherReceipt": readback_payload,
        "terminal": "published",
        "createdAt": _utc_now(),
    }
    result["publishResultId"] = exact_digest(result)
    return _write_create_once(root / "publish-results" / f"{result['publishResultId']}.json", result)


def _remote_ref_oid(repository: Path, remote: str, ref: str) -> str | None:
    """`git ls-remote` 精确读回一个远端 ref；不存在时返回 None。"""
    completed = subprocess.run(
        ["git", "ls-remote", "--exit-code", remote, ref], cwd=repository,
        text=True, capture_output=True, check=False,
    )
    if completed.returncode == 2:
        return None
    if completed.returncode != 0:
        raise ScopedCandidateError(
            "SCOPED_CANDIDATE.PUBLISHER_UNAVAILABLE",
            f"remote readback failed: {' '.join((completed.stderr or completed.stdout).split())}",
        )
    for line in completed.stdout.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1] == ref:
            return _sha(parts[0], "readbackOid")
    raise ScopedCandidateError("SCOPED_CANDIDATE.PUBLISHER_UNAVAILABLE", "remote readback did not return the target ref")


def local_git_cas_publish(
    *, repository: Path, policy_path: Path, admission_ref: Path, remote: str = "origin",
    ref: str = "refs/heads/dev1.0",
) -> Path:
    """integration 工作区通道：本地 ff-only 跟到候选，再以 expected-old lease 做一次 non-force fast-forward push。

    前置：当前工作区 HEAD 就在目标分支上且工作树干净；本地分支 == expectedRemoteOid 或已等于候选。
    CAS：`--force-with-lease=<ref>:<before>` 只在远端仍为 before 时更新；pre-push hook 与
    hosted ruleset 继续独立保证 fast-forward。终态按 ls-remote 读回 before|after|other 收口。
    """
    repository = _repo_root(repository)
    root = _claim_root(repository, policy_path)
    validate_integration_publish_origin(repository, remote)
    admission_digest = exact_digest(admission_ref)
    admission = _validated_admission(repository, admission_ref, policy_path, admission_digest)
    if admission["targetRef"] != ref:
        raise ScopedCandidateError("SCOPED_CANDIDATE.INVALID", "publish ref drifted")
    before = str(admission["expectedRemoteOid"])
    after = str(admission["commit"])
    branch = ref.removeprefix("refs/heads/")
    current_branch = _git(repository, "symbolic-ref", "--quiet", "HEAD").stdout.strip()
    if current_branch != ref:
        raise ScopedCandidateError("SCOPED_CANDIDATE.INVALID", f"worktree HEAD must be on {ref} for the integration channel")
    if _git(repository, "status", "--porcelain", "--untracked-files=no").stdout.strip():
        raise ScopedCandidateError("SCOPED_CANDIDATE.INVALID", "worktree must be clean before publish")
    remote_before = _remote_ref_oid(repository, remote, ref)
    if remote_before != before:
        state = _terminal_readback(before=before, after=after, readback=remote_before or "")
        code = "SCOPED_CANDIDATE.STALE" if state == "after" else "SCOPED_CANDIDATE.CAS_CONFLICT"
        raise ScopedCandidateError(code, f"remote readback before publish is {state}")
    local = _git(repository, "rev-parse", ref).stdout.strip()
    if local == before:
        _git(repository, "merge", "--ff-only", after)
    elif local != after:
        raise ScopedCandidateError("SCOPED_CANDIDATE.CAS_CONFLICT", "local integration branch is neither expected parent nor candidate")
    if _git(repository, "rev-parse", ref).stdout.strip() != after:
        raise ScopedCandidateError("SCOPED_CANDIDATE.CAS_CONFLICT", "local fast-forward did not land on the candidate")
    _validated_admission(repository, admission_ref, policy_path, admission_digest)
    validate_integration_publish_origin(repository, remote)
    publish_env = os.environ.copy()
    publish_env.pop("QWQ_ACCEPTANCE_PUBLISH", None)
    publish_env["QWQ_PUBLISH_ADMISSION_REF"] = admission_ref.relative_to(root).as_posix()
    publish_env["QWQ_PUBLISH_ADMISSION_DIGEST"] = admission_digest
    push = subprocess.run(
        ["git", "push", f"--force-with-lease={ref}:{before}", remote, f"{ref}:{ref}"],
        cwd=repository, text=True, capture_output=True, check=False,
        env=publish_env,
    )
    observed = _remote_ref_oid(repository, remote, ref)
    state = _terminal_readback(before=before, after=after, readback=observed or "")
    if state != "after":
        detail = " ".join((push.stderr or push.stdout).split())[:400]
        code = "SCOPED_CANDIDATE.CAS_CONFLICT" if state == "other" else "SCOPED_CANDIDATE.PUBLISHER_UNAVAILABLE"
        raise ScopedCandidateError(code, f"publish terminal readback is {state}: {detail}")
    result: dict[str, Any] = {
        "schema": _PUBLISH_RESULT_SCHEMA,
        "admission": {"ref": admission_ref.resolve().relative_to(root).as_posix(), "digest": exact_digest(admission_ref)},
        "admissionId": admission["admissionId"],
        "targetRef": ref,
        "beforeOid": before,
        "afterOid": after,
        "readbackOid": observed,
        "publisherReceipt": {
            "channel": "integration_worktree_fast_forward",
            "remote": remote,
            "branch": branch,
            "pushExitCode": push.returncode,
            "worktree": str(repository),
        },
        "terminal": "published",
        "createdAt": _utc_now(),
    }
    result["publishResultId"] = exact_digest(result)
    return _write_create_once(root / "publish-results" / f"{result['publishResultId']}.json", result)
