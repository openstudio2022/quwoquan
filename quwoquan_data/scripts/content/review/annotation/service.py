"""Typed human-review decisions for an execution review ledger."""
from __future__ import annotations

from dataclasses import dataclass, replace

from core.control_types import (
    ReviewItemKind,
    ReviewJudgment,
    ReviewOverride,
    ReviewPublishState,
)
from content.review.ledger import (
    iter_ledgers,
    load_ledger,
    needs_human,
    reprocess_exhausted,
    resolve_publish_state,
    save_ledger,
)
from content.review.policy import review_policy

KINDS = tuple(ReviewItemKind)
JUDGMENTS = (ReviewJudgment.CREDIBLE, ReviewJudgment.DOUBTFUL)
OVERRIDES = tuple(ReviewOverride)


@dataclass(frozen=True)
class AnnotationDecision:
    execution_id: str
    ref: str
    kind: ReviewItemKind
    target: str
    judgment: ReviewJudgment | None = None
    score: int | None = None
    override: ReviewOverride | None = None
    reprocess: bool = False
    note: str | None = None


def print_pending_queue(execution_id: str, refs: list[str] | None = None) -> int:
    ledgers = iter_ledgers(execution_id)
    ref_filter = set(refs or [])
    pending = 0
    for ledger in ledgers:
        if ref_filter and ledger.ref not in ref_filter:
            continue
        rows = []
        for item in ledger.all_items():
            state = resolve_publish_state(item)
            if needs_human(item) or state is not ReviewPublishState.PUBLISHABLE:
                exhausted = reprocess_exhausted(item)
                rows.append(
                    f"    [{item.kind.value}] {item.target} :: state={state.value} "
                    f"agent={item.agent_judgment.value}/{item.agent_score} "
                    f"human={item.human_judgment.value}/{item.human_score} "
                    f"reprocess={item.reprocess_count}{' EXHAUSTED' if exhausted else ''}"
                    + (f" reasons={item.reasons}" if item.reasons else "")
                )
        if rows:
            pending += len(rows)
            print(f"[annotate] {ledger.ref}:")
            for r in rows:
                print(r)
    if pending == 0:
        print("[annotate] queue empty — 无待人工处理项。")
    else:
        print(f"[annotate] {pending} item(s) awaiting human decision.")
    return pending


def apply_annotation(decision: AnnotationDecision) -> str:
    if decision.kind not in KINDS:
        raise ValueError(f"unsupported annotation kind: {decision.kind!r}")
    if decision.judgment is not None and decision.judgment not in JUDGMENTS:
        raise ValueError(f"unsupported annotation judgment: {decision.judgment!r}")
    if decision.override is not None and decision.override not in OVERRIDES:
        raise ValueError(f"unsupported annotation override: {decision.override!r}")
    if decision.score is not None:
        review_policy().validate_score(decision.score, label="annotation score")

    ledger = load_ledger(decision.execution_id, decision.ref)
    if ledger is None:
        raise KeyError(f"review ledger not found for ref={decision.ref!r}")

    item = ledger.find_item(decision.kind, decision.target)
    if item is None:
        raise KeyError(f"review item not found: kind={decision.kind!r} target={decision.target!r}")

    replacement = item
    if decision.judgment:
        replacement = replace(replacement, human_judgment=decision.judgment)
    if decision.score is not None:
        replacement = replace(replacement, human_score=decision.score)
    if decision.override:
        replacement = replace(replacement, human_override=decision.override)
    if decision.reprocess:
        replacement = replace(
            replacement,
            reprocess_count=replacement.reprocess_count + 1,
        )
    if decision.note:
        replacement = replace(replacement, notes=decision.note)

    if replacement == item:
        raise ValueError("annotation decision has no change")

    save_ledger(ledger.replace_item(replacement))
    return resolve_publish_state(replacement).value


__all__ = ["AnnotationDecision", "apply_annotation", "print_pending_queue"]
