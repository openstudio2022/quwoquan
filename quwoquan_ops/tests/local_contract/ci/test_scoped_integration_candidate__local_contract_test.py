# spec_ref: specs/feature-tree/runtime/development-workflow-governance/shared-worktree-scoped-candidate/spec.md#gwt-001.t1
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/shared-worktree-scoped-candidate/spec.md#gwt-001.t2
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-001.t3
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-001.t4
from __future__ import annotations

import hashlib
import json
import subprocess
from io import BytesIO
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from quwoquan_ops.ci.scoped_candidate import (
    ScopedCandidateError,
    acquire_claim,
    build_candidate,
    build_head_candidate,
    create_publish_admission,
    create_source_fact,
    exact_digest,
    hosted_broker_cas_publish,
    local_git_cas_publish,
    local_ref_cas_publish,
    store_ref,
    store_root,
)

ROOT = Path(__file__).resolve().parents[4]
POLICY = ROOT / "quwoquan_ops/policies/scoped_candidate_policy.yaml"
DIGEST = "sha256:" + "a" * 64
OWNER = "evidence-fingerprint-v1:sha256:" + "b" * 64


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=True)
    return completed.stdout.strip()


def repo(tmp_path: Path) -> tuple[Path, str]:
    target = tmp_path / "repo"
    target.mkdir()
    git(target, "init", "-b", "dev1.0")
    git(target, "config", "user.name", "Test")
    git(target, "config", "user.email", "test@example.com")
    (target / "owned.txt").write_text("before\n")
    (target / "foreign.txt").write_text("before\n")
    git(target, "add", ".")
    git(target, "commit", "-m", "initial")
    return target, git(target, "rev-parse", "HEAD")


def claim(target: Path, parent: str, paths: list[str], writer: str = "writer-1") -> Path:
    return acquire_claim(
        repository=target, policy_path=POLICY, writer_id=writer,
        owner_identity_ref="evidence-fingerprint-v1:sha256:" + "b" * 64,
        expected_parent=parent, paths=paths,
        expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    )


def test_claims_allow_disjoint_files_and_block_overlap(tmp_path: Path) -> None:
    target, parent = repo(tmp_path)
    claim(target, parent, ["owned.txt"])
    claim(target, parent, ["foreign.txt"], writer="writer-2")
    with pytest.raises(ScopedCandidateError, match="CLAIM_CONFLICT"):
        claim(target, parent, ["owned.txt"], writer="writer-3")


def test_private_index_candidate_contains_only_claimed_bytes(tmp_path: Path) -> None:
    target, parent = repo(tmp_path)
    default_index = Path(git(target, "rev-parse", "--git-path", "index"))
    if not default_index.is_absolute():
        default_index = target / default_index
    before_index = hashlib.sha256(default_index.read_bytes()).hexdigest()
    claim_ref = claim(target, parent, ["owned.txt"])
    (target / "owned.txt").write_text("candidate\n")
    (target / "foreign.txt").write_text("foreign writer\n")

    candidate_ref = build_candidate(
        repository=target, policy_path=POLICY, claim_ref=claim_ref,
        owner_identity_ref="evidence-fingerprint-v1:sha256:" + "b" * 64,
        impact_plan_digest=DIGEST, message="scoped candidate",
        author_name="Candidate", author_email="candidate@example.com",
    )
    candidate = json.loads(candidate_ref.read_text())

    assert git(target, "rev-parse", "HEAD") == parent
    assert hashlib.sha256(default_index.read_bytes()).hexdigest() == before_index
    assert git(target, "diff-tree", "--no-commit-id", "--name-only", "-r", candidate["commit"]) == "owned.txt"
    assert git(target, "show", f"{candidate['commit']}:owned.txt") == "candidate"
    assert git(target, "show", f"{candidate['commit']}:foreign.txt") == "before"
    assert (target / "foreign.txt").read_text() == "foreign writer\n"


def write_fact(target: Path, name: str, payload: dict[str, object]) -> dict[str, str]:
    # 链内 ref 一律相对唯一 store root，而不是 worktree 根。
    path = store_root(repository=target, policy_path=POLICY) / name
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return {"ref": name, "digest": exact_digest(path)}


def candidate_exact(target: Path, candidate_ref: Path) -> dict[str, str]:
    return store_ref(repository=target, policy_path=POLICY, path=candidate_ref)


