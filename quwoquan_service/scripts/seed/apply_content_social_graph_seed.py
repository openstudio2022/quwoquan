#!/usr/bin/env python3
"""幂等地把内容推荐社交图读模型种子应用到 content-service 的 Mongo（gamma-local）。

env-seed-first：唯一真相源是
quwoquan_service/contracts/metadata/_shared/test_fixtures/content_recommendation_social_graph.gamma_seed.json，
本脚本只读消费该 fixture，向 quwoquan_content 库幂等 upsert：

  - follow_edges          : { followerId, followeeId }          —— viewer 关注边
  - rm_recommend_feature  : userFeatures.tagInteraction.<tag>    —— 关注对象兴趣特征（按 tag dotted-path 合并，不清空既有）

并失效 viewer 的 rm_viewer_object_intersection 预物化快照（删除该 _id 文档），
使下一次 feed/summary 读穿透回算交集（ReadModelIntersectionSource.FactReasons 缺快照即重算）。

这些 follow_edges / rm_recommend_feature 在真实部署由 user-service 关注事件投影产出；
gamma-local 未接线该跨服务投影，故此 fixture 充当其最小正规替身（可重跑、可审计、不硬编码业务列表到 UI/服务）。

用法（gamma-local）：
  python3 quwoquan_service/scripts/seed/apply_content_social_graph_seed.py \
    --container quwoquan_service-mongodb-1 --db quwoquan_content
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FIXTURE = (
    ROOT
    / "quwoquan_service"
    / "contracts"
    / "metadata"
    / "_shared"
    / "test_fixtures"
    / "content_recommendation_social_graph.gamma_seed.json"
)


def build_mongo_script(fixture: dict) -> str:
    """把 fixture 编译成幂等 mongosh JS（值经 json.dumps 安全转义）。"""
    lines: list[str] = ["var applied={followEdges:0,featureTags:0,invalidated:0};"]
    invalidate = bool(fixture.get("invalidateViewerIntersectionCache", False))
    for viewer in fixture.get("viewers", []):
        viewer_id = viewer["viewerId"]
        vid = json.dumps(viewer_id, ensure_ascii=False)
        for follow in viewer.get("follows", []):
            followee = follow["followeeId"]
            fid = json.dumps(followee, ensure_ascii=False)
            lines.append(
                "applied.followEdges += db.follow_edges.updateOne("
                f"{{followerId:{vid}, followeeId:{fid}}}, "
                f"{{$set:{{followerId:{vid}, followeeId:{fid}, source:\"gamma_social_graph_seed\", updatedAt:new Date()}}}}, "
                "{upsert:true}).upsertedCount;"
            )
            for tag, weight in (follow.get("interestTags") or {}).items():
                field = json.dumps("userFeatures.tagInteraction." + tag, ensure_ascii=False)
                wlit = int(weight)
                lines.append(
                    "db.rm_recommend_feature.updateOne("
                    f"{{userId:{fid}}}, "
                    f"{{$set:{{userId:{fid}, {field}:{wlit}}}}}, "
                    "{upsert:true});"
                )
                lines.append("applied.featureTags += 1;")
        if invalidate:
            lines.append(
                "applied.invalidated += db.rm_viewer_object_intersection.deleteOne("
                f"{{_id:{vid}}}).deletedCount;"
            )
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
    args = parser.parse_args()

    fixture = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    script = build_mongo_script(fixture)
    out = run_mongosh(args.container, args.db, script)
    print(f"[seed] applied content social-graph seed -> {out}")

    if args.report:
        Path(args.report).write_text(
            json.dumps(
                {
                    "fixture": args.fixture,
                    "targetStore": fixture.get("targetStore", ""),
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
