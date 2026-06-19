"""task run 编排器回归（目标① 无人值守 DAG）：

验证编排器在 Agent checkpoint 正确暂停/推进、workflow_state 可 resume：
1. 首跑停在 download_plan checkpoint（无 source_plan）。
2. 预置 source_plan(含 body 离线兜底) 后 resume → 过 download_plan/download_fetch/
   build_prepare，停在下一个 checkpoint build_homepage（主页未物化）。
3. workflow_state.completed 正确累积、幂等。

隔离 QWQ_DATA_ROOT，造最小单实体 task，不依赖联网/真实 committed 任务。
可直接运行 python3 quwoquan_data/tests/workflow/test_task_run_pipeline.py
"""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import argparse
import copy
import hashlib
import importlib
import inspect
import os
import struct
import sys
import tempfile
import zlib
from io import BytesIO
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="task_run_"))
os.environ["QWQ_DATA_ROOT"] = str(_TMP)
os.environ["QWQ_RUNTIME_ROOT"] = str(_TMP / "runtime")
os.environ["QWQ_PUBLISH_ROOT"] = str(_TMP / "publish")
os.environ["QWQ_COMMITTED_TASKS_ROOT"] = str(_TMP / "tasks")

sys.path.insert(0, str(SCRIPTS_ROOT))

from _common.draft_io import draft_article_path, write_placeholder_draft, write_writing_pack  # noqa: E402
from _common.command_packet import build_packet, write_packet  # noqa: E402
from _common.io import read_json, write_json  # noqa: E402
from _common.stage_reports import write_gate_report  # noqa: E402
from _common import content_object  # noqa: E402
from _common.paths import (  # noqa: E402
    batch_posts_root,
    batch_root,
    committed_task_spec,
    STAGE_DOWNLOAD,
    batch_command_root,
    batch_inputs_dir,
    batch_assistant_task,
    batch_entity_page_input_path,
    ensure_batch_layout,
    release_root,
    task_baseline_freeze_packet_path,
    task_data,
    task_entities,
    task_tags,
    task_shared_dir,
)
from _common.source_unit import resolve_entity_object_dir  # noqa: E402
from _common.release_integrity import ARTICLE_HARD_CHECKS  # noqa: E402
from task import object_queue as oq  # noqa: E402
from task import run as run_mod  # noqa: E402
from task import store  # noqa: E402

_EID = "测试景区甲"


def test_prepare_entity_pages_prunes_stale_inactive_inputs():
    from build.homepage import prepare_entity_pages

    task_id = "workflow_prepare_homepage_prune"
    batch_id = "batch"
    active = "当前有效景区"
    stale = "已放弃景区"
    stale_input = batch_entity_page_input_path(task_id, batch_id, "地点", "景区", stale)
    write_json(stale_input, {"payload": {"name": stale}})

    spec = {
        "scope": {
            "coverageTargets": [
                {"entityType": "地点/景区", "name": active},
            ],
        },
    }

    prepare_entity_pages(task_id, batch_id, spec)

    active_input = batch_entity_page_input_path(task_id, batch_id, "地点", "景区", active)
    assert active_input.is_file()
    assert not stale_input.exists()
    manifest = read_json(batch_assistant_task(task_id, batch_id, "build", "entity_page"))
    assert manifest["refs"] == ["地点__景区__当前有效景区"]


def _real_jpeg(seed: int) -> bytes:
    from PIL import Image

    width, height = 960, 640
    img = Image.new("RGB", (width, height))
    for y in range(height):
        for x in range(width):
            r = (x * 3 + seed * 17) % 256
            g = (y * 5 + seed * 29) % 256
            b = ((x + y) * 7 + seed * 11) % 256
            img.putpixel((x, y), (r, g, b))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )


def _oversized_png_header(width: int = 9000, height: int = 6000) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _png_chunk(b"IEND", b"")
    )


def _make_task(*, workflow_policy: dict | None = None) -> str:
    spec = store.scaffold_spec(
        vertical="travel",
        organize_by="地域",
        key="测试省",
        name="景区全覆盖",
        category="景区",
        scope={
            "region": "测试省",
            "entityTypes": ["地点/景区"],
            "coverageTargets": [{"entityType": "地点/景区", "name": _EID}],
        },
        content={
            "modalityContract": "separated_research",
            "research": {
                "lanes": ["homepage", "article", "image"],
                "maxConcurrency": 10,
                "laneConcurrency": {"homepage": 3, "article": 3, "image": 4},
                "allowAiImages": False,
            },
            "carriers": ["article", "image"],
            "quotas": {
                "entityArticlesPerTarget": 2,
                "imageWorksPerTarget": 2,
                "entityHomepagesPerTarget": 1,
                "routeArticles": 0,
            },
        },
        created_by="test",
    )
    if workflow_policy is not None:
        spec["workflowPolicy"] = workflow_policy
    store.save_spec(spec)
    store.save_progress(store.init_progress(spec["taskId"], remaining=[f"地点/景区/{_EID}"]))
    _seed_baseline(spec["taskId"])
    return spec["taskId"]


def _seed_baseline(task_id: str) -> None:
    packet = build_packet(
        task_id=task_id,
        command="data baseline",
        object_kind="task",
        object_ref=task_id,
        stage="baseline",
        read_policy=["task.yaml", "progress.json"],
        stop_if=["taskId mismatch"],
        output_policy=["write task/_shared/baseline_freeze_packet.json"],
        inputs={"taskSpecPath": str(committed_task_spec(task_id))},
        outputs={"packetPath": str(task_baseline_freeze_packet_path(task_id))},
        handoff_to="data workflow run",
        evidence={"required": ["baseline_freeze_packet.json"]},
        summary={"coverageTargetCount": 1, "catalogRowCount": 1},
    )
    write_packet(task_baseline_freeze_packet_path(task_id), packet)


def _ctx(task_id: str, batch_id: str) -> run_mod.PipelineContext:
    spec = store.load_spec(task_id)
    baseline_packet = read_json(task_baseline_freeze_packet_path(task_id))
    return run_mod.PipelineContext(
        task_id=task_id, batch_id=batch_id,
        entity_ids=run_mod._coverage_entity_ids(spec), spec=spec,
        baseline_packet=baseline_packet, baseline_packet_path=task_baseline_freeze_packet_path(task_id),
    )


def test_review_fallback_does_not_rewind_to_download_for_traceability(monkeypatch):
    reports = [
        (
            "post-a",
            {
                "payload": {
                    "passed": False,
                    "fallbackStage": "download",
                    "issues": [
                        "factTraceability: mustIncludeFact not traceable: editorial advice"
                    ],
                }
            },
        )
    ]
    monkeypatch.setattr(
        "_common.stage_reports.iter_stage_envelopes",
        lambda *_args, **_kwargs: iter(reports),
    )
    task_id = _make_task()
    assert run_mod._aggregate_review_fallback(_ctx(task_id, "b_review_fallback")) == "compose"


def test_review_fallback_rewinds_to_download_for_missing_source(monkeypatch):
    reports = [
        (
            "post-a",
            {
                "payload": {
                    "passed": False,
                    "fallbackStage": "download",
                    "issues": ["source file missing: entities/x/1.download/sources/01/source.md"],
                }
            },
        )
    ]
    monkeypatch.setattr(
        "_common.stage_reports.iter_stage_envelopes",
        lambda *_args, **_kwargs: iter(reports),
    )
    task_id = _make_task()
    assert run_mod._aggregate_review_fallback(_ctx(task_id, "b_missing_source")) == "download"


def test_cursor_bridge_startup_errors_are_retryable_infra():
    assert run_mod._cursor_bridge_error_is_retryable(
        "Bridge exited before discovery with status 1: "
        "cursor-sdk-bridge failed: Error: Missing value for --tool-callback-auth-token"
    )
    assert run_mod._cursor_bridge_error_is_retryable(
        "Bridge request failed: ConnectError: [Errno 61] Connection refused"
    )
    assert not run_mod._cursor_bridge_error_is_retryable("CURSOR_API_KEY missing")


def test_cursor_callback_token_factory_never_starts_with_dash():
    calls = iter(["-bad-token", "ok-token"])
    factory = run_mod._cursor_safe_auth_token_factory(lambda: next(calls))
    assert factory() == "qwq_bad-token"
    assert factory() == "ok-token"


def test_managed_lane_limits_are_configurable():
    assert run_mod._parse_managed_lane_limits("article:8,image=5,homepage:2") == {
        "homepage": 2,
        "article": 8,
        "image": 5,
    }
    assert run_mod._parse_managed_lane_limits("article:not-a-number,unknown:9") == {
        "homepage": 3,
        "article": 3,
        "image": 4,
    }


def test_recover_stale_agent_scheduler_clears_orphaned_waiting_state(monkeypatch):
    task_id = _make_task()
    batch_id = "stale_scheduler_recovery"
    ctx = _ctx(task_id, batch_id)
    state = run_mod.load_workflow_state(task_id, batch_id)
    state.update(
        {
            "status": "waiting_agent",
            "waitingCheckpoint": "produce_author",
            "heartbeatAt": "2000-01-01T00:00:00+00:00",
            "activeAgentScheduler": {
                "stage": "produce_author",
                "runtime": "local",
                "promptCount": 10,
                "startedAt": "2000-01-01T00:00:00+00:00",
            },
        }
    )
    monkeypatch.setattr(run_mod, "MANAGED_SCHEDULER_STALE_SECONDS", 60)
    monkeypatch.setattr(run_mod, "_managed_agent_process_alive", lambda _ctx: False)

    assert run_mod._recover_stale_agent_scheduler(ctx, state) is True

    recovered = run_mod.load_workflow_state(task_id, batch_id)
    assert recovered["status"] == "running"
    assert "activeAgentScheduler" not in recovered
    assert recovered["waitingCheckpoint"] == "produce_author"
    assert recovered["schedulerRecoveryActions"][-1]["stage"] == "produce_author"


def _seed_source_plan(task_id: str, batch_id: str) -> None:
    # separated_research：Agent 必须分别写 homepage/article/image 三路计划。
    ensure_batch_layout(task_id, batch_id, "download")
    obj = resolve_entity_object_dir(task_id, batch_id, _EID, etype_hint="地点/景区")
    dl = obj / STAGE_DOWNLOAD
    source_body = (
        "测试景区甲位于测试省山地森林地带，景区开放时间通常从上午到傍晚，"
        "门票与观光车费用需要在出发前确认。主游线步行强度中等，遇到雨天路况会变得湿滑，"
        "建议预留补给和返程时间。景区海拔有起伏，核心停留点之间需要一定徒步时间。"
    )
    write_json(dl / "homepage_source_plan.json", {
        "payload": {
            "primaryEvidenceRef": "home_official",
            "sources": [
                {
                    "source_id": "home_official",
                    "platform": "景区官网",
                    "url": "https://x.invalid/home",
                    "sourceUseMode": "factual_reference_only",
                    "body": source_body,
                    "imageUrls": [
                        {
                            "url": "https://img.invalid/home.jpg",
                            "platform": "景区官网",
                            "license": "CC-BY-SA 4.0",
                            "credit": "景区官方",
                            "sourceUrl": "https://img.invalid/home.jpg",
                            "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                            "licenseSnapshot": "CC-BY-SA 4.0 test fixture",
                            "authorizationProof": "fixture homepage image rights",
                            "usageScope": "app_publish",
                            "width": 960,
                            "height": 640,
                            "caption": "测试景区甲主景实拍",
                            "relevance": "直接呈现测试景区甲核心景区主景",
                        }
                    ],
                },
                {
                    "source_id": "home_baike",
                    "platform": "百度百科",
                    "url": "https://x.invalid/baike",
                    "sourceUseMode": "factual_reference_only",
                    "body": source_body,
                },
            ],
        }
    })
    article_sources = [
        ("article_baike", "百度百科", "https://x.invalid/a", "supporting"),
        ("article_wiki", "维基百科", "https://x.invalid/b", "supporting"),
        ("article_official", "景区官网", "https://x.invalid/c", "supporting"),
        ("article_guide", "马蜂窝", "https://x.invalid/d", "base"),
        ("article_qunar", "去哪儿攻略", "https://x.invalid/e", "base"),
    ]
    write_json(dl / "article_source_plan.json", {
        "payload": {
            "sources": [
                {
                    "source_id": sid,
                    "platform": platform,
                    "url": url,
                    "sourceUseMode": "factual_reference_only",
                    "body": source_body,
                    "sourceRole": role,
                    "imageEvidenceMode": "same_authorized_collection",
                    "imageUrls": [
                        {
                            "url": f"https://img.invalid/{sid}.jpg",
                            "platform": platform,
                            "license": "CC-BY-SA 4.0",
                            "credit": f"{platform} fixture",
                            "sourceUrl": f"https://img.invalid/{sid}.jpg",
                            "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                            "licenseSnapshot": "CC-BY-SA 4.0 test fixture",
                            "authorizationProof": f"fixture article source image rights {sid}",
                            "usageScope": "app_publish",
                            "width": 960,
                            "height": 640,
                            "caption": f"测试景区甲 {sid} 同源配图",
                            "relevance": "直接呈现测试景区甲正文底稿对应景观",
                        }
                    ],
                }
                for sid, platform, url, role in article_sources
            ],
        }
    })
    write_json(dl / "image_source_plan.json", {
        "payload": {
            "collections": [
                {
                    "sourceCollectionId": "fixture:collection:a",
                    "creator": "测试摄影师甲",
                    "credit": "测试摄影师甲",
                    "collectionPageUrl": "https://img.invalid/collection/a",
                    "platform": "Wikimedia Commons",
                    "license": "CC-BY-SA 4.0",
                    "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                    "licenseSnapshot": "CC-BY-SA 4.0 test fixture",
                    "authorizationProof": "fixture image collection a rights",
                    "usageScope": "app_publish",
                    "images": [
                        {
                            "url": "https://img.invalid/a.jpg",
                            "sourceUrl": "https://img.invalid/a.jpg",
                            "width": 960,
                            "height": 640,
                            "contentType": "image/jpeg",
                            "caption": "测试景区甲栈道实拍",
                            "relevance": "直接呈现测试景区甲核心景区栈道",
                        }
                    ],
                },
                {
                    "sourceCollectionId": "fixture:collection:b",
                    "creator": "测试摄影师乙",
                    "credit": "测试摄影师乙",
                    "collectionPageUrl": "https://img.invalid/collection/b",
                    "platform": "Wikimedia Commons",
                    "license": "CC-BY-SA 4.0",
                    "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                    "licenseSnapshot": "CC-BY-SA 4.0 test fixture",
                    "authorizationProof": "fixture image collection b rights",
                    "usageScope": "app_publish",
                    "images": [
                        {
                            "url": "https://img.invalid/b.jpg",
                            "sourceUrl": "https://img.invalid/b.jpg",
                            "width": 960,
                            "height": 640,
                            "contentType": "image/jpeg",
                            "caption": "测试景区甲森林实拍",
                            "relevance": "直接呈现测试景区甲核心景区森林步道",
                        }
                    ],
                },
            ],
        }
    })


def _run_pipeline_with_fake_download(ctx: run_mod.PipelineContext) -> int:
    import download.handler as download_handler_mod

    img_home = _real_jpeg(3)
    img_a = _real_jpeg(11)
    img_b = _real_jpeg(97)

    def _fake_payload(url, *, min_bytes=3000):
        import hashlib as _h

        body = {
            "https://img.invalid/home.jpg": img_home,
            "https://img.invalid/a.jpg": img_a,
            "https://img.invalid/b.jpg": img_b,
        }.get(url, img_a)
        return {
            "url": url,
            "ext": ".jpg",
            "bytes": body,
            "contentType": "image/jpeg",
            "sha256": _h.sha256(body).hexdigest(),
        }

    def _fake_source_fetch(url: str, **_kwargs):
        fetched_text = "\n\n".join(
            [
                f"{_EID}位于测试省山地森林地带，适合安排半日到一日游。",
                f"{_EID}景区开放时间、门票、观光车与交通接驳信息需要在出发前确认，节假日还要关注预约和限流。",
                f"{_EID}主景段和栈道段体验差异明显，核心停留点之间需要一定徒步时间，清晨进入能减少排队。",
                f"{_EID}如果遇到雨天，路况会更湿滑，返程和补给都要预留冗余，亲子和老人同行要控制强度。",
                f"{_EID}的游览决策应结合门票费用、开放时段、交通耗时、现场停留、海拔起伏和应急路线。",
            ]
            * 3
        )
        return {
            "url": url,
            "statusCode": 200,
            "htmlBytes": b"<html></html>",
            "text": fetched_text,
            "sha256": "sha-source",
        }

    orig_payload = download_handler_mod.fetch_image_payload
    orig_source = download_handler_mod.fetch_source_payload
    try:
        download_handler_mod.fetch_image_payload = _fake_payload
        download_handler_mod.fetch_source_payload = _fake_source_fetch
        return run_mod.run_pipeline(ctx)
    finally:
        download_handler_mod.fetch_image_payload = orig_payload
        download_handler_mod.fetch_source_payload = orig_source


def _long_base_text(title: str) -> str:
    sentence = (
        f"{title}的底稿围绕入口动线、核心景观、停留节奏、季节差异和安全边界展开，"
        "其中图片记录的是同一来源页面内的现场画面，文字说明与图片主题保持一致。"
        "这段资料只用于事实核验，成稿需要重新组织结构和表达。"
    )
    return "# 底稿\n\n" + "\n\n".join(sentence for _ in range(12))


def _write_source_unit(
    *,
    task_id: str,
    batch_id: str,
    unit_rel: str,
    source_kind: str,
    source_text: str,
    asset_name: str,
    seed: int,
    collection_id: str,
    creator: str,
) -> dict[str, str]:
    unit = batch_root(task_id, batch_id) / unit_rel
    unit.mkdir(parents=True, exist_ok=True)
    (unit / "source.md").write_text(source_text, encoding="utf-8")
    assets = unit / "assets"
    assets.mkdir(exist_ok=True)
    data = _real_jpeg(seed)
    (assets / asset_name).write_bytes(data)
    sha = hashlib.sha256(data).hexdigest()
    write_json(unit / "meta.json", {
        "sourceKind": source_kind,
        "platform": source_kind,
        "sourceUseMode": "factual_reference_only",
        "sourceCollectionId": collection_id,
        "creator": creator,
        "collectionPageUrl": f"https://source.invalid/{collection_id}",
        "license": "CC-BY-SA 4.0",
        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
        "authorizationProof": f"https://source.invalid/{collection_id}/license",
        "licenseSnapshot": {"license": "CC-BY-SA 4.0", "capturedAt": "2026-06-14T00:00:00Z"},
    })
    return {
        "sourceRef": f"{unit_rel}/source.md",
        "sourceAssetRef": f"{unit_rel}/assets/{asset_name}",
        "sha256": sha,
        "assetName": asset_name,
        "sourceCollectionId": collection_id,
        "creator": creator,
        "collectionPageUrl": f"https://source.invalid/{collection_id}",
        "license": "CC-BY-SA 4.0",
        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
        "authorizationProof": f"https://source.invalid/{collection_id}/license",
    }


def _approved_review_payload() -> dict:
    return {
        "decision": "approved",
        "issues": [],
        "checks": {name: {"passed": True, "issues": []} for name in sorted(ARTICLE_HARD_CHECKS)},
    }


