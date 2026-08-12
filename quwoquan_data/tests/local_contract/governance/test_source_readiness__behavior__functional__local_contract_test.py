from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest


def _write_candidates(path: Path) -> Path:
    rows = [
        {
            "name": "西湖",
            "canonicalName": "西湖",
            "province": "浙江省",
            "city": "杭州市",
            "district": "西湖区",
            "source": "master_list",
            "typeTagRefs": ["Entity/地点/自然景观/水体"],
        },
        {
            "name": "西湖",
            "province": "浙江省",
            "city": "杭州市",
            "district": "西湖区",
            "source": "osm_poi",
            "identityRefs": {"osmType": "way", "osmId": "1"},
            "coordinates": {"lat": 30.24, "lon": 120.14},
            "typeTagRefs": ["Entity/地点/自然景观/水体"],
        },
        {
            "name": "九寨沟",
            "province": "四川省",
            "city": "阿坝藏族羌族自治州",
            "district": "九寨沟县",
            "source": "osm_poi",
            "identityRefs": {"osmType": "relation", "osmId": "2"},
            "coordinates": {"lat": 33.26, "lon": 103.92},
            "typeTagRefs": ["Entity/地点/景区/自然保护区"],
        },
    ]
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    return path


def _exact_master_rows() -> list[dict[str, object]]:
    return [
        {
            "name": "黄龙",
            "canonicalName": "黄龙风景名胜区",
            "province": "四川省",
            "city": "阿坝藏族羌族自治州",
            "district": "松潘县",
            "source": "master_list",
            "typeTagRefs": ["Entity/地点/景区/5A景区"],
        },
        {
            "name": "西湖",
            "canonicalName": "西湖",
            "province": "浙江省",
            "city": "杭州市",
            "district": "西湖区",
            "source": "master_list",
            "typeTagRefs": ["Entity/地点/自然景观/水体"],
        },
    ]


def _qualified_result(mod, candidate, *, sources, qualified=True):
    return {
        "schema": "quwoquan_data.source_ready_candidate",
        "identityKey": mod._readiness_key(candidate),
        "candidate": candidate,
        "attemptedSources": list(sources),
        "qualified": qualified,
        **(
            {
                "evidence": {
                    "sourceKind": "wikipedia",
                    "extractor": "wikipedia_api",
                    "canonicalUrl": "https://zh.wikipedia.org/wiki/test",
                    "resolvedTitle": str(candidate["canonicalName"]),
                    "matchConfidence": 0.95,
                }
            }
            if qualified
            else {}
        ),
        "qualifiedAt": "2026-08-12T00:00:00Z",
    }


def test_source_readiness_dedupes_locations_and_resumes_without_duplicate_rows(
    monkeypatch,
    tmp_path,
):
    import governance.coverage.source_readiness as mod

    candidate_file = _write_candidates(tmp_path / "candidates.ndjson")
    workspace = tmp_path / "workspace"

    class _Digest:
        @staticmethod
        def to_document():
            return {
                "algorithm": "sha256",
                "digest": "sha256:" + "1" * 64,
                "inputs": ["test"],
            }

    monkeypatch.setattr(mod, "coverage_workspace_root", lambda: workspace)
    monkeypatch.setattr(mod, "current_source_definition_snapshot", lambda: _Digest())
    monkeypatch.setattr(
        mod,
        "_qualify_candidate",
        lambda candidate, *, sources: {
            "schema": "quwoquan_data.source_ready_candidate",
            "identityKey": mod._readiness_key(candidate),
            "candidate": candidate,
            "attemptedSources": list(sources),
            "qualified": True,
            "evidence": {
                "sourceKind": "wikipedia",
                "extractor": "wikipedia_api",
                "canonicalUrl": "https://zh.wikipedia.org/wiki/test",
                "resolvedTitle": candidate["name"],
                "matchConfidence": 0.95,
            },
            "qualifiedAt": "2026-07-20T00:00:00Z",
        },
    )

    first = mod.qualify_source_ready_candidates(
        run_id="source-ready-test",
        provinces=["浙江省", "四川省"],
        candidate_files=[candidate_file],
        sources=["wikipedia"],
        minimum_per_province=1,
        include_master_list=False,
        exhaust_input=False,
        resume=False,
    )
    second = mod.qualify_source_ready_candidates(
        run_id="source-ready-test",
        provinces=["浙江省", "四川省"],
        candidate_files=[candidate_file],
        sources=["wikipedia"],
        minimum_per_province=1,
        include_master_list=False,
        exhaust_input=False,
        resume=True,
    )

    assert first["decision"] == second["decision"] == "GO"
    assert first["inputUniqueByProvince"] == {"浙江省": 1, "四川省": 1}
    ready_path = Path(first["outputs"]["ready"])
    assert len(ready_path.read_text(encoding="utf-8").splitlines()) == 2
    assert first["frozenByProvince"] == {"浙江省": 1, "四川省": 1}


