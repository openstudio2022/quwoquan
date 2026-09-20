# spec_ref: specs/feature-tree/runtime/development-workflow-governance/shared-worktree-scoped-candidate/spec.md#gwt-001.t1
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/shared-worktree-scoped-candidate/spec.md#gwt-001.t2
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-001.t3
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-001.t4
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-006.t1
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-006.t2
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-006.t3
from __future__ import annotations

import base64
import hashlib
import json
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier

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
    inspect_claims,
    local_git_cas_publish,
    local_ref_cas_publish,
    release_claim,
    store_ref,
    store_root,
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


def environment_fact(target: Path, candidate: dict[str, object], environment: str, status: str, *, prefix: str = "", reason_code: str | None = None) -> dict[str, object]:
    from quwoquan_ops.cli.lib.environment_acceptance_fact_contract import _EVIDENCE_ROLE_CONTRACT, DSSE_PAYLOAD_TYPE
    from quwoquan_ops.cli.lib.evidence_signing import ENVIRONMENT_OPS_IDENTITY, KEYRING_RELATIVE_PATH
    from quwoquan_ops.ci.environment_scheduler import dsse_pae
    from quwoquan_ops.tests.support.evidence_signing_test_support import create_temporary_signing
    signing = create_temporary_signing(target / ".qwq_output/signing")
    keyring = target / KEYRING_RELATIVE_PATH
    keyring.parent.mkdir(parents=True, exist_ok=True)
    keyring.write_bytes(signing.keyring_path.read_bytes())
    now = datetime.now(timezone.utc)
    binding = {key: candidate[key] for key in ("candidateId", "commit", "tree")}
    roles = {field: write_fact(target, f"{prefix}{environment}-{role}.json", {
        "role": role, "status": sorted(statuses)[0], "environment": environment,
        "profile": "integration", "impactPlanDigest": DIGEST, **binding,
    }) for field, (role, statuses) in _EVIDENCE_ROLE_CONTRACT.items()}
    case = write_fact(target, f"{prefix}{environment}-case.json", {
        "objectId": "admission-case", "specRef": "specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-002.t1",
        "caseId": "admission-case", "producer": "ops", "layer": "environment_acceptance", "status": "passed",
        "target": {"kind": "operation", "id": "admission-case"}, "commitSha": candidate["commit"],
        "contractGraphSourceHash": "4" * 64, "deploymentTarget": f"{environment}-local", "baselineId": "admission-test",
        "packageDigest": DIGEST, "configurationDigest": DIGEST, "candidateManifestSha256": "7" * 64,
        "candidateDigest": candidate["candidateId"], "environment": environment, "provider": "first-party-https",
        "startedAt": now.isoformat(), "completedAt": now.isoformat(), "runnerIdentity": "environment-scheduler",
        "artifactSha256": "8" * 64, "receiptRef": f"environment/{environment}/case.json",
    })
    root = store_root(repository=target, policy_path=POLICY)
    body = {
        "schema": "quwoquan_ops.environment_acceptance_fact.v2", "environment": environment,
        "status": status, "profile": "integration", "candidate": binding, "impactPlanDigest": DIGEST,
        "caseResultRefs": [case], **roles, "nonPromotable": False,
        "predecessor": None if environment == "alpha" else {"ref": f"{prefix}alpha.json", "digest": exact_digest(root / f"{prefix}alpha.json")},
        "issuedAt": (now - timedelta(minutes=1)).isoformat(), "expiresAt": (now + timedelta(hours=1)).isoformat(),
        **({"reasonCode": reason_code or "IMPACT_PLAN.NO_LIVE_ENVIRONMENT_REQUIRED"} if status == "not_required" else {}),
    }
    payload = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    body["signer"] = {"identity": ENVIRONMENT_OPS_IDENTITY, "payloadType": DSSE_PAYLOAD_TYPE,
        "payload": base64.b64encode(payload).decode(), "signature": signing.signer(ENVIRONMENT_OPS_IDENTITY)(dsse_pae(DSSE_PAYLOAD_TYPE, payload))}
    body["factId"] = exact_digest(body)
    return body


@pytest.fixture
def source_receipt_boundary(monkeypatch: pytest.MonkeyPatch):
    """只隔离昂贵 readiness 执行；不替换 admission/EAF/签名验证或 source wrapper 绑定。"""
    from quwoquan_ops.ci.scoped_candidate import core
    monkeypatch.setattr(core, "_validate_source_receipt", lambda *args: None)


def source_fact(target: Path, candidate: dict[str, object], candidate_ref: Path, *, prefix: str = "") -> dict[str, str]:
    receipt = target / f".qwq_output/{prefix}receipt.json"
    receipt.write_text('{"status":"PASS"}\n')
    body = {"schema": "quwoquan_ops.integration_source_fact.v1", "kind": "local_readiness_scope", "status": "passed",
        **{key: candidate[key] for key in ("candidateId", "commit", "tree", "expectedParent", "pathsDigest")},
        "candidate": candidate_exact(target, candidate_ref), "receipt": {"ref": receipt.relative_to(target).as_posix(), "digest": exact_digest(receipt)},
        "createdAt": datetime.now(timezone.utc).isoformat()}
    body["sourceFactId"] = exact_digest(body)
    return write_fact(target, f"{prefix}source.json", body)


def independent_admission(target: Path, candidate_ref: Path, prefix: str) -> Path:
    """各候选的回执、source、EAF 及其引用分别落盘；仅共享临时签名信任根。"""
    candidate = json.loads(candidate_ref.read_text())
    source = source_fact(target, candidate, candidate_ref, prefix=prefix)
    alpha = write_fact(target, f"{prefix}alpha.json", environment_fact(target, candidate, "alpha", "passed", prefix=prefix))
    beta = write_fact(target, f"{prefix}beta.json", environment_fact(target, candidate, "beta", "not_required", prefix=prefix))
    return create_publish_admission(
        repository=target, policy_path=POLICY, candidate_ref=candidate_exact(target, candidate_ref),
        source_fact_refs=[source], alpha_fact_ref=alpha, beta_fact_ref=beta,
        expected_remote_oid=candidate["expectedParent"],
    )


