"""Typed review ledger and publication decision rules.

The ledger is runtime evidence only. Its policy never lives in an execution
workspace: all review thresholds are loaded from the repository-owned control
plane policy.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Mapping

from core.control_types import (
    ImageSafetyReviewStatus,
    ReviewItemKind,
    ReviewJudgment,
    ReviewOverride,
    ReviewPublishState,
)
from core.io import read_json, write_json
from core.paths import execution_shared_dir
from content.review.policy import ReviewPolicy, review_policy


REVIEW_LEDGER_SCHEMA = "quwoquan_data.review_ledger"


def _required_string(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"review ledger {label} must be a non-empty string")
    return value.strip()


def _optional_string(value: object, *, label: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"review ledger {label} must be a string")
    return value


def _optional_score(value: object, *, policy: ReviewPolicy, label: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"review ledger {label} must be an integer or null")
    return policy.validate_score(value, label=label)


def _string_tuple(value: object, *, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"review ledger {label} must be an array of strings")
    return tuple(value)


@dataclass(frozen=True, slots=True)
class ReviewVerdict:
    """One immutable agent/human verdict for a publishable review target."""

    kind: ReviewItemKind
    target: str
    agent_judgment: ReviewJudgment
    agent_score: int
    human_judgment: ReviewJudgment = ReviewJudgment.UNJUDGED
    human_score: int | None = None
    human_override: ReviewOverride | None = None
    reprocess_count: int = 0
    reasons: tuple[str, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        policy = review_policy()
        if not isinstance(self.kind, ReviewItemKind):
            raise TypeError("ReviewVerdict.kind must use ReviewItemKind")
        if not isinstance(self.agent_judgment, ReviewJudgment):
            raise TypeError("ReviewVerdict.agent_judgment must use ReviewJudgment")
        if not isinstance(self.human_judgment, ReviewJudgment):
            raise TypeError("ReviewVerdict.human_judgment must use ReviewJudgment")
        if self.human_override is not None and not isinstance(self.human_override, ReviewOverride):
            raise TypeError("ReviewVerdict.human_override must use ReviewOverride")
        _required_string(self.target, label="target")
        policy.validate_score(self.agent_score, label="agent_score")
        if self.human_score is not None:
            policy.validate_score(self.human_score, label="human_score")
        if self.reprocess_count < 0:
            raise ValueError("review ledger reprocess_count must be non-negative")
        if not all(isinstance(reason, str) for reason in self.reasons):
            raise TypeError("ReviewVerdict.reasons must contain strings")

    @classmethod
    def from_document(cls, value: object) -> "ReviewVerdict":
        if not isinstance(value, Mapping):
            raise ValueError("review verdict must be an object")
        policy = review_policy()
        allowed = {
            "kind", "target", "agentJudgment", "agentScore", "humanJudgment",
            "humanScore", "humanOverride", "reprocessCount", "reasons", "notes",
            "publishState",
        }
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise ValueError(f"review verdict has unknown fields: {', '.join(unknown)}")
        try:
            verdict = cls(
                kind=ReviewItemKind(_required_string(value.get("kind"), label="kind")),
                target=_required_string(value.get("target"), label="target"),
                agent_judgment=ReviewJudgment(
                    _required_string(value.get("agentJudgment"), label="agentJudgment")
                ),
                agent_score=policy.validate_score(
                    _optional_score(value.get("agentScore"), policy=policy, label="agentScore")
                    or 0,
                    label="agentScore",
                ),
                human_judgment=ReviewJudgment(
                    _required_string(
                        value.get("humanJudgment", ReviewJudgment.UNJUDGED.value),
                        label="humanJudgment",
                    )
                ),
                human_score=_optional_score(value.get("humanScore"), policy=policy, label="humanScore"),
                human_override=(
                    ReviewOverride(_required_string(value.get("humanOverride"), label="humanOverride"))
                    if value.get("humanOverride") is not None
                    else None
                ),
                reprocess_count=int(value.get("reprocessCount", 0)),
                reasons=_string_tuple(value.get("reasons", []), label="reasons"),
                notes=_optional_string(value.get("notes", ""), label="notes"),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid review verdict: {exc}") from exc
        derived = value.get("publishState")
        if derived is not None and derived != resolve_publish_state(verdict).value:
            raise ValueError("review verdict publishState does not match derived decision")
        return verdict

    def to_document(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "target": self.target,
            "agentJudgment": self.agent_judgment.value,
            "agentScore": self.agent_score,
            "humanJudgment": self.human_judgment.value,
            "humanScore": self.human_score,
            "humanOverride": self.human_override.value if self.human_override else None,
            "reprocessCount": self.reprocess_count,
            "reasons": list(self.reasons),
            "notes": self.notes,
            "publishState": resolve_publish_state(self).value,
        }


@dataclass(frozen=True, slots=True)
class ReviewLedger:
    execution_id: str
    ref: str
    article: ReviewVerdict | None = None
    images: tuple[ReviewVerdict, ...] = ()
    facts: tuple[ReviewVerdict, ...] = ()

    def __post_init__(self) -> None:
        _required_string(self.execution_id, label="executionId")
        _required_string(self.ref, label="ref")
        if self.article is not None and self.article.kind is not ReviewItemKind.ARTICLE:
            raise ValueError("review ledger article must use ReviewItemKind.ARTICLE")
        if any(item.kind is not ReviewItemKind.IMAGE for item in self.images):
            raise ValueError("review ledger images must use ReviewItemKind.IMAGE")
        if any(item.kind is not ReviewItemKind.FACT for item in self.facts):
            raise ValueError("review ledger facts must use ReviewItemKind.FACT")

    def all_items(self) -> tuple[ReviewVerdict, ...]:
        return ((self.article,) if self.article else ()) + self.images + self.facts

    def find_item(self, kind: ReviewItemKind, target: str) -> ReviewVerdict | None:
        if kind is ReviewItemKind.ARTICLE:
            return self.article
        pool = self.images if kind is ReviewItemKind.IMAGE else self.facts
        return next((item for item in pool if item.target == target), None)

    def replace_item(self, replacement: ReviewVerdict) -> "ReviewLedger":
        if replacement.kind is ReviewItemKind.ARTICLE:
            if self.article is None or self.article.target != replacement.target:
                raise KeyError(f"review article target not found: {replacement.target!r}")
            return replace(self, article=replacement)
        current = self.images if replacement.kind is ReviewItemKind.IMAGE else self.facts
        found = any(item.target == replacement.target for item in current)
        if not found:
            raise KeyError(
                f"review item not found: kind={replacement.kind.value!r} target={replacement.target!r}"
            )
        updated = tuple(
            replacement if item.target == replacement.target else item for item in current
        )
        return replace(self, images=updated) if replacement.kind is ReviewItemKind.IMAGE else replace(self, facts=updated)

    @classmethod
    def from_document(cls, value: object) -> "ReviewLedger":
        if not isinstance(value, Mapping):
            raise ValueError("review ledger must be an object")
        allowed = {"schema", "executionId", "ref", "article", "images", "facts"}
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise ValueError(f"review ledger has unknown fields: {', '.join(unknown)}")
        if value.get("schema") != REVIEW_LEDGER_SCHEMA:
            raise ValueError("review ledger schema is invalid")
        raw_images = value.get("images", [])
        raw_facts = value.get("facts", [])
        if not isinstance(raw_images, list) or not isinstance(raw_facts, list):
            raise ValueError("review ledger images and facts must be arrays")
        article = value.get("article")
        return cls(
            execution_id=_required_string(value.get("executionId"), label="executionId"),
            ref=_required_string(value.get("ref"), label="ref"),
            article=ReviewVerdict.from_document(article) if article is not None else None,
            images=tuple(ReviewVerdict.from_document(item) for item in raw_images),
            facts=tuple(ReviewVerdict.from_document(item) for item in raw_facts),
        )

    def to_document(self) -> dict[str, object]:
        return {
            "schema": REVIEW_LEDGER_SCHEMA,
            "executionId": self.execution_id,
            "ref": self.ref,
            "article": self.article.to_document() if self.article else None,
            "images": [item.to_document() for item in self.images],
            "facts": [item.to_document() for item in self.facts],
        }


def resolve_publish_state(
    item: ReviewVerdict,
    policy: ReviewPolicy | None = None,
) -> ReviewPublishState:
    """Derive the only publish state from a typed verdict and source policy."""
    active_policy = policy or review_policy()
    if item.human_override is ReviewOverride.DISCARD:
        return ReviewPublishState.DISCARD
    if item.human_override is ReviewOverride.PUBLISHABLE:
        return ReviewPublishState.PUBLISHABLE
    if (
        item.human_judgment is ReviewJudgment.CREDIBLE
        or (
            item.human_score is not None
            and item.human_score >= active_policy.human_publish_at_least
        )
    ):
        return ReviewPublishState.PUBLISHABLE
    if item.human_judgment is ReviewJudgment.DOUBTFUL:
        return ReviewPublishState.FIX
    if item.agent_judgment is ReviewJudgment.DOUBTFUL:
        if item.agent_score <= active_policy.auto_discard_at_most:
            return ReviewPublishState.DISCARD
        if active_policy.require_human_when_doubtful:
            return ReviewPublishState.FIX
        return (
            ReviewPublishState.PUBLISHABLE
            if item.agent_score >= active_policy.agent_publish_at_least
            else ReviewPublishState.FIX
        )
    return (
        ReviewPublishState.PUBLISHABLE
        if item.agent_score >= active_policy.agent_publish_at_least
        else ReviewPublishState.FIX
    )


def reprocess_exhausted(item: ReviewVerdict, policy: ReviewPolicy | None = None) -> bool:
    return item.reprocess_count >= (policy or review_policy()).max_reprocess_attempts


def needs_human(item: ReviewVerdict, policy: ReviewPolicy | None = None) -> bool:
    if resolve_publish_state(item, policy) is not ReviewPublishState.FIX:
        return False
    if item.human_judgment is ReviewJudgment.DOUBTFUL:
        return True
    if (
        item.agent_judgment is ReviewJudgment.DOUBTFUL
        and item.human_judgment is ReviewJudgment.UNJUDGED
    ):
        return True
    return item.agent_judgment is ReviewJudgment.CREDIBLE and reprocess_exhausted(item, policy)


def _image_verdict(value: object) -> tuple[ImageSafetyReviewStatus, tuple[str, ...]]:
    if not isinstance(value, Mapping):
        raise ValueError("image safety verdict must be an object")
    try:
        status = ImageSafetyReviewStatus(
            _required_string(value.get("status"), label="imageSafety.status")
        )
    except ValueError as exc:
        raise ValueError(f"image safety verdict status is invalid: {exc}") from exc
    return status, _string_tuple(value.get("reasons", []), label="imageSafety.reasons")


def agent_image_verdict(asset_id: str, value: object) -> ReviewVerdict:
    status, reasons = _image_verdict(value)
    policy = review_policy()
    if status is ImageSafetyReviewStatus.SAFE:
        score = policy.maximum_score
        judgment = ReviewJudgment.CREDIBLE
    elif status is ImageSafetyReviewStatus.TEXT_HEAVY:
        score = policy.agent_publish_at_least
        judgment = ReviewJudgment.CREDIBLE
    elif status is ImageSafetyReviewStatus.UNSAFE:
        score = policy.auto_discard_at_most
        judgment = ReviewJudgment.DOUBTFUL
    else:
        score = max(policy.minimum_score, policy.auto_discard_at_most + 1)
        judgment = ReviewJudgment.DOUBTFUL
    return ReviewVerdict(
        kind=ReviewItemKind.IMAGE,
        target=_required_string(asset_id, label="assetId"),
        agent_judgment=judgment,
        agent_score=score,
        reasons=reasons,
    )


def agent_article_verdict(ref: str, *, passed: bool, score: int) -> ReviewVerdict:
    return ReviewVerdict(
        kind=ReviewItemKind.ARTICLE,
        target=_required_string(ref, label="ref"),
        agent_judgment=ReviewJudgment.CREDIBLE if passed else ReviewJudgment.DOUBTFUL,
        agent_score=review_policy().validate_score(score, label="article score"),
    )


def agent_fact_verdict(fact: str, *, traceable: bool) -> ReviewVerdict:
    policy = review_policy()
    return ReviewVerdict(
        kind=ReviewItemKind.FACT,
        target=_required_string(fact, label="fact"),
        agent_judgment=ReviewJudgment.CREDIBLE if traceable else ReviewJudgment.DOUBTFUL,
        agent_score=(
            policy.agent_publish_at_least
            if traceable
            else max(policy.minimum_score, policy.auto_discard_at_most + 1)
        ),
        reasons=() if traceable else ("fact not traceable to source",),
    )


def post_publishability(ledger: ReviewLedger) -> tuple[bool, list[str], list[str]]:
    """Return whether publication is allowed, blocked reasons, and discards."""
    reasons: list[str] = []
    discards: list[str] = []
    if ledger.article is None:
        reasons.append("article item missing")
    elif resolve_publish_state(ledger.article) is not ReviewPublishState.PUBLISHABLE:
        reasons.append(
            f"article publishState={resolve_publish_state(ledger.article).value}"
        )
    for item in (*ledger.images, *ledger.facts):
        state = resolve_publish_state(item)
        if state is ReviewPublishState.DISCARD:
            discards.append(item.target)
        elif state is not ReviewPublishState.PUBLISHABLE:
            reasons.append(f"{item.kind.value}:{item.target} publishState={state.value}")
    return not reasons, reasons, discards


OBJECT_LEDGER_FILE = "review_ledger.json"
OBJECT_ENTITIES_FILE = "review_entities.json"


def review_dir(execution_id: str) -> Path:
    return execution_shared_dir(execution_id) / "review"


def _object_review_dir(execution_id: str, ref: str) -> Path | None:
    from content.post import object_index as content_object
    from core.paths import STAGE_REVIEW

    if not content_object.content_coords(execution_id, ref):
        return None
    return content_object.content_object_stage_dir(execution_id, ref, STAGE_REVIEW)


def ledger_path(execution_id: str, ref: str) -> Path:
    obj = _object_review_dir(execution_id, ref)
    if obj is None:
        raise KeyError(f"review ledger not registered for ref={ref!r} (execution={execution_id})")
    return obj / OBJECT_LEDGER_FILE


def entities_path(execution_id: str, ref: str) -> Path:
    obj = _object_review_dir(execution_id, ref)
    if obj is None:
        raise KeyError(f"review entities not registered for ref={ref!r} (execution={execution_id})")
    return obj / OBJECT_ENTITIES_FILE


def load_ledger(execution_id: str, ref: str) -> ReviewLedger | None:
    try:
        path = ledger_path(execution_id, ref)
    except KeyError:
        return None
    return ReviewLedger.from_document(read_json(path)) if path.is_file() else None


def save_ledger(ledger: ReviewLedger) -> Path:
    path = ledger_path(ledger.execution_id, ledger.ref)
    write_json(path, ledger.to_document())
    return path


def iter_ledgers(execution_id: str) -> tuple[ReviewLedger, ...]:
    from content.post import object_index as content_object

    rows: list[ReviewLedger] = []
    for ref in content_object.iter_content_refs(execution_id):
        path = ledger_path(execution_id, ref)
        if path.is_file():
            rows.append(ReviewLedger.from_document(read_json(path)))
    return tuple(rows)


__all__ = [
    "OBJECT_ENTITIES_FILE",
    "OBJECT_LEDGER_FILE",
    "REVIEW_LEDGER_SCHEMA",
    "ReviewLedger",
    "ReviewVerdict",
    "agent_article_verdict",
    "agent_fact_verdict",
    "agent_image_verdict",
    "entities_path",
    "iter_ledgers",
    "ledger_path",
    "load_ledger",
    "needs_human",
    "post_publishability",
    "reprocess_exhausted",
    "resolve_publish_state",
    "review_dir",
    "save_ledger",
]
