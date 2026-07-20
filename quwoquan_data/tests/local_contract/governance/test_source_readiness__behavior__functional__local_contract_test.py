from __future__ import annotations

import json
from pathlib import Path


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
    monkeypatch.setattr(mod, "current_source_digest", lambda: _Digest())
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
