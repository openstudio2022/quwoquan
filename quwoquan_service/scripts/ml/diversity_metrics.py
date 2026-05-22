#!/usr/bin/env python3
"""Helpers for ranking diversity metrics."""

from __future__ import annotations

import math
from collections import Counter, defaultdict


def _primary_topic(tags: list[str]) -> str:
    for tag in tags:
        if tag.startswith("Topic/") and not tag.startswith("Topic/地理/行政区/"):
            return tag
    return ""


def _geo_bucket(tags: list[str]) -> str:
    for tag in tags:
        if tag.startswith("Topic/地理/行政区/"):
            parts = tag.split("/")
            if len(parts) >= 5:
                return parts[4]
    return ""


def _geo_bucket_from_ref(geo_ref: str) -> str:
    if not geo_ref.startswith("Topic/地理/行政区/"):
        return ""
    parts = geo_ref.split("/")
    if len(parts) >= 5:
        return parts[4]
    return ""


def _normalized_entropy(counter: Counter[str]) -> float:
    total = sum(counter.values())
    if total <= 0 or len(counter) <= 1:
        return 0.0
    entropy = -sum((count / total) * math.log(count / total) for count in counter.values() if count > 0)
    return entropy / math.log(len(counter))


def compute_diversity_metrics(rows: list[dict], scores: list[float], top_k: int = 20) -> dict[str, float]:
    """Compute simple slate-level diversity metrics from scored samples.

    The input rows are grouped by userId, the top-k items per user are selected
    by score, and then we aggregate coverage / repeat / entropy signals.
    """

    scored_by_user: dict[str, list[tuple[float, dict]]] = defaultdict(list)
    for row, score in zip(rows, scores):
        user_id = str(row.get("userId", "") or "")
        scored_by_user[user_id].append((float(score), row))

    total_topk = 0
    unique_item_ids: set[str] = set()
    unique_authors: set[str] = set()
    unique_topics: set[str] = set()
    unique_geo_buckets: set[str] = set()
    topic_entropies: list[float] = []
    author_hhis: list[float] = []
    author_repeat_rates: list[float] = []
    geo_coverage_rates: list[float] = []

    for scored_rows in scored_by_user.values():
        top_rows = sorted(scored_rows, key=lambda x: x[0], reverse=True)[:top_k]
        if not top_rows:
            continue

        total_topk += len(top_rows)
        author_counts: Counter[str] = Counter()
        topic_counts: Counter[str] = Counter()
        geo_counts: Counter[str] = Counter()

        for _, row in top_rows:
            item = row.get("itemFeatures") or {}
            target_id = str(row.get("targetId", "") or "")
            author_id = str(item.get("authorId", "") or "")
            tags = item.get("tags") or []
            topic = _primary_topic(tags)
            geo_bucket = _geo_bucket_from_ref(str(item.get("geoTagRef", "") or "")) or _geo_bucket(tags)

            if target_id:
                unique_item_ids.add(target_id)
            if author_id:
                unique_authors.add(author_id)
                author_counts[author_id] += 1
            if topic:
                unique_topics.add(topic)
                topic_counts[topic] += 1
            if geo_bucket:
                unique_geo_buckets.add(geo_bucket)
                geo_counts[geo_bucket] += 1

        if topic_counts:
            topic_entropies.append(_normalized_entropy(topic_counts))
        if author_counts:
            total_authors = sum(author_counts.values())
            if total_authors > 0:
                author_hhis.append(sum((count / total_authors) ** 2 for count in author_counts.values()))
                author_repeat_rates.append(1.0 - (len(author_counts) / total_authors))
        if geo_counts and top_rows:
            geo_coverage_rates.append(len(geo_counts) / len(top_rows))

    def _mean(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    return {
        f"item_coverage_at_{top_k}": round(len(unique_item_ids) / total_topk, 4) if total_topk else 0.0,
        f"author_repeat_rate_at_{top_k}": round(_mean(author_repeat_rates), 4),
        f"topic_entropy_at_{top_k}": round(_mean(topic_entropies), 4),
        f"author_hhi_at_{top_k}": round(_mean(author_hhis), 4),
        f"geo_coverage_at_{top_k}": round(_mean(geo_coverage_rates), 4),
        f"distinct_authors_at_{top_k}": float(len(unique_authors)),
        f"distinct_topics_at_{top_k}": float(len(unique_topics)),
        f"distinct_geo_buckets_at_{top_k}": float(len(unique_geo_buckets)),
    }
