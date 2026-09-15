# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-002
from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path

import pytest

from quwoquan_ops.ci.promotion_hosted import required_evidence_fact

from quwoquan_ops.ci.promotion_evidence import (
    HANDOFF_CONTEXT,
    PromotionEvidenceError,
    create_main_source_seal,
    create_promotion_admission,
    create_promotion_handoff,
    digest,
    main,
    validate_hosted_promotion_handoff,
)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=True).stdout.strip()


def write(root: Path, name: str, payload: dict[str, object]) -> dict[str, str]:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return {"ref": name, "digest": digest(path)}


def setup(tmp_path: Path) -> tuple[Path, Path, str, str, str]:
    repo = tmp_path / "repo"
    evidence = tmp_path / "evidence"
    repo.mkdir(); evidence.mkdir()
    policy = repo / "quwoquan_ops/policies/code_health_policy.yaml"
    policy.parent.mkdir(parents=True)
    policy.write_bytes((Path(__file__).resolve().parents[4] / "quwoquan_ops/policies/code_health_policy.yaml").read_bytes())
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "Test"); git(repo, "config", "user.email", "test@example.com")
    (repo / "base.txt").write_text("base\n"); git(repo, "add", "."); git(repo, "commit", "-m", "base")
    base = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-b", "dev1.0")
    (repo / "dev.txt").write_text("dev\n"); git(repo, "add", "."); git(repo, "commit", "-m", "dev")
    head = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "main")
    git(repo, "merge", "--no-ff", "--no-commit", "dev1.0")
    merge_tree = git(repo, "write-tree")
    synthetic = git(repo, "commit-tree", merge_tree, "-p", base, "-p", head, "-m", "synthetic")
    git(repo, "merge", "--abort")
    return repo, evidence, base, head, synthetic


def qualification_fact(root: Path, head: str, repo: Path) -> dict[str, str]:
    tree = git(repo, "show", "-s", "--format=%T", head)

    def exact_ref(name: str, digit: str) -> dict[str, str]:
        return {"ref": f"{name}.json", "digest": "sha256:" + digit * 64}

    body: dict[str, object] = {
        "schema": "quwoquan_ops.integration_qualification_fact.v1",
        "decision": "qualified",
        "devRef": "refs/heads/dev1.0",
        "devHead": head,
        "devTree": tree,
        "candidate": {
            "candidateId": "sha256:" + "1" * 64,
            "commit": head,
            "tree": tree,
        },
        "publishResult": exact_ref("publish-result", "2"),
        "publishAdmission": exact_ref("publish-admission", "3"),
        "environmentChain": {
            "alpha": exact_ref("alpha", "4"),
            "beta": exact_ref("beta", "5"),
            "gamma": exact_ref("gamma", "6"),
        },
        "impactPlanDigest": "sha256:" + "7" * 64,
        "issuedAt": "2026-09-05T09:00:00Z",
        "expiresAt": "2026-09-05T11:00:00Z",
    }
    body["signer"] = {
        "identity": "spiffe://quwoquan.local/integration",
        "payloadType": (
            "application/vnd.quwoquan.integration-qualification-fact.v1+json"
        ),
        "payload": base64.b64encode(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        ).decode(),
        "signature": "verified-upstream",
    }
    body["qualificationId"] = digest(body)
    return write(root, "qualification.json", body)


def authority_fact(root: Path, name: str, schema: str, head: str, base: str) -> dict[str, str]:
    semantic = {
        "quwoquan_ops.promotion_approval_fact.v1": {"decision": "approved", "commitSha": head, "approvalCount": 1},
        "quwoquan_ops.promotion_thread_fact.v1": {"commitSha": head, "unresolvedCount": 0},
        "quwoquan_ops.promotion_ruleset_fact.v1": {"commitSha": head, "requiredCheck": "03. Delivery Gate", "requiredCheckEnforced": True, "bypassActors": []},
        "quwoquan_ops.promotion_boundary_fact.v1": {"verifiedHeadSha": head, "verifiedBaseSha": base, "secretStatus": "passed", "generatedBoundaryStatus": "passed"},
    }.get(schema, {})
    return write(root, name, {"schema": schema, "status": "passed", "headSha": head, "baseSha": base, **semantic})


def hosted_handoff(*, head: str, base: str, synthetic: str, tree: str) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    record = create_promotion_handoff(
        repository="leadwise/quwoquan", pull_request_number=42,
        head_sha=head, base_sha=base, synthetic_merge_sha=synthetic,
        synthetic_merge_tree=tree, workflow_run_id=9001, workflow_run_attempt=1,
        workflow_repository="leadwise/quwoquan", workflow_head_sha=head,
        workflow_actor_login="merge-owner", workflow_actor_id=77,
        promotion_admission_ref="ghcr.io/leadwise/quwoquan/promotion-admission@sha256:" + "a" * 64,
        admission_bytes_digest="sha256:" + "b" * 64,
        created_at="2026-09-05T10:00:00Z",
    )
    check: dict[str, object] = {
        "id": 501, "node_id": "CR_kwDOtrusted", "name": HANDOFF_CONTEXT,
        "head_sha": head, "status": "completed", "conclusion": "success",
        "external_id": record["recordId"],
        "statuses_url": f"https://api.github.com/repos/leadwise/quwoquan/statuses/{head}",
        "started_at": "2026-09-05T10:00:00Z", "completed_at": "2026-09-05T10:00:00Z",
        "details_url": "https://github.com/leadwise/quwoquan/actions/runs/9001/attempts/1",
        "app": {"id": 1234, "slug": "quwoquan-promotion-recorder"},
        "output": {"title": "quwoquan_ops.promotion_admission_handoff.v1", "summary": base64.b64encode(json.dumps(record, sort_keys=True, separators=(",", ":")).encode()).decode()},
    }
    run: dict[str, object] = {
        "id": 9001, "run_attempt": 1, "event": "pull_request",
        "path": ".github/workflows/delivery-gate.yml", "head_sha": head,
        "html_url": "https://github.com/leadwise/quwoquan/actions/runs/9001",
        "actor": {"login": "merge-owner", "id": 77},
        "repository": {"full_name": "leadwise/quwoquan"},
        "head_repository": {"full_name": "leadwise/quwoquan"},
        "pull_requests": [{"number": 42}],
    }
    return record, check, run


