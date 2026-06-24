from __future__ import annotations



from support.site_supply_fixtures import *  # noqa: F401,F403



def test_downstream_evidence_promotes_ship_import_search_reco_into_rerollup():
    from _common.io import read_json, write_json
    from _common.paths import PUBLISH_ROOT

    source_batch = "downstream_source"
    task_id = TEST_COMMITTED_TASK_ID
    target_batch = "downstream_target"
    candidate = _write_candidate(source_batch)
    score = ss.build_site_score_packet(candidate)
    ss.write_site_score_packet(score)
    mapped = ss.build_site_map_packet(candidate, score)
    ss.write_site_map_packet(mapped)
    initial = ss.build_site_rollup_report(
        vertical="travel",
        site_id="qunar_guide",
        batch_id=source_batch,
        objects_per_hour=500,
        first_pass_rate=1.0,
        token_ledger_count=1,
    )
    ss.write_site_rollup_report(initial)

    target_root = ss._runtime_batch_root(task_id, target_batch)
    shared = target_root / "_shared"
    shared.mkdir(parents=True, exist_ok=True)
    post_ref = "posts/article/攻略/九寨沟·行前指南/1"
    write_json(
        shared / "content_plan_packet.json",
        {
            "schemaVersion": "quwoquan_data.content_plan_packet",
            "taskId": task_id,
            "batchId": target_batch,
            "sourceSite": {"vertical": "travel", "siteId": "qunar_guide", "batchId": source_batch},
            "items": [{"ref": candidate["candidateRef"]}],
        },
    )
    write_json(
        shared / "content_object_index.json",
        {
            "schemaVersion": "quwoquan_data.content_object_index",
            "refs": {
                candidate["candidateRef"]: {
                    "contentType": "article",
                    "angle": "攻略",
                    "title": "九寨沟·行前指南",
                    "seq": 1,
                }
            },
        },
    )

    index_dir = PUBLISH_ROOT / "index" / "posts"
    index_dir.mkdir(parents=True, exist_ok=True)
    (index_dir / "article__攻略__四川.ndjson").write_text(
        json.dumps({"postRef": post_ref}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_json(
        PUBLISH_ROOT / "sample_bundles" / "gamma.json",
        {
            "schemaVersion": "quwoquan.content_sample_bundle",
            "environment": "gamma",
            "posts": [post_ref],
            "entities": ["地点/景区/九寨沟"],
            "counts": {"posts": 1, "entities": 1},
        },
    )
    release_dir = PUBLISH_ROOT / "env_releases" / "rel_downstream"
    release_dir.mkdir(parents=True, exist_ok=True)
    release_contract = release_dir / "gamma.json"
    consistency = release_dir / "consistency-preflight-gamma.json"
    write_json(release_contract, {"releaseId": "rel_downstream", "environment": "gamma"})
    write_json(consistency, {"status": "passed", "releaseId": "rel_downstream", "environment": "gamma"})
    write_json(
        shared / "ship_report.json",
        {
            "schemaVersion": "quwoquan_data.ship_report/1",
            "taskId": task_id,
            "batchId": target_batch,
            "envs": ["gamma"],
            "importRequested": True,
            "summary": [
                {
                    "env": "gamma",
                    "releaseId": "rel_downstream",
                    "posts": 1,
                    "entities": 1,
                    "releaseContract": str(release_contract),
                    "consistencyReport": str(consistency),
                }
            ],
        },
    )
    write_json(
        shared / "gamma_import_report.json",
        {
            "schemaVersion": "quwoquan.content_import_report.v1",
            "status": "active",
            "environment": "gamma",
            "releaseId": "rel_downstream",
            "counts": {"postsLoaded": 1, "entitiesLoaded": 1, "feedUpserted": 1},
        },
    )

    report = ss.build_downstream_e2e_report(
        vertical="travel",
        site_id="qunar_guide",
        batch_id=source_batch,
        task_id=task_id,
        target_batch=target_batch,
        env="gamma",
    )
    assert report["gate"]["passed"], report
    assert report["checks"]["releaseVerified"] is True
    assert report["checks"]["importVerified"] is True
    assert report["checks"]["searchVisible"] is True
    assert report["checks"]["currentSampleBundleVisible"] is True
    assert report["checks"]["recommendationFeedbackReady"] is True
    path = ss.write_downstream_e2e_report(report)
    assert read_json(path)["schemaVersion"] == ss.DOWNSTREAM_E2E_SCHEMA

    rerollup = ss._recomputed_site_rollup_report(
        vertical="travel",
        site_id="qunar_guide",
        batch_id=source_batch,
    )
    assert rerollup["executionReadiness"]["releaseVerified"] is True
    assert rerollup["executionReadiness"]["importVerified"] is True
    assert rerollup["executionReadiness"]["searchVisible"] is True
    assert rerollup["executionReadiness"]["recommendationFeedbackReady"] is True

def test_downstream_evidence_appends_stage_outputs_for_multiple_target_batches():
    from _common.io import read_json

    source_batch = "downstream_append_source"
    reports = []
    for target_batch in ("downstream_append_target_a", "downstream_append_target_b"):
        reports.append(
            {
                "schemaVersion": ss.DOWNSTREAM_E2E_SCHEMA,
                "vertical": "travel",
                "siteId": "qunar_guide",
                "sourceBatchId": source_batch,
                "taskId": TEST_COMMITTED_TASK_ID,
                "targetBatch": target_batch,
                "env": "gamma",
                "postRefs": [f"posts/article/攻略/{target_batch}/1"],
                "plannedPostRefs": [f"posts/article/攻略/{target_batch}/1"],
                "releasedPostRefs": [f"posts/article/攻略/{target_batch}/1"],
                "plannedPostRefCount": 1,
                "releasedPostRefCount": 1,
                "droppedBeforeReleaseCount": 0,
                "checks": {
                    "releaseVerified": True,
                    "importVerified": True,
                    "searchVisible": True,
                    "recommendationFeedbackReady": True,
                },
                "importStatus": "active",
                "importCounts": {"postsUpserted": 1, "feedUpserted": 1},
                "evidencePaths": [],
                "gate": ss._gate_report("ship_import", [], []),
                "createdAt": ss.now_iso(),
            }
        )

    paths = [ss.write_downstream_e2e_report(report) for report in reports]
    stage_result = read_json(
        ss.site_supply_root("travel", "qunar_guide", source_batch)
        / "ship_import"
        / "stage_result.json"
    )

    outputs = set(stage_result["outputs"])
    assert str(paths[0]) in outputs
    assert str(paths[1]) in outputs
    assert len([item for item in outputs if item.endswith("site_supply_downstream_e2e_report.json")]) == 2

def test_downstream_evidence_keeps_historical_visibility_when_sample_bundle_changes():
    from _common.io import write_json
    from _common.paths import PUBLISH_ROOT

    source_batch = "downstream_historical_bundle_source"
    task_id = TEST_COMMITTED_TASK_ID
    target_batch = "downstream_historical_bundle_target"
    candidate = _write_candidate(source_batch)
    target_root = ss._runtime_batch_root(task_id, target_batch)
    shared = target_root / "_shared"
    shared.mkdir(parents=True, exist_ok=True)
    post_ref = "posts/article/攻略/九寨沟·历史发布/1"
    write_json(
        shared / "content_plan_packet.json",
        {
            "schemaVersion": "quwoquan_data.content_plan_packet",
            "taskId": task_id,
            "batchId": target_batch,
            "sourceSite": {"vertical": "travel", "siteId": "qunar_guide", "batchId": source_batch},
            "items": [{"ref": candidate["candidateRef"]}],
        },
    )
    write_json(
        shared / "content_object_index.json",
        {
            "schemaVersion": "quwoquan_data.content_object_index",
            "refs": {
                candidate["candidateRef"]: {
                    "contentType": "article",
                    "angle": "攻略",
                    "title": "九寨沟·历史发布",
                    "seq": 1,
                }
            },
        },
    )
    index_dir = PUBLISH_ROOT / "index" / "posts"
    index_dir.mkdir(parents=True, exist_ok=True)
    (index_dir / "article__攻略__九寨沟历史.ndjson").write_text(
        json.dumps({"postRef": post_ref}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_json(
        PUBLISH_ROOT / "sample_bundles" / "gamma.json",
        {
            "schemaVersion": "quwoquan.content_sample_bundle",
            "environment": "gamma",
            "posts": ["posts/article/攻略/other-release/1"],
            "entities": [],
            "counts": {"posts": 1, "entities": 0},
        },
    )
    release_dir = PUBLISH_ROOT / "env_releases" / "rel_downstream_historical"
    release_dir.mkdir(parents=True, exist_ok=True)
    release_contract = release_dir / "gamma.json"
    consistency = release_dir / "consistency-preflight-gamma.json"
    write_json(
        release_contract,
        {
            "releaseId": "rel_downstream_historical",
            "environment": "gamma",
            "desiredRefs": {"posts": [post_ref], "entities": []},
        },
    )
    write_json(consistency, {"status": "passed", "releaseId": "rel_downstream_historical", "environment": "gamma"})
    write_json(
        shared / "ship_report.json",
        {
            "schemaVersion": "quwoquan_data.ship_report/1",
            "taskId": task_id,
            "batchId": target_batch,
            "envs": ["gamma"],
            "importRequested": True,
            "summary": [
                {
                    "env": "gamma",
                    "releaseId": "rel_downstream_historical",
                    "posts": 1,
                    "entities": 0,
                    "releaseContract": str(release_contract),
                    "consistencyReport": str(consistency),
                }
            ],
        },
    )
    write_json(
        shared / "gamma_import_report.json",
        {
            "schemaVersion": "quwoquan.content_import_report.v1",
            "status": "active",
            "environment": "gamma",
            "releaseId": "rel_downstream_historical",
            "counts": {"postsLoaded": 1, "entitiesLoaded": 0, "feedUpserted": 1},
        },
    )

    report = ss.build_downstream_e2e_report(
        vertical="travel",
        site_id="qunar_guide",
        batch_id=source_batch,
        task_id=task_id,
        target_batch=target_batch,
        env="gamma",
    )

    assert report["gate"]["passed"], report
    assert report["checks"]["searchVisible"] is True
    assert report["checks"]["currentSampleBundleVisible"] is False
    assert "current mutable sample bundle" in "\n".join(report["gate"]["warnings"])

def test_downstream_evidence_failed_recheck_does_not_overwrite_existing_pass_report():
    from _common.io import read_json

    source_batch = "downstream_preserve_pass_source"
    target_batch = "downstream_preserve_pass_target"
    passed_report = {
        "schemaVersion": ss.DOWNSTREAM_E2E_SCHEMA,
        "vertical": "travel",
        "siteId": "qunar_guide",
        "sourceBatchId": source_batch,
        "taskId": TEST_COMMITTED_TASK_ID,
        "targetBatch": target_batch,
        "env": "gamma",
        "postRefs": ["posts/article/攻略/pass/1"],
        "plannedPostRefs": ["posts/article/攻略/pass/1"],
        "releasedPostRefs": ["posts/article/攻略/pass/1"],
        "plannedPostRefCount": 1,
        "releasedPostRefCount": 1,
        "droppedBeforeReleaseCount": 0,
        "checks": {"releaseVerified": True, "importVerified": True, "searchVisible": True},
        "importStatus": "active",
        "importCounts": {},
        "evidencePaths": [],
        "gate": ss._gate_report("ship_import", [], []),
        "createdAt": ss.now_iso(),
    }
    pass_path = ss.write_downstream_e2e_report(passed_report)
    failed_report = dict(passed_report)
    failed_report["postRefs"] = []
    failed_report["releasedPostRefCount"] = 0
    failed_report["gate"] = ss._gate_report("ship_import", ["sample bundle gamma missing post ref"], [])

    failed_path = ss.write_downstream_e2e_report(failed_report)

    assert failed_path.name == "site_supply_downstream_e2e_report_last_failed.json"
    assert read_json(pass_path)["gate"]["passed"] is True
    assert read_json(failed_path)["gate"]["passed"] is False

def test_downstream_evidence_uses_release_refs_after_publish_attrition():
    from _common.io import write_json
    from _common.paths import PUBLISH_ROOT

    source_batch = "downstream_attrition_source"
    task_id = TEST_COMMITTED_TASK_ID
    target_batch = "downstream_attrition_target"
    candidate = _write_candidate(source_batch)
    dropped_ref = "site_candidate_dropped_before_release"
    score = ss.build_site_score_packet(candidate)
    ss.write_site_score_packet(score)
    mapped = ss.build_site_map_packet(candidate, score)
    ss.write_site_map_packet(mapped)
    ss.write_site_rollup_report(
        ss.build_site_rollup_report(
            vertical="travel",
            site_id="qunar_guide",
            batch_id=source_batch,
            objects_per_hour=500,
            first_pass_rate=1.0,
            token_ledger_count=1,
        )
    )

    target_root = ss._runtime_batch_root(task_id, target_batch)
    shared = target_root / "_shared"
    shared.mkdir(parents=True, exist_ok=True)
    released_post_ref = "posts/article/攻略/九寨沟·准出稿/1"
    dropped_post_ref = "posts/article/攻略/九寨沟·发布前淘汰稿/1"
    write_json(
        shared / "content_plan_packet.json",
        {
            "schemaVersion": "quwoquan_data.content_plan_packet",
            "taskId": task_id,
            "batchId": target_batch,
            "sourceSite": {"vertical": "travel", "siteId": "qunar_guide", "batchId": source_batch},
            "items": [{"ref": candidate["candidateRef"]}, {"ref": dropped_ref}],
        },
    )
    write_json(
        shared / "content_object_index.json",
        {
            "schemaVersion": "quwoquan_data.content_object_index",
            "refs": {
                candidate["candidateRef"]: {
                    "contentType": "article",
                    "angle": "攻略",
                    "title": "九寨沟·准出稿",
                    "seq": 1,
                },
                dropped_ref: {
                    "contentType": "article",
                    "angle": "攻略",
                    "title": "九寨沟·发布前淘汰稿",
                    "seq": 1,
                },
            },
        },
    )

    index_dir = PUBLISH_ROOT / "index" / "posts"
    index_dir.mkdir(parents=True, exist_ok=True)
    (index_dir / "article__攻略__九寨沟.ndjson").write_text(
        json.dumps({"postRef": released_post_ref}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_json(
        PUBLISH_ROOT / "sample_bundles" / "gamma.json",
        {
            "schemaVersion": "quwoquan.content_sample_bundle",
            "environment": "gamma",
            "posts": [released_post_ref],
            "entities": [],
            "counts": {"posts": 1, "entities": 0},
        },
    )
    release_dir = PUBLISH_ROOT / "env_releases" / "rel_downstream_attrition"
    release_dir.mkdir(parents=True, exist_ok=True)
    release_contract = release_dir / "gamma.json"
    consistency = release_dir / "consistency-preflight-gamma.json"
    write_json(
        release_contract,
        {
            "releaseId": "rel_downstream_attrition",
            "environment": "gamma",
            "desiredRefs": {"posts": [released_post_ref], "entities": []},
        },
    )
    write_json(consistency, {"status": "passed", "releaseId": "rel_downstream_attrition", "environment": "gamma"})
    write_json(
        shared / "ship_report.json",
        {
            "schemaVersion": "quwoquan_data.ship_report/1",
            "taskId": task_id,
            "batchId": target_batch,
            "envs": ["gamma"],
            "importRequested": True,
            "summary": [
                {
                    "env": "gamma",
                    "releaseId": "rel_downstream_attrition",
                    "posts": 1,
                    "entities": 0,
                    "releaseContract": str(release_contract),
                    "consistencyReport": str(consistency),
                }
            ],
        },
    )
    write_json(
        shared / "gamma_import_report.json",
        {
            "schemaVersion": "quwoquan.content_import_report.v1",
            "status": "active",
            "environment": "gamma",
            "releaseId": "rel_downstream_attrition",
            "counts": {"postsLoaded": 1, "entitiesLoaded": 0, "feedUpserted": 1},
        },
    )

    report = ss.build_downstream_e2e_report(
        vertical="travel",
        site_id="qunar_guide",
        batch_id=source_batch,
        task_id=task_id,
        target_batch=target_batch,
        env="gamma",
    )
    assert report["gate"]["passed"], report
    assert report["plannedPostRefCount"] == 2
    assert report["releasedPostRefCount"] == 1
    assert report["droppedBeforeReleaseCount"] == 1
    assert report["postRefs"] == [released_post_ref]
    assert dropped_post_ref not in report["postRefs"]
    assert report["checks"]["searchVisible"] is True
    assert report["checks"]["recommendationFeedbackReady"] is True

def test_downstream_write_repairs_content_plan_source_site_from_bridge_report():
    from _common.io import read_json, write_json

    task_id = TEST_COMMITTED_TASK_ID
    target_batch = "downstream_source_site_repair"
    source_batch = "source_site_bridge_batch"
    shared = ss._runtime_batch_root(task_id, target_batch) / "_shared"
    shared.mkdir(parents=True, exist_ok=True)
    packet_path = shared / "content_plan_packet.json"
    write_json(
        packet_path,
        {
            "schemaVersion": "quwoquan_data.content_plan_packet",
            "taskId": task_id,
            "batchId": target_batch,
            "generatedBy": "deterministic_source_ready_planner",
            "items": [{"ref": "九寨沟_planning_consultation"}],
        },
    )
    write_json(
        shared / "site_supply_content_plan_report.json",
        {
            "schemaVersion": "quwoquan.site_supply.content_plan_report/1",
            "vertical": "travel",
            "siteId": "wikivoyage_zh",
            "batchId": source_batch,
            "taskId": task_id,
            "targetBatch": target_batch,
            "gate": {"passed": True},
        },
    )

    repaired = ss.repair_content_plan_source_site_provenance(
        vertical="travel",
        site_id="wikivoyage_zh",
        batch_id=source_batch,
        task_id=task_id,
        target_batch=target_batch,
    )

    assert repaired is True
    assert read_json(packet_path)["sourceSite"] == {
        "vertical": "travel",
        "siteId": "wikivoyage_zh",
        "batchId": source_batch,
    }

def test_rerollup_derives_throughput_from_fetch_stage_timestamps():
    from _common.io import write_json

    batch = "throughput_from_stage_results"
    root = ss.site_supply_root("travel", "qunar_guide", batch)
    for ref, created_at in {
        "candidate_a": "2026-06-20T00:00:00+00:00",
        "candidate_b": "2026-06-20T00:01:00+00:00",
    }.items():
        write_json(
            root / "fetches" / ref / "stage_result.json",
            {
                "schemaVersion": ss.STAGE_SCHEMA,
                "stage": "site_fetch",
                "status": "succeeded",
                "createdAt": created_at,
            },
        )

    observed = ss._observed_objects_per_hour_from_stage_results(root)
    assert round(observed, 2) == 120.0

