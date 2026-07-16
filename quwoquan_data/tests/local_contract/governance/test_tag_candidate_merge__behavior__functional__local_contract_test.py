from __future__ import annotations

import json
import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from governance.creators.candidates.store import CandidateRepository, candidate_id_for  # noqa: E402
from governance.taxonomy.candidate_merge import run_merge  # noqa: E402
from governance.taxonomy.candidate_merge import merge_tag  # noqa: E402


def _write_ndjson(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_tag_candidate_never_merges_before_human_approval(tmp_path: Path) -> None:
    candidates = tmp_path / "tag_runtime" / "candidates.ndjson"
    tags_root = tmp_path / "publish" / "tags"
    governance_root = tmp_path / "runtime" / "governance"
    merge_log = tmp_path / "tag_runtime" / "merge_log.ndjson"
    _write_ndjson(
        candidates,
        [
            {
                "label": "雪山摄影",
                "frequency": 8,
                "reason": "content_keyword",
                "suggestedGroup": "Topic",
                "source": "posts/a/article.md",
            }
        ],
    )

    waiting = run_merge(
        candidates_file=candidates,
        tags_root=tags_root,
        governance_root=governance_root,
        merge_log=merge_log,
    )
    assert waiting["pending"] == 1
    assert waiting["merged"] == 0
    assert not (tags_root / "Topic" / "主题" / "雪山摄影" / "_definition.json").exists()

    candidate_id = candidate_id_for("tag", "Topic/主题/雪山摄影")
    candidate = CandidateRepository(governance_root).get(candidate_id)
    assert candidate is not None
    assert candidate["status"] == "pending_review"

    reviews = tmp_path / "reviews.json"
    reviews.write_text(
        json.dumps(
            [
                {
                    "candidateId": candidate_id,
                    "decisionId": "tag-review-1",
                    "decision": "approve",
                    "reviewer": "taxonomy-ops",
                    "actorType": "human",
                    "reason": "语义边界清晰",
                    "reviewedAt": "2026-06-13T00:00:00+00:00",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    approved = run_merge(
        candidates_file=candidates,
        reviews_file=reviews,
        tags_root=tags_root,
        governance_root=governance_root,
        merge_log=merge_log,
    )
    assert approved["pending"] == 0
    assert approved["merged"] == 1
    definition = json.loads(
        (tags_root / "Topic" / "主题" / "雪山摄影" / "_definition.json").read_text(encoding="utf-8")
    )
    assert definition["sourceRefs"] == [f"governance:{candidate_id}"]


def test_rejected_tag_candidate_is_not_merged(tmp_path: Path) -> None:
    candidates = tmp_path / "candidates.ndjson"
    tags_root = tmp_path / "tags"
    governance_root = tmp_path / "governance"
    _write_ndjson(
        candidates,
        [{"tagRef": "Topic/旅行/模糊词", "source": "manifest.json", "reason": "dead_ref"}],
    )
    run_merge(
        candidates_file=candidates,
        tags_root=tags_root,
        governance_root=governance_root,
        merge_log=tmp_path / "merge.ndjson",
    )
    candidate_id = candidate_id_for("tag", "Topic/旅行/模糊词")
    reviews = tmp_path / "reviews.ndjson"
    _write_ndjson(
        reviews,
        [
            {
                "candidateId": candidate_id,
                "decisionId": "reject-tag-1",
                "decision": "reject",
                "reviewer": "taxonomy-ops",
            }
        ],
    )
    result = run_merge(
        candidates_file=candidates,
        reviews_file=reviews,
        tags_root=tags_root,
        governance_root=governance_root,
        merge_log=tmp_path / "merge.ndjson",
    )
    assert result["merged"] == 0
    assert result["pending"] == 0
    assert not (tags_root / "Topic" / "旅行" / "模糊词" / "_definition.json").exists()


def test_tag_merge_rejects_path_traversal_even_after_approval(tmp_path: Path) -> None:
    try:
        merge_tag(
            "../../outside",
            "outside",
            "outside",
            "invalid",
            candidate_id=candidate_id_for("tag", "../../outside"),
            tags_root=tmp_path / "tags",
        )
    except ValueError as exc:
        assert "invalid tag ref" in str(exc)
    else:
        raise AssertionError("tag ref path traversal must be rejected")
