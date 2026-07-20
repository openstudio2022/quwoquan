#!/usr/bin/env python3
"""幂等地把混合对象卡（entity_homepage）验收种子应用到 content-service 的 Mongo（gamma-local）。

env-seed-first：唯一真相源是
quwoquan_service/contracts/metadata/_shared/test_fixtures/content_recommendation_object_cards.gamma_seed.json，
本脚本只读消费该 fixture，向 quwoquan_content 库幂等 upsert（N2-2）：

  - rm_recommend_feature.entityInstanceAffinities.<entityRef>  —— 对象卡召回信号 1（隐式亲和）
  - entity_wishlist_events: { userId, entityId, status, updatedAt } —— 信号 2（显式想去），
    字段与 MongoWishlistEventStore 写入 schema 逐字段对齐
  - entities: { entityRef, label, name, hasPage, tagRefs }     —— 展示装配（hasPage=true 才成卡）
  - posts.entityMentions: { subjectId, homepageId }            —— homepageId 路由解析锚点
    （无 canonical homepage 解析的实体 fail-closed 不成卡）

用法（gamma-local）：
  python3 quwoquan_service/services/seed-box/scripts/apply_content_object_cards_seed.py \
    --container quwoquan_service-mongodb-1 --db quwoquan_content
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_FIXTURE = (
    ROOT
    / "quwoquan_service"
    / "contracts"
    / "metadata"
    / "_shared"
    / "test_fixtures"
    / "content_recommendation_object_cards.gamma_seed.json"
)


def build_mongo_script(fixture: dict, viewer_id_override: str = "") -> str:
    """把 fixture 编译成幂等 mongosh JS（值经 json.dumps 安全转义）。"""
    viewer_id = viewer_id_override.strip() or str(fixture.get("viewerId") or "").strip()
    if not viewer_id:
        raise SystemExit("fixture viewerId is required")
    vid = json.dumps(viewer_id, ensure_ascii=False)

    lines: list[str] = [
        "var applied={affinities:0,wishlist:0,entities:0,postMentions:0};"
    ]

    for entity_ref, score in (fixture.get("entityInstanceAffinities") or {}).items():
        field = json.dumps(
            "userFeatures.entityInstanceAffinities." + str(entity_ref),
            ensure_ascii=False,
        )
        lines.append(
            "db.rm_recommend_feature.updateOne("
            f"{{userId:{vid}}}, "
            f"{{$set:{{userId:{vid}, {field}:{float(score)}}}}}, "
            "{upsert:true});"
        )
        lines.append("applied.affinities += 1;")

    for event in fixture.get("wishlistEvents", []):
        entity_id = json.dumps(str(event["entityId"]), ensure_ascii=False)
        object_type = json.dumps(str(event.get("objectType") or ""), ensure_ascii=False)
        display_name = json.dumps(str(event.get("displayName") or ""), ensure_ascii=False)
        status = json.dumps(str(event.get("status") or "active"), ensure_ascii=False)
        source_surface = json.dumps(str(event.get("sourceSurface") or ""), ensure_ascii=False)
        lines.append(
            "applied.wishlist += db.entity_wishlist_events.updateOne("
            f"{{userId:{vid}, entityId:{entity_id}}}, "
            f"{{$set:{{userId:{vid}, entityId:{entity_id}, objectType:{object_type}, "
            f"displayName:{display_name}, status:{status}, sourceSurface:{source_surface}, "
            "updatedAt:new Date()}, $setOnInsert:{createdAt:new Date()}}, "
            "{upsert:true}).upsertedCount;"
        )

    for entity in fixture.get("entities", []):
        entity_ref = json.dumps(str(entity["entityRef"]), ensure_ascii=False)
        label = json.dumps(str(entity.get("label") or ""), ensure_ascii=False)
        name = json.dumps(str(entity.get("name") or ""), ensure_ascii=False)
        has_page = "true" if bool(entity.get("hasPage", False)) else "false"
        tag_refs = json.dumps(list(entity.get("tagRefs") or []), ensure_ascii=False)
        lines.append(
            "db.entities.updateOne("
            f"{{entityRef:{entity_ref}}}, "
            f"{{$set:{{entityRef:{entity_ref}, label:{label}, name:{name}, hasPage:{has_page}, "
            f"tagRefs:{tag_refs}, source:\"gamma_object_cards_seed\", updatedAt:new Date()}}}}, "
            "{upsert:true});"
        )
        lines.append("applied.entities += 1;")

    for post in fixture.get("postEntityMentions", []):
        post_id = json.dumps(str(post["postId"]), ensure_ascii=False)
        title = json.dumps(str(post.get("title") or ""), ensure_ascii=False)
        content_type = json.dumps(str(post.get("contentType") or "image"), ensure_ascii=False)
        status = json.dumps(str(post.get("status") or "published"), ensure_ascii=False)
        author_id = json.dumps(str(post.get("authorId") or ""), ensure_ascii=False)
        mentions = json.dumps(
            [
                {
                    "subjectId": str(m["subjectId"]),
                    "homepageId": str(m["homepageId"]),
                }
                for m in post.get("entityMentions", [])
            ],
            ensure_ascii=False,
        )
        lines.append(
            "db.posts.updateOne("
            f"{{_id:{post_id}}}, "
            f"{{$set:{{title:{title}, contentType:{content_type}, status:{status}, "
            f"authorId:{author_id}, entityMentions:{mentions}, "
            "source:\"gamma_object_cards_seed\", updatedAt:new Date()}, "
            "$setOnInsert:{createdAt:new Date(), publishedAt:new Date()}}, "
            "{upsert:true});"
        )
        lines.append("applied.postMentions += 1;")

    lines.append("print(JSON.stringify(applied));")
    return "\n".join(lines)


def run_mongosh(container: str, db: str, script: str) -> str:
    cmd = ["docker", "exec", "-i", container, "mongosh", "--quiet", "--eval", script, db]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        raise SystemExit(f"mongosh apply failed (exit {proc.returncode})")
    for line in reversed(proc.stdout.splitlines()):
        s = line.strip()
        if s.startswith("{") and s.endswith("}"):
            return s
    return proc.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", default="quwoquan_service-mongodb-1")
    parser.add_argument("--db", default="quwoquan_content")
    parser.add_argument("--fixture", default=str(DEFAULT_FIXTURE))
    parser.add_argument(
        "--viewer-id",
        default="",
        help="覆盖 fixture 的 canonical viewerId（真机验收用真实账号时使用）",
    )
    parser.add_argument(
        "--report",
        default="",
        help="可选：把 apply 汇总 JSON 写到该路径（gamma T3 证据归档）",
    )
    args = parser.parse_args()

    fixture = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    script = build_mongo_script(fixture, viewer_id_override=args.viewer_id)
    summary = run_mongosh(args.container, args.db, script)
    print(summary)
    if args.report.strip():
        report_path = Path(args.report.strip())
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(summary + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
