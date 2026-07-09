"""重建「对象同构 + 来源内聚 + 资产可追溯 + 相对路径」代表样例批次。

产出 docs/pipeline_directory_layout_spec.md 规定的新布局样例（无网络、确定性）：
  batches/{batch}/entities/地点/景区/峨眉山/     （实体对象 + 来源单元 + 成品）
  batches/{batch}/entities/地点/景区/海螺沟/     （实体对象 + 来源单元 + 成品）
  batches/{batch}/posts/article/环线攻略/.../1/   （内容对象，asset:// 可直查源图）

用法：python3 quwoquan_data/scripts/publish_ops/rebuild_directory_layout_sample.py [--task T --batch B]
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
import shutil
import sys
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_ROOT))

import numpy as np
import cv2

from _common import content_object
from _common.article_package import compute_document_sha256
from _common.batch_asset_registry import allocate_post_asset_id, load_batch_asset_registry
from _common.batch_manifest import load_batch_manifest, write_batch_manifest
from _common.io import read_json, write_json
from _common.paths import (
    batch_entity_object_dir,
    batch_manifest_path,
    batch_root,
    ensure_batch_layout,
    ensure_task_layout,
    relative_batch_ref,
)
from _common.source_unit import object_image_candidates, write_source_unit

DEFAULT_TASK = "旅行/地域/四川省/景区/景区全覆盖"
DEFAULT_BATCH = "layout_sample"
FORBIDDEN_TOP_LEVEL_DIRS = ("download", "build", "produce", "pipeline", "publish")

ENTITIES = {
    "峨眉山": {
        "source_md": (
            "# 峨眉山\n\n"
            "峨眉山位于四川盆地西南缘，最高峰万佛顶海拔约 3099 米，是著名的佛教名山与世界遗产。"
            "金顶常见云海、日出与佛光；从山脚到金顶垂直气候差异明显，山下温暖、金顶湿冷。"
            "建议清晨上金顶看日出，午后转至清音阁、一线天等中低山区域；雨雾多发，需带防滑与保暖装备。\n\n"
            "适宜季节以春（4-5 月杜鹃）与秋（10 月红叶、能见度高）为佳；夏季多雨、冬季金顶易冰雪封山。"
        ),
    },
    "海螺沟": {
        "source_md": (
            "# 海螺沟\n\n"
            "海螺沟位于贡嘎山东坡，以低海拔现代冰川与温泉著称，沟内可乘观光车加索道近距离观赏冰川。"
            "清晨晴天常能看到贡嘎雪山被照亮；午后可在山下泡温泉缓解徒步疲劳。"
            "全程海拔变化大，需防高原反应、强紫外线与昼夜温差；秋季红叶与彩林窗口短而集中。"
        ),
    },
}


def _texture(seed: int) -> bytes:
    # 尺寸需满足像素门：宽≥640、高≥426、长边≥800（见 _common.image_rules）。
    rng = np.random.default_rng(seed)
    canvas = rng.integers(0, 255, size=(640, 960, 3), dtype=np.uint8)
    for k in range(6):
        c = tuple(int(x) for x in rng.integers(0, 255, size=3))
        cv2.rectangle(canvas, (40 + k * 60, 40 + k * 36), (360 + k * 50, 320 + k * 24), c, -1)
        cv2.circle(canvas, (600 + k * 20, 240 + k * 40), 60 + k * 12, c, -1)
    canvas = cv2.GaussianBlur(canvas, (5, 5), 0)
    ok, buf = cv2.imencode(".jpg", canvas, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
    assert ok
    return buf.tobytes()


def _ensure_object_stages(obj: Path, stages: tuple[str, ...]) -> None:
    for stage in stages:
        (obj / stage).mkdir(parents=True, exist_ok=True)


def _build_entity(
    task: str,
    batch: str,
    name: str,
    spec: dict,
    seed: int,
    *,
    global_batch_seq: int,
    asset_registry,
) -> Path:
    obj = batch_entity_object_dir(task, batch, "地点", "景区", name)
    if obj.exists():
        shutil.rmtree(obj)
    _ensure_object_stages(obj, ("1.download", "2.quality", "3.compose", "4.draft", "5.review"))
    images = [
        {"bytes": _texture(seed + i), "url": f"https://commons.example/{name}/{i}.jpg",
         "license": "CC BY-SA (Wikimedia Commons)", "credit": "Wikimedia Commons",
         "caption": f"{name}实景{i}", "relevance": f"{name}核心体验配图", "slug": name}
        for i in range(1, 4)
    ]
    source_manifest = write_source_unit(
        obj,
        ordinal=1,
        source_id="overview_baike",
        source_md=spec["source_md"],
        clean_md=spec["source_md"],
        quality={"sourceId": "overview_baike", "quality": "Good", "score": 4, "url": f"https://zh.wikipedia.org/wiki/{name}"},
        platform="baike",
        source_category="overview_baike",
        url=f"https://zh.wikipedia.org/wiki/{name}",
        title=f"{name}（维基百科）",
        target_ref=f"/entity/地点/景区/{name}",
        relevance=f"覆盖 {name} 的基础事实、交通、季节与海拔",
        images=images,
        task_id=task,
        batch_id=batch,
    )
    source_ref = str(source_manifest["sourceRef"])
    source_unit_ref = str(source_manifest["sourceUnitRef"])
    # 实体成品（落对象根，与 publish 同构）
    cands = object_image_candidates(obj, task, batch)
    assets_dir = obj / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    manifest_assets = []
    page_figs = []
    for i, cand in enumerate(cands[:2], start=1):
        asset_role = "cover" if i == 1 else "detail"
        asset_id = allocate_post_asset_id(
            entity_name=name,
            role=asset_role,
            ref=f"entity/{name}#{cand['sourceAssetRef']}",
            global_batch_seq=global_batch_seq,
            registry=asset_registry,
            caption=str(cand.get("caption") or ""),
            ordinal=i,
        )
        ext = cand["path"].suffix.lower()
        dest = assets_dir / f"{asset_id}{ext}"
        dest.write_bytes(cand["path"].read_bytes())
        manifest_assets.append({
            "assetId": asset_id,
            "fileName": dest.name,
            "caption": cand["caption"] or f"{name}实景",
            "imageLayout": "fullWidth" if i == 1 else "gallery",
            "sourceAssetRef": cand["sourceAssetRef"],
            "sourceRef": cand["sourceRef"],
        })
        page_figs.append(f':::figure id="fig{i}" layout="{"fullWidth" if i == 1 else "gallery"}" caption="{cand["caption"] or name+"实景"}"\nasset://{asset_id}\n:::')
    page_md = (
        f"# {name}\n\n"
        f"{spec['source_md'].split(chr(10), 2)[-1].strip()}\n\n"
        + "\n\n".join(page_figs)
        + f"\n\n## 出发前要确认的事\n\n把到达、门票时段、海拔与保暖装备就地确认好；"
        f"值不值得专程跑一趟，于我是值的，慢慢来即可。\n"
    )
    (obj / "page.md").write_text(page_md, encoding="utf-8")
    (obj / "4.draft" / "page.md").write_text(page_md, encoding="utf-8")
    page_digest = compute_document_sha256(page_md)
    write_json(obj / "2.quality" / "quality_analysis.json", {
        "sourcePaths": [source_ref],
        "recommendation": "proceed",
        "baseDraft": {
            "sourceRef": source_ref,
            "mode": "factual_reference_only",
        },
    })
    write_json(obj / "_entity.json", {
        "label": name,
        "domain": "地点",
        "type": "景区",
        "sourceTaskId": task,
        "tagRefs": [],
    })
    write_json(obj / "manifest.json", {
        "schemaVersion": "quwoquan_data.entity_manifest",
        "entityRef": f"/entity/地点/景区/{name}",
        "assets": manifest_assets,
        "citedSourceRefs": [source_ref],
    })
    review_dir = obj / "5.review"
    review_dir.mkdir(parents=True, exist_ok=True)
    write_json(review_dir / "review.json", {
        "decision": "approved",
        "checks": {
            "sourceReadiness": {"passed": True},
            "entityPageQuality": {"passed": True},
        },
    })
    write_json(review_dir / "provenance.json", {
        "schemaVersion": "quwoquan_data.entity_provenance",
        "final": {
            "entityRef": f"/entity/地点/景区/{name}",
            "generator": "agent",
            "pageDigest": page_digest,
        },
        "agentInput": {
            "writingPack": "3.compose/entity_page_input.json",
            "prompt": "4.draft/page.md",
        },
        "originalSources": [{"path": source_ref, "url": f"https://zh.wikipedia.org/wiki/{name}"}],
    })
    write_json(review_dir / "finalization_report.json", {
        "draftArticleRef": "4.draft/page.md",
        "finalArticleRef": "page.md",
        "draftSha256": page_digest,
        "finalSha256": page_digest,
    })
    return obj


def _build_post(task: str, batch: str, *, global_batch_seq: int, asset_registry) -> Path:
    name = "海螺沟"
    ent = batch_entity_object_dir(task, batch, "地点", "景区", name)
    cands = object_image_candidates(ent, task, batch)
    # 经路由登记内容对象（坐标真相源），post 目录由路由解析，保证与 content_object_index 同步。
    ref = "海螺沟_体验"
    content_object.register_content_object(
        task, batch, ref, content_type="article", angle="环线攻略", title="在海螺沟看冰川泡温泉"
    )
    post = content_object.content_object_dir(task, batch, ref)
    if post.exists():
        shutil.rmtree(post)
    _ensure_object_stages(post, ("1.download", "2.quality", "3.compose", "4.draft", "5.review"))
    assets_dir = post / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    roles = [("cover", "fullWidth"), ("detail_1", "gallery"), ("closing", "fullWidth")]
    assets = []
    figures = []
    for idx, ((role, layout), cand) in enumerate(zip(roles, cands), start=1):
        asset_role = "detail" if role.startswith("detail") else role
        asset_id = allocate_post_asset_id(
            entity_name=name,
            role=asset_role,
            ref=f"{ref}#{cand['sourceAssetRef']}",
            global_batch_seq=global_batch_seq,
            registry=asset_registry,
            caption=str(cand.get("caption") or ""),
            ordinal=idx,
        )
        ext = cand["path"].suffix.lower()
        dest = assets_dir / f"{asset_id}{ext}"
        dest.write_bytes(cand["path"].read_bytes())
        assets.append({
            "assetId": asset_id,
            "fileName": dest.name,
            "caption": cand["caption"] or "海螺沟",
            "kind": "image",
            "scope": "cold_start",
            "objectKey": f"media/image/s/archived-image/post/海螺沟环线/{role}{ext}",
            "imageLayout": layout,
            "sha256": "",
            "sourceAssetRef": cand["sourceAssetRef"],
            "sourceRef": cand["sourceRef"],
        })
        figures.append(f':::figure id="{role}" layout="{layout}" caption="{cand["caption"] or "海螺沟"}"\nasset://{asset_id}\n:::')
    article_md = (
        "---\ntitle: 在海螺沟看冰川泡温泉：两天高原徒步体验\ntemplate: journal\narticleMarkdownVersion: qwq-rich-md/1\n---\n\n"
        "# 在海螺沟看冰川泡温泉：两天高原徒步体验\n\n"
        "清晨的贡嘎被第一缕阳光点亮时，我正站在观景台上发抖——值了。\n\n"
        f"{figures[0]}\n\n"
        "## 第一天：进沟看冰川\n\n"
        "乘观光车加索道上行，低海拔现代冰川近在眼前；午后下撤泡温泉，缓解徒步带来的疲惫。\n\n"
        f"{figures[1]}\n\n"
        "## 出发前真正要确认的事\n\n"
        "海拔变化大，注意高原反应、强紫外线与昼夜温差；秋季红叶与彩林窗口短，挑晴天清晨上山最稳。\n\n"
        f"{figures[2]}\n\n"
        "如果你时间只够一天、体能一般，老实坐车看够冰川、下午泡温泉就很好；"
        "若有两天、愿意为风景吃点苦，就把观景台留给状态最好的清晨。于我，这趟是值的。\n"
    )
    (post / "article.md").write_text(article_md, encoding="utf-8")
    (post / "4.draft" / "draft.article.md").write_text(article_md, encoding="utf-8")
    render_profile = {"template": "journal", "fontPreset": "handwritten"}
    article_digest = compute_document_sha256(article_md)
    source_refs = read_json(ent / "1.download" / "source_refs.json")
    source_row = (source_refs.get("sources") or [])[0]
    source_ref = str(source_row["sourceRef"])
    source_unit_ref = str(source_row.get("sourceUnitRef") or source_ref.rsplit("/", 1)[0])
    # 单底稿零参考宪法 v2：source_refs.json 只登记唯一底稿来源，
    # 禁止 citedSourceRefs / sourcePaths 等第二来源或全量索引字段。
    write_json(post / "1.download" / "source_refs.json", {
        "baseSourceRef": source_ref,
        "sources": [
            {
                "sourceRef": source_ref,
                "sourceUnitRef": source_unit_ref,
                "role": "base",
            }
        ],
    })
    manifest = {
        "schemaVersion": "quwoquan_data.post_manifest",
        "topicId": "海螺沟_体验",
        "contentType": "article",
        "entityRefs": ["/entity/地点/景区/海螺沟"],
        "tagRefs": ["Topic/旅行", "Format/内容角度/攻略"],
        "assets": [{"assetId": a["assetId"], "fileName": a["fileName"], "caption": a["caption"],
                    "imageLayout": a["imageLayout"], "sourceAssetRef": a["sourceAssetRef"], "sourceRef": a["sourceRef"]} for a in assets],
        "template": "journal",
        "carrier": "article",
        "generator": "agent",
        "generatorModel": "sample-rebuild",
        "citedSourceRefs": [source_ref],
        "reviewDecision": "approved",
        "articleMarkdownVersion": "qwq-rich-md/1",
        "articleRenderProfile": render_profile,
        "publishLayout": "entity",
        "publishAngle": "环线攻略",
        "publishTitle": "在海螺沟看冰川泡温泉：两天高原徒步体验",
        "publishSeq": 1,
        "sourceTaskId": task,
        "sourceBatchId": batch,
    }
    write_json(post / "manifest.json", manifest)
    review_dir = post / "5.review"
    review_dir.mkdir(parents=True, exist_ok=True)
    write_json(review_dir / "provenance.json", {
        "schemaVersion": "quwoquan_data.provenance",
        "ref": "海螺沟_体验",
        "final": {"publishTitle": manifest["publishTitle"], "publishSeq": 1, "generator": "agent",
                  "articleDigest": article_digest, "entityRefs": manifest["entityRefs"]},
        "agentInput": {"writingPack": "3.compose/writing_pack.json", "prompt": "4.draft/prompt.md"},
        "originalSources": [{"path": source_ref, "url": "https://zh.wikipedia.org/wiki/海螺沟"}],
        "gateResults": {"decision": "approved", "checks": {}},
        "citedSourcePaths": [source_ref],
    })
    write_json(review_dir / "finalization_report.json", {
        "draftArticleRef": "4.draft/draft.article.md",
        "finalArticleRef": "article.md",
        "draftSha256": article_digest,
        "finalSha256": article_digest,
    })
    # 对象索引 _object.json（§14.3）：与真实 materialize 一致。
    content_object.write_content_object_index(task, batch, ref)
    return post


def rebuild(task: str, batch: str) -> Path:
    ensure_task_layout(task)
    ensure_batch_layout(task, batch, "download")
    root = batch_root(task, batch)
    for top_level in FORBIDDEN_TOP_LEVEL_DIRS:
        top_level_path = root / top_level
        if top_level_path.exists():
            shutil.rmtree(top_level_path)
    write_batch_manifest(task, batch, command="rebuild_sample")
    manifest = load_batch_manifest(task, batch)
    manifest.update(
        {
            "purpose": "目录与资产证据链新布局代表样例（确定性重建，无网络）",
            "objects": {
                "entities": ["地点/景区/峨眉山", "地点/景区/海螺沟"],
                "posts": ["article/环线攻略/在海螺沟看冰川泡温泉/1"],
            },
        }
    )
    write_json(batch_manifest_path(task, batch), manifest)
    global_batch_seq = int(manifest.get("globalBatchSeq") or 0)
    asset_registry = load_batch_asset_registry(task, batch, global_batch_seq)
    for i, (name, spec) in enumerate(ENTITIES.items()):
        _build_entity(
            task,
            batch,
            name,
            spec,
            seed=1000 + i * 100,
            global_batch_seq=global_batch_seq,
            asset_registry=asset_registry,
        )
    _build_post(task, batch, global_batch_seq=global_batch_seq, asset_registry=asset_registry)
    return root


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="重建目录与资产证据链代表样例")
    parser.add_argument("--task", default=DEFAULT_TASK)
    parser.add_argument("--batch", default=DEFAULT_BATCH)
    args = parser.parse_args(argv)
    root = rebuild(args.task, args.batch)
    print(f"rebuilt sample at: {root}")
    from verify.verify_directory_evidence_chain import scan_batch

    issues = scan_batch(args.task, args.batch)
    if issues:
        print("FAIL evidence chain:")
        for i in issues:
            print(f"  - {i}")
        return 1
    print("PASS evidence chain on rebuilt sample")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