@pytest.fixture
def competing_admissions(tmp_path: Path, source_receipt_boundary) -> tuple[Path, str, list[Path]]:
    """真实 Git/签名合同夹具，不代表完整 readiness 或真实 Alpha/Beta 环境验收。"""
    target, parent = repo(tmp_path)
    admissions = []
    for label, owned_path in (("a", "owned.txt"), ("b", "foreign.txt")):
        claimed = claim(target, parent, [owned_path], writer=label)
        (target / owned_path).write_text(f"candidate {label}\n")
        candidate_ref = build_candidate(
            repository=target, policy_path=POLICY, claim_ref=claimed,
            impact_plan_digest=DIGEST, message=label, author_name="Test", author_email="test@example.com",
        )
        admissions.append(independent_admission(target, candidate_ref, f"{label}-"))
    bodies = [json.loads(path.read_text()) for path in admissions]
    for key in ("candidateId", "commit", "tree", "admissionId"):
        assert bodies[0][key] != bodies[1][key]
    root = store_root(repository=target, policy_path=POLICY)
    for body in bodies:
        assert body["expectedRemoteOid"] == parent
        assert git(target, "rev-parse", f"{body['commit']}^") == parent
        beta = json.loads((root / body["environmentFacts"]["beta"]["ref"]).read_text())
        assert beta["status"] == "not_required"
        assert beta["reasonCode"] == "IMPACT_PLAN.NO_LIVE_ENVIRONMENT_REQUIRED"
        assert beta["predecessor"] == body["environmentFacts"]["alpha"]
    return target, parent, admissions


def test_distinct_admissions_compete_at_atomic_git_cas(competing_admissions, monkeypatch: pytest.MonkeyPatch) -> None:
    target, parent, admissions = competing_admissions
    root = store_root(repository=target, policy_path=POLICY)
    # B 已创建后再次验真 A；引用不能通过覆盖共同 source/EAF 文件来换绑。
    before_facts = {path: path.read_bytes() for path in root.glob("*.json")}
    receipts = {path: path.read_bytes() for path in (target / ".qwq_output").glob("*-receipt.json")}
    assert len(receipts) == 2
    barrier = Barrier(2, timeout=20)
    real_run = subprocess.run
    updates = {}

    def synchronized_run(args, **kwargs):
        if args[:2] != ["git", "update-ref"]:
            return real_run(args, **kwargs)
        assert args[2] == "refs/heads/dev1.0" and args[4] == parent
        # 两方都完成真实 admission/签名校验和旧 ref 读取，再同时进入 Git 原子 CAS。
        barrier.wait()
        completed = real_run(args, **kwargs)
        updates[args[3]] = completed
        return completed

    def publish(path):
        try:
            return local_ref_cas_publish(repository=target, admission_ref=path, allow_test_adapter=True)
        except ScopedCandidateError as error:
            return error

    with monkeypatch.context() as race_patch:
        race_patch.setattr(subprocess, "run", synchronized_run)
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(publish, admissions))
    winners = [result for result in outcomes if isinstance(result, dict)]
    losers = [result for result in outcomes if isinstance(result, ScopedCandidateError)]
    assert len(winners) == len(losers) == 1
    winner = winners[0]
    assert winner == {"before": parent, "after": winner["after"], "readback": winner["after"], "terminal": "published"}
    assert losers[0].code == "SCOPED_CANDIDATE.CAS_CONFLICT"
    assert "make accept PUBLISH=1 SYNC=1" in losers[0].detail
    assert len(updates) == 2
    assert updates[winner["after"]].returncode == 0
    loser_commit = next(commit for commit in updates if commit != winner["after"])
    assert updates[loser_commit].returncode != 0
    assert git(target, "rev-parse", "refs/heads/dev1.0") == winner["after"]
    loser_admission = next(path for path in admissions if json.loads(path.read_text())["commit"] == loser_commit)
    with pytest.raises(ScopedCandidateError, match="CAS_CONFLICT"):
        local_ref_cas_publish(repository=target, admission_ref=loser_admission, allow_test_adapter=True)
    assert git(target, "rev-parse", "refs/heads/dev1.0") == winner["after"]
    assert all(path.read_bytes() == contents for path, contents in {**before_facts, **receipts}.items())


