# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-002.t1
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-002.t2
from __future__ import annotations

import hashlib
import io
import json
import subprocess
import tarfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from quwoquan_ops.ci.integration_qualification import PAYLOAD_TYPE
from quwoquan_ops.ci.promotion_evidence import (
    PromotionEvidenceError,
    canonical_bytes,
    create_promotion_admission,
    digest,
)
from quwoquan_ops.ci.promotion_hosted import (
    BUNDLE_MANIFEST,
    approval_fact,
    build_bundle_tar,
    extract_bundle,
    ruleset_fact,
    threads_fact,
    write_hosted_authority_facts,
)

HEAD = "a" * 40
BASE = "b" * 40


def _write_stage(tmp_path: Path, manifest: dict[str, object], tar_bytes: bytes) -> Path:
    stage = tmp_path / "stage"
    stage.mkdir(parents=True)
    (stage / "bundle.tar").write_bytes(tar_bytes)
    (stage / BUNDLE_MANIFEST).write_bytes(canonical_bytes(manifest) + b"\n")
    return stage


def test_bundle_tar_is_deterministic_and_round_trips(tmp_path: Path) -> None:
    root = tmp_path / "store"
    (root / "integration-qualification" / HEAD).mkdir(parents=True)
    (root / "integration-qualification" / HEAD / "fact.json").write_bytes(b'{"a":1}\n')
    (root / "environment-execution").mkdir()
    (root / "environment-execution" / "alpha.json").write_bytes(b'{"b":2}\n')
    first = build_bundle_tar(bundle_root=root, output_file=tmp_path / "one.tar")
    second = build_bundle_tar(bundle_root=root, output_file=tmp_path / "two.tar")
    assert first == second
    assert (tmp_path / "one.tar").read_bytes() == (tmp_path / "two.tar").read_bytes()
    assert [entry["ref"] for entry in first["entries"]] == [
        "environment-execution/alpha.json", f"integration-qualification/{HEAD}/fact.json",
    ]
    stage = _write_stage(tmp_path, first, (tmp_path / "one.tar").read_bytes())
    result = extract_bundle(stage=stage, output_dir=tmp_path / "out")
    assert result["entries"] == 2
    assert (tmp_path / "out" / "environment-execution" / "alpha.json").read_bytes() == b'{"b":2}\n'


def test_bundle_extract_rejects_drift_and_unsafe_members(tmp_path: Path) -> None:
    root = tmp_path / "store"
    root.mkdir()
    (root / "fact.json").write_bytes(b"{}\n")
    manifest = build_bundle_tar(bundle_root=root, output_file=tmp_path / "bundle.tar")
    raw = (tmp_path / "bundle.tar").read_bytes()
    # manifest tarSha256 与 tar 字节不一致
    drifted = dict(manifest, tarSha256="sha256:" + "0" * 64)
    with pytest.raises(PromotionEvidenceError, match="does not bind tar bytes"):
        extract_bundle(stage=_write_stage(tmp_path / "d1", drifted, raw), output_dir=tmp_path / "o1")
    # 成员字节漂移但 tar 摘要被同步伪造：逐文件 digest 仍拦住
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.PAX_FORMAT) as tar:
        info = tarfile.TarInfo(name="fact.json")
        payload = b'{"tampered":true}\n'
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    tampered = buffer.getvalue()
    forged = dict(manifest, tarSha256="sha256:" + hashlib.sha256(tampered).hexdigest())
    with pytest.raises(PromotionEvidenceError, match="digest drifted"):
        extract_bundle(stage=_write_stage(tmp_path / "d2", forged, tampered), output_dir=tmp_path / "o2")
    # 路径逃逸成员
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.PAX_FORMAT) as tar:
        info = tarfile.TarInfo(name="../escape.json")
        info.size = 3
        tar.addfile(info, io.BytesIO(b"{}\n"))
    escape = buffer.getvalue()
    unsafe = {"schema": manifest["schema"], "tarSha256": "sha256:" + hashlib.sha256(escape).hexdigest(),
              "entries": [{"ref": "../escape.json", "digest": "sha256:" + hashlib.sha256(b"{}\n").hexdigest(), "bytes": 3}]}
    with pytest.raises(PromotionEvidenceError, match="unsafe"):
        extract_bundle(stage=_write_stage(tmp_path / "d3", unsafe, escape), output_dir=tmp_path / "o3")


# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-001
def test_review_bundle_preserves_original_report_bytes_and_rejects_missing_dependencies(tmp_path: Path) -> None:
    from quwoquan_ops.ci.promotion_hosted import review_bundle_evidence
    from quwoquan_ops.cli.lib.agent_governance_contract import contract_schema_version, contract_section
    from quwoquan_ops.ci.verify_code_health_delivery import read_review_evidence

    control = tmp_path / "control"
    bundle = control / "qualification-bundle"
    bundle.mkdir(parents=True)
    report_raw = b'{\n  "schema": "quwoquan.code-health-delta",\n  "terminal": "PR_WARN"\n}\n'
    (bundle / "health.json").write_bytes(report_raw)
    exact_owner = bundle / ".qwq_output/owner.json"
    exact_owner.parent.mkdir()
    exact_owner.write_bytes(b"{}")
    receipt = {"evidence": [{"artifact": {"kind": "code-health-report-v1", "ref": "health.json"}}]}
    (bundle / "receipt.json").write_text(json.dumps(receipt, indent=2))
    for ref in ("plan.json", "review.json", "consolidation.json", "owner.json", "candidate.json", "impact.json"):
        (bundle / ref).write_bytes(b"{}")
    handoff = {field: None for field in contract_section("handoff_manifest")["required_fields"]}
    handoff.update(schema_version=contract_schema_version("handoff_manifest"), review_plan_ref="plan.json",
        review_consolidation_ref="consolidation.json", evidence_receipt_refs=["receipt.json"],
        reviewer_result_refs=["review.json"], owner_identity_ref=".qwq_output/owner.json", candidate_evidence_ref="candidate.json",
        candidate_closure=[{"ref": "impact.json", "canonical_json": "{}"}])
    (bundle / "handoff.json").write_text(json.dumps(handoff))
    evidence = review_bundle_evidence(bundle_root=bundle, evidence_root=control, handoff_ref="handoff.json")
    exact = next(item for item in evidence if item["ref"].endswith("/health.json"))
    assert exact["digest"] == digest(report_raw)
    assert read_review_evidence(control, exact)[0]["terminal"] == "PR_WARN"
    manifest = build_bundle_tar(bundle_root=bundle, output_file=tmp_path / "bundle.tar")
    stage = _write_stage(tmp_path, manifest, (tmp_path / "bundle.tar").read_bytes())
    extract_bundle(stage=stage, output_dir=tmp_path / "readback")
    assert (tmp_path / "readback/health.json").read_bytes() == report_raw
    assert (tmp_path / "readback/.qwq_output/owner.json").read_bytes() == b"{}"
    (bundle / "impact.json").unlink()
    with pytest.raises((ValueError, OSError)):
        review_bundle_evidence(bundle_root=bundle, evidence_root=control, handoff_ref="handoff.json")


def test_hosted_authority_semantics_follow_readback_not_assertion() -> None:
    reviews = [
        {"user": {"login": "author"}, "state": "APPROVED", "commit_id": HEAD},
        {"user": {"login": "reviewer"}, "state": "CHANGES_REQUESTED", "commit_id": HEAD},
        {"user": {"login": "reviewer"}, "state": "APPROVED", "commit_id": HEAD},
        {"user": {"login": "stale"}, "state": "APPROVED", "commit_id": BASE},
    ]
    approval = approval_fact(reviews=reviews, head_sha=HEAD, base_sha=BASE, author_login="author")
    # 作者自批与旧 commit 上的批准都不计；同一 reviewer 只取最后一条
    assert approval["approvalCount"] == 1 and approval["approvers"] == ["reviewer"] and approval["status"] == "passed"
    blocked = approval_fact(reviews=reviews[:2], head_sha=HEAD, base_sha=BASE, author_login="author")
    assert blocked["status"] == "failed" and blocked["decision"] == "not_approved"

    assert threads_fact(threads=[{"isResolved": True}, {"isResolved": False}], head_sha=HEAD, base_sha=BASE)["status"] == "failed"
    assert threads_fact(threads=[], head_sha=HEAD, base_sha=BASE)["unresolvedCount"] == 0

    ruleset = {
        "enforcement": "active", "target": "branch",
        "conditions": {"ref_name": {"include": ["refs/heads/main"], "exclude": []}},
        "bypass_actors": [],
        "rules": [
            {"type": "pull_request", "parameters": {}},
            {"type": "required_status_checks", "parameters": {
                "strict_required_status_checks_policy": True,
                "required_status_checks": [{"context": "03. Delivery Gate", "integration_id": 15368}],
            }},
        ],
    }
    good = ruleset_fact(rulesets=[ruleset], head_sha=HEAD, base_sha=BASE)
    assert good["status"] == "passed" and good["requiredCheckEnforced"] is True and good["bypassActors"] == []
    with_bypass = json.loads(json.dumps(ruleset))
    with_bypass["bypass_actors"] = [{"actor_type": "DeployKey"}]
    assert ruleset_fact(rulesets=[with_bypass], head_sha=HEAD, base_sha=BASE)["status"] == "failed"
    assert ruleset_fact(rulesets=[], head_sha=HEAD, base_sha=BASE)["requiredCheckEnforced"] is False