def _seed_publish_inputs(task_id: str, batch_id: str) -> None:
    runtime_batch = batch_root(task_id, batch_id)
    shared = runtime_batch / "_shared"
    shared.mkdir(parents=True, exist_ok=True)
    ledger_assignments: dict[str, str] = {}

    homepage_source = _write_source_unit(
        task_id=task_id,
        batch_id=batch_id,
        unit_rel=f"entities/地点/景区/{_EID}/1.download/sources/homepage_primary",
        source_kind="Wikipedia百科",
        source_text=_long_base_text(f"{_EID}实体介绍"),
        asset_name="homepage_cover.jpg",
        seed=21,
        collection_id="fixture:homepage:primary",
        creator="测试百科图片作者",
    )

    entity_batch_dir = runtime_batch / "entities" / "地点" / "景区" / _EID
    entity_batch_dir.mkdir(parents=True, exist_ok=True)
    (entity_batch_dir / "assets").mkdir(exist_ok=True)
    (entity_batch_dir / "assets" / "homepage_cover.jpg").write_bytes(_real_jpeg(21))
    write_json(entity_batch_dir / "_entity.json", {
        "entityRef": f"/entity/地点/景区/{_EID}",
        "label": _EID,
        "tagRefs": ["四川省", "景区"],
        "geoTagRef": "四川省",
        "sourceTaskId": task_id,
    })
    (entity_batch_dir / "page.md").write_text(
        f"# {_EID}\n\n{_EID}是测试省的百科型景区实体主页，用于验证发布证据链。",
        encoding="utf-8",
    )
    write_json(entity_batch_dir / "manifest.json", {
        "entityRef": f"/entity/地点/景区/{_EID}",
        "sourceTaskId": task_id,
        "tagRefs": ["四川省", "景区"],
        "assets": [
            {
                "assetId": "homepage_cover",
                "fileName": "homepage_cover.jpg",
                "caption": f"{_EID}百科主图",
                **homepage_source,
            }
        ],
    })
    quality_dir = entity_batch_dir / "2.quality"
    quality_dir.mkdir(exist_ok=True)
    write_json(quality_dir / "quality_analysis.json", {"baseDraft": {"sourceRef": homepage_source["sourceRef"]}})
    compose_dir = entity_batch_dir / "3.compose"
    compose_dir.mkdir(exist_ok=True)
    write_json(compose_dir / "entity_page_input.json", {"baseDraft": {"sourceRef": homepage_source["sourceRef"]}})
    review_dir = entity_batch_dir / "5.review"
    review_dir.mkdir(exist_ok=True)
    write_json(review_dir / "review.json", {"decision": "approved", "issues": []})

    entities_dir = task_data(task_id).entities_dir()
    entity_dir = entities_dir / "地点" / "景区" / _EID
    entity_dir.mkdir(parents=True, exist_ok=True)
    write_json(entity_dir / "_entity.json", {
        "entityRef": f"/entity/地点/景区/{_EID}",
        "label": _EID,
        "tagRefs": ["四川省", "景区"],
        "geoTagRef": "四川省",
        "sourceTaskId": task_id,
    })
    (entity_dir / "page.md").write_text(f"# {_EID}\n\n这是用于 publish 回归的实体主页。", encoding="utf-8")
    write_json(entity_dir / "manifest.json", {
        "entityRef": f"/entity/地点/景区/{_EID}",
        "sourceTaskId": task_id,
        "tagRefs": ["四川省", "景区"],
    })

    for index, title in enumerate((f"{_EID} 规划咨询", f"{_EID} 体验决策"), start=1):
        topic_id = f"{_EID}-article-{index:03d}"
        article_source = _write_source_unit(
            task_id=task_id,
            batch_id=batch_id,
            unit_rel=f"posts/article/攻略/{title}/{index:03d}/1.download/sources/base",
            source_kind="官方图文资料",
            source_text=_long_base_text(title),
            asset_name=f"article_{index}.jpg",
            seed=30 + index,
            collection_id=f"fixture:article:{index}",
            creator=f"测试图文作者{index}",
        )
        ledger_assignments[article_source["sourceRef"]] = topic_id
        post_dir = batch_posts_root(task_id, batch_id) / "article" / "攻略" / title / f"{index:03d}"
        assets_dir = post_dir / "assets"
        post_dir.mkdir(parents=True, exist_ok=True)
        assets_dir.mkdir(exist_ok=True)
        (assets_dir / f"article_{index}.jpg").write_bytes(_real_jpeg(30 + index))
        (post_dir / "article.md").write_text(f"# {title}\n\n这是用于 publish 的真实成品正文。", encoding="utf-8")
        write_json(post_dir / "manifest.json", {
            "contentType": "article",
            "publishTitle": title,
            "title": title,
            "topicId": topic_id,
            "sourceTaskId": task_id,
            "sourceBatchId": batch_id,
            "entityRefs": [f"/entity/地点/景区/{_EID}"],
            "tagRefs": ["四川省", "景区"],
            "assets": [
                {
                    "assetId": f"article_{index}",
                    "fileName": f"article_{index}.jpg",
                    "caption": f"{_EID}{'入口动线' if index == 1 else '核心景观'}实拍",
                    "alignmentEvidence": f"图片对应《{title}》底稿中关于{'入口动线' if index == 1 else '核心景观'}的段落。",
                    **article_source,
                }
            ],
        })
        dl_dir = post_dir / "1.download"
        dl_dir.mkdir(exist_ok=True)
        write_json(dl_dir / "source_refs.json", {
            "baseSourceRef": article_source["sourceRef"],
            "primaryEvidenceRef": article_source["sourceRef"],
            "supportingEvidenceRefs": [],
        })
        compose_dir = post_dir / "3.compose"
        compose_dir.mkdir(exist_ok=True)
        write_json(compose_dir / "writing_pack.json", {
            "baseSourceRef": article_source["sourceRef"],
            "sourceUseMode": "factual_reference_only",
            "baseDraftText": _long_base_text(title),
        })
        draft_dir = post_dir / "4.draft"
        draft_dir.mkdir(exist_ok=True)
        (draft_dir / "prompt.md").write_text(
            "## 事实参考材料（只取可核验事实，必须独立表达）\n\n"
            "只抽取事实，独立拟定标题、结构和句子。\n",
            encoding="utf-8",
        )
        review_dir = post_dir / "5.review"
        review_dir.mkdir(parents=True, exist_ok=True)
        write_json(review_dir / "review.json", _approved_review_payload())
        write_json(review_dir / "review_ledger.json", {
            "schemaVersion": "quwoquan_data.review_ledger",
            "taskId": task_id,
            "batchId": batch_id,
            "ref": title,
            "policy": {
                "autoApprove": {"agentMinScore": 3, "requireHumanWhenDoubtful": True, "autoDiscardScoreAtMost": 1},
                "reprocess": {"maxAttempts": 3},
            },
            "article": {
                "kind": "article",
                "target": title,
                "agentJudgment": "credible",
                "agentScore": 4,
                "humanJudgment": "unjudged",
                "humanScore": None,
                "humanOverride": None,
                "reprocessCount": 0,
                "reasons": [],
                "notes": "",
            },
            "images": [],
            "facts": [],
        })
        write_json(review_dir / "review_entities.json", {
            "schemaVersion": "quwoquan_data.review_entities",
            "ref": title,
            "entities": [
                {
                    "name": _EID,
                    "domain": "地点",
                    "type": "景区",
                    "ref": f"/entity/地点/景区/{_EID}",
                    "hasHomepage": True,
                    "generated": False,
                    "evidenceRef": "",
                }
            ],
        })

    for index, collection in enumerate(("fixture:collection:a", "fixture:collection:b"), start=1):
        image_source = _write_source_unit(
            task_id=task_id,
            batch_id=batch_id,
            unit_rel=f"posts/image/画报/{_EID} 图像作品{index}/{index:03d}/1.download/sources/collection",
            source_kind="官方图库",
            source_text=f"# {_EID} 图像作品{index}\n\n同一作品集的授权图片。",
            asset_name=f"image_{index}.jpg",
            seed=40 + index,
            collection_id=collection,
            creator=f"测试摄影师{index}",
        )
        image_dir = batch_posts_root(task_id, batch_id) / "image" / "画报" / f"{_EID} 图像作品{index}" / f"{index:03d}"
        assets_dir = image_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        asset_name = f"image_{index}.jpg"
        (assets_dir / asset_name).write_bytes(_real_jpeg(40 + index))
        write_json(image_dir / "manifest.json", {
            "contentType": "image",
            "carrier": "image",
            "title": f"{_EID} 图像作品{index}",
            "caption": "",
            "sourceTaskId": task_id,
            "sourceBatchId": batch_id,
            "entityRefs": [f"/entity/地点/景区/{_EID}"],
            "tagRefs": ["四川省", "景区"],
            "sourceCollectionId": collection,
            "creator": f"测试摄影师{index}",
            "collectionPageUrl": f"https://img.invalid/collection/{index}",
            "license": "CC-BY-SA 4.0",
            "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
            "authorizationProof": f"https://source.invalid/{collection}/license",
            "assets": [
                {
                    "assetId": f"image_{index}",
                    "fileName": asset_name,
                    "sourceRef": image_source["sourceRef"],
                    "sourceAssetRef": image_source["sourceAssetRef"],
                    "sha256": image_source["sha256"],
                    "sourceCollectionId": collection,
                    "creator": f"测试摄影师{index}",
                    "collectionPageUrl": f"https://img.invalid/collection/{index}",
                    "license": "CC-BY-SA 4.0",
                    "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                    "authorizationProof": f"https://source.invalid/{collection}/license",
                }
            ],
        })
        review_dir = image_dir / "5.review"
        review_dir.mkdir(parents=True, exist_ok=True)
        write_json(review_dir / "review.json", {"decision": "approved", "issues": []})
        write_json(
            review_dir / "provenance.json",
            {
                "sourceCollectionId": collection,
                "creator": f"测试摄影师{index}",
                "collectionPageUrl": f"https://img.invalid/collection/{index}",
                "license": "CC-BY-SA 4.0",
                "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                "authorizationProof": f"https://source.invalid/{collection}/license",
            },
        )

    write_json(shared / "base_draft_ledger.json", {
        "schemaVersion": "quwoquan_data.base_draft_ledger",
        "taskId": task_id,
        "batchId": batch_id,
        "assignments": ledger_assignments,
    })


def test_first_run_pauses_at_download_plan():
    task_id = _make_task()
    code = run_mod.run_pipeline(_ctx(task_id, "b1"))
    assert code == 10, f"expected pause(10), got {code}"
    state = run_mod.load_workflow_state(task_id, "b1")
    assert state["waitingCheckpoint"] == "download_plan"
    assert "download_fetch" not in state["completed"]


def test_resume_advances_after_source_plan():
    task_id = _make_task()
    run_mod.run_pipeline(_ctx(task_id, "b2"))  # pause at download_plan
    _seed_source_plan(task_id, "b2")
    ctx = _ctx(task_id, "b2")
    ctx.until = "build_prepare"
    code = _run_pipeline_with_fake_download(ctx)  # resume
    assert code == 0, f"expected stopped-at-until success(0), got {code}"
    state = run_mod.load_workflow_state(task_id, "b2")
    # download_plan/fetch/build_prepare 应已完成，并在 build_prepare 截止点停住。
    assert "download_plan" in state["completed"]
    assert "download_fetch" in state["completed"]
    assert "build_prepare" in state["completed"]
    assert "build_homepage" not in state["completed"]
    assert state["status"] == "stopped_at_until"
    assert state["stoppedAtStage"] == "build_prepare"


def test_build_prepare_blocks_missing_homepage_base_draft():
    task_id = _make_task()
    ctx = _ctx(task_id, "build_prepare_missing_homepage")

    result = run_mod._run_build_prepare(ctx)

    assert result.status == "failed"
    assert result.fallback_stage == "download_plan"
    assert any("baseDraft.sourceRef is empty" in issue for issue in result.issues), result.issues


def test_rewind_drops_target_and_subsequent():
    """ReAct 回退：rewind 到 produce_compose 应清掉它及之后所有 stage，保留之前。"""
    completed = set(run_mod.STAGE_NAMES)  # 全完成
    kept = run_mod._rewind_to(completed, "produce_compose")
    assert "produce_compose" not in kept
    assert "produce_review" not in kept
    assert "publish" not in kept
    assert "download_fetch" in kept and "build_validate" in kept


def test_react_rewind_respects_max_and_writes_repair():
    """ReAct 回退计数到上限后不再回退；回退时写 repair_report。"""
    task_id = _make_task()
    state = run_mod.load_workflow_state(task_id, "rw1")
    ctx = _ctx(task_id, "rw1")
    completed = set(run_mod.STAGE_NAMES)
    fail = run_mod.StageResult("produce_review", run_mod.AUTO, "failed",
                               "发布门未过", fallback_stage="download", issues=["x"])
    # 前 MAX 次应成功回退
    for i in range(run_mod.MAX_REACT_REWINDS):
        completed, ok = run_mod._react_rewind(ctx, state, completed, fail)
        assert ok, f"rewind {i} should succeed"
        assert "download_plan" not in completed  # download→download_plan 已回退
        completed = set(run_mod.STAGE_NAMES)  # 模拟重跑后再次失败
    # 超限后不再回退
    _, ok = run_mod._react_rewind(ctx, state, completed, fail)
    assert ok is False
    # repair_report 已落盘
    from _common.paths import batch_results_dir
    repair_dir = batch_results_dir(task_id, "rw1", "workflow_run", "repair_report")
    assert repair_dir.is_dir() and any(repair_dir.glob("*.json"))


def test_until_stops_early():
    task_id = _make_task()
    run_mod.run_pipeline(_ctx(task_id, "b3"))
    _seed_source_plan(task_id, "b3")
    ctx = _ctx(task_id, "b3")
    ctx.until = "download_fetch"
    code = _run_pipeline_with_fake_download(ctx)
    assert code == 0, f"expected clean stop(0) at --until, got {code}"
    state = run_mod.load_workflow_state(task_id, "b3")
    assert "download_fetch" in state["completed"]
    assert "build_homepage" not in state["completed"]
    assert state["status"] == "stopped_at_until"
    assert state["stoppedAtStage"] == "download_fetch"


def test_until_completed_checkpoint_stops_without_downstream(monkeypatch):
    task_id = _make_task()
    batch_id = "until_completed_download_plan"
    ctx = _ctx(task_id, batch_id)
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["completed"] = ["download_plan"]
    run_mod.save_workflow_state(state)
    ctx.until = "download_plan"

    monkeypatch.setattr("task.run._source_plan_filled", lambda _ctx: (True, []))
    monkeypatch.setattr("task.run._stale_source_plan_entities", lambda _ctx, entity_ids: [])

    code = run_mod.run_pipeline(ctx)

    assert code == 0
    state = run_mod.load_workflow_state(task_id, batch_id)
    assert state["status"] == "stopped_at_until"
    assert state["stoppedAtStage"] == "download_plan"
    assert "download_fetch" not in state["completed"]


def test_until_completed_checkpoint_revalidates_before_downstream(monkeypatch):
    task_id = _make_task()
    batch_id = "until_revalidate_download_plan"
    ctx = _ctx(task_id, batch_id)
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["completed"] = ["download_plan"]
    run_mod.save_workflow_state(state)
    ctx.until = "download_plan"

    monkeypatch.setattr(
        "task.run._source_plan_filled",
        lambda _ctx: (False, ["article sources=1 need>=2"]),
    )
    monkeypatch.setenv("QWQ_DOWNLOAD_AUTO_RESEARCH", "0")

    code = run_mod.run_pipeline(ctx)

    assert code == 10
    state = run_mod.load_workflow_state(task_id, batch_id)
    assert state["waitingCheckpoint"] == "download_plan"
    assert "download_plan" not in state["completed"]
    assert "download_fetch" not in state["completed"]
    assert any("article sources=0 need>=2" in item for item in state["failedObjects"])
    assert not any("article sources=1 need>=2" in item for item in state["failedObjects"])


def test_waiting_checkpoint_replaces_stale_failed_objects(monkeypatch):
    task_id = _make_task()
    batch_id = "waiting_replaces_stale_failed_objects"
    ctx = _ctx(task_id, batch_id)
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["failedObjects"] = ["旧景区: article sources=1 need>=2"]
    run_mod.save_workflow_state(state)

    monkeypatch.setattr(
        "task.run._source_plan_filled",
        lambda _ctx: (False, ["新景区: image collections=1 need>=2"]),
    )
    monkeypatch.setattr(
        "task.run._download_plan_unresolved_entities",
        lambda _ctx: {_EID: {"image": ["image collections=1 need>=2"]}},
    )
    monkeypatch.setenv("QWQ_DOWNLOAD_AUTO_RESEARCH", "0")

    code = run_mod.run_pipeline(ctx)

    assert code == 10
    state = run_mod.load_workflow_state(task_id, batch_id)
    assert state["waitingCheckpoint"] == "download_plan"
    assert state["failedObjects"] == [
        f"{_EID}: source_plan: image: image collections=1 need>=2"
    ]


def test_author_checkpoint_only_reads_packaged_drafts():
    task_id = _make_task()
    batch_id = "drafts1"
    ensure_batch_layout(task_id, batch_id, "produce")
    ctx = _ctx(task_id, batch_id)
    legacy = batch_command_root(task_id, batch_id, "produce") / "drafts" / "旧.article.md"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text("# 旧平铺正文\n\n这不应被新 checkpoint 识别。", encoding="utf-8")
    ok, pending = run_mod._drafts_authored(ctx)
    assert ok is False
    assert pending == ["(no content objects; run compose-brief first)"]

    content_object.register_content_object(task_id, batch_id, "新", content_type="article", angle="体验", title="新")
    write_placeholder_draft(task_id, batch_id, "新")
    ok, pending = run_mod._drafts_authored(ctx)
    assert ok is False and pending == ["新"]
    report = run_mod.mark_abandoned_content_refs(
        task_id,
        batch_id,
        ["新"],
        stage="produce_author",
        reason="agent_unrecoverable: fixture object skipped",
    )
    assert report["added"] == ["新"]
    ok, pending = run_mod._drafts_authored(ctx)
    assert ok is True and pending == []
    draft_article_path(task_id, batch_id, "新").write_text("# 新正文\n\n这是 Agent 完成的正文。", encoding="utf-8")
    ok, pending = run_mod._drafts_authored(ctx)
    assert ok is True and pending == []


def test_content_object_index_schema_has_single_contract_name():
    task_id = _make_task()
    batch_id = "content_index_schema"
    content_object.write_brief_object(
        task_id,
        batch_id,
        "schema_ref",
        {
            "titleHint": f"{_EID}·行前建议",
            "templateId": "travel.entity.guide",
            "carrier": "article",
            "writingIntent": "planning_consultation",
            "mustIncludeFacts": ["fixture"],
        },
        content_type="article",
    )
    index = read_json(batch_root(task_id, batch_id) / "_shared" / "content_object_index.json")
    assert index["schemaVersion"] == "quwoquan_data.content_object_index"
    assert "/1" not in index["schemaVersion"]


def test_content_plan_prunes_briefs_outside_packet_index():
    from _common.content_plan import CONTENT_PLAN_SCHEMA, validate_content_plan

    task_id = _make_task()
    batch_id = "content_plan_prune_extra_brief"
    root = batch_root(task_id, batch_id)
    ensure_batch_layout(task_id, batch_id, "produce")
    evidence = (
        root
        / "entities"
        / "地点"
        / "景区"
        / _EID
        / "1.download"
        / "sources"
        / "01.article_fixture"
        / "source.md"
    )
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text("fixture source", encoding="utf-8")
    evidence_ref = evidence.relative_to(root).as_posix()
    item = {
        "ref": f"{_EID}_planning_consultation",
        "kind": "entity",
        "carrier": "article",
        "researchLane": "article",
        "title": f"{_EID}·行前建议",
        "entityRefs": [f"/entity/地点/景区/{_EID}"],
        "evidenceRefs": [evidence_ref],
        "rationale": "fixture evidence plan",
    }
    write_json(
        root / "_shared" / "content_plan_packet.json",
        {"schemaVersion": CONTENT_PLAN_SCHEMA, "items": [item]},
    )
    content_object.write_brief_object(
        task_id,
        batch_id,
        item["ref"],
        {
            "titleHint": item["title"],
            "templateId": "travel.entity.guide",
            "carrier": "article",
            "entityRefs": item["entityRefs"],
            "mustIncludeFacts": ["fixture"],
        },
        content_type="article",
    )
    stale_brief = root / "posts" / "image" / "攻略" / f"{_EID}·旧图集" / "1" / "3.compose" / "brief.json"
    stale_brief.parent.mkdir(parents=True, exist_ok=True)
    write_json(stale_brief, {"titleHint": f"{_EID}·旧图集", "carrier": "image"})

    spec = {
        "scope": {"coverageTargets": [{"name": _EID}]},
        "content": {"modalityContract": "separated_research", "quotas": {}},
        "acceptance": {},
    }
    issues = validate_content_plan(task_id, batch_id, spec)
    assert any("posts contains brief(s) outside content_plan_packet/index" in issue for issue in issues), issues

    ctx = _ctx(task_id, batch_id)
    removed = run_mod._prune_content_plan_extra_briefs(ctx)
    assert any(f"{_EID}·旧图集" in item for item in removed), removed
    assert not stale_brief.exists()
    issues = validate_content_plan(task_id, batch_id, spec)
    assert not any("posts contains brief(s) outside content_plan_packet/index" in issue for issue in issues), issues


def test_produce_review_rewind_invalidates_failed_ref_outputs():
    task_id = _make_task()
    batch_id = "retry1"
    ensure_batch_layout(task_id, batch_id, "produce")
    ctx = _ctx(task_id, batch_id)

    brief_ok = {
        "titleHint": f"{_EID}·顺游攻略",
        "templateId": "travel.route.guide",
        "carrier": "article",
        "writingIntent": "planning_consultation",
        "mustIncludeFacts": ["预约"],
    }
    brief_bad = {
        **brief_ok,
        "titleHint": f"{_EID}·避峰攻略",
    }
    content_object.write_brief_object(task_id, batch_id, "ref_ok", brief_ok, content_type="article")
    content_object.write_brief_object(task_id, batch_id, "ref_bad", brief_bad, content_type="article")

    write_placeholder_draft(task_id, batch_id, "ref_ok")
    write_placeholder_draft(task_id, batch_id, "ref_bad")
    oq.enqueue_ref_job(task_id, batch_id, "ref_ok", "author")
    oq.enqueue_ref_job(task_id, batch_id, "ref_bad", "author")
    draft_article_path(task_id, batch_id, "ref_ok").write_text("# 已完成\n\n正文。", encoding="utf-8")
    draft_article_path(task_id, batch_id, "ref_bad").write_text("# 旧稿\n\n需要重写。", encoding="utf-8")
    write_json(
        draft_article_path(task_id, batch_id, "ref_bad").parent / "author_self_check.json",
        {"ok": False},
    )

    bad_obj = content_object.content_object_dir(task_id, batch_id, "ref_bad")
    bad_obj.mkdir(parents=True, exist_ok=True)
    (bad_obj / "5.review").mkdir(parents=True, exist_ok=True)
    (bad_obj / "article.md").write_text("# 旧成品\n\n旧正文。", encoding="utf-8")
    write_json(bad_obj / "manifest.json", {"reviewDecision": "approved"})
    write_json(bad_obj / "5.review" / "ref_review_gate.json", {"passed": True})
    assets_dir = bad_obj / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    (assets_dir / "a.jpg").write_text("x", encoding="utf-8")

    write_gate_report(
        task_id=task_id,
        batch_id=batch_id,
        command="produce",
        step="review",
        ref="ref_bad",
        passed=False,
        issues=["skeletonSimilarity: heading sequence too similar to a peer (0.85)"],
        fallback_stage="agent_compose",
    )

    result = run_mod.StageResult(
        "produce_review",
        run_mod.AUTO,
        "failed",
        "发布门未过",
        fallback_stage="agent_compose",
        issues=[f"{content_object.content_object_rel(task_id, batch_id, 'ref_bad')}: skeletonSimilarity"],
    )
    state = run_mod.load_workflow_state(task_id, batch_id)
    completed = set(run_mod.STAGE_NAMES)

    completed, ok = run_mod._react_rewind(ctx, state, completed, result)
    assert ok is True
    assert "produce_compose" not in completed
    assert "produce_author" not in completed
    assert run_mod._drafts_authored(ctx) == (False, ["ref_bad"])
    assert "<!-- QWQ_AWAITING_AGENT_DRAFT -->" in draft_article_path(task_id, batch_id, "ref_bad").read_text(encoding="utf-8")
    assert not (bad_obj / "article.md").exists()
    assert not (bad_obj / "manifest.json").exists()
    assert not (bad_obj / "5.review" / "ref_review_gate.json").exists()
    assert not (bad_obj / "assets").exists()
    assert draft_article_path(task_id, batch_id, "ref_ok").read_text(encoding="utf-8") == "# 已完成\n\n正文。"
    queue = oq.queue_summary(task_id, batch_id)
    assert "ref_bad" in queue["byState"]["queued"], queue


