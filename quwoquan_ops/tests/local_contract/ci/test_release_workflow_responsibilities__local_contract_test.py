# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-003
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[4]
WORKFLOWS = ROOT / ".github/workflows"


def load(name: str) -> tuple[str, dict]:
    text = (WORKFLOWS / name).read_text(encoding="utf-8")
    return text, yaml.safe_load(text)


def test_artifact_gc_has_no_workflow_run_fanout() -> None:
    text, workflow = load("artifact-lifecycle.yml")
    assert "workflow_run" not in workflow[True]
    assert set(workflow[True]) == {"schedule", "workflow_dispatch", "pull_request"}
    assert "github.event.workflow_run" not in text


def test_environment_and_device_actions_are_deleted_after_cutover() -> None:
    for name in (
        "pre-release-gate.yml", "app-env-device-matrix-self-hosted.yml",
        "beta-device-platform.yml", "provider-release-evidence.yml",
    ):
        assert not (WORKFLOWS / name).exists()


def test_release_workflows_have_three_separate_responsibilities() -> None:
    qualification, q = load("release-qualification.yml")
    selection, s = load("release-tag-selection.yml")
    prod, p = load("deploy-prod-auto.yml")
    assert set(q[True]) == {"workflow_dispatch"}
    assert set(q[True]["workflow_dispatch"]["inputs"]) == {
        "rc_tag_admission_ref", "qualification_request_ref", "source_git_sha",
        "product_version_manifest_ref", "package_acceptance_fact_ref",
        "provider_fact_ref", "uat_fact_ref", "supply_chain_fact_ref",
    }
    assert q["jobs"]["allocate_build_number"]["environment"] == "release-qualification"
    assert q["jobs"]["service_factory"]["uses"] == "./.github/workflows/service_pipeline.yml"
    assert q["jobs"]["app_factory"]["uses"] == "./.github/workflows/app_pipeline.yml"
    assert "artifact_build_number" not in q[True]["workflow_dispatch"]["inputs"]
    assert "github.run_number" in qualification
    assert "reusable factory omitted" in qualification
    assert "qualification-material" in qualification
    assert "qualification-finalize" in qualification
    assert "QualificationFact issued" in qualification
    assert "pending external qualification facts" not in qualification
    assert set(s[True]) == {"workflow_dispatch"}
    assert s["jobs"]["pre_admission"]["environment"] == "release-selection"
    assert s["jobs"]["create_and_readback"]["environment"] == "release-selection"
    assert selection.index("tag-admit-stable") < selection.index("git push origin")
    assert selection.index("tag-admit-rc") < selection.index("git push origin")
    assert "git tag -a" in selection and "release-controller" in selection
    assert "verified-pre-push-local-admission" not in selection
    assert set(p[True]) == {"workflow_dispatch"}
    assert set(p[True]["workflow_dispatch"]["inputs"]) == {
        "release_tag_admission_ref", "previous_active_released_ledger_ref",
        "rollback_readiness_ref",
    }
    assert "push:" not in prod and "latestQualified" not in prod and "RELEASED_RELEASE_EVIDENCE_REF" not in prod
    assert 'release_control.py --store-root "$STORE" prod-admit' in prod
    assert "prod-materialize-input" in prod
    assert "stackctl.py deploy --target prod-hosted" in prod
    assert '--prod-activation-admission "$STORE/$ADMISSION_LOCAL_REF"' in prod
    assert "${{ steps.publish.outputs.admission_ref }}" in prod
    for retired in (
        "QWQ_ENVIRONMENT_ACCEPTANCE_ROOT",
        "PROD_ENVIRONMENT_ACCEPTANCE_REF",
        "PROD_ENVIRONMENT_ACCEPTANCE_DIGEST",
        "PROD_ENVIRONMENT_ACCEPTANCE_ROOT",
        "--environment-acceptance-ref",
        "--environment-acceptance-sha256",
        "--environment-acceptance-root",
    ):
        assert retired not in prod
    assert "unreachable until" not in prod
    assert "release tag admission transport must expose" not in prod


def _prod_inline(job: str, step: str, marker: str) -> str:
    _, workflow = load("deploy-prod-auto.yml")
    run = next(item["run"] for item in workflow["jobs"][job]["steps"] if item.get("id") == step)
    return next(body for body in re.findall(r"<<'PY'\n(.*?)\nPY", run, re.S) if marker in body)


def _bytes_digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _oci_fact(payload: dict) -> tuple[dict[str, str], bytes, bytes]:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    manifest = json.dumps({"schemaVersion": 2, "layers": [{"digest": _bytes_digest(raw), "size": len(raw)}]}).encode()
    exact = {"ref": "ghcr.io/contract/prod-fact@" + _bytes_digest(manifest), "digest": _bytes_digest(raw)}
    assert exact["ref"].rsplit("@", 1)[1] != exact["digest"]
    return exact, manifest, raw


