# spec_ref: specs/feature-tree/runtime/development-workflow-governance/shared-worktree-scoped-candidate/spec.md#gwt-001.t1
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/shared-worktree-scoped-candidate/spec.md#gwt-001.t2
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
    create_publish_admission,
    exact_digest,
    hosted_broker_cas_publish,
    local_ref_cas_publish,
)

ROOT = Path(__file__).resolve().parents[4]
POLICY = ROOT / "quwoquan_ops/policies/scoped_candidate_policy.yaml"
DIGEST = "sha256:" + "a" * 64


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
    path = target / name
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return {"ref": name, "digest": exact_digest(path)}


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
    candidate_exact = {"ref": str(candidate_ref.relative_to(target)), "digest": exact_digest(candidate_ref)}
    source = write_fact(target, "source.json", {"status": "passed", "candidateId": candidate["candidateId"]})
    alpha = write_fact(target, "alpha.json", environment_fact(candidate, "alpha", "passed"))
    beta = write_fact(target, "beta.json", environment_fact(candidate, "beta", "not_required"))
    admission_ref = create_publish_admission(
        repository=target, policy_path=POLICY, candidate_ref=candidate_exact,
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
        candidate_ref={"ref": str(candidate_ref.relative_to(target)), "digest": exact_digest(candidate_ref)},
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
        candidate_ref={"ref": str(candidate_ref.relative_to(target)), "digest": exact_digest(candidate_ref)},
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
