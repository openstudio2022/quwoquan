# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/gray-release-to-prod/spec.md#gwt-001.t1
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/gray-release-to-prod/spec.md#gwt-001.t2
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/gray-release-to-prod/spec.md#gwt-001.t3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from quwoquan_ops.ci.qualified_prod import (
    QualifiedProdError,
    append_prod_stage_attempt,
    create_post_release_soak_fact,
    create_prod_activation_admission,
    create_prod_rollback_fact,
    create_terminal_released_fact,
    digest,
    materialize_prod_activation_input,
    validate_post_release_soak_fact,
    validate_prod_released_fact,
    validate_prod_rollback_fact,
    validate_prod_stage_attempt_fact,
)
from quwoquan_ops.ci import release_evidence_reader as lifecycle
from quwoquan_ops.cli.prod import hosted_release_ledger
from quwoquan_ops.tests.support.rollout_stage_promotion_evidence_test_support import (
    promotion_evidence,
)

SOURCE_SHA = "a" * 40
CONTROL_SHA = "b" * 40
CURRENT_DIGESTS = ("sha256:" + "1" * 64, "sha256:" + "2" * 64)
PREVIOUS_DIGESTS = ("sha256:" + "8" * 64, "sha256:" + "9" * 64)
SERVICE_OCI_DIGEST = CURRENT_DIGESTS[0]
APP_OCI_DIGEST = CURRENT_DIGESTS[1]
SERVICE_MATERIAL_DIGEST = "sha256:" + "6" * 64
APP_MATERIAL_DIGEST = "sha256:" + "a" * 64
ROOT = Path(__file__).resolve().parents[4]
SCHEMA = ROOT / "quwoquan_ops/environments/evidence/prod_activation_admission_fact.schema.json"
LIFECYCLE_SCHEMAS = {
    "quwoquan_ops.prod_stage_attempt_fact.v1": ROOT / "quwoquan_ops/environments/evidence/prod_stage_attempt_fact.schema.json",
    "quwoquan_ops.prod_released_fact.v1": ROOT / "quwoquan_ops/environments/evidence/prod_released_fact.schema.json",
    "quwoquan_ops.prod_rollback_fact.v1": ROOT / "quwoquan_ops/environments/evidence/prod_rollback_fact.schema.json",
    "quwoquan_ops.prod_unactivated_safe_fact.v1": ROOT / "quwoquan_ops/environments/evidence/prod_unactivated_safe_fact.schema.json",
    "quwoquan_ops.post_release_soak_fact.v1": ROOT / "quwoquan_ops/environments/evidence/post_release_soak_fact.schema.json",
}


def write(root: Path, ref: str, payload: dict[str, Any]) -> dict[str, str]:
    path = root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return {"ref": ref, "digest": digest(path)}


def facts_by_ref(root: Path, exact: dict[str, str]) -> dict[str, Any]:
    return json.loads((root / exact["ref"]).read_text(encoding="utf-8"))