def test_balanced_freeze_round_robins_district_type_cells():
    import governance.coverage.source_readiness as mod

    rows = []
    for index, (district, type_ref) in enumerate(
        (
            ("西湖区", "Entity/地点/博物馆"),
            ("西湖区", "Entity/地点/公园"),
            ("余杭区", "Entity/地点/博物馆"),
            ("余杭区", "Entity/地点/公园"),
            ("西湖区", "Entity/地点/博物馆"),
        ),
        start=1,
    ):
        rows.append(
            {
                "schema": "quwoquan_data.source_ready_candidate",
                "identityKey": f"name_location:对象{index}|浙江省|杭州市|{district}",
                "candidate": {
                    "name": f"对象{index}",
                    "province": "浙江省",
                    "city": "杭州市",
                    "district": district,
                    "typeTagRefs": [type_ref],
                },
                "attemptedSources": ["wikipedia"],
                "qualified": True,
                "evidence": {
                    "sourceKind": "wikipedia",
                    "extractor": "wikipedia_api",
                    "canonicalUrl": "https://zh.wikipedia.org/wiki/test",
                    "resolvedTitle": f"对象{index}",
                    "matchConfidence": 0.95,
                },
                "qualifiedAt": "2026-07-20T00:00:00Z",
            }
        )

    frozen, covered = mod._balanced_frozen_targets(
        rows,
        provinces=["浙江省"],
        minimum_per_province=4,
    )

    assert len(frozen) == 4
    assert covered == {"浙江省": 4}
    assert [row["selection"]["provinceRank"] for row in frozen] == [1, 2, 3, 4]


def test_exhaustive_balanced_freeze_keeps_all_qualified_rows_in_same_cell():
    import governance.coverage.source_readiness as mod

    rows = []
    for index in range(8):
        rows.append(
            {
                "schema": "quwoquan_data.source_ready_candidate",
                "identityKey": f"name_location:对象{index}|浙江省|杭州市|西湖区",
                "candidate": {
                    "name": f"对象{index}",
                    "province": "浙江省",
                    "city": "杭州市",
                    "district": "西湖区",
                    "typeTagRefs": ["Entity/地点/博物馆"],
                },
                "attemptedSources": ["wikipedia"],
                "qualified": True,
                "evidence": {
                    "sourceKind": "wikipedia",
                    "extractor": "wikipedia_api",
                    "canonicalUrl": "https://zh.wikipedia.org/wiki/test",
                    "resolvedTitle": f"对象{index}",
                    "matchConfidence": 0.95,
                },
                "qualifiedAt": "2026-08-12T00:00:00Z",
            }
        )

    frozen, covered = mod._balanced_frozen_targets(
        list(reversed(rows)),
        provinces=["浙江省"],
        minimum_per_province=2,
        freeze_all=True,
    )

    assert len(frozen) == 8
    assert covered == {"浙江省": 1}
    assert [row["identityKey"] for row in frozen] == sorted(
        row["identityKey"] for row in rows
    )
    assert [row["selection"]["provinceRank"] for row in frozen] == list(
        range(1, 9)
    )


def test_wikipedia_candidate_resolves_location_and_reuses_readable_evidence():
    import governance.coverage.source_readiness as mod

    candidates = mod._dedupe_candidates(
        [
            {
                "name": "中国湿地博物馆",
                "province": "浙江省",
                "source": "wiki_category",
                "identityRefs": {"qid": "Q22100874", "wikipediaPageId": 1},
                "typeTagRefs": ["Entity/地点/博物馆"],
                "extract": "中国湿地博物馆位于浙江省杭州市西湖区。",
            }
        ],
        provinces=["浙江省"],
    )

    assert len(candidates) == 1
    assert candidates[0]["city"] == "杭州市"
    assert candidates[0]["district"] == "西湖区"
    evidence = mod._wikipedia_evidence(candidates[0])
    assert evidence is not None
    assert evidence["sourceKind"] == "wikipedia"
    assert evidence["matchConfidence"] == 1.0