@pytest.mark.parametrize("bypass", ["missing", None, [], [{"actor_type": "DeployKey"}], {}, ""])
def test_ruleset_bypass_observation_never_fabricates_empty(bypass: object) -> None:
    # spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#open-007
    ruleset = {
        "enforcement": "active", "target": "branch",
        "conditions": {"ref_name": {"include": ["refs/heads/main"], "exclude": []}},
        "rules": [
            {"type": "pull_request"},
            {"type": "required_status_checks", "parameters": {
                "strict_required_status_checks_policy": True,
                "required_status_checks": [{"context": "03. Delivery Gate", "integration_id": 15368}],
            }},
        ],
    }
    if bypass != "missing":
        ruleset["bypass_actors"] = bypass
    fact = ruleset_fact(rulesets=[ruleset], head_sha=HEAD, base_sha=BASE)
    observable = isinstance(bypass, list)
    assert fact["bypassActorsObservable"] is observable
    assert fact["bypassActors"] == (bypass if observable else None)
    assert fact["rulesets"][0]["bypassActorsObservable"] is observable
    # required check 的形状可证，不意味着不可见的 bypass 为空。
    assert fact["requiredCheckEnforced"] is True
    assert fact["status"] == ("passed" if observable and not bypass else "failed")


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=True).stdout.strip()