def test_produce_review_rewind_to_download_purges_stale_author_queue():
    task_id = _make_task()
    batch_id = "retry_download"
    ensure_batch_layout(task_id, batch_id, "produce")
    ctx = _ctx(task_id, batch_id)

    brief = {
        "titleHint": f"{_EID}·图集",
        "templateId": "travel.gallery",
        "carrier": "gallery",
        "writingIntent": "post_trip_journal",
        "mustIncludeFacts": ["云海"],
    }
    content_object.write_brief_object(task_id, batch_id, "ref_a", brief, content_type="image")
    content_object.write_brief_object(task_id, batch_id, "ref_b", brief, content_type="image")
    write_placeholder_draft(task_id, batch_id, "ref_a")
    write_placeholder_draft(task_id, batch_id, "ref_b")
    oq.enqueue_ref_job(task_id, batch_id, "ref_a", "author")
    oq.enqueue_ref_job(task_id, batch_id, "ref_b", "author")

    result = run_mod.StageResult(
        "produce_review",
        run_mod.AUTO,
        "failed",
        "发布门未过",
        fallback_stage="download_plan",
        issues=["images must be recollected"],
    )
    state = run_mod.load_workflow_state(task_id, batch_id)
    completed = set(run_mod.STAGE_NAMES)

    completed, ok = run_mod._react_rewind(ctx, state, completed, result)
    assert ok is True
    assert "download_fetch" not in completed
    queue = oq.queue_summary(task_id, batch_id)
    assert queue["total"] == 0, queue


def test_publish_stage_materializes_task_inputs_and_release():
    task_id = _make_task()
    batch_id = "publish1"
    _seed_publish_inputs(task_id, batch_id)
    first_title = f"{_EID} 规划咨询"
    post_dir = batch_posts_root(task_id, batch_id) / "article" / "攻略" / first_title / "001"
    (post_dir / "_author_run.py").write_text("raise RuntimeError('must not ship')\n", encoding="utf-8")
    (post_dir / "_article_body.md").write_text("helper", encoding="utf-8")
    oq.enqueue_ref_job(task_id, batch_id, f"{_EID} 攻略", "author", max_attempts=1)
    job = oq.acquire_lease(task_id, batch_id, worker="w1", stage="author")
    assert job is not None
    oq.fail_job(task_id, batch_id, job["jobId"], job["lease"], error="dead now")
    ctx = _ctx(task_id, batch_id)
    result = run_mod._run_publish(ctx)
    assert result.status == "done", result.message
    assert task_entities(task_id).exists()
    assert task_tags(task_id).exists()
    assert task_shared_dir(task_id).is_dir()
    release_id = run_mod._workflow_release_id(task_id, batch_id)
    release_root_dir = release_root(release_id)
    assert (release_root_dir / "release_manifest.json").exists()
    assert (release_root_dir / "entities" / "地点" / "景区" / _EID / "page.md").exists()
    assert not (release_root_dir / "entity_pages").exists()
    assert not (release_root_dir / "graph").exists()
    assert not (release_root_dir / "tags").exists()
    release_post_dir = release_root_dir / "posts" / "article" / "攻略" / first_title / "001"
    assert (release_post_dir / "5.review" / "review_ledger.json").exists()
    assert not (release_post_dir / "_author_run.py").exists()
    assert not (release_post_dir / "_article_body.md").exists()
    queue = oq.queue_summary(task_id, batch_id)
    assert queue["total"] == 0, queue


def test_managed_loop_consumes_checkpoint_instead_of_returning_10():
    task_id = _make_task()
    ctx = _ctx(task_id, "managed1")
    ctx.managed = True
    calls = {"pipeline": 0, "checkpoint": 0}
    original_pipeline = run_mod.run_pipeline
    original_checkpoint = run_mod._run_managed_checkpoint
    try:
        def _fake_pipeline(_ctx):
            calls["pipeline"] += 1
            if calls["pipeline"] == 1:
                state = run_mod.load_workflow_state(task_id, "managed1")
                state["waitingCheckpoint"] = "download_plan"
                run_mod.save_workflow_state(state)
                return 10
            return 0

        def _fake_checkpoint(_ctx, stage):
            calls["checkpoint"] += 1
            assert stage == "download_plan"
            return True

        run_mod.run_pipeline = _fake_pipeline
        run_mod._run_managed_checkpoint = _fake_checkpoint
        assert run_mod.run_managed_pipeline(ctx) == 0
    finally:
        run_mod.run_pipeline = original_pipeline
        run_mod._run_managed_checkpoint = original_checkpoint
    assert calls == {"pipeline": 2, "checkpoint": 1}


def test_managed_loop_continues_when_infra_fails_but_checkpoint_gate_passes(monkeypatch):
    task_id = _make_task()
    batch_id = "managed_infra_gate_passes"
    ctx = _ctx(task_id, batch_id)
    ctx.managed = True
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["infrastructureRetryCounts"] = {
        "download_plan": run_mod.MAX_MANAGED_INFRA_RETRIES - 1
    }
    run_mod.save_workflow_state(state)
    calls = {"pipeline": 0, "checkpoint": 0}

    def _fake_pipeline(_ctx):
        calls["pipeline"] += 1
        if calls["pipeline"] == 1:
            state = run_mod.load_workflow_state(task_id, batch_id)
            state["waitingCheckpoint"] = "download_plan"
            run_mod.save_workflow_state(state)
            return 10
        return 0

    def _fake_checkpoint(_ctx, stage):
        calls["checkpoint"] += 1
        assert stage == "download_plan"
        state = run_mod.load_workflow_state(task_id, batch_id)
        state["lastAgentRun"] = {
            "stage": stage,
            "infrastructureFailures": 1,
            "outcomes": [
                {
                    "started": False,
                    "status": "error",
                    "error": "agent subprocess timed out after 240s",
                }
            ],
        }
        state["failedObjects"] = ["agent subprocess timed out after 240s"]
        run_mod.save_workflow_state(state)
        return False

    monkeypatch.setattr("task.run.run_pipeline", _fake_pipeline)
    monkeypatch.setattr("task.run._run_managed_checkpoint", _fake_checkpoint)
    monkeypatch.setattr("task.run._checkpoint_is_done", lambda _ctx, stage: (True, []))

    assert run_mod.run_managed_pipeline(ctx) == 0
    assert calls == {"pipeline": 2, "checkpoint": 1}
    final_state = run_mod.load_workflow_state(task_id, batch_id)
    assert final_state["failedObjects"] == []
    assert "checkpoint gate passed" in final_state["nextAction"]


def test_managed_download_infra_failure_cannot_abandon_strict_task(monkeypatch):
    task_id = _make_task()
    batch_id = "managed_strict_infra_no_abandon"
    ctx = _ctx(task_id, batch_id)
    ctx.managed = True
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["infrastructureRetryCounts"] = {
        "download_plan": run_mod.MAX_MANAGED_INFRA_RETRIES - 1
    }
    run_mod.save_workflow_state(state)

    def _fake_pipeline(_ctx):
        state = run_mod.load_workflow_state(task_id, batch_id)
        state["waitingCheckpoint"] = "download_plan"
        run_mod.save_workflow_state(state)
        return 10

    def _fake_checkpoint(_ctx, stage):
        state = run_mod.load_workflow_state(task_id, batch_id)
        state["lastAgentRun"] = {
            "stage": stage,
            "infrastructureFailures": 1,
            "outcomes": [{"started": False, "status": "error", "error": "internal error"}],
        }
        run_mod.save_workflow_state(state)
        return False

    unresolved = {_EID: {"article": ["article research needs >= 4 text-qualified base sources"]}}
    monkeypatch.setattr("task.run.run_pipeline", _fake_pipeline)
    monkeypatch.setattr("task.run._run_managed_checkpoint", _fake_checkpoint)
    monkeypatch.setattr("task.run._checkpoint_is_done", lambda _ctx, stage: (False, []))
    monkeypatch.setattr("task.run._download_plan_unresolved_entities", lambda _ctx: unresolved)

    assert run_mod.run_managed_pipeline(ctx) == 1
    final_state = run_mod.load_workflow_state(task_id, batch_id)
    assert final_state["status"] == "manual_required"
    assert final_state.get("abandonedObjects") == []
    assert "allowPartialContent is not true" in final_state["failedObjects"][0]


def test_managed_download_infra_failure_can_fast_fail_partial_task(monkeypatch):
    task_id = _make_task(workflow_policy={"allowPartialContent": True})
    spec = store.load_spec(task_id)
    spec["scope"]["coverageTargets"].append({"entityType": "地点/景区", "name": "测试景区乙"})
    store.save_spec(spec)
    batch_id = "managed_partial_infra_abandon"
    ctx = _ctx(task_id, batch_id)
    ctx.managed = True
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["infrastructureRetryCounts"] = {
        "download_plan": run_mod.MAX_MANAGED_INFRA_RETRIES - 1
    }
    run_mod.save_workflow_state(state)
    calls = {"pipeline": 0}

    def _fake_pipeline(_ctx):
        calls["pipeline"] += 1
        if calls["pipeline"] == 1:
            state = run_mod.load_workflow_state(task_id, batch_id)
            state["waitingCheckpoint"] = "download_plan"
            run_mod.save_workflow_state(state)
            return 10
        return 0

    def _fake_checkpoint(_ctx, stage):
        state = run_mod.load_workflow_state(task_id, batch_id)
        state["lastAgentRun"] = {
            "stage": stage,
            "infrastructureFailures": 1,
            "outcomes": [{"started": False, "status": "error", "error": "internal error"}],
        }
        run_mod.save_workflow_state(state)
        return False

    unresolved = {_EID: {"article": ["article research needs >= 4 text-qualified base sources"]}}
    monkeypatch.setattr("task.run.run_pipeline", _fake_pipeline)
    monkeypatch.setattr("task.run._run_managed_checkpoint", _fake_checkpoint)
    monkeypatch.setattr("task.run._checkpoint_is_done", lambda _ctx, stage: (False, []))
    monkeypatch.setattr("task.run._download_plan_unresolved_entities", lambda _ctx: unresolved)

    assert run_mod.run_managed_pipeline(ctx) == 0
    final_state = run_mod.load_workflow_state(task_id, batch_id)
    assert [item["entityId"] for item in final_state["abandonedObjects"]] == [_EID]
    assert "fast-failing source-unavailable" in final_state["nextAction"]


def test_download_plan_deterministic_license_failure_fast_fails_strict_task(monkeypatch):
    task_id = _make_task()
    batch_id = "download_plan_deterministic_strict"
    ctx = _ctx(task_id, batch_id)
    monkeypatch.setenv("QWQ_DOWNLOAD_AUTO_RESEARCH", "0")
    monkeypatch.setattr(
        "download.prepare.prepare_source_plan",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "task.run._source_plan_filled",
        lambda _ctx: (False, ["九寨沟 article source has unsupported license"]),
    )
    monkeypatch.setattr(
        "task.run._download_plan_unresolved_entities",
        lambda _ctx: {_EID: {"article": ["imageRights: unsupported license CC BY-SA 1.0"]}},
    )

    result = run_mod._checkpoint_download_plan(ctx)

    assert result.status == "failed"
    assert "deterministic_source_unavailable" in result.issues[0]
    assert "allowPartialContent is not true" in result.issues[0]


def test_download_plan_deterministic_license_failure_activates_reserve(monkeypatch):
    task_id = _make_task(workflow_policy={"allowPartialContent": True})
    spec = store.load_spec(task_id)
    spec["scope"]["reserveCoverageTargets"] = [{"entityType": "地点/景区", "name": "替补景区乙"}]
    store.save_spec(spec)
    batch_id = "download_plan_deterministic_reserve"
    ctx = _ctx(task_id, batch_id)
    monkeypatch.setenv("QWQ_DOWNLOAD_AUTO_RESEARCH", "0")
    monkeypatch.setattr(
        "download.prepare.prepare_source_plan",
        lambda *_args, **_kwargs: None,
    )

    def _filled(current_ctx):
        if _EID not in current_ctx.entity_ids:
            return True, []
        return False, ["测试景区甲 article source has unsupported license"]

    monkeypatch.setattr("task.run._source_plan_filled", _filled)
    monkeypatch.setattr(
        "task.run._download_plan_unresolved_entities",
        lambda current_ctx: (
            {_EID: {"article": ["imageRights: unsupported license CC BY-SA 1.0"]}}
            if _EID in current_ctx.entity_ids
            else {}
        ),
    )

    result = run_mod._checkpoint_download_plan(ctx)

    assert result.status == "done"
    state = run_mod.load_workflow_state(task_id, batch_id)
    assert [item["entityId"] for item in state["abandonedObjects"]] == [_EID]
    assert [item["entityId"] for item in state["replacementObjects"]] == ["替补景区乙"]
    availability = read_json(batch_root(task_id, batch_id) / "_shared" / "source_unavailable_targets.json")
    assert availability["readyTargets"] == ["替补景区乙"]


def test_download_plan_auto_research_repeats_replacement_waves(monkeypatch):
    task_id = _make_task(workflow_policy={"allowPartialContent": True})
    spec = store.load_spec(task_id)
    spec["scope"]["reserveCoverageTargets"] = [
        {"entityType": "地点/景区", "name": "替补景区乙"},
        {"entityType": "地点/景区", "name": "替补景区丙"},
    ]
    store.save_spec(spec)
    batch_id = "download_plan_auto_research_replacement_waves"
    ctx = _ctx(task_id, batch_id)
    monkeypatch.setattr(
        "download.prepare.prepare_source_plan",
        lambda *_args, **_kwargs: None,
    )

    def _filled(current_ctx):
        if "替补景区丙" in current_ctx.entity_ids:
            return True, []
        return False, ["image research needs enough rights-cleared source collections for 2 image work(s)"]

    def _report_for(entity_id: str) -> dict:
        if entity_id == "替补景区丙":
            return {
                "sourceAvailability": {
                    "readyTargets": ["替补景区丙"],
                    "ineligibleTargets": [],
                }
            }
        return {
            "sourceAvailability": {
                "readyTargets": [],
                "ineligibleTargets": [
                    {
                        "entityId": entity_id,
                        "issues": [f"{entity_id}: no rights-compatible open-license images discovered"],
                        "blockers": [
                            {
                                "lane": "image",
                                "reason": "no single-author/single-file rights-cleared image collection",
                                "nextAction": "manual_authorized_gallery_or_target_replacement",
                            }
                        ],
                        "nextActions": ["manual_authorized_gallery_or_target_replacement"],
                    }
                ],
            }
        }

    calls: list[list[str]] = []

    def _auto(current_ctx, entity_ids, *, entity_type, force=False, scope="primary"):
        del entity_type, force, scope
        calls.append(list(entity_ids))
        return _report_for(entity_ids[0])

    monkeypatch.setattr("task.run._source_plan_filled", _filled)
    monkeypatch.setattr("task.run._run_download_auto_research", _auto)

    result = run_mod._checkpoint_download_plan(ctx)

    assert result.status == "done"
    assert calls == [[_EID], ["替补景区乙"], ["替补景区丙"]]
    state = run_mod.load_workflow_state(task_id, batch_id)
    assert [item["entityId"] for item in state["abandonedObjects"]] == [_EID, "替补景区乙"]
    assert [
        item["entityId"]
        for item in state["replacementObjects"]
        if item.get("status") == "active"
    ] == ["替补景区丙"]
    assert [
        item["entityId"]
        for item in state["replacementObjects"]
        if item.get("status") == "rejected"
    ] == ["替补景区乙"]


def test_auto_research_replacement_wave_stops_without_new_target(monkeypatch):
    task_id = _make_task(workflow_policy={"allowPartialContent": True})
    spec = store.load_spec(task_id)
    spec["scope"]["coverageTargets"] = [
        {"entityType": "地点/景区", "name": _EID},
        {"entityType": "地点/景区", "name": "稳定景区乙"},
    ]
    spec["scope"]["reserveCoverageTargets"] = []
    store.save_spec(spec)
    batch_id = "download_plan_replacement_no_new_target"
    ctx = _ctx(task_id, batch_id)

    primary = {
        "sourceAvailability": {
            "readyTargets": [],
            "ineligibleTargets": [
                {
                    "entityId": _EID,
                    "issues": [f"{_EID}: no rights-compatible open-license images discovered"],
                    "blockers": [
                        {
                            "lane": "image",
                            "reason": "no single-author/single-file rights-cleared image collection",
                            "nextAction": "manual_authorized_gallery_or_target_replacement",
                        }
                    ],
                    "nextActions": ["manual_authorized_gallery_or_target_replacement"],
                }
            ],
        }
    }
    calls: list[list[str]] = []

    def _auto(current_ctx, entity_ids, *, entity_type, force=False, scope="primary"):
        del current_ctx, entity_type, force, scope
        calls.append(list(entity_ids))
        return primary

    monkeypatch.setattr("task.run._run_download_auto_research", _auto)
    monkeypatch.setattr("task.run._source_plan_filled", lambda _ctx: (False, ["still missing source"]))
    monkeypatch.setattr("task.run._download_plan_unresolved_entities", lambda _ctx: {_EID: {"image": ["still missing source"]}})

    ok, abandoned, missing, _report = run_mod._rerun_auto_research_with_replacements(
        ctx,
        primary,
        entity_type="地点/景区",
        reason_prefix="source_unavailable_after_auto_research",
    )

    assert ok is False
    assert abandoned == [_EID]
    assert missing == ["still missing source"]
    assert calls == []


def test_download_plan_repairable_source_gap_does_not_screen_replacements(monkeypatch):
    task_id = _make_task(workflow_policy={"allowPartialContent": True})
    spec = store.load_spec(task_id)
    spec["scope"]["reserveCoverageTargets"] = [
        {"entityType": "地点/景区", "name": "替补景区乙"},
    ]
    store.save_spec(spec)
    batch_id = "download_plan_repairable_gap_no_replacement"
    ctx = _ctx(task_id, batch_id)
    calls: list[list[str]] = []

    monkeypatch.setattr("download.prepare.prepare_source_plan", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "task.run._source_plan_filled",
        lambda _ctx: (
            False,
            [f"{_EID}: download_repair required: {_EID}: missing core source categories ['encyclopedia']"],
        ),
    )
    monkeypatch.setattr(
        "task.run._stale_source_plan_entities",
        lambda _ctx, entity_ids: [],
    )

    def _auto(current_ctx, entity_ids, *, entity_type, force=False, scope="primary"):
        del current_ctx, entity_type, force, scope
        calls.append(list(entity_ids))
        return {
            "sourceAvailability": {
                "readyTargets": [],
                "ineligibleTargets": [
                    {
                        "entityId": _EID,
                        "status": "repairable",
                        "lanes": ["homepage"],
                        "issues": [
                            f"homepage: download_repair required: {_EID}: missing core source categories ['encyclopedia']"
                        ],
                        "nextActions": ["source_repair"],
                        "deterministic": False,
                    }
                ],
            }
        }

    monkeypatch.setattr("task.run._run_download_auto_research", _auto)

    result = run_mod._checkpoint_download_plan(ctx)

    assert result.status == "waiting"
    assert calls == [[_EID]]
    state = run_mod.load_workflow_state(task_id, batch_id)
    assert not state.get("replacementObjects")