def test_wikipedia_discovery_candidate_resolves_location_and_reuses_fetch_evidence(
    monkeypatch,
):
    import governance.coverage.source_readiness as mod
    import governance.coverage.source_readiness_candidates as candidates_mod

    candidates = mod._dedupe_candidates(
        [
            {
                "name": "中国湿地博物馆",
                "province": "浙江省",
                "source": "wiki_category",
                "identityRefs": {"qid": "Q22100874", "wikipediaPageId": 123},
                "typeTagRefs": ["Entity/地点/博物馆"],
                "extract": "中国湿地博物馆位于浙江省杭州市西湖区。",
                "categories": ["Category:浙江省的博物馆"],
            }
        ],
        provinces=["浙江省"],
    )
    monkeypatch.setattr(
        candidates_mod.network_io,
        "wiki_api",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("已下载的 Wikipedia 证据不得重复抓取")
        ),
    )

    assert len(candidates) == 1
    assert candidates[0]["city"] == "杭州市"
    assert candidates[0]["district"] == "西湖区"
    evidence = mod._wikipedia_evidence(candidates[0])
    assert evidence is not None
    assert evidence["sourceKind"] == "wikipedia"


def test_exact_master_targets_freeze_only_ordered_refs_and_use_canonical_name(
    monkeypatch,
    tmp_path,
):
    import governance.coverage.source_readiness as mod
    import governance.coverage.source_readiness_candidates as candidates_mod

    workspace = tmp_path / "workspace"
    requested = [
        "/entity/地点/景区/黄龙风景名胜区",
        "/entity/地点/自然景观/西湖",
    ]
    qualified_refs: list[str] = []

    class _Digest:
        @staticmethod
        def to_document():
            return {
                "algorithm": "sha256",
                "digest": "sha256:" + "5" * 64,
                "inputs": ["test"],
            }

    monkeypatch.setattr(candidates_mod, "_master_candidates", lambda _p: _exact_master_rows())
    monkeypatch.setattr(mod, "coverage_workspace_root", lambda: workspace)
    monkeypatch.setattr(mod, "current_source_definition_snapshot", lambda: _Digest())

    def qualify(candidate, *, sources):
        qualified_refs.append(str(candidate["canonicalEntityRef"]))
        return _qualified_result(mod, candidate, sources=sources)

    monkeypatch.setattr(mod, "_qualify_candidate", qualify)
    report = mod.qualify_source_ready_candidates(
        run_id="exact-source-ready",
        provinces=["四川省", "浙江省"],
        candidate_files=[tmp_path / "ignored-missing.ndjson"],
        sources=["wikipedia"],
        minimum_per_province=100,
        include_master_list=False,
        exhaust_input=False,
        resume=False,
        required_entity_refs=requested,
    )

    manifest = json.loads(
        (workspace / "source-readiness" / "exact-source-ready" / "manifest.json")
        .read_text(encoding="utf-8")
    )
    frozen = [
        json.loads(line)
        for line in Path(report["outputs"]["frozenTargets"])
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert qualified_refs == requested
    assert manifest["requiredEntityRefs"] == requested
    assert manifest["candidateFiles"] == []
    assert manifest["includeMasterList"] is True
    assert manifest["exhaustInput"] is True
    assert report["requiredEntityRefs"] == requested
    assert report["frozenEntityRefs"] == requested
    assert report["missingRequiredEntityRefs"] == []
    assert report["belowMinimum"] == {}
    assert report["decision"] == "GO"
    assert [row["candidate"]["canonicalName"] for row in frozen] == [
        "黄龙风景名胜区",
        "西湖",
    ]
    assert frozen[0]["candidate"]["name"] == "黄龙"
    assert [row["candidate"]["canonicalEntityRef"] for row in frozen] == requested


def test_exact_master_target_shortfall_is_not_masked_by_province_minimum(
    monkeypatch,
    tmp_path,
):
    import governance.coverage.source_readiness as mod
    import governance.coverage.source_readiness_candidates as candidates_mod

    requested = [
        "/entity/地点/景区/黄龙风景名胜区",
        "/entity/地点/自然景观/西湖",
    ]

    class _Digest:
        @staticmethod
        def to_document():
            return {
                "algorithm": "sha256",
                "digest": "sha256:" + "6" * 64,
                "inputs": ["test"],
            }

    monkeypatch.setattr(candidates_mod, "_master_candidates", lambda _p: _exact_master_rows())
    monkeypatch.setattr(mod, "coverage_workspace_root", lambda: tmp_path / "workspace")
    monkeypatch.setattr(mod, "current_source_definition_snapshot", lambda: _Digest())
    monkeypatch.setattr(
        mod,
        "_qualify_candidate",
        lambda candidate, *, sources: _qualified_result(
            mod,
            candidate,
            sources=sources,
            qualified=candidate["canonicalName"] != "黄龙风景名胜区",
        ),
    )

    report = mod.qualify_source_ready_candidates(
        run_id="exact-source-shortfall",
        provinces=["四川省", "浙江省"],
        candidate_files=[],
        sources=["wikipedia"],
        minimum_per_province=1,
        include_master_list=False,
        exhaust_input=False,
        resume=False,
        required_entity_refs=requested,
    )

    assert report["decision"] == "NO_GO"
    assert report["belowMinimum"] == {}
    assert report["frozenEntityRefs"] == [requested[1]]
    assert report["missingRequiredEntityRefs"] == [requested[0]]

    import governance.coverage.handler as handler_mod

    monkeypatch.setattr(mod, "qualify_source_ready_candidates", lambda **_kwargs: report)
    args = argparse.Namespace(
        provinces="四川省,浙江省",
        candidates=None,
        required_entity_ref=requested,
        include_master_list=False,
        sources="wikipedia",
        minimum_per_province=1,
        run_id="exact-source-shortfall",
        exhaust_input=False,
        resume=False,
    )
    with pytest.raises(SystemExit) as captured:
        handler_mod.handle_coverage_source_ready(args)
    assert "DATA.SOURCE.POOL_SHORTFALL" in str(captured.value)
    assert requested[0] in str(captured.value)


@pytest.mark.parametrize(
    ("required_refs", "master_rows", "issue"),
    [
        (["/entity/地点/景区"], _exact_master_rows(), "malformed"),
        (
            [
                "/entity/地点/景区/黄龙风景名胜区",
                "/entity/地点/景区/黄龙风景名胜区",
            ],
            _exact_master_rows(),
            "duplicate",
        ),
        (
            ["/entity/地点/景区/黄龙风景名胜区"],
            _exact_master_rows(),
            "outside selected provinces",
        ),
        (["/entity/地点/景区/不存在"], _exact_master_rows(), "missing"),
        (
            ["/entity/地点/景区/黄龙风景名胜区"],
            [_exact_master_rows()[0], dict(_exact_master_rows()[0])],
            "ambiguous",
        ),
    ],
)
def test_exact_target_preflight_rejects_invalid_refs_before_workspace_or_network(
    monkeypatch,
    required_refs,
    master_rows,
    issue,
):
    import governance.coverage.source_readiness as mod
    import governance.coverage.source_readiness_candidates as candidates_mod

    monkeypatch.setattr(candidates_mod, "_master_candidates", lambda _p: master_rows)
    monkeypatch.setattr(
        mod,
        "coverage_workspace_root",
        lambda: (_ for _ in ()).throw(AssertionError("run dir must not be resolved")),
    )
    monkeypatch.setattr(
        mod,
        "current_source_definition_snapshot",
        lambda: (_ for _ in ()).throw(AssertionError("source digest must not run")),
    )
    monkeypatch.setattr(
        mod,
        "_qualify_candidate",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("network qualification must not run")
        ),
    )
    provinces = ["浙江省"] if issue == "outside selected provinces" else ["四川省", "浙江省"]

    with pytest.raises(candidates_mod.SourceReadinessTargetError) as captured:
        mod.qualify_source_ready_candidates(
            run_id="exact-preflight",
            provinces=provinces,
            candidate_files=[],
            sources=["wikipedia"],
            minimum_per_province=1,
            include_master_list=False,
            exhaust_input=False,
            resume=False,
            required_entity_refs=required_refs,
        )
    assert captured.value.code == "DATA.SOURCE.INVALID_TARGET"
    assert issue in str(captured.value)