def validate_handoff(check: dict[str, object], run: dict[str, object], *, head: str, base: str, tree: str) -> dict[str, object]:
    return validate_hosted_promotion_handoff(
        check_run=check, workflow_run=run, repository="leadwise/quwoquan",
        pull_request_number=42, head_sha=head, base_sha=base,
        synthetic_merge_tree=tree, expected_context=HANDOFF_CONTEXT,
        expected_app_slug="quwoquan-promotion-recorder", expected_app_id=1234,
        expected_workflow_repository="leadwise/quwoquan",
        verified_at="2026-09-05T10:04:30Z",
    )


# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-001
@pytest.mark.parametrize("kind", ["missing", "wrong-range", "wrong-head", "wrong-tree", "wrong-impact",
    "fast", "blocker", "stale", "policy", "implementation", "fingerprint", "summary", "duplicate"])
def test_admission_rejects_passed_wrapper_without_current_full_health(tmp_path: Path, kind: str) -> None:
    repo, root, base, head, synthetic = setup(tmp_path)
    qualification = qualification_fact(root, head, repo)
    schemas = ("approval", "thread", "ruleset", "boundary")
    exacts = [authority_fact(root, f"{name}.json", f"quwoquan_ops.promotion_{name}_fact.v1", head, base) for name in schemas]
    wrapper = required_evidence_fact(repository=repo, evidence_root=root,
        head_sha=head, base_sha=base, evidence=[qualification])
    health_ref = next(item for item in wrapper["evidence"] if item != qualification)
    health = json.loads((root / health_ref["ref"]).read_bytes())
    changes = {"wrong-range": ("baseSha", head), "wrong-head": ("headSha", base),
        "fast": ("mode", "fast"), "blocker": ("terminal", "GATE_BLOCK"),
        "policy": ("policyDigest", "sha256:" + "0" * 64),
        "implementation": ("implementationDigest", "sha256:" + "0" * 64),
        "fingerprint": ("evidenceFingerprint", {}), "summary": ("summary", {})}
    if kind in changes:
        key, value = changes[kind]
        health[key] = value
    health_ref = write(root, "health.json", health)
    wrapper["evidence"] = [qualification] + ([] if kind == "missing" else [health_ref])
    if kind == "duplicate":
        wrapper["evidence"].append(health_ref)
    if kind == "wrong-tree":
        wrapper["headTree"] = base
    if kind == "wrong-impact":
        wrapper["impactPlanDigest"] = "sha256:" + "0" * 64
    if kind == "stale":
        (root / "health.json").write_text("{}\n")
    required = write(root, "required.json", wrapper)
    with pytest.raises(PromotionEvidenceError, match="PROMOTION.(HEALTH|STALE)"):
        create_promotion_admission(repository=repo, evidence_root=root, qualification_ref=qualification,
            head_sha=head, base_sha=base, synthetic_merge_sha=synthetic, approval_fact_ref=exacts[0],
            thread_fact_ref=exacts[1], ruleset_fact_ref=exacts[2], boundary_fact_ref=exacts[3],
            required_evidence=[required], promotion_ready_at="2026-09-05T10:00:00Z")


# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-001
@pytest.mark.parametrize("kind", ["blocker", "warning", "last-push"])
def test_full_promotion_cannot_hide_earlier_health_findings(tmp_path: Path, kind: str) -> None:
    repo, root, base, _, _ = setup(tmp_path)
    git(repo, "checkout", "dev1.0")
    source = repo / "quwoquan_ops/ci/large.sh"
    source.parent.mkdir(parents=True, exist_ok=True)
    count = 2100 if kind != "warning" else 410
    source.write_text("\n".join(f"echo value_{index}" for index in range(count)) + "\n")
    git(repo, "add", "."); git(repo, "commit", "-m", "earlier health debt")
    previous = git(repo, "rev-parse", "HEAD")
    (repo / "last.txt").write_text("last push is harmless\n")
    git(repo, "add", "."); git(repo, "commit", "-m", "last push")
    head = git(repo, "rev-parse", "HEAD")
    tree = git(repo, "rev-parse", "HEAD^{tree}")
    synthetic = git(repo, "commit-tree", tree, "-p", base, "-p", head, "-m", "synthetic")
    qualification = qualification_fact(root, head, repo)
    wrapper = required_evidence_fact(repository=repo, evidence_root=root,
        head_sha=head, base_sha=base, evidence=[qualification])
    report_ref = next(item for item in wrapper["evidence"] if item != qualification)
    report = json.loads((root / report_ref["ref"]).read_bytes())
    assert report["terminal"] == ("PR_WARN" if kind == "warning" else "GATE_BLOCK")
    if kind == "last-push":
        last = required_evidence_fact(repository=repo, evidence_root=root,
            head_sha=head, base_sha=previous, evidence=[qualification])
        last_ref = next(item for item in last["evidence"] if item != qualification)
        assert json.loads((root / last_ref["ref"]).read_bytes())["terminal"] == "PASS"
        wrapper["evidence"] = [qualification, last_ref]
    wrapper["status"] = "passed"  # 调用者伪造包装成功，reader 仍需读取真实报告。
    required = write(root, "required.json", wrapper)
    exacts = [authority_fact(root, f"{name}.json", f"quwoquan_ops.promotion_{name}_fact.v1", head, base)
        for name in ("approval", "thread", "ruleset", "boundary")]
    expected = "HEALTH_DISPOSITION_REQUIRED" if kind == "warning" else "HEALTH_INVALID"
    with pytest.raises(PromotionEvidenceError, match=expected):
        create_promotion_admission(repository=repo, evidence_root=root, qualification_ref=qualification,
            head_sha=head, base_sha=base, synthetic_merge_sha=synthetic, approval_fact_ref=exacts[0],
            thread_fact_ref=exacts[1], ruleset_fact_ref=exacts[2], boundary_fact_ref=exacts[3],
            required_evidence=[required], promotion_ready_at="2026-09-05T10:00:00Z")
    assert not (root / "promotion/admissions").exists()


# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-001
@pytest.mark.parametrize("mutation", ["missing-disposition", "another-range", "stale-report", "valid-owner-open"])
def test_real_warning_existing_review_closure(tmp_path: Path, mutation: str) -> None:
    """现有 closure validator 真实验证 owner OPEN；不将该局部正例伪称完整 admission。"""
    from quwoquan_ops.ci.verify_code_health_delivery import verify_delivery, promotion_health_plan
    from quwoquan_ops.cli import review_consolidator
    import tempfile

    repo, _, base, _, _ = setup(tmp_path)
    git(repo, "checkout", "dev1.0")
    source = repo / "quwoquan_ops/ci/warning.sh"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("\n".join(f"echo {index}" for index in range(410)) + "\n")
    git(repo, "add", "."); git(repo, "commit", "-m", "real warning")
    head = git(repo, "rev-parse", "HEAD")
    impact = promotion_health_plan(repo, base, head)
    report, _, _ = verify_delivery(repo, base_sha=base, head_sha=head,
        expected_path_digest=impact["changed_paths_digest"], expected_impact_plan_digest=impact["plan_digest"])
    assert report["terminal"] == "PR_WARN" and report["findings"]
    runtime = Path(__file__).resolve().parents[4] / ".qwq_output/env/repo/local/promotion-review-tests"
    runtime.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=runtime) as directory:
        case = Path(directory)
        ref = (case / "report.json").relative_to(review_consolidator.ROOT).as_posix()
        exact = write(review_consolidator.ROOT, ref, report)
        candidate = {"ref": "candidate", "canonical_bytes_sha256": "sha256:" + "1" * 64,
            "changed_paths_digest": report["changedPathsDigest"], "impact_plan_ref": "impact",
            "impact_plan_digest": impact["plan_digest"], "fingerprint_ref": "candidate-fingerprint", "fingerprint_digest": "candidate-digest"}
        owner = "specs/feature-tree/platform-ops-governance/spec.md"
        plan = {"workflow": "dev", "head_sha": head, "merge_base_sha": base,
            "changed_paths": report["changedPaths"], "candidate_evidence_identity": candidate,
            "owner_identity": {"resolved_owner": owner}, "contexts": [{"path": owner, "exists": True}],
            "reviewers": [{"role": "developer", "kind": "primary"}]}
        artifact = {"kind": "code-health-report-v1", "ref": ref, "canonical_bytes_sha256": exact["digest"],
            "schema": report["schema"], "terminal": report["terminal"], "base_sha": base, "head_sha": head,
            "changed_paths_digest": report["changedPathsDigest"], "summary": report["summary"], "findings": report["findings"],
            "evidence_fingerprint_ref": report["evidenceFingerprint"]["ref"], "evidence_fingerprint_digest": report["evidenceFingerprint"]["digest"],
            "candidate_evidence_ref": candidate["ref"], "candidate_evidence_sha256": candidate["canonical_bytes_sha256"],
            "impact_plan_ref": "impact", "impact_plan_digest": impact["plan_digest"]}
        receipt = {"evidence": [{"id": "health", "exit_code": 0, "timed_out": False, "artifact": artifact}]}
        closure = {"candidate_fingerprint_ref": "candidate-fingerprint", "candidate_fingerprint_digest": "candidate-digest",
            "health_dispositions": [{"finding_id": finding["findingId"], "disposition": "owner-open",
                "reason": "完整范围的规模信号按当前 owner OPEN 跟踪", "evidence_ids": ["health"], "open_ref": owner + "#open-004"}
                for finding in report["findings"] if finding["terminal"] == "PR_WARN"], "replacements": []}
        if mutation == "missing-disposition":
            closure["health_dispositions"] = []
        elif mutation == "another-range":
            artifact["base_sha"] = head
        elif mutation == "stale-report":
            (case / "report.json").write_text("{}")
        results = {"developer": {"status": "completed", "candidate_closure": closure}}
        if mutation == "valid-owner-open":
            review_consolidator.validate_candidate_closure(plan, receipt, results)
        else:
            with pytest.raises(ValueError):
                review_consolidator.validate_candidate_closure(plan, receipt, results)


# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-001
def test_existing_review_range_resolver_cannot_represent_hosted_promotion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """真实 Git ref 证明现有 Review API 缺口，不 mock range resolver 或 validator。"""
    from quwoquan_ops.cli import review_consolidator

    repo, _, base, head, _ = setup(tmp_path)
    git(repo, "checkout", "dev1.0")
    git(repo, "update-ref", "refs/remotes/origin/dev1.0", head)
    monkeypatch.setattr(review_consolidator.review_dispatch, "REPO_ROOT", repo)
    actual = review_consolidator.review_dispatch._merge_base_sha()
    assert actual == head and actual != base


# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-001
def test_admission_real_portable_review_warning_open_and_tampering(tmp_path: Path) -> None:
    """真实 candidate→plan→runner→Review→运输→promotion admission，无核心 mock。"""
    import shutil
    import yaml
    from quwoquan_ops.cli import review_consolidator as review
    from lib import candidate_evidence as candidates
    from lib import feature_context_fingerprint as owner_fingerprint
    from lib.feature_tree import context
    from lib.feature_tree.content_addressed_writer import _write_content_addressed_bytes
    from lib.evidence_fingerprint import canonical_json_bytes
    from lib.agent_governance_contract import contract_schema_version
    from quwoquan_ops.ci.promotion_hosted import required_evidence_fact

    original = Path(__file__).resolve().parents[4]
    source, control = tmp_path / "source", tmp_path / "control"
    source.mkdir(); control.mkdir()
    transport = control / "qualification-bundle"
    for root_name in ("quwoquan_ops", "specs", ".agents"):
        for path in (original / root_name).rglob("*"):
            if path.is_file() and path.suffix in {".py", ".yaml", ".yml", ".json", ".md", ".sh"}:
                target = source / path.relative_to(original)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
    (source / ".gitignore").write_text(".qwq_output/\n")
    # 与 portable canonical 测试同一实际 runner adapter，报告由真实 engine 生产。
    script = source / "quwoquan_ops/cli/promotion_health_fixture.py"
    script.write_text('''import os,json,hashlib
from pathlib import Path
from quwoquan_ops.ci.verify_code_health_delivery import verify_delivery
root=Path.cwd()
plan=json.loads(Path(os.environ["QWQ_REVIEW_BASELINE_PLAN_PATH"]).read_text())
candidate=plan["candidate_evidence_identity"]
report,path,identity=verify_delivery(root,base_sha=plan["merge_base_sha"],head_sha=plan["head_sha"],expected_path_digest=candidate["changed_paths_digest"],expected_impact_plan_digest=candidate["impact_plan_digest"])
raw=path.read_bytes()
artifact={"kind":"code-health-report-v1","ref":path.relative_to(root).as_posix(),"canonical_bytes_sha256":"sha256:"+hashlib.sha256(raw).hexdigest(),"schema":report["schema"],"terminal":report["terminal"],"report_identity":identity,"evidence_fingerprint_ref":report["evidenceFingerprint"]["ref"],"evidence_fingerprint_digest":report["evidenceFingerprint"]["digest"],"base_sha":report["baseSha"],"head_sha":report["headSha"],"changed_paths_digest":report["changedPathsDigest"],"impact_plan_ref":candidate["impact_plan_ref"],"impact_plan_digest":candidate["impact_plan_digest"],"candidate_evidence_ref":candidate["ref"],"candidate_evidence_sha256":candidate["canonical_bytes_sha256"],"plan_ref":os.environ["QWQ_REVIEW_BASELINE_PLAN_REF"],"plan_sha256":os.environ["QWQ_REVIEW_BASELINE_PLAN_SHA256"],"summary":report["summary"],"findings":report["findings"]}
Path(os.environ["QWQ_NAMED_EVIDENCE_RESULT_PATH"]).write_text(json.dumps(artifact))
''')
    registry_path = source / ".agents/skills/review/references/registry.yaml"
    registry = yaml.safe_load(registry_path.read_text())
    registry["workflows"]["dev"]["baseline_evidence"] = ""
    registry["profiles"] = {}
    registry["evidence"] = {"code-health-delta": {"command": "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python3 -B quwoquan_ops/cli/promotion_health_fixture.py",
        "segment": "POST", "required": True, "timeout_seconds": 300, "covers": [], "result_artifact": "code-health-report-v1"}}
    registry_path.write_text(yaml.safe_dump(registry))
    git(source, "init", "-b", "main"); git(source, "config", "user.name", "Test"); git(source, "config", "user.email", "t@example.invalid")
    git(source, "add", "."); git(source, "commit", "-qm", "base")
    base = git(source, "rev-parse", "HEAD")
    target = "quwoquan_ops/cli/review_consolidator.py"
    with (source / target).open("a") as stream:
        stream.write("\ndef promotion_warning(value):\n" + "".join(f"    if value == {n}:\n        return {n}\n" for n in range(24)) + "    return -1\n")
    git(source, "checkout", "-b", "dev1.0"); git(source, "add", target); git(source, "commit", "-qm", "warning")
    head = git(source, "rev-parse", "HEAD")
    tree = git(source, "rev-parse", "HEAD^{tree}")
    # 测试源仓本来存在真实本地 producer ref；hosted 不得照此从自报字段补造。
    git(source, "branch", "lane/engineering", head)
    git(source, "update-ref", "refs/remotes/origin/dev1.0", head)
    exact_range = {"base_sha": base, "head_sha": head, "head_tree": tree}
    current = candidates._current_owner(target, repo_root=source)
    owner = {**current, "schema_version": 4, "canonical_contexts": [{"path": current["resolved_owner"], "anchor": None, "kind": "spec"}],
        "applicable_agents": ["AGENTS.md"], "open_items": []}
    owner["evidence_fingerprint"] = owner_fingerprint.embedded_fingerprint_binding(owner_fingerprint.build_feature_context_fingerprint(owner, repo_root=source))
    def publish(value, subdirectory=None):
        with context.source_repository(source):
            return _write_content_addressed_bytes(canonical_json_bytes(value), subdirectory=subdirectory).relative_to(source).as_posix()
    owner_ref = publish(owner)
    candidate = candidates.build_candidate_evidence(owner_ref, [target], repo_root=source,
        source_identity={**exact_range, "producer_lane": "lane/engineering"})
    candidate_ref = publish(candidate, "candidates/by-fingerprint")
    plan = review.review_dispatch.build_plan(registry, "dev", "POST", None, [target], context_manifest=owner,
        context_manifest_ref=owner_ref, candidate_evidence_ref=candidate_ref, git_range=exact_range, source_repository=source)
    plan_ref, receipt_ref, result_ref = (f".qwq_output/promotion-review/{name}.json" for name in ("plan", "evidence", "review"))
    (source / plan_ref).parent.mkdir(parents=True)
    (source / plan_ref).write_bytes(canonical_json_bytes(plan))
    receipt = review.evidence_runner.run_plan(plan, cwd=source, registry=registry, plan_bytes=canonical_json_bytes(plan),
        plan_ref=plan_ref, source_repository=source)
    assert receipt["terminal"]["status"] == "PASS"
    artifact = receipt["evidence"][0]["artifact"]
    assert artifact["terminal"] == "PR_WARN"
    receipt_bytes = json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    (source / receipt_ref).write_bytes(receipt_bytes)
    identity = review.handoff_consumer.named_evidence_identity_from_raw(receipt_ref, receipt_bytes, receipt)
    result = {"schema_version": contract_schema_version("review_result"), "role": "developer", "status": "completed",
        "evidence_receipt_ref": receipt_ref, "evidence_receipt_canonical_bytes_sha256": identity["canonical_bytes_sha256"],
        "evidence_run_id": identity["run_id"], "evidence_generation_id": identity["generation_id"],
        "assembled_input_byte_count": 1024, "assembled_input_digest": "sha256:" + "a" * 64, "assembled_input_compression": {},
        "started_at": receipt["finished_at"], "finished_at": receipt["finished_at"], "findings": []}
    for field in ("plan_fingerprint_ref", "plan_fingerprint_digest", "execution_fingerprint_ref", "execution_fingerprint_digest", "result_fingerprint_ref", "result_fingerprint_digest"):
        result[field] = identity[field]
    result["candidate_closure"] = {"candidate_fingerprint_ref": plan["candidate_evidence_identity"]["fingerprint_ref"],
        "candidate_fingerprint_digest": plan["candidate_evidence_identity"]["fingerprint_digest"], "replacements": [],
        "health_dispositions": [{"finding_id": item["findingId"], "disposition": "owner-open", "reason": "current owner scope",
            "evidence_ids": ["code-health-delta"], "open_ref": current["resolved_owner"] + "#open-003"}
            for item in artifact["findings"] if item["terminal"] == "PR_WARN"]}
    (source / result_ref).write_bytes(canonical_json_bytes(result))
    consolidation = review.consolidate(plan, [(receipt_ref, receipt)], [(result_ref, result)], registry=registry, source_repository=source)
    (source / ".qwq_output/promotion-review/consolidation.json").write_bytes(canonical_json_bytes(consolidation))
    shutil.copytree(source / ".qwq_output", transport / ".qwq_output")
    # 删除 source 输出证明 reader 只使用 transport；source Git 与 canonical policy 保持不变。
    shutil.rmtree(source / ".qwq_output")
    qualification = qualification_fact(control, head, source)
    refs = [qualification] + [{"ref": path.relative_to(control).as_posix(), "digest": digest(path)}
        for path in transport.rglob("*.json") if path.name != "code-health-delta.json" and "results" not in path.parts]
    # 只使用 canonical producer 前驱，避免 runner descriptor 被错当 report。
    report_refs = [item for item in refs if json.loads((control / item["ref"]).read_bytes()).get("schema") == "quwoquan.code-health-delta"]
    assert len(report_refs) == 1
    required = write(control, "required.json", required_evidence_fact(repository=source, evidence_root=control,
        head_sha=head, base_sha=base, evidence=refs))
    authorities = [authority_fact(control, f"{name}.json", f"quwoquan_ops.promotion_{name}_fact.v1", head, base)
        for name in ("approval", "thread", "ruleset", "boundary")]
    merge = git(source, "commit-tree", tree, "-p", base, "-p", head, "-m", "synthetic")
    def admit():
        return create_promotion_admission(repository=source, evidence_root=control, qualification_ref=qualification,
            head_sha=head, base_sha=base, synthetic_merge_sha=merge, approval_fact_ref=authorities[0],
            thread_fact_ref=authorities[1], ruleset_fact_ref=authorities[2], boundary_fact_ref=authorities[3],
            required_evidence=[required], promotion_ready_at="2026-09-05T10:00:00Z")
    admission = admit()
    assert json.loads(admission.read_bytes())["decision"] == "admitted"
    assert not (source / ".qwq_output").exists()
    report_path = control / report_refs[0]["ref"]
    raw = report_path.read_bytes(); report_path.write_text("{}")
    with pytest.raises(PromotionEvidenceError, match="STALE"): admit()
    report_path.write_bytes(raw)
    plan_path = transport / plan_ref
    raw_plan = plan_path.read_bytes()
    wrong_plan = json.loads(raw_plan); wrong_plan["merge_base_sha"] = head
    plan_path.write_bytes(canonical_json_bytes(wrong_plan))
    with pytest.raises(PromotionEvidenceError): admit()
    # 即使攻击者重签外层 required digest，原始 receipt 的 exact plan 绑定仍拒绝另一 range。
    wrapper = json.loads((control / "required.json").read_bytes())
    plan_transport_ref = plan_path.relative_to(control).as_posix()
    for item in wrapper["evidence"]:
        if item["ref"] == plan_transport_ref:
            item["digest"] = digest(plan_path)
    required = write(control, "required.json", wrapper)
    with pytest.raises(PromotionEvidenceError, match="HEALTH_DISPOSITION_INVALID"): admit()
    plan_path.write_bytes(raw_plan)
    for item in wrapper["evidence"]:
        if item["ref"] == plan_transport_ref:
            item["digest"] = digest(plan_path)
    required = write(control, "required.json", wrapper)
    # 漏裁决并更新外层 bytes 不能冒充原先 full-chain consolidation。
    result_path = transport / result_ref
    raw_result = result_path.read_bytes()
    missing = json.loads(raw_result); missing["candidate_closure"]["health_dispositions"] = []
    result_path.write_bytes(canonical_json_bytes(missing))
    for item in wrapper["evidence"]:
        if item["ref"] == result_path.relative_to(control).as_posix():
            item["digest"] = digest(result_path)
    required = write(control, "required.json", wrapper)
    with pytest.raises(PromotionEvidenceError, match="HEALTH_DISPOSITION_INVALID"): admit()
    result_path.write_bytes(raw_result)
    for item in wrapper["evidence"]:
        if item["ref"] == result_path.relative_to(control).as_posix():
            item["digest"] = digest(result_path)
    required = write(control, "required.json", wrapper)
    assert json.loads(admit().read_bytes())["decision"] == "admitted"
    git(source, "branch", "-D", "lane/engineering")
    with pytest.raises(PromotionEvidenceError): admit()
    assert git(source, "rev-parse", "HEAD") == head