def environment_fact(candidate: dict[str, object], environment: str, status: str) -> dict[str, object]:
    return {
        "schema": "quwoquan_ops.environment_acceptance_fact.v2",
        "environment": environment,
        "status": status,
        "candidate": {
            "candidateId": candidate["candidateId"],
            "commit": candidate["commit"],
            "tree": candidate["tree"],
        },
        "signer": {"identity": "spiffe://quwoquan.local/environment-ops", "signature": "dsse:test"},
        "expiresAt": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        "cleanupEvidence": {"ref": "cleanup.json", "digest": DIGEST},
        "leaseClosureEvidence": {"ref": "lease.json", "digest": DIGEST},
        **({"reasonCode": "IMPACT_PLAN.NO_LIVE_ENVIRONMENT_REQUIRED"} if status == "not_required" else {}),
    }


def test_publish_admission_and_local_cas_have_one_winner(tmp_path: Path) -> None:
    target, parent = repo(tmp_path)
    claim_ref = claim(target, parent, ["owned.txt"])
    (target / "owned.txt").write_text("candidate\n")
    candidate_ref = build_candidate(
        repository=target, policy_path=POLICY, claim_ref=claim_ref,
        owner_identity_ref="evidence-fingerprint-v1:sha256:" + "b" * 64,
        impact_plan_digest=DIGEST, message="candidate", author_name="Candidate", author_email="candidate@example.com",
    )
    candidate = json.loads(candidate_ref.read_text())
    candidate_exact_ref = candidate_exact(target, candidate_ref)
    source = write_fact(target, "source.json", {"status": "passed", "candidateId": candidate["candidateId"]})
    alpha = write_fact(target, "alpha.json", environment_fact(candidate, "alpha", "passed"))
    beta = write_fact(target, "beta.json", environment_fact(candidate, "beta", "not_required"))
    admission_ref = create_publish_admission(
        repository=target, policy_path=POLICY, candidate_ref=candidate_exact_ref,
        source_fact_refs=[source], alpha_fact_ref=alpha, beta_fact_ref=beta,
        expected_remote_oid=parent,
    )

    result = local_ref_cas_publish(repository=target, admission_ref=admission_ref, allow_test_adapter=True)
    assert result["readback"] == candidate["commit"]
    with pytest.raises(ScopedCandidateError, match="CAS_CONFLICT"):
        local_ref_cas_publish(repository=target, admission_ref=admission_ref, allow_test_adapter=True)
    with pytest.raises(ScopedCandidateError, match="PUBLISHER_UNAVAILABLE"):
        local_ref_cas_publish(repository=target, admission_ref=admission_ref)


class BrokerResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._raw = BytesIO(json.dumps(payload).encode("utf-8"))

    def __enter__(self) -> "BrokerResponse":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self, amount: int = -1) -> bytes:
        return self._raw.read(amount)


def test_hosted_broker_publish_reconciles_unknown_mutation_outcome(tmp_path: Path) -> None:
    target, parent = repo(tmp_path)
    claim_ref = claim(target, parent, ["owned.txt"])
    (target / "owned.txt").write_text("candidate\n")
    candidate_ref = build_candidate(
        repository=target, policy_path=POLICY, claim_ref=claim_ref,
        owner_identity_ref="evidence-fingerprint-v1:sha256:" + "b" * 64,
        impact_plan_digest=DIGEST, message="candidate", author_name="Candidate", author_email="candidate@example.com",
    )
    candidate = json.loads(candidate_ref.read_text())
    source = write_fact(target, "source.json", {"status": "passed", "candidateId": candidate["candidateId"]})
    alpha = write_fact(target, "alpha.json", environment_fact(candidate, "alpha", "passed"))
    beta = write_fact(target, "beta.json", environment_fact(candidate, "beta", "not_required"))
    admission_ref = create_publish_admission(
        repository=target, policy_path=POLICY,
        candidate_ref=candidate_exact(target, candidate_ref),
        source_fact_refs=[source], alpha_fact_ref=alpha, beta_fact_ref=beta, expected_remote_oid=parent,
    )
    admission = json.loads(admission_ref.read_text())
    calls: list[str] = []

    def opener(request: object, *, timeout: float) -> BrokerResponse:
        del timeout
        method = str(getattr(request, "method"))
        calls.append(method)
        if method == "POST":
            raise TimeoutError("unknown mutation outcome")
        return BrokerResponse({
            "schema": "quwoquan_ops.integration_publisher_readback.v1",
            "admissionId": admission["admissionId"],
            "targetRef": "refs/heads/dev1.0",
            "beforeOid": parent,
            "afterOid": candidate["commit"],
            "readbackOid": candidate["commit"],
            "publisher": "github-app:integration-publisher",
        })

    result_ref = hosted_broker_cas_publish(
        repository=target, policy_path=POLICY, admission_ref=admission_ref,
        broker_url="https://publisher.example.invalid/v1/integration-publishes",
        token_provider=lambda: "oidc-token", opener=opener,
    )
    result = json.loads(result_ref.read_text())
    assert calls == ["POST", "GET"]
    assert result["terminal"] == "published"
    assert result["readbackOid"] == candidate["commit"]