def test_exact_target_resume_rejects_order_drift_before_network(
    monkeypatch,
    tmp_path,
):
    import governance.coverage.source_readiness as mod
    import governance.coverage.source_readiness_candidates as candidates_mod

    requested = [
        "/entity/地点/景区/黄龙风景名胜区",
        "/entity/地点/自然景观/西湖",
    ]

    class _Digest:
        @staticmethod
        def to_document():
            return {
                "algorithm": "sha256",
                "digest": "sha256:" + "7" * 64,
                "inputs": ["test"],
            }

    monkeypatch.setattr(candidates_mod, "_master_candidates", lambda _p: _exact_master_rows())
    monkeypatch.setattr(mod, "coverage_workspace_root", lambda: tmp_path / "workspace")
    monkeypatch.setattr(mod, "current_source_definition_snapshot", lambda: _Digest())
    monkeypatch.setattr(
        mod,
        "_qualify_candidate",
        lambda candidate, *, sources: _qualified_result(mod, candidate, sources=sources),
    )
    kwargs = {
        "run_id": "exact-resume-order",
        "provinces": ["四川省", "浙江省"],
        "candidate_files": [],
        "sources": ["wikipedia"],
        "minimum_per_province": 1,
        "include_master_list": False,
        "exhaust_input": False,
        "required_entity_refs": requested,
    }
    mod.qualify_source_ready_candidates(**kwargs, resume=False)
    monkeypatch.setattr(
        mod,
        "_qualify_candidate",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("resume drift must fail before network")
        ),
    )
    with pytest.raises(ValueError, match="resume 输入或冻结来源摘要漂移"):
        mod.qualify_source_ready_candidates(
            **{**kwargs, "required_entity_refs": list(reversed(requested))},
            resume=True,
        )


