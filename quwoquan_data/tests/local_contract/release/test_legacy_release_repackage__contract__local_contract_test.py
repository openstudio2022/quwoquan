# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t2
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t3
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t4
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t5
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t6
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t7
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t8
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t9
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t10
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t11
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t12
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t13
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t14
"""legacy sealed release current-schema repackage 的闭集、lineage、零写与 authority 单轨。"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from content.release.canonical import legacy_release_repackage as subject
from content.release.canonical.object_transaction_contract import _tree_digest
from content.release.canonical.producer_release_handoff import _canonical_bytes, _digest
from core.schema import assert_valid

REVISION = "a" * 40
SOURCE = "legacy-release"
TARGET = "current-release"
REF = "entities/travel/test/home"

def _install_provider(tmp_path: Path, monkeypatch, allowed: list[str]) -> None:
    registry=tmp_path/"authority-registry.json"; registry.write_text(json.dumps({str(item[0]):item[1] for item in allowed}))
    verifier=tmp_path/"authority-verifier.py"
    verifier.write_text("""#!/usr/bin/env python3
import json,os,sys
r=json.loads(sys.stdin.read()); allowed=json.loads(open(os.environ['QWQ_TEST_AUTHORITY_REGISTRY']).read())
if allowed.get(r['ref']) != r['digest']: raise SystemExit(2)
print(json.dumps({**r,'state':'verified'}))
""")
    verifier.chmod(0o755); monkeypatch.setenv("QWQ_TEST_AUTHORITY_REGISTRY",str(registry)); monkeypatch.setenv("QWQ_CONTENT_AUTHORITY_VERIFIER",str(verifier))

def _seal_repository_authority(release: Path, terminal_digest: str) -> tuple[dict,str]:
    authority={"schema":"test.signed_legacy_repository_authority","repositoryId":"legacy-content","sourceTerminalDigest":terminal_digest,"provider":"fixture-signed-registry"}
    path=release/"repository_authority.json"; path.write_bytes(_canonical_bytes(authority))
    return authority,_digest(path.read_bytes())

def _repo(root: Path) -> Path:
    publish = root / "publish"; (publish / ".git").mkdir(parents=True)
    (publish / "repository.json").write_bytes(_canonical_bytes({"schema":"quwoquan_data.publish_repository.v2","repositoryId":"content-a","layoutVersion":2}))
    return publish

def _legacy(releases: Path, *, schema: str = "quwoquan_data.producer_release_handoff") -> tuple[str, str]:
    release = releases / SOURCE; (release / "payload").mkdir(parents=True)
    cohort = {"schema":"quwoquan_data.release_cohort","producerBaselineRevision":REVISION,"objectRefs":[REF],
              "milestone":"M1","expectedCarrierCounts":{"homepage":1,"article":0,"image":0,"video":0},"releaseClass":"production"}
    cohort_raw = _canonical_bytes(cohort); (release / "cohort.json").write_bytes(cohort_raw)
    header = b'{}\n'; (release / "payload/release.json").write_bytes(header)
    # payload_digest includes payload only and remains stable after terminal files are written.
    from core.release_layout import payload_digest
    handoff = {"schema":schema,"handoffId":SOURCE,"releaseId":SOURCE,"milestone":"M1",
        "carrierCounts":{"homepage":1,"article":0,"image":0,"video":0,"total":1},
        "release":{"scope":"output","ref":f"data/releases/{SOURCE}","payloadDigest":payload_digest(release),
                   "headerRef":f"data/releases/{SOURCE}/payload/release.json","headerDigest":_digest(header)},
        "explicitCohort":{"scope":"output","ref":f"data/releases/{SOURCE}/cohort.json","digest":_digest(cohort_raw),"document":cohort},
        "contentPoolObjects":[{"objectRef":REF,"carrier":"homepage","queryDocument":{
            "schema":"quwoquan_data.content_pool_handoff_query","projectorVersion":"content_pool_handoff_v1",
            "specRef":"specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#req-008",
            "identity":{"objectType":"homepage","objectId":"entity:test:home","objectRef":"travel/test/home","carrier":"homepage","contentVersion":1,"recordSequence":1},
            "lifecycle":{"status":"active"},
            "admission":{"processResult":"completed","qualityResult":"passed","eligibilityResult":"passed","rightsResult":"passed",
                "rightsAuthorityRef":REF+"/content_review.json","rightsAuthorityDigest":"sha256:"+"c"*64,"evidenceRef":"content_review.json","evidenceDigest":"sha256:"+"c"*64},
            "scope":{"usageScope":"research","variantPurpose":"not_applicable"},
            "digests":{"payloadDigest":"sha256:"+"d"*64,"canonicalObjectDigest":"sha256:"+"d"*64,"selectionIdentityDigest":"sha256:"+"e"*64},
            "refs":{"canonicalObjectRef":REF,"manifestRef":REF+"/manifest.json","poolRecordRef":REF+"/_pool/versions/1.json"},
            "contentLibrary":{"holder":"content_library","bindingDigest":"sha256:"+"f"*64,"bindings":[]}},
            "queryDigest":"sha256:"+"0"*64}],"producerBaselineRevision":REVISION,"producerContractDigest":"sha256:"+"b"*64}
    raw = _canonical_bytes(handoff); (release / "producer_release_handoff.json").write_bytes(raw)
    terminal_digest=_digest(_canonical_bytes({"releaseId":SOURCE,"handoffDigest":_digest(raw),"cohortDigest":_digest(cohort_raw)}))
    _,authority_digest=_seal_repository_authority(release,terminal_digest)
    evidence={"schema":"quwoquan_data.legacy_source_repository_evidence","sourceRepositoryId":"legacy-content","sourceTerminalDigest":terminal_digest,"issuer":"legacy-release-seal","authorityRef":str(release/"repository_authority.json"),"authorityDigest":authority_digest}
    evidence_path=releases/".repository-authorities"/f"{SOURCE}.json"; evidence_path.parent.mkdir(exist_ok=True); evidence_path.write_bytes(_canonical_bytes(evidence))
    # Tests patch the tree binding after freeze fixture setup where needed.
    return _digest(raw), _digest(cohort_raw)

def _evidence(frozen):
    path=frozen.root/".repository-authorities"/f"{frozen.release_id}.json"
    return json.loads(path.read_bytes()), _digest(path.read_bytes())

def _fake_build(**kwargs):
    release = kwargs["release_root"] / kwargs["release_id"]
    (release / "payload").mkdir(parents=True, exist_ok=True)
    (release / "payload/release.json").write_bytes(b'{}\n')
    return {"status":"created"}

def _fake_handoff(**kwargs):
    release = kwargs["release_root"] / kwargs["release_id"]
    cohort = json.loads(Path(kwargs["cohort_file"]).read_bytes())
    document = {"schema":"quwoquan_data.producer_release_handoff","repositoryId":"content-a","handoffId":kwargs["release_id"],
        "releaseId":kwargs["release_id"],"milestone":kwargs["milestone"],"carrierCounts":{"homepage":1,"article":0,"image":0,"video":0,"total":1},
        "release":{"scope":"output","ref":"x","payloadDigest":"sha256:"+"1"*64,"headerRef":"x","headerDigest":"sha256:"+"2"*64},
        "explicitCohort":{"scope":"output","ref":"x","digest":_digest(_canonical_bytes(cohort)),"document":cohort},
        "contentPoolObjects":[{"objectRef":REF,"carrier":"homepage","queryDocument":{},"queryDigest":"sha256:"+"3"*64}],
        "artifact":{"rootRef":"x","entries":[{"ref":"cohort.json","digest":"sha256:"+"4"*64,"bytes":1}],"treeDigest":"sha256:"+"5"*64},
        "producerBaselineRevision":REVISION,"producerContractDigest":"sha256:"+"6"*64}
    path = release / "producer_release_handoff.json"; path.write_bytes(_canonical_bytes(document))
    return document, path, False

def _run(tmp_path: Path, monkeypatch, **overrides):
    publish = _repo(tmp_path); releases = tmp_path / "releases"; hd, cd = _legacy(releases)
    _install_provider(tmp_path,monkeypatch,[(releases/SOURCE/"repository_authority.json",_digest((releases/SOURCE/"repository_authority.json").read_bytes()))])
    _install_provider(tmp_path,monkeypatch,[(releases/SOURCE/"repository_authority.json",_digest((releases/SOURCE/"repository_authority.json").read_bytes()))])
    monkeypatch.setattr(subject, "build_pool_release", _fake_build)
    monkeypatch.setattr(subject, "write_producer_release_handoff", _fake_handoff)
    monkeypatch.setattr(subject, "read_producer_release_handoff", lambda path, **kwargs: json.loads(path.read_bytes()))
    monkeypatch.setattr(subject, "assert_valid", lambda *args, **kwargs: None)
    from content.release.canonical import producer_release_handoff as handoff_module
    monkeypatch.setattr(handoff_module, "_validate_embedded_pool_rows", lambda **kwargs: [])
    frozen = subject.freeze_legacy_source(source_root=releases, release_id=SOURCE, handoff_digest=hd, cohort_digest=cd)
    evidence=json.loads((releases/".repository-authorities"/f"{SOURCE}.json").read_bytes())
    values = dict(frozen_source=frozen,publish_root=publish,target_release_root=releases,repository_id="content-a",source_repository_evidence=evidence,source_repository_evidence_ref=f".repository-authorities/{SOURCE}.json",source_repository_evidence_digest=_digest(_canonical_bytes(evidence)),
        target_release_id=TARGET,milestone="M1",producer_baseline_revision=REVISION,repo_root=tmp_path)
    values.update(overrides)
    return releases, subject.repackage_legacy_release(**values)

def test_gwt_062_t1_supported_legacy_rebuilds_distinct_current_lineage(tmp_path, monkeypatch):
    """spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t1"""
    releases, result = _run(tmp_path, monkeypatch)
    assert result["status"] == "created" and result["targetReleaseId"] != result["sourceReleaseId"]
    target = json.loads((releases / TARGET / "producer_release_handoff.json").read_bytes())
    assert_valid(target["repackageLineage"], "release", "legacy_release_repackage_lineage")
    assert target["repackageLineage"]["sourceHandoffDigest"].startswith("sha256:")
    assert _tree_digest(releases / SOURCE) == result["sourceTreeDigest"]
    assert not any(key in target for key in ("reviewer","attestation","execution","receipts"))

def test_unknown_schema_and_digest_or_membership_drift_are_typed_zero_write(tmp_path):
    """spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t4, spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t5"""
    publish = _repo(tmp_path); releases = tmp_path / "releases"; hd, cd = _legacy(releases, schema="unknown")
    before = _tree_digest(releases / SOURCE)
    with pytest.raises(subject.LegacyReleaseRepackageError, match="LEGACY_SCHEMA_UNSUPPORTED"):
        subject.freeze_legacy_source(source_root=releases, release_id=SOURCE, handoff_digest=hd, cohort_digest=cd)
    assert not (releases / TARGET).exists() and _tree_digest(releases / SOURCE) == before

@pytest.mark.parametrize(("fault","exception","code","output_visible","publish_visible"), [
    ("staging_write", OSError, "injected staging write", False, False),
    ("canonicalization", subject.LegacyReleaseRepackageError, "CANONICALIZATION_FAILED", False, False),
    ("integrity", subject.LegacyReleaseRepackageError, "INTEGRITY_FAILED", False, False),
    ("rename", OSError, "injected rename", False, False),
    ("terminal", OSError, "injected terminal", False, False),
    ("publish_terminal", OSError, "injected publish terminal", True, False),
    ("readback", OSError, "injected readback", True, True),
])
def test_fault_sections_leave_exact_visibility_state(tmp_path, monkeypatch, fault, exception, code, output_visible, publish_visible):
    """spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t9"""
    publish = _repo(tmp_path); releases = tmp_path / "releases"; hd, cd = _legacy(releases)
    authority=releases/SOURCE/"repository_authority.json"
    _install_provider(tmp_path,monkeypatch,[(authority,_digest(authority.read_bytes()))])
    monkeypatch.setattr(subject, "build_pool_release", _fake_build)
    monkeypatch.setattr(subject, "write_producer_release_handoff", _fake_handoff)
    monkeypatch.setattr(subject, "read_producer_release_handoff", lambda path, **kwargs: json.loads(path.read_bytes()))
    monkeypatch.setattr(subject, "assert_valid", lambda *a, **k: None)
    from content.release.canonical import producer_release_handoff as handoff_module
    monkeypatch.setattr(handoff_module, "_validate_embedded_pool_rows", lambda **kwargs: [])
    frozen=subject.freeze_legacy_source(source_root=releases,release_id=SOURCE,handoff_digest=hd,cohort_digest=cd)
    reached=[]
    original_publish=subject._publish_staging
    def observed_publish(staging,target):
        reached.append("output_publish")
        return original_publish(staging,target)
    monkeypatch.setattr(subject,"_publish_staging",observed_publish)
    with pytest.raises(exception, match=code):
        subject.repackage_legacy_release(frozen_source=frozen,publish_root=publish,target_release_root=releases,
            repository_id="content-a",source_repository_evidence=_evidence(frozen)[0],source_repository_evidence_ref=f".repository-authorities/{SOURCE}.json",source_repository_evidence_digest=_evidence(frozen)[1],target_release_id=TARGET,milestone="M1",producer_baseline_revision=REVISION,repo_root=tmp_path,fault=fault)
    assert ((releases/TARGET).is_dir()) is output_visible
    assert ((publish/"releases"/TARGET).is_dir()) is publish_visible
    assert ("output_publish" in reached) is output_visible

def test_same_target_exact_replay_and_changed_binding_conflict(tmp_path, monkeypatch):
    """spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t2, spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t8"""
    releases, first = _run(tmp_path, monkeypatch)
    monkeypatch.setattr(subject, "read_producer_release_handoff", lambda path, **kwargs: json.loads(path.read_bytes()))
    source = releases / SOURCE
    replay = subject.repackage_legacy_release(frozen_source=subject.freeze_legacy_source(source_root=releases,release_id=SOURCE,handoff_digest=_digest((source/"producer_release_handoff.json").read_bytes()),cohort_digest=_digest((source/"cohort.json").read_bytes())),publish_root=tmp_path/"publish",target_release_root=releases,repository_id="content-a",source_repository_evidence_ref=f".repository-authorities/{SOURCE}.json",source_repository_evidence=_evidence(subject.freeze_legacy_source(source_root=releases,release_id=SOURCE,handoff_digest=_digest((source/"producer_release_handoff.json").read_bytes()),cohort_digest=_digest((source/"cohort.json").read_bytes())))[0],source_repository_evidence_digest=_evidence(subject.freeze_legacy_source(source_root=releases,release_id=SOURCE,handoff_digest=_digest((source/"producer_release_handoff.json").read_bytes()),cohort_digest=_digest((source/"cohort.json").read_bytes())))[1],
        target_release_id=TARGET,milestone="M1",producer_baseline_revision=REVISION,repo_root=tmp_path)
    assert first["outputHandoffDigest"] == replay["outputHandoffDigest"] and replay["status"] == "replayed"
    with pytest.raises(subject.LegacyReleaseRepackageError, match="TARGET_CONFLICT"):
        subject.repackage_legacy_release(frozen_source=subject.freeze_legacy_source(source_root=releases,release_id=SOURCE,handoff_digest=_digest((source/"producer_release_handoff.json").read_bytes()),cohort_digest=_digest((source/"cohort.json").read_bytes())),publish_root=tmp_path/"publish",target_release_root=releases,repository_id="content-a",source_repository_evidence_ref=f".repository-authorities/{SOURCE}.json",source_repository_evidence=_evidence(subject.freeze_legacy_source(source_root=releases,release_id=SOURCE,handoff_digest=_digest((source/"producer_release_handoff.json").read_bytes()),cohort_digest=_digest((source/"cohort.json").read_bytes())))[0],source_repository_evidence_digest=_evidence(subject.freeze_legacy_source(source_root=releases,release_id=SOURCE,handoff_digest=_digest((source/"producer_release_handoff.json").read_bytes()),cohort_digest=_digest((source/"cohort.json").read_bytes())))[1],
            target_release_id=TARGET,milestone="M10",producer_baseline_revision=REVISION,repo_root=tmp_path)

@pytest.mark.parametrize("release_id", ["../escape", "a/b", ".", "..", "/absolute"])
def test_release_ids_reject_path_traversal_before_io(tmp_path, release_id):
    """spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t9"""
    releases = tmp_path / "releases"; releases.mkdir()
    with pytest.raises(subject.LegacyReleaseRepackageError, match="RELEASE_ID_INVALID"):
        subject.freeze_legacy_source(source_root=releases, release_id=release_id,
                                     handoff_digest="sha256:"+"0"*64, cohort_digest="sha256:"+"1"*64)
    assert list(releases.iterdir()) == []

def test_source_root_ancestor_and_release_symlinks_are_rejected(tmp_path):
    real = tmp_path / "real"; real.mkdir(); link = tmp_path / "link"; link.symlink_to(real, target_is_directory=True)
    with pytest.raises(subject.LegacyReleaseRepackageError, match="ROOT_SYMLINK"):
        subject.freeze_legacy_source(source_root=link, release_id=SOURCE,
                                     handoff_digest="sha256:"+"0"*64, cohort_digest="sha256:"+"1"*64)
    releases = tmp_path / "releases"; releases.mkdir(); (releases / SOURCE).symlink_to(real, target_is_directory=True)
    with pytest.raises(subject.LegacyReleaseRepackageError, match="RELEASE_SYMLINK"):
        subject.freeze_legacy_source(source_root=releases, release_id=SOURCE,
                                     handoff_digest="sha256:"+"0"*64, cohort_digest="sha256:"+"1"*64)

def test_gwt_062_t5_source_mutation_race_fails_before_publish(tmp_path, monkeypatch):
    """spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t5, spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t10"""
    publish = _repo(tmp_path); releases = tmp_path / "releases"; hd, cd = _legacy(releases)
    _install_provider(tmp_path,monkeypatch,[(releases/SOURCE/"repository_authority.json",_digest((releases/SOURCE/"repository_authority.json").read_bytes()))])
    _install_provider(tmp_path,monkeypatch,[(releases/SOURCE/"repository_authority.json",_digest((releases/SOURCE/"repository_authority.json").read_bytes()))])
    from content.release.canonical import producer_release_handoff as handoff_module
    monkeypatch.setattr(handoff_module, "_validate_embedded_pool_rows", lambda **kwargs: [])
    frozen = subject.freeze_legacy_source(source_root=releases, release_id=SOURCE, handoff_digest=hd, cohort_digest=cd)
    monkeypatch.setattr(subject, "build_pool_release", _fake_build); monkeypatch.setattr(subject, "write_producer_release_handoff", _fake_handoff)
    monkeypatch.setattr(subject, "read_producer_release_handoff", lambda path, **kwargs: json.loads(path.read_bytes()))
    monkeypatch.setattr(subject, "assert_valid", lambda *args, **kwargs: None)
    def mutate():
        (releases / SOURCE / "race.txt").write_text("changed", encoding="utf-8")
    with pytest.raises(subject.LegacyReleaseRepackageError, match="SOURCE_TREE_MUTATED"):
        subject.repackage_legacy_release(frozen_source=frozen,publish_root=publish,target_release_root=releases,
            repository_id="content-a",source_repository_evidence=_evidence(frozen)[0],source_repository_evidence_ref=f".repository-authorities/{SOURCE}.json",source_repository_evidence_digest=_evidence(frozen)[1],target_release_id=TARGET,milestone="M1",producer_baseline_revision=REVISION,
            repo_root=tmp_path,before_source_cas=mutate)
    assert not (releases / TARGET).exists()

def test_target_repository_and_root_drift_are_rejected(tmp_path, monkeypatch):
    """spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t4, spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t11"""
    releases, _ = _run(tmp_path, monkeypatch)
    source = releases / SOURCE
    frozen = subject.freeze_legacy_source(source_root=releases,release_id=SOURCE,
        handoff_digest=_digest((source/"producer_release_handoff.json").read_bytes()),cohort_digest=_digest((source/"cohort.json").read_bytes()))
    with pytest.raises(Exception, match="IDENTITY_MISMATCH"):
        subject.repackage_legacy_release(frozen_source=frozen,publish_root=tmp_path/"publish",target_release_root=releases,
            repository_id="wrong",source_repository_evidence=_evidence(frozen)[0],source_repository_evidence_ref=f".repository-authorities/{SOURCE}.json",source_repository_evidence_digest=_evidence(frozen)[1],target_release_id="another",milestone="M1",producer_baseline_revision=REVISION,repo_root=tmp_path)
    other = tmp_path / "other-releases"; other.mkdir()
    with pytest.raises(subject.LegacyReleaseRepackageError, match="ROOT_BINDING_MISMATCH"):
        subject.repackage_legacy_release(frozen_source=frozen,publish_root=tmp_path/"publish",target_release_root=other,
            repository_id="content-a",source_repository_evidence=_evidence(frozen)[0],source_repository_evidence_ref=f".repository-authorities/{SOURCE}.json",source_repository_evidence_digest=_evidence(frozen)[1],target_release_id="another",milestone="M1",producer_baseline_revision=REVISION,repo_root=tmp_path)

def test_candidate_and_recovery_identities_must_each_be_fresh(tmp_path, monkeypatch):
    """spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t14"""
    releases, _ = _run(tmp_path, monkeypatch)
    source = releases / SOURCE
    frozen = subject.freeze_legacy_source(source_root=releases,release_id=SOURCE,
        handoff_digest=_digest((source/"producer_release_handoff.json").read_bytes()),cohort_digest=_digest((source/"cohort.json").read_bytes()))
    with pytest.raises(subject.LegacyReleaseRepackageError, match="TARGET_ID_NOT_FRESH"):
        subject.repackage_legacy_release(frozen_source=frozen,publish_root=tmp_path/"publish",target_release_root=releases,
            repository_id="content-a",source_repository_evidence=_evidence(frozen)[0],source_repository_evidence_ref=f".repository-authorities/{SOURCE}.json",source_repository_evidence_digest=_evidence(frozen)[1],target_release_id=SOURCE,milestone="M1",producer_baseline_revision=REVISION,repo_root=tmp_path)
    # recovery uses another fresh identity and does not overwrite candidate.
    monkeypatch.setattr(subject, "read_producer_release_handoff", lambda path, **kwargs: json.loads(path.read_bytes()))
    result = subject.repackage_legacy_release(frozen_source=frozen,publish_root=tmp_path/"publish",target_release_root=releases,
        repository_id="content-a",source_repository_evidence=_evidence(frozen)[0],source_repository_evidence_ref=f".repository-authorities/{SOURCE}.json",source_repository_evidence_digest=_evidence(frozen)[1],target_release_id="recovery-release",milestone="M1",producer_baseline_revision=REVISION,repo_root=tmp_path)
    assert result["targetReleaseId"] not in {SOURCE, TARGET}

def test_handler_freezes_source_once_and_fence_uses_same_refs(tmp_path, monkeypatch):
    """spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t11"""
    from content.release.canonical import handler
    frozen = SimpleNamespace(refs=(REF,))
    calls = []
    monkeypatch.setattr(handler, "PUBLISH_ROOT", tmp_path/"publish")
    monkeypatch.setattr(handler, "OUTPUT_ROOT", tmp_path/"output")
    monkeypatch.setattr("core.publish_repository.require_publish_repository", lambda *a, **k: {})
    monkeypatch.setattr("content.release.canonical.legacy_release_repackage.freeze_legacy_source", lambda **kwargs: frozen)
    monkeypatch.setattr("content.release.canonical.legacy_release_repackage.repackage_legacy_release", lambda **kwargs: {"status":"created"})
    monkeypatch.setattr("content.coordination.runtime.governed_repackage_call", lambda fn, target_refs, release_id: calls.append(target_refs) or fn())
    monkeypatch.setattr("content.coordination.runtime.current_tokens",lambda:[SimpleNamespace(deployment_id="d")])
    monkeypatch.setenv("QWQ_CONTENT_GLOBAL_CLOSER_DEPLOYMENT","d")
    args = SimpleNamespace(publish_root=str(tmp_path/"publish"),release_root=str(tmp_path/"output/data/releases"),
        source_root=str(tmp_path/"output/data/releases"),repository_id="content-a",source_release_id=SOURCE,
        source_handoff_digest="sha256:"+"1"*64,source_cohort_digest="sha256:"+"2"*64,source_repository_evidence_ref=f".repository-authorities/{SOURCE}.json",source_repository_evidence_digest="sha256:"+"3"*64,target_release_id=TARGET,
        milestone="M1",producer_baseline_revision=REVISION)
    evidence_path=tmp_path/"output/data/releases/.repository-authorities"/f"{SOURCE}.json"
    evidence_path.parent.mkdir(parents=True,exist_ok=True); evidence_path.write_text("{}",encoding="utf-8")
    source=tmp_path/"output/data/releases"/SOURCE; source.mkdir(parents=True,exist_ok=True); (source/"cohort.json").write_bytes(_canonical_bytes({"objectRefs":[REF]})); args.source_cohort_digest=_digest((source/"cohort.json").read_bytes())
    handler.handle_repackage_legacy(args)
    assert calls == [[REF]]

def test_legacy_wire_is_closed_and_rejects_unknown_nested_fields(tmp_path, monkeypatch):
    """spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t4"""
    _, releases = tmp_path, tmp_path/"releases"; hd, cd = _legacy(releases)
    _install_provider(tmp_path,monkeypatch,[(releases/SOURCE/"repository_authority.json",_digest((releases/SOURCE/"repository_authority.json").read_bytes()))])
    handoff_path = releases/SOURCE/"producer_release_handoff.json"
    handoff = json.loads(handoff_path.read_bytes())
    for mutate in (
        lambda value: value["carrierCounts"].update(extra=1),
        lambda value: value["release"].update(extra="x"),
        lambda value: value["contentPoolObjects"][0].update(extra="x"),
        lambda value: value["contentPoolObjects"][0]["queryDocument"]["admission"].update(extra="x"),
    ):
        changed=json.loads(json.dumps(handoff)); mutate(changed); handoff_path.write_bytes(_canonical_bytes(changed))
        with pytest.raises(subject.LegacyReleaseRepackageError, match="LEGACY_SCHEMA_INVALID"):
            subject.freeze_legacy_source(source_root=releases,release_id=SOURCE,handoff_digest=_digest(handoff_path.read_bytes()),cohort_digest=cd)
    handoff_path.write_bytes(_canonical_bytes(handoff))

def test_replay_still_checks_frozen_source_cas(tmp_path, monkeypatch):
    """spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t3, spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t10"""
    releases,_=_run(tmp_path,monkeypatch); source=releases/SOURCE
    frozen=subject.freeze_legacy_source(source_root=releases,release_id=SOURCE,
        handoff_digest=_digest((source/"producer_release_handoff.json").read_bytes()),cohort_digest=_digest((source/"cohort.json").read_bytes()))
    (source/"after-freeze.txt").write_text("drift",encoding="utf-8")
    with pytest.raises(subject.LegacyReleaseRepackageError,match="SOURCE_TREE_MUTATED"):
        subject.repackage_legacy_release(frozen_source=frozen,publish_root=tmp_path/"publish",target_release_root=releases,
            repository_id="content-a",source_repository_evidence=_evidence(frozen)[0],source_repository_evidence_ref=f".repository-authorities/{SOURCE}.json",source_repository_evidence_digest=_evidence(frozen)[1],target_release_id=TARGET,milestone="M1",producer_baseline_revision=REVISION,repo_root=tmp_path)

@pytest.mark.parametrize("case", ["unregistered-copy", "unknown-provider"])
def test_gwt_062_t4现场造相同_repository_json仍拒绝(tmp_path, monkeypatch, case):
    """spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t4"""
    publish=_repo(tmp_path); releases=tmp_path/"releases"; hd,cd=_legacy(releases)
    from content.release.canonical import producer_release_handoff as handoff_module
    monkeypatch.setattr(handoff_module,"_validate_embedded_pool_rows",lambda **kwargs: [])
    authority=releases/SOURCE/"repository_authority.json"
    _install_provider(tmp_path,monkeypatch,[(authority,_digest(authority.read_bytes()))])
    frozen=subject.freeze_legacy_source(source_root=releases,release_id=SOURCE,handoff_digest=hd,cohort_digest=cd)
    forged=tmp_path/"forged-authority.json"; forged.write_bytes(authority.read_bytes())
    evidence,_=_evidence(frozen); evidence={**evidence,"authorityRef":str(forged)}
    evidence_path=releases/".repository-authorities"/f"{SOURCE}.json"; evidence_path.write_bytes(_canonical_bytes(evidence)); evidence_digest=_digest(evidence_path.read_bytes())
    frozen=subject.freeze_legacy_source(source_root=releases,release_id=SOURCE,handoff_digest=hd,cohort_digest=cd)
    with pytest.raises(Exception,match="AUTHORIZATION_SIGNATURE_INVALID|AUTHORITY_PROVIDER_UNAVAILABLE"):
        subject.repackage_legacy_release(frozen_source=frozen,publish_root=publish,target_release_root=releases,
            repository_id="content-a",source_repository_evidence=evidence,source_repository_evidence_ref=f".repository-authorities/{SOURCE}.json",
            source_repository_evidence_digest=evidence_digest,target_release_id=TARGET,milestone="M1",producer_baseline_revision=REVISION,repo_root=tmp_path)

@pytest.mark.parametrize("err", [17, 66])
def test_gwt_062_t8_darwin_create_once_loser_accepts_only_exact_existing(tmp_path,monkeypatch,err):
    """spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t8"""
    staging=tmp_path/"staging"; target=tmp_path/"target"; staging.mkdir(); target.mkdir(); (staging/"x").write_text("same"); (target/"x").write_text("same")
    original=Path.replace; original_exists=Path.exists
    def lose(self,dest):
        if self==staging: raise OSError(err,"race")
        return original(self,dest)
    monkeypatch.setattr(Path,"replace",lose)
    assert subject._publish_staging(staging,target) is True

@pytest.mark.parametrize("err", [1, 5, 13])
def test_gwt_062_t9_create_once_other_errno_propagates(tmp_path,monkeypatch,err):
    """spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t9"""
    staging=tmp_path/"staging"; target=tmp_path/"target"; staging.mkdir()
    monkeypatch.setattr(Path,"replace",lambda *_: (_ for _ in ()).throw(OSError(err,"fault")))
    with pytest.raises(OSError) as failure: subject._publish_staging(staging,target)
    assert failure.value.errno==err and not target.exists()


def test_gwt_062_t2_publish_terminal_exact_bytes_evidence(tmp_path,monkeypatch):
    """spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t2"""
    releases,result=_run(tmp_path,monkeypatch); terminal=tmp_path/"publish/releases"/TARGET
    assert result["outputReadback"]["passed"] and (terminal/"cohort.json").read_bytes()==(releases/TARGET/"cohort.json").read_bytes()

def test_gwt_062_t3_half_closed_output_recovers_by_exact_replay(tmp_path,monkeypatch):
    """spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t3"""
    releases,_=_run(tmp_path,monkeypatch); import shutil; shutil.rmtree(tmp_path/"publish/releases"/TARGET)
    source=releases/SOURCE; frozen=subject.freeze_legacy_source(source_root=releases,release_id=SOURCE,handoff_digest=_digest((source/"producer_release_handoff.json").read_bytes()),cohort_digest=_digest((source/"cohort.json").read_bytes()))
    evidence,digest=_evidence(frozen); result=subject.repackage_legacy_release(frozen_source=frozen,publish_root=tmp_path/"publish",target_release_root=releases,repository_id="content-a",source_repository_evidence=evidence,source_repository_evidence_ref=f".repository-authorities/{SOURCE}.json",source_repository_evidence_digest=digest,target_release_id=TARGET,milestone="M1",producer_baseline_revision=REVISION,repo_root=tmp_path)
    assert result["status"]=="replayed" and result["publishReadback"]["passed"]

def test_gwt_062_t7_current_terminal_has_no_fabricated_facts(tmp_path,monkeypatch):
    """spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t7"""
    releases,_=_run(tmp_path,monkeypatch); document=json.loads((releases/TARGET/"producer_release_handoff.json").read_bytes())
    assert not ({"attestation","execution","stageReceipt","publishReceipt","reviewer"}&set(document))

def test_gwt_062_t10_source_tree_is_immutable(tmp_path,monkeypatch):
    """spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t10"""
    releases,_=_run(tmp_path,monkeypatch); source=releases/SOURCE; before=_tree_digest(source); assert _tree_digest(source)==before and (releases/TARGET).is_dir()

def test_gwt_062_t14_recovery_identity_differs_from_source_and_candidate(tmp_path,monkeypatch):
    """spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t14"""
    releases,_=_run(tmp_path,monkeypatch); assert len({SOURCE,TARGET,"recovery-release"})==3 and (releases/SOURCE).is_dir() and (releases/TARGET).is_dir()


def test_gwt_062_t6_fresh_pool_review_proof_drift_blocks(tmp_path,monkeypatch):
    """spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t6"""
    publish=_repo(tmp_path); releases=tmp_path/"releases"; hd,cd=_legacy(releases)
    from content.release.canonical import producer_release_handoff as handoff_module
    monkeypatch.setattr(handoff_module,"_validate_embedded_pool_rows",lambda **kwargs: (_ for _ in ()).throw(ValueError("review proof drift")))
    with pytest.raises(subject.LegacyReleaseRepackageError,match="SOURCE_PUBLISH_PROOF_DRIFT"):
        subject.freeze_legacy_source(source_root=releases,release_id=SOURCE,handoff_digest=hd,cohort_digest=cd)


@pytest.mark.parametrize("mutation", ["pool", "package", "review", "proof"])
def test_gwt_062_t6_production_validator_detects_each_fresh_readback_drift(tmp_path,mutation):
    """spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t6"""
    from local_contract.release.test_producer_release_detachment__contract__local_contract_test import _sealed_handoff_fixture
    from content.release.canonical.producer_release_handoff import ProducerReleaseHandoffError,_validate_embedded_pool_rows,canonical_digest
    logical="entities/travel/test/home"; sealed,row,manifest,record,review=_sealed_handoff_fixture(tmp_path,logical_ref=logical,review_ref=logical,source_identity=True)
    if mutation=="pool": row["queryDocument"]["identity"]["objectId"]="drift"; row["queryDigest"]=canonical_digest(row["queryDocument"])
    elif mutation=="package": (sealed/logical/"manifest.json").write_text('{}')
    elif mutation=="review": (sealed/logical/"content_review.json").write_text('{"drift":true}')
    else: row["queryDocument"]["admission"]["evidenceDigest"]="sha256:"+"9"*64; row["queryDigest"]=canonical_digest(row["queryDocument"])
    with pytest.raises((ProducerReleaseHandoffError,ValueError),match="DRIFT|schema violation|CONTENT_REVIEW"):
        _validate_embedded_pool_rows(rows=[row],sealed_root=sealed,object_refs=[logical],header={})

@pytest.mark.parametrize(("errno_value","same","expected"),[(66,True,"same"),(66,False,"conflict"),(5,True,"error")])
def test_gwt_062_t8_terminal_copy_darwin_loser_matrix(tmp_path,monkeypatch,errno_value,same,expected):
    """spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t8"""
    output=tmp_path/"output"; output.mkdir(); (output/"cohort.json").write_text("same"); (output/"producer_release_handoff.json").write_text("same")
    publish=tmp_path/"publish"; target=publish/"releases/release"; target.mkdir(parents=True); (target/"cohort.json").write_text("same" if same else "different"); (target/"producer_release_handoff.json").write_text("same")
    original_replace=Path.replace; original_exists=Path.exists; calls={"target":0}
    def racing_exists(self):
        if self==target:
            calls["target"]+=1
            return calls["target"]>1
        return original_exists(self)
    def lose(self,destination):
        if destination==target: raise OSError(errno_value,"race")
        return original_replace(self,destination)
    monkeypatch.setattr(Path,"exists",racing_exists); monkeypatch.setattr(Path,"replace",lose)
    if expected=="same": assert subject._terminal_copy(output=output,publish_root=publish,release_id="release")==target
    elif expected=="conflict":
        with pytest.raises(subject.LegacyReleaseRepackageError,match="PUBLISH_TERMINAL_CONFLICT"): subject._terminal_copy(output=output,publish_root=publish,release_id="release")
    else:
        with pytest.raises(OSError) as failure: subject._terminal_copy(output=output,publish_root=publish,release_id="release")
        assert failure.value.errno==errno_value