@pytest.mark.parametrize("donor", [0, 1], ids=["candidate-a", "candidate-b"])
@pytest.mark.parametrize("old_fact", ["source", "alpha", "beta"])
def test_merged_candidate_rejects_each_old_fact(competing_admissions, donor: int, old_fact: str) -> None:
    target, parent, admissions = competing_admissions
    root = store_root(repository=target, policy_path=POLICY)
    bodies = [json.loads(path.read_text()) for path in admissions]
    before_facts = {path: path.read_bytes() for path in root.glob("*.json")}
    a, b = (body["commit"] for body in bodies)
    tree = git(target, "merge-tree", "--write-tree", a, b)
    commit = git(target, "commit-tree", tree, "-p", a, "-p", b, "-m", "combine A and B")
    assert git(target, "show", "-s", "--format=%P", commit) == f"{a} {b}"
    assert git(target, "show", f"{commit}:owned.txt") == "candidate a"
    assert git(target, "show", f"{commit}:foreign.txt") == "candidate b"
    for body in bodies:
        candidate = json.loads((root / body["candidate"]["ref"]).read_text())
        release_claim(repository=target, policy_path=POLICY, claim_ref=root / candidate["claimRef"], reason="combine candidates")
    merged_ref = build_head_candidate(
        repository=target, policy_path=POLICY, commit=commit, expected_parent=parent,
 impact_plan_digest=DIGEST, writer_id="merged",
        expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    )
    # 先用 C 自己的完整签名事实准入，避免负例被无效夹具提前拒绝。
    merged_admission = independent_admission(target, merged_ref, "c-")
    merged = json.loads(merged_admission.read_text())
    old = bodies[donor]
    sources = old["sourceFacts"] if old_fact == "source" else merged["sourceFacts"]
    environments = {**merged["environmentFacts"]}
    if old_fact != "source":
        environments[old_fact] = old["environmentFacts"][old_fact]
    before_admissions = set((root / "admissions").iterdir())
    with pytest.raises(ScopedCandidateError, match="binding drifted|candidate/impact/predecessor drifted") as rejected:
        create_publish_admission(
            repository=target, policy_path=POLICY, candidate_ref=merged["candidate"],
            source_fact_refs=sources, alpha_fact_ref=environments["alpha"], beta_fact_ref=environments["beta"],
            expected_remote_oid=parent,
        )
    assert rejected.value.code == "SCOPED_CANDIDATE.STALE"
    assert set((root / "admissions").iterdir()) == before_admissions
    assert all(path.read_bytes() == contents for path, contents in before_facts.items())
    assert git(target, "rev-parse", "refs/heads/dev1.0") == parent
    result = local_ref_cas_publish(repository=target, admission_ref=merged_admission, allow_test_adapter=True)
    assert result["readback"] == commit


def test_same_admission_replay_is_rejected(tmp_path: Path, source_receipt_boundary) -> None:
    target, parent = repo(tmp_path)
    claim_ref = claim(target, parent, ["owned.txt"])
    (target / "owned.txt").write_text("candidate\n")
    candidate_ref = build_candidate(
        repository=target, policy_path=POLICY, claim_ref=claim_ref,
        impact_plan_digest=DIGEST, message="candidate", author_name="Candidate", author_email="candidate@example.com",
    )
    candidate = json.loads(candidate_ref.read_text())
    candidate_exact_ref = candidate_exact(target, candidate_ref)
    source = source_fact(target, candidate, candidate_ref)
    alpha = write_fact(target, "alpha.json", environment_fact(target, candidate, "alpha", "passed"))
    beta = write_fact(target, "beta.json", environment_fact(target, candidate, "beta", "not_required"))
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


def test_source_admitted_alpha_deferred_can_create_admission(tmp_path: Path, source_receipt_boundary) -> None:
    from quwoquan_ops.cli.lib.environment_acceptance_fact_contract import ALPHA_LIVE_DEFERRED_TO_PUBLISHED_DEV

    target, parent = repo(tmp_path)
    claim_ref = claim(target, parent, ["owned.txt"])
    (target / "owned.txt").write_text("candidate\n")
    candidate_ref = build_candidate(
        repository=target, policy_path=POLICY, claim_ref=claim_ref,
        impact_plan_digest=DIGEST, message="deferred-alpha", author_name="Candidate", author_email="candidate@example.com",
    )
    candidate = json.loads(candidate_ref.read_text())
    source = source_fact(target, candidate, candidate_ref)
    alpha = write_fact(
        target, "alpha.json",
        environment_fact(target, candidate, "alpha", "not_required", reason_code=ALPHA_LIVE_DEFERRED_TO_PUBLISHED_DEV),
    )
    beta = write_fact(target, "beta.json", environment_fact(target, candidate, "beta", "not_required"))
    admission_ref = create_publish_admission(
        repository=target, policy_path=POLICY, candidate_ref=candidate_exact(target, candidate_ref),
        source_fact_refs=[source], alpha_fact_ref=alpha, beta_fact_ref=beta,
        expected_remote_oid=parent,
    )
    body = json.loads(admission_ref.read_text())
    assert body["decision"] == "admitted"
    wrong = write_fact(
        target, "alpha-wrong.json",
        environment_fact(target, candidate, "alpha", "not_required", prefix="wrong-", reason_code="ACCEPTANCE.BETA_OPTIONAL_BY_POLICY"),
    )
    with pytest.raises(ScopedCandidateError, match="ALPHA_LIVE_DEFERRED|typed"):
        create_publish_admission(
            repository=target, policy_path=POLICY, candidate_ref=candidate_exact(target, candidate_ref),
            source_fact_refs=[source], alpha_fact_ref=wrong, beta_fact_ref=beta,
            expected_remote_oid=parent,
        )


class BrokerResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._raw = BytesIO(json.dumps(payload).encode("utf-8"))

    def __enter__(self) -> "BrokerResponse":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self, amount: int = -1) -> bytes:
        return self._raw.read(amount)


def test_hosted_broker_publish_reconciles_unknown_mutation_outcome(tmp_path: Path, source_receipt_boundary) -> None:
    target, parent = repo(tmp_path)
    claim_ref = claim(target, parent, ["owned.txt"])
    (target / "owned.txt").write_text("candidate\n")
    candidate_ref = build_candidate(
        repository=target, policy_path=POLICY, claim_ref=claim_ref,
        impact_plan_digest=DIGEST, message="candidate", author_name="Candidate", author_email="candidate@example.com",
    )
    candidate = json.loads(candidate_ref.read_text())
    source = source_fact(target, candidate, candidate_ref)
    alpha = write_fact(target, "alpha.json", environment_fact(target, candidate, "alpha", "passed"))
    beta = write_fact(target, "beta.json", environment_fact(target, candidate, "beta", "not_required"))
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


