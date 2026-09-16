# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t6
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t10
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t14
"""同一 source legacy handoff 与不同 current target handoff 的真实文件/并发原子边界。"""
from __future__ import annotations

import concurrent.futures
import json
from pathlib import Path

from content.release.canonical import legacy_release_repackage as subject
from content.release.canonical.producer_release_handoff import _canonical_bytes, _digest
from local_contract.release.test_legacy_release_repackage__contract__local_contract_test import (
    REVISION, SOURCE, TARGET, _evidence, _install_provider, _legacy, _repo,
)

def _real_terminal_builder(*, publish: Path, repo_root: Path):
    def build(**kwargs):
        release = kwargs["release_root"] / kwargs["release_id"]
        (release / "payload").mkdir(parents=True, exist_ok=True)
        (release / "payload/release.json").write_bytes(b'{}\n')
        return {"status":"created"}
    def handoff(**kwargs):
        release = kwargs["release_root"] / kwargs["release_id"]
        cohort = json.loads(Path(kwargs["cohort_file"]).read_bytes())
        lineage = cohort["repackageLineage"]
        document = {"schema":"quwoquan_data.producer_release_handoff","repositoryId":"content-a","handoffId":kwargs["release_id"],
            "releaseId":kwargs["release_id"],"milestone":kwargs["milestone"],"carrierCounts":{"homepage":1,"article":0,"image":0,"video":0,"total":1},
            "release":{"scope":"output","ref":"data/releases/x","payloadDigest":"sha256:"+"1"*64,"headerRef":"data/releases/x/payload/release.json","headerDigest":"sha256:"+"2"*64},
            "explicitCohort":{"scope":"output","ref":"data/releases/x/cohort.json","digest":_digest(_canonical_bytes(cohort)),"document":cohort},
            "contentPoolObjects":[],"artifact":{"rootRef":"data/releases/x","entries":[],"treeDigest":"sha256:"+"3"*64},
            "producerBaselineRevision":REVISION,"producerContractDigest":"sha256:"+"4"*64,"repackageLineage":lineage}
        path=release/"producer_release_handoff.json"; path.write_bytes(_canonical_bytes(document)); return document,path,False
    return build, handoff

def test_real_source_and_distinct_current_handoff_coexist_and_create_once_has_one_winner(tmp_path, monkeypatch):
    """spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-062.t8"""
    publish=_repo(tmp_path); releases=tmp_path/"releases"; hd,cd=_legacy(releases)
    _install_provider(tmp_path,monkeypatch,[(releases/SOURCE/"repository_authority.json",_digest((releases/SOURCE/"repository_authority.json").read_bytes()))])
    from content.release.canonical import producer_release_handoff as handoff_module
    monkeypatch.setattr(handoff_module,"_validate_embedded_pool_rows",lambda **kwargs: [])
    frozen=subject.freeze_legacy_source(source_root=releases,release_id=SOURCE,handoff_digest=hd,cohort_digest=cd)
    build,handoff=_real_terminal_builder(publish=publish,repo_root=tmp_path)
    monkeypatch.setattr(subject,"build_pool_release",build); monkeypatch.setattr(subject,"write_producer_release_handoff",handoff)
    monkeypatch.setattr(subject,"assert_valid",lambda *a,**k: None)
    monkeypatch.setattr(subject,"read_producer_release_handoff",lambda path,**kwargs: json.loads(path.read_bytes()))
    source_bytes=(releases/SOURCE/"producer_release_handoff.json").read_bytes()
    def run():
        return subject.repackage_legacy_release(frozen_source=frozen,publish_root=publish,target_release_root=releases,
            repository_id="content-a",source_repository_evidence=_evidence(frozen)[0],source_repository_evidence_ref=f".repository-authorities/{SOURCE}.json",source_repository_evidence_digest=_evidence(frozen)[1],target_release_id=TARGET,milestone="M1",producer_baseline_revision=REVISION,repo_root=tmp_path)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        results=[future.result() for future in (executor.submit(run),executor.submit(run))]
    assert sorted(row["status"] for row in results)==["created","replayed"]
    assert len({row["outputHandoffDigest"] for row in results})==1
    assert (releases/SOURCE/"producer_release_handoff.json").read_bytes()==source_bytes
    target=json.loads((releases/TARGET/"producer_release_handoff.json").read_bytes())
    assert target["repackageLineage"]["sourceRepositoryId"]=="legacy-content"
    assert (publish/"releases"/TARGET/"producer_release_handoff.json").read_bytes()==(releases/TARGET/"producer_release_handoff.json").read_bytes()
