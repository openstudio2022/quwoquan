"""Governed strong-topic classification for acquired Article source units."""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

from core.schema import assert_valid


PHOTOGRAPHY_CATEGORY = "photography"
PHOTOGRAPHY_TOPIC_TAG = "Topic/旅行/玩法/摄影旅拍"
PHOTOGRAPHY_WRITING_INTENT = "planning_consultation"
CLASSIFIER_VERSION = "article-source-topic-v1"

_TITLE_SIGNALS = (
    "摄影",
    "旅拍",
    "机位",
    "拍摄攻略",
    "拍照攻略",
    "取景攻略",
)
_BODY_SIGNALS = (
    "机位",
    "构图",
    "焦段",
    "光线",
    "逆光",
    "蓝调时刻",
    "黄金时刻",
    "长曝光",
    "拍摄参数",
    "快门",
    "光圈",
    "三脚架",
    "取景",
    "摄影路线",
    "旅拍",
)


class ArticleSourceClassificationRejected(ValueError):
    """The fetched page cannot prove the requested governed Article category."""


def _digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def photography_classification(
    *,
    entity_ref: str,
    entity_name: str,
    title: str,
    body: str,
    discovery_query: str,
) -> dict[str, Any]:
    """Freeze a deterministic strong photography classification.

    A generic guide that happens to say ``拍照`` is deliberately rejected.
    The page must retain the exact entity identity at the caller and prove a
    photography editorial intent in its title or through multiple independent
    body concepts.
    """

    compact_title = re.sub(r"\s+", "", title)
    compact_body = re.sub(r"\s+", "", body)
    title_signals = [term for term in _TITLE_SIGNALS if term in compact_title]
    body_signals = [term for term in _BODY_SIGNALS if term in compact_body]
    if not title_signals and len(body_signals) < 3:
        raise ArticleSourceClassificationRejected(
            "photography source requires a strong title signal or at least "
            "three distinct photography body concepts"
        )
    if title_signals and not body_signals:
        raise ArticleSourceClassificationRejected(
            "photography title is not supported by photography body evidence"
        )
    stable = {
        "schema": "quwoquan_data.article_source_classification",
        "classifierVersion": CLASSIFIER_VERSION,
        "articleCategory": PHOTOGRAPHY_CATEGORY,
        "writingIntent": PHOTOGRAPHY_WRITING_INTENT,
        "topicTagRefs": [PHOTOGRAPHY_TOPIC_TAG],
        "requestedTopic": "摄影",
        "entityRef": entity_ref,
        "entityName": entity_name,
        "entityMatched": True,
        "photographyIntentMatched": True,
        "discoveryQuery": discovery_query,
        "sourceTitle": title,
        "matchedTitleSignals": title_signals,
        "matchedBodySignals": body_signals,
        "bodyContentSha256": "sha256:"
        + hashlib.sha256(body.encode("utf-8")).hexdigest(),
    }
    document = {**stable, "classificationDigest": _digest(stable)}
    assert_valid(
        document,
        "source",
        "article_source_classification",
        label=f"article source classification:{entity_ref}",
    )
    return document


__all__ = [
    "ArticleSourceClassificationRejected",
    "PHOTOGRAPHY_CATEGORY",
    "PHOTOGRAPHY_TOPIC_TAG",
    "PHOTOGRAPHY_WRITING_INTENT",
    "photography_classification",
]
