# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-004.t1
"""场景组：campaign capsule 只复制选中候选的 capsule 与 CAS。

从 test_scale_source_pool_homepage_article__catalog_projection__contract
__local_contract_test.py 按场景拆出；测试逐字搬移。
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from content.execution.campaign.external_input_runtime import (
    ExternalInputRuntimeContext,
    bind_runtime_external_input_context,
)
from content.execution.campaign.source_pool_binding import (
    _selected_evidence_refs,
    bind_scale_source_pool,
    materialize_bound_scale_source_pool,
    validate_capsule_scale_source_pool,
)
from content.source.research.auto_plan_writer import _write_auto_research_plans_impl
from content.source.research.scale_source_pool import (
    build_scale_source_pool_plan,
    validate_scale_source_pool_evidence,
)
from content.source.research.scale_source_pool_runtime import (
    ScaleSourcePoolRuntimeError,
    _frozen_homepage_media_inputs,
    frozen_scale_source_pool_candidates,
    frozen_scale_source_pool_targets,
    materialize_frozen_scale_source_pool_entity,
)
from core.carrier_contract import research_plan_files

from quwoquan_data.tests.local_contract.source.test_media_source_admission__portable_bridge__contract__local_contract_test import (
    _admit,
)
from support.scale_source_pool_catalog_fixture import (
    IDENTITY,
    _article_candidate,
    _document_digest,
    _homepage_candidate,
    _write_json,
)
from support.scale_source_pool_projection_fixture import (
    _clone_row,
    _project,
)


def test_campaign_capsule_collects_media_admission_receipt_evidence_and_asset_bytes(
    tmp_path: Path,
) -> None:
    candidates = []
    expected_refs: set[str] = set()
    for carrier in ("image", "video"):
        receipt, receipt_ref, _ = _admit(tmp_path, kind=carrier)
        candidates.append(
            {
                "carrier": carrier,
                "objectRef": receipt["objectRef"],
                "sourceAdmissionRef": receipt_ref,
                "sourceAdmissionDigest": receipt["receiptDigest"],
            }
        )
        expected_refs.add(receipt_ref)
        expected_refs.add(str(receipt["assetSnapshot"]["assetRef"]))
        expected_refs.update(
            str(binding["ref"]) for binding in receipt["evidenceBindings"]
        )

    refs = _selected_evidence_refs(candidates, evidence_root=tmp_path)

    assert set(refs) == expected_refs
    assert all(value.startswith("sha256:") for value in refs.values())


def test_article_workload_campaign_capsule_copies_nested_raw_evidence(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    evidence_root = output_root / "evidence"
    projection = _project(
        evidence_root,
        homepage_candidates=[_homepage_candidate(0)],
        article_candidates=[_article_candidate(0), _article_candidate(1)],
        per_member_roots=True,
    )
    article_rows = [
        copy.deepcopy(row)
        for row in projection["rows"]
        if row["carrier"] == "article"
    ]
    plan = build_scale_source_pool_plan(
        pool_id="article-workload-raw-evidence",
        target_scale="WORKLOAD",
        created_at="2026-08-08T00:00:00Z",
        candidates=article_rows,
        workload_targets={"article": 1},
        source_revision=IDENTITY["sourceRevision"],
        source_digest=IDENTITY["sourceDigest"],
        entity_catalog_digest=IDENTITY["entityCatalogDigest"],
    )
    plan_path = output_root / "pool/plan.json"
    _write_json(plan_path, plan)
    binding, evidence_ref, selection = bind_scale_source_pool(
        plan_path,
        evidence_root=evidence_root,
        output_root=output_root,
        target_scale="WORKLOAD",
        carrier="article",
        count=1,
        source_revision=IDENTITY["sourceRevision"],
        source_digest=IDENTITY["sourceDigest"],
        entity_catalog_digest=IDENTITY["entityCatalogDigest"],
    )
    snapshot_root = tmp_path / "capsule/scale-source-pool"
    snapshot_digest = materialize_bound_scale_source_pool(
        binding,
        evidence_root_ref=evidence_ref,
        output_root=output_root,
        destination=snapshot_root,
        lane_selections={"article": selection},
    )
    validate_capsule_scale_source_pool(
        binding,
        snapshot_root=snapshot_root,
        lane_selections={"article": selection},
        expected_snapshot_digest=snapshot_digest,
    )

    selected_id = str(selection["candidateIds"][0])
    unselected_id = next(
        str(row["candidateId"])
        for row in article_rows
        if row["candidateId"] != selected_id
    )
    selected_raw = (
        snapshot_root
        / "evidence"
        / "members"
        / "article"
        / selected_id
        / "raw"
        / "article"
        / f"{selected_id}.json"
    )
    assert selected_raw.is_file()
    assert not any(
        unselected_id in path.as_posix()
        for path in (snapshot_root / "evidence").rglob("*")
    )


def test_campaign_capsule_copies_only_selected_candidate_capsules_and_cas(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "output"
    evidence_root = output_root / "evidence"
    projection = _project(
        evidence_root,
        homepage_candidates=[_homepage_candidate(0), _homepage_candidate(1)],
        article_candidates=[_article_candidate(0), _article_candidate(1)],
        per_member_roots=True,
    )
    rows = {
        (row["carrier"], row["candidateId"]): row for row in projection["rows"]
    }
    homepage_rows = [
        copy.deepcopy(rows[("homepage", f"homepage-west-lake-{index}")])
        for index in range(2)
    ]
    article_rows = [
        copy.deepcopy(rows[("article", f"article-hangzhou-{index}")])
        for index in range(2)
    ]
    candidates = [*homepage_rows, *article_rows]
    candidates.extend(
        _clone_row(homepage_rows[0], carrier="homepage", index=index, provider="维基百科")
        for index in range(2, 180)
    )
    candidates.extend(
        _clone_row(article_rows[0], carrier="article", index=index, provider="Wikivoyage")
        for index in range(2, 180)
    )
    image_providers = (
        ["Pinterest"] * 80 + ["图虫"] * 20
        + ["Pexels"] * 50 + ["Wikimedia Commons"] * 30
    )
    candidates.extend(
        _clone_row(
            article_rows[0],
            carrier="image",
            index=index,
            provider=provider,
            evidence_root=evidence_root,
        )
        for index, provider in enumerate(image_providers)
    )
    candidates.extend(
        _clone_row(
            article_rows[0],
            carrier="video",
            index=index,
            provider="Pexels Videos",
            evidence_root=evidence_root,
        )
        for index in range(18)
    )
    plan = build_scale_source_pool_plan(
        pool_id="selected-only-physical-pool",
        target_scale="M100",
        created_at="2026-08-08T00:00:00Z",
        candidates=candidates,
        **{
            "source_revision": IDENTITY["sourceRevision"],
            "source_digest": IDENTITY["sourceDigest"],
            "entity_catalog_digest": IDENTITY["entityCatalogDigest"],
        },
    )
    plan_path = output_root / "pool/plan.json"
    _write_json(plan_path, plan)
    selections: dict[str, dict[str, object]] = {}
    evidence_ref = ""
    binding: dict[str, object] | None = None
    for carrier in ("homepage", "article", "image", "video"):
        lane_binding, lane_evidence_ref, selection = bind_scale_source_pool(
            plan_path,
            evidence_root=evidence_root,
            output_root=output_root,
            target_scale="M100",
            carrier=carrier,
            count=1,
            source_revision=IDENTITY["sourceRevision"],
            source_digest=IDENTITY["sourceDigest"],
            entity_catalog_digest=IDENTITY["entityCatalogDigest"],
        )
        binding = lane_binding
        evidence_ref = lane_evidence_ref
        selections[carrier] = selection
    for carrier, candidate_id in (
        ("homepage", "homepage-west-lake-0"),
        ("article", "article-hangzhou-0"),
    ):
        stable_selection = {
            "carrier": carrier,
            "candidateIds": [candidate_id],
            "candidateCount": 1,
        }
        selections[carrier] = {
            **stable_selection,
            "selectionDigest": _document_digest(stable_selection),
        }
    assert binding is not None
    snapshot_root = tmp_path / "capsule/scale-source-pool"
    snapshot_digest = materialize_bound_scale_source_pool(
        binding,
        evidence_root_ref=evidence_ref,
        output_root=output_root,
        destination=snapshot_root,
        lane_selections=selections,
    )
    validate_capsule_scale_source_pool(
        binding,
        snapshot_root=snapshot_root,
        lane_selections=selections,
        expected_snapshot_digest=snapshot_digest,
    )
    copied = {
        path.relative_to(snapshot_root / "evidence").as_posix()
        for path in (snapshot_root / "evidence").rglob("*")
        if path.is_file()
    }
    homepage_member = "members/homepage/homepage-west-lake-0"
    article_member = "members/article/article-hangzhou-0"
    assert f"{homepage_member}/capsule.json" in copied
    assert f"{article_member}/capsule.json" in copied
    assert f"{homepage_member}/provenance/discovery.json" in copied
    assert f"{article_member}/provenance/discovery.json" in copied
    assert f"{homepage_member}/raw/homepage/homepage-west-lake-0.json" in copied
    assert f"{article_member}/raw/article/article-hangzhou-0.json" in copied
    assert "members/homepage/homepage-west-lake-1/capsule.json" not in copied
    assert "members/article/article-hangzhou-1/capsule.json" not in copied
    assert not any("west-lake-1" in ref or "hangzhou-1" in ref for ref in copied)

    empty_digest = "sha256:" + "0" * 64
    capsule_root = snapshot_root.parent
    lane_inputs = {
        carrier: {
            "rootRef": f"external-inputs/{carrier}",
            "externalInputRefs": [],
            "externalInputsDigest": empty_digest,
        }
        for carrier in ("homepage", "article", "image", "video")
    }
    _write_json(
        capsule_root / ".qwq_campaign_capsule.json",
        {
            "schema": "quwoquan_data.content_campaign_source_capsule",
            "format": "source-capsule-v2",
            "gitBranch": "main",
            "gitCommitSha": "a" * 40,
            **IDENTITY,
            "executionBundle": {
                "algorithm": "sha256",
                "digest": "sha256:" + "f" * 64,
                "inputs": ["quwoquan_data/scripts"],
            },
            "roots": ["quwoquan_data"],
            "laneExternalInputs": lane_inputs,
            "externalInputsDigest": empty_digest,
            "scaleSourcePool": binding,
            "sourcePoolSnapshotRootRef": "scale-source-pool",
            "sourcePoolSnapshotDigest": snapshot_digest,
            "laneSourcePoolSelections": selections,
            "capsuleDigest": "sha256:" + "b" * 64,
            "treeDigest": "sha256:" + "c" * 64,
        },
    )
    monkeypatch.setattr(
        "content.source.research.scale_source_pool_runtime._frozen_homepage_media_inputs",
        lambda **_kwargs: (
            {
                "schema": "quwoquan_data.source_layout",
                "sourceKind": "wikipedia",
                "extractor": "wikipedia_api",
                "title": "西湖-0",
                "parseStatus": "ok",
                "rejectReason": "",
                "blocks": [
                    {
                        "type": "figure",
                        "figureId": "fig_001",
                        "sourceOrder": 0,
                        "fileTitle": "west-lake-hero-0.jpg",
                        "caption": "西湖-0湖景",
                        "sectionSlug": "",
                        "groupId": "",
                        "placementType": "infoboxLead",
                        "coverCandidateRank": 1,
                        "isMapLike": False,
                        "paragraphIndex": 0,
                    }
                ],
                "figureCount": 1,
                "tables": [],
            },
            {
                "hero-0": {
                    "fileName": "west-lake-hero-0.jpg",
                    "caption": "西湖-0湖景",
                    "placementType": "infoboxLead",
                    "sourceOrder": 0,
                    "coverCandidateRank": 1,
                    "pageResolvedTitle": "西湖-0",
                    "pageId": 1,
                    "pageRevisionId": 1,
                }
            },
            {
                "candidateCount": 1,
                "keptCount": 1,
                "droppedCount": 0,
                "dedupeRemoved": 0,
                "drops": [],
                "fetchFailures": [],
            },
        ),
    )
    for carrier in ("homepage", "article"):
        execution_id = f"20260808--travel-{carrier}-m100--china--scale-991"
        bind_runtime_external_input_context(
            ExternalInputRuntimeContext(
                root=capsule_root / f"external-inputs/{carrier}",
                envelope={"executionId": execution_id, "carrier": carrier},
                refs=(),
                blob_refs_by_digest={},
                capsule_root=capsule_root,
            )
        )
        resolved = frozen_scale_source_pool_candidates(execution_id, carrier)
        targets = frozen_scale_source_pool_targets(execution_id, carrier)
        assert [row["candidateId"] for row in resolved] == [
            selections[carrier]["candidateIds"][0]
        ]
        assert len(targets) == 1
        assert targets[0]["entityType"] == "地点/景区"
        if carrier == "homepage":
            assert targets[0]["qualifiedHomepageSource"]["provider"] == "wikipedia"
        execution_root = tmp_path / "tasks" / execution_id
        monkeypatch.setattr(
            "content.source.research.scale_source_pool_runtime.resolve_entity_object_dir",
            lambda _execution_id, name, etype_hint="": (
                execution_root / "entities" / Path(etype_hint) / name
            ),
        )
        monkeypatch.setattr(
            "content.source.source_unit_writer.execution_source_unit_dir",
            lambda _execution_id, source_unit_id: execution_root
            / "sources"
            / source_unit_id,
        )
        monkeypatch.setattr(
            "content.source.source_unit_writer.stage_execution_context",
            lambda _execution_id: {
                "executionId": execution_id,
                "executionBinding": "frozen",
            },
        )
        monkeypatch.setattr(
            "content.source.source_unit_writer.relative_execution_ref",
            lambda path, _execution_id: path.relative_to(execution_root).as_posix(),
        )
        spec = {
            "scope": {"coverageTargets": [dict(targets[0])]},
            "executionPolicy": {"scaleSourcePool": binding},
        }
        monkeypatch.setattr(
            "content.execution.store.load_spec", lambda _execution_id: spec
        )
        plan_path = (
            execution_root
            / "entities"
            / Path(targets[0]["entityType"])
            / targets[0]["name"]
            / "1.download"
            / research_plan_files()[carrier]
        )

        def prepare_plan(_execution_id: str, _entities: list[dict[str, object]]) -> Path:
            _write_json(plan_path, {"payload": {}})
            return plan_path

        monkeypatch.setattr(
            "content.source.research.auto_plan_writer.prepare_source_plan",
            prepare_plan,
        )
        monkeypatch.setattr(
            "content.source.research.auto_plan_writer.discover_homepage_authority",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("frozen source-pool runtime must not discover online")
            ),
        )
        report = _write_auto_research_plans_impl(
            execution_id,
            [targets[0]["name"]],
            entity_type=targets[0]["entityType"],
            lanes={carrier},
            write_shared_report=False,
        )
        assert report["selectionAuthority"] == "frozen_scale_source_pool"
        assert json.loads(plan_path.read_text(encoding="utf-8"))["payload"][
            "runtimeInputAuthority"
        ] == (
            "frozen_scale_source_pool"
        )
        manifest = materialize_frozen_scale_source_pool_entity(
            execution_id,
            carrier,
            targets[0]["name"],
            targets[0]["entityType"],
        )
        assert manifest is not None
        unit = execution_root / "sources" / manifest["sourceUnitId"]
        assert (unit / "source.md").is_file()
        assert (unit / "assets/index.json").is_file()
        assert manifest["assetCount"] >= 1
        if carrier == "homepage":
            assert manifest["imagePlacements"] == [
                {
                    "fileName": "west-lake-hero-0.jpg",
                    "caption": "西湖-0湖景",
                    "sectionSlug": "",
                    "paragraphIndex": 0,
                    "sourceOrder": 0,
                    "placementType": "infoboxLead",
                    "groupId": "",
                    "coverCandidateRank": 1,
                    "placeholderId": "source-inline-001",
                    "subjectKey": "西湖0湖景",
                    "isMapLike": False,
                }
            ]
            assert manifest["assetFunnel"] == {
                "candidateCount": 1,
                "keptCount": 1,
                "droppedCount": 0,
                "dedupeRemoved": 0,
                "drops": [],
                "fetchFailures": [],
            }
            index = json.loads(
                (unit / "assets/index.json").read_text(encoding="utf-8")
            )
            assert index["assets"][0]["placementType"] == "infoboxLead"
            assert index["assets"][0]["pageRevisionId"] == 1
        assert materialize_frozen_scale_source_pool_entity(
            execution_id,
            carrier,
            targets[0]["name"],
            targets[0]["entityType"],
        ) == manifest
        (unit / "source.md").write_text("tampered", encoding="utf-8")
        with pytest.raises(
            ScaleSourcePoolRuntimeError, match="existing frozen source unit"
        ):
            materialize_frozen_scale_source_pool_entity(
                execution_id,
                carrier,
                targets[0]["name"],
                targets[0]["entityType"],
            )

    def with_member_root(value: str) -> dict[str, object]:
        drifted = copy.deepcopy(plan)
        for candidate in drifted["candidates"]:
            if candidate["candidateId"] == "homepage-west-lake-0":
                candidate["sourceReadyEvidenceRootRef"] = value
                break
        stable = {
            key: item for key, item in drifted.items() if key != "planDigest"
        }
        drifted["planDigest"] = _document_digest(stable)
        return drifted

    wrong_member = "members/homepage/homepage-west-lake-1"
    with pytest.raises(ValueError, match="FileSha256 drift"):
        validate_scale_source_pool_evidence(
            with_member_root(wrong_member),
            evidence_root=evidence_root,
        )

    symlink_ref = "members/homepage/symlink-member"
    (evidence_root / symlink_ref).symlink_to(
        evidence_root / homepage_member,
        target_is_directory=True,
    )
    with pytest.raises(ValueError, match="must not traverse a symlink"):
        validate_scale_source_pool_evidence(
            with_member_root(symlink_ref),
            evidence_root=evidence_root,
        )

    homepage_capsule = evidence_root / homepage_member / "capsule.json"
    homepage_capsule.write_bytes(homepage_capsule.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="FileSha256 drift"):
        validate_scale_source_pool_evidence(plan, evidence_root=evidence_root)
