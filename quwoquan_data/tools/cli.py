from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import batch
import tree_ops
import workflow_ops


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qwq-data")
    subparsers = parser.add_subparsers(dest="command", required=True)

    tree_parser = subparsers.add_parser("tree")
    tree_sub = tree_parser.add_subparsers(dest="tree_command", required=True)
    tree_validate = tree_sub.add_parser("validate")
    tree_validate.add_argument("--tree", choices=["entities", "content", "tags", "all"], default="all")
    tree_validate.set_defaults(handler=tree_ops.handle_validate)

    crawl_parser = subparsers.add_parser("crawl")
    crawl_sub = crawl_parser.add_subparsers(dest="crawl_command", required=True)

    crawl_spec_discovery = crawl_sub.add_parser("spec-discovery")
    crawl_spec_discovery.add_argument("--spec", required=True)
    crawl_spec_discovery.add_argument(
        "--skip-hydrate",
        action="store_true",
        help="不逐条抓取 HTML，仅刷新 discovery/topic_tasks（大 spec 时建议）",
    )
    crawl_spec_discovery.set_defaults(handler=batch.handle_spec_discovery)

    crawl_status = crawl_sub.add_parser("status")
    crawl_status.add_argument("--spec", required=True)
    crawl_status.add_argument("--skip-hydrate", action="store_true")
    crawl_status.set_defaults(handler=batch.handle_status)

    crawl_fetch_source = crawl_sub.add_parser("fetch-source")
    crawl_fetch_source.add_argument("--spec", required=True)
    crawl_fetch_source.add_argument("--topic", required=True)
    crawl_fetch_source.add_argument("--task-type", required=True, choices=["article", "image"])
    crawl_fetch_source.add_argument("--source-id", required=True)
    crawl_fetch_source.add_argument("--url", required=True)
    crawl_fetch_source.add_argument("--title", default="")
    crawl_fetch_source.add_argument("--query", default="")
    crawl_fetch_source.add_argument("--snippet", default="")
    crawl_fetch_source.add_argument("--source-role", default="publish_candidate")
    crawl_fetch_source.add_argument("--rights-status", default="clear")
    crawl_fetch_source.add_argument("--watermark-status", default="clean")
    crawl_fetch_source.set_defaults(handler=batch.handle_fetch_source)

    crawl_compose_topic = crawl_sub.add_parser("compose-topic")
    crawl_compose_topic.add_argument("--spec", required=True)
    crawl_compose_topic.add_argument("--topic", required=True)
    crawl_compose_topic.add_argument("--targets", default="")
    crawl_compose_topic.add_argument("--dry-run", action="store_true")
    crawl_compose_topic.set_defaults(handler=batch.handle_compose_topic)

    crawl_audit_topic = crawl_sub.add_parser("audit-topic")
    crawl_audit_topic.add_argument("--spec", required=True)
    crawl_audit_topic.add_argument("--topic", required=True)
    crawl_audit_topic.set_defaults(handler=batch.handle_audit_topic)

    crawl_run_topic = crawl_sub.add_parser("run-topic")
    crawl_run_topic.add_argument("--spec", required=True)
    crawl_run_topic.add_argument("--topic", required=True)
    crawl_run_topic.add_argument("--targets", default="")
    crawl_run_topic.add_argument("--dry-run", action="store_true")
    crawl_run_topic.set_defaults(handler=batch.handle_run_topic)

    crawl_pool_bootstrap = crawl_sub.add_parser("pool-bootstrap")
    crawl_pool_bootstrap.add_argument("--spec", required=True)
    crawl_pool_bootstrap.add_argument(
        "--catalog",
        default="",
        help="景点 YAML 或 NDJSON；省略则使用 spec.article_topic_catalog_ref",
    )
    crawl_pool_bootstrap.add_argument("--merge", action="store_true", help="按 sourceUrl 去重追加，不整文件覆盖")
    crawl_pool_bootstrap.add_argument("--topics", default="", help="逗号分隔 topic_id")
    crawl_pool_bootstrap.add_argument("--travel-seed", default="", help="按 topic 分组的旅游 URL NDJSON")
    crawl_pool_bootstrap.add_argument("--max-sources", type=int, default=22)
    crawl_pool_bootstrap.add_argument(
        "--wiki-expand",
        default="filtered",
        choices=["none", "filtered", "full"],
        help="维基外链：默认 filtered（与景点词相关）；full 为旧行为（不推荐）",
    )
    crawl_pool_bootstrap.add_argument("--wiki-link-budget", type=int, default=40)
    crawl_pool_bootstrap.add_argument("--baike-link-budget", type=int, default=24)
    crawl_pool_bootstrap.add_argument("--wikivoyage-limit", type=int, default=12)
    crawl_pool_bootstrap.add_argument("--sleep", type=float, default=0.35)
    crawl_pool_bootstrap.add_argument("--skip-baike-scrape", action="store_true")
    crawl_pool_bootstrap.set_defaults(handler=batch.handle_pool_bootstrap)

    crawl_export_poi = crawl_sub.add_parser("export-poi-topics")
    crawl_export_poi.add_argument("--input", required=True, help="Overpass JSON（含 elements）")
    crawl_export_poi.add_argument("--output", required=True, help="输出 NDJSON，供 article_topic_catalog_ref 引用")
    crawl_export_poi.add_argument("--topic-id-prefix", default="poi", help="生成 topic_id 前缀")
    crawl_export_poi.set_defaults(handler=batch.handle_export_poi_topics)

    crawl_instruction_build = crawl_sub.add_parser("instruction-build")
    crawl_instruction_build.add_argument("--spec", default="")
    crawl_instruction_build.add_argument("--spec-id", default="")
    crawl_instruction_build.add_argument("--instruction", default="")
    crawl_instruction_build.add_argument("--intent", default="discover_and_publish")
    crawl_instruction_build.add_argument("--verticals", default="travel")
    crawl_instruction_build.add_argument("--tag-refs", default="")
    crawl_instruction_build.add_argument("--platform-priority", default="")
    crawl_instruction_build.add_argument("--coverage", default="wide")
    crawl_instruction_build.add_argument("--content-modes", default="article,image")
    crawl_instruction_build.add_argument("--style", default="balanced")
    crawl_instruction_build.add_argument("--chapter-preference", default="grounded")
    crawl_instruction_build.add_argument("--regions", default="")
    crawl_instruction_build.set_defaults(handler=workflow_ops.handle_instruction_build)

    crawl_tag_catalog_build = crawl_sub.add_parser("tag-catalog-build")
    crawl_tag_catalog_build.set_defaults(handler=workflow_ops.handle_tag_catalog_build)

    crawl_entity_catalog_build = crawl_sub.add_parser("entity-catalog-build")
    crawl_entity_catalog_build.add_argument("--catalog", default="", help="附加 YAML/NDJSON catalog，合并到 entity catalog")
    crawl_entity_catalog_build.set_defaults(handler=workflow_ops.handle_entity_catalog_build)

    crawl_entities_by_tag = crawl_sub.add_parser("entities-by-tag")
    crawl_entities_by_tag.add_argument("--spec", default="")
    crawl_entities_by_tag.add_argument("--spec-id", default="")
    crawl_entities_by_tag.add_argument("--tag-refs", default="")
    crawl_entities_by_tag.add_argument("--tag-labels", default="")
    crawl_entities_by_tag.add_argument("--tag-ids", default="")
    crawl_entities_by_tag.set_defaults(handler=workflow_ops.handle_entities_by_tag)

    crawl_spec_build = crawl_sub.add_parser("spec-build")
    crawl_spec_build.add_argument("--spec", default="")
    crawl_spec_build.add_argument("--spec-id", default="")
    crawl_spec_build.add_argument("--output", default="")
    crawl_spec_build.set_defaults(handler=workflow_ops.handle_spec_build)

    crawl_authority_sync = crawl_sub.add_parser("authority-sync")
    crawl_authority_sync.add_argument("--spec", default="")
    crawl_authority_sync.add_argument("--spec-id", default="")
    crawl_authority_sync.set_defaults(handler=workflow_ops.handle_authority_sync)

    crawl_authority_review = crawl_sub.add_parser("authority-review")
    crawl_authority_review.add_argument("--spec", default="")
    crawl_authority_review.add_argument("--spec-id", default="")
    crawl_authority_review.set_defaults(handler=workflow_ops.handle_authority_review)

    crawl_content_discover = crawl_sub.add_parser("content-discover")
    crawl_content_discover.add_argument("--spec", default="")
    crawl_content_discover.add_argument("--spec-id", default="")
    crawl_content_discover.add_argument("--seed", default="", help="按 entityId/topicId 分组的内容 URL NDJSON")
    crawl_content_discover.set_defaults(handler=workflow_ops.handle_content_discover)

    crawl_content_hydrate = crawl_sub.add_parser("content-hydrate")
    crawl_content_hydrate.add_argument("--spec", default="")
    crawl_content_hydrate.add_argument("--spec-id", default="")
    crawl_content_hydrate.set_defaults(handler=workflow_ops.handle_content_hydrate)

    crawl_content_review = crawl_sub.add_parser("content-review")
    crawl_content_review.add_argument("--spec", default="")
    crawl_content_review.add_argument("--spec-id", default="")
    crawl_content_review.set_defaults(handler=workflow_ops.handle_content_review)

    crawl_compose_post = crawl_sub.add_parser("compose-post")
    crawl_compose_post.add_argument("--spec", required=True)
    crawl_compose_post.add_argument("--topic", default="")
    crawl_compose_post.add_argument("--topics", default="")
    crawl_compose_post.add_argument("--targets", default="")
    crawl_compose_post.set_defaults(handler=workflow_ops.handle_compose_post)

    crawl_review_generated = crawl_sub.add_parser("review-generated")
    crawl_review_generated.add_argument("--spec", required=True)
    crawl_review_generated.add_argument("--topic", default="")
    crawl_review_generated.add_argument("--topics", default="")
    crawl_review_generated.set_defaults(handler=workflow_ops.handle_review_generated)

    crawl_publish_approved = crawl_sub.add_parser("publish-approved")
    crawl_publish_approved.add_argument("--spec", required=True)
    crawl_publish_approved.add_argument("--topic", default="")
    crawl_publish_approved.add_argument("--topics", default="")
    crawl_publish_approved.set_defaults(handler=workflow_ops.handle_publish_approved)

    crawl_feedback_extract = crawl_sub.add_parser("feedback-extract")
    crawl_feedback_extract.add_argument("--spec", required=True)
    crawl_feedback_extract.add_argument("--topic", default="")
    crawl_feedback_extract.add_argument("--topics", default="")
    crawl_feedback_extract.set_defaults(handler=workflow_ops.handle_feedback_extract)

    crawl_feedback_verify = crawl_sub.add_parser("feedback-verify")
    crawl_feedback_verify.add_argument("--spec", required=True)
    crawl_feedback_verify.set_defaults(handler=workflow_ops.handle_feedback_verify)

    crawl_graph_verify = crawl_sub.add_parser("graph-verify")
    crawl_graph_verify.set_defaults(handler=workflow_ops.handle_graph_verify)

    crawl_auto_run = crawl_sub.add_parser("auto-run")
    crawl_auto_run.add_argument("--spec", required=True)
    crawl_auto_run.add_argument("--instruction", default="")
    crawl_auto_run.add_argument("--intent", default="discover_and_publish")
    crawl_auto_run.add_argument("--verticals", default="travel")
    crawl_auto_run.add_argument("--platform-priority", default="")
    crawl_auto_run.add_argument("--coverage", default="wide")
    crawl_auto_run.add_argument("--content-modes", default="article,image")
    crawl_auto_run.add_argument("--style", default="balanced")
    crawl_auto_run.add_argument("--chapter-preference", default="grounded")
    crawl_auto_run.add_argument("--regions", default="")
    crawl_auto_run.add_argument("--seed", default="")
    crawl_auto_run.add_argument("--topics", default="")
    crawl_auto_run.add_argument("--targets", default="")
    crawl_auto_run.add_argument("--skip-hydrate", action="store_true")
    crawl_auto_run.add_argument("--entity-catalog", default="")
    crawl_auto_run.set_defaults(handler=workflow_ops.handle_auto_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
