from __future__ import annotations



from support.data_cli_fixtures import *  # noqa: F401,F403



def _real_jpeg(seed: int) -> bytes:
    from io import BytesIO

    from PIL import Image

    image = Image.new("RGB", (960, 640), (60 + seed, 120, 180))
    buf = BytesIO()
    image.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _seed_homepage_only_source_plans(task_id: str, batch_id: str) -> None:
    ensure_batch_layout(task_id, batch_id, "workflow_test")
    for name in ("峨眉山", "乐山大佛"):
        dl = batch_entity_object_dir(task_id, batch_id, "地点", "景区", name) / "1.download"
        dl.mkdir(parents=True, exist_ok=True)
        write_json(
            dl / "homepage_source_plan.json",
            {
                "payload": {
                    "sources": [
                        {
                            "source_id": f"homepage_baike_{name}",
                            "title": name,
                            "platform": "百度百科",
                            "sourceKind": "encyclopedia",
                            "sourceRole": "primary",
                            "category": "encyclopedia",
                            "url": f"https://fixture.invalid/{name}/baike",
                            "sourceUseMode": "factual_reference_only",
                            "body": f"{name}景区基础事实来源，仅用于本地 contract 测试。",
                            "imageUrls": [
                                {
                                    "url": f"https://fixture.invalid/{name}/cover.jpg",
                                    "platform": "Wikimedia Commons",
                                    "license": "CC-BY-SA 4.0",
                                    "credit": f"{name} fixture photographer",
                                    "sourceUrl": f"https://fixture.invalid/{name}/cover.jpg",
                                    "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                                    "licenseSnapshot": "CC-BY-SA 4.0 fixture",
                                    "authorizationProof": f"fixture homepage image rights {name}",
                                    "usageScope": "app_publish",
                                    "modelReleaseStatus": "not_required",
                                    "width": 960,
                                    "height": 640,
                                    "contentType": "image/jpeg",
                                    "caption": f"{name}核心景区实拍",
                                    "relevance": f"直接呈现{name}核心景区景观",
                                }
                            ],
                        }
                    ],
                }
            },
        )


def _stub_download_fetch(monkeypatch):
    from types import SimpleNamespace
    import hashlib

    import download.handler as download_handler_mod

    def _fake_source_fetch(url: str, **_kwargs):
        entity = "峨眉山" if "峨眉山" in url else "乐山大佛"
        fetched_text = "\n\n".join(
            [
                f"{entity}位于四川省，是面向游客开放的著名景区。",
                f"{entity}游览需要关注开放时间、交通接驳、门票预约、天气变化和返程安排。",
                f"{entity}核心游线包含自然或人文景观，适合以实体主页底稿方式整理基础事实。",
                f"{entity}相关行程应根据季节、客流和现场管理要求调整停留时间。",
            ]
            * 4
        )
        return {
            "url": url,
            "statusCode": 200,
            "htmlBytes": b"<html><body>fixture</body></html>",
            "text": fetched_text,
            "sha256": "fixture-source",
        }

    def _fake_image_fetch(url: str, **_kwargs):
        seed = 11 if "峨眉山" in url else 29
        body = _real_jpeg(seed)
        return {
            "url": url,
            "ext": ".jpg",
            "bytes": body,
            "contentType": "image/jpeg",
            "sha256": hashlib.sha256(body).hexdigest(),
        }

    def _safe_image(*_args, **_kwargs):
        return SimpleNamespace(blocks_image_publish=False, status="passed", reasons=[])

    monkeypatch.setattr(download_handler_mod, "fetch_source_payload", _fake_source_fetch)
    monkeypatch.setattr(download_handler_mod, "fetch_image_payload", _fake_image_fetch)
    monkeypatch.setattr(download_handler_mod, "assess_image", _safe_image)
    monkeypatch.setattr(download_handler_mod, "assess_image_cached", _safe_image)


