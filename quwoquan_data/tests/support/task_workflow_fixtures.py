"""Shared fixtures and helpers for task workflow tests."""



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

import shutil

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

from _common.draft_io import (  # noqa: E402
    draft_article_path,
    draft_meta_path,
    prompt_path,
    writing_pack_path,
    write_image_evidence_draft,
    write_placeholder_draft,
    write_writing_pack,
)

from _common.command_packet import build_packet, write_packet

from _common.io import read_json, write_json

from _common.stage_reports import write_gate_report

from _common import content_object

from _common.paths import (  # noqa: E402
    batch_posts_root,
    batch_root,
    batch_workflow_state_path,
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

from _common.source_unit import resolve_entity_object_dir, write_source_unit as write_structured_source_unit

from _common.release_integrity import ARTICLE_HARD_CHECKS

from task import object_queue as oq

from task import run as run_mod

from task import store

_EID = "测试景区甲"

_TASK_COUNTER = 0

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
    global _TASK_COUNTER
    _TASK_COUNTER += 1
    spec = store.scaffold_spec(
        vertical="travel",
        organize_by="地域",
        key="测试省",
        name=f"景区全覆盖{_TASK_COUNTER}",
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
                "imageAssetStrategy": "open_license_publish",
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

    def _fake_payload(url, *, min_bytes=3000, max_bytes=0):
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
    orig_capacity = run_mod._download_content_capacity_preflight
    try:
        download_handler_mod.fetch_image_payload = _fake_payload
        download_handler_mod.fetch_source_payload = _fake_source_fetch
        run_mod._download_content_capacity_preflight = lambda _ctx: []
        return run_mod.run_pipeline(ctx)
    finally:
        download_handler_mod.fetch_image_payload = orig_payload
        download_handler_mod.fetch_source_payload = orig_source
        run_mod._download_content_capacity_preflight = orig_capacity

def _long_base_text(title: str) -> str:
    sentence = (
        f"{title}的底稿围绕入口动线、核心景观、停留节奏、季节差异和安全边界展开，"
        "其中图片记录的是同一来源页面内的现场画面，文字说明与图片主题保持一致。"
        "这段资料只用于事实核验，成稿需要重新组织结构和表达。"
    )
    return "# 底稿\n\n" + "\n\n".join(sentence for _ in range(12))

def _creator_assignment() -> dict[str, object]:
    creator_dir = _TMP / "templates" / "creator_profiles" / "system_builtin"
    creator_dir.mkdir(parents=True, exist_ok=True)
    creator_path = creator_dir / "travel_blogger_chuanxi.creator.yaml"
    if not creator_path.is_file():
        creator_path.write_text(
            """
creatorProfileId: qwq_creator_travel_blogger_chuanxi_001
authorId: builtin_travel_blogger_chuanxi
creatorArchetype: travel_blogger
status: active
profileVersion: "1.0.0"
disclosure:
  type: platform_virtual_creator
  displayText: 平台虚拟创作者，内容由资料整理与 AI 辅助生成，经平台审核发布。
  visible: true
claimPolicy:
  experienceClaimMode: editorial_synthesis
  mayUseFirstPerson: false
  mustCiteEvidenceForClaims: true
carrierAffinity:
  article: 0.55
  image: 0.4
  video: 0.05
""".lstrip(),
            encoding="utf-8",
        )
    return {
        "authorId": "builtin_travel_blogger_chuanxi",
        "creatorProfileId": "qwq_creator_travel_blogger_chuanxi_001",
        "creatorArchetype": "travel_blogger",
        "creatorProfileVersion": "1.0.0",
        "creatorDisclosure": {
            "type": "platform_virtual_creator",
            "displayText": "平台虚拟创作者，内容由资料整理与 AI 辅助生成，经平台审核发布。",
            "visible": True,
        },
        "experienceClaimMode": "editorial_synthesis",
        "authorQualitySignals": {"qualityScore": 0.86, "fatigueScore": 0.2, "riskTier": "low"},
    }

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



__all__ = sorted(name for name in globals() if name != "__all__" and not name.startswith("__"))