@pytest.mark.parametrize("field", ["qualificationFact", "candidateMaterialManifest"])
@pytest.mark.parametrize("drift", ["none", "payload", "expected", "transport", "layer"])
def test_prod_tag_materialization_separates_transport_and_fact_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, drift: str,
) -> None:
    from quwoquan_ops.ci import promotion_evidence
    from quwoquan_ops.ci.qualified_prod import _exact

    registry = {}
    tag = {}
    for name in ("qualificationFact", "candidateMaterialManifest"):
        exact, manifest, raw = _oci_fact({"field": name})
        if name == field and drift == "payload":
            changed, manifest, raw = _oci_fact({"field": name, "changed": True})
            exact["ref"] = changed["ref"]
        if name == field and drift == "expected":
            exact["digest"] = exact["ref"].rsplit("@", 1)[1]
        if name == field and drift == "transport":
            manifest += b" "
        if name == field and drift == "layer":
            raw = b'{"changed":true}\n'
        registry[exact["ref"]] = (manifest, raw)
        tag[name] = exact
    tag_path = tmp_path / "tag.json"
    tag_path.write_text(json.dumps(tag), encoding="utf-8")
    original = tag_path.read_bytes()
    pulled = []

    def run(command, **kwargs):
        if command[:2] == ["oras", "pull"]:
            assert command[2] == "--output"
            ref = command[-1]
            pulled.append(ref)
            manifest, raw = registry[ref]
            # 只替换 ORAS/registry 边界；exact pull 的 manifest/layer 完整性失败不得继续。
            valid = ref.rsplit("@", 1)[1] == _bytes_digest(manifest)
            valid = valid and json.loads(manifest)["layers"][0]["digest"] == _bytes_digest(raw)
            if valid:
                (Path(command[3]) / "fact.json").write_bytes(raw)
            return subprocess.CompletedProcess(command, 0 if valid else 1, "", "OCI integrity drift")
        assert command[:3] == ["python3", "quwoquan_ops/ci/promotion_evidence.py", "materialize-oci"]
        promotion_evidence.materialize_oci_fact(
            exact_ref=command[command.index("--ref") + 1],
            output_file=Path(command[command.index("--output-file") + 1]),
        )
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(sys, "argv", ["-", str(tmp_path), "tag.json"])
    code = _prod_inline("prod_activation_admission", "admit", "original_tag_bytes")
    if drift == "none":
        exec(compile(code, "prod-tag-materialization", "exec"), {})
        for name, exact in tag.items():
            assert _exact(tmp_path, exact, name)[1] == exact
        assert set(pulled) == set(registry)
    elif drift in {"transport", "layer"}:
        with pytest.raises(promotion_evidence.PromotionEvidenceError, match="OCI_UNAVAILABLE"):
            exec(compile(code, "prod-tag-materialization", "exec"), {})
    else:
        with pytest.raises(SystemExit, match="payload digest drifted"):
            exec(compile(code, "prod-tag-materialization", "exec"), {})
    assert tag_path.read_bytes() == original


@pytest.mark.parametrize("field", ["releaseTagAdmission", "qualification", "candidateMaterialManifest", "previousActiveReleasedLedger", "rollbackReadiness"])
def test_prod_activation_predecessor_digest_is_payload_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], field: str,
) -> None:
    fields = ("releaseTagAdmission", "qualification", "candidateMaterialManifest", "previousActiveReleasedLedger", "rollbackReadiness")
    fact = {name: _oci_fact({"field": name})[0] for name in fields}
    factory = _oci_fact({"factory": True})[0]
    fact["factoryMaterials"] = {
        kind: {"ociRef": factory["ref"], "ociDigest": factory["ref"].rsplit("@", 1)[1],
               "payloadDigest": factory["digest"], "materialDigest": factory["digest"]}
        for kind in ("service", "app")
    }
    path = tmp_path / "admission.json"
    code = _prod_inline("prod_rollout", "activation_input", "factoryMaterials")
    monkeypatch.setattr(sys, "argv", ["-", str(path)])
    path.write_text(json.dumps(fact))
    exec(compile(code, "prod-activation-predecessors", "exec"), {})
    assert f"authority\t{fact[field]['ref']}\t{fact[field]['digest']}\n" in capsys.readouterr().out
    for bad in ({**fact[field], "ref": "ghcr.io/contract/fact:latest"}, {**fact[field], "digest": "not-a-digest"}, {**fact[field], "extra": True}):
        path.write_text(json.dumps({**fact, field: bad}))
        with pytest.raises(SystemExit, match="exact OCI-bound evidence"):
            exec(compile(code, "prod-activation-predecessors", "exec"), {})
    fact["factoryMaterials"]["service"]["ociDigest"] = factory["digest"]
    path.write_text(json.dumps(fact))
    with pytest.raises(SystemExit, match="factory material locator drifted"):
        exec(compile(code, "prod-activation-predecessors", "exec"), {})


def test_prod_authority_materialization_keeps_payload_checks_and_propagates_parser_failure() -> None:
    text, _ = load("deploy-prod-auto.yml")
    # process substitution 的退出码不会由 set -e/pipefail 传播；先完成验证再消费 TSV。
    assert 'done < <(python3 - "$STORE/$ADMISSION_OCI_REF"' not in text
    assert 'done < <(python3 - "$STORE/$RELEASED_LOCAL_REF"' not in text
    for expected in ('= "$ADMISSION_DIGEST"', '= "$digest"', '= "$RELEASED_DIGEST"', '= "$payload_digest"'):
        assert expected in text
    assert 'value["ociRef"].rsplit("@", 1)[-1] != value.get("ociDigest")' in text