def test_hosted_broker_publish_blocks_before_and_other_readback(tmp_path: Path, source_receipt_boundary) -> None:
    target, parent = repo(tmp_path)
    claim_ref = claim(target, parent, ["owned.txt"])
    (target / "owned.txt").write_text("candidate\n")
    candidate_ref = build_candidate(
        repository=target, policy_path=POLICY, claim_ref=claim_ref,
        impact_plan_digest=DIGEST, message="candidate", author_name="Candidate", author_email="candidate@example.com",
    )
    candidate = json.loads(candidate_ref.read_text())
    source = source_fact(target, candidate, candidate_ref)
    alpha = write_fact(target, "alpha.json", environment_fact(target, candidate, "alpha", "passed"))
    beta = write_fact(target, "beta.json", environment_fact(target, candidate, "beta", "not_required"))
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


def admitted_fixture(tmp_path: Path) -> tuple[Path, Path]:
    target, parent = repo(tmp_path)
    claimed = claim(target, parent, ["owned.txt"])
    (target / "owned.txt").write_text("candidate\n")
    path = build_candidate(repository=target, policy_path=POLICY, claim_ref=claimed,
        impact_plan_digest=DIGEST, message="candidate", author_name="Test", author_email="test@example.com")
    candidate = json.loads(path.read_text())
    source = source_fact(target, candidate, path)
    alpha = write_fact(target, "alpha.json", environment_fact(target, candidate, "alpha", "passed"))
    beta = write_fact(target, "beta.json", environment_fact(target, candidate, "beta", "not_required"))
    admission = create_publish_admission(repository=target, policy_path=POLICY, candidate_ref=candidate_exact(target, path),
        source_fact_refs=[source], alpha_fact_ref=alpha, beta_fact_ref=beta, expected_remote_oid=parent)
    return target, admission


# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-008
@pytest.mark.parametrize("attack", [None, "claim", "receipt", "symlink", "missing-receipt", "fast"])
def test_portable_publish_prevalidation_is_read_only_and_uses_full_chain(
    tmp_path: Path, source_receipt_boundary, attack: str | None,
) -> None:
    from quwoquan_ops.ci.scoped_candidate import core
    target, path = admitted_fixture(tmp_path)
    body = json.loads(path.read_text())
    root = store_root(repository=target, policy_path=POLICY)
    bundle = tmp_path / "portable"
    sealed_store = bundle / "store"
    shutil.copytree(root, sealed_store)
    source = json.loads((sealed_store / body["sourceFacts"][0]["ref"]).read_text())
    receipt_ref = source["receipt"]
    receipt_path = bundle / "repository" / receipt_ref["ref"]
    receipt_path.parent.mkdir(parents=True)
    receipt_path.write_bytes((target / receipt_ref["ref"]).read_bytes())
    candidate = json.loads((sealed_store / body["candidate"]["ref"]).read_text())
    if attack == "claim":
        (sealed_store / candidate["claimRef"]).write_text("{}")
    elif attack == "receipt":
        receipt_path.write_text("{}")
    elif attack == "symlink":
        receipt_path.unlink()
        receipt_path.symlink_to(target / receipt_ref["ref"])
    elif attack == "missing-receipt":
        receipt_path.unlink()
    elif attack == "fast":
        source["kind"] = "local_readiness_fast"
        source.pop("sourceFactId")
        source["sourceFactId"] = exact_digest(source)
        source_path = sealed_store / body["sourceFacts"][0]["ref"]
        source_path.write_text(json.dumps(source, sort_keys=True, separators=(",", ":")) + "\n")
        body["sourceFacts"][0]["digest"] = exact_digest(source_path)
    def snapshot(base: Path) -> dict[str, str]:
        return {p.relative_to(base).as_posix(): exact_digest(p) for p in base.rglob("*") if p.is_file()}
    before_store, before_bundle = snapshot(root), snapshot(bundle)
    before_ref, before_index = git(target, "rev-parse", "HEAD"), (target / ".git/index").read_bytes()
    inputs = dict(repository=target, store_root=sealed_store, candidate_ref=body["candidate"],
        source_fact_refs=body["sourceFacts"], alpha_fact_ref=body["environmentFacts"]["alpha"],
        beta_fact_ref=body["environmentFacts"]["beta"], expected_remote_oid=body["expectedRemoteOid"],
        receipt_root=bundle / "repository")
    if attack is None:
        assert core.validate_publish_inputs(**inputs) is None
    else:
        with pytest.raises(ScopedCandidateError):
            core.validate_publish_inputs(**inputs)
    assert snapshot(root) == before_store and snapshot(bundle) == before_bundle
    assert git(target, "rev-parse", "HEAD") == before_ref
    assert (target / ".git/index").read_bytes() == before_index


def rewrite_admission(path: Path, body: dict[str, object]) -> None:
    body.pop("admissionId", None)
    body["admissionId"] = exact_digest(body)
    path.write_text(json.dumps(body, sort_keys=True, separators=(",", ":")) + "\n")


