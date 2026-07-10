#!/usr/bin/env python3
"""幂等地把首页推荐频道多形态 moment 种子应用到 content-service 的 Mongo（gamma-local）。

env-seed-first：唯一真相源是
quwoquan_service/contracts/metadata/_shared/test_fixtures/content_recommendation_moment_channel.gamma_seed.json，
本脚本只读消费该 fixture，向 quwoquan_content.posts 幂等 upsert 一批多形态 moment-identity 内容：

  - 单图 / 多图轮播 / 九宫格 micro（feed 视图 type=moment）
  - 横屏 / 竖屏 video（feed 视图 type=video，横竖屏由 deviceInfo.width/height 表达）

推荐频道（recommend，feed_query={category:micro, identity:moment}）在 content-service 走
identity=moment 的 repository 分页（ListPublished 按 createdAt DESC 扫描 posts，绕过推荐引擎），
命中条件为 contentIdentity=moment + status=published + visibility=public，且不被该 viewer 的
rec:hidden_authors / rec:negative / rec:hidden_types 抑制。本种子用全新非抑制作者（既有真实作者，
不创建账号）+ 全新 post id（t4hrec_moment_*）+ 既有真实 archived-* 媒体 object key（origin 可解析），
createdAt 递减唯一且按运行时 UTC 当前分钟置顶，使推荐频道首刷多形态非空、连续下拉≥2 页曝光不重复。

幂等：每次以 fixture 为准 $set 全字段 upsert，可重复运行得到确定结果。
缓存失效：post 详情走 read-through `cache:post:{id}`，本脚本对每个种子 id 执行 redis DEL（幂等，
不存在亦无害），保证种子即时对 detail 路径生效；推荐频道分页（ListPublished）本身不缓存，新 id 立即可见。

用法（gamma-local）：
  python3 quwoquan_service/services/seed-box/scripts/apply_content_moment_channel_seed.py \
    --container quwoquan_service-mongodb-1 --redis-container quwoquan_service-redis-1 --db quwoquan_content \
    --report .qwq_output/env/gamma/local/gamma-local/app-artifacts/moment-channel-seed-report.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_FIXTURE = (
    ROOT
    / "quwoquan_service"
    / "contracts"
    / "metadata"
    / "_shared"
    / "test_fixtures"
    / "content_recommendation_moment_channel.gamma_seed.json"
)

SOURCE_TASK_ID = "gamma_moment_channel_seed"


def _parse_base(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _default_created_at_base() -> datetime:
    return datetime.now(timezone.utc).replace(second=0, microsecond=0)


def _resolve_media(post: dict, fixture: dict) -> tuple[str, list[str], str, dict]:
    """根据 form 解析 (contentType, mediaUrls, videoUrl, deviceInfo)。"""
    images = fixture["mediaPool"]["images"]
    videos = fixture["mediaPool"]["videos"]
    grid_keys = fixture["gridImageKeys"]
    multi_keys = fixture["multiImageKeys"]
    single_rotation = list(images.keys())
    form = post["form"]
    idx = post["_seedIndex"]

    if form == "moment_single":
        key = single_rotation[idx % len(single_rotation)]
        return "micro", [images[key]], "", {}
    if form == "moment_multi":
        return "micro", [images[k] for k in multi_keys], "", {}
    if form == "moment_grid":
        return "micro", [images[k] for k in grid_keys], "", {}
    if form == "video_portrait":
        return "video", [images["moment_cover"]], videos["sample"], dict(fixture["videoPortraitDimensions"])
    if form == "video_landscape":
        return "video", [images["citywalk_cover"]], videos["sample"], dict(fixture["videoLandscapeDimensions"])
    raise SystemExit(f"unknown form: {form!r} (post {post.get('id')})")


def build_docs(fixture: dict, created_at_base: datetime | None = None) -> list[dict]:
    base = created_at_base or _default_created_at_base()
    step = int(fixture["createdAtStepSeconds"])
    defaults = fixture["postDefaults"]
    authors = fixture["authors"]
    intersection_tags = fixture["intersectionInterestTags"]
    neutral_tags = fixture["neutralTags"]

    docs: list[dict] = []
    for idx, post in enumerate(fixture["posts"]):
        post = dict(post, _seedIndex=idx)
        author_id = post["author"]
        author = authors[author_id]
        content_type, media_urls, video_url, device_info = _resolve_media(post, fixture)
        # idx 越小 createdAt 越新（首刷置顶）。
        created = base - timedelta(seconds=idx * step)
        created_iso = created.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        tags = list(intersection_tags) if post.get("intersection") else list(neutral_tags)
        docs.append(
            {
                "_id": post["id"],
                "postId": post["id"],
                "postRef": post["id"],
                "authorId": author_id,
                "subAccountId": author_id,
                "authorDisplayNameSnapshot": author["displayName"],
                "authorAvatarUrlSnapshot": author["avatarObjectKey"],
                "personaContextVersion": int(defaults["personaContextVersion"]),
                "contentType": content_type,
                "contentIdentity": defaults["contentIdentity"],
                "title": post["title"],
                "body": post["body"],
                "tags": tags,
                "tagRefs": tags,
                "mediaUrls": media_urls,
                "coverUrl": media_urls[0],
                "videoUrl": video_url,
                "locationName": post["locationName"],
                "status": defaults["status"],
                "visibility": defaults["visibility"],
                "moderationStatus": defaults["moderationStatus"],
                "assistantUsePolicy": defaults["assistantUsePolicy"],
                "circleId": "",
                "circleIds": [],
                "likeCount": int(post["likeCount"]),
                "commentCount": int(post["commentCount"]),
                "shareCount": int(post["shareCount"]),
                "viewCount": int(defaults["viewCount"]),
                "deviceInfo": device_info,
                "sourceTaskId": SOURCE_TASK_ID,
                "_createdIso": created_iso,
            }
        )
    return docs


def build_mongo_script(docs: list[dict]) -> str:
    lines = ["var applied={upserted:0,modified:0,matched:0,ids:[]};"]
    for doc in docs:
        created_iso = doc.pop("_createdIso")
        doc_json = json.dumps(doc, ensure_ascii=False)
        iso_lit = json.dumps(created_iso)
        lines.append(
            "(function(){"
            f"var d={doc_json};"
            f"d.createdAt=new Date({iso_lit});"
            f"d.updatedAt=new Date({iso_lit});"
            f"d.publishedAt=new Date({iso_lit});"
            f"d.lastActiveAt=new Date({iso_lit});"
            "var r=db.posts.updateOne({_id:d._id},{$set:d},{upsert:true});"
            "applied.upserted+=r.upsertedCount;applied.modified+=r.modifiedCount;"
            "applied.matched+=r.matchedCount;applied.ids.push(d._id);"
            "})();"
        )
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


def invalidate_post_cache(redis_container: str, ids: list[str]) -> int:
    if not ids:
        return 0
    keys = [f"cache:post:{pid}" for pid in ids]
    cmd = ["docker", "exec", "-i", redis_container, "redis-cli", "DEL", *keys]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        raise SystemExit(f"redis DEL failed (exit {proc.returncode})")
    out = proc.stdout.strip().splitlines()
    try:
        return int(out[-1]) if out else 0
    except ValueError:
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", default=str(DEFAULT_FIXTURE), help="seed fixture path")
    parser.add_argument("--container", default="quwoquan_service-mongodb-1", help="mongo container name")
    parser.add_argument("--redis-container", default="quwoquan_service-redis-1", help="redis container name")
    parser.add_argument("--db", default="quwoquan_content", help="content-service mongo database")
    parser.add_argument("--skip-cache-invalidation", action="store_true", help="skip redis post-cache DEL")
    parser.add_argument("--report", default="", help="optional machine-readable report path")
    parser.add_argument(
        "--created-at-base",
        default="",
        help="optional UTC base time (YYYY-MM-DDTHH:MM:SSZ); defaults to current UTC minute",
    )
    args = parser.parse_args()

    fixture = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    created_at_base = _parse_base(args.created_at_base) if args.created_at_base else _default_created_at_base()
    docs = build_docs(fixture, created_at_base=created_at_base)
    ids = [d["_id"] for d in docs]
    script = build_mongo_script([dict(d) for d in docs])
    out = run_mongosh(args.container, args.db, script)
    print(f"[seed] applied moment-channel seed -> {out}")

    invalidated = 0
    if not args.skip_cache_invalidation:
        invalidated = invalidate_post_cache(args.redis_container, ids)
        print(f"[seed] invalidated post cache keys -> {invalidated}")

    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(
                {
                    "fixture": args.fixture,
                    "targetStore": fixture.get("targetStore", ""),
                    "createdAtBase": created_at_base.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "seedCount": len(ids),
                    "ids": ids,
                    "applied": json.loads(out) if out.startswith("{") else out,
                    "postCacheInvalidated": invalidated,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