def test_stale_source_plan_uses_entity_scoped_signature(monkeypatch):
    task_id = _make_task()
    spec = store.load_spec(task_id)
    spec["scope"]["coverageTargets"] = [
        {"entityType": "地点/景区", "name": _EID},
        {"entityType": "地点/景区", "name": "稳定景区乙"},
    ]
    store.save_spec(spec)
    batch_id = "download_plan_signature_scoped_stale"
    ctx = _ctx(task_id, batch_id)
    ctx.entity_ids = [_EID, "稳定景区乙"]
    etype = "地点/景区"
    for entity_id in ctx.entity_ids:
        dl = resolve_entity_object_dir(task_id, batch_id, entity_id, etype_hint=etype) / STAGE_DOWNLOAD
        dl.mkdir(parents=True, exist_ok=True)
        signature_hash = "old" if entity_id == _EID else "current"
        for lane in ("homepage", "article", "image"):
            write_json(
                dl / f"{lane}_source_plan.json",
                {
                    "taskId": task_id,
                    "batchId": batch_id,
                    "ref": entity_id,
                    "sourceRuleSignature": {"hash": signature_hash},
                    "payload": {"entityId": entity_id, "researchLane": lane},
                },
            )

    monkeypatch.setattr(
        "task.run.source_plan_rule_signature",
        lambda _vertical, entity_id: {"hash": "old" if entity_id == "unrelated" else "current"},
    )

    stale = run_mod._stale_source_plan_entities(ctx, entity_ids=ctx.entity_ids)
    assert [item["entityId"] for item in stale] == [_EID]
    assert stale[0]["sourcePlanRuleState"] == "signature_stale"


def test_auto_research_replacement_wave_preserves_primary_report():
    task_id = _make_task(workflow_policy={"allowPartialContent": True})
    batch_id = "auto_research_wave_report"
    ctx = _ctx(task_id, batch_id)
    primary = {
        "schemaVersion": "quwoquan.download.auto_research_plan",
        "taskId": task_id,
        "batchId": batch_id,
        "updated": [{"entityId": _EID, "lane": "article"}],
        "issues": [f"{_EID}: article base sources=1 need>=2"],
        "sourceUnavailable": [{"entityId": _EID, "lane": "article"}],
        "sourceAvailability": {
            "readyTargets": [],
            "readyTargetCount": 0,
            "ineligibleTargets": [{"entityId": _EID}],
            "ineligibleTargetCount": 1,
        },
        "throughput": {"maxWorkers": 8, "entityCount": 2, "elapsedSeconds": 20, "entitiesPerMinute": 6},
    }
    replacement = {
        "schemaVersion": "quwoquan.download.auto_research_plan",
        "taskId": task_id,
        "batchId": batch_id,
        "updated": [{"entityId": "替补景区乙", "lane": "article"}],
        "issues": [],
        "sourceUnavailable": [],
        "sourceAvailability": {
            "readyTargets": ["替补景区乙"],
            "readyTargetCount": 1,
            "ineligibleTargets": [],
            "ineligibleTargetCount": 0,
        },
        "throughput": {"maxWorkers": 8, "entityCount": 1, "elapsedSeconds": 10, "entitiesPerMinute": 6},
    }

    run_mod._write_auto_research_report(ctx, primary, scope="primary", entity_ids=[_EID, "缺图景区乙"])
    run_mod._write_auto_research_report(
        ctx,
        replacement,
        scope="replacement_wave_1",
        entity_ids=["替补景区乙"],
    )
    availability = {
        "readyTargets": [_EID, "替补景区乙"],
        "readyTargetCount": 2,
        "ineligibleTargets": [],
        "ineligibleTargetCount": 0,
    }
    run_mod._sync_auto_research_availability(ctx, availability)

    report = read_json(batch_root(task_id, batch_id) / "_shared" / "auto_research_plan.json")
    assert report["waveCount"] == 2
    assert [wave["scope"] for wave in report["waves"]] == ["primary", "replacement_wave_1"]
    assert len(report["updated"]) == 2
    assert report["issues"] == [f"{_EID}: article base sources=1 need>=2"]
    assert report["sourceAvailability"]["readyTargetCount"] == 2
    assert report["latestWaveSourceAvailability"]["readyTargetCount"] == 1
    assert report["throughput"]["entityCount"] == 3
    assert report["throughput"]["elapsedSeconds"] == 30


def test_download_plan_hint_uses_full_unresolved_entities(monkeypatch):
    task_id = _make_task()
    batch_id = "download_plan_full_unresolved_hint"
    ctx = _ctx(task_id, batch_id)
    ctx.entity_ids = [_EID, "额外景区乙"]

    monkeypatch.setenv("QWQ_DOWNLOAD_AUTO_RESEARCH", "0")
    monkeypatch.setattr("download.prepare.prepare_source_plan", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "task.run._source_plan_filled",
        lambda _ctx: (False, [f"{_EID}: article sources=1 need>=2"]),
    )
    monkeypatch.setattr("task.run._stale_source_plan_entities", lambda _ctx, entity_ids: [])
    monkeypatch.setattr(
        "task.run._download_plan_unresolved_entities",
        lambda _ctx: {
            _EID: {"article": ["article sources=1 need>=2"]},
            "额外景区乙": {"article": ["article sources=0 need>=2"]},
        },
    )

    result = run_mod._checkpoint_download_plan(ctx)

    assert result.status == "waiting"
    assert _EID in result.checkpoint_hint
    assert "额外景区乙" in result.checkpoint_hint
    availability = read_json(batch_root(task_id, batch_id) / "_shared" / "source_unavailable_targets.json")
    assert availability["ineligibleTargetCount"] == 2


def test_real_local_cursor_runner_defaults_to_serial_bridge_workers(monkeypatch):
    task_id = _make_task()
    ctx = _ctx(task_id, "managed_cursor_workers")
    ctx.runtime = "local"
    ctx.max_workers = 10
    ctx.agent_runner = None
    assert run_mod._managed_checkpoint_worker_count(ctx, 5) == 1
    monkeypatch.setattr("task.run.MANAGED_LOCAL_CURSOR_MAX_WORKERS", 2)
    assert run_mod._managed_checkpoint_worker_count(ctx, 5) == 2

    ctx.agent_runner = lambda _prompt: {"started": True, "status": "finished"}
    assert run_mod._managed_checkpoint_worker_count(ctx, 5) == 5


def test_managed_download_job_must_satisfy_lane_gate():
    task_id = _make_task()
    batch_id = "managed_download_lane_gate"
    ctx = _ctx(task_id, batch_id)
    assert run_mod.run_pipeline(ctx) == 10

    calls = []

    def _fake_finished_without_output(prompt: str) -> dict:
        calls.append(prompt)
        return {"started": True, "status": "finished", "result": "done"}

    ctx.agent_runner = _fake_finished_without_output
    ctx.max_workers = 1
    ok = run_mod._run_managed_checkpoint(ctx, "download_plan")
    assert ok is False
    assert calls
    state = run_mod.load_workflow_state(task_id, batch_id)
    assert state["status"] == "repairing"
    assert state["lastAgentRun"]["plannedJobCount"] == len(calls)
    assert state["lastAgentRun"]["jobCount"] == len(calls)
    failed_outcomes = [
        outcome for outcome in state["lastAgentRun"]["outcomes"]
        if outcome.get("status") == "error"
    ]
    assert failed_outcomes
    for outcome in failed_outcomes:
        assert outcome["started"] is True
        assert "checkpoint lane gate still fails" in outcome["error"]
        assert outcome["gateIssues"]


def test_managed_checkpoint_continues_after_one_job_failure(monkeypatch):
    task_id = _make_task()
    batch_id = "managed_partial_failure_continues"
    ctx = _ctx(task_id, batch_id)
    prompts = ["job-a", "job-b", "job-c"]
    calls: list[str] = []

    monkeypatch.setattr("task.run._checkpoint_prompts", lambda _ctx, stage: prompts if stage == "content_plan" else [])
    monkeypatch.setattr("task.run._checkpoint_is_done", lambda _ctx, stage: (False, ["content_plan still incomplete"]))

    def _runner(prompt: str) -> dict:
        calls.append(prompt)
        if prompt == "job-a":
            return {"started": True, "status": "error", "error": "deterministic bad object"}
        return {"started": True, "status": "finished", "result": "ok"}

    ctx.agent_runner = _runner
    ctx.max_workers = 3
    ok = run_mod._run_managed_checkpoint(ctx, "content_plan")
    assert ok is False
    assert sorted(calls) == sorted(prompts)
    state = run_mod.load_workflow_state(task_id, batch_id)
    assert state["status"] == "repairing"
    assert state["lastAgentRun"]["plannedJobCount"] == 3
    assert state["lastAgentRun"]["jobCount"] == 3
    assert state["lastAgentRun"]["finishedCount"] == 2
    assert state["lastAgentRun"]["scheduler"]["requestedMaxWorkers"] == 3
    assert state["lastAgentRun"]["scheduler"]["effectiveWorkerCount"] == 3
    assert state["lastAgentRun"]["scheduler"]["estimatedMinWaves"] == 1
    assert state["agentRunHistory"][-1]["scheduler"]["effectiveWorkerCount"] == 3
    assert all("timing" in outcome for outcome in state["lastAgentRun"]["outcomes"])
    assert state["failedObjects"] == ["deterministic bad object"]


def test_mark_abandoned_entities_records_fast_fail_state():
    task_id = _make_task()
    batch_id = "abandon_entity"
    report = run_mod.mark_abandoned_entities(
        task_id,
        batch_id,
        [_EID],
        stage="download_plan",
        reason="source_unavailable",
    )
    assert report["added"] == [_EID]
    state = run_mod.load_workflow_state(task_id, batch_id)
    assert state["abandonedObjects"][0]["entityId"] == _EID
    assert state["abandonedObjects"][0]["reason"] == "source_unavailable"


def test_download_fast_fail_classifies_duplicate_limited_images(monkeypatch):
    task_id = _make_task()
    ctx = _ctx(task_id, "download_fast_fail_duplicate_images")
    monkeypatch.setattr("download.gate.download_requirements", lambda _task_id: {"minImages": 3})
    monkeypatch.setattr(
        "_common.download_diagnostics.entity_download_diagnostics",
        lambda _root, _entity_id: {
            "downloadedImages": 2,
            "rejectedByCategory": {
                "duplicate": 1,
                "rights": 0,
                "safety_or_watermark": 0,
                "fetch_or_non_image": 0,
            },
        },
    )

    reasons = run_mod._download_fast_fail_reasons(
        ctx,
        [f"{_EID}: only 2 unique publishable images (need >= 3)"],
    )

    assert _EID in reasons
    assert "need >= 3" in reasons[_EID]


def test_download_fast_fail_does_not_abandon_when_replacement_capacity_insufficient(monkeypatch):
    task_id = _make_task(
        workflow_policy={
            "allowPartialContent": True,
            "deliveryMode": "partial_with_replacement_report",
        }
    )
    ctx = _ctx(task_id, "download_fast_fail_no_reserve")
    monkeypatch.setattr("download.gate.download_requirements", lambda _task_id: {"minImages": 3})
    monkeypatch.setattr(
        "_common.download_diagnostics.entity_download_diagnostics",
        lambda _root, _entity_id: {
            "downloadedImages": 2,
            "rejectedByCategory": {
                "duplicate": 1,
                "rights": 0,
                "safety_or_watermark": 0,
                "fetch_or_non_image": 0,
            },
        },
    )

    issues = run_mod._apply_download_fast_fail(
        ctx,
        [f"{_EID}: only 2 unique publishable images (need >= 3)"],
    )

    assert len(issues) == 1
    assert "replacement capacity exhausted" in issues[0]
    state = run_mod.load_workflow_state(task_id, ctx.batch_id)
    assert run_mod._abandoned_entity_ids(state) == set()


def test_run_pipeline_preserves_stage_state_deltas(monkeypatch):
    task_id = _make_task()
    batch_id = "preserve_state_deltas"
    ctx = _ctx(task_id, batch_id)

    def _runner(_ctx: run_mod.PipelineContext) -> run_mod.StageResult:
        run_mod.mark_abandoned_content_refs(
            task_id,
            batch_id,
            [f"{_EID}_planning_consultation"],
            stage="content_plan",
            reason="source_unavailable: fixture lacks usable base source",
        )
        return run_mod.StageResult(
            "content_plan",
            run_mod.CHECKPOINT,
            "failed",
            "content_plan incomplete",
            issues=["fixture missing article source"],
        )

    monkeypatch.setattr("task.run.DAG", [("content_plan", run_mod.CHECKPOINT, _runner)])
    monkeypatch.setattr("task.run.STAGE_NAMES", ["content_plan"])

    assert run_mod.run_pipeline(ctx) == 1
    state = run_mod.load_workflow_state(task_id, batch_id)
    assert state["status"] == "manual_required"
    assert state["abandonedContentObjects"][0]["ref"] == f"{_EID}_planning_consultation"
    assert state["abandonedContentObjects"][0]["reason"].startswith("source_unavailable:")


def test_content_plan_strict_source_unavailable_fails_before_agent(monkeypatch):
    task_id = _make_task()
    batch_id = "content_plan_strict_source_unavailable"
    ctx = _ctx(task_id, batch_id)
    issue = (
        f"{_EID}_route_transport: source_unavailable: usable article base sources "
        "1 < 2; missing writingIntent=route_transport; "
        "workflowPolicy.allowContentQuotaShortfall is not true"
    )

    monkeypatch.setattr("task.run._content_plan_done", lambda _ctx: (False, ["missing packet"]))
    monkeypatch.setattr("task.run._auto_content_plan", lambda _ctx, _spec: [issue])

    result = run_mod._checkpoint_content_plan(ctx)

    assert result.status == "failed"
    assert "严格任务禁止继续消耗 Agent" in result.message
    assert result.issues == [issue]
    assert result.fallback_stage == "download_plan"


def test_content_plan_source_shortfall_activates_replacement(monkeypatch):
    task_id = _make_task(
        workflow_policy={
            "allowPartialContent": True,
            "deliveryMode": "partial_with_replacement_report",
        }
    )
    spec = store.load_spec(task_id)
    spec["scope"]["reserveCoverageTargets"] = [{"entityType": "地点/景区", "name": "替补景区乙"}]
    store.save_spec(spec)
    batch_id = "content_plan_source_shortfall_replacement"
    ctx = _ctx(task_id, batch_id)
    write_json(
        batch_root(task_id, batch_id) / "_shared" / "content_plan_source_diagnostics.json",
        {
            "schemaVersion": "quwoquan_data.content_plan_source_diagnostics/1",
            "taskId": task_id,
            "batchId": batch_id,
            "targets": {
                _EID: {
                    "rawArticleBaseSources": 3,
                    "qualifiedArticleBaseSources": 1,
                    "pickedArticleBaseSources": 1,
                    "pickedImageSources": 2,
                    "articleRejects": {"text_too_short": 2},
                }
            },
        },
    )
    issue = (
        f"{_EID}_route_transport: source_unavailable: usable article base sources "
        "1 < 2; missing writingIntent=route_transport; "
        "workflowPolicy.allowContentQuotaShortfall is not true"
    )

    def _screen(current_ctx, *, entity_type, reason, needed, scope):
        del entity_type, reason, needed, scope
        run_mod._append_replacement_row(
            current_ctx,
            entity_id="替补景区乙",
            entity_type="地点/景区",
            status="active",
            reason="test replacement passed",
            source_gate_status="passed",
        )
        if "替补景区乙" not in current_ctx.entity_ids:
            current_ctx.entity_ids.append("替补景区乙")
        return ["替补景区乙"], [], {}

    monkeypatch.setattr("task.run._content_plan_done", lambda _ctx: (False, ["missing packet"]))
    monkeypatch.setattr("task.run._auto_content_plan", lambda _ctx, _spec: [issue])
    monkeypatch.setattr("task.run._screen_replacement_targets", _screen)

    result = run_mod._checkpoint_content_plan(ctx)

    assert result.status == "failed"
    assert result.fallback_stage == "download_plan"
    assert "源短缺实体已快速放弃" in result.message
    state = run_mod.load_workflow_state(task_id, batch_id)
    assert [item["entityId"] for item in state["abandonedObjects"]] == [_EID]
    assert [
        item["entityId"]
        for item in state["replacementObjects"]
        if item.get("status") == "active"
    ] == ["替补景区乙"]


def test_content_plan_source_shortfall_continues_replacement_waves(monkeypatch):
    task_id = _make_task(
        workflow_policy={
            "allowPartialContent": True,
            "deliveryMode": "partial_with_replacement_report",
        }
    )
    spec = store.load_spec(task_id)
    spec["scope"]["reserveCoverageTargets"] = [
        {"entityType": "地点/景区", "name": "替补景区乙"},
        {"entityType": "地点/景区", "name": "替补景区丙"},
    ]
    store.save_spec(spec)
    batch_id = "content_plan_source_shortfall_replacement_waves"
    ctx = _ctx(task_id, batch_id)
    write_json(
        batch_root(task_id, batch_id) / "_shared" / "content_plan_source_diagnostics.json",
        {
            "schemaVersion": "quwoquan_data.content_plan_source_diagnostics/1",
            "taskId": task_id,
            "batchId": batch_id,
            "targets": {
                _EID: {
                    "rawArticleBaseSources": 3,
                    "qualifiedArticleBaseSources": 1,
                    "pickedArticleBaseSources": 1,
                    "pickedImageSources": 2,
                    "articleRejects": {"text_too_short": 2},
                }
            },
        },
    )
    issue = (
        f"{_EID}_route_transport: source_unavailable: usable article base sources "
        "1 < 2; missing writingIntent=route_transport; "
        "workflowPolicy.allowContentQuotaShortfall is not true"
    )
    calls: list[str] = []

    def _screen(current_ctx, *, entity_type, reason, needed, scope):
        del entity_type, reason, needed
        calls.append(scope)
        if len(calls) == 1:
            run_mod._append_replacement_row(
                current_ctx,
                entity_id="替补景区乙",
                entity_type="地点/景区",
                status="rejected",
                reason="test replacement rejected",
                source_gate_status="failed",
                issues=["image research needs enough rights-cleared source collections"],
            )
            run_mod.mark_abandoned_entities(
                task_id,
                batch_id,
                ["替补景区乙"],
                stage="download_plan",
                reason="test replacement rejected",
            )
            return [], ["替补景区乙"], {}
        run_mod._append_replacement_row(
            current_ctx,
            entity_id="替补景区丙",
            entity_type="地点/景区",
            status="active",
            reason="test replacement passed",
            source_gate_status="passed",
        )
        if "替补景区丙" not in current_ctx.entity_ids:
            current_ctx.entity_ids.append("替补景区丙")
        return ["替补景区丙"], [], {}

    monkeypatch.setattr("task.run._content_plan_done", lambda _ctx: (False, ["missing packet"]))
    monkeypatch.setattr("task.run._auto_content_plan", lambda _ctx, _spec: [issue])
    monkeypatch.setattr("task.run._screen_replacement_targets", _screen)

    result = run_mod._checkpoint_content_plan(ctx)

    assert result.status == "failed"
    assert result.fallback_stage == "download_plan"
    assert calls == ["content_plan_source_shortfall_1", "content_plan_source_shortfall_2"]
    state = run_mod.load_workflow_state(task_id, batch_id)
    assert [item["entityId"] for item in state["abandonedObjects"]] == ["替补景区乙", _EID]
    assert [
        (item["entityId"], item.get("status"))
        for item in state["replacementObjects"]
    ] == [("替补景区乙", "rejected"), ("替补景区丙", "active")]


def test_download_retained_source_shortfall_fast_fails_after_repair_rewind():
    task_id = _make_task()
    batch_id = "download_retained_shortfall_fast_fail"
    ctx = _ctx(task_id, batch_id)
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["reactRewinds"] = {"download_fetch": run_mod.MAX_REACT_REWINDS - 1}
    run_mod.save_workflow_state(state)

    reasons = run_mod._download_fast_fail_reasons(
        ctx,
        [
            (
                f"地点/景区/{_EID}/1.download/sources: "
                "article retained sources=3 need>=4"
            )
        ],
    )

    assert _EID in reasons
    assert "retained-source shortfall survived repair" in reasons[_EID]


def test_download_retained_source_shortfall_repairs_before_fast_fail():
    task_id = _make_task()
    batch_id = "download_retained_shortfall_repair_first"
    ctx = _ctx(task_id, batch_id)
    reasons = run_mod._download_fast_fail_reasons(
        ctx,
        [
            (
                f"地点/景区/{_EID}/1.download/sources: "
                "article retained sources=3 need>=4"
            )
        ],
    )

    assert reasons == {}


def test_download_homepage_base_ready_shortfall_fast_fails_after_repair_rewind():
    task_id = _make_task()
    batch_id = "download_homepage_base_ready_fast_fail"
    ctx = _ctx(task_id, batch_id)
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["reactRewinds"] = {"download_fetch": run_mod.MAX_REACT_REWINDS - 1}
    run_mod.save_workflow_state(state)

    reasons = run_mod._download_fast_fail_reasons(
        ctx,
        [
            (
                f"地点/景区/{_EID}/1.download/sources: "
                "homepage baseDraft-ready sources=0 need>=1"
            )
        ],
    )

    assert _EID in reasons
    assert "retained-source shortfall survived repair" in reasons[_EID]