@pytest.mark.parametrize("bypass", [[], "missing", None, [{"actor_type": "DeployKey"}]])
def test_gate_produced_facts_are_accepted_by_promotion_admit(tmp_path: Path, bypass: object) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    policy = repo / "quwoquan_ops/policies/code_health_policy.yaml"
    policy.parent.mkdir(parents=True)
    policy.write_bytes((Path(__file__).resolve().parents[4] / "quwoquan_ops/policies/code_health_policy.yaml").read_bytes())
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "user.email", "t@example.com")
    (repo / "a.txt").write_text("base\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "-b", "dev1.0")
    (repo / "b.txt").write_text("head\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "head")
    head = _git(repo, "rev-parse", "HEAD")
    head_tree = _git(repo, "show", "-s", "--format=%T", head)
    _git(repo, "checkout", "-q", "main")
    _git(repo, "merge", "-q", "--no-ff", "-m", "synthetic", "dev1.0")
    merge = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "dev1.0")
    _git(repo, "branch", "-f", "main", base)

    store = tmp_path / "control"
    store.mkdir()
    now = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
    unsigned = {
        "schema": "quwoquan_ops.integration_qualification_fact.v1", "decision": "qualified",
        "devRef": "refs/heads/dev1.0", "devHead": head, "devTree": head_tree,
        "candidate": {"candidateId": "sha256:" + "c" * 64, "commit": head, "tree": head_tree},
        "publishResult": {"ref": "publish.json", "digest": "sha256:" + "1" * 64},
        "publishAdmission": {"ref": "admission.json", "digest": "sha256:" + "2" * 64},
        "environmentChain": {name: {"ref": f"{name}.json", "digest": "sha256:" + "3" * 64} for name in ("alpha", "beta", "gamma")},
        "impactPlanDigest": "sha256:" + "4" * 64,
        "issuedAt": (now - timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
        "expiresAt": (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
    }
    import base64

    from quwoquan_ops.cli.lib.evidence_signing import INTEGRATION_SCHEDULER_IDENTITY
    from quwoquan_ops.tests.support.evidence_signing_test_support import (
        create_temporary_signing,
    )
    signing = create_temporary_signing(tmp_path / "signing", identities=(INTEGRATION_SCHEDULER_IDENTITY,))
    payload = canonical_bytes(unsigned)
    payload_type = PAYLOAD_TYPE.encode("utf-8")
    pae = b"DSSEv1 " + str(len(payload_type)).encode() + b" " + payload_type + b" " + str(len(payload)).encode() + b" " + payload
    fact = dict(unsigned, signer={
        "identity": INTEGRATION_SCHEDULER_IDENTITY,
        "payloadType": PAYLOAD_TYPE,
        "payload": base64.b64encode(payload).decode("ascii"),
        "signature": signing.signer(INTEGRATION_SCHEDULER_IDENTITY)(pae),
    })
    assert signing.verifier(INTEGRATION_SCHEDULER_IDENTITY)(pae, fact["signer"]["signature"])
    fact["qualificationId"] = digest(fact)
    qualification_path = store / "qualification-bundle" / "integration-qualification" / head / "fact.json"
    qualification_path.parent.mkdir(parents=True)
    qualification_path.write_bytes(canonical_bytes(fact) + b"\n")
    qualification_ref = {"ref": qualification_path.relative_to(store).as_posix(), "digest": digest(qualification_path)}

    readback = tmp_path / "readback"
    readback.mkdir()
    (readback / "reviews.json").write_text(json.dumps([{"user": {"login": "reviewer"}, "state": "APPROVED", "commit_id": head}]))
    (readback / "threads.json").write_text("[]")
    (readback / "rulesets.json").write_text(json.dumps([{
        "enforcement": "active", "target": "branch", "bypass_actors": [],
        "conditions": {"ref_name": {"include": ["refs/heads/main"], "exclude": []}},
        "rules": [{"type": "pull_request", "parameters": {}}, {"type": "required_status_checks", "parameters": {
            "strict_required_status_checks_policy": True,
            "required_status_checks": [{"context": "03. Delivery Gate", "integration_id": 15368}]}}],
    }]))
    ruleset_rows = json.loads((readback / "rulesets.json").read_text())
    if bypass == "missing":
        ruleset_rows[0].pop("bypass_actors")
    else:
        ruleset_rows[0]["bypass_actors"] = bypass
    (readback / "rulesets.json").write_text(json.dumps(ruleset_rows))
    facts = write_hosted_authority_facts(
        repository=repo, evidence_root=store, head_sha=head, base_sha=base, reviews_file=readback / "reviews.json",
        threads_file=readback / "threads.json", rulesets_file=readback / "rulesets.json", author_login="author",
        branch_policy_exit=0, changed_boundary_exit=0, impact_plan_digest="sha256:" + "5" * 64,
        changed_paths_digest="sha256:" + "6" * 64, required_evidence=[qualification_ref],
    )
    assert {name: value["status"] for name, value in facts.items()} == {
        "approval": "passed", "threads": "passed", "ruleset": "passed" if bypass == [] else "failed",
        "boundary": "passed", "required-evidence": "passed",
    }
    exact = {name: {"ref": value["ref"], "digest": value["digest"]} for name, value in facts.items()}
    if bypass != []:
        with pytest.raises(PromotionEvidenceError, match="ruleset does not bind promotion range"):
            create_promotion_admission(
                repository=repo, evidence_root=store, qualification_ref=qualification_ref,
                head_sha=head, base_sha=base, synthetic_merge_sha=merge,
                approval_fact_ref=exact["approval"], thread_fact_ref=exact["threads"],
                ruleset_fact_ref=exact["ruleset"], boundary_fact_ref=exact["boundary"],
                required_evidence=[exact["required-evidence"]],
                promotion_ready_at=now.isoformat().replace("+00:00", "Z"),
            )
        return
    admission = create_promotion_admission(
        repository=repo, evidence_root=store, qualification_ref=qualification_ref,
        head_sha=head, base_sha=base, synthetic_merge_sha=merge,
        approval_fact_ref=exact["approval"], thread_fact_ref=exact["threads"],
        ruleset_fact_ref=exact["ruleset"], boundary_fact_ref=exact["boundary"],
        required_evidence=[exact["required-evidence"]],
        promotion_ready_at=now.isoformat().replace("+00:00", "Z"),
    )
    body = json.loads(admission.read_text())
    assert body["decision"] == "admitted" and body["headSha"] == head and body["baseSha"] == base
    assert body["authority"]["approval"] == exact["approval"]
    # 边界失败的事实不得被 promotion-admit 接受；前驱也必须真实物化。
    failed_qualification = tmp_path / "control-failed" / qualification_ref["ref"]
    failed_qualification.parent.mkdir(parents=True)
    failed_qualification.write_bytes(qualification_path.read_bytes())
    failed = write_hosted_authority_facts(
        repository=repo, evidence_root=tmp_path / "control-failed", head_sha=head, base_sha=base, reviews_file=readback / "reviews.json",
        threads_file=readback / "threads.json", rulesets_file=readback / "rulesets.json", author_login="author",
        branch_policy_exit=0, changed_boundary_exit=2, impact_plan_digest="sha256:" + "5" * 64,
        changed_paths_digest="sha256:" + "6" * 64, required_evidence=[qualification_ref],
    )
    assert failed["boundary"]["status"] == "failed"