def test_admission_and_seal_bind_synthetic_tree(tmp_path: Path) -> None:
    repo, root, base, head, synthetic = setup(tmp_path)
    qualification = qualification_fact(root, head, repo)
    approval = authority_fact(root, "approval.json", "quwoquan_ops.promotion_approval_fact.v1", head, base)
    threads = authority_fact(root, "threads.json", "quwoquan_ops.promotion_thread_fact.v1", head, base)
    ruleset = authority_fact(root, "ruleset.json", "quwoquan_ops.promotion_ruleset_fact.v1", head, base)
    boundary = authority_fact(root, "boundary.json", "quwoquan_ops.promotion_boundary_fact.v1", head, base)
    required = write(root, "required.json", required_evidence_fact(
        repository=repo, evidence_root=root, head_sha=head, base_sha=base, evidence=[qualification]))
    admission_path = create_promotion_admission(
        repository=repo, evidence_root=root, qualification_ref=qualification,
        head_sha=head, base_sha=base, synthetic_merge_sha=synthetic,
        approval_fact_ref=approval, thread_fact_ref=threads, ruleset_fact_ref=ruleset,
        boundary_fact_ref=boundary, required_evidence=[required],
        promotion_ready_at="2026-09-05T10:00:00Z",
    )
    git(repo, "checkout", "main"); git(repo, "merge", "--no-ff", "dev1.0", "-m", "promotion")
    main = git(repo, "rev-parse", "main")
    admission_exact = {"ref": admission_path.relative_to(root).as_posix(), "digest": digest(admission_path)}
    admission_oci = "ghcr.io/leadwise/quwoquan/promotion-admission@sha256:" + "a" * 64
    record, check, run = hosted_handoff(
        head=head, base=base, synthetic=main,
        tree=json.loads(admission_path.read_text())["syntheticMergeTree"],
    )
    record["admissionBytesDigest"] = admission_exact["digest"]
    record.pop("recordId")
    record["recordId"] = digest(record)
    check["external_id"] = record["recordId"]
    check["output"]["summary"] = base64.b64encode(
        json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
    ).decode()
    hosted = validate_handoff(check, run, head=head, base=base, tree=record["syntheticMergeTree"])
    hosted_ref = write(root, "hosted-handoff.json", hosted)
    seal = create_main_source_seal(
        repository=repo, evidence_root=root, admission_ref=admission_exact,
        main_sha=main, main_readback_at="2026-09-05T10:04:30Z",
        admission_oci_ref=admission_oci, hosted_handoff_ref=hosted_ref,
    )
    payload = json.loads(seal.read_text())
    assert payload["sourceStatus"] == "source-admitted"
    assert payload["releaseStatus"] == "not_selected"
    assert payload["durationSeconds"] == 270
    assert payload["mainTree"] == json.loads(admission_path.read_text())["syntheticMergeTree"]
    assert payload["promotionAdmissionOciRef"] == admission_oci
    assert payload["hostedPromotionHandoff"] == hosted_ref
    assert git(repo, "rev-parse", "refs/heads/main") == main
    assert git(repo, "rev-parse", "refs/heads/dev1.0") == head