def test_auto_content_plan_article_sources_are_deduped_by_source_ref_not_image_sha():
    task_id = _make_task()
    spec = store.load_spec(task_id)
    spec.setdefault("content", {}).setdefault("quotas", {})["entityArticlesPerTarget"] = 4
    spec["content"]["quotas"]["imageWorksPerTarget"] = 0
    spec.setdefault("acceptance", {})["requiredAngles"] = [
        "planning_consultation",
        "decision_experience",
        "route_transport",
        "seasonal_timing",
    ]
    store.save_spec(spec)
    batch_id = "content_plan_article_dedupe_by_source_ref"
    ctx = _ctx(task_id, batch_id)
    object_dir = resolve_entity_object_dir(task_id, batch_id, _EID, etype_hint="地点/景区")
    sources_dir = object_dir / STAGE_DOWNLOAD / "sources"
    repeated_body = "\n".join(
        [
            f"{_EID}是测试省核心景区，行前需要核对开放时间、门票预约、交通接驳和天气情况。",
            f"{_EID}的主要游览点之间有步行距离，建议安排半日到一日，携带饮水并预留返程时间。",
            f"{_EID}在不同季节体验差异明显，春夏看植被，秋季看层林，雨天需要注意路面湿滑。",
            f"{_EID}适合把入口动线、核心观景点、返程交通和周边餐饮拆开记录，避免只写百科式介绍。",
            f"{_EID}的体验判断需要结合现场排队、道路坡度、休息点密度、遮阴条件和亲子老人同行成本。",
            f"{_EID}如果遇到节假日，应提前确认分时预约、停车饱和、公共交通末班和临时限流通知。",
            f"{_EID}的文章底稿要能支持规划咨询、决策体验、路线交通和季节时机四种不同写作角度。",
            f"{_EID}的事实引用应保留来源边界，不能把同一段文字轻改成多篇，也不能混用图片发布权利。",
            f"{_EID}的游览建议需要说明适合人群、体力消耗、避峰时间和恶劣天气下的替代安排。",
            f"{_EID}的内容生产应优先形成可追溯的底稿，再由 agent 基于写作契约生成非模板化正文。",
        ]
        * 8
    )
    for index in range(1, 5):
        source_dir = sources_dir / f"{index:02d}.article_fixture_{index}"
        (source_dir / "assets").mkdir(parents=True, exist_ok=True)
        write_json(
            source_dir / "meta.json",
            {
                "sourceId": f"article_fixture_{index}",
                "researchLane": "article",
                "sourceRole": "base",
                "sourceUseMode": "factual_reference_only",
                "category": "travelogue",
                "title": f"测试底稿 {index}",
                "sourceQualityScore": 0.9,
            },
        )
        (source_dir / "source.md").write_text(repeated_body, encoding="utf-8")
        write_json(
            source_dir / "assets" / "index.json",
            {
                "assets": [
                    {
                        "fileName": "shared.jpg",
                        "sha256": f"sha256:article-image-sha-{index}",
                        "sourceCollectionId": f"article-collection-{index}",
                        "caption": f"{_EID} 共享测试图",
                        "license": "reference_only",
                        "credit": "测试来源",
                        "sourceUrl": f"https://example.test/{index}",
                        "termsUrl": "https://example.test/terms",
                        "usageScope": "factual_reference_only",
                    }
                ]
            },
        )

    issues = run_mod._auto_content_plan(ctx, spec)

    assert issues == []
    packet = read_json(batch_root(task_id, batch_id) / "_shared" / "content_plan_packet.json")
    article_items = [item for item in packet["items"] if item["carrier"] == "article"]
    assert [item["writingIntent"] for item in article_items] == spec["acceptance"]["requiredAngles"]
    assert len({item["baseSourceRef"] for item in article_items}) == 4


def test_auto_content_plan_image_work_skips_article_source_asset_reuse():
    task_id = _make_task()
    spec = store.load_spec(task_id)
    spec.setdefault("content", {}).setdefault("quotas", {})["entityArticlesPerTarget"] = 1
    spec["content"]["quotas"]["imageWorksPerTarget"] = 1
    spec.setdefault("acceptance", {})["requiredAngles"] = ["planning_consultation", "image"]
    store.save_spec(spec)
    batch_id = "content_plan_image_avoids_article_asset"
    ctx = _ctx(task_id, batch_id)
    object_dir = resolve_entity_object_dir(task_id, batch_id, _EID, etype_hint="地点/景区")
    sources_dir = object_dir / STAGE_DOWNLOAD / "sources"
    article_image = _real_jpeg(211)
    article_digest = hashlib.sha256(article_image).hexdigest()
    article_dir = sources_dir / "01.article_base"
    (article_dir / "assets").mkdir(parents=True, exist_ok=True)
    (article_dir / "source.md").write_text(
        "\n".join(
            [
                f"{_EID}行前需要核对开放时间、门票预约、交通接驳和天气情况，并把停车、接驳车、返程末班都写入计划。",
                f"{_EID}适合把入口动线、核心观景点、返程交通和周边餐饮拆开记录，亲子或老人同行时还要降低坡道路段强度。",
                f"{_EID}不同季节体验差异明显，需要结合现场排队、道路坡度、遮阴条件和雨天湿滑风险来判断值不值得去。",
            ]
            * 90
        ),
        encoding="utf-8",
    )
    write_json(
        article_dir / "meta.json",
        {
            "sourceId": "article_base",
            "researchLane": "article",
            "sourceRole": "base",
            "sourceUseMode": "factual_reference_only",
            "category": "travelogue",
            "title": "有图文章底稿",
            "sourceQualityScore": 0.9,
        },
    )
    (article_dir / "assets" / "article.jpg").write_bytes(article_image)
    write_json(
        article_dir / "assets" / "index.json",
        {
            "assets": [
                {
                    "fileName": "article.jpg",
                    "sha256": f"sha256:{article_digest}",
                    "sourceCollectionId": "article:collection",
                    "caption": f"{_EID} 文章源图",
                    "license": "CC-BY-SA 4.0",
                    "credit": "测试作者",
                    "sourceUrl": "https://example.test/article-image",
                    "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                    "usageScope": "factual_reference_only",
                }
            ]
        },
    )
    for index, (source_name, image_bytes, collection_id) in enumerate(
        [
            ("02.image_reused", article_image, "article:collection"),
            ("03.image_safe", _real_jpeg(212), "image:collection:safe"),
        ],
        start=2,
    ):
        source_dir = sources_dir / source_name
        assets_dir = source_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        asset_name = "image.jpg"
        (source_dir / "source.md").write_text(f"# {_EID} 图片 {index}", encoding="utf-8")
        (assets_dir / asset_name).write_bytes(image_bytes)
        digest = hashlib.sha256(image_bytes).hexdigest()
        write_json(
            source_dir / "meta.json",
            {
                "sourceId": source_name,
                "researchLane": "image",
                "title": f"图片 {index}",
                "sourceCollectionId": collection_id,
            },
        )
        write_json(
            assets_dir / "index.json",
            {
                "assets": [
                    {
                        "fileName": asset_name,
                        "sha256": f"sha256:{digest}",
                        "sourceCollectionId": collection_id,
                        "caption": f"{_EID} 图片 {index}",
                        "license": "CC-BY-SA 4.0",
                        "credit": "测试摄影师",
                        "sourceUrl": f"https://example.test/image/{index}",
                        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                        "usageScope": "app_publish",
                    }
                ]
            },
        )

    issues = run_mod._auto_content_plan(ctx, spec)

    assert issues == []
    packet = read_json(batch_root(task_id, batch_id) / "_shared" / "content_plan_packet.json")
    image_items = [item for item in packet["items"] if item["carrier"] == "image"]
    assert len(image_items) == 1
    assert image_items[0]["sourceCollectionId"] == "image:collection:safe"
    diagnostics = read_json(batch_root(task_id, batch_id) / "_shared" / "content_plan_source_diagnostics.json")
    assert diagnostics["targets"][_EID]["imageRejects"]["source_asset_reused"] == 1


def test_auto_content_plan_skips_article_base_without_source_assets():
    task_id = _make_task()
    spec = store.load_spec(task_id)
    spec.setdefault("content", {}).setdefault("quotas", {})["entityArticlesPerTarget"] = 1
    spec["content"]["quotas"]["imageWorksPerTarget"] = 0
    spec.setdefault("acceptance", {})["requiredAngles"] = ["planning_consultation"]
    store.save_spec(spec)
    batch_id = "content_plan_article_requires_source_asset"
    ctx = _ctx(task_id, batch_id)
    object_dir = resolve_entity_object_dir(task_id, batch_id, _EID, etype_hint="地点/景区")
    sources_dir = object_dir / STAGE_DOWNLOAD / "sources"
    repeated_body = "\n".join(
        [
            f"{_EID}行前需要核对开放时间、门票预约、交通接驳和天气情况，并把停车、接驳车、返程末班都写入计划。",
            f"{_EID}核心游览点之间有步行距离，需要预留返程时间，同时说明亲子、老人同行时哪些路段应该降低强度。",
            f"{_EID}不同季节体验差异明显，雨天要注意路面湿滑，晴天则更适合把观景点和补给点拆成两段安排。",
            f"{_EID}文章底稿必须同时具备文字和可追溯源图，源图不是装饰，而是支撑现场判断和图文闭环的底稿证据。",
        ]
        * 90
    )
    for index, (source_id, has_asset, quality) in enumerate(
        [
            ("article_without_image", False, 1.0),
            ("article_with_image", True, 0.8),
        ],
        start=1,
    ):
        source_dir = sources_dir / f"{index:02d}.{source_id}"
        source_dir.mkdir(parents=True, exist_ok=True)
        write_json(
            source_dir / "meta.json",
            {
                "sourceId": source_id,
                "researchLane": "article",
                "sourceRole": "base",
                "sourceUseMode": "factual_reference_only",
                "category": "travelogue",
                "title": f"测试底稿 {index}",
                "sourceQualityScore": quality,
            },
        )
        (source_dir / "source.md").write_text(repeated_body, encoding="utf-8")
        if has_asset:
            assets_dir = source_dir / "assets"
            assets_dir.mkdir(parents=True, exist_ok=True)
            asset_name = "source.jpg"
            data = _real_jpeg(120 + index)
            (assets_dir / asset_name).write_bytes(data)
            write_json(
                assets_dir / "index.json",
                {
                    "assets": [
                        {
                            "fileName": asset_name,
                            "sha256": "sha256:" + hashlib.sha256(data).hexdigest(),
                            "sourceCollectionId": "article-source-with-image",
                            "caption": f"{_EID} 图文底稿配图",
                            "license": "CC-BY-SA 4.0",
                            "credit": "测试摄影师",
                            "sourceUrl": "https://example.test/source-image",
                            "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                            "usageScope": "app_publish",
                        }
                    ]
                },
            )

    issues = run_mod._auto_content_plan(ctx, spec)

    assert issues == []
    packet = read_json(batch_root(task_id, batch_id) / "_shared" / "content_plan_packet.json")
    article_items = [item for item in packet["items"] if item["carrier"] == "article"]
    assert len(article_items) == 1
    assert "article_with_image" in article_items[0]["baseSourceRef"]
    diagnostics = read_json(batch_root(task_id, batch_id) / "_shared" / "content_plan_source_diagnostics.json")
    assert diagnostics["targets"][_EID]["articleRejects"]["no_source_assets"] == 1


def test_auto_content_plan_disambiguates_duplicate_image_captions():
    task_id = _make_task()
    spec = store.load_spec(task_id)
    spec.setdefault("content", {}).setdefault("quotas", {})["entityArticlesPerTarget"] = 0
    spec["content"]["quotas"]["imageWorksPerTarget"] = 2
    spec.setdefault("acceptance", {})["requiredAngles"] = ["image"]
    store.save_spec(spec)
    batch_id = "content_plan_duplicate_image_caption_titles"
    ctx = _ctx(task_id, batch_id)
    object_dir = resolve_entity_object_dir(task_id, batch_id, _EID, etype_hint="地点/景区")
    sources_dir = object_dir / STAGE_DOWNLOAD / "sources"
    shared_caption_prefix = "共享景观" * 16
    for index in range(1, 3):
        source_dir = sources_dir / f"{index:02d}.image_fixture_{index}"
        assets_dir = source_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        asset_name = f"image_{index}.jpg"
        asset_bytes = _real_jpeg(80 + index)
        (assets_dir / asset_name).write_bytes(asset_bytes)
        digest = hashlib.sha256(asset_bytes).hexdigest()
        write_json(
            source_dir / "meta.json",
            {
                "sourceId": f"image_fixture_{index}",
                "researchLane": "image",
                "title": "共享景观",
                "sourceCollectionId": f"fixture:image:{index}",
            },
        )
        (source_dir / "source.md").write_text(f"# {_EID} 共享景观图 {index}", encoding="utf-8")
        write_json(
            assets_dir / "index.json",
            {
                "assets": [
                    {
                        "fileName": asset_name,
                        "sha256": f"sha256:{digest}",
                        "sourceCollectionId": f"fixture:image:{index}",
                        "caption": f"{shared_caption_prefix}{index}",
                        "license": "CC-BY-SA 4.0",
                        "credit": f"测试摄影师{index}",
                        "sourceUrl": f"https://example.test/image/{index}",
                        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                        "usageScope": "app_publish",
                    }
                ]
            },
        )

    issues = run_mod._auto_content_plan(ctx, spec)

    assert issues == []
    packet = read_json(batch_root(task_id, batch_id) / "_shared" / "content_plan_packet.json")
    image_items = [item for item in packet["items"] if item["carrier"] == "image"]
    title_prefix = shared_caption_prefix[:60]
    assert [item["title"] for item in image_items] == [
        f"{_EID}·{title_prefix}·视角1",
        f"{_EID}·{title_prefix}·视角2",
    ]


def test_auto_content_plan_skips_image_assets_blocked_by_safety_gate():
    task_id = _make_task()
    spec = store.load_spec(task_id)
    spec.setdefault("content", {}).setdefault("quotas", {})["entityArticlesPerTarget"] = 0
    spec["content"]["quotas"]["imageWorksPerTarget"] = 1
    spec.setdefault("acceptance", {})["requiredAngles"] = ["image"]
    store.save_spec(spec)
    batch_id = "content_plan_image_safety_prefilter"
    ctx = _ctx(task_id, batch_id)
    object_dir = resolve_entity_object_dir(task_id, batch_id, _EID, etype_hint="地点/景区")
    sources_dir = object_dir / STAGE_DOWNLOAD / "sources"
    fixtures = [
        (
            "01.image_bad",
            "oversized.png",
            _oversized_png_header(),
            "fixture:image:z_bad",
            "超大原图",
        ),
        (
            "02.image_safe",
            "safe.jpg",
            _real_jpeg(311),
            "fixture:image:a_safe",
            "合格视角",
        ),
    ]
    for index, (source_name, asset_name, asset_bytes, collection_id, caption) in enumerate(fixtures, start=1):
        source_dir = sources_dir / source_name
        assets_dir = source_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        (source_dir / "source.md").write_text(f"# {_EID} {caption}", encoding="utf-8")
        (assets_dir / asset_name).write_bytes(asset_bytes)
        digest = hashlib.sha256(asset_bytes).hexdigest()
        write_json(
            source_dir / "meta.json",
            {
                "sourceId": source_name,
                "researchLane": "image",
                "title": caption,
                "sourceCollectionId": collection_id,
            },
        )
        write_json(
            assets_dir / "index.json",
            {
                "assets": [
                    {
                        "fileName": asset_name,
                        "sha256": f"sha256:{digest}",
                        "sourceCollectionId": collection_id,
                        "caption": caption,
                        "license": "CC-BY-SA 4.0",
                        "credit": f"测试摄影师{index}",
                        "sourceUrl": f"https://example.test/image/{index}",
                        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                        "usageScope": "app_publish",
                    }
                ]
            },
        )

    issues = run_mod._auto_content_plan(ctx, spec)

    assert issues == []
    packet = read_json(batch_root(task_id, batch_id) / "_shared" / "content_plan_packet.json")
    image_items = [item for item in packet["items"] if item["carrier"] == "image"]
    assert len(image_items) == 1
    assert image_items[0]["sourceCollectionId"] == "fixture:image:a_safe"
    assert image_items[0]["assetRefs"][0].endswith("/safe.jpg")
    diagnostics = read_json(batch_root(task_id, batch_id) / "_shared" / "content_plan_source_diagnostics.json")
    target_diag = diagnostics["targets"][_EID]
    assert target_diag["rawImageAssets"] == 2
    assert target_diag["qualifiedImageAssets"] == 1
    assert target_diag["imageRejects"]["image_safety_blocked"] == 1
    assert "image_pixels_too_large" in target_diag["imageRejectExamples"]["image_safety_blocked"][0]


def test_source_availability_fast_fails_unrecoverable_subset():
    names = ["可用景区甲", "缺图景区乙"]
    spec = store.scaffold_spec(
        vertical="travel",
        organize_by="地域",
        key="测试省",
        name="source availability subset",
        category="景区",
        scope={
            "region": "测试省",
            "entityTypes": ["地点/景区"],
            "coverageTargets": [
                {"entityType": "地点/景区", "name": name}
                for name in names
            ],
        },
        content={
            "modalityContract": "separated_research",
            "research": {"lanes": ["homepage", "article", "image"]},
            "carriers": ["article", "image"],
            "quotas": {
                "entityArticlesPerTarget": 1,
                "imageWorksPerTarget": 1,
                "entityHomepagesPerTarget": 1,
                "routeArticles": 0,
            },
        },
        created_by="test",
    )
    spec["workflowPolicy"] = {"allowPartialContent": True}
    ctx = run_mod.PipelineContext(
        task_id=spec["taskId"],
        batch_id="source_availability_fast_fail",
        entity_ids=names,
        spec=spec,
        baseline_packet={},
        baseline_packet_path=Path("/tmp/nonexistent-baseline.json"),
    )
    report = {
        "sourceAvailability": {
            "readyTargets": ["可用景区甲"],
            "ineligibleTargets": [
                {
                    "entityId": "缺图景区乙",
                    "issues": ["缺图景区乙: no rights-compatible open-license images discovered"],
                    "blockers": [
                        {
                            "lane": "image",
                            "reason": "no single-author/single-file rights-cleared image collection",
                            "nextAction": "manual_authorized_gallery_or_target_replacement",
                        }
                    ],
                    "nextActions": ["manual_authorized_gallery_or_target_replacement"],
                }
            ],
        }
    }

    added = run_mod._abandon_source_unavailable_entities(
        ctx,
        report,
        reason_prefix="source_unavailable_after_auto_research",
    )

    assert added == ["缺图景区乙"]
    state = run_mod.load_workflow_state(ctx.task_id, ctx.batch_id)
    assert run_mod._abandoned_entity_ids(state) == {"缺图景区乙"}
    assert "source_unavailable_after_auto_research" in state["abandonedObjects"][0]["reason"]


def test_source_availability_does_not_fast_fail_strict_task():
    names = ["可用景区甲", "缺图景区乙"]
    spec = store.scaffold_spec(
        vertical="travel",
        organize_by="地域",
        key="测试省",
        name="source availability strict",
        category="景区",
        scope={
            "region": "测试省",
            "entityTypes": ["地点/景区"],
            "coverageTargets": [
                {"entityType": "地点/景区", "name": name}
                for name in names
            ],
        },
        content={
            "modalityContract": "separated_research",
            "research": {"lanes": ["homepage", "article", "image"]},
            "carriers": ["article", "image"],
            "quotas": {
                "entityArticlesPerTarget": 1,
                "imageWorksPerTarget": 1,
                "entityHomepagesPerTarget": 1,
                "routeArticles": 0,
            },
        },
        created_by="test",
    )
    ctx = run_mod.PipelineContext(
        task_id=spec["taskId"],
        batch_id="source_availability_strict",
        entity_ids=names,
        spec=spec,
        baseline_packet={},
        baseline_packet_path=Path("/tmp/nonexistent-baseline.json"),
    )
    report = {
        "sourceAvailability": {
            "readyTargets": ["可用景区甲"],
            "ineligibleTargets": [
                {
                    "entityId": "缺图景区乙",
                    "issues": ["缺图景区乙: no rights-compatible open-license images discovered"],
                    "blockers": [
                        {
                            "lane": "image",
                            "reason": "no single-author/single-file rights-cleared image collection",
                            "nextAction": "manual_authorized_gallery_or_target_replacement",
                        }
                    ],
                    "nextActions": ["manual_authorized_gallery_or_target_replacement"],
                }
            ],
        }
    }

    added = run_mod._abandon_source_unavailable_entities(
        ctx,
        report,
        reason_prefix="source_unavailable_after_auto_research",
    )

    assert added == []
    state = run_mod.load_workflow_state(ctx.task_id, ctx.batch_id)
    assert run_mod._abandoned_entity_ids(state) == set()


def test_source_availability_does_not_fast_fail_when_replacement_capacity_insufficient():
    names = ["可用景区甲", "缺图景区乙", "缺图景区丙"]
    spec = store.scaffold_spec(
        vertical="travel",
        organize_by="地域",
        key="测试省",
        name="source availability reserve shortage",
        category="景区",
        scope={
            "region": "测试省",
            "entityTypes": ["地点/景区"],
            "coverageTargets": [
                {"entityType": "地点/景区", "name": name}
                for name in names
            ],
            "reserveCoverageTargets": [
                {"entityType": "地点/景区", "name": "替补景区丁"},
            ],
        },
        content={
            "modalityContract": "separated_research",
            "research": {"lanes": ["homepage", "article", "image"]},
            "carriers": ["article", "image"],
            "quotas": {
                "entityArticlesPerTarget": 1,
                "imageWorksPerTarget": 1,
                "entityHomepagesPerTarget": 1,
                "routeArticles": 0,
            },
        },
        acceptance={"minEntities": 3},
        created_by="test",
    )
    spec["workflowPolicy"] = {
        "allowPartialContent": True,
        "deliveryMode": "partial_with_replacement_report",
    }
    ctx = run_mod.PipelineContext(
        task_id=spec["taskId"],
        batch_id="source_availability_reserve_shortage",
        entity_ids=names,
        spec=spec,
        baseline_packet={},
        baseline_packet_path=Path("/tmp/nonexistent-baseline.json"),
    )
    report = {
        "sourceAvailability": {
            "readyTargets": ["可用景区甲"],
            "ineligibleTargets": [
                {
                    "entityId": entity,
                    "issues": [f"{entity}: no rights-compatible open-license images discovered"],
                    "blockers": [
                        {
                            "lane": "image",
                            "reason": "no single-author/single-file rights-cleared image collection",
                            "nextAction": "manual_authorized_gallery_or_target_replacement",
                        }
                    ],
                    "nextActions": ["manual_authorized_gallery_or_target_replacement"],
                }
                for entity in ("缺图景区乙", "缺图景区丙")
            ],
        }
    }

    added = run_mod._abandon_source_unavailable_entities(
        ctx,
        report,
        reason_prefix="source_unavailable_after_auto_research",
    )

    assert added == []
    state = run_mod.load_workflow_state(ctx.task_id, ctx.batch_id)
    assert run_mod._abandoned_entity_ids(state) == set()