def test_hosted_broker_publish_blocks_before_and_other_readback(tmp_path: Path) -> None:
    target, parent = repo(tmp_path)
    claim_ref = claim(target, parent, ["owned.txt"])
    (target / "owned.txt").write_text("candidate\n")
    candidate_ref = build_candidate(
        repository=target, policy_path=POLICY, claim_ref=claim_ref,
        owner_identity_ref="evidence-fingerprint-v1:sha256:" + "b" * 64,
        impact_plan_digest=DIGEST, message="candidate", author_name="Candidate", author_email="candidate@example.com",
    )
    candidate = json.loads(candidate_ref.read_text())
    source = write_fact(target, "source.json", {"status": "passed", "candidateId": candidate["candidateId"]})
    alpha = write_fact(target, "alpha.json", environment_fact(candidate, "alpha", "passed"))
    beta = write_fact(target, "beta.json", environment_fact(candidate, "beta", "not_required"))
    admission_ref = create_publish_admission(
        repository=target, policy_path=POLICY,
        candidate_ref=candidate_exact(target, candidate_ref),
        source_fact_refs=[source], alpha_fact_ref=alpha, beta_fact_ref=beta, expected_remote_oid=parent,
    )
    admission = json.loads(admission_ref.read_text())

    for observed, code in ((parent, "PUBLISHER_UNAVAILABLE"), ("f" * 40, "CAS_CONFLICT")):
        calls = 0
        def opener(request: object, *, timeout: float) -> BrokerResponse:
            nonlocal calls
            del timeout
            calls += 1
            if calls == 1:
                raise TimeoutError("unknown")
            return BrokerResponse({"admissionId": admission["admissionId"], "readbackOid": observed})
        with pytest.raises(ScopedCandidateError, match=code):
            hosted_broker_cas_publish(
                repository=target, policy_path=POLICY, admission_ref=admission_ref,
                broker_url="https://publisher.example.invalid/v1/integration-publishes",
                token_provider=lambda: "oidc-token", opener=opener,
            )


def committed_candidate(target: Path) -> tuple[str, str]:
    """在 dev1.0 上再落一个提交作为 integration 通道候选，返回 (parent, commit)。"""
    parent = git(target, "rev-parse", "HEAD")
    (target / "owned.txt").write_text("head candidate\n")
    git(target, "add", ".")
    git(target, "commit", "-m", "head candidate")
    return parent, git(target, "rev-parse", "HEAD")


def test_build_head_candidate_binds_exact_commit_and_changed_scope(tmp_path: Path) -> None:
    target, _ = repo(tmp_path)
    parent, commit = committed_candidate(target)
    expires = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    candidate_ref = build_head_candidate(
        repository=target, policy_path=POLICY, commit=commit, expected_parent=parent,
        owner_identity_ref=OWNER, impact_plan_digest=DIGEST, writer_id="integration", expires_at=expires,
    )
    candidate = json.loads(candidate_ref.read_text())
    assert candidate["schema"] == "quwoquan_ops.exact_integration_candidate.v1"
    assert candidate["commit"] == commit and candidate["expectedParent"] == parent
    assert candidate["tree"] == git(target, "show", "-s", "--format=%T", commit)
    assert candidate["paths"] == ["owned.txt"]
    # 同 scope 的并行 writer 仍被 claim generation 拒绝
    with pytest.raises(ScopedCandidateError, match="CLAIM_CONFLICT"):
        claim(target, parent, ["owned.txt"], writer="writer-2")
    # 非 fast-forward 候选（parent 不是祖先）不能成为 candidate
    git(target, "checkout", "-q", "-b", "side", parent)
    (target / "foreign.txt").write_text("side\n")
    git(target, "add", ".")
    git(target, "commit", "-m", "side")
    side = git(target, "rev-parse", "HEAD")
    with pytest.raises(ScopedCandidateError, match="CAS_CONFLICT"):
        build_head_candidate(
            repository=target, policy_path=POLICY, commit=side, expected_parent=commit,
            owner_identity_ref=OWNER, impact_plan_digest=DIGEST, writer_id="integration-2", expires_at=expires,
        )