def facts(
    root: Path,
    *,
    stable_tag: str = "v1.2.3",
    artifact_refs: tuple[str, ...] | None = None,
    previous_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    locators = artifact_refs or (
        f"ghcr.io/quwoquan/service@{CURRENT_DIGESTS[0]}",
        f"ghcr.io/quwoquan/web@{CURRENT_DIGESTS[1]}",
    )
    artifacts = [
        {
            "platform": platform,
            "ociRef": locator,
            "digest": locator.rsplit("@", 1)[-1] if "@" in locator else CURRENT_DIGESTS[index],
        }
        for index, (platform, locator) in enumerate(
            zip(("service", "web"), locators, strict=True)
        )
    ]
    factory_outputs = {
        "service": {
            "ociRef": f"ghcr.io/quwoquan/service@{SERVICE_OCI_DIGEST}",
            "ociDigest": SERVICE_OCI_DIGEST,
            "payloadDigest": "sha256:" + "b" * 64,
            "materialDigest": SERVICE_MATERIAL_DIGEST,
            "serviceDigest": CURRENT_DIGESTS[0],
            "prodRuntimeConfigDeploymentBundle": {
                "schema": "quwoquan_ops.prod_runtime_config_deployment_bundle.v1",
                "algorithm": "sha256_sorted_tracked_path_bytes_v1",
                "files": [{"path": "prod/runtime.yaml", "digest": "sha256:" + "c" * 64}],
                "digest": "sha256:" + "d" * 64,
            },
        },
        "web": {
            "ociRef": f"ghcr.io/quwoquan/web@{APP_OCI_DIGEST}",
            "ociDigest": APP_OCI_DIGEST,
            "payloadDigest": "sha256:" + "e" * 64,
            "materialDigest": APP_MATERIAL_DIGEST,
            "artifactDigest": CURRENT_DIGESTS[1],
            "artifactManifest": {},
            "sourceTreeDigest": "sha1:" + "d" * 40,
        },
        "qualificationRequestOciRef": "ghcr.io/quwoquan/request@sha256:" + "1" * 64,
        "artifactBuildNumberAllocationOciRef": "ghcr.io/quwoquan/allocation@sha256:" + "2" * 64,
    }
    material_body = {
        "schema": "quwoquan_ops.candidate_material_manifest.v1",
        "deliveryTargets": ["service"],
        "sourceGitSha": SOURCE_SHA,
        "sourceTree": "d" * 40,
        "artifactBuildNumber": 17,
        "artifacts": artifacts,
        "factoryOutputs": factory_outputs,
    }
    material_body["materialId"] = digest(material_body)
    material = write(root, "immutable/material/v1.2.3-rc.1.json", material_body)
    qualification_body = {
        "schema": "quwoquan_ops.qualification_fact.v1",
        "deliveryTargets": ["service"],
        "decision": "qualified",
        "tagName": "v1.2.3-rc.1",
        "sourceGitSha": SOURCE_SHA,
        "sourceTree": material_body["sourceTree"],
        "artifactBuildNumber": material_body["artifactBuildNumber"],
        "candidateMaterialManifest": material,
        "artifacts": artifacts,
    }
    qualification_body["qualificationId"] = digest(qualification_body)
    qualification = write(
        root, "immutable/qualification/v1.2.3-rc.1.json", qualification_body
    )
    tag = write(
        root,
        "immutable/release-tags/v1.2.3.json",
        {
            "schema": "quwoquan_ops.release_tag_admission_fact.v1",
            "deliveryTargets": ["service"],
            "decision": "admitted",
            "tagKind": "stable",
            "tagName": stable_tag,
            "tagObjectOid": "c" * 40,
            "peeledCommit": SOURCE_SHA,
            "sourceTree": material_body["sourceTree"],
            "artifactBuildNumber": material_body["artifactBuildNumber"],
            "qualificationFact": qualification,
            "qualificationId": qualification_body["qualificationId"],
            "candidateMaterialManifest": material,
            "candidateMaterialId": material_body["materialId"],
            "candidateIdentity": "sha256:" + "3" * 64,
            "artifacts": artifacts,
        },
    )
    _, previous_hosted = hosted_stage_readback(
        root,
        stage="100",
        generation=0,
        candidate_id="sha256:" + "7" * 64,
        previous_candidate_id="sha256:" + "6" * 64,
        verified_at="2026-09-04T10:00:00Z",
    )
    previous_payload: dict[str, Any] = {
        "schema": "quwoquan_ops.prod_released_fact.v1",
        "terminal": "released",
        "active": True,
        "revoked": False,
        "digestsExist": True,
        "compatible": True,
        "candidateId": "sha256:" + "7" * 64,
        "admission": {"ref": "immutable/prod/previous-admission.json", "digest": "sha256:" + "4" * 64},
        "stableTag": "v1.1.0",
        "sourceGitSha": "1" * 40,
        "controlPlaneGitSha": "2" * 40,
        "ociDigests": list(PREVIOUS_DIGESTS),
        "finalAttempt": {"ref": "immutable/prod/previous-final-attempt.json", "digest": "sha256:" + "5" * 64},
        "hostedReceiptReadback": previous_hosted,
        "releasedAt": "2026-09-04T10:00:00Z",
    }
    previous_payload.update(previous_overrides or {})
    previous_payload["releaseId"] = digest(previous_payload)
    previous = write(root, "immutable/prod/previous-released.json", previous_payload)
    rollback = write(
        root,
        "immutable/prod/rollback-readiness.json",
        {
            "schema": "quwoquan_ops.rollback_readiness_fact.v1",
            "status": "ready",
            "previousActiveReleasedLedger": previous,
            "ociDigests": list(PREVIOUS_DIGESTS),
            "digestsExist": True,
            "compatible": True,
        },
    )
    prior = write(root, "immutable/prod/prior.json", {
        "state": "present", "target": "prod-hosted", "environment": "prod",
        "previousReleased": previous, "rollbackReadiness": rollback,
        "expectedGeneration": 1, "ociDigests": sorted(PREVIOUS_DIGESTS),
    })
    return {
        "prior": prior,
        "tag": tag,
        "qualification": qualification,
        "previous": previous,
        "rollback": rollback,
        "material": material,
    }


def admit(root: Path, source: dict[str, Any] | None = None) -> tuple[Path, dict[str, str]]:
    source = source or facts(root)
    path = create_prod_activation_admission(
        root=root,
        release_tag_admission_ref=source["tag"],
        prior_ref=source["prior"],
        control_plane_git_sha=CONTROL_SHA,
        admitted_at="2026-09-05T10:00:00Z",
    )
    return path, {"ref": path.relative_to(root).as_posix(), "digest": digest(path)}


# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-004
@pytest.mark.parametrize("targets", [None, [], ["app"], ["app", "service"]])
def test_prod_rejects_missing_unselected_or_drifted_delivery_scope(tmp_path: Path, targets) -> None:
    source = facts(tmp_path)
    tag = facts_by_ref(tmp_path, source["tag"])
    if targets is None:
        tag.pop("deliveryTargets")
    else:
        tag["deliveryTargets"] = targets
    source["tag"] = write(tmp_path, "changed-tag.json", tag)
    with pytest.raises(QualifiedProdError, match="deliveryTargets"):
        admit(tmp_path, source)


# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-005
def test_admission_requires_explicit_prior_not_legacy_fields(tmp_path: Path) -> None:
    path, _ = admit(tmp_path)
    payload = json.loads(path.read_bytes())
    assert "prior" in payload
    assert "previousActiveReleasedLedger" not in payload
    assert "previousOciDigests" not in payload
    assert "rollbackReadiness" not in payload


def test_present_producer_derives_actual_receipt_and_is_idempotent(tmp_path: Path) -> None:
    from quwoquan_ops.ci.qualified_prod import create_present_prior
    source = facts(tmp_path)
    kwargs = dict(root=tmp_path, previous_released_ref=source["previous"], rollback_readiness_ref=source["rollback"])
    path = create_present_prior(**kwargs)
    assert path == create_present_prior(**kwargs)
    prior = json.loads(path.read_bytes())
    assert prior == facts_by_ref(tmp_path, source["prior"])
    source["prior"] = {"ref": path.relative_to(tmp_path).as_posix(), "digest": digest(path)}
    admit(tmp_path, source)


def test_present_candidate_self_reference_rejected_before_admission(tmp_path: Path) -> None:
    source = facts(tmp_path)
    tag = facts_by_ref(tmp_path, source["tag"])
    tag["candidateIdentity"] = facts_by_ref(tmp_path, source["previous"])["candidateId"]
    source["tag"] = write(tmp_path, "self-tag.json", tag)
    with pytest.raises(QualifiedProdError, match="self-reference"):
        admit(tmp_path, source)


def test_initial_human_cli_runtime_error_is_typed_and_never_queries_provider(tmp_path: Path, capsys) -> None:
    from quwoquan_ops.ci import release_control
    from quwoquan_ops.cli.lib import hosted_authority
    binding = write(tmp_path, "binding.json", {"diagnostic": "runtime-configuration-failure"})
    with mock.patch.object(hosted_authority, "runtime_from_env", side_effect=RuntimeError("HOSTED_AUTHORITY_EXTERNAL_DEPENDENCY")), mock.patch.object(hosted_authority, "HostedAuthorityHttpClient") as client:
        result = release_control.main(["--store-root", str(tmp_path), "prod-initial-human-check",
                                       "--binding", binding["ref"] + "=" + binding["digest"], "--decision-id", "decision/1"])
    assert result == 1  # release_control统一异常出口；非准入诊断正常结果另为2。
    payload = json.loads(capsys.readouterr().out)
    assert payload["terminal"] == "GATE_BLOCK"
    assert payload["detail"] == "HOSTED_AUTHORITY_EXTERNAL_DEPENDENCY"
    client.assert_not_called()
    assert not (tmp_path / "prod").exists()


def test_controller_release_locks_do_not_fence_one_remote_target(tmp_path: Path) -> None:
    """证明现役锁的边界，不能作为target取证保护通过证据。"""
    from quwoquan_ops.cli import stackctl
    from quwoquan_ops.cli.commands.repair_runtime_recovery import _prod_release_lock
    from quwoquan_ops.cli.prod.hosted_release_ledger_lib.ledger_store import _ledger_lock
    first = tmp_path / "controller-a" / "release-state"
    second = tmp_path / "controller-b" / "release-state"
    remote = tmp_path / "remote" / "release-ledger"
    # 同调用端互斥成立，但另一调用端及远端ledger使用不同真实flock inode。
    with mock.patch.object(stackctl, "_release_state_dir", return_value=first):
        with _prod_release_lock():
            with pytest.raises(RuntimeError, match="release lock is held"):
                with _prod_release_lock():
                    pytest.fail("same controller unexpectedly bypassed lock")
            with mock.patch.object(stackctl, "_release_state_dir", return_value=second):
                with _prod_release_lock():
                    with _ledger_lock(remote):
                        assert (first / ".global-deploy.lock").stat().st_ino != (second / ".global-deploy.lock").stat().st_ino
                        assert (remote / ".ledger.lock").is_file()


def test_target_route_writers_have_no_hosted_ledger_fence_binding() -> None:
    """源码证据标识尚未接入的writer；未执行任何远端动作。"""
    import inspect
    from quwoquan_ops.cli.commands.deploy_domain import command_deploy
    source = inspect.getsource(command_deploy)
    assert source.index("_command_prod_prevalidate") < source.index("_prod_release_lock")
    assert source.index("_command_deploy_distribution") < source.index("_prod_release_lock")
    sync = (ROOT / "quwoquan_ops/cli/prod/sync_prod_plane_stack.sh").read_text()
    effect = sync.split('if [[ -n "$source_dir" ]]; then', 1)[1]
    assert 'tar -xf - -C' in effect
    assert 'release-ledger' not in effect and 'flock' not in effect


def test_initial_human_binding_rejects_missing_recovery_before_provider_query(tmp_path: Path) -> None:
    from quwoquan_ops.ci import qualified_prod
    provider = mock.Mock()
    with pytest.raises(QualifiedProdError, match="binding"):
        qualified_prod.verify_initial_human_binding(
            binding={}, provider=provider, verifier=mock.Mock(), receipt_ref="decision/1",
            now="2026-09-13T00:00:00Z",
        )
    provider.readback.assert_not_called()


def test_initial_human_exact_binding_uses_real_ed25519_and_never_consumes(tmp_path: Path) -> None:
    from quwoquan_ops.ci.qualified_prod import verify_initial_human_binding
    from quwoquan_ops.tests.local_contract.gate import test_hosted_authority_adapter__local_contract_test as authority
    exact = {"ref": "immutable/evidence.json", "digest": "sha256:" + "a" * 64}
    binding = {"target": "prod-hosted", "environment": "prod", "deliveryTargets": ["service"],
               "inventoryDigest": "sha256:" + "b" * 64, "attemptId": "sha256:" + "c" * 64,
               "candidateDigest": "sha256:" + "d" * 64, "observationDigest": "sha256:" + "e" * 64,
               "executionOwner": "owner-1", "executionGeneration": 3, "releaseGeneration": 0,
               "recoveryEffects": ["disable_attempt_units", "stop_attempt_traffic"],
               "actions": ["observe_initial_prod"], **{field: dict(exact) for field in
               ("stableAdmission", "candidateMaterialManifest", "serviceMaterial", "webMaterial", "absenceProof", "recoveryResources")}}
    temporary, private, public = authority.keypair()
    try:
        overrides = {"role": "release_owner", "decisionKind": "production_campaign_approval",
                     "scope": {"increment": binding["attemptId"]}, "evidenceFingerprint": digest(binding),
                     "actions": binding["actions"]}
        for failure in (None, "revoked", "consumed", "expired", "role", "scope", "signature", "material", "recovery"):
            claims = dict(overrides)
            state = failure if failure in {"revoked", "consumed"} else "available"
            if failure == "expired": claims["expiresAt"] = "2020-01-01T00:00:00Z"
            if failure == "role": claims["role"] = "product_owner"
            if failure == "scope": claims["scope"] = {"increment": "wrong"}
            raw, headers = authority.wrapper_fixture(private, release_eligible=False, test_key=True,
                state=state, generation=2 if state != "available" else 1,
                winner_key="winner" if state != "available" else "",
                winner_digest=digest(binding) if state != "available" else "", claim_overrides=claims)
            if failure == "signature":
                import base64
                wrapper = json.loads(raw)
                wrapper["signature"] = base64.b64encode(b"x" * 64).decode().rstrip("=")
                raw = authority.exact(wrapper)
            calls = []
            def opener(request, **kwargs):
                calls.append(request.get_method())
                return authority.Response(raw, headers)
            client = authority.wire_config(opener=opener)
            provider = authority.HostedAuthorityProvider(client)
            verifier = authority.HostedAuthorityVerifier(provider, {authority.KEY_ID: public})
            tested = dict(binding)
            if failure == "material": tested["serviceMaterial"] = {**exact, "digest": "sha256:" + "d" * 64}
            if failure == "recovery": tested.pop("recoveryResources")
            if failure:
                with pytest.raises(QualifiedProdError):
                    verify_initial_human_binding(binding=tested, provider=provider, verifier=verifier,
                        receipt_ref=authority.DECISION_ID, now="2026-09-13T00:00:00Z")
            else:
                result = verify_initial_human_binding(binding=tested, provider=provider, verifier=verifier,
                    receipt_ref=authority.DECISION_ID, now="2026-09-13T00:00:00Z")
                assert result["humanBindingVerified"] is True
                assert result["releaseEvidenceEligible"] is False  # 隔离testKey不可冒充hosted。
                assert result["consumed"] is False and result["admissionEligible"] is False
            assert calls == ([] if failure == "recovery" else ["GET"])
    finally:
        temporary.cleanup()


def absent_prior(root: Path, *, candidate: str = "sha256:" + "3" * 64, generation: int = 0) -> dict[str, str]:
    owner, execution_generation = "owner-1", 7
    common = {"status": "complete", "target": "prod-hosted", "environment": "prod",
              "executionOwner": owner, "executionGeneration": execution_generation,
              "releaseGeneration": generation, "guardsContinuous": True}
    payloads = {
        "inventoryObservation": {**common, "completeInventory": True},
        "ledgerHistoryObservation": {**common, "activeReleased": False, "unexplainedHistory": False},
        "routeObservation": {**common, "candidateRouted": False},
        "unitObservation": {**common, "candidateUnitsActive": False},
        "autoRestartObservation": {**common, "candidateAutoRestartEnabled": False},
        "inflightObservation": {**common, "inflightActivation": False},
    }
    refs = {field: write(root, f"immutable/absence/{field}.json", payload) for field, payload in payloads.items()}
    observation_digest = digest({field: refs[field] for field in sorted(refs)})
    attempt = "sha256:" + "c" * 64
    human_binding_digest = "sha256:" + "d" * 64
    human = write(root, "immutable/absence/human.json", {"bindingDigest": human_binding_digest,
        "consumed": True, "winnerAttemptId": attempt, "observationDigest": observation_digest,
        "candidateDigest": candidate, "target": "prod-hosted", "executionOwner": owner,
        "executionGeneration": execution_generation, "releaseGeneration": generation})
    recovery = write(root, "immutable/absence/recovery.json", {"status": "ready", "preservePersistentResources": True})
    prior = {"state": "absent", "target": "prod-hosted", "environment": "prod",
             "expectedGeneration": generation, "executionOwner": owner,
             "executionGeneration": execution_generation, "attemptId": attempt,
             "observationDigest": observation_digest, "humanAuthority": human,
             "humanBindingDigest": human_binding_digest, "recoveryResources": recovery, **refs}
    return write(root, f"immutable/prod/absent-{generation}.json", prior)


def test_absent_prior_requires_complete_guarded_observation_and_human_authority(tmp_path: Path) -> None:
    from quwoquan_ops.ci.qualified_prod import validate_absent_prior
    prior_ref = absent_prior(tmp_path)
    prior = facts_by_ref(tmp_path, prior_ref)
    assert validate_absent_prior(tmp_path, prior, candidate="sha256:" + "3" * 64)["state"] == "absent"
    source = facts(tmp_path)
    prior = facts_by_ref(tmp_path, prior_ref); authority = facts_by_ref(tmp_path, prior["humanAuthority"])
    authority.update({"stableAdmission": source["tag"], "candidateMaterialManifest": source["material"],
                      "serviceMaterial": {"ref":"immutable/evidence.json","digest":"sha256:"+"a"*64},
                      "webMaterial": {"ref":"immutable/evidence.json","digest":"sha256:"+"a"*64},
                      "recoveryResources": prior["recoveryResources"], "recoveryEffects":["stop_attempt_traffic"]})
    prior["humanAuthority"] = write(tmp_path, "immutable/absence/human-bound.json", authority)
    source["prior"] = write(tmp_path, "immutable/prod/absent-bound.json", prior)
    path, _ = admit(tmp_path, source)
    assert facts_by_ref(tmp_path, {"ref": path.relative_to(tmp_path).as_posix(), "digest": digest(path)})["prior"]["state"] == "absent"
    for field, key, value in (("inventoryObservation", "completeInventory", False),
                              ("ledgerHistoryObservation", "status", "unknown"),
                              ("routeObservation", "guardsContinuous", False)):
        changed = facts_by_ref(tmp_path, prior[field]); changed[key] = value
        bad = dict(prior); bad[field] = write(tmp_path, f"bad-{field}.json", changed)
        with pytest.raises(QualifiedProdError, match="UNKNOWN"):
            validate_absent_prior(tmp_path, bad, candidate="sha256:" + "3" * 64)


def test_state_file_absence_or_query_failure_never_proves_absent(tmp_path: Path) -> None:
    from quwoquan_ops.ci.qualified_prod import validate_absent_prior
    prior = facts_by_ref(tmp_path, absent_prior(tmp_path))
    for payload in ({}, {"status": "unknown", "reason": "permission_denied"},
                    {"status": "complete", "completeInventory": False}):
        prior["inventoryObservation"] = write(tmp_path, "bad-inventory.json", payload)
        with pytest.raises(QualifiedProdError):
            validate_absent_prior(tmp_path, prior, candidate="sha256:" + "3" * 64)


@pytest.mark.parametrize("field,value", [("state", "unknown"), ("target", "gamma-local"),
    ("environment", "gamma"), ("expectedGeneration", 0), ("expectedGeneration", 2),
    ("ociDigests", ["sha256:" + "a" * 64])])
def test_present_prior_wrong_target_generation_or_digest_rejected(tmp_path: Path, field, value) -> None:
    source = facts(tmp_path)
    prior = facts_by_ref(tmp_path, source["prior"])
    prior[field] = value
    source["prior"] = write(tmp_path, "bad-prior.json", prior)
    with pytest.raises(QualifiedProdError, match="PROD.PRIOR.INVALID"):
        admit(tmp_path, source)


def test_legacy_admission_fields_are_rejected_even_with_explicit_prior(tmp_path: Path) -> None:
    from quwoquan_ops.ci.qualified_prod import admission_prior
    path, _ = admit(tmp_path)
    admission = json.loads(path.read_bytes())
    for field in ("previousActiveReleasedLedger", "rollbackReadiness", "previousOciDigests"):
        changed = dict(admission); changed[field] = {}
        with pytest.raises(QualifiedProdError, match="retired implicit"):
            admission_prior(changed)
    admission.pop("prior")
    with pytest.raises(QualifiedProdError, match="PROD.PRIOR.INVALID"):
        admission_prior(admission)


def candidate_material_promotion_evidence(
    *, candidate_id: str, candidate_material_id: str, stage: str
) -> dict[str, Any]:
    value = promotion_evidence(
        candidate_id=candidate_id,
        artifact_digest=candidate_material_id,
        stage=stage,
    )
    value["candidateMaterialId"] = value.pop("artifactDigest")
    unsigned = dict(value)
    unsigned.pop("evidenceDigest")
    value["evidenceDigest"] = hosted_release_ledger._canonical_bytes(unsigned)
    value["evidenceDigest"] = "sha256:" + __import__("hashlib").sha256(value["evidenceDigest"]).hexdigest()
    return value


def hosted_stage_readback(
    root: Path,
    *,
    stage: str,
    generation: int,
    decision: str = "continue",
    verified_at: str | None = None,
    candidate_id: str = "sha256:" + "3" * 64,
    previous_candidate_id: str = "sha256:" + "7" * 64,
) -> tuple[dict[str, Any], dict[str, str]]:
    rolled_back = decision == "rolled_back"
    failed = decision in {"rolled_back", "rollback_failed", "pause"}
    from_candidate = candidate_id if rolled_back else previous_candidate_id
    to_candidate = previous_candidate_id if rolled_back else candidate_id
    candidate_material_id = "sha256:" + "5" * 64
    receipt = {
        "schema": lifecycle.HOSTED_RECEIPT_SCHEMA,
        "authority": lifecycle.HOSTED_AUTHORITY,
        "service": "prod-stack",
        "fromCandidateDigest": from_candidate,
        "toCandidateDigest": to_candidate,
        "step": "100" if rolled_back else ("0" if stage == "canary" else stage),
        "stage": "100" if rolled_back else stage,
        "triggerStage": stage,
        "fromServiceFactoryOciDigest": from_candidate,
        "toServiceFactoryOciDigest": to_candidate,
        "fromAppFactoryOciDigest": "sha256:" + "8" * 64,
        "toAppFactoryOciDigest": "sha256:" + "9" * 64,
        "decision": decision,
        "rollbackOutcome": decision if decision in {"rolled_back", "rollback_failed"} else "not_triggered",
        "rollbackEvidence": (
            {
                "triggered": True,
                "startedAt": "2026-09-05T10:00:00Z",
                "endedAt": "2026-09-05T10:00:01Z",
                "durationMs": 1000,
                "postChecks": [{"name": "rollback-health", "status": "passed" if rolled_back else "failed", "receiptDigest": "sha256:" + "6" * 64}],
            }
            if decision in {"rolled_back", "rollback_failed"}
            else {"triggered": False}
        ),
        "candidateMaterialId": candidate_material_id,
        "prodActivationAdmissionRef": "ghcr.io/quwoquan/prod-admission@sha256:" + "0" * 64,
        "prodActivationAdmissionOciDigest": "sha256:" + "0" * 64,
        "prodActivationAdmissionPayloadDigest": "sha256:" + "0" * 64,
        "prodActivationAdmissionId": "sha256:" + "1" * 64,
        "candidateMaterialManifestRef": "ghcr.io/quwoquan/candidate-material@sha256:" + "4" * 64,
        "candidateMaterialManifestOciDigest": "sha256:" + "4" * 64,
        "candidateMaterialManifestPayloadDigest": "sha256:" + "4" * 64,
        "previousReleasedRef": "ghcr.io/quwoquan/released-prod@sha256:" + "6" * 64,
        "previousReleasedOciDigest": "sha256:" + "6" * 64,
        "previousReleasedPayloadDigest": "sha256:" + "6" * 64,
        "previousReleasedId": "sha256:" + "7" * 64,
        "imageDigest": "sha256:" + "c" * 64,
        "configDigest": "sha256:" + "d" * 64,
        "contractGraphDigest": "sha256:" + "e" * 64,
        "adapterDigest": "sha256:" + "f" * 64,
        "expectedGeneration": generation,
        "committedGeneration": generation + 1,
        "sloReadback": (
            {"sampleCount": 100, "promotionEvidence": candidate_material_promotion_evidence(candidate_id=candidate_id, candidate_material_id=candidate_material_id, stage=stage)}
            if decision == "continue"
            else {"sampleCount": 100}
        ),
        "postChecks": [{"name": "health", "status": "failed" if failed else "passed", "receiptDigest": "sha256:" + "4" * 64}],
        "lastGoodCandidateDigest": previous_candidate_id if failed else candidate_id,
        "verifiedAt": verified_at or f"2026-09-05T10:{generation + 1:02d}:00Z",
    }
    receipt["receiptId"] = lifecycle._receipt_id(receipt)
    payload = {
        "schema": lifecycle.HOSTED_RECEIPT_READBACK_SCHEMA,
        "authority": lifecycle.HOSTED_AUTHORITY,
        "receipt": receipt,
        "receiptRef": f"receipt:hosted:{receipt['receiptId']}",
    }
    exact = write(root, f"immutable/hosted/{receipt['receiptId']}.json", payload)
    return payload, exact


def stage_evidence(
    root: Path,
    admission: dict[str, str],
    stage: str,
    status: str,
    hosted: dict[str, Any],
    *,
    attempt: int = 1,
) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for index, kind in enumerate(("activation", "health", "slo", "placement", "readback")):
        evidence_status = status if kind == "readback" else (
            "failed" if status == "failed" and index == 0 else "passed"
        )
        result[kind] = write(
            root,
            f"immutable/stage-evidence/{stage}-{attempt}-{kind}.json",
            {
                "schema": f"quwoquan_ops.prod_{kind}_evidence.v1",
                "admission": admission,
                "stage": stage,
                "status": evidence_status,
                "source": hosted if kind == "readback" else {"kind": kind},
            },
        )
    return result


def append_stage(
    root: Path,
    admission: dict[str, str],
    stage: str,
    predecessor: dict[str, str] | None,
    *,
    status: str = "passed",
    attempt: int = 1,
    decision: str | None = None,
) -> tuple[Path, dict[str, str]]:
    if predecessor is not None:
        previous = facts_by_ref(root, predecessor)
    else:
        admission_fact = facts_by_ref(root, admission)
        previous = facts_by_ref(root, admission_fact["prior"]["previousReleased"])
    previous_readback = facts_by_ref(root, previous["hostedReceiptReadback"])
    generation = previous_readback["receipt"]["committedGeneration"]
    resolved_decision = decision or ("continue" if status == "passed" else "pause")
    hosted, hosted_exact = hosted_stage_readback(
        root, stage=stage, generation=generation, decision=resolved_decision
    )
    path = append_prod_stage_attempt(
        root=root,
        admission_ref=admission,
        stage=stage,
        status=status,
        evidence_refs=stage_evidence(root, admission, stage, status, hosted, attempt=attempt),
        hosted_receipt_readback_ref=hosted_exact,
        predecessor_ref=predecessor,
        recorded_at=hosted["receipt"]["verifiedAt"],
    )
    return path, {"ref": path.relative_to(root).as_posix(), "digest": digest(path)}


def released(root: Path, admission: dict[str, str]) -> tuple[Path, dict[str, str]]:
    predecessor = None
    final_hosted = None
    for stage in ("canary", "5", "20", "50", "100"):
        path, predecessor = append_stage(root, admission, stage, predecessor)
        final_hosted = facts_by_ref(root, predecessor)["hostedReceiptReadback"]
    assert predecessor is not None and final_hosted is not None
    final_receipt = facts_by_ref(root, final_hosted)["receipt"]
    path = create_terminal_released_fact(
        root=root,
        admission_ref=admission,
        final_attempt_ref=predecessor,
        hosted_receipt_readback_ref=final_hosted,
        released_at=final_receipt["verifiedAt"],
    )
    return path, {"ref": path.relative_to(root).as_posix(), "digest": digest(path)}


def test_admission_accepts_only_stable_exact_facts_and_parses_digest_set(tmp_path: Path) -> None:
    path, _ = admit(tmp_path)
    fact = json.loads(path.read_text(encoding="utf-8"))

    Draft202012Validator.check_schema(json.loads(SCHEMA.read_text(encoding="utf-8")))
    Draft202012Validator(
        json.loads(SCHEMA.read_text(encoding="utf-8")), format_checker=FormatChecker()
    ).validate(fact)
    assert fact["stableTag"] == "v1.2.3"
    assert fact["qualification"] == facts_by_ref(tmp_path, fact["releaseTagAdmission"])["qualificationFact"]
    assert fact["candidateMaterialManifest"] == facts_by_ref(tmp_path, fact["releaseTagAdmission"])["candidateMaterialManifest"]
    assert fact["ociDigests"] == sorted(set(CURRENT_DIGESTS) | {SERVICE_MATERIAL_DIGEST, APP_MATERIAL_DIGEST})
    assert fact["createdBeforeStage"] == "canary"
    assert not any("rollout" in key.casefold() or "eaf" in key.casefold() for key in fact)
    assert fact["qualification"]["ref"].endswith("v1.2.3-rc.1.json")
    activation_input = tmp_path / "activation-input.json"
    service_material = write(tmp_path, "immutable/factory/service/manifest.json", {"schema": "quwoquan_ops.service_factory_material", "materialDigest": SERVICE_MATERIAL_DIGEST})
    app_material = write(tmp_path, "immutable/factory/app/manifest.json", {"schema": "quwoquan_ops.app_factory_material", "materialDigest": APP_MATERIAL_DIGEST})
    validated_service = {**facts_by_ref(tmp_path, fact["candidateMaterialManifest"])["factoryOutputs"]["service"]}
    validated_app = {**facts_by_ref(tmp_path, fact["candidateMaterialManifest"])["factoryOutputs"]["web"]}
    with mock.patch(
        "quwoquan_ops.ci.qualified_prod._validated_factory_actual_materials",
        return_value=(
            {"service": (facts_by_ref(tmp_path, service_material), service_material),
             "web": (facts_by_ref(tmp_path, app_material), app_material)},
            {"service": validated_service, "web": validated_app},
        ),
    ):
        materialize_prod_activation_input(
            root=tmp_path,
            admission_ref={"ref": path.relative_to(tmp_path).as_posix(), "digest": digest(path)},
            service_material_ref=service_material,
            web_material_ref=app_material,
            app_material_ref=None,
            output=activation_input,
        )
    payload = json.loads(activation_input.read_text(encoding="utf-8"))
    assert payload["serviceFactoryMaterial"] == {**{key: validated_service[key] for key in ("ociRef", "ociDigest", "payloadDigest", "materialDigest")}, "materializedManifest": service_material}
    assert payload["webFactoryMaterial"] == {**{key: validated_app[key] for key in ("ociRef", "ociDigest", "payloadDigest", "materialDigest")}, "materializedManifest": app_material}
    assert "appFactoryMaterial" not in payload and "appMaterialDigest" not in payload
    assert payload["candidateDigest"] == "sha256:" + "3" * 64
    assert payload["previousCandidateDigest"] == "sha256:" + "7" * 64
    assert "releaseEvidenceRef" not in payload


@pytest.mark.parametrize(
    "selector",
    ("refs/heads/main", SOURCE_SHA, "selectors/latestQualified.json", "${{ vars.RELEASE_TAG }}"),
)
def test_admission_rejects_main_bare_sha_and_mutable_selectors(
    tmp_path: Path, selector: str
) -> None:
    source = facts(tmp_path)
    source["tag"] = {"ref": selector, "digest": "sha256:" + "0" * 64}
    with pytest.raises(QualifiedProdError):
        admit(tmp_path, source)


def test_admission_rejects_rc_and_mutable_oci_refs(tmp_path: Path) -> None:
    with pytest.raises(QualifiedProdError, match="stable SemVer"):
        admit(tmp_path / "rc", facts(tmp_path / "rc", stable_tag="v1.2.3-rc.1"))
    with pytest.raises(QualifiedProdError, match="exact OCI"):
        admit(
            tmp_path / "latest",
            facts(
                tmp_path / "latest",
                artifact_refs=(
                    "ghcr.io/quwoquan/service:latest",
                    f"ghcr.io/quwoquan/web@{CURRENT_DIGESTS[1]}",
                ),
            ),
        )


@pytest.mark.parametrize("drifted", ("tag", "qualification"))
def test_tag_or_qualification_byte_drift_blocks_before_canary(
    tmp_path: Path, drifted: str
) -> None:
    source = facts(tmp_path)
    _, admission = admit(tmp_path, source)
    path = tmp_path / source[drifted]["ref"]
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["drift"] = True
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")

    with pytest.raises(QualifiedProdError, match="drifted"):
        append_stage(tmp_path, admission, "canary", None)


def test_stage_order_is_strict_and_success_creates_released_terminal(tmp_path: Path) -> None:
    _, admission = admit(tmp_path)
    _, canary = append_stage(tmp_path, admission, "canary", None)
    with pytest.raises(QualifiedProdError, match="stage order"):
        append_stage(tmp_path, admission, "20", canary)

    predecessor = canary
    for stage in ("5", "20", "50", "100"):
        _, predecessor = append_stage(tmp_path, admission, stage, predecessor)
    final = facts_by_ref(tmp_path, predecessor)
    terminal = create_terminal_released_fact(
        root=tmp_path,
        admission_ref=admission,
        final_attempt_ref=predecessor,
        hosted_receipt_readback_ref=final["hostedReceiptReadback"],
        released_at=facts_by_ref(tmp_path, final["hostedReceiptReadback"])["receipt"]["verifiedAt"],
    )
    assert validate_prod_released_fact(json.loads(terminal.read_text()))["terminal"] == "released"


def test_stage_rejects_local_synthetic_readback_without_hosted_envelope(tmp_path: Path) -> None:
    _, admission = admit(tmp_path)
    synthetic = write(tmp_path, "immutable/local/readback.json", {"receiptId": "0" * 64})
    with pytest.raises(QualifiedProdError, match="canonical hosted receipt readback"):
        append_prod_stage_attempt(
            root=tmp_path,
            admission_ref=admission,
            stage="canary",
            status="passed",
            evidence_refs={},
            hosted_receipt_readback_ref=synthetic,
            predecessor_ref=None,
            recorded_at="2026-09-05T10:01:00Z",
        )


def test_forged_lifecycle_self_id_is_rejected(tmp_path: Path) -> None:
    _, admission = admit(tmp_path)
    path, exact = append_stage(tmp_path, admission, "canary", None)
    fact = facts_by_ref(tmp_path, exact)
    validate_prod_stage_attempt_fact(fact)
    fact["status"] = "failed"
    with pytest.raises(QualifiedProdError, match="self-ID"):
        validate_prod_stage_attempt_fact(fact)
    assert path.name == f"{facts_by_ref(tmp_path, exact)['attemptId']}.json"


# 失败尝试保留，retry 只能追加同阶段下一 attempt。
def test_failed_stage_retry_is_append_only(tmp_path: Path) -> None:
    _, admission = admit(tmp_path)
    failed_path, failed = append_stage(
        tmp_path, admission, "canary", None, status="failed", attempt=1
    )
    failed_bytes = failed_path.read_bytes()
    retry_path, retry = append_stage(
        tmp_path, admission, "canary", failed, status="passed", attempt=2
    )
    retry_fact = json.loads(retry_path.read_text())
    assert retry_fact["attemptNumber"] == 2
    assert retry_fact["predecessor"] == failed
    assert failed_path.read_bytes() == failed_bytes
    assert retry != failed


def rollback_evidence(
    root: Path,
    admission: dict[str, str],
    previous: dict[str, str],
    stage: str,
    hosted: dict[str, Any],
    *,
    digests: tuple[str, ...] = PREVIOUS_DIGESTS,
) -> dict[str, dict[str, str]]:
    return {
        kind: write(
            root,
            f"immutable/rollback/{stage}-{kind}.json",
            {
                "schema": f"quwoquan_ops.prod_rollback_{kind}_evidence.v1",
                "admission": admission,
                "stage": stage,
                "status": "passed",
                "rollbackTarget": previous,
                "ociDigests": list(digests),
                "source": hosted if kind == "readback" else {"kind": kind},
            },
        )
        for kind in ("activation", "health", "readback")
    }


def test_rollback_uses_only_previous_released_exact_digests(tmp_path: Path) -> None:
    source = facts(tmp_path)
    _, admission = admit(tmp_path, source)
    failed_path, failed = append_stage(tmp_path, admission, "canary", None, status="failed", decision="rolled_back")
    failed_fact = json.loads(failed_path.read_text())
    hosted_exact = failed_fact["hostedReceiptReadback"]
    hosted = facts_by_ref(tmp_path, hosted_exact)
    rollback = create_prod_rollback_fact(
        root=tmp_path,
        admission_ref=admission,
        failed_attempt_ref=failed,
        evidence_refs=rollback_evidence(tmp_path, admission, source["previous"], "canary", hosted),
        hosted_receipt_readback_ref=hosted_exact,
        rolled_back_at=hosted["receipt"]["verifiedAt"],
    )
    fact = validate_prod_rollback_fact(json.loads(rollback.read_text()))
    assert fact["terminal"] == "rolled_back"
    assert fact["ociDigests"] == sorted(PREVIOUS_DIGESTS)
    assert fact["builderInvocationCount"] == 0
    assert fact["tagMutation"] is False


@pytest.mark.parametrize(
    "overrides",
    ({"revoked": True}, {"digestsExist": False}, {"compatible": False}),
)
def test_revoked_missing_or_incompatible_previous_release_is_illegal(
    tmp_path: Path, overrides: dict[str, Any]
) -> None:
    with pytest.raises(QualifiedProdError):
        admit(tmp_path, facts(tmp_path, previous_overrides=overrides))


def test_rollback_rejects_any_digest_other_than_ledger_identity(tmp_path: Path) -> None:
    source = facts(tmp_path)
    _, admission = admit(tmp_path, source)
    failed_path, failed = append_stage(tmp_path, admission, "canary", None, status="failed", decision="rolled_back")
    failed_fact = json.loads(failed_path.read_text())
    hosted_exact = failed_fact["hostedReceiptReadback"]
    hosted = facts_by_ref(tmp_path, hosted_exact)
    with pytest.raises(QualifiedProdError, match="rollback evidence"):
        create_prod_rollback_fact(
            root=tmp_path,
            admission_ref=admission,
            failed_attempt_ref=failed,
            evidence_refs=rollback_evidence(
                tmp_path, admission, source["previous"], "canary", hosted,
                digests=("sha256:" + "7" * 64,),
            ),
            hosted_receipt_readback_ref=hosted_exact,
            rolled_back_at=hosted["receipt"]["verifiedAt"],
        )


def hosted_soak_readback(
    root: Path,
    released_ref: dict[str, str],
    *,
    error_rate: float = 0.001,
    sample_count: int = 200,
) -> tuple[dict[str, Any], dict[str, str], dict[str, dict[str, str]]]:
    released_fact = facts_by_ref(root, released_ref)
    full_readback = facts_by_ref(root, released_fact["hostedReceiptReadback"])
    full = full_readback["receipt"]
    started = "2026-09-05T10:05:00Z"
    ended = "2026-09-06T10:05:00Z"
    observations: dict[str, dict[str, str]] = {}
    source_payloads: dict[str, dict[str, Any]] = {
        "slo": {
            "source": "prometheus", "queriedAt": ended, "window": "24h", "minimumSamples": 100,
            "values": {"errorRate": error_rate, "p95Ms": 100.0, "redisErrorRate": 0.001, "sampleCount": sample_count},
        },
        "alerts": {"schema": "prod-alertmanager-soak-observation", "source": "alertmanager", "queriedAt": ended, "status": "passed", "activeFiring": 0},
        "health": {"command": "health", "target": "prod-hosted", "scope": "full", "readOnly": False, "findings": [], "checks": [{"name": "service", "ok": True}], "timestamp": ended},
    }
    hosted_evidence = {
        "slo": {"source": "prometheus", "observedAt": ended, "windowSeconds": 86400, "minimumSamples": 100, "sampleCount": sample_count, "status": "passed", "decision": "continue", "values": {"errorRate": error_rate, "p95Ms": 100.0, "redisErrorRate": 0.001}, "receiptDigest": "sha256:" + "a" * 64},
        "alerts": {"source": "alertmanager", "observedAt": ended, "status": "passed", "activeFiring": 0, "receiptDigest": "sha256:" + "b" * 64},
        "health": {"source": "stackctl", "observedAt": ended, "target": "prod-hosted", "scope": "full", "status": "passed", "receiptDigest": "sha256:" + "c" * 64},
    }
    for kind in ("health", "slo", "alerts"):
        observations[kind] = write(root, f"immutable/soak/{kind}.json", {
            "schema": f"quwoquan_ops.prod_soak_{kind}_observation.v1", "release": released_ref,
            "status": "passed", "readOnly": True, "observedAt": ended,
            "sourceDigest": hosted_evidence[kind]["receiptDigest"], "source": source_payloads[kind],
        })
    receipt = {
        "schema": lifecycle.HOSTED_SOAK_RECEIPT_SCHEMA,
        "authority": lifecycle.HOSTED_AUTHORITY,
        "service": "prod-stack",
        "environment": "prod", "target": "prod-hosted", "fullRolloutReceiptId": full["receiptId"],
        "candidateId": released_fact["candidateId"], "candidateMaterialId": full["candidateMaterialId"],
        "prodActivationAdmissionRef": full["prodActivationAdmissionRef"],
        "prodActivationAdmissionOciDigest": full["prodActivationAdmissionOciDigest"],
        "prodActivationAdmissionPayloadDigest": full["prodActivationAdmissionPayloadDigest"],
        "prodActivationAdmissionId": full["prodActivationAdmissionId"],
        "candidateMaterialManifestRef": full["candidateMaterialManifestRef"],
        "candidateMaterialManifestOciDigest": full["candidateMaterialManifestOciDigest"],
        "candidateMaterialManifestPayloadDigest": full["candidateMaterialManifestPayloadDigest"],
        "serviceFactoryOciDigest": full["toServiceFactoryOciDigest"],
        "appFactoryOciDigest": full["toAppFactoryOciDigest"],
        "releasedRef": "ghcr.io/owner/quwoquan/released-prod@" + released_ref["digest"],
        "releasedOciDigest": released_ref["digest"],
        "releasedPayloadDigest": released_ref["digest"],
        "releasedId": released_fact["releaseId"], "sourceGitSha": SOURCE_SHA,
        "sourceTreeDigest": "sha1:" + "2" * 40, "rolloutConfigDigest": full["configDigest"],
        "configGraphDigest": "sha256:" + "3" * 64, "contractGraphDigest": full["contractGraphDigest"],
        "requiredSoakSeconds": 86400, "soakPolicyDigest": digest(ROOT / "quwoquan_ops/policies/config-release/slo_thresholds.yaml"),
        "credentialPolicyDigest": "sha256:" + "4" * 64, **hosted_evidence,
        "credentials": [{"plane": "service", "account": "svc", "reference": "github-secret://PROD_SERVICE_SSH_KEY", "publicDigest": "sha256:" + "5" * 64, "issuer": "github-actions-production-environment", "expiresAt": "2026-10-06T10:05:00Z", "verifiedAt": ended}],
        "approval": {"kind": "github-production-environment", "repository": "owner/quwoquan", "sourceGitSha": SOURCE_SHA, "candidateMaterialId": full["candidateMaterialId"], "prodActivationAdmissionId": full["prodActivationAdmissionId"], "environment": "production", "workflowRunId": "42", "workflowRunAttempt": "1", "actor": "deployer", "receiptDigest": "sha256:" + "6" * 64, "verifiedAt": ended},
        "soakStartedAt": started, "soakEndedAt": ended, "soakDurationSeconds": 86400, "verifiedAt": ended,
    }
    receipt["receiptId"] = lifecycle._receipt_id(receipt)
    payload = {"schema": lifecycle.HOSTED_SOAK_READBACK_SCHEMA, "authority": lifecycle.HOSTED_AUTHORITY, "receipt": receipt, "receiptRef": f"receipt:hosted-soak:{receipt['receiptId']}"}
    exact = write(root, f"immutable/hosted-soak/{receipt['receiptId']}.json", payload)
    return payload, exact, observations


def test_post_release_soak_is_hosted_authoritative_and_read_only(tmp_path: Path) -> None:
    source = facts(tmp_path)
    tag_before = (tmp_path / source["tag"]["ref"]).read_bytes()
    qualification_before = (tmp_path / source["qualification"]["ref"]).read_bytes()
    _, admission = admit(tmp_path, source)
    released_path, released_ref = released(tmp_path, admission)
    terminal_before = released_path.read_bytes()
    hosted, hosted_exact, observations = hosted_soak_readback(tmp_path, released_ref)
    soak = create_post_release_soak_fact(
        root=tmp_path,
        released_fact_ref=released_ref,
        observation_refs=observations,
        hosted_soak_readback_ref=hosted_exact,
        status="passed",
        observed_at=hosted["receipt"]["verifiedAt"],
    )
    fact = validate_post_release_soak_fact(json.loads(soak.read_text()))
    assert fact["readOnly"] is True
    assert fact["releasedFact"] == released_ref
    assert fact["hostedSoakReadback"] == hosted_exact
    assert fact["aggregate"]["successRatio"] == 1.0
    assert fact["aggregate"]["failureRatio"] == 0.0
    assert fact["aggregate"]["requestSuccessRatio"] == pytest.approx(0.999)
    assert fact["aggregate"]["requestFailureRatio"] == pytest.approx(0.001)
    assert fact["aggregate"]["window"]["complete"] is True
    assert released_path.read_bytes() == terminal_before
    assert (tmp_path / source["tag"]["ref"]).read_bytes() == tag_before
    assert (tmp_path / source["qualification"]["ref"]).read_bytes() == qualification_before


def test_soak_threshold_and_incomplete_aggregate_fail_closed(tmp_path: Path) -> None:
    _, admission = admit(tmp_path)
    _, released_ref = released(tmp_path, admission)
    hosted, hosted_exact, observations = hosted_soak_readback(tmp_path, released_ref, error_rate=0.02)
    with pytest.raises(QualifiedProdError, match="threshold"):
        create_post_release_soak_fact(
            root=tmp_path, released_fact_ref=released_ref, observation_refs=observations,
            hosted_soak_readback_ref=hosted_exact, status="passed", observed_at=hosted["receipt"]["verifiedAt"],
        )
    observations.pop("alerts")
    with pytest.raises(QualifiedProdError, match="incomplete"):
        create_post_release_soak_fact(
            root=tmp_path, released_fact_ref=released_ref, observation_refs=observations,
            hosted_soak_readback_ref=hosted_exact, status="passed", observed_at=hosted["receipt"]["verifiedAt"],
        )


def test_all_lifecycle_schemas_are_strict_and_canonical() -> None:
    for path in LIFECYCLE_SCHEMAS.values():
        schema = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        assert schema["additionalProperties"] is False

# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-005
def test_absent_and_present_prior_are_mutually_exclusive_schema_forms(tmp_path: Path) -> None:
    schema = json.loads(SCHEMA.read_bytes())
    validator = Draft202012Validator({"$ref": "#/$defs/prior", "$defs": schema["$defs"]})
    absent = facts_by_ref(tmp_path, absent_prior(tmp_path))
    present = facts_by_ref(tmp_path, facts(tmp_path)["prior"])
    validator.validate(absent); validator.validate(present)
    mixed = {**absent, "previousReleased": present["previousReleased"], "rollbackReadiness": present["rollbackReadiness"]}
    assert list(validator.iter_errors(mixed))


# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-005
def test_human_consume_lost_response_reads_exact_winner_and_rejects_competitor() -> None:
    from types import SimpleNamespace
    from quwoquan_ops.ci.qualified_prod import consume_initial_human_authority
    exact = {"ref": "immutable/evidence.json", "digest": "sha256:" + "a" * 64}
    binding = {"target": "prod-hosted", "environment": "prod", "deliveryTargets": ["service"],
        "stableAdmission": exact, "candidateMaterialManifest": exact, "serviceMaterial": exact,
        "webMaterial": exact, "inventoryDigest": "sha256:" + "b" * 64, "absenceProof": exact,
        "attemptId": "sha256:" + "c" * 64, "recoveryResources": exact,
        "candidateDigest": "sha256:" + "d" * 64, "observationDigest": "sha256:" + "e" * 64,
        "executionOwner": "owner-1", "executionGeneration": 3, "releaseGeneration": 0,
        "recoveryEffects": ["disable_attempt_units", "stop_attempt_traffic"],
        "actions": ["authorize_initial_prod"]}
    command = digest(binding)
    class Provider:
        release_evidence_eligible = True
        consumed = False
        competitor = False
        def readback(self, _): return SimpleNamespace(status="present", exact_bytes=b"signed", provider_receipt_ref="provider/1")
        def consume(self, *_args, **_kwargs): self.consumed = True; raise TimeoutError("lost response")
    class Verifier:
        def __init__(self, provider): self.provider = provider
        def verify(self, *_):
            state = "consumed" if self.provider.consumed else "available"
            return {"role":"release_owner", "decision_kind":"production_campaign_approval", "actor_authenticated":True,
                "scope":{"increment":binding["attemptId"]}, "evidence_fingerprint":command,
                "actions":binding["actions"], "receipt_state":state, "expires_at":"2027-01-01T00:00:00Z",
                "receipt_generation":2 if state == "consumed" else 1, "receipt_previous_generation":1 if state == "consumed" else 0,
                "receipt_etag":"etag-1", "winner_idempotency_key":("competitor" if self.provider.competitor else binding["attemptId"]) if state == "consumed" else "",
                "winner_command_digest":command if state == "consumed" else ""}
    provider = Provider(); result = consume_initial_human_authority(binding=binding, provider=provider,
        verifier=Verifier(provider), receipt_ref="decision/1", now="2026-09-13T00:00:00Z")
    assert result["winnerAttemptId"] == binding["attemptId"] and result["authorityGeneration"] == 2
    provider = Provider(); provider.competitor = True
    with pytest.raises(QualifiedProdError, match="OUTCOME_UNKNOWN|CONFLICT"):
        consume_initial_human_authority(binding=binding, provider=provider, verifier=Verifier(provider),
            receipt_ref="decision/1", now="2026-09-13T00:00:00Z")


# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-005
def test_unactivated_safe_terminal_requires_ordered_stop_and_preserves_resources(tmp_path: Path) -> None:
    from quwoquan_ops.ci.qualified_prod import create_prod_unactivated_safe_fact, validate_prod_unactivated_safe_fact
    source = facts(tmp_path); prior = facts_by_ref(tmp_path, absent_prior(tmp_path))
    authority = facts_by_ref(tmp_path, prior["humanAuthority"])
    authority.update({"stableAdmission": source["tag"], "candidateMaterialManifest": source["material"],
                      "serviceMaterial": {"ref":"immutable/evidence.json","digest":"sha256:"+"a"*64},
                      "webMaterial": {"ref":"immutable/evidence.json","digest":"sha256:"+"a"*64},
                      "recoveryResources": prior["recoveryResources"], "recoveryEffects":["stop_attempt_traffic"]})
    prior["humanAuthority"] = write(tmp_path, "immutable/absence/human-bound.json", authority)
    source["prior"] = write(tmp_path, "immutable/prod/absent-bound.json", prior)
    _, admission = admit(tmp_path, source)
    admission_body = facts_by_ref(tmp_path, admission)
    failed = {"schema":"quwoquan_ops.prod_stage_attempt_fact.v1", "admission":admission,
        "stage":"canary", "attemptNumber":1, "status":"failed", "predecessor":None,
        "evidence":{k:{"ref":f"e/{k}","digest":"sha256:"+str(i)*64} for i,k in enumerate(("activation","health","slo","placement","readback"),1)},
        "hostedReceiptReadback":{"ref":"hosted/failure","digest":"sha256:"+"7"*64},
        "ociDigests":admission_body["ociDigests"], "recordedAt":"2026-09-13T00:01:00Z"}
    failed["attemptId"] = digest(failed)
    failed_ref = write(tmp_path, f"prod/rollout/{admission_body['admissionId']}/canary/{failed['attemptId']}.json", failed)
    recovery = {"schema":"quwoquan_ops.prod_initial_recovery_readback.v1", "status":"passed",
        "target":"prod-hosted", "environment":"prod", "admission":admission, "attempt":failed_ref,
        "executionOwner":"owner-1", "executionGeneration":7, "previousGeneration":0, "committedGeneration":1,
        "trafficStoppedAt":"2026-09-13T00:02:00Z", "trafficReadbackAt":"2026-09-13T00:02:01Z",
        "unitsStoppedAt":"2026-09-13T00:02:02Z", "autoRestartDisabled":True,
        "inactiveConfigRemoved":True, "inventoryComplete":True, "candidateExposed":False,
        "preservedResources":["database","volume","media","backup","recoveryPoints","audit"],
        "coexistingWorkloadsUnchanged":True, "auditAppended":True}
    recovery_ref = write(tmp_path, "immutable/recovery/readback.json", recovery)
    path = create_prod_unactivated_safe_fact(root=tmp_path, admission_ref=admission,
        failed_attempt_ref=failed_ref, recovery_readback_ref=recovery_ref, recorded_at="2026-09-13T00:03:00Z")
    safe = validate_prod_unactivated_safe_fact(json.loads(path.read_text()))
    assert safe["terminal"] == "unactivated_safe" and safe["committedGeneration"] == 1
    assert not (tmp_path / "prod/released").exists() and not (tmp_path / "prod/rollbacks").exists() and not (tmp_path / "prod/soak").exists()
    broken = dict(recovery); broken["candidateExposed"] = True
    with pytest.raises(QualifiedProdError, match="UNKNOWN"):
        create_prod_unactivated_safe_fact(root=tmp_path, admission_ref=admission,
            failed_attempt_ref=failed_ref, recovery_readback_ref=write(tmp_path,"immutable/recovery/broken.json",broken),
            recorded_at="2026-09-13T00:03:00Z")
