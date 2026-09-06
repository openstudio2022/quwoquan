# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-001.t4
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-001.t6
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker

from quwoquan_ops.ci.release_tag_admission import (
    ReleaseTagAdmissionError,
    assert_release_tag_intent_unused,
    create_release_candidate_tag_intent,
    create_release_tag_intent,
    digest,
    finalize_release_candidate_tag_admission,
    finalize_release_tag_admission,
    record_tag_mutation_outcome,
    validate_product_version_manifest,
)

ROOT = Path(__file__).resolve().parents[4]
BASE_MANIFEST = ROOT / "quwoquan_ops/policies/product_version.yaml"
POLICY = ROOT / "quwoquan_ops/policies/release_selection_policy.yaml"
SCHEMA = ROOT / "quwoquan_ops/environments/evidence/release_tag_admission_fact.schema.json"
INTENT_AT = "2026-09-05T11:00:00Z"
OUTCOME_AT = "2026-09-05T11:00:01Z"
HOSTED_AT = "2026-09-05T11:00:02Z"
FINAL_AT = "2026-09-05T11:00:03Z"
REPOSITORY = "quwoquan/integration"
PRODUCER = {
    "kind": "github_app_installation",
    "appId": 24680,
    "installationId": 13579,
    "slug": "release-controller",
}
D1 = "sha256:" + "1" * 64
D2 = "sha256:" + "2" * 64
D3 = "sha256:" + "3" * 64
D4 = "sha256:" + "4" * 64


def git(repo: Path, *args: str, check: bool = True) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, text=True,
        capture_output=True, check=check,
    ).stdout.strip()


def write(root: Path, ref: str, value: dict[str, Any]) -> dict[str, str]:
    path = root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return {"ref": ref, "digest": digest(path)}


def create_tag(repo: Path, name: str, commit: str, *, annotated: bool = True) -> None:
    args = ["tag", "-a", name, commit, "-m", name] if annotated else ["tag", name, commit]
    git(repo, *args)


def active_manifest(tmp_path: Path, version: str = "1.2.0") -> Path:
    value = yaml.safe_load(BASE_MANIFEST.read_text(encoding="utf-8"))
    value["releaseTrain"] = {
        "state": "active", "targetVersion": version, "bump": "minor",
        "bumpReason": "backward-compatible release", "compatibilityBoundary": "public-api",
    }
    value["previousStable"] = {
        "status": "not_imported", "tagName": None,
        "tagObjectOid": None, "peeledCommit": None, "admissionFact": None,
        "reasonCode": "PRODUCT_VERSION.PREVIOUS_STABLE_NOT_IMPORTED",
    }
    authority = write(tmp_path / "evidence", "authority/initial-release.json", {
        "schema": "quwoquan_ops.initial_release_authority_fact.v1",
        "status": "approved",
        "purpose": "activate_initial_product_release_train",
    })
    value["initialReleaseAuthority"] = {
        "status": "approved", "authorityFact": authority,
    }
    value["activation"] = {
        "decision": "active", "basis": "initial_release_authority_approved", "reasonCode": None,
    }
    path = tmp_path / "product_version.yaml"
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
    return path