@pytest.mark.parametrize("tamper", ["admissionId", "candidate-digest", "source-digest", "receipt", "signature", "expired", "future", "cleanup", "lease", "tree", "before", "ref"])
def test_final_publish_revalidates_entire_admission(tmp_path: Path, source_receipt_boundary, tamper: str) -> None:
    from quwoquan_ops.ci.scoped_candidate import core
    target, path = admitted_fixture(tmp_path)
    body = json.loads(path.read_text())
    root = store_root(repository=target, policy_path=POLICY)
    if tamper == "admissionId":
        body["admissionId"] = DIGEST
        path.write_text(json.dumps(body, sort_keys=True, separators=(",", ":")) + "\n")
    else:
        if tamper == "candidate-digest":
            body["candidate"]["digest"] = DIGEST
        elif tamper == "source-digest":
            body["sourceFacts"][0]["digest"] = DIGEST
        elif tamper == "receipt":
            (target / ".qwq_output/receipt.json").write_text('{"status":"FAIL"}\n')
        elif tamper in {"tree", "before", "ref"}:
            body[{"tree": "tree", "before": "expectedRemoteOid", "ref": "targetRef"}[tamper]] = "refs/heads/main" if tamper == "ref" else "f" * 40
        else:
            alpha = json.loads((root / "alpha.json").read_text())
            if tamper == "signature":
                alpha["signer"]["signature"] = "ed25519:" + base64.b64encode(b"0" * 64).decode()
            elif tamper in {"expired", "future"}:
                alpha["expiresAt" if tamper == "expired" else "issuedAt"] = (datetime.now(timezone.utc) + timedelta(hours=-2 if tamper == "expired" else 2)).isoformat()
            else:
                evidence = root / alpha["cleanupEvidence" if tamper == "cleanup" else "leaseClosureEvidence"]["ref"]
                evidence.write_text('{}\n')
            alpha.pop("factId")
            if tamper in {"expired", "future"}:
                from quwoquan_ops.tests.support.evidence_signing_test_support import create_temporary_signing
                from quwoquan_ops.ci.environment_scheduler import dsse_pae
                signer = alpha.pop("signer")
                payload = json.dumps(alpha, sort_keys=True, separators=(",", ":")).encode()
                signer["payload"] = base64.b64encode(payload).decode()
                signer["signature"] = create_temporary_signing(target / ".qwq_output/signing").signer(signer["identity"])(dsse_pae(signer["payloadType"], payload))
                alpha["signer"] = signer
            alpha["factId"] = exact_digest(alpha)
            body["environmentFacts"]["alpha"] = write_fact(target, "alpha.json", alpha)
        rewrite_admission(path, body)
    before = git(target, "rev-parse", "refs/heads/dev1.0")
    with pytest.raises(ScopedCandidateError):
        local_ref_cas_publish(repository=target, admission_ref=path, allow_test_adapter=True)
    assert git(target, "rev-parse", "refs/heads/dev1.0") == before
    with pytest.raises(ScopedCandidateError):
        hosted_broker_cas_publish(repository=target, policy_path=POLICY, admission_ref=path,
            broker_url="https://publisher.example.invalid", token_provider=lambda: pytest.fail("must reject before token/network"))


@pytest.mark.parametrize("entry", ["admit", "publish-local", "publish-broker"])
def test_direct_cli_cannot_bypass_admission_validation(tmp_path: Path, source_receipt_boundary, monkeypatch, entry: str) -> None:
    from quwoquan_ops.cli import integration_candidate as cli
    from quwoquan_ops.ci.scoped_candidate import core
    target, path = admitted_fixture(tmp_path)
    monkeypatch.setattr(cli, "ROOT", target)
    monkeypatch.setattr(cli, "POLICY", POLICY)
    monkeypatch.setattr(core, "validate_publish_worktree_origin", lambda *args: None)
    body = json.loads(path.read_text())
    (target / ".qwq_output/receipt.json").write_text('{"status":"FAIL"}\n')
    if entry == "admit":
        exact = lambda value: value["ref"] + "=" + value["digest"]
        args = ["admit", "--candidate", exact(body["candidate"]), "--source-fact", exact(body["sourceFacts"][0]),
            "--alpha-fact", exact(body["environmentFacts"]["alpha"]), "--beta-fact", exact(body["environmentFacts"]["beta"]),
            "--expected-remote-oid", body["expectedRemoteOid"]]
    else:
        args = ["publish", "--admission-ref", candidate_exact(target, path)["ref"]]
        if entry == "publish-broker":
            args += ["--adapter", "hosted-broker", "--broker-url", "https://publisher.example.invalid"]
    assert cli.main(args) == 1


@pytest.mark.parametrize("drift", [None, "before", "after", "ref", "digest"])
def test_hook_uses_same_exact_admission_chain(tmp_path: Path, source_receipt_boundary, monkeypatch, drift) -> None:
    from quwoquan_ops.ci.scoped_candidate import core
    from quwoquan_ops.gate import verify_git_branch_policy as gate
    target, path = admitted_fixture(tmp_path)
    body = json.loads(path.read_text())
    monkeypatch.setattr(gate, "ROOT", target)
    monkeypatch.setattr(core, "validate_publish_worktree_origin", lambda *args: None)
    # 临时仓库仅缺 policy 文件，不改变验证器。
    policy = target / "quwoquan_ops/policies/scoped_candidate_policy.yaml"
    policy.write_bytes(POLICY.read_bytes())
    exact = candidate_exact(target, path)
    env = {"QWQ_PUBLISH_ADMISSION_REF": exact["ref"], "QWQ_PUBLISH_ADMISSION_DIGEST": exact["digest"]}
    before, after, ref = body["expectedRemoteOid"], body["commit"], body["targetRef"]
    if drift == "before": before = "f" * 40
    if drift == "after": after = "f" * 40
    if drift == "ref": ref = "refs/heads/main"
    if drift == "digest": env["QWQ_PUBLISH_ADMISSION_DIGEST"] = DIGEST
    if drift:
        with pytest.raises(ScopedCandidateError):
            gate._verify_acceptance_update(env, before, after, ref, "origin", "remote")
    else:
        gate._verify_acceptance_update(env, before, after, ref, "origin", "remote")