def test_source_ready_resume_reuses_frozen_source_definition_after_live_drift(
    monkeypatch,
    tmp_path,
):
    import governance.coverage.source_readiness as mod

    candidate_file = tmp_path / "candidates.ndjson"
    candidate_file.write_text(
        json.dumps(
            {
                "name": "西湖",
                "canonicalName": "西湖",
                "canonicalEntityRef": "/entity/地点/自然景观/西湖",
                "province": "浙江省",
                "city": "杭州市",
                "district": "西湖区",
                "entityType": "地点/自然景观",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    class _Digest:
        digest = "sha256:" + "1" * 64

        def to_document(self):
            return {
                "algorithm": "sha256",
                "digest": self.digest,
                "inputs": ["test"],
            }

    monkeypatch.setattr(mod, "coverage_workspace_root", lambda: tmp_path / "workspace")
    monkeypatch.setattr(mod, "current_source_definition_snapshot", _Digest)
    monkeypatch.setattr(
        mod,
        "_qualify_candidate",
        lambda candidate, *, sources: _qualified_result(mod, candidate, sources=sources),
    )
    kwargs = {
        "run_id": "resume-frozen-source-definition",
        "provinces": ["浙江省"],
        "candidate_files": [candidate_file],
        "sources": ["wikipedia"],
        "minimum_per_province": 1,
        "include_master_list": False,
        "exhaust_input": True,
    }
    first = mod.qualify_source_ready_candidates(**kwargs, resume=False)
    _Digest.digest = "sha256:" + "2" * 64
    monkeypatch.setattr(
        mod,
        "current_source_definition_snapshot",
        lambda: (_ for _ in ()).throw(
            AssertionError("resume must not read the live source tree")
        ),
    )
    second = mod.qualify_source_ready_candidates(**kwargs, resume=True)

    assert second["sourceDigest"] == first["sourceDigest"]


def test_source_ready_parser_preserves_repeated_exact_target_order():
    from governance.coverage.handler import register_coverage_parser

    parser = argparse.ArgumentParser()
    register_coverage_parser(parser.add_subparsers(dest="command"))
    args = parser.parse_args(
        [
            "coverage",
            "source-ready",
            "--provinces",
            "四川省,浙江省",
            "--minimum-per-province",
            "1",
            "--run-id",
            "exact-parser",
            "--required-entity-ref",
            "/entity/地点/景区/黄龙风景名胜区",
            "--required-entity-ref",
            "/entity/地点/自然景观/西湖",
        ]
    )

    assert args.required_entity_ref == [
        "/entity/地点/景区/黄龙风景名胜区",
        "/entity/地点/自然景观/西湖",
    ]