def test_reset_stage_retries_records_infra_recovery():
    task_id = _make_task()
    batch_id = "retry_stage"
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["waitingCheckpoint"] = "build_homepage"
    state["status"] = "manual_required"
    state["completed"] = ["download_plan", "download_fetch", "build_prepare", "build_homepage", "build_validate", "content_plan"]
    state["retryCounts"] = {"build_homepage": 2, "content_plan": 1}
    state["infrastructureRetryCounts"] = {"build_homepage": 3, "content_plan": 1}
    state["reactRewinds"] = {"build_validate": 1, "content_plan": 2}
    state["failedObjects"] = ["Bridge request failed", "internal error"]
    run_mod.save_workflow_state(state)

    report = run_mod.reset_stage_retries(
        task_id,
        batch_id,
        stage="build_homepage",
        reason="cursor bridge recovered",
    )

    assert report["status"] == "waiting_agent"
    assert report["completed"] == ["download_plan", "download_fetch", "build_prepare"]
    assert report["retryCounts"] == {}
    assert report["infrastructureRetryCounts"] == {}
    assert report["reactRewinds"] == {}
    state = run_mod.load_workflow_state(task_id, batch_id)
    assert state["failedObjects"] == []
    assert state["completed"] == ["download_plan", "download_fetch", "build_prepare"]
    assert state["recoveryActions"][-1]["stage"] == "build_homepage"
    assert state["recoveryActions"][-1]["previous"]["infrastructureRetryCount"] == 3
    assert "content_plan" in state["recoveryActions"][-1]["previous"]["completed"]


def test_approved_review_refs_exclude_failed_objects_from_batch_reducer():
    task_id = _make_task()
    batch_id = "approved_review_refs"
    ctx = _ctx(task_id, batch_id)
    content_object.register_content_object(
        task_id, batch_id, "ref_ok", content_type="article", angle="攻略", title="OK"
    )
    content_object.register_content_object(
        task_id, batch_id, "ref_bad", content_type="article", angle="攻略", title="BAD"
    )
    ok_dir = content_object.content_object_dir(task_id, batch_id, "ref_ok") / "5.review"
    bad_dir = content_object.content_object_dir(task_id, batch_id, "ref_bad") / "5.review"
    ok_dir.mkdir(parents=True, exist_ok=True)
    bad_dir.mkdir(parents=True, exist_ok=True)
    write_json(ok_dir / "review_gate.json", {"passed": True})
    write_json(bad_dir / "review_gate.json", {"passed": False, "issues": ["skeletonSimilarity"]})

    assert run_mod._approved_review_refs(ctx) == ["ref_ok"]


def test_batch_reducer_payload_excludes_image_refs():
    task_id = _make_task()
    batch_id = "batch_reducer_payload_image_refs"
    ctx = _ctx(task_id, batch_id)
    content_object.register_content_object(
        task_id, batch_id, "article_ref", content_type="article", angle="攻略", title="Article"
    )
    content_object.register_content_object(
        task_id, batch_id, "image_ref", content_type="image", angle="攻略", title="Image"
    )
    for ref in ("article_ref", "image_ref"):
        review_dir = content_object.content_object_dir(task_id, batch_id, ref) / "5.review"
        review_dir.mkdir(parents=True, exist_ok=True)
        write_json(review_dir / "review_gate.json", {"passed": True})
        draft = draft_article_path(task_id, batch_id, ref)
        draft.parent.mkdir(parents=True, exist_ok=True)
        draft.write_text(f"{ref} draft body with enough words to be visible.", encoding="utf-8")
        write_writing_pack(
            task_id,
            batch_id,
            ref,
            {
                "writingIntent": "planning_consultation",
                "baseSourceRef": f"sources/{ref}.md",
            },
        )

    payload = run_mod._batch_reducer_payload(ctx, refs={"article_ref", "image_ref"})

    assert [row["ref"] for row in payload] == ["article_ref"]


def test_post_verify_scope_excludes_unrelated_green_refs():
    from verify.verify_content_quality import verify_posts

    root = _TMP / "scoped_post_verify" / "posts"
    good = root / "article" / "攻略" / "Good" / "1"
    bad = root / "article" / "攻略" / "Bad" / "1"
    for post_dir, title, body in (
        (good, "Good", "这是一个正常正文。" * 220),
        (bad, "Bad", "这个正文含有批次边界词。" * 220),
    ):
        post_dir.mkdir(parents=True, exist_ok=True)
        (post_dir / "article.md").write_text(body, encoding="utf-8")
        write_json(
            post_dir / "manifest.json",
            {
                "topicId": title,
                "carrier": "article",
                "sourceTaskId": "task",
                "tagRefs": ["tag/a", "tag/b"],
                "entityRefs": ["地点/景区/测试"],
                "normalizedEntityRefs": ["entity:地点:景区:测试"],
                "assets": [],
                "sourceUrls": ["https://example.com/source"],
                "intersectionHints": [],
            },
        )

    scoped_good = verify_posts(root, post_rels={"posts/article/攻略/Good/1"})
    assert not any("forbidden phrase found: 批次" in issue for issue in scoped_good)

    scoped_bad = verify_posts(root, post_rels={"posts/article/攻略/Bad/1"})
    assert any("forbidden phrase found: 批次" in issue for issue in scoped_bad)


