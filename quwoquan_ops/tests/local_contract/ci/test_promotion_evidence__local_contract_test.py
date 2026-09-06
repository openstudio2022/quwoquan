# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-002
from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path

import pytest

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


def test_admission_and_seal_bind_synthetic_tree(tmp_path: Path) -> None:
    repo, root, base, head, synthetic = setup(tmp_path)
    qualification = qualification_fact(root, head, repo)
    approval = authority_fact(root, "approval.json", "quwoquan_ops.promotion_approval_fact.v1", head, base)
    threads = authority_fact(root, "threads.json", "quwoquan_ops.promotion_thread_fact.v1", head, base)
    ruleset = authority_fact(root, "ruleset.json", "quwoquan_ops.promotion_ruleset_fact.v1", head, base)
    boundary = authority_fact(root, "boundary.json", "quwoquan_ops.promotion_boundary_fact.v1", head, base)
    required = write(root, "required.json", {"schema": "quwoquan_ops.promotion_required_evidence_fact.v1", "status": "passed", "headSha": head, "baseSha": base})
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
    required = write(root, "required.json", {"schema": "quwoquan_ops.promotion_required_evidence_fact.v1", "status": "passed", "headSha": head, "baseSha": base})
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
    required = write(root, "required.json", {"schema": "quwoquan_ops.promotion_required_evidence_fact.v1", "status": "passed", "headSha": head, "baseSha": base})

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
    required = write(root, "required.json", {"schema": "quwoquan_ops.promotion_required_evidence_fact.v1", "status": "passed", "headSha": head, "baseSha": base})

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
