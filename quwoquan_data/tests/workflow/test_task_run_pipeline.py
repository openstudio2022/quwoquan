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
import hashlib
import importlib
import inspect
import os
import sys
import tempfile
from io import BytesIO
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="task_run_"))
os.environ["QWQ_DATA_ROOT"] = str(_TMP)
os.environ["QWQ_RUNTIME_ROOT"] = str(_TMP / "runtime")
os.environ["QWQ_PUBLISH_ROOT"] = str(_TMP / "publish")
os.environ["QWQ_COMMITTED_TASKS_ROOT"] = str(_TMP / "tasks")

sys.path.insert(0, str(SCRIPTS_ROOT))

from _common.draft_io import draft_article_path, write_placeholder_draft  # noqa: E402
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


def _make_task() -> str:
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
        ("article_baike", "百度百科", "https://x.invalid/a"),
        ("article_wiki", "维基百科", "https://x.invalid/b"),
        ("article_official", "景区官网", "https://x.invalid/c"),
        ("article_guide", "马蜂窝", "https://x.invalid/d"),
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
                for sid, platform, url in article_sources
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

    def _fake_source_fetch(url: str):
        return {
            "url": url,
            "statusCode": 200,
            "htmlBytes": b"<html></html>",
            "text": (
                f"{_EID} 位于测试省山地森林地带，适合安排半日到一日游。"
                f"景区开放时间、门票、观光车与交通接驳信息需要在出发前确认，"
                f"主景段和栈道段体验差异明显。清晨徒步更舒服，午后返程更容易排队，"
                f"如遇雨天，路况湿滑，应预留补给和返程时间。"
            ),
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
    code = _run_pipeline_with_fake_download(_ctx(task_id, "b2"))  # resume
    assert code == 10, f"expected next-checkpoint pause(10), got {code}"
    state = run_mod.load_workflow_state(task_id, "b2")
    # download_plan/fetch/build_prepare 应已完成，停在 build_homepage
    assert "download_plan" in state["completed"]
    assert "download_fetch" in state["completed"]
    assert "build_prepare" in state["completed"]
    assert state["waitingCheckpoint"] == "build_homepage"


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
    assert pending == ["(no article drafts; run compose-brief first)"]

    content_object.register_content_object(task_id, batch_id, "新", content_type="article", angle="体验", title="新")
    write_placeholder_draft(task_id, batch_id, "新")
    ok, pending = run_mod._drafts_authored(ctx)
    assert ok is False and pending == ["新"]
    draft_article_path(task_id, batch_id, "新").write_text("# 新正文\n\n这是 Agent 完成的正文。", encoding="utf-8")
    ok, pending = run_mod._drafts_authored(ctx)
    assert ok is True and pending == []


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


def test_real_local_cursor_runner_defaults_to_serial_bridge_workers():
    task_id = _make_task()
    ctx = _ctx(task_id, "managed_cursor_workers")
    ctx.runtime = "local"
    ctx.max_workers = 10
    ctx.agent_runner = None
    assert run_mod._managed_checkpoint_worker_count(ctx, 5) == 1

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
    assert len(calls) == 1
    state = run_mod.load_workflow_state(task_id, batch_id)
    assert state["status"] == "repairing"
    outcome = state["lastAgentRun"]["outcomes"][0]
    assert outcome["started"] is True
    assert outcome["status"] == "error"
    assert "checkpoint lane gate still fails" in outcome["error"]
    assert outcome["gateIssues"]


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


def test_download_repair_lanes_are_driven_by_failure_summary_not_extra_hints():
    repair = {
        "issues": [
            "地点/景区/测试景区甲/1.download/sources: only 3 article source unit(s) with images"
        ],
        "researchLaneIssues": {},
        "imageRepairHints": [
            {"lane": "homepage", "issue": "generic homepage imageFetch failed"},
            {"lane": "article", "issue": "sourceImage:article_a failed"},
        ],
    }

    assert run_mod._download_repair_lanes(repair) == {"article"}


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
                        f"{_EID}: only 3 article source unit(s) with images "
                        "(need >= 4; article base draft must be text+source images)"
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
    assert "only 3 article source unit" in article_prompts[0]
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

    def setattr(self, target: str, value) -> None:
        module_name, attr = target.rsplit(".", 1)
        module = importlib.import_module(module_name)
        old = getattr(module, attr)
        self._restore.append((module, attr, old))
        setattr(module, attr, value)

    def undo(self) -> None:
        while self._restore:
            module, attr, old = self._restore.pop()
            setattr(module, attr, old)


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