def test_source_fact_binds_receipt_to_candidate_and_keeps_receipt_verdict(tmp_path: Path) -> None:
    target, _ = repo(tmp_path)
    parent, commit = committed_candidate(target)
    expires = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    candidate_ref = build_head_candidate(
        repository=target, policy_path=POLICY, commit=commit, expected_parent=parent,
        owner_identity_ref=OWNER, impact_plan_digest=DIGEST, writer_id="integration", expires_at=expires,
    )
    receipt = target / ".qwq_output/env/repo/local/local-readiness/receipt.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text('{"result":"ok"}\n')
    fact_ref = create_source_fact(
        repository=target, policy_path=POLICY, candidate_ref=candidate_exact(target, candidate_ref),
        kind="local_readiness_scope", receipt_path=receipt, status="passed",
    )
    fact = json.loads(fact_ref.read_text())
    assert fact["status"] == "passed" and fact["commit"] == commit
    assert fact["candidateId"] == json.loads(candidate_ref.read_text())["candidateId"]
    assert fact["receipt"]["digest"] == exact_digest(receipt)
    failed = create_source_fact(
        repository=target, policy_path=POLICY, candidate_ref=candidate_exact(target, candidate_ref),
        kind="commit_gate", receipt_path=receipt, status="failed",
    )
    alpha = write_fact(target, "alpha.json", environment_fact(json.loads(candidate_ref.read_text()), "alpha", "passed"))
    beta = write_fact(target, "beta.json", environment_fact(json.loads(candidate_ref.read_text()), "beta", "not_required"))
    with pytest.raises(ScopedCandidateError, match="STALE"):
        create_publish_admission(
            repository=target, policy_path=POLICY, candidate_ref=candidate_exact(target, candidate_ref),
            source_fact_refs=[store_ref(repository=target, policy_path=POLICY, path=failed)],
            alpha_fact_ref=alpha, beta_fact_ref=beta, expected_remote_oid=parent,
        )


def test_local_git_publish_is_expected_old_cas_with_readback(tmp_path: Path) -> None:
    target, _ = repo(tmp_path)
    remote = tmp_path / "hub.git"
    git(tmp_path, "init", "--bare", "-b", "dev1.0", str(remote))
    git(target, "remote", "add", "origin", str(remote))
    git(target, "push", "-q", "origin", "dev1.0")
    parent, commit = committed_candidate(target)
    expires = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    candidate_ref = build_head_candidate(
        repository=target, policy_path=POLICY, commit=commit, expected_parent=parent,
        owner_identity_ref=OWNER, impact_plan_digest=DIGEST, writer_id="integration", expires_at=expires,
    )
    candidate = json.loads(candidate_ref.read_text())
    source = write_fact(target, "source.json", {"status": "passed", "candidateId": candidate["candidateId"]})
    alpha = write_fact(target, "alpha.json", environment_fact(candidate, "alpha", "passed"))
    beta = write_fact(target, "beta.json", environment_fact(candidate, "beta", "not_required"))
    admission_ref = create_publish_admission(
        repository=target, policy_path=POLICY, candidate_ref=candidate_exact(target, candidate_ref),
        source_fact_refs=[source], alpha_fact_ref=alpha, beta_fact_ref=beta, expected_remote_oid=parent,
    )

    result_ref = local_git_cas_publish(repository=target, policy_path=POLICY, admission_ref=admission_ref)
    result = json.loads(result_ref.read_text())
    assert result["terminal"] == "published"
    assert result["beforeOid"] == parent and result["afterOid"] == commit == result["readbackOid"]
    assert result["publisherReceipt"]["channel"] == "integration_worktree_fast_forward"
    assert git(tmp_path, "--git-dir", str(remote), "rev-parse", "refs/heads/dev1.0") == commit
    # 远端已经是 after：不重复推送，报 STALE
    with pytest.raises(ScopedCandidateError, match="STALE"):
        local_git_cas_publish(repository=target, policy_path=POLICY, admission_ref=admission_ref)
    # 远端被其他 writer 移到 other：CAS 冲突，零写
    other = tmp_path / "other"
    git(tmp_path, "clone", "-q", "-b", "dev1.0", str(remote), str(other))
    git(other, "config", "user.name", "Other")
    git(other, "config", "user.email", "other@example.com")
    (other / "foreign.txt").write_text("other writer\n")
    git(other, "add", ".")
    git(other, "commit", "-q", "-m", "other")
    git(other, "push", "-q", "origin", "dev1.0")
    with pytest.raises(ScopedCandidateError, match="CAS_CONFLICT"):
        local_git_cas_publish(repository=target, policy_path=POLICY, admission_ref=admission_ref)
