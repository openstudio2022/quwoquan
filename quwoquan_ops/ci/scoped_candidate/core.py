"""Exact path claim、私有 Git index 与 ref CAS 的单轨实现。"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import secrets
import stat
import subprocess
import tempfile
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterator

import yaml

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
    for name in ("claims", "releases", "candidates", "admissions", "publish-results", "private-index"):
        child = root / name
        child.mkdir(exist_ok=True, mode=0o700)
        os.chmod(child, 0o700)
    return root


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
        "schema": _SCHEMA, "claimRef": str(claim_ref.relative_to(repository)),
        "claimDigest": exact_digest(claim_ref), "ownerIdentityRef": owner_identity_ref,
        "expectedParent": parent, "commit": commit, "tree": tree,
        "paths": list(paths), "pathsDigest": exact_digest({"paths": list(paths)}),
        "impactPlanDigest": impact_plan_digest, "createdAt": _utc_now(),
    }
    body["candidateId"] = exact_digest(body)
    return _write_create_once(root / "candidates" / f"{body['candidateId']}.json", body)


def _load_exact_ref(repository: Path, value: Mapping[str, str], label: str) -> tuple[dict[str, Any], str]:
    if not isinstance(value, Mapping) or set(value) != {"ref", "digest"}:
        raise ScopedCandidateError("SCOPED_CANDIDATE.INVALID", f"{label} must contain ref and digest")
    ref = _normalize_path(repository, value.get("ref"))
    expected = _digest(value.get("digest"), f"{label}.digest")
    path = repository / ref
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
    candidate, candidate_digest = _load_exact_ref(repository, candidate_ref, "candidate")
    if candidate.get("schema") != _SCHEMA:
        raise ScopedCandidateError("SCOPED_CANDIDATE.INVALID", "candidate schema is invalid")
    candidate_id = _digest(candidate.get("candidateId"), "candidateId")
    expected_remote_oid = _sha(expected_remote_oid, "expectedRemoteOid")
    if candidate.get("expectedParent") != expected_remote_oid:
        raise ScopedCandidateError("SCOPED_CANDIDATE.CAS_CONFLICT", "candidate parent does not equal remote-before")
    normalized_sources: list[dict[str, str]] = []
    if not source_fact_refs:
        raise ScopedCandidateError("SCOPED_CANDIDATE.INVALID", "at least one source fact is required")
    now = datetime.now(timezone.utc)
    for index, exact_ref in enumerate(source_fact_refs):
        fact, digest = _load_exact_ref(repository, exact_ref, f"sourceFacts[{index}]")
        if fact.get("status") != "passed" or fact.get("candidateId") != candidate_id:
            raise ScopedCandidateError("SCOPED_CANDIDATE.STALE", "source fact is not passed for this candidate")
        normalized_sources.append({"ref": exact_ref["ref"], "digest": digest})
    normalized_environment: dict[str, dict[str, str]] = {}
    for environment, exact_ref, allowed in (
        ("alpha", alpha_fact_ref, {"passed"}),
        ("beta", beta_fact_ref, {"passed", "not_required"}),
    ):
        fact, digest = _load_exact_ref(repository, exact_ref, environment)
        expires_at = fact.get("expiresAt")
        signer = fact.get("signer")
        candidate_binding = fact.get("candidate")
        if (
            fact.get("schema") != "quwoquan_ops.environment_acceptance_fact.v2"
            or fact.get("environment") != environment
            or fact.get("status") not in allowed
            or not isinstance(candidate_binding, Mapping)
            or candidate_binding.get("candidateId") != candidate_id
            or candidate_binding.get("commit") != candidate.get("commit")
            or candidate_binding.get("tree") != candidate.get("tree")
            or not isinstance(signer, Mapping)
            or not signer.get("identity")
            or not signer.get("signature")
            or not isinstance(expires_at, str)
        ):
            raise ScopedCandidateError("SCOPED_CANDIDATE.STALE", f"{environment} fact is not admissible for this candidate")
        try:
            expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ScopedCandidateError("SCOPED_CANDIDATE.STALE", f"{environment} fact expiry is invalid") from exc
        if expiry.tzinfo is None or expiry <= now:
            raise ScopedCandidateError("SCOPED_CANDIDATE.STALE", f"{environment} fact expired")
        if (
            not isinstance(fact.get("cleanupEvidence"), Mapping)
            or not isinstance(fact.get("leaseClosureEvidence"), Mapping)
        ):
            raise ScopedCandidateError(
                "SCOPED_CANDIDATE.STALE",
                f"{environment} cleanup or lease evidence is incomplete",
            )
        if fact.get("status") == "not_required" and fact.get("reasonCode") != "IMPACT_PLAN.NO_LIVE_ENVIRONMENT_REQUIRED":
            raise ScopedCandidateError("SCOPED_CANDIDATE.STALE", f"{environment} not_required reason is invalid")
        normalized_environment[environment] = {"ref": exact_ref["ref"], "digest": digest}
    body: dict[str, Any] = {
        "schema": _ADMISSION_SCHEMA, "candidate": {"ref": candidate_ref["ref"], "digest": candidate_digest},
        "candidateId": candidate_id, "expectedRemoteOid": expected_remote_oid,
        "targetRef": "refs/heads/dev1.0", "commit": candidate["commit"], "tree": candidate["tree"],
        "sourceFacts": normalized_sources, "environmentFacts": normalized_environment,
        "decision": "admitted", "createdAt": _utc_now(),
    }
    body["admissionId"] = exact_digest(body)
    return _write_create_once(root / "admissions" / f"{body['admissionId']}.json", body)


def _validated_admission(repository: Path, admission_ref: Path) -> dict[str, Any]:
    admission = _read_json(admission_ref)
    if admission.get("schema") != _ADMISSION_SCHEMA or admission.get("decision") != "admitted":
        raise ScopedCandidateError("SCOPED_CANDIDATE.INVALID", "publish admission is invalid")
    if admission.get("targetRef") != "refs/heads/dev1.0":
        raise ScopedCandidateError("SCOPED_CANDIDATE.INVALID", "publish ref drifted")
    _sha(admission.get("expectedRemoteOid"), "expectedRemoteOid")
    _sha(admission.get("commit"), "commit")
    _digest(admission.get("admissionId"), "admissionId")
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


def hosted_broker_cas_publish(
    *, repository: Path, policy_path: Path, admission_ref: Path,
    broker_url: str, token_provider: Callable[[], str],
    opener: Callable[..., object] = urllib.request.urlopen,
    timeout_seconds: float = 15.0,
) -> Path:
    """调用受信 publisher 一次，并用精确 readback 收敛未知网络结果。"""
    repository = _repo_root(repository)
    root = _claim_root(repository, policy_path)
    admission = _validated_admission(repository, admission_ref)
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
    request_body = canonical_bytes(
        {
            "schema": _ADMISSION_SCHEMA,
            "admission": {"ref": str(admission_ref.relative_to(repository)), "digest": admission_digest},
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
    if response_payload is not None and (
        not isinstance(response_payload, dict)
        or response_payload.get("admissionId") != admission["admissionId"]
        or response_payload.get("readbackOid") != after
    ):
        raise ScopedCandidateError("SCOPED_CANDIDATE.PUBLISHER_UNAVAILABLE", "publisher mutation response drifted")
    result: dict[str, Any] = {
        "schema": _PUBLISH_RESULT_SCHEMA,
        "admission": {"ref": str(admission_ref.relative_to(repository)), "digest": admission_digest},
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