def test_admission_rejects_non_current_dev_head(tmp_path: Path) -> None:
    repo, root, base, head, synthetic = setup(tmp_path)
    qualification = qualification_fact(root, head, repo)
    schemas = (
        "quwoquan_ops.promotion_approval_fact.v1",
        "quwoquan_ops.promotion_thread_fact.v1",
        "quwoquan_ops.promotion_ruleset_fact.v1",
        "quwoquan_ops.promotion_boundary_fact.v1",
    )
    exacts = [authority_fact(root, f"a-{index}.json", schema, head, base) for index, schema in enumerate(schemas)]
    required = write(root, "required.json", required_evidence_fact(
        repository=repo, evidence_root=root, head_sha=head, base_sha=base, evidence=[qualification]))
    git(repo, "checkout", "dev1.0"); (repo / "new.txt").write_text("new\n"); git(repo, "add", "."); git(repo, "commit", "-m", "new")
    with pytest.raises(PromotionEvidenceError, match="HEAD_DRIFT"):
        create_promotion_admission(
            repository=repo, evidence_root=root, qualification_ref=qualification,
            head_sha=head, base_sha=base, synthetic_merge_sha=synthetic,
            approval_fact_ref=exacts[0], thread_fact_ref=exacts[1], ruleset_fact_ref=exacts[2],
            boundary_fact_ref=exacts[3], required_evidence=[required],
            promotion_ready_at="2026-09-05T10:00:00Z",
        )


def test_admission_rejects_wrong_authority_schema_and_expired_qualification(tmp_path: Path) -> None:
    repo, root, base, head, synthetic = setup(tmp_path)
    qualification = qualification_fact(root, head, repo)
    schemas = {
        "approval": "quwoquan_ops.promotion_approval_fact.v1",
        "threads": "quwoquan_ops.promotion_thread_fact.v1",
        "ruleset": "quwoquan_ops.promotion_ruleset_fact.v1",
        "boundary": "quwoquan_ops.promotion_boundary_fact.v1",
    }
    required = write(root, "required.json", required_evidence_fact(
        repository=repo, evidence_root=root, head_sha=head, base_sha=base, evidence=[qualification]))

    for wrong_name in schemas:
        authority = {
            name: authority_fact(
                root,
                f"{wrong_name}-{name}.json",
                "quwoquan_ops.not_authority.v1" if name == wrong_name else schema,
                head,
                base,
            )
            for name, schema in schemas.items()
        }
        with pytest.raises(PromotionEvidenceError, match="AUTHORITY_INVALID"):
            create_promotion_admission(
                repository=repo, evidence_root=root, qualification_ref=qualification,
                head_sha=head, base_sha=base, synthetic_merge_sha=synthetic,
                approval_fact_ref=authority["approval"],
                thread_fact_ref=authority["threads"],
                ruleset_fact_ref=authority["ruleset"],
                boundary_fact_ref=authority["boundary"], required_evidence=[required],
                promotion_ready_at="2026-09-05T12:00:00Z",
            )

    authority = {
        name: authority_fact(root, f"correct-{name}.json", schema, head, base)
        for name, schema in schemas.items()
    }
    with pytest.raises(PromotionEvidenceError, match="QUALIFICATION_INVALID"):
        create_promotion_admission(
            repository=repo, evidence_root=root, qualification_ref=qualification,
            head_sha=head, base_sha=base, synthetic_merge_sha=synthetic,
            approval_fact_ref=authority["approval"],
            thread_fact_ref=authority["threads"],
            ruleset_fact_ref=authority["ruleset"],
            boundary_fact_ref=authority["boundary"], required_evidence=[required],
            promotion_ready_at="2026-09-05T12:00:00Z",
        )