def test_gate_produce_passes_ref_scope_to_post_verify(monkeypatch):
    from produce.gate import gate_produce

    task_id = _make_task()
    batch_id = "gate_produce_ref_scope"
    content_object.register_content_object(
        task_id, batch_id, "ref_ok", content_type="article", angle="攻略", title="OK"
    )
    content_object.register_content_object(
        task_id, batch_id, "ref_bad", content_type="article", angle="攻略", title="BAD"
    )
    ok_dir = content_object.content_object_dir(task_id, batch_id, "ref_ok")
    ok_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        ok_dir / "manifest.json",
        {
            "entityRefs": ["地点/景区/测试"],
            "tagRefs": ["tag/a", "tag/b"],
            "reviewDecision": "approved",
            "storySpine": {"readerPromise": "ok"},
            "sourceUrls": ["https://example.com/source"],
        },
    )
    (ok_dir / "article.md").write_text("正文" * 400, encoding="utf-8")

    captured: list[set[str] | None] = []

    monkeypatch.setattr("produce.gate.gate_media_check", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("produce.gate.scan_runtime_batch_integrity", lambda *_args, **_kwargs: {"issues": []})
    monkeypatch.setattr(
        "produce.gate.iter_stage_envelopes",
        lambda *_args, **_kwargs: iter([("ref_ok", {"payload": {"passed": True}})]),
    )

    def _fake_verify_posts_root(_root, **kwargs):
        captured.append(kwargs.get("post_rels"))
        return []

    monkeypatch.setattr("produce.gate.verify_posts_root", _fake_verify_posts_root)

    gate_produce(task_id, batch_id, "article", refs=["ref_ok"])

    assert captured == [{"posts/article/攻略/OK/1"}]


def test_review_retry_maps_release_gate_issue_after_object_gates_are_green():
    task_id = _make_task()
    batch_id = "review_retry_release_issue"
    ctx = _ctx(task_id, batch_id)
    content_object.register_content_object(
        task_id, batch_id, "ref_ok", content_type="article", angle="攻略", title="OK"
    )
    content_object.register_content_object(
        task_id, batch_id, "ref_bad", content_type="article", angle="攻略", title="BAD"
    )
    for ref in ("ref_ok", "ref_bad"):
        review_dir = content_object.content_object_dir(task_id, batch_id, ref) / "5.review"
        review_dir.mkdir(parents=True, exist_ok=True)
        write_json(review_dir / "review_gate.json", {"passed": True})

    bad_rel = content_object.content_object_rel(task_id, batch_id, "ref_bad")
    refs, issue_map = run_mod._produce_review_retry_refs(
        ctx,
        [f"{bad_rel}/article.md: forbidden phrase found: 批次"],
    )

    assert refs == ["ref_bad"]
    assert "批次" in issue_map["ref_bad"][0]


def test_release_only_ship_report_records_no_import_claim():
    from ship.handler import write_release_only_ship_report

    task_id = _make_task()
    batch_id = "release_only_ship_report"
    path = write_release_only_ship_report(
        task_id=task_id,
        batch_id=batch_id,
        release_id="release_1",
        summary={"entityCount": 1, "postCount": 2},
    )

    payload = read_json(path)
    assert payload["closureType"] == "release_only"
    assert payload["sourceReleaseId"] == "release_1"
    assert payload["importRequested"] is False
    assert payload["importReports"] == []


def test_agent_active_throughput_is_diagnostic_not_wall_clock_replacement():
    metrics = run_mod._agent_active_throughput(
        {
            "agentRunHistory": [
                {
                    "stage": "produce_author",
                    "plannedJobCount": 4,
                    "finishedCount": 3,
                    "infrastructureFailures": 1,
                    "scheduler": {"elapsedSeconds": 120, "startedAt": "s1"},
                    "finishedAt": "t1",
                },
                {
                    "stage": "produce_author",
                    "plannedJobCount": 4,
                    "finishedCount": 3,
                    "infrastructureFailures": 1,
                    "scheduler": {"elapsedSeconds": 120, "startedAt": "s1"},
                    "finishedAt": "t1",
                }
            ],
            "lastAgentRun": {
                "stage": "produce_author",
                "plannedJobCount": 2,
                "finishedCount": 2,
                "infrastructureFailures": 0,
                "scheduler": {"elapsedSeconds": 60, "startedAt": "s2"},
                "finishedAt": "t2",
            },
        }
    )

    assert metrics["authorRunCount"] == 2
    assert metrics["finishedAuthorJobs"] == 5
    assert metrics["infrastructureFailures"] == 1
    assert metrics["finishedAuthorJobsPerHour"] == 100.0


def test_completion_gate_ignores_stale_agent_run_for_abandoned_refs():
    task_id = _make_task()
    batch_id = "completion_ignores_abandoned_agent"
    ctx = _ctx(task_id, batch_id)
    state = {
        "waitingCheckpoint": None,
        "failedObjects": [],
        "abandonedContentObjects": [
            {
                "ref": "ref_dead",
                "stage": "produce_author",
                "reason": "agent failed",
                "status": "abandoned",
            }
        ],
        "lastAgentRun": {
            "stage": "produce_author",
            "jobCount": 1,
            "plannedJobCount": 1,
            "refs": ["ref_dead"],
            "startedCount": 0,
            "finishedCount": 0,
            "infrastructureFailures": 1,
            "outcomes": [{"ref": "ref_dead", "started": False, "status": "error"}],
        },
    }

    assert run_mod._workflow_completion_issues(ctx, state) == []


def test_completion_gate_blocks_active_failed_agent_run():
    task_id = _make_task()
    batch_id = "completion_blocks_active_agent"
    ctx = _ctx(task_id, batch_id)
    state = {
        "waitingCheckpoint": None,
        "failedObjects": [],
        "abandonedContentObjects": [],
        "lastAgentRun": {
            "stage": "produce_author",
            "jobCount": 1,
            "plannedJobCount": 1,
            "refs": ["ref_active"],
            "startedCount": 0,
            "finishedCount": 0,
            "infrastructureFailures": 1,
            "outcomes": [{"ref": "ref_active", "started": False, "status": "error"}],
        },
    }

    issues = run_mod._workflow_completion_issues(ctx, state)
    assert "lastAgentRun.infrastructureFailures=1" in issues


def test_download_plan_rejects_low_resolution_article_source_image():
    task_id = _make_task()
    batch_id = "download_plan_low_res_article"
    _seed_source_plan(task_id, batch_id)
    ctx = _ctx(task_id, batch_id)
    assert run_mod._source_plan_filled(ctx)[0] is True

    plan_path = (
        resolve_entity_object_dir(task_id, batch_id, _EID, etype_hint="地点/景区")
        / STAGE_DOWNLOAD
        / "article_source_plan.json"
    )
    plan = read_json(plan_path)
    first_image = plan["payload"]["sources"][0]["imageUrls"][0]
    first_image["width"] = 720
    first_image["height"] = 480
    write_json(plan_path, plan)

    ok, issues = run_mod._source_plan_filled(ctx)
    assert ok is False
    assert any("article source article_baike image[1]: imagePixels" in issue for issue in issues), issues


def test_download_plan_allows_recoverable_compressed_article_source_image():
    task_id = _make_task()
    batch_id = "download_plan_recoverable_article_image"
    _seed_source_plan(task_id, batch_id)
    ctx = _ctx(task_id, batch_id)
    plan_path = (
        resolve_entity_object_dir(task_id, batch_id, _EID, etype_hint="地点/景区")
        / STAGE_DOWNLOAD
        / "article_source_plan.json"
    )
    plan = read_json(plan_path)
    first_image = plan["payload"]["sources"][0]["imageUrls"][0]
    first_image["url"] = (
        "https://img1.qunarzz.com/travel/d1/1509/f3/"
        "foo.jpg_r_720x480x95_abcd1234.jpg"
    )
    first_image["width"] = 720
    first_image["height"] = 480
    write_json(plan_path, plan)

    assert run_mod._source_plan_filled(ctx)[0] is True


def test_download_plan_allows_single_authoritative_homepage_source():
    task_id = _make_task()
    batch_id = "download_plan_single_authoritative_homepage"
    _seed_source_plan(task_id, batch_id)
    ctx = _ctx(task_id, batch_id)
    plan_path = (
        resolve_entity_object_dir(task_id, batch_id, _EID, etype_hint="地点/景区")
        / STAGE_DOWNLOAD
        / "homepage_source_plan.json"
    )
    plan = read_json(plan_path)
    plan["payload"]["sources"] = plan["payload"]["sources"][:1]
    plan["payload"]["sources"][0]["category"] = "official"
    write_json(plan_path, plan)

    ok, issues = run_mod._source_plan_filled(ctx)
    assert ok is True
    assert not any("homepage sources=" in issue for issue in issues), issues


def test_download_plan_blocks_travelogue_as_homepage_source():
    task_id = _make_task()
    batch_id = "download_plan_homepage_travelogue"
    _seed_source_plan(task_id, batch_id)
    ctx = _ctx(task_id, batch_id)
    plan_path = (
        resolve_entity_object_dir(task_id, batch_id, _EID, etype_hint="地点/景区")
        / STAGE_DOWNLOAD
        / "homepage_source_plan.json"
    )
    plan = read_json(plan_path)
    plan["payload"]["sources"].append(
        {
            "source_id": "home_qunar_guide",
            "platform": "去哪儿攻略",
            "url": "https://touch.travel.qunar.com/youji/fixture",
            "category": "travelogue",
            "sourceUseMode": "factual_reference_only",
        }
    )
    write_json(plan_path, plan)

    ok, issues = run_mod._source_plan_filled(ctx)
    assert ok is False
    assert any("entity homepage cannot use author/guide/review source category travelogue" in i for i in issues), issues


def test_download_repair_requires_source_plan_update_before_resume():
    task_id = _make_task()
    batch_id = "download_repair1"
    _seed_source_plan(task_id, batch_id)
    ctx = _ctx(task_id, batch_id)
    assert run_mod._source_plan_filled(ctx)[0] is True

    repair_path = run_mod._record_download_repair(
        ctx,
        [f"{_EID}: only 1 retained source; only 1 unique publishable image"],
    )
    repair = read_json(repair_path)
    assert repair["schemaVersion"] == "quwoquan.download_repair"
    assert repair["entities"][0]["downloadDiagnostics"]["entityId"] == _EID
    assert any(
        hint["action"] == "add_or_replace_image_source_collections_with_complete_rights"
        for hint in repair["entities"][0]["imageRepairHints"]
    )
    ok, issues = run_mod._source_plan_filled(ctx)
    assert ok is False
    assert any("download_repair required" in issue for issue in issues), issues
    availability = run_mod._write_download_plan_availability(ctx, {})
    assert availability["readyTargets"] == []
    assert availability["ineligibleTargets"][0]["entityId"] == _EID
    assert "image" in availability["ineligibleTargets"][0]["lanes"]
    persisted = read_json(batch_root(task_id, batch_id) / "_shared" / "source_unavailable_targets.json")
    assert persisted["ineligibleTargets"][0]["entityId"] == _EID

    plan_path = (
        resolve_entity_object_dir(task_id, batch_id, _EID, etype_hint="地点/景区")
        / STAGE_DOWNLOAD
        / "image_source_plan.json"
    )
    current = plan_path.stat().st_mtime_ns
    os.utime(plan_path, ns=(current + 1_000_000_000, current + 1_000_000_000))
    assert run_mod._source_plan_filled(ctx)[0] is True
    assert repair_path.exists()
    assert run_mod._download_retry_entity_ids(ctx) == [_EID]


def test_download_repair_fetch_only_image_failure_retries_fetch_before_agent():
    task_id = _make_task()
    batch_id = "download_repair_fetch_only_image_retry"
    _seed_source_plan(task_id, batch_id)
    ctx = _ctx(task_id, batch_id)
    assert run_mod._source_plan_filled(ctx)[0] is True

    plan_dir = (
        resolve_entity_object_dir(task_id, batch_id, _EID, etype_hint="地点/景区")
        / STAGE_DOWNLOAD
    )
    plan_paths = [
        plan_dir / "homepage_source_plan.json",
        plan_dir / "article_source_plan.json",
        plan_dir / "image_source_plan.json",
    ]
    repair_path = run_mod._download_repair_path(ctx)
    repair_entity = {
        "entityId": _EID,
        "issues": [
            f"{_EID}: imageCount: {_EID} 仅下到 0 张合格去重图（规模化任务要求 ≥3）",
            f"{_EID}: imageFetch: 未下到真实图片，请在 source_plan 提供可用 imageUrls(CC/PD/授权)",
        ],
        "sourcePlanPath": str(plan_paths[0]),
        "sourcePlanPaths": [str(path) for path in plan_paths],
        "sourcePlanMtimeNs": max(path.stat().st_mtime_ns for path in plan_paths),
        "fetchRetryCount": 1,
        "downloadDiagnostics": {
            "entityId": _EID,
            "plannedImages": 5,
            "downloadedImages": 0,
            "rejectedByCategory": {
                "fetch_or_non_image": 5,
                "rights": 0,
                "safety_or_watermark": 0,
                "duplicate": 0,
            },
        },
        "researchLaneIssues": {},
        "imageRepairHints": [
            {
                "lane": "image",
                "issue": "imageFetch failed/non-image/too small",
                "action": "replace_unfetchable_or_low_quality_image",
            }
        ],
    }
    write_json(
        repair_path,
        {
            "schemaVersion": "quwoquan.download_repair",
            "taskId": task_id,
            "batchId": batch_id,
            "entities": [repair_entity],
        },
    )

    assert run_mod._source_plan_filled(ctx)[0] is True
    assert run_mod._checkpoint_prompts(ctx, "download_plan") == []
    assert run_mod._download_retry_entity_ids(ctx) == [_EID]

    repair_entity["fetchRetryCount"] = 2
    write_json(
        repair_path,
        {
            "schemaVersion": "quwoquan.download_repair",
            "taskId": task_id,
            "batchId": batch_id,
            "entities": [repair_entity],
        },
    )
    ok, issues = run_mod._source_plan_filled(ctx)
    assert ok is False
    assert any("download_repair required" in issue for issue in issues), issues
    prompts = run_mod._checkpoint_prompts(ctx, "download_plan")
    assert any("[AGENT_LANE:image]" in prompt for prompt in prompts)


def test_download_fetch_preserves_nonzero_handler_stage_gate_failure(monkeypatch):
    task_id = _make_task()
    batch_id = "download_stage_gate_failure"
    ctx = _ctx(task_id, batch_id)
    ensure_batch_layout(task_id, batch_id, "download")
    write_gate_report(
        task_id=task_id,
        batch_id=batch_id,
        command="download",
        step="image_fetch",
        ref=_EID,
        passed=False,
        issues=["imageCount: only 1 publishable image"],
        evidence_summary={},
        fallback_stage="source_plan",
    )

    monkeypatch.setattr("task.run._download_retry_entity_ids", lambda _ctx: [_EID])
    monkeypatch.setattr("download.gate.gate_download", lambda *_args, **_kwargs: [])

    def _raise_nonzero(_args):
        raise SystemExit(1)

    monkeypatch.setattr("download.handler.handle_download", _raise_nonzero)

    result = run_mod._run_download_fetch(ctx)
    assert result.status == "failed"
    assert "imageCount: only 1 publishable image" in result.message
    repair = read_json(run_mod._download_repair_path(ctx))
    assert repair["entities"][0]["entityId"] == _EID
    assert "imageCount: only 1 publishable image" in repair["entities"][0]["issues"][0]


def test_download_repair_records_only_entity_scoped_issues():
    task_id = _make_task()
    batch_id = "download_repair_entity_scoped"
    ctx = _ctx(task_id, batch_id)
    ctx.entity_ids = [_EID, "无关景区乙"]
    issues = [
        f"{_EID}: imageCount: {_EID} 仅下到 2 张合格去重图（规模化任务要求 ≥3）",
        "batch diagnostic: source_screen worker completed",
    ]

    path = run_mod._record_download_repair(ctx, issues)
    repair = read_json(path)
    assert [row["entityId"] for row in repair["entities"]] == [_EID]
    assert repair["entities"][0]["issues"] == [issues[0]]


def test_pending_download_repair_ignores_stale_cross_entity_issues():
    task_id = _make_task()
    batch_id = "download_repair_stale_cross_entity"
    ctx = _ctx(task_id, batch_id)
    ctx.entity_ids = [_EID, "无关景区乙"]
    write_json(
        run_mod._download_repair_path(ctx),
        {
            "schemaVersion": "quwoquan.download_repair",
            "taskId": task_id,
            "batchId": batch_id,
            "entities": [
                {
                    "entityId": "无关景区乙",
                    "issues": [
                        f"{_EID}: imageCount: {_EID} 仅下到 1 张合格图（要求 ≥2）"
                    ],
                    "sourcePlanMtimeNs": 0,
                    "imageRepairHints": [{"lane": "image", "issue": "stale cross entity"}],
                }
            ],
        },
    )

    assert run_mod._pending_download_repair_unresolved(ctx) == {}


def test_pending_download_repair_ignores_stale_source_category_rule_issue():
    task_id = _make_task()
    batch_id = "download_repair_stale_source_category_rule"
    _seed_source_plan(task_id, batch_id)
    ctx = _ctx(task_id, batch_id)
    plan_paths = run_mod._source_plan_lane_paths(ctx, _EID, "地点/景区")
    write_json(
        run_mod._download_repair_path(ctx),
        {
            "schemaVersion": "quwoquan.download_repair",
            "taskId": task_id,
            "batchId": batch_id,
            "entities": [
                {
                    "entityId": _EID,
                    "issues": [
                        f"{_EID}: missing core source categories ['travelogue']"
                    ],
                    "sourcePlanPaths": [str(path) for path in plan_paths],
                    "sourcePlanMtimeNs": max(
                        run_mod._source_plan_mtime_ns(path) for path in plan_paths
                    ),
                    "imageRepairHints": [
                        {
                            "lane": "article",
                            "entityId": _EID,
                            "issue": f"{_EID}: missing core source categories ['travelogue']",
                        }
                    ],
                }
            ],
        },
    )

    assert run_mod._pending_download_repair_unresolved(ctx) == {}
    prompts = run_mod._checkpoint_prompts(ctx, "download_plan")
    assert not any("download_repair" in prompt for prompt in prompts)


def test_source_plan_filled_ignores_stale_cross_entity_download_repair(monkeypatch):
    task_id = _make_task()
    batch_id = "source_plan_ignores_stale_cross_repair"
    _seed_source_plan(task_id, batch_id)
    ctx = _ctx(task_id, batch_id)
    plan_paths = run_mod._source_plan_lane_paths(ctx, _EID, "地点/景区")
    write_json(
        run_mod._download_repair_path(ctx),
        {
            "schemaVersion": "quwoquan.download_repair",
            "taskId": task_id,
            "batchId": batch_id,
            "entities": [
                {
                    "entityId": _EID,
                    "issues": [
                        "无关景区乙: imageCount: 无关景区乙 仅下到 1 张合格图（要求 ≥2）"
                    ],
                    "sourcePlanPaths": [str(path) for path in plan_paths],
                    "sourcePlanMtimeNs": max(
                        run_mod._source_plan_mtime_ns(path) for path in plan_paths
                    ),
                    "imageRepairHints": [
                        {
                            "lane": "image",
                            "entityId": _EID,
                            "issue": "无关景区乙: imageCount: 无关景区乙 仅下到 1 张合格图（要求 ≥2）",
                        }
                    ],
                }
            ],
        },
    )
    monkeypatch.setattr(
        "download.gate.gate_download",
        lambda *_args, **_kwargs: ["无关景区乙: imageCount: 无关景区乙 仅下到 1 张合格图（要求 ≥2）"],
    )

    ok, issues = run_mod._source_plan_filled(ctx)

    assert ok is True
    assert issues == []


def test_pending_download_repair_is_scoped_to_context_entities():
    task_id = _make_task()
    batch_id = "download_repair_scoped_to_context"
    _seed_source_plan(task_id, batch_id)
    ctx = _ctx(task_id, batch_id)
    plan_paths = run_mod._source_plan_lane_paths(ctx, _EID, "地点/景区")
    write_json(
        run_mod._download_repair_path(ctx),
        {
            "schemaVersion": "quwoquan.download_repair",
            "taskId": task_id,
            "batchId": batch_id,
            "entities": [
                {
                    "entityId": _EID,
                    "issues": [
                        f"{_EID}: missing core source categories ['encyclopedia']"
                    ],
                    "sourcePlanPaths": [str(path) for path in plan_paths],
                    "sourcePlanMtimeNs": max(
                        run_mod._source_plan_mtime_ns(path) for path in plan_paths
                    ),
                    "imageRepairHints": [
                        {
                            "lane": "homepage",
                            "entityId": _EID,
                            "issue": f"{_EID}: missing core source categories ['encyclopedia']",
                        }
                    ],
                }
            ],
        },
    )

    scoped = copy.copy(ctx)
    scoped.entity_ids = ["替补候选景区"]
    assert run_mod._pending_download_repair_unresolved(scoped) == {}


def test_download_fetch_passes_ctx_max_workers_to_handler(monkeypatch):
    task_id = _make_task()
    batch_id = "download_fetch_workers"
    ctx = _ctx(task_id, batch_id)
    ctx.max_workers = 7
    captured: dict[str, int] = {}

    monkeypatch.setattr("task.run._download_retry_entity_ids", lambda _ctx: [_EID])
    monkeypatch.setattr("download.gate.gate_download", lambda *_args, **_kwargs: [])

    def _fake_download(args):
        captured["max_workers"] = int(args.max_workers)

    monkeypatch.setattr("download.handler.handle_download", _fake_download)

    result = run_mod._run_download_fetch(ctx)
    assert result.status == "done"
    assert captured["max_workers"] == 7


def test_download_fetch_scopes_single_lane_pending_repair(monkeypatch):
    task_id = _make_task()
    batch_id = "download_fetch_lane_scope"
    ctx = _ctx(task_id, batch_id)
    captured: dict[str, str] = {}

    monkeypatch.setattr("task.run._download_retry_entity_ids", lambda _ctx: [_EID])
    monkeypatch.setattr(
        "task.run._pending_download_repair_unresolved",
        lambda _ctx: {_EID: {"homepage": ["homepage retained sources=0 need>=1"]}},
    )
    monkeypatch.setattr("download.gate.gate_download", lambda *_args, **_kwargs: [])

    def _fake_download(args):
        captured["lane"] = str(args.lane)

    monkeypatch.setattr("download.handler.handle_download", _fake_download)

    result = run_mod._run_download_fetch(ctx)
    assert result.status == "done"
    assert captured["lane"] == "homepage"


def test_download_stage_gate_issues_are_scoped_to_current_entities():
    task_id = _make_task()
    batch_id = "download_stage_gate_scope"
    ctx = _ctx(task_id, batch_id)
    result_dir = batch_root(task_id, batch_id) / "task_download" / "results" / "source_plan_gate"
    write_json(
        result_dir / f"{_EID}.json",
        {"payload": {"passed": False, "ref": _EID, "issues": ["imageCount: only 2 images"]}},
    )
    write_json(
        result_dir / "无关景区乙.json",
        {"payload": {"passed": False, "ref": "无关景区乙", "issues": ["old stale issue"]}},
    )

    issues = run_mod._download_stage_gate_issues(ctx, entity_ids=[_EID])

    assert issues == [f"{_EID}: imageCount: only 2 images"]


def test_download_plan_auto_research_uses_download_repair_scope(monkeypatch):
    task_id = _make_task()
    batch_id = "download_plan_repair_scope"
    ctx = _ctx(task_id, batch_id)
    ctx.entity_ids = [_EID, "额外景区乙"]
    captured: dict[str, list[str]] = {}
    checks = iter([(False, ["download_repair required"]), (True, [])])

    monkeypatch.setattr("task.run._source_plan_filled", lambda _ctx: next(checks))
    monkeypatch.setattr("task.run._download_plan_unresolved_entities", lambda _ctx: {})
    monkeypatch.setattr("task.run._download_retry_entity_ids", lambda _ctx: [_EID])
    monkeypatch.setattr("task.run._stale_source_plan_entities", lambda _ctx, entity_ids: [])

    def _fake_auto_research(_ctx, entity_ids, *, entity_type, force=False, scope="primary"):
        _ = (entity_type, force, scope)
        captured["entity_ids"] = list(entity_ids)
        return {
            "sourceAvailability": {
                "readyTargets": list(entity_ids),
                "ineligibleTargets": [],
            }
        }

    monkeypatch.setattr("task.run._run_download_auto_research", _fake_auto_research)

    result = run_mod._checkpoint_download_plan(ctx)
    assert result.status == "done"
    assert captured["entity_ids"] == [_EID]


def test_download_plan_auto_research_prefers_current_unresolved_lane_scope(monkeypatch):
    task_id = _make_task()
    batch_id = "download_plan_current_unresolved_scope"
    ctx = _ctx(task_id, batch_id)
    ctx.entity_ids = [_EID, "当前文章不足景区", "旧fetch失败景区"]
    captured: dict[str, object] = {}
    checks = iter([(False, ["article research needs >= 4 text-qualified base sources"]), (True, [])])

    monkeypatch.setattr("task.run._source_plan_filled", lambda _ctx: next(checks))
    monkeypatch.setattr(
        "task.run._download_plan_unresolved_entities",
        lambda _ctx: {"当前文章不足景区": {"article": ["article sources=2 need>=4"]}},
    )
    monkeypatch.setattr("task.run._download_retry_entity_ids", lambda _ctx: ["旧fetch失败景区"])
    monkeypatch.setattr("task.run._stale_source_plan_entities", lambda _ctx, entity_ids: [])

    def _fake_auto_research(_ctx, entity_ids, *, entity_type, force=False, scope="primary"):
        _ = (entity_type, scope)
        captured["entity_ids"] = list(entity_ids)
        captured["force"] = force
        return {
            "sourceAvailability": {
                "readyTargets": list(entity_ids),
                "ineligibleTargets": [],
            }
        }

    monkeypatch.setattr("task.run._run_download_auto_research", _fake_auto_research)

    result = run_mod._checkpoint_download_plan(ctx)
    assert result.status == "done"
    assert captured == {"entity_ids": ["当前文章不足景区"], "force": True}


def test_download_plan_checkpoint_does_not_full_refresh_ready_batch_on_rule_mtime(monkeypatch):
    task_id = _make_task()
    batch_id = "download_plan_ready_batch_no_global_stale_refresh"
    ctx = _ctx(task_id, batch_id)
    ctx.entity_ids = [_EID, "额外景区乙"]
    calls: dict[str, object] = {}

    monkeypatch.setattr("task.run._source_plan_filled", lambda _ctx: (True, []))
    monkeypatch.setattr("task.run._download_plan_unresolved_entities", lambda _ctx: {})
    monkeypatch.setattr("task.run._download_retry_entity_ids", lambda _ctx: [])

    def _fake_stale(_ctx, *, entity_ids):
        calls["stale_entity_ids"] = list(entity_ids)
        return [{"entityId": entity_ids[0]}]

    monkeypatch.setattr("task.run._stale_source_plan_entities", _fake_stale)

    result = run_mod._checkpoint_download_plan(ctx)
    assert result.status == "done"
    assert calls == {}


def test_download_plan_repairs_build_prepare_homepage_base_draft_scope(monkeypatch):
    task_id = _make_task()
    batch_id = "download_plan_build_prepare_homepage_scope"
    ctx = _ctx(task_id, batch_id)
    ctx.entity_ids = [_EID, "额外景区乙"]
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["failedObjects"] = [
        f"地点/景区/{_EID}: homepage baseDraft 可用事实不足",
    ]
    run_mod.save_workflow_state(state)
    captured: dict[str, object] = {}

    monkeypatch.setattr("task.run._source_plan_filled", lambda _ctx: (True, []))
    monkeypatch.setattr("task.run._download_plan_unresolved_entities", lambda _ctx: {})
    monkeypatch.setattr("task.run._download_retry_entity_ids", lambda _ctx: [])
    monkeypatch.setattr("task.run._stale_source_plan_entities", lambda _ctx, entity_ids: [])
    monkeypatch.setattr("download.prepare.prepare_source_plan", lambda *_args, **_kwargs: None)

    def _fake_auto_research(_ctx, entity_ids, *, entity_type, force=False, scope="primary"):
        _ = (entity_type, scope)
        captured["entity_ids"] = list(entity_ids)
        captured["force"] = force
        return {"issues": [], "sourceUnavailable": []}

    monkeypatch.setattr("task.run._run_download_auto_research", _fake_auto_research)

    result = run_mod._checkpoint_download_plan(ctx)
    assert result.status == "done"
    assert captured == {"entity_ids": [_EID], "force": True}


def test_legacy_non_actionable_download_repair_does_not_block_static_valid_plan():
    task_id = _make_task()
    batch_id = "download_repair_legacy_non_actionable"
    _seed_source_plan(task_id, batch_id)
    ctx = _ctx(task_id, batch_id)
    assert run_mod._source_plan_filled(ctx)[0] is True
    plan_dir = (
        resolve_entity_object_dir(task_id, batch_id, _EID, etype_hint="地点/景区")
        / STAGE_DOWNLOAD
    )
    plan_paths = [
        plan_dir / "homepage_source_plan.json",
        plan_dir / "article_source_plan.json",
        plan_dir / "image_source_plan.json",
    ]
    write_json(
        run_mod._download_repair_path(ctx),
        {
            "schemaVersion": "quwoquan.download_repair",
            "taskId": task_id,
            "batchId": batch_id,
            "entities": [
                {
                    "entityId": _EID,
                    "issues": [f"{_EID}: legacy fetch-only issue without actionable hint"],
                    "sourcePlanPath": str(plan_paths[0]),
                    "sourcePlanPaths": [str(path) for path in plan_paths],
                    "sourcePlanMtimeNs": max(path.stat().st_mtime_ns for path in plan_paths),
                    "researchLaneIssues": {},
                    "imageRepairHints": [],
                }
            ],
        },
    )

    assert run_mod._source_plan_filled(ctx)[0] is True
    assert run_mod._checkpoint_prompts(ctx, "download_plan") == []


def test_download_repair_includes_replace_source_image_hint():
    task_id = _make_task()
    batch_id = "download_repair_low_res_hint"
    _seed_source_plan(task_id, batch_id)
    ctx = _ctx(task_id, batch_id)
    plan_path = (
        resolve_entity_object_dir(task_id, batch_id, _EID, etype_hint="地点/景区")
        / STAGE_DOWNLOAD
        / "article_source_plan.json"
    )
    plan = read_json(plan_path)
    first_image = plan["payload"]["sources"][0]["imageUrls"][0]
    first_image["width"] = 720
    first_image["height"] = 480
    write_json(plan_path, plan)

    repair_path = run_mod._record_download_repair(
        ctx,
        [f"{_EID}: article source image too small"],
    )
    repair = read_json(repair_path)
    hints = repair["entities"][0]["imageRepairHints"]
    assert hints[0]["lane"] == "article"
    assert hints[0]["sourceId"] == "article_baike"
    assert hints[0]["action"] == "replace_image_or_source_unit"
    assert hints[0]["sameSourceHighResCandidate"] == ""
    assert repair["entities"][0]["researchLaneIssues"]["article"]


def test_download_repair_includes_same_source_high_res_hint():
    task_id = _make_task()
    batch_id = "download_repair_recoverable_hint"
    _seed_source_plan(task_id, batch_id)
    ctx = _ctx(task_id, batch_id)
    plan_path = (
        resolve_entity_object_dir(task_id, batch_id, _EID, etype_hint="地点/景区")
        / STAGE_DOWNLOAD
        / "article_source_plan.json"
    )
    plan = read_json(plan_path)
    first_image = plan["payload"]["sources"][0]["imageUrls"][0]
    first_image["url"] = (
        "https://img1.qunarzz.com/travel/d1/1509/f3/"
        "foo.jpg_r_720x480x95_abcd1234.jpg"
    )
    first_image["width"] = 720
    first_image["height"] = 480
    write_json(plan_path, plan)

    repair_path = run_mod._record_download_repair(
        ctx,
        [f"{_EID}: image_fetch_gate rejected low-res source image"],
    )
    repair = read_json(repair_path)
    hints = repair["entities"][0]["imageRepairHints"]
    retry_hints = [
        hint for hint in hints
        if hint["action"] == "retry_with_same_source_high_resolution_url"
    ]
    assert retry_hints
    assert retry_hints[0]["sameSourceHighResCandidate"].endswith("/foo.jpg")


def test_download_repair_rejects_source_use_mode_as_image_license_hint():
    task_id = _make_task()
    batch_id = "download_repair_source_mode_as_license"
    _seed_source_plan(task_id, batch_id)
    ctx = _ctx(task_id, batch_id)
    plan_path = (
        resolve_entity_object_dir(task_id, batch_id, _EID, etype_hint="地点/景区")
        / STAGE_DOWNLOAD
        / "article_source_plan.json"
    )
    plan = read_json(plan_path)
    first_image = plan["payload"]["sources"][0]["imageUrls"][0]
    first_image["license"] = "factual_reference_only"
    write_json(plan_path, plan)

    repair_path = run_mod._record_download_repair(
        ctx,
        [f"{_EID}: article source image unsupported license"],
    )
    repair = read_json(repair_path)
    actions = [hint["action"] for hint in repair["entities"][0]["imageRepairHints"]]
    assert "replace_image_or_source_unit_do_not_use_sourceUseMode_as_image_license" in actions


def test_download_plan_prompt_surfaces_image_repair_hints():
    task_id = _make_task()
    batch_id = "download_repair_prompt_hint"
    _seed_source_plan(task_id, batch_id)
    ctx = _ctx(task_id, batch_id)
    plan_path = (
        resolve_entity_object_dir(task_id, batch_id, _EID, etype_hint="地点/景区")
        / STAGE_DOWNLOAD
        / "article_source_plan.json"
    )
    plan = read_json(plan_path)
    first_image = plan["payload"]["sources"][0]["imageUrls"][0]
    first_image["width"] = 720
    first_image["height"] = 480
    write_json(plan_path, plan)
    run_mod._record_download_repair(
        ctx,
        [f"{_EID}: article source image too small"],
    )

    prompts = run_mod._checkpoint_prompts(ctx, "download_plan")
    article_prompts = [prompt for prompt in prompts if "[AGENT_LANE:article]" in prompt]
    assert article_prompts
    assert "源图修复指令" in article_prompts[0]
    assert "replace_image_or_source_unit" in article_prompts[0]
    assert "sourceUseMode 是文字来源权利模式，不是图片许可" in article_prompts[0]


def test_article_official_source_id_cannot_use_travelogue_platform():
    task_id = _make_task()
    batch_id = "download_article_official_identity"
    _seed_source_plan(task_id, batch_id)
    ctx = _ctx(task_id, batch_id)
    plan_path = (
        resolve_entity_object_dir(task_id, batch_id, _EID, etype_hint="地点/景区")
        / STAGE_DOWNLOAD
        / "article_source_plan.json"
    )
    plan = read_json(plan_path)
    for source in plan["payload"]["sources"]:
        if source["source_id"] == "article_official":
            source["platform"] = "去哪儿攻略"
            source["url"] = "https://touch.travel.qunar.com/comment/not-official"
            break
    write_json(plan_path, plan)

    issues = run_mod._download_research_lane_issues(ctx, _EID, "地点/景区", "article")
    assert any("source_id implies official" in issue for issue in issues), issues


def test_content_plan_override_replaces_stale_brief_base_source():
    from produce.handler import _apply_writing_intent_override

    brief = {
        "writingIntent": "planning_consultation",
        "baseSourceRef": "entities/地点/景区/毕棚沟/1.download/sources/03.home_official/source.md",
        "carrier": "article",
    }
    override = {
        "writingIntent": "seasonal_timing",
        "baseSourceRef": "entities/地点/景区/毕棚沟/1.download/sources/07.article_wiki_seasonal/source.md",
        "carrier": "article",
    }

    merged = _apply_writing_intent_override(brief, override)
    assert merged["writingIntent"] == "seasonal_timing"
    assert merged["baseSourceRef"].endswith("07.article_wiki_seasonal/source.md")
    assert merged["_contentPlanBaseSourceLocked"] is True


def test_image_content_plan_override_clears_stale_article_base_source():
    from produce.handler import _apply_writing_intent_override

    brief = {
        "carrier": "article",
        "baseSourceRef": "entities/地点/景区/稻城亚丁/1.download/sources/07.article_wiki_seasonal/source.md",
        "_contentPlanBaseSourceLocked": True,
    }
    override = {
        "carrier": "image",
        "sourceCollectionId": "daochengyading:image:wikimedia",
        "assetRefs": ["entities/地点/景区/稻城亚丁/1.download/sources/09.image/assets/001.jpg"],
    }

    merged = _apply_writing_intent_override(brief, override)
    assert merged["carrier"] == "image"
    assert "baseSourceRef" not in merged
    assert "_contentPlanBaseSourceLocked" not in merged
    assert merged["sourceCollectionId"] == "daochengyading:image:wikimedia"


def test_produce_review_bulk_failure_does_not_invalidate_drafts(monkeypatch):
    task_id = _make_task()
    ctx = _ctx(task_id, "bulk_review")
    refs = [f"ref_{idx}" for idx in range(47)]
    invalidated: list[str] = []
    reports: list[str] = []

    monkeypatch.setattr(
        "task.run._produce_review_retry_refs",
        lambda *_args, **_kwargs: (refs, {ref: ["travelogueDensity: opening lacks a real hook"] for ref in refs}),
    )
    monkeypatch.setattr(
        "task.run._content_issue_matchers",
        lambda *_args, **_kwargs: {f"ref_{idx}": {f"ref_{idx}"} for idx in range(50)},
    )
    monkeypatch.setattr(
        "task.run._write_retry_reports_for_refs",
        lambda _ctx, *, refs, issue_map, target_stage: reports.extend(refs),
    )
    monkeypatch.setattr(
        "task.run._invalidate_ref_for_retry",
        lambda _ctx, ref: invalidated.append(ref) or True,
    )

    prepared = run_mod._prepare_produce_review_retry(
        ctx,
        run_mod.StageResult(
            "produce_review",
            run_mod.AUTO,
            "failed",
            "发布门未过",
            fallback_stage="produce_compose",
            issues=["many failures"],
        ),
        "produce_compose",
    )

    assert prepared is False
    assert len(reports) == 47
    assert invalidated == []


def test_compose_base_draft_clear_removes_stale_source_occupant():
    ledger = {
        "schemaVersion": "quwoquan_data.base_draft_ledger",
        "assignments": {
            "entities/x/sources/07.article/source.md": "old_image_ref",
            "entities/x/sources/04.article/source.md": "selected_ref",
            "entities/y/sources/01.article/source.md": "other_ref",
        },
    }
    cleaned, duplicates, changed = run_mod._clear_compose_base_draft_assignments(
        ledger,
        ["selected_ref", "new_article_ref"],
        {
            "new_article_ref": {
                "baseSourceRef": "entities/x/sources/07.article/source.md",
            }
        },
    )

    assert duplicates == []
    assert changed is True
    assert cleaned["assignments"] == {
        "entities/y/sources/01.article/source.md": "other_ref",
    }


def test_compose_base_draft_clear_detects_duplicate_current_plan_sources():
    ledger = {"schemaVersion": "quwoquan_data.base_draft_ledger", "assignments": {}}
    cleaned, duplicates, changed = run_mod._clear_compose_base_draft_assignments(
        ledger,
        ["article_a", "article_b"],
        {
            "article_a": {"baseSourceRef": "entities/x/sources/07.article/source.md"},
            "article_b": {"baseSourceRef": "entities/x/sources/07.article/source.md"},
        },
    )

    assert cleaned["assignments"] == {}
    assert changed is False
    assert duplicates == [
        "entities/x/sources/07.article/source.md -> article_a, article_b"
    ]


def test_download_repair_includes_diagnostic_rejected_source_image_hint():
    hints = run_mod._download_diagnostic_image_repair_hints(
        {
            "sampleRejected": [
                "sourceImage:article_official_planning: "
                "测试景区甲/article_official_planning#1: "
                "imageFetch failed/non-image/too small "
                "(https://x.invalid/bad.jpg)"
            ]
        },
        entity_id=_EID,
    )

    assert hints
    assert hints[0]["lane"] == "article"
    assert hints[0]["sourceId"] == "article_official_planning"
    assert hints[0]["action"] == "replace_unfetchable_or_low_quality_image"
    assert hints[0]["url"] == "https://x.invalid/bad.jpg"


def test_download_repair_classifies_independent_image_fetch_hint_as_image_lane():
    hints = run_mod._download_diagnostic_image_repair_hints(
        {
            "sampleRejected": [
                "imageFetch: 测试景区甲#1 下载失败/非图片/过小 "
                "(https://x.invalid/gallery-bad.jpg)"
            ]
        },
        entity_id=_EID,
    )

    assert hints
    assert hints[0]["lane"] == "image"
    assert hints[0]["sourceId"] == ""
    assert hints[0]["action"] == "replace_unfetchable_or_low_quality_image"


def test_download_repair_lanes_are_driven_by_failure_summary_not_extra_hints():
    repair = {
        "issues": [
            "地点/景区/测试景区甲/1.download/sources: article research needs >= 4 text-qualified base sources"
        ],
        "researchLaneIssues": {},
        "imageRepairHints": [
            {"lane": "homepage", "issue": "generic homepage imageFetch failed"},
            {"lane": "article", "issue": "sourceImage:article_a failed"},
        ],
    }

    assert run_mod._download_repair_lanes(repair) == {"article"}


def test_download_repair_lanes_recognize_image_fetch_summary():
    repair = {
        "issues": [
            "测试景区甲: imageFetch: 未下到真实图片，请在 source_plan 提供可用 imageUrls(CC/PD/授权)"
        ],
        "researchLaneIssues": {},
        "imageRepairHints": [
            {"lane": "homepage", "issue": "legacy diagnostic fallback"},
        ],
    }

    assert run_mod._download_repair_lanes(repair) == {"image"}


def test_download_repair_lanes_route_encyclopedia_core_gap_to_homepage():
    repair = {
        "issues": [
            "天下第一泉景区: missing core source categories ['encyclopedia']"
        ],
        "researchLaneIssues": {},
        "imageRepairHints": [
            {"lane": "article", "issue": "sourceImage:article_a failed"},
        ],
    }

    assert run_mod._download_repair_lanes(repair) == {"homepage"}
    hints = run_mod._download_issue_repair_hints(
        repair["issues"],
        entity_id="天下第一泉景区",
    )
    assert hints[0]["lane"] == "homepage"
    assert hints[0]["action"] == "add_or_replace_homepage_encyclopedia_or_official_seed_source"


def test_download_issue_repair_hints_classify_image_gate_failure():
    hints = run_mod._download_issue_repair_hints(
        ["测试景区甲: image gates failed (rights/fetch/safety/min-count)"],
        entity_id=_EID,
    )

    assert hints
    assert hints[0]["lane"] == "image"
    assert hints[0]["action"] == "add_or_replace_image_source_collections_with_complete_rights"


def test_download_plan_prompt_includes_repair_only_article_lane():
    task_id = _make_task()
    batch_id = "download_repair_prompt_repair_only_lane"
    _seed_source_plan(task_id, batch_id)
    ctx = _ctx(task_id, batch_id)
    assert run_mod._source_plan_filled(ctx)[0] is True

    plan_dir = (
        resolve_entity_object_dir(task_id, batch_id, _EID, etype_hint="地点/景区")
        / STAGE_DOWNLOAD
    )
    plan_paths = [
        plan_dir / "homepage_source_plan.json",
        plan_dir / "article_source_plan.json",
        plan_dir / "image_source_plan.json",
    ]
    repair_path = run_mod._download_repair_path(ctx)
    write_json(
        repair_path,
        {
            "schemaVersion": "quwoquan.download_repair",
            "taskId": task_id,
            "batchId": batch_id,
            "entities": [
                {
                    "entityId": _EID,
                    "issues": [
                        f"{_EID}: article research needs >= 4 text-qualified base sources"
                    ],
                    "sourcePlanPath": str(plan_paths[0]),
                    "sourcePlanPaths": [str(path) for path in plan_paths],
                    "sourcePlanMtimeNs": max(path.stat().st_mtime_ns for path in plan_paths),
                    "reportPaths": ["reports/entity_source_bundle_gate/测试景区甲.json"],
                    "downloadDiagnostics": {
                        "entityId": _EID,
                        "sampleRejected": [
                            "sourceImage:article_official_planning: "
                            "测试景区甲/article_official_planning#1: "
                            "imageFetch failed/non-image/too small "
                            "(https://x.invalid/bad.jpg)"
                        ],
                    },
                    "researchLaneIssues": {},
                    "imageRepairHints": [
                        {
                            "lane": "article",
                            "sourceId": "article_official_planning",
                            "imageIndex": 1,
                            "action": "replace_unfetchable_or_low_quality_image",
                            "issue": "imageFetch failed/non-image/too small",
                        }
                    ],
                }
            ],
        },
    )

    prompts = run_mod._checkpoint_prompts(ctx, "download_plan")
    article_prompts = [prompt for prompt in prompts if "[AGENT_LANE:article]" in prompt]
    assert article_prompts
    assert "download_repair" in article_prompts[0]
    assert "text-qualified base sources" in article_prompts[0]
    assert "replace_unfetchable_or_low_quality_image" in article_prompts[0]


def test_download_plan_prompt_ignores_stale_repair_when_static_issue_remains():
    task_id = _make_task()
    batch_id = "download_repair_stale_static_issue"
    _seed_source_plan(task_id, batch_id)
    ctx = _ctx(task_id, batch_id)
    repair_path = run_mod._record_download_repair(
        ctx,
        [f"{_EID}: old fetch repair should be stale after source plan changes"],
    )
    assert repair_path.exists()

    plan_path = (
        resolve_entity_object_dir(task_id, batch_id, _EID, etype_hint="地点/景区")
        / STAGE_DOWNLOAD
        / "article_source_plan.json"
    )
    plan = read_json(plan_path)
    first_image = plan["payload"]["sources"][0]["imageUrls"][0]
    first_image["license"] = "factual_reference_only"
    write_json(plan_path, plan)
    current = plan_path.stat().st_mtime_ns
    os.utime(plan_path, ns=(current + 1_000_000_000, current + 1_000_000_000))

    prompts = run_mod._checkpoint_prompts(ctx, "download_plan")
    article_prompts = [prompt for prompt in prompts if "[AGENT_LANE:article]" in prompt]
    assert article_prompts
    assert "unsupported license factual_reference_only" in article_prompts[0]
    assert "old fetch repair should be stale" not in article_prompts[0]
    assert "这是 download_repair" not in article_prompts[0]


def test_download_plan_checkpoint_forces_auto_research_for_stale_source_rules():
    import download.prepare as prepare_mod
    import download.research_plan as research_mod

    task_id = _make_task()
    batch_id = "download_plan_stale_source_rules"
    _seed_source_plan(task_id, batch_id)
    ctx = _ctx(task_id, batch_id)
    assert run_mod._source_plan_filled(ctx)[0] is True

    plan_dir = (
        resolve_entity_object_dir(task_id, batch_id, _EID, etype_hint="地点/景区")
        / STAGE_DOWNLOAD
    )
    plan_paths = [
        plan_dir / "homepage_source_plan.json",
        plan_dir / "article_source_plan.json",
        plan_dir / "image_source_plan.json",
    ]
    rule_mtime = max(path.stat().st_mtime_ns for path in plan_paths) + 1_000_000_000
    calls: list[dict[str, object]] = []
    original_rule_mtime = run_mod._source_plan_rule_mtime_ns
    original_prepare = prepare_mod.prepare_source_plan
    original_auto = research_mod.write_auto_research_plans

    def fake_prepare_source_plan(*_args, **_kwargs):
        return None

    def fake_write_auto_research_plans(_task_id, _batch_id, entity_ids, **kwargs):
        calls.append({
            "entity_ids": list(entity_ids),
            "force": kwargs.get("force"),
            "has_progress_callback": callable(kwargs.get("progress_callback")),
        })
        progress_callback = kwargs.get("progress_callback")
        if callable(progress_callback):
            progress_callback({
                "status": "running",
                "entityId": _EID,
                "entityCount": len(entity_ids),
                "completedCount": 1,
                "remainingCount": 0,
                "workers": kwargs.get("max_workers"),
                "entitiesPerMinute": 60.0,
                "updatedAt": "2026-06-17T00:00:00+00:00",
                "message": "auto research completed 1/1",
            })
        fresh_mtime = rule_mtime + 1_000_000_000
        for path in plan_paths:
            os.utime(path, ns=(fresh_mtime, fresh_mtime))
        return {"issues": [], "sourceUnavailable": []}

    run_mod._source_plan_rule_mtime_ns = lambda _ctx: rule_mtime
    prepare_mod.prepare_source_plan = fake_prepare_source_plan
    research_mod.write_auto_research_plans = fake_write_auto_research_plans
    try:
        result = run_mod._checkpoint_download_plan(ctx)
    finally:
        run_mod._source_plan_rule_mtime_ns = original_rule_mtime
        prepare_mod.prepare_source_plan = original_prepare
        research_mod.write_auto_research_plans = original_auto

    assert result.status == "done"
    assert calls == [{"entity_ids": [_EID], "force": True, "has_progress_callback": True}]
    state = run_mod.load_workflow_state(task_id, batch_id)
    assert state["activeAutoResearch"]["completedCount"] == 1
    assert "download_plan auto_research 1/1" in state["nextAction"]
    assert "过期 source_plan" in result.message


def test_download_plan_stale_source_rules_override_pending_repair(monkeypatch):
    task_id = _make_task()
    batch_id = "download_plan_stale_over_repair"
    ctx = _ctx(task_id, batch_id)
    captured: dict[str, object] = {}
    checks = iter([(False, ["download_repair required: old source_plan_gate"]), (True, [])])
    stale_checks = iter([
        [{"entityId": _EID, "sourcePlanMtimeNs": 1, "sourceRuleMtimeNs": 2}],
        [],
    ])

    monkeypatch.setattr("task.run._source_plan_filled", lambda _ctx: next(checks))
    monkeypatch.setattr("task.run._download_retry_entity_ids", lambda _ctx: [_EID])
    monkeypatch.setattr(
        "task.run._stale_source_plan_entities",
        lambda _ctx, entity_ids: next(stale_checks),
    )

    def _fake_auto_research(_ctx, entity_ids, *, entity_type, force=False, scope="primary"):
        _ = (entity_type, scope)
        captured["entity_ids"] = list(entity_ids)
        captured["force"] = force
        return {"issues": [], "sourceUnavailable": []}

    monkeypatch.setattr("task.run._run_download_auto_research", _fake_auto_research)

    result = run_mod._checkpoint_download_plan(ctx)
    assert result.status == "done"
    assert captured == {"entity_ids": [_EID], "force": True}
    assert "过期 source_plan" in result.message


def test_download_fetch_refreshes_stale_source_plan_before_retry(monkeypatch):
    task_id = _make_task()
    batch_id = "download_fetch_stale_source_plan_refresh"
    ctx = _ctx(task_id, batch_id)
    captured: dict[str, object] = {}

    monkeypatch.setattr("task.run._download_retry_entity_ids", lambda _ctx: [_EID])
    monkeypatch.setattr("task.run._download_fetch_stale_entity_ids", lambda _ctx: [])
    monkeypatch.setattr("task.run._content_plan_source_shortfall_entity_ids", lambda _ctx: [])
    monkeypatch.setattr(
        "task.run._stale_source_plan_entities",
        lambda _ctx, entity_ids: [{"entityId": _EID}] if list(entity_ids) == [_EID] else [],
    )

    def _fake_prepare_source_plan(_task_id, _batch_id, entities, **_kwargs):
        captured["prepared_entities"] = [entity["entityId"] for entity in entities]

    def _fake_auto_research(_ctx, entity_ids, *, entity_type, force=False, scope="primary"):
        captured["auto_entity_ids"] = list(entity_ids)
        captured["auto_force"] = force
        captured["auto_scope"] = scope
        captured["entity_type"] = entity_type
        return {"issues": [], "sourceUnavailable": []}

    def _fake_handle_download(ns):
        captured["download_entity_ids"] = ns.entity_ids

    monkeypatch.setattr("download.prepare.prepare_source_plan", _fake_prepare_source_plan)
    monkeypatch.setattr("task.run._run_download_auto_research", _fake_auto_research)
    monkeypatch.setattr("download.handler.handle_download", _fake_handle_download)
    monkeypatch.setattr("download.gate.gate_download", lambda *_args, **_kwargs: [])

    result = run_mod._run_download_fetch(ctx)
    assert result.status == "done"
    assert captured["prepared_entities"] == [_EID]
    assert captured["auto_entity_ids"] == [_EID]
    assert captured["auto_force"] is True
    assert captured["auto_scope"] == "download_fetch_stale_source_plan"
    assert captured["download_entity_ids"] == _EID


def test_download_fetch_does_not_auto_research_fetch_stale_only_entities(monkeypatch):
    task_id = _make_task()
    batch_id = "download_fetch_stale_only_no_research"
    ctx = _ctx(task_id, batch_id)
    ctx.entity_ids = [_EID, "额外景区乙"]
    captured: dict[str, object] = {}

    monkeypatch.setattr("task.run._download_retry_entity_ids", lambda _ctx: [])
    monkeypatch.setattr("task.run._download_fetch_stale_entity_ids", lambda _ctx: [_EID, "额外景区乙"])
    monkeypatch.setattr("task.run._content_plan_source_shortfall_entity_ids", lambda _ctx: [])

    def _unexpected_stale_source_plan_check(*_args, **_kwargs):
        raise AssertionError("fetch-stale-only entities must not be sent back to source-plan refresh")

    def _unexpected_auto_research(*_args, **_kwargs):
        raise AssertionError("fetch-stale-only entities must not trigger auto research")

    def _fake_handle_download(ns):
        captured["download_entity_ids"] = ns.entity_ids
        captured["download_lane"] = ns.lane

    monkeypatch.setattr("task.run._stale_source_plan_entities", _unexpected_stale_source_plan_check)
    monkeypatch.setattr("task.run._run_download_auto_research", _unexpected_auto_research)
    monkeypatch.setattr("download.handler.handle_download", _fake_handle_download)
    monkeypatch.setattr("download.gate.gate_download", lambda *_args, **_kwargs: [])

    result = run_mod._run_download_fetch(ctx)
    assert result.status == "done"
    assert captured["download_entity_ids"] == f"{_EID},额外景区乙"
    assert captured["download_lane"] == "all"


def test_download_stage_gate_issues_scopes_source_screen_by_payload_entity():
    task_id = _make_task()
    batch_id = "download_source_screen_scope"
    ctx = _ctx(task_id, batch_id)
    write_gate_report(
        task_id=task_id,
        batch_id=batch_id,
        command="download",
        step="source_screen",
        ref="测试景区甲__article_qunar_base_1",
        passed=False,
        issues=["sourceScreen: source scored Reject"],
        evidence_summary={"entityId": _EID, "sourceId": "article_qunar_base_1"},
    )
    write_gate_report(
        task_id=task_id,
        batch_id=batch_id,
        command="download",
        step="source_screen",
        ref="无关景区乙__article_qunar_base_1",
        passed=False,
        issues=["sourceScreen: source scored Reject"],
        evidence_summary={"entityId": "无关景区乙", "sourceId": "article_qunar_base_1"},
    )

    issues = run_mod._download_stage_gate_issues(ctx, entity_ids=[_EID])
    assert issues == [
        "测试景区甲__article_qunar_base_1: sourceScreen: source scored Reject"
    ]


def test_managed_preflight_rejects_missing_key_without_creating_batch():
    task_id = _make_task()
    spec = store.load_spec(task_id)
    spec["status"] = "active"
    spec.setdefault("content", {})["quotas"] = {
        "entityArticlesPerTarget": 2,
        "imageWorksPerTarget": 2,
        "entityHomepagesPerTarget": 1,
        "routeArticles": 0,
    }
    old_key = os.environ.pop("CURSOR_API_KEY", None)
    try:
        issues = run_mod._managed_preflight(
            task_id,
            "preflight_no_key",
            spec,
            argparse.Namespace(runtime="local", baseline_packet=None),
        )
    finally:
        if old_key is not None:
            os.environ["CURSOR_API_KEY"] = old_key
    assert "CURSOR_API_KEY missing" in issues
    assert not batch_root(task_id, "preflight_no_key").exists()


class _MiniMonkeyPatch:
    def __init__(self) -> None:
        self._restore: list[tuple[object, str, object]] = []
        self._env_restore: list[tuple[str, str | None]] = []

    def setattr(self, target: str, value) -> None:
        module_name, attr = target.rsplit(".", 1)
        module = importlib.import_module(module_name)
        old = getattr(module, attr)
        self._restore.append((module, attr, old))
        setattr(module, attr, value)

    def setenv(self, key: str, value: str) -> None:
        self._env_restore.append((key, os.environ.get(key)))
        os.environ[key] = value

    def undo(self) -> None:
        while self._restore:
            module, attr, old = self._restore.pop()
            setattr(module, attr, old)
        while self._env_restore:
            key, old = self._env_restore.pop()
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        params = inspect.signature(fn).parameters
        if "monkeypatch" in params:
            monkeypatch = _MiniMonkeyPatch()
            try:
                fn(monkeypatch)
            finally:
                monkeypatch.undo()
        else:
            fn()
        print(f"PASS {fn.__name__}")
    print(f"task run pipeline tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
