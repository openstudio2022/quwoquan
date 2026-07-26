#!/usr/bin/env python3
"""幂等地把内容推荐社交图读模型种子应用到 content-service 的 Mongo（gamma-local）。

env-seed-first：唯一真相源是
quwoquan_service/contracts/metadata/_shared/test_fixtures/content_recommendation_social_graph.gamma_seed.json，
本脚本只读消费该 fixture，向 quwoquan_content 库幂等 upsert：

  - persona_follow_projection: { sourcePersonaId, targetPersonaId, following } —— viewer 关注投影
  - rm_recommend_feature  : userFeatures.tagInteraction.<tag>    —— 关注对象兴趣特征（按 tag dotted-path 合并，不清空既有）
  - rm_entity_tags        : { entityId, tags }                  —— canonical homepage/circle 对象标签
  - rm_behavior_events    : { userId, action, entityRefs }      —— 关注对象到访 canonical object 的事实事件
  - circle_members        : { circleId, userId }                —— canonical circle 共同成员边

并失效 viewer 的 rm_viewer_object_intersection 预物化快照（删除该 _id 文档），
使下一次 feed/summary 读穿透回算交集（ReadModelIntersectionSource.FactReasons 缺快照即重算）。

这些 persona_follow_projection / rm_recommend_feature 在真实部署由 user-service
PersonaRelationship Stream 投影产出；本 fixture 仅用于受控 gamma 验证预置读模型
事实，不替代跨服务事件链或生产数据。

用法（gamma-local）：
  python3 quwoquan_service/services/content-service/cmd/jobs/seed-social-graph/main.py \
    --container quwoquan_service-mongodb-1 --db quwoquan_content
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "quwoquan_service").is_dir() and (parent / "quwoquan_ops").is_dir()
)
DEFAULT_FIXTURE = (
    ROOT
    / "quwoquan_service"
    / "contracts"
    / "metadata"
    / "_shared"
    / "test_fixtures"
    / "content_recommendation_social_graph.gamma_seed.json"
)


def build_mongo_script(fixture: dict, viewer_id_override: str = "") -> str:
    """把 fixture 编译成幂等 mongosh JS（值经 json.dumps 安全转义）。"""
    lines: list[str] = [
        "var applied={relationshipProjection:0,featureTags:0,entityTags:0,objectVisits:0,circleMembers:0,invalidated:0};"
    ]
    invalidate = bool(fixture.get("invalidateViewerIntersectionCache", False))
    canonical_viewer_ids = {
        str(viewer.get("viewerId") or "").strip()
        for viewer in fixture.get("viewers", [])
        if str(viewer.get("viewerId") or "").strip()
    }
    for viewer in fixture.get("viewers", []):
        viewer_id = viewer_id_override.strip() or viewer["viewerId"]
        vid = json.dumps(viewer_id, ensure_ascii=False)
        for relationship in viewer.get("relationships", []):
            target_persona_id = relationship["targetPersonaId"]
            tid = json.dumps(target_persona_id, ensure_ascii=False)
            following = bool(relationship.get("following", False))
            following_literal = "true" if following else "false"
            lines.append(
                "applied.relationshipProjection += db.persona_follow_projection.updateOne("
                f"{{sourcePersonaId:{vid}, targetPersonaId:{tid}}}, "
                f"{{$set:{{sourcePersonaId:{vid}, targetPersonaId:{tid}, following:{following_literal}, source:\"gamma_social_graph_seed\", updatedAt:new Date()}}}}, "
                "{upsert:true}).upsertedCount;"
            )
            for tag, weight in (relationship.get("interestTags") or {}).items():
                field = json.dumps("userFeatures.tagInteraction." + tag, ensure_ascii=False)
                wlit = int(weight)
                lines.append(
                    "db.rm_recommend_feature.updateOne("
                    f"{{userId:{tid}}}, "
                    f"{{$set:{{userId:{tid}, {field}:{wlit}}}}}, "
                    "{upsert:true});"
                )
                lines.append("applied.featureTags += 1;")
        if invalidate:
            lines.append(
                "applied.invalidated += db.rm_viewer_object_intersection.deleteOne("
                f"{{_id:{vid}}}).deletedCount;"
            )
    for entity in fixture.get("entityTags", []):
        entity_id = json.dumps(entity["entityId"], ensure_ascii=False)
        tags = json.dumps(list(entity.get("tags") or []), ensure_ascii=False)
        lines.append(
            "db.rm_entity_tags.updateOne("
            f"{{entityId:{entity_id}}}, "
            f"{{$set:{{entityId:{entity_id}, tags:{tags}, source:\"gamma_social_graph_seed\", updatedAt:new Date()}}}}, "
            "{upsert:true});"
        )
        lines.append("applied.entityTags += 1;")
    for visit in fixture.get("objectVisits", []):
        user_id = json.dumps(visit["userId"], ensure_ascii=False)
        object_id = json.dumps(visit["objectId"], ensure_ascii=False)
        object_type = json.dumps(str(visit.get("objectType") or "").strip(), ensure_ascii=False)
        display_name = json.dumps(str(visit.get("displayName") or "").strip(), ensure_ascii=False)
        lines.append(
            "db.rm_behavior_events.updateOne("
            f"{{userId:{user_id}, action:\"entity_page_view\", entityRefs:{object_id}, source:\"gamma_social_graph_seed\"}}, "
            f"{{$set:{{userId:{user_id}, action:\"entity_page_view\", entityRefs:[{object_id}], objectType:{object_type}, displayName:{display_name}, source:\"gamma_social_graph_seed\", updatedAt:new Date()}}, "
            "$setOnInsert:{createdAt:new Date()}}, "
            "{upsert:true});"
        )
        lines.append("applied.objectVisits += 1;")
    for membership in fixture.get("circleMemberships", []):
        circle_id = json.dumps(membership["circleId"], ensure_ascii=False)
        membership_user_id = str(membership["userId"])
        if viewer_id_override.strip() and membership_user_id in canonical_viewer_ids:
            membership_user_id = viewer_id_override.strip()
        user_id = json.dumps(membership_user_id, ensure_ascii=False)
        lines.append(
            "db.circle_members.updateOne("
            f"{{circleId:{circle_id}, userId:{user_id}}}, "
            f"{{$set:{{circleId:{circle_id}, userId:{user_id}, source:\"gamma_social_graph_seed\", updatedAt:new Date()}}, "
            "$setOnInsert:{joinedAt:new Date()}}, "
            "{upsert:true});"
        )
        lines.append("applied.circleMembers += 1;")
    lines.append("print(JSON.stringify(applied));")
    return "\n".join(lines)


def run_mongosh(container: str, db: str, script: str) -> str:
    # 非交互 --eval 模式：不回显 REPL 提示符，stdout 即脚本 print 输出（末行为汇总 JSON）。
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
    parser.add_argument("--fixture", default=str(DEFAULT_FIXTURE), help="seed fixture path")
    parser.add_argument("--container", default="quwoquan_service-mongodb-1", help="mongo container name")
    parser.add_argument("--db", default="quwoquan_content", help="content-service mongo database")
    parser.add_argument("--report", default="", help="optional machine-readable report path")
    parser.add_argument(
        "--viewer-id",
        default="",
        help="bind the canonical fixture viewer to the authenticated runtime persona",
    )
    args = parser.parse_args()

    fixture = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    script = build_mongo_script(fixture, args.viewer_id)
    out = run_mongosh(args.container, args.db, script)
    print(f"[seed] applied content social-graph seed -> {out}")

    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(
                {
                    "fixture": args.fixture,
                    "targetStore": fixture.get("targetStore", ""),
                    "activeViewerId": args.viewer_id,
                    "applied": json.loads(out) if out.startswith("{") else out,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
