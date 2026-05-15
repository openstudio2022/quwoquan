"""Materialize approved compose results into post packages."""
from __future__ import annotations

from pathlib import Path

from _common.paths import batch_command_root
from _common.io import read_json, write_json


def materialize_posts(task_id: str, batch_id: str, content_type: str) -> list[Path]:
    """Convert approved compose+review results into final post packages."""
    produce_root = batch_command_root(task_id, batch_id, "produce")
    review_dir = produce_root / "results" / "review"
    compose_dir = produce_root / "results" / "compose"
    posts_dir = produce_root / "posts" / content_type

    materialized = []

    if not review_dir.exists():
        return materialized

    for review_file in sorted(review_dir.glob("*.json")):
        review = read_json(review_file)
        payload = review.get("payload", review)
        if payload.get("decision") != "approved":
            continue

        ref = review.get("ref", review_file.stem)
        compose_file = compose_dir / f"{ref}.json"
        if not compose_file.exists():
            continue

        compose = read_json(compose_file)
        compose_payload = compose.get("payload", compose)

        post_dir = posts_dir / ref
        post_dir.mkdir(parents=True, exist_ok=True)

        article_md = compose_payload.get("articleMarkdown", "")
        (post_dir / "article.md").write_text(article_md, encoding="utf-8")

        manifest = {
            "schemaVersion": "quwoquan_data.post_manifest",
            "topicId": ref,
            "contentType": content_type,
            "entityRefs": compose_payload.get("entityRefs", []),
            "tagRefs": compose_payload.get("tagRefs", []),
            "sourceUrls": compose_payload.get("sourceUrls", []),
            "reviewDecision": "approved",
        }
        write_json(post_dir / "manifest.json", manifest)
        materialized.append(post_dir)

    return materialized
