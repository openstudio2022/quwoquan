"""Typed human-review decisions for an execution review ledger."""
from __future__ import annotations

from dataclasses import dataclass

from content.review.ledger import (
    JUDGE_CREDIBLE,
    JUDGE_DOUBTFUL,
    KIND_ARTICLE,
    KIND_FACT,
    KIND_IMAGE,
    OVERRIDE_DISCARD,
    OVERRIDE_PUBLISHABLE,
    iter_ledgers,
    load_ledger,
    needs_human,
    reprocess_exhausted,
    resolve_publish_state,
    save_ledger,
)

KINDS = (KIND_IMAGE, KIND_FACT, KIND_ARTICLE)
JUDGMENTS = (JUDGE_CREDIBLE, JUDGE_DOUBTFUL)
OVERRIDES = (OVERRIDE_PUBLISHABLE, OVERRIDE_DISCARD)


@dataclass(frozen=True)
class AnnotationDecision:
    execution_id: str
    ref: str
    kind: str
    target: str
    judgment: str | None = None
    score: int | None = None
    override: str | None = None
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
            state = resolve_publish_state(item, ledger.policy)
            if needs_human(item, ledger.policy) or state != "publishable":
                exhausted = reprocess_exhausted(item, ledger.policy)
                rows.append(
                    f"    [{item.kind}] {item.target} :: state={state} "
                    f"agent={item.agentJudgment}/{item.agentScore} human={item.humanJudgment}/{item.humanScore} "
                    f"reprocess={item.reprocessCount}{' EXHAUSTED' if exhausted else ''}"
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
    if decision.score is not None and decision.score not in {1, 2, 3, 4, 5}:
        raise ValueError(f"annotation score must be 1..5: {decision.score!r}")

    ledger = load_ledger(decision.execution_id, decision.ref)
    if ledger is None:
        raise KeyError(f"review ledger not found for ref={decision.ref!r}")

    item = ledger.find_item(decision.kind, decision.target)
    if item is None:
        raise KeyError(f"review item not found: kind={decision.kind!r} target={decision.target!r}")

    changed = False
    if decision.judgment:
        item.humanJudgment = decision.judgment
        changed = True
    if decision.score is not None:
        item.humanScore = decision.score
        changed = True
    if decision.override:
        item.humanOverride = decision.override
        changed = True
    if decision.reprocess:
        item.reprocessCount += 1
        changed = True
    if decision.note:
        item.notes = decision.note
        changed = True

    if not changed:
        raise ValueError("annotation decision has no change")

    save_ledger(ledger)
    return resolve_publish_state(item, ledger.policy)


__all__ = ["AnnotationDecision", "apply_annotation", "print_pending_queue"]