def fixture(tmp_path: Path) -> tuple[Path, Path, Path, str, str]:
    repo = tmp_path / "repo"
    store = tmp_path / "evidence"
    repo.mkdir()
    store.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "release-controller")
    git(repo, "config", "user.email", "release-controller@example.com")
    (repo / "source.txt").write_text("main\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "main")
    main = git(repo, "rev-parse", "HEAD")
    tree = git(repo, "show", "-s", "--format=%T", main)
    return repo, store, active_manifest(tmp_path), main, tree


def authority_ref(manifest: Path) -> dict[str, str]:
    return yaml.safe_load(manifest.read_text(encoding="utf-8"))[
        "initialReleaseAuthority"
    ]["authorityFact"]


def reservation(
    store: Path, name: str, kind: str, commit: str, tree: str,
) -> dict[str, str]:
    return write(store, f"reservation/{name}.json", {
        "schema": "quwoquan_ops.release_tag_reservation_fact.v1",
        "status": "reserved", "tagName": name, "tagKind": kind,
        "sourceGitSha": commit, "sourceTree": tree,
    })


def identified(value: dict[str, Any], field: str) -> dict[str, Any]:
    value[field] = digest(value)
    return value


def pre_creator(store: Path, name: str) -> dict[str, str]:
    return write(store, f"readback/{name}-creator-before.json", identified({
        "schema": "quwoquan_ops.creator_readback_fact.v1", "status": "verified",
        "phase": "pre_mutation", "producer": PRODUCER, "repository": REPOSITORY,
        "tagRef": f"refs/tags/{name}", "tagName": name,
        "tagObjectOid": None, "peeledCommit": None,
        "creator": None, "creationRecord": None, "observedAt": INTENT_AT,
    }, "readbackId"))



def ruleset_body(
    tag_name: str, *, phase: str, oid: str | None, commit: str | None,
    observed_at: str,
) -> dict[str, Any]:
    return identified({
        "schema": "quwoquan_ops.ruleset_readback_fact.v1", "status": "verified",
        "phase": phase, "producer": PRODUCER, "repository": REPOSITORY,
        "tagRef": f"refs/tags/{tag_name}", "tagName": tag_name,
        "tagObjectOid": oid, "peeledCommit": commit,
        "rulesetId": 7001,
        "rulesetVersion": {"etag": '"ruleset-etag-12"', "apiPayloadDigest": D4},
        "target": "tag", "enforcement": "active",
        "refNamePattern": {"include": ["refs/tags/v*"], "exclude": []},
        "create": {"decision": "allowed", "mode": "create_only", "bypassActors": []},
        "update": {"decision": "denied", "bypassActors": []},
        "delete": {"decision": "denied", "bypassActors": []},
        "bypass": {"mode": "closed", "actors": []},
        "observedAt": observed_at,
    }, "readbackId")


def pre_ruleset(store: Path, name: str) -> dict[str, str]:
    return write(
        store, f"readback/{name}-ruleset-before.json",
        ruleset_body(name, phase="pre_mutation", oid=None, commit=None, observed_at=INTENT_AT),
    )

def hosted_readbacks(
    store: Path, repo: Path, tag_name: str, outcome_id: str,
) -> tuple[dict[str, str], dict[str, str]]:
    oid = git(repo, "rev-parse", f"refs/tags/{tag_name}")
    commit = git(repo, "rev-parse", f"refs/tags/{tag_name}^{{}}")
    creation_record = {
        "kind": "github_check_run", "recordId": 98765,
        "nodeId": "CR_kwDOrelease123", "name": "release-tag-creation",
        "externalId": f"release-tag:{REPOSITORY}:{tag_name}:{oid}:{outcome_id}",
        "status": "completed", "conclusion": "success", "headSha": commit,
        "appId": PRODUCER["appId"], "appSlug": PRODUCER["slug"],
        "repository": REPOSITORY, "completedAt": HOSTED_AT,
    }
    creator = write(store, f"readback/{tag_name}-creator-after.json", identified({
        "schema": "quwoquan_ops.creator_readback_fact.v1", "status": "verified",
        "phase": "post_mutation", "producer": PRODUCER, "repository": REPOSITORY,
        "tagRef": f"refs/tags/{tag_name}", "tagName": tag_name,
        "tagObjectOid": oid, "peeledCommit": commit,
        "creator": "release-controller[bot]",
        "creationRecord": creation_record, "observedAt": HOSTED_AT,
    }, "readbackId"))
    ruleset = write(
        store, f"readback/{tag_name}-ruleset.json",
        ruleset_body(
            tag_name, phase="post_mutation", oid=oid,
            commit=commit, observed_at=HOSTED_AT,
        ),
    )
    return creator, ruleset



def load_fact(store: Path, ref: dict[str, str]) -> dict[str, Any]:
    return json.loads((store / ref["ref"]).read_text(encoding="utf-8"))


def rewrite_identified(
    store: Path, ref: str, value: dict[str, Any], identity: str = "readbackId",
) -> dict[str, str]:
    value.pop(identity, None)
    return write(store, ref, identified(value, identity))


def exact(store: Path, path: Path) -> dict[str, str]:
    return {"ref": path.relative_to(store).as_posix(), "digest": digest(path)}


def rc_selection(
    store: Path, manifest: Path, name: str, commit: str, tree: str,
) -> dict[str, str]:
    return write(store, f"selection/{name}.json", {
        "schema": "quwoquan_ops.release_candidate_selection_fact.v1",
        "status": "approved", "tagName": name, "sourceGitSha": commit,
        "sourceTree": tree, "productVersionManifestDigest": digest(manifest),
    })


def create_rc_intent(
    repo: Path, store: Path, manifest: Path, name: str, commit: str, tree: str,
) -> tuple[Path, dict[str, str]]:
    path = create_release_candidate_tag_intent(
        repository=repo, evidence_root=store, tag_name=name, source_git_sha=commit,
        product_version_manifest_path=manifest, release_selection_policy_path=POLICY,
        reservation_ref=reservation(store, name, "rc", commit, tree),
        selection_fact_ref=rc_selection(store, manifest, name, commit, tree),
        creator_readback_ref=pre_creator(store, name),
        ruleset_readback_ref=pre_ruleset(store, name),
        repository_identity=REPOSITORY,
        controller_app_id=PRODUCER["appId"],
        controller_installation_id=PRODUCER["installationId"],
        controller_app_slug=PRODUCER["slug"],
        initial_release_authority_ref=authority_ref(manifest), admitted_at=INTENT_AT,
    )
    return path, exact(store, path)


def finalize_rc(
    repo: Path, store: Path, name: str, intent: dict[str, str], commit: str,
) -> tuple[Path, dict[str, str]]:
    create_tag(repo, name, commit)
    oid = git(repo, "rev-parse", f"refs/tags/{name}")
    outcome_path = record_tag_mutation_outcome(
        evidence_root=store, admission_intent_ref=intent, tag_kind="rc",
        tag_name=name, status="created", tag_object_oid=oid,
        peeled_commit=commit, recorded_at=OUTCOME_AT,
    )
    creator, ruleset = hosted_readbacks(
        store, repo, name, json.loads(outcome_path.read_text())["outcomeId"],
    )
    path = finalize_release_candidate_tag_admission(
        repository=repo, evidence_root=store, tag_name=name,
        admission_intent_ref=intent, mutation_outcome_ref=exact(store, outcome_path),
        creator_readback_ref=creator, ruleset_readback_ref=ruleset,
        release_selection_policy_path=POLICY, admitted_at=FINAL_AT,
    )
    return path, exact(store, path)


def admit_rc(
    repo: Path, store: Path, manifest: Path, name: str, commit: str, tree: str,
) -> tuple[Path, dict[str, str]]:
    _, intent = create_rc_intent(repo, store, manifest, name, commit, tree)
    return finalize_rc(repo, store, name, intent, commit)


def stable_inputs(
    store: Path, manifest: Path, rc: dict[str, str], *, tag_name: str = "v1.2.0",
) -> dict[str, dict[str, str]]:
    rc_fact = json.loads((store / rc["ref"]).read_text(encoding="utf-8"))
    artifacts = [
        {"platform": "android", "ociRef": f"ghcr.io/q/app@{D1}", "digest": D1},
        {"platform": "ios", "ociRef": f"ghcr.io/q/ios@{D4}", "digest": D4},
        {"platform": "service", "ociRef": f"ghcr.io/q/service@{D2}", "digest": D2},
        {"platform": "web", "ociRef": f"ghcr.io/q/web@{D3}", "digest": D3},
    ]
    request_body: dict[str, Any] = {
        "schema": "quwoquan_ops.release_qualification_request.v1",
        "rcTagAdmission": rc,
        "sourceGitSha": rc_fact["peeledCommit"], "sourceTree": rc_fact["sourceTree"],
        "tagName": rc_fact["tagName"],
    }
    request_body["requestId"] = digest(request_body)
    request = write(store, "qualification/request.json", request_body)
    allocation_body: dict[str, Any] = {
        "schema": "quwoquan_ops.artifact_build_number_allocation.v1",
        "requestId": request_body["requestId"], "qualificationRequest": request,
        "artifactBuildNumber": 17, "predecessor": None,
        "hostedAuthority": {
            "provider": "github_actions_workflow_run_number", "runId": "9001", "runNumber": 17,
        },
    }
    allocation_body["allocationId"] = digest(allocation_body)
    allocation = write(store, "qualification/allocation.json", allocation_body)
    material_body: dict[str, Any] = {
        "schema": "quwoquan_ops.candidate_material_manifest.v1",
        "qualificationRequest": request, "artifactBuildNumberAllocation": allocation,
        "sourceGitSha": rc_fact["peeledCommit"], "sourceTree": rc_fact["sourceTree"],
        "tagName": rc_fact["tagName"], "artifactBuildNumber": 17,
        "productVersionManifest": {"ref": "source/product_version.yaml", "digest": digest(manifest)},
        "artifacts": artifacts,
    }
    material_body["materialId"] = digest(material_body)
    material = write(store, "qualification/material.json", material_body)
    qualification_body: dict[str, Any] = {
        "schema": "quwoquan_ops.qualification_fact.v1", "decision": "qualified",
        "qualificationRequest": request, "candidateMaterialManifest": material,
        "sourceGitSha": rc_fact["peeledCommit"], "sourceTree": rc_fact["sourceTree"],
        "tagName": rc_fact["tagName"], "artifactBuildNumber": 17, "artifacts": artifacts,
    }
    qualification_body["qualificationId"] = digest(qualification_body)
    qualification = write(store, "qualification/fact.json", qualification_body)
    product = write(store, "authority/product.json", {
        "schema": "quwoquan_ops.product_release_authority_fact.v1", "status": "approved",
        "selectedRcTagObjectOid": rc_fact["tagObjectOid"],
        "qualificationId": qualification_body["qualificationId"],
        "productVersionManifestDigest": digest(manifest),
        "sourceGitSha": rc_fact["peeledCommit"], "candidateMaterialId": material_body["materialId"],
    })
    release = write(store, "authority/release.json", {
        "schema": "quwoquan_ops.release_authority_fact.v1", "status": "approved",
        "stableTagName": tag_name, "selectedRcTagObjectOid": rc_fact["tagObjectOid"],
        "qualificationId": qualification_body["qualificationId"],
        "sourceGitSha": rc_fact["peeledCommit"], "candidateMaterialId": material_body["materialId"],
    })
    return {"qualification": qualification, "product": product, "release": release}


def create_stable_intent(
    repo: Path, store: Path, manifest: Path, rc: dict[str, str],
    inputs: dict[str, dict[str, str]], main: str, tree: str, name: str = "v1.2.0",
) -> tuple[Path, dict[str, str]]:
    path = create_release_tag_intent(
        repository=repo, evidence_root=store, tag_name=name, source_git_sha=main,
        product_version_manifest_path=manifest, release_selection_policy_path=POLICY,
        reservation_ref=reservation(store, name, "stable", main, tree),
        selected_rc_admission_ref=rc,
        qualification_fact_ref=inputs["qualification"],
        product_authority_fact_ref=inputs["product"],
        release_authority_fact_ref=inputs["release"],
        creator_readback_ref=pre_creator(store, name),
        ruleset_readback_ref=pre_ruleset(store, name),
        repository_identity=REPOSITORY,
        controller_app_id=PRODUCER["appId"],
        controller_installation_id=PRODUCER["installationId"],
        controller_app_slug=PRODUCER["slug"],
        initial_release_authority_ref=authority_ref(manifest), admitted_at=INTENT_AT,
    )
    return path, exact(store, path)


def finalize_stable(
    repo: Path, store: Path, name: str, intent: dict[str, str], main: str,
) -> Path:
    create_tag(repo, name, main)
    oid = git(repo, "rev-parse", f"refs/tags/{name}")
    outcome = record_tag_mutation_outcome(
        evidence_root=store, admission_intent_ref=intent, tag_kind="stable",
        tag_name=name, status="created", tag_object_oid=oid,
        peeled_commit=main, recorded_at=OUTCOME_AT,
    )
    creator, ruleset = hosted_readbacks(
        store, repo, name, json.loads(outcome.read_text())["outcomeId"],
    )
    return finalize_release_tag_admission(
        repository=repo, evidence_root=store, tag_name=name,
        admission_intent_ref=intent, mutation_outcome_ref=exact(store, outcome),
        creator_readback_ref=creator, ruleset_readback_ref=ruleset,
        release_selection_policy_path=POLICY, admitted_at=FINAL_AT,
    )


def test_repository_manifest_is_strict_fail_closed_without_fabricated_previous_stable() -> None:
    value = yaml.safe_load(BASE_MANIFEST.read_text(encoding="utf-8"))
    assert value["kind"] == "ProductVersionManifest"
    assert value["previousStable"]["status"] == "not_imported"
    assert value["previousStable"]["tagObjectOid"] is None
    assert value["releaseTrain"]["state"] == "inactive"
    parsed, _, state = validate_product_version_manifest(manifest_path=BASE_MANIFEST)
    assert parsed == value
    assert state == "blocked"


def test_rc_intent_is_sealed_before_any_git_tag_mutation(tmp_path: Path) -> None:
    repo, store, manifest, main, tree = fixture(tmp_path)
    path, intent = create_rc_intent(repo, store, manifest, "v1.2.0-rc.1", main, tree)
    assert not git(repo, "show-ref", "--verify", "refs/tags/v1.2.0-rc.1", check=False)
    value = json.loads(path.read_text(encoding="utf-8"))
    assert value["schema"] == "quwoquan_ops.release_tag_admission_intent.v1"
    assert value["decision"] == "mutation_admitted"
    assert value["preCreatorReadback"]["ref"].endswith("creator-before.json")
    assert value["preRulesetReadback"]["ref"].endswith("ruleset-before.json")
    assert "tagObjectOid" not in value
    assert_release_tag_intent_unused(
        evidence_root=store, admission_intent_ref=intent,
        tag_kind="rc", tag_name="v1.2.0-rc.1",
    )


def test_pre_admission_rejects_invalid_reservation_and_qualification_without_mutation(
    tmp_path: Path,
) -> None:
    repo, store, manifest, main, tree = fixture(tmp_path)
    bad_reservation = reservation(store, "v1.2.0-rc.1", "rc", main, "f" * 40)
    with pytest.raises(ReleaseTagAdmissionError, match="RESERVATION_INVALID"):
        create_release_candidate_tag_intent(
            repository=repo, evidence_root=store, tag_name="v1.2.0-rc.1",
            source_git_sha=main, product_version_manifest_path=manifest,
            release_selection_policy_path=POLICY, reservation_ref=bad_reservation,
            selection_fact_ref=rc_selection(store, manifest, "v1.2.0-rc.1", main, tree),
            creator_readback_ref=pre_creator(store, "v1.2.0-rc.1"),
            ruleset_readback_ref=pre_ruleset(store, "v1.2.0-rc.1"),
            repository_identity=REPOSITORY,
            controller_app_id=PRODUCER["appId"],
            controller_installation_id=PRODUCER["installationId"],
            controller_app_slug=PRODUCER["slug"],
            initial_release_authority_ref=authority_ref(manifest), admitted_at=INTENT_AT,
        )
    assert not git(repo, "show-ref", "--verify", "refs/tags/v1.2.0-rc.1", check=False)

    _, rc = admit_rc(repo, store, manifest, "v1.2.0-rc.2", main, tree)
    inputs = stable_inputs(store, manifest, rc)
    rejected = json.loads((store / inputs["qualification"]["ref"]).read_text())
    rejected["decision"] = "rejected"
    inputs["qualification"] = write(store, "qualification/rejected.json", rejected)
    with pytest.raises(ReleaseTagAdmissionError, match="QUALIFICATION_INVALID"):
        create_stable_intent(repo, store, manifest, rc, inputs, main, tree)
    assert not git(repo, "show-ref", "--verify", "refs/tags/v1.2.0", check=False)


def test_failed_mutation_is_terminal_and_intent_cannot_replay(tmp_path: Path) -> None:
    repo, store, manifest, main, tree = fixture(tmp_path)
    _, intent = create_rc_intent(repo, store, manifest, "v1.2.0-rc.1", main, tree)
    outcome = record_tag_mutation_outcome(
        evidence_root=store, admission_intent_ref=intent, tag_kind="rc",
        tag_name="v1.2.0-rc.1", status="failed", recorded_at=OUTCOME_AT,
    )
    assert json.loads(outcome.read_text())["status"] == "failed"
    with pytest.raises(ReleaseTagAdmissionError, match="MUTATION_FAILED"):
        assert_release_tag_intent_unused(
            evidence_root=store, admission_intent_ref=intent,
            tag_kind="rc", tag_name="v1.2.0-rc.1",
        )
    with pytest.raises(ReleaseTagAdmissionError, match="MUTATION_FAILED"):
        record_tag_mutation_outcome(
            evidence_root=store, admission_intent_ref=intent, tag_kind="rc",
            tag_name="v1.2.0-rc.1", status="created",
            tag_object_oid="a" * 40, peeled_commit=main, recorded_at=OUTCOME_AT,
        )


def test_created_intent_replay_is_rejected_before_second_mutation(tmp_path: Path) -> None:
    repo, store, manifest, main, tree = fixture(tmp_path)
    _, intent = create_rc_intent(repo, store, manifest, "v1.2.0-rc.1", main, tree)
    create_tag(repo, "v1.2.0-rc.1", main)
    record_tag_mutation_outcome(
        evidence_root=store, admission_intent_ref=intent, tag_kind="rc",
        tag_name="v1.2.0-rc.1", status="created",
        tag_object_oid=git(repo, "rev-parse", "refs/tags/v1.2.0-rc.1"),
        peeled_commit=main, recorded_at=OUTCOME_AT,
    )
    with pytest.raises(ReleaseTagAdmissionError, match="INTENT_REPLAY"):
        assert_release_tag_intent_unused(
            evidence_root=store, admission_intent_ref=intent,
            tag_kind="rc", tag_name="v1.2.0-rc.1",
        )


def test_rc_sequence_reuse_and_non_monotonic_intents_are_rejected(tmp_path: Path) -> None:
    repo, store, manifest, main, tree = fixture(tmp_path)
    create_rc_intent(repo, store, manifest, "v1.2.0-rc.2", main, tree)
    with pytest.raises(ReleaseTagAdmissionError, match="INTENT_REPLAY"):
        create_rc_intent(repo, store, manifest, "v1.2.0-rc.2", main, tree)
    with pytest.raises(ReleaseTagAdmissionError, match="RC_NOT_MONOTONIC"):
        create_rc_intent(repo, store, manifest, "v1.2.0-rc.1", main, tree)
    assert not git(repo, "show-ref", "--verify", "refs/tags/v1.2.0-rc.1", check=False)
    assert not git(repo, "show-ref", "--verify", "refs/tags/v1.2.0-rc.2", check=False)


def test_final_rc_binds_actual_object_and_hosted_creator_readback(tmp_path: Path) -> None:
    repo, store, manifest, main, tree = fixture(tmp_path)
    _, intent = create_rc_intent(repo, store, manifest, "v1.2.0-rc.1", main, tree)
    path, _ = finalize_rc(repo, store, "v1.2.0-rc.1", intent, main)
    value = json.loads(path.read_text())
    assert value["schema"] == "quwoquan_ops.release_candidate_tag_admission_fact.v1"
    assert value["tagObjectOid"] == git(repo, "rev-parse", "refs/tags/v1.2.0-rc.1")
    creator = load_fact(store, value["creatorReadback"])
    assert creator["tagObjectOid"] == value["tagObjectOid"]
    assert value["admissionIntent"] == intent
    outcome = load_fact(store, value["mutationOutcome"])
    assert outcome["intent"] == intent
    assert outcome["tagObjectOid"] == value["tagObjectOid"]
    Draft202012Validator(
        json.loads(SCHEMA.read_text()), format_checker=FormatChecker(),
    ).validate(value)


def test_finalization_rejects_hosted_object_or_creator_mismatch(tmp_path: Path) -> None:
    repo, store, manifest, main, tree = fixture(tmp_path)
    _, intent = create_rc_intent(repo, store, manifest, "v1.2.0-rc.1", main, tree)
    create_tag(repo, "v1.2.0-rc.1", main)
    actual = git(repo, "rev-parse", "refs/tags/v1.2.0-rc.1")
    outcome = record_tag_mutation_outcome(
        evidence_root=store, admission_intent_ref=intent, tag_kind="rc",
        tag_name="v1.2.0-rc.1", status="created", tag_object_oid=actual,
        peeled_commit=main, recorded_at=OUTCOME_AT,
    )
    creator, ruleset = hosted_readbacks(
        store, repo, "v1.2.0-rc.1", json.loads(outcome.read_text())["outcomeId"],
    )
    wrong_creator_body = json.loads((store / creator["ref"]).read_text())
    wrong_creator_body["tagObjectOid"] = "b" * 40
    wrong_creator_body.pop("readbackId")
    wrong_creator = write(
        store, "readback/wrong-creator.json",
        identified(wrong_creator_body, "readbackId"),
    )
    with pytest.raises(ReleaseTagAdmissionError, match="READBACK_INVALID"):
        finalize_release_candidate_tag_admission(
            repository=repo, evidence_root=store, tag_name="v1.2.0-rc.1",
            admission_intent_ref=intent, mutation_outcome_ref=exact(store, outcome),
            creator_readback_ref=wrong_creator, ruleset_readback_ref=ruleset,
            release_selection_policy_path=POLICY, admitted_at=FINAL_AT,
        )
    wrong_body = {
        "schema": "quwoquan_ops.release_tag_mutation_outcome_fact.v1",
        "intent": intent, "intentId": json.loads((store / intent["ref"]).read_text())["intentId"],
        "tagKind": "rc", "tagName": "v1.2.0-rc.1", "status": "created",
        "tagObjectOid": "c" * 40, "peeledCommit": main, "recordedAt": OUTCOME_AT,
    }
    wrong_body["outcomeId"] = digest(wrong_body)
    wrong_outcome = write(store, "mutation/wrong-with-id.json", wrong_body)
    with pytest.raises(ReleaseTagAdmissionError, match="MUTATION_MISMATCH"):
        finalize_release_candidate_tag_admission(
            repository=repo, evidence_root=store, tag_name="v1.2.0-rc.1",
            admission_intent_ref=intent, mutation_outcome_ref=wrong_outcome,
            creator_readback_ref=creator, ruleset_readback_ref=ruleset,
            release_selection_policy_path=POLICY, admitted_at=FINAL_AT,
        )


def prepared_rc_finalization(
    tmp_path: Path,
) -> tuple[Path, Path, str, dict[str, str], Path, dict[str, str], dict[str, str]]:
    repo, store, manifest, main, tree = fixture(tmp_path)
    _, intent = create_rc_intent(repo, store, manifest, "v1.2.0-rc.1", main, tree)
    create_tag(repo, "v1.2.0-rc.1", main)
    oid = git(repo, "rev-parse", "refs/tags/v1.2.0-rc.1")
    outcome = record_tag_mutation_outcome(
        evidence_root=store, admission_intent_ref=intent, tag_kind="rc",
        tag_name="v1.2.0-rc.1", status="created", tag_object_oid=oid,
        peeled_commit=main, recorded_at=OUTCOME_AT,
    )
    creator, ruleset = hosted_readbacks(
        store, repo, "v1.2.0-rc.1", load_fact(store, exact(store, outcome))["outcomeId"],
    )
    return repo, store, main, intent, outcome, creator, ruleset


def test_pre_readback_rejects_wrong_producer_app_repository_and_fabricated_creator(
    tmp_path: Path,
) -> None:
    repo, store, manifest, main, tree = fixture(tmp_path)
    for field, replacement in (
        ("appId", 99999), ("installationId", 99999), ("repository", "evil/fork"),
        ("creator", "release-controller"),
    ):
        creator = load_fact(store, pre_creator(store, "v1.2.0-rc.1"))
        if field in {"appId", "installationId"}:
            creator["producer"][field] = replacement
        else:
            creator[field] = replacement
        bad = rewrite_identified(store, f"bad/pre-{field}.json", creator)
        with pytest.raises(ReleaseTagAdmissionError, match="READBACK_INVALID"):
            create_release_candidate_tag_intent(
                repository=repo, evidence_root=store, tag_name="v1.2.0-rc.1",
                source_git_sha=main, product_version_manifest_path=manifest,
                release_selection_policy_path=POLICY,
                reservation_ref=reservation(store, "v1.2.0-rc.1", "rc", main, tree),
                selection_fact_ref=rc_selection(store, manifest, "v1.2.0-rc.1", main, tree),
                creator_readback_ref=bad,
                ruleset_readback_ref=pre_ruleset(store, "v1.2.0-rc.1"),
                repository_identity=REPOSITORY,
                controller_app_id=PRODUCER["appId"],
                controller_installation_id=PRODUCER["installationId"],
                controller_app_slug=PRODUCER["slug"],
                initial_release_authority_ref=authority_ref(manifest),
                admitted_at=INTENT_AT,
            )


def test_finalization_rejects_post_producer_repo_commit_and_check_record_drift(
    tmp_path: Path,
) -> None:
    repo, store, _, intent, outcome, creator, ruleset = prepared_rc_finalization(tmp_path)
    for label, mutate, code in (
        ("producer", lambda fact: fact["producer"].update(appId=99999), "READBACK_INVALID"),
        ("repository", lambda fact: fact.update(repository="evil/fork"), "READBACK_INVALID"),
        ("commit", lambda fact: fact.update(peeledCommit="f" * 40), "READBACK_INVALID"),
        ("actor", lambda fact: fact.update(creator="release-controller"), "CONTROLLER_DENIED"),
        ("check-app", lambda fact: fact["creationRecord"].update(appId=99999), "CONTROLLER_DENIED"),
        ("check-object", lambda fact: fact["creationRecord"].update(externalId="release-tag:forged"), "CONTROLLER_DENIED"),
    ):
        fact = load_fact(store, creator)
        mutate(fact)
        bad = rewrite_identified(store, f"bad/post-{label}.json", fact)
        with pytest.raises(ReleaseTagAdmissionError, match=code):
            finalize_release_candidate_tag_admission(
                repository=repo, evidence_root=store, tag_name="v1.2.0-rc.1",
                admission_intent_ref=intent, mutation_outcome_ref=exact(store, outcome),
                creator_readback_ref=bad, ruleset_readback_ref=ruleset,
                release_selection_policy_path=POLICY, admitted_at=FINAL_AT,
            )


def test_finalization_rejects_forged_readback_self_identity(tmp_path: Path) -> None:
    repo, store, _, intent, outcome, creator, ruleset = prepared_rc_finalization(tmp_path)
    fact = load_fact(store, creator)
    fact["readbackId"] = D1
    forged = write(store, "bad/forged-readback-id.json", fact)
    with pytest.raises(ReleaseTagAdmissionError, match="IDENTITY_INVALID"):
        finalize_release_candidate_tag_admission(
            repository=repo, evidence_root=store, tag_name="v1.2.0-rc.1",
            admission_intent_ref=intent, mutation_outcome_ref=exact(store, outcome),
            creator_readback_ref=forged, ruleset_readback_ref=ruleset,
            release_selection_policy_path=POLICY, admitted_at=FINAL_AT,
        )


def test_finalization_rejects_ruleset_version_policy_and_bypass_drift(tmp_path: Path) -> None:
    repo, store, _, intent, outcome, creator, ruleset = prepared_rc_finalization(tmp_path)
    for label, mutate in (
        ("producer", lambda fact: fact["producer"].update(installationId=99999)),
        ("repository", lambda fact: fact.update(repository="evil/fork")),
        ("object", lambda fact: fact.update(tagObjectOid="f" * 40)),
        ("version", lambda fact: fact["rulesetVersion"].update(etag='"ruleset-etag-13"')),
        ("create", lambda fact: fact["create"].update(mode="upsert")),
        ("update", lambda fact: fact["update"].update(decision="allowed")),
        ("delete", lambda fact: fact["delete"].update(decision="allowed")),
        ("bypass", lambda fact: fact["bypass"].update(actors=[{"type": "Integration", "id": 1}])),
    ):
        fact = load_fact(store, ruleset)
        mutate(fact)
        bad = rewrite_identified(store, f"bad/ruleset-{label}.json", fact)
        with pytest.raises(ReleaseTagAdmissionError, match="READBACK_INVALID"):
            finalize_release_candidate_tag_admission(
                repository=repo, evidence_root=store, tag_name="v1.2.0-rc.1",
                admission_intent_ref=intent, mutation_outcome_ref=exact(store, outcome),
                creator_readback_ref=creator, ruleset_readback_ref=bad,
                release_selection_policy_path=POLICY, admitted_at=FINAL_AT,
            )


def test_finalization_rejects_missing_predecessor_and_time_reversal(tmp_path: Path) -> None:
    repo, store, _, intent, outcome, creator, ruleset = prepared_rc_finalization(tmp_path)
    intent_body = load_fact(store, intent)
    intent_body.pop("preRulesetReadback")
    missing = rewrite_identified(store, "bad/intent-missing-predecessor.json", intent_body, "intentId")
    with pytest.raises(ReleaseTagAdmissionError, match="INTENT_INVALID"):
        finalize_release_candidate_tag_admission(
            repository=repo, evidence_root=store, tag_name="v1.2.0-rc.1",
            admission_intent_ref=missing, mutation_outcome_ref=exact(store, outcome),
            creator_readback_ref=creator, ruleset_readback_ref=ruleset,
            release_selection_policy_path=POLICY, admitted_at=FINAL_AT,
        )
    with pytest.raises(ReleaseTagAdmissionError, match="TIME_ORDER_INVALID"):
        finalize_release_candidate_tag_admission(
            repository=repo, evidence_root=store, tag_name="v1.2.0-rc.1",
            admission_intent_ref=intent, mutation_outcome_ref=exact(store, outcome),
            creator_readback_ref=creator, ruleset_readback_ref=ruleset,
            release_selection_policy_path=POLICY, admitted_at=INTENT_AT,
        )
    reversed_root = tmp_path / "outcome-reversed"
    reversed_root.mkdir()
    repo2, store2, manifest2, main2, tree2 = fixture(reversed_root)
    _, intent2 = create_rc_intent(repo2, store2, manifest2, "v1.2.0-rc.1", main2, tree2)
    with pytest.raises(ReleaseTagAdmissionError, match="TIME_ORDER_INVALID"):
        record_tag_mutation_outcome(
            evidence_root=store2, admission_intent_ref=intent2, tag_kind="rc",
            tag_name="v1.2.0-rc.1", status="failed",
            recorded_at="2026-09-05T10:59:59Z",
        )


def test_stable_intent_and_final_admission_use_same_two_phase_protocol(tmp_path: Path) -> None:
    repo, store, manifest, main, tree = fixture(tmp_path)
    _, rc = admit_rc(repo, store, manifest, "v1.2.0-rc.1", main, tree)
    inputs = stable_inputs(store, manifest, rc)
    intent_path, intent = create_stable_intent(
        repo, store, manifest, rc, inputs, main, tree,
    )
    assert not git(repo, "show-ref", "--verify", "refs/tags/v1.2.0", check=False)
    assert json.loads(intent_path.read_text())["decision"] == "mutation_admitted"
    path = finalize_stable(repo, store, "v1.2.0", intent, main)
    stable = json.loads(path.read_text())
    assert stable["schema"] == "quwoquan_ops.release_tag_admission_fact.v1"
    assert stable["tagObjectOid"] == git(repo, "rev-parse", "refs/tags/v1.2.0")
    assert stable["qualificationFact"] == inputs["qualification"]
    creator = load_fact(store, stable["creatorReadback"])
    assert creator["tagObjectOid"] == stable["tagObjectOid"]
    assert stable["admissionIntent"] == intent
    assert load_fact(store, stable["mutationOutcome"])["intent"] == intent
    Draft202012Validator(
        json.loads(SCHEMA.read_text()), format_checker=FormatChecker(),
    ).validate(stable)


def test_release_control_uses_only_two_phase_canonical_tag_api() -> None:
    control = (ROOT / "quwoquan_ops/ci/release_control.py").read_text()
    implementation = (ROOT / "quwoquan_ops/ci/release_tag_admission.py").read_text()
    for token in (
        "create_release_candidate_tag_intent",
        "create_release_tag_intent",
        "record_tag_mutation_outcome",
        "finalize_release_candidate_tag_admission",
        "finalize_release_tag_admission",
    ):
        assert token in control
        assert f"def {token}(" in implementation
    for retired in ("admit_release_candidate_tag", "admit_release_tag"):
        assert retired not in control
        assert f"def {retired}(" not in implementation
    for command in (
        'sub.add_parser(f"tag-admit-{kind}-intent")',
        'sub.add_parser("tag-mutation-outcome")',
        'sub.add_parser(f"tag-admit-{kind}-finalize")',
    ):
        assert command in control


def test_no_committer_date_identity_synthesis_in_controller() -> None:
    workflow = (ROOT / ".github/workflows/release-tag-selection.yml").read_text()
    assert "GIT_COMMITTER_DATE" not in workflow
    assert "pending:" not in workflow
    assert "tag-admit-rc-intent" in workflow and "tag-admit-stable-intent" in workflow
    create = workflow.index('git tag -a "$TAG"')
    push = workflow.index('git push origin "refs/tags/$TAG:refs/tags/$TAG"')
    remote = workflow.index('repos/${GITHUB_REPOSITORY}/git/ref/tags/${TAG}', push)
    finalize = workflow.index('"tag-admit-$KIND-finalize"')
    assert workflow.index("tag-admit-rc-intent") < create
    assert workflow.index("tag-admit-stable-intent") < create
    assert create < push < remote < finalize
    assert 'creator": "release-controller"' not in workflow
    assert 'git fetch --force' not in workflow
    assert "RELEASE_CONTROLLER_DEPLOY_KEY" not in workflow
    assert "RELEASE_CONTROLLER_APP_ID" in workflow
    assert "RELEASE_CONTROLLER_READBACK_URL" in workflow
    assert "actions/create-github-app-token@" in workflow
    assert '"name": "release-tag-creation"' in workflow
    assert '"external_id": sys.argv[2]' in workflow
    assert '"checkRunId=$CHECK_RUN_ID"' in workflow
    assert 'git/tags/${REMOTE_OBJECT_OID}' in workflow
    assert 'github.run_started_at' not in workflow
    assert 'if git show-ref --verify --quiet "refs/tags/$TAG"' in workflow
    assert workflow.count('git tag -a "$TAG"') == 1