def test_explore_writes_catalog_and_packet():
    task_id = _make_task(with_baseline=False)
    handle_explore(
        argparse.Namespace(
            task=task_id,
            regions="四川省",
            entity_types="地点/景区",
        )
    )
    rows = read_ndjson(task_catalog(task_id))
    assert [row["topic_id"] for row in rows] == ["地点/景区/峨眉山", "地点/景区/乐山大佛"]
    packet = read_json(task_explore_packet_path(task_id))
    assert packet["command"] == "data explore"
    assert packet["summary"]["catalogRowCount"] == 2
    assert packet["handoffTo"] == "data baseline"

def test_baseline_freezes_bundle_and_enforces_catalog_config_pair():
    task_id = _make_task(with_baseline=False)
    handle_explore(
        argparse.Namespace(
            task=task_id,
            regions="四川省",
            entity_types="地点/景区",
        )
    )
    config_dir = _TMP / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    catalog_config = config_dir / "geo_catalog_config.yaml"
    geo_band_rules = config_dir / "geo_band_rules.sichuan.yaml"
    catalog_config.write_text("geo_band_rules_path: geo_band_rules.sichuan.yaml\n", encoding="utf-8")
    geo_band_rules.write_text("schemaVersion: demo\n", encoding="utf-8")

    handle_baseline(
        argparse.Namespace(
            task=task_id,
            catalog=None,
            spec_doc=None,
            design_doc=None,
            acceptance_doc=None,
            workflow_doc=None,
            command_matrix_doc=None,
            catalog_config=str(catalog_config),
            naming_rules=None,
            geo_band_rules=str(geo_band_rules),
            schema_files=[],
            config_files=[],
            output=None,
        )
    )
    packet = read_json(task_baseline_freeze_packet_path(task_id))
    report = read_json(task_shared_dir(task_id) / "baseline_report.json")
    assert packet["command"] == "data baseline"
    assert packet["summary"]["coverageTargetCount"] == 2
    assert report["status"] == "passed"
    assert report["issues"] == []

def test_baseline_allows_dynamic_site_supply_task_without_catalog():
    task_id = _make_task("旅行/主题/网站供给线/百级动态验证", with_baseline=False)
    spec = store.load_spec(task_id)
    spec["taskArchetype"] = "theme_collection"
    spec["organizeBy"] = "主题"
    spec["key"] = "网站供给线"
    spec.setdefault("scope", {})["theme"] = "百级动态验证"
    spec.setdefault("workflowPolicy", {})["siteSupplyDynamicContentPlan"] = True
    store.save_spec(spec)

    handle_baseline(
        argparse.Namespace(
            task=task_id,
            catalog=None,
            spec_doc=None,
            design_doc=None,
            acceptance_doc=None,
            workflow_doc=None,
            command_matrix_doc=None,
            catalog_config=None,
            naming_rules=None,
            geo_band_rules=None,
            schema_files=[],
            config_files=[],
            output=None,
        )
    )

    packet = read_json(task_baseline_freeze_packet_path(task_id))
    report = read_json(task_shared_dir(task_id) / "baseline_report.json")
    assert report["status"] == "passed"
    assert report["issues"] == []
    assert packet["summary"]["siteSupplyDynamicContentPlan"] is True
    assert packet["summary"]["catalogRequired"] is False

def test_workflow_run_requires_baseline_packet():
    task_id = _make_task(with_baseline=False)
    try:
        run_mod.handle_run(
            argparse.Namespace(
                task=task_id,
                batch="b1",
                resume=False,
                reset_state=False,
                until=None,
                baseline_packet=None,
            )
        )
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("workflow run should require baseline packet")