def test_admission_rejects_qualification_digest_and_identity_drift(tmp_path: Path) -> None:
    repo, root, base, head, synthetic = setup(tmp_path)
    qualification = qualification_fact(root, head, repo)
    authority = {
        "approval": authority_fact(root, "approval.json", "quwoquan_ops.promotion_approval_fact.v1", head, base),
        "threads": authority_fact(root, "threads.json", "quwoquan_ops.promotion_thread_fact.v1", head, base),
        "ruleset": authority_fact(root, "ruleset.json", "quwoquan_ops.promotion_ruleset_fact.v1", head, base),
        "boundary": authority_fact(root, "boundary.json", "quwoquan_ops.promotion_boundary_fact.v1", head, base),
    }
    required = write(root, "required.json", required_evidence_fact(
        repository=repo, evidence_root=root, head_sha=head, base_sha=base, evidence=[qualification]))

    def admit(exact: dict[str, str]) -> None:
        create_promotion_admission(
            repository=repo, evidence_root=root, qualification_ref=exact,
            head_sha=head, base_sha=base, synthetic_merge_sha=synthetic,
            approval_fact_ref=authority["approval"],
            thread_fact_ref=authority["threads"],
            ruleset_fact_ref=authority["ruleset"],
            boundary_fact_ref=authority["boundary"], required_evidence=[required],
            promotion_ready_at="2026-09-05T10:00:00Z",
        )

    fact = json.loads((root / qualification["ref"]).read_text())
    fact["qualificationId"] = "sha256:" + "f" * 64
    with pytest.raises(PromotionEvidenceError, match="QUALIFICATION_INVALID"):
        admit(write(root, "digest-drifted-qualification.json", fact))

    fact = json.loads((root / qualification["ref"]).read_text())
    fact["candidate"]["commit"] = base
    unsigned = {
        key: value
        for key, value in fact.items()
        if key not in {"qualificationId", "signer"}
    }
    fact["signer"]["payload"] = base64.b64encode(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    ).decode()
    identity = {key: value for key, value in fact.items() if key != "qualificationId"}
    fact["qualificationId"] = digest(identity)
    with pytest.raises(PromotionEvidenceError, match="QUALIFICATION_INVALID"):
        admit(write(root, "identity-drifted-qualification.json", fact))


def test_admission_rejects_semantically_empty_authority_and_wrong_range_evidence(tmp_path: Path) -> None:
    repo, root, base, head, synthetic = setup(tmp_path)
    qualification = qualification_fact(root, head, repo)
    approval = write(root, "approval.json", {
        "schema": "quwoquan_ops.promotion_approval_fact.v1", "status": "passed",
        "headSha": head, "baseSha": base, "commitSha": head, "decision": "pending", "approvalCount": 0,
    })
    threads = authority_fact(root, "threads.json", "quwoquan_ops.promotion_thread_fact.v1", head, base)
    ruleset = authority_fact(root, "ruleset.json", "quwoquan_ops.promotion_ruleset_fact.v1", head, base)
    boundary = authority_fact(root, "boundary.json", "quwoquan_ops.promotion_boundary_fact.v1", head, base)
    wrong_range = write(root, "required.json", {
        "schema": "quwoquan_ops.promotion_required_evidence_fact.v1", "status": "passed",
        "headSha": head, "baseSha": "f" * 40,
    })
    with pytest.raises(PromotionEvidenceError, match="AUTHORITY_INVALID"):
        create_promotion_admission(
            repository=repo, evidence_root=root, qualification_ref=qualification,
            head_sha=head, base_sha=base, synthetic_merge_sha=synthetic,
            approval_fact_ref=approval, thread_fact_ref=threads, ruleset_fact_ref=ruleset,
            boundary_fact_ref=boundary, required_evidence=[wrong_range],
            promotion_ready_at="2026-09-05T10:00:00Z",
        )
    approval = authority_fact(root, "correct-approval.json", "quwoquan_ops.promotion_approval_fact.v1", head, base)
    with pytest.raises(PromotionEvidenceError, match="EVIDENCE_INVALID"):
        create_promotion_admission(
            repository=repo, evidence_root=root, qualification_ref=qualification,
            head_sha=head, base_sha=base, synthetic_merge_sha=synthetic,
            approval_fact_ref=approval, thread_fact_ref=threads, ruleset_fact_ref=ruleset,
            boundary_fact_ref=boundary, required_evidence=[wrong_range],
            promotion_ready_at="2026-09-05T10:00:00Z",
        )