@pytest.mark.parametrize("remote,url,push_urls", [("other", "url", ["url"]), ("origin", "other", ["url"]), ("origin", "url", ["url", "other"])])
def test_origin_identity_rejects_alias_url_and_multiple_targets(tmp_path: Path, monkeypatch, remote, url, push_urls) -> None:
    from quwoquan_ops.ci.scoped_candidate import core
    target = tmp_path / "integration"
    hub = tmp_path / "quwoquan.git"
    def fake_git(repository, *args, **kwargs):
        value = str(hub) if args[0] == "rev-parse" else "\n".join(push_urls) if args[0] == "remote" else "url"
        return subprocess.CompletedProcess(args, 0, value + "\n", "")
    monkeypatch.setattr(core, "_git", fake_git)
    with pytest.raises(ScopedCandidateError):
        core.validate_publish_worktree_origin(target, remote, url)


def test_local_publisher_rejects_noncanonical_worktree_before_network(tmp_path: Path, source_receipt_boundary, monkeypatch) -> None:
    from quwoquan_ops.ci.scoped_candidate import core
    target, path = admitted_fixture(tmp_path)
    monkeypatch.setattr(core, "_remote_ref_oid", lambda *args: pytest.fail("no network before identity validation"))
    with pytest.raises(ScopedCandidateError, match="canonical lane or integration worktree"):
        local_git_cas_publish(repository=target, policy_path=POLICY, admission_ref=path)


def test_final_publish_checks_ff_even_when_local_branch_already_is_candidate(tmp_path: Path, source_receipt_boundary, monkeypatch) -> None:
    from quwoquan_ops.ci.scoped_candidate import core
    target, path = admitted_fixture(tmp_path)
    body = json.loads(path.read_text())
    candidate_path = store_root(repository=target, policy_path=POLICY) / body["candidate"]["ref"]
    candidate = json.loads(candidate_path.read_text())
    git(target, "update-ref", "refs/heads/dev1.0", candidate["commit"])
    orphan = git(target, "commit-tree", candidate["tree"], "-m", "unrelated root")
    candidate["expectedParent"] = orphan
    candidate.pop("candidateId")
    candidate["candidateId"] = exact_digest(candidate)
    candidate_path.write_text(json.dumps(candidate, sort_keys=True, separators=(",", ":")) + "\n")
    body.update(expectedRemoteOid=orphan, candidateId=candidate["candidateId"], candidate=candidate_exact(target, candidate_path))
    rewrite_admission(path, body)
    monkeypatch.setattr(core, "validate_publish_worktree_origin", lambda *args: None)
    monkeypatch.setattr(core, "_remote_ref_oid", lambda *args: pytest.fail("FF must be checked before remote readback"))
    with pytest.raises(ScopedCandidateError, match="merge-base"):
        local_git_cas_publish(repository=target, policy_path=POLICY, admission_ref=path)


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
 impact_plan_digest=DIGEST, writer_id="integration", expires_at=expires,
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
 impact_plan_digest=DIGEST, writer_id="integration-2", expires_at=expires,
        )


def test_source_fact_binds_receipt_to_candidate_and_keeps_receipt_verdict(tmp_path: Path) -> None:
    target, _ = repo(tmp_path)
    parent, commit = committed_candidate(target)
    expires = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    candidate_ref = build_head_candidate(
        repository=target, policy_path=POLICY, commit=commit, expected_parent=parent,
 impact_plan_digest=DIGEST, writer_id="integration", expires_at=expires,
    )
    receipt = target / ".qwq_output/env/repo/local/local-readiness/receipt.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text('{"result":"ok"}\n')
    for kind, status in (("local_readiness_scope", "passed"), ("commit_gate", "failed")):
        with pytest.raises(ScopedCandidateError, match="SOURCE_RECEIPT"):
            create_source_fact(
                repository=target, policy_path=POLICY, candidate_ref=candidate_exact(target, candidate_ref),
                kind=kind, receipt_path=receipt, status=status,
            )
    assert list((store_root(repository=target, policy_path=POLICY) / "source-facts").iterdir()) == []


# spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-007.t4
@pytest.mark.parametrize("payload", [{"status": "FAIL"}, {"status": "PASS"}, {"result": "ok"}])
def test_source_fact_rejects_false_passed_wrapper(tmp_path: Path, payload: dict[str, object]) -> None:
    target, _ = repo(tmp_path)
    parent, commit = committed_candidate(target)
    candidate_ref = build_head_candidate(
        repository=target, policy_path=POLICY, commit=commit, expected_parent=parent,
 impact_plan_digest=DIGEST, writer_id="integration",
        expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    )
    receipt = target / ".qwq_output/receipt.json"
    receipt.write_text(json.dumps(payload))
    with pytest.raises(ScopedCandidateError, match="SOURCE_RECEIPT"):
        create_source_fact(repository=target, policy_path=POLICY,
                           candidate_ref=candidate_exact(target, candidate_ref),
                           kind="local_readiness_fast", receipt_path=receipt, status="passed")


def test_local_git_publish_is_expected_old_cas_with_readback(tmp_path: Path, source_receipt_boundary, monkeypatch: pytest.MonkeyPatch) -> None:
    from quwoquan_ops.ci.scoped_candidate import core
    # 本测试只覆盖 transport CAS；规范路径另有独立负向用例。
    monkeypatch.setattr(core, "validate_publish_worktree_origin", lambda *args: None)
    target, _ = repo(tmp_path)
    remote = tmp_path / "hub.git"
    git(tmp_path, "init", "--bare", "-b", "dev1.0", str(remote))
    git(target, "remote", "add", "origin", str(remote))
    git(target, "push", "-q", "origin", "dev1.0")
    parent, commit = committed_candidate(target)
    expires = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    candidate_ref = build_head_candidate(
        repository=target, policy_path=POLICY, commit=commit, expected_parent=parent,
 impact_plan_digest=DIGEST, writer_id="integration", expires_at=expires,
    )
    candidate = json.loads(candidate_ref.read_text())
    source = source_fact(target, candidate, candidate_ref)
    alpha = write_fact(target, "alpha.json", environment_fact(target, candidate, "alpha", "passed"))
    beta = write_fact(target, "beta.json", environment_fact(target, candidate, "beta", "not_required"))
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


# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-001
def test_publish_allows_non_overlapping_dirty_and_blocks_overlap(
    tmp_path: Path, source_receipt_boundary, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from quwoquan_ops.ci.scoped_candidate import core
    monkeypatch.setattr(core, "validate_publish_worktree_origin", lambda *args: None)
    target, _ = repo(tmp_path)
    remote = tmp_path / "hub.git"
    git(tmp_path, "init", "--bare", "-b", "dev1.0", str(remote))
    git(target, "remote", "add", "origin", str(remote))
    git(target, "push", "-q", "origin", "dev1.0")
    parent, commit = committed_candidate(target)
    candidate_ref = build_head_candidate(
        repository=target, policy_path=POLICY, commit=commit, expected_parent=parent,
impact_plan_digest=DIGEST, writer_id="integration",
        expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    )
    candidate = json.loads(candidate_ref.read_text())
    # lane 发布形态：HEAD 就是 candidate，脏树判定必须落在 expectedParent...candidate 上。
    source = source_fact(target, candidate, candidate_ref)
    alpha = write_fact(target, "alpha.json", environment_fact(target, candidate, "alpha", "passed"))
    beta = write_fact(target, "beta.json", environment_fact(target, candidate, "beta", "not_required"))
    admission_ref = create_publish_admission(
        repository=target, policy_path=POLICY, candidate_ref=candidate_exact(target, candidate_ref),
        source_fact_refs=[source], alpha_fact_ref=alpha, beta_fact_ref=beta, expected_remote_oid=parent,
    )
    (target / "owned.txt").write_text("dirty overlap\n")
    with pytest.raises(ScopedCandidateError, match="DIRTY_WORKTREE"):
        local_git_cas_publish(repository=target, policy_path=POLICY, admission_ref=admission_ref)
    git(target, "checkout", "--", "owned.txt")
    (target / "foreign.txt").write_text("gamma wip\n")
    (target / "unrelated.wip").write_text("untracked\n")
    result_ref = local_git_cas_publish(repository=target, policy_path=POLICY, admission_ref=admission_ref)
    assert json.loads(result_ref.read_text())["afterOid"] == commit
    assert (target / "foreign.txt").read_text() == "gamma wip\n"
    assert (target / "unrelated.wip").read_text() == "untracked\n"


def canonical_layout(tmp_path: Path) -> tuple[Path, Path, Path, str]:
    """搭出规范布局：bare hub + 同源 lane linked worktree + 独立 origin 远端。"""
    project = tmp_path / "project"
    seed = project / "seed"
    seed.mkdir(parents=True)
    git(seed, "init", "-b", "dev1.0")
    git(seed, "config", "user.name", "Test")
    git(seed, "config", "user.email", "test@example.com")
    (seed / "owned.txt").write_text("before\n")
    (seed / "foreign.txt").write_text("before\n")
    git(seed, "add", ".")
    git(seed, "commit", "-m", "initial")
    remote = project / "remote.git"
    git(project, "init", "--bare", "-b", "dev1.0", str(remote))
    git(seed, "remote", "add", "origin", str(remote))
    git(seed, "push", "-q", "origin", "dev1.0")
    hub = project / "quwoquan.git"
    git(project, "clone", "--bare", "-q", str(seed), str(hub))
    git(hub, "remote", "set-url", "origin", str(remote))
    git(hub, "config", "user.name", "Test")
    git(hub, "config", "user.email", "test@example.com")
    return project, hub, remote, git(hub, "rev-parse", "refs/heads/dev1.0")


def lane_candidate(hub: Path, project: Path, branch: str, parent: str, content: str) -> tuple[Path, str]:
    lane = project / branch.removeprefix("lane/")
    git(hub, "worktree", "add", "-q", "-b", branch, str(lane), parent)
    (lane / "owned.txt").write_text(content)
    git(lane, "add", "owned.txt")
    git(lane, "commit", "-m", f"{branch} candidate")
    return lane, git(lane, "rev-parse", "HEAD")


def lane_admission(lane: Path, parent: str, commit: str) -> Path:
    candidate_ref = build_head_candidate(
        repository=lane, policy_path=POLICY, commit=commit, expected_parent=parent,
impact_plan_digest=DIGEST, writer_id=lane.name,
        expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    )
    candidate = json.loads(candidate_ref.read_text())
    return create_publish_admission(
        repository=lane, policy_path=POLICY, candidate_ref=candidate_exact(lane, candidate_ref),
        source_fact_refs=[source_fact(lane, candidate, candidate_ref)],
        # 默认 source-admitted：两份 typed not_required，live Alpha 延后到已发布 dev。
        alpha_fact_ref=write_fact(lane, "alpha.json", environment_fact(
            lane, candidate, "alpha", "not_required", reason_code="ACCEPTANCE.ALPHA_LIVE_DEFERRED_TO_PUBLISHED_DEV")),
        beta_fact_ref=write_fact(lane, "beta.json", environment_fact(
            lane, candidate, "beta", "not_required", reason_code="ACCEPTANCE.BETA_OPTIONAL_BY_POLICY")),
        expected_remote_oid=parent,
    )


# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-001.t3
def test_lane_worktree_publishes_without_moving_its_own_head(tmp_path: Path, source_receipt_boundary) -> None:
    project, hub, remote, parent = canonical_layout(tmp_path)
    lane, commit = lane_candidate(hub, project, "lane/engineering", parent, "engineering candidate\n")
    admission_ref = lane_admission(lane, parent, commit)

    result = json.loads(local_git_cas_publish(repository=lane, policy_path=POLICY, admission_ref=admission_ref).read_text())
    assert (result["terminal"], result["beforeOid"], result["afterOid"], result["readbackOid"]) == ("published", parent, commit, commit)
    assert git(project, "--git-dir", str(remote), "rev-parse", "refs/heads/dev1.0") == commit
    # 发布不移动本 lane 的分支名/HEAD，也不移动 hub 的本地 dev1.0。
    assert git(lane, "symbolic-ref", "--short", "HEAD") == "lane/engineering"
    assert git(lane, "rev-parse", "HEAD") == commit
    assert git(hub, "rev-parse", "refs/heads/dev1.0") == parent
    assert result["publisherReceipt"]["sourceBranch"] == "refs/heads/lane/engineering"

    # 同 parent 的第二条 lane 是 CAS loser：零写、零自动 merge/stash。
    loser, loser_commit = lane_candidate(hub, project, "lane/ops", parent, "ops candidate\n")
    loser_admission = lane_admission(loser, parent, loser_commit)
    with pytest.raises(ScopedCandidateError, match="CAS_CONFLICT"):
        local_git_cas_publish(repository=loser, policy_path=POLICY, admission_ref=loser_admission)
    assert git(project, "--git-dir", str(remote), "rev-parse", "refs/heads/dev1.0") == commit
    assert git(loser, "rev-parse", "HEAD") == loser_commit
    assert git(loser, "stash", "list") == ""


# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-001.t3
def test_seat_named_foreign_clone_cannot_publish(tmp_path: Path, source_receipt_boundary, monkeypatch) -> None:
    project, hub, remote, parent = canonical_layout(tmp_path)
    lane, commit = lane_candidate(hub, project, "lane/engineering", parent, "engineering candidate\n")
    admission_ref = lane_admission(lane, parent, commit)
    # 目录名看起来是规范座位，但 git-common-dir 不是政策 bare hub：外来 clone 零写。
    foreign = project / "ops"
    git(project, "clone", "-q", "-b", "dev1.0", str(remote), str(foreign))
    shutil.copytree(lane / ".qwq_output", foreign / ".qwq_output", dirs_exist_ok=True)
    shutil.copytree(lane / "quwoquan_ops", foreign / "quwoquan_ops", dirs_exist_ok=True)
    monkeypatch.setattr(core_module(), "_remote_ref_oid", lambda *args: pytest.fail("no network before identity validation"))
    with pytest.raises(ScopedCandidateError, match="canonical lane or integration worktree"):
        local_git_cas_publish(repository=foreign, policy_path=POLICY,
                              admission_ref=foreign / ".qwq_output" / admission_ref.relative_to(lane / ".qwq_output"))
    assert git(project, "--git-dir", str(remote), "rev-parse", "refs/heads/dev1.0") == parent


def core_module():
    from quwoquan_ops.ci.scoped_candidate import core
    return core


# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-005.t2
def test_head_candidate_supersedes_unpublished_same_worktree_claim(tmp_path: Path) -> None:
    target, parent = repo(tmp_path)
    _parent, first_commit = committed_candidate(target)
    leftover = claim(target, parent, ["owned.txt", "foreign.txt"], writer="old-accept")
    first_ref = build_head_candidate(
        repository=target, policy_path=POLICY, commit=first_commit, expected_parent=parent,
impact_plan_digest=DIGEST, writer_id="integration",
        expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    )
    first = json.loads(first_ref.read_text())
    (target / "unrelated.txt").write_text("receipt note\n")
    git(target, "add", "unrelated.txt")
    git(target, "commit", "-m", "unrelated head")
    second_commit = git(target, "rev-parse", "HEAD")
    second_ref = build_head_candidate(
        repository=target, policy_path=POLICY, commit=second_commit, expected_parent=parent,
impact_plan_digest=DIGEST, writer_id="integration",
        expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    )
    second = json.loads(second_ref.read_text())
    claims = {item["claimId"]: item for item in inspect_claims(repository=target, policy_path=POLICY)}
    leftover_id = json.loads(leftover.read_text())["claimId"]
    first_id = Path(first["claimRef"]).stem
    second_id = Path(second["claimRef"]).stem
    assert claims[leftover_id]["active"] is False
    assert claims[first_id]["active"] is False
    assert claims[second_id]["active"] is True
    assert second["paths"] == ["owned.txt", "unrelated.txt"]
    release = store_root(repository=target, policy_path=POLICY) / "releases" / f"{first_id}.json"
    assert json.loads(release.read_text())["reason"] == "superseded_by_new_head"
    with pytest.raises(ScopedCandidateError, match="CLAIM_CONFLICT"):
        claim(target, parent, ["owned.txt"], writer="writer-2")


# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-005.t2
def test_head_candidate_does_not_supersede_different_parent_claim(tmp_path: Path) -> None:
    target, parent = repo(tmp_path)
    claim(target, parent, ["owned.txt"], writer="other-parent-writer")
    git(target, "checkout", "-q", "-b", "side", parent)
    (target / "side.txt").write_text("side\n")
    git(target, "add", ".")
    git(target, "commit", "-m", "side parent")
    side_parent = git(target, "rev-parse", "HEAD")
    (target / "owned.txt").write_text("side candidate\n")
    git(target, "add", ".")
    git(target, "commit", "-m", "side candidate")
    side_commit = git(target, "rev-parse", "HEAD")
    with pytest.raises(ScopedCandidateError, match="CLAIM_CONFLICT"):
        build_head_candidate(
            repository=target, policy_path=POLICY, commit=side_commit, expected_parent=side_parent,
impact_plan_digest=DIGEST, writer_id="integration",
            expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        )