def test_workflow_run_records_baseline_packet_when_present(monkeypatch):
    task_id = _make_task()
    _seed_homepage_only_source_plans(task_id, "b1")
    _stub_download_fetch(monkeypatch)
    code = None
    try:
        run_mod.handle_run(
            argparse.Namespace(
                task=task_id,
                batch="b1",
                resume=False,
                reset_state=False,
                until=None,
                baseline_packet=None,
            )
        )
    except SystemExit as exc:
        code = exc.code
    assert code == 10, code
    state = run_mod.load_workflow_state(task_id, "b1")
    assert state["baselinePacketPath"].endswith("baseline_freeze_packet.json")
    # download_plan 由 CLI auto_research 自动完成；build_homepage 仍需 Agent 写实体主页正文。
    assert state["waitingCheckpoint"] == "build_homepage"

def test_task_new_persists_explicit_content_quotas():
    task_handler_mod.handle_new(
        argparse.Namespace(
            vertical="travel",
            organize_by="地域",
            key="四川省",
            name="三景点真实实跑",
            category="景区",
            archetype=None,
            title="四川三景点真实实跑",
            parent=None,
            region="四川省",
            regions=None,
            entity_types="地点/景区",
            route=None,
            anchor_entities=None,
            theme=None,
            coverage="地点/景区/都江堰,地点/景区/乐山大佛,地点/景区/峨眉山",
            angles="攻略",
            audiences=None,
            carriers="article,gallery",
            entity_articles=3,
            route_articles=0,
            gallery_posts=3,
            emphasis=None,
            cond_regions=None,
            cond_seasons=None,
            owner="test",
            force=False,
        )
    )
    spec = store.load_raw_spec("旅行/地域/四川省/景区/三景点真实实跑")
    quotas = ((spec.get("content") or {}).get("quotas") or {})
    assert quotas == {"entityArticles": 3, "routeArticles": 0, "galleryPosts": 3}, quotas

def test_task_scaled_e2e_prepare_enters_standard_checkpointed_workflow(monkeypatch):
    task_id = _make_task(with_baseline=False)
    spec = store.load_spec(task_id)
    spec["status"] = "active"
    store.save_spec(spec)
    _seed_homepage_only_source_plans(task_id, "se1")
    _stub_download_fetch(monkeypatch)
    monkeypatch.setattr(run_mod, "_managed_local_workspace_conflicts", lambda _workspace: [])
    try:
        task_handler_mod.handle_scaled_e2e(
            argparse.Namespace(
                scaled_e2e_command="prepare",
                task=task_id,
                batch="se1",
                plan="dummy_plan",
                catalog=None,
                reset_state=False,
                max_workers=1,
            )
        )
    except SystemExit as exc:
        assert exc.code == 10
    else:
        raise AssertionError("scaled-e2e prepare should stop at standard workflow checkpoint")
    state = run_mod.load_workflow_state(task_id, "se1")
    assert state["baselinePacketPath"].endswith("baseline_freeze_packet.json"), state
    # scaled-e2e prepare 走标准 DAG，并在需 Agent 写主页正文的 build_homepage 处暂停。
    assert state["waitingCheckpoint"] == "build_homepage", state
    packet = read_json(task_explore_packet_path(task_id))
    assert packet["command"] == "data explore"

def test_task_scaled_e2e_fanout_author_delegates_to_run_fanout():
    called: dict = {}
    original = run_mod.handle_run
    try:
        def _fake_handle_run(args):
            called["mode"] = args.mode
            called["plan"] = args.plan
            called["strategy"] = args.strategy
            called["concurrency"] = args.concurrency
            called["batch_size"] = args.batch_size

        run_mod.handle_run = _fake_handle_run
        task_handler_mod.handle_scaled_e2e(
            argparse.Namespace(
                scaled_e2e_command="fanout-author",
                plan="plan_x",
                batch="b2",
                strategy="flat-pool",
                concurrency=3,
                batch_size=5,
            )
        )
    finally:
        run_mod.handle_run = original
    assert called == {
        "mode": "fanout",
        "plan": "plan_x",
        "strategy": "flat-pool",
        "concurrency": 3,
        "batch_size": 5,
    }, called
