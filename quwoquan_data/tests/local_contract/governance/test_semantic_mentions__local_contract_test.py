from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from _common.semantic_mentions import (  # noqa: E402
    STATUS_OFFLINE,
    STATUS_PENDING_REVIEW,
    bounded_candidate_walk,
    semantic_mentions_for_target,
)


def test_utf16_offsets_and_stable_ids_ignore_status_and_offset_shift() -> None:
    text = "A😀九寨沟与九寨沟"
    pending = semantic_mentions_for_target(
        text,
        source_ref="post:1",
        target_ref="/entity/地点/景区/九寨沟",
        surface="九寨沟",
        status=STATUS_PENDING_REVIEW,
    )
    assert [(row["startUtf16"], row["endUtf16"]) for row in pending] == [(3, 6), (7, 10)]
    assert pending[0]["mentionId"] != pending[1]["mentionId"]

    shifted = semantic_mentions_for_target(
        "前缀" + text,
        source_ref="post:1",
        target_ref="/entity/地点/景区/九寨沟",
        surface="九寨沟",
        status=STATUS_OFFLINE,
    )
    assert [row["mentionId"] for row in shifted] == [row["mentionId"] for row in pending]
    assert shifted[0]["startUtf16"] == pending[0]["startUtf16"] + 2
    assert all(row["status"] == STATUS_OFFLINE for row in shifted)


def test_semantic_mention_rejects_unknown_status() -> None:
    try:
        semantic_mentions_for_target(
            "九寨沟",
            source_ref="post:1",
            target_ref="/entity/地点/景区/九寨沟",
            surface="九寨沟",
            status="candidate",
        )
    except ValueError as exc:
        assert "unsupported semantic mention status" in str(exc)
    else:
        raise AssertionError("unknown mention status must be rejected")


def test_bounded_walk_uses_visited_and_stops_at_depth_two() -> None:
    graph = {
        "a": ["b", "c"],
        "b": ["a", "d"],
        "c": ["d"],
        "d": ["e"],
        "e": [],
    }
    walked = bounded_candidate_walk(
        ["a"],
        lambda node: graph[node],
        identity=lambda node: node,
    )
    assert walked == [("a", 0), ("b", 1), ("c", 1), ("d", 2)]


def test_bounded_walk_caps_candidates_at_200() -> None:
    walked = bounded_candidate_walk(
        range(250),
        lambda _node: (),
        identity=lambda node: str(node),
    )
    assert len(walked) == 200
    assert walked[-1] == (199, 0)