def test_admission_rejects_head_or_base_as_synthetic_merge(tmp_path: Path) -> None:
    repo, root, base, head, _ = setup(tmp_path)
    qualification = qualification_fact(root, head, repo)
    authority = {
        "approval": authority_fact(root, "approval.json", "quwoquan_ops.promotion_approval_fact.v1", head, base),
        "threads": authority_fact(root, "threads.json", "quwoquan_ops.promotion_thread_fact.v1", head, base),
        "ruleset": authority_fact(root, "ruleset.json", "quwoquan_ops.promotion_ruleset_fact.v1", head, base),
        "boundary": authority_fact(root, "boundary.json", "quwoquan_ops.promotion_boundary_fact.v1", head, base),
    }
    required = write(root, "required.json", {
        "schema": "quwoquan_ops.promotion_required_evidence_fact.v1", "status": "passed",
        "headSha": head, "baseSha": base,
    })
    for invalid in (head, base):
        with pytest.raises(PromotionEvidenceError, match="MERGE_INVALID"):
            create_promotion_admission(
                repository=repo, evidence_root=root, qualification_ref=qualification,
                head_sha=head, base_sha=base, synthetic_merge_sha=invalid,
                approval_fact_ref=authority["approval"], thread_fact_ref=authority["threads"],
                ruleset_fact_ref=authority["ruleset"], boundary_fact_ref=authority["boundary"],
                required_evidence=[required], promotion_ready_at="2026-09-05T10:00:00Z",
            )


def test_validate_hosted_handoff_cli_writes_canonical_binding(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo, _, base, head, synthetic = setup(tmp_path)
    tree = git(repo, "show", "-s", "--format=%T", synthetic)
    record, check, run = hosted_handoff(
        head=head, base=base, synthetic=synthetic, tree=tree
    )
    check_path = tmp_path / "check-run.json"
    run_path = tmp_path / "workflow-run.json"
    output_path = tmp_path / "hosted-handoff.json"
    check_path.write_text(json.dumps(check))
    run_path.write_text(json.dumps(run))

    exit_code = main(
        [
            "validate-hosted-handoff",
            "--check-run-file",
            str(check_path),
            "--workflow-run-file",
            str(run_path),
            "--repository",
            "leadwise/quwoquan",
            "--pull-request-number",
            "42",
            "--head-sha",
            head,
            "--base-sha",
            base,
            "--synthetic-merge-tree",
            tree,
            "--expected-context",
            HANDOFF_CONTEXT,
            "--expected-app-slug",
            "quwoquan-promotion-recorder",
            "--expected-app-id",
            "1234",
            "--expected-workflow-repository",
            "leadwise/quwoquan",
            "--verified-at",
            "2026-09-05T10:04:30Z",
            "--output-file",
            str(output_path),
        ]
    )

    assert exit_code == 0
    result = json.loads(capsys.readouterr().out)
    payload = json.loads(output_path.read_bytes())
    assert output_path.read_bytes() == (
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    )
    assert result == {
        "path": str(output_path.resolve()),
        "exactRef": record["promotionAdmissionRef"],
        "admissionBytesDigest": record["admissionBytesDigest"],
    }
    assert payload["syntheticMergeSha"] == record["syntheticMergeSha"]
    assert payload["syntheticMergeTree"] == tree
    assert payload["headSha"] == head
    assert payload["baseSha"] == base


def test_hosted_handoff_rejects_wrong_actor_app_context_and_range(tmp_path: Path) -> None:
    repo, _, base, head, synthetic = setup(tmp_path)
    tree = git(repo, "show", "-s", "--format=%T", synthetic)
    _, check, run = hosted_handoff(head=head, base=base, synthetic=synthetic, tree=tree)
    mutations = (
        ("context", lambda c, r: c.update(name="untrusted/context")),
        ("app", lambda c, r: c.update(app={"id": 999, "slug": "wrong"})),
        ("actor", lambda c, r: r.update(actor={"login": "head-writer", "id": 88})),
        ("head", lambda c, r: c.update(head_sha=base)),
        ("repository", lambda c, r: c.update(statuses_url="https://api.github.com/repos/evil/repo/statuses/" + head)),
        ("base", lambda c, r: None),
        ("tree", lambda c, r: None),
    )
    import copy
    for name, mutate in mutations:
        bad_check, bad_run = copy.deepcopy(check), copy.deepcopy(run)
        mutate(bad_check, bad_run)
        kwargs = {"head": head, "base": base, "tree": tree}
        if name == "base": kwargs["base"] = "f" * 40
        if name == "tree": kwargs["tree"] = "e" * 40
        with pytest.raises(PromotionEvidenceError):
            validate_handoff(bad_check, bad_run, **kwargs)


def test_hosted_handoff_rejects_replacement_stale_or_non_exact_ref(tmp_path: Path) -> None:
    repo, _, base, head, synthetic = setup(tmp_path)
    tree = git(repo, "show", "-s", "--format=%T", synthetic)
    record, check, run = hosted_handoff(head=head, base=base, synthetic=synthetic, tree=tree)
    check["completed_at"] = "2026-09-05T10:00:01Z"
    with pytest.raises(PromotionEvidenceError, match="HANDOFF_REPLACED"):
        validate_handoff(check, run, head=head, base=base, tree=tree)
    check["completed_at"] = check["started_at"]
    with pytest.raises(PromotionEvidenceError, match="HANDOFF_STALE"):
        validate_hosted_promotion_handoff(
            check_run=check, workflow_run=run, repository="leadwise/quwoquan",
            pull_request_number=42, head_sha=head, base_sha=base,
            synthetic_merge_tree=tree,
            expected_context=HANDOFF_CONTEXT,
            expected_app_slug="quwoquan-promotion-recorder", expected_app_id=1234,
            expected_workflow_repository="leadwise/quwoquan",
            verified_at="2026-09-05T11:00:00Z",
        )
    with pytest.raises(PromotionEvidenceError, match="HANDOFF_INVALID"):
        create_promotion_handoff(
            repository="leadwise/quwoquan", pull_request_number=42,
            head_sha=head, base_sha=base, synthetic_merge_sha=synthetic,
            synthetic_merge_tree=tree, workflow_run_id=1, workflow_run_attempt=1,
            workflow_repository="leadwise/quwoquan", workflow_head_sha=head,
            workflow_actor_login="actor", workflow_actor_id=1,
            promotion_admission_ref="ghcr.io/leadwise/quwoquan/promotion-admission:latest",
            admission_bytes_digest="sha256:" + "b" * 64,
            created_at="2026-09-05T10:00:00Z",
        )
