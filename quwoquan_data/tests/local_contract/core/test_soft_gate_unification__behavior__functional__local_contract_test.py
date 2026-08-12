"""P5 字数门自适应 + 软门统一口径契约：消除 review/verify 第二真相源 + 非致命检查降软扣分。

- 软门集合单一真相源 = quality_gates.SOFT_QUALITY_GATES；route_core.SOFT_CHECKS 必须等于它。
- 字数门唯一真相源 = base_draft（长文≥600/图文混排≥200），review 与 verify 同源。
- publish-face verify 的软门（writingIntentConsistency/mechanicalHeading）只进 advisories，
  绝不 hard-block（与 produce review SOFT_CHECKS 同口径）。

可直接运行：python3 quwoquan_data/tests/local_contract/core/test_soft_gate_unification__behavior__functional__local_contract_test.py
"""
from __future__ import annotations

import sys
import tempfile
import json
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import os  # noqa: E402


from core import quality_gates as qg  # noqa: E402
from content.post.article import base_draft  # noqa: E402
from content.post.article import route_core  # noqa: E402
from content.post.article.route_review_fallback import _review_fallback_stage  # noqa: E402
from content.post.article.entity_review import _entity_fallback_stage  # noqa: E402
from content.release.canonical import integrity  # noqa: E402
from verify.verify_content_quality import _semantic_gate_issues  # noqa: E402


def test_soft_gate_single_source_is_unified():
    # 软门集合单一真相源：route_core 必须直接复用 quality_gates，不得另起一套。
    assert set(route_core.SOFT_CHECKS) == set(qg.SOFT_QUALITY_GATES)
    # P5 非致命检查（情感密度/写作主线/机械小标题/机械结尾）必须都在软门集合。
    assert {
        "travelogueDensity",
        "writingIntentConsistency",
        "mechanicalHeading",
        "proseStyle",
    } <= set(qg.SOFT_QUALITY_GATES)


def test_is_soft_quality_gate_classification():
    assert qg.is_soft_quality_gate("writingIntentConsistency") is True
    assert qg.is_soft_quality_gate("mechanicalHeading") is True
    # 硬门（图文闭环/语域/联系方式/去重）不得被误判为软门。
    for hard in ("imageGate", "registerMismatch", "contactInfo", "skeletonSimilarity", "baseDraftFidelity"):
        assert qg.is_soft_quality_gate(hard) is False, hard


def test_commercial_near_copy_is_authoring_diagnostic_but_release_hard_gate():
    """轻编辑不得因来源模式回卷；同一诊断仍由 release integrity fail closed。"""

    checks = {
        "commercialNearCopy": {
            "passed": False,
            "issues": [
                "factual_reference_only article containment 0.916 > 0.550"
            ],
            "suggestions": ["保留来源归因并记录重复度诊断。"],
        }
    }

    blocking, suggestions, diagnostic_failed = route_core.aggregate_checks(checks)

    assert blocking == []
    assert diagnostic_failed == 1
    assert any("commercialNearCopy" in item for item in suggestions)
    assert _review_fallback_stage(checks) == "review"
    assert _entity_fallback_stage(checks) == "review"
    assert qg.is_authoring_diagnostic_gate("commercialNearCopy") is True
    assert qg.is_soft_quality_gate("commercialNearCopy") is False
    assert "commercialNearCopy" in integrity.ARTICLE_HARD_CHECKS

    with tempfile.TemporaryDirectory(prefix="article_release_near_copy_") as raw:
        runtime_post = Path(raw)
        review_dir = runtime_post / "5.review"
        review_dir.mkdir(parents=True)
        (review_dir / "review.json").write_text(
            json.dumps(
                {
                    "decision": "approved",
                    "checks": {
                        "commercialNearCopy": checks["commercialNearCopy"],
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        release_issues = integrity._review_gate_issues("posts/article/x", runtime_post)
    assert any(
        "hard review check failed: commercialNearCopy" in issue
        for issue in release_issues
    )


def test_word_gate_single_source_thresholds():
    # 字数门唯一真相源 = base_draft（长文≥600/图文混排≥200）；review 与 verify 都消费它。
    assert base_draft.ARTICLE_MIN_BASE_DRAFT_CHARS == 600
    assert base_draft.RICH_MIXED_MIN_TEXT_CHARS == 200


def test_verify_soft_gates_go_to_advisories_not_blocking():
    # 写作主线不符 + 机械化小标题：软门，只进 advisories，绝不 hard-block。
    article = (
        "## 行程速览\n\n"
        "那天清晨我们抵达湖边，沿着栈道慢慢走。午后阳光很好，心里很安静。"
        "傍晚回头看了一眼，水色还在变。\n"
    )
    manifest = {
        "carrier": "article",
        "writingIntent": "planning_consultation",  # 与游记式正文不符 → writingIntentConsistency
        "mechanicalHeadingTerms": ["行程速览"],      # → mechanicalHeading
        "assets": [],
    }
    advisories: list[str] = []
    hard = _semantic_gate_issues(Path("posts/x/article.md"), article, manifest, advisories=advisories)

    joined_hard = " ".join(hard)
    assert "writingIntentConsistency" not in joined_hard
    assert "mechanicalHeading" not in joined_hard

    joined_soft = " ".join(advisories)
    assert "[soft:writingIntentConsistency]" in joined_soft
    assert "[soft:mechanicalHeading]" in joined_soft


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"soft gate unification tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
