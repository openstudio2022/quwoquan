"""Canonical quota and disposition closure for one post execution."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from content.execution import spec_contract
from content.execution.workspace import execution_root
from core.io import read_json, write_json
from core.schema import assert_valid


POST_REVIEW_CLOSURE_REF = "_shared/post_review_closure.json"


@dataclass(frozen=True, slots=True)
class PostReviewObjectVerdict:
    object_ref: str
    publish_ref: str
    disposition: str
    issues: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PostReviewClosure:
    execution_id: str
    carrier: str
    approved_quota: int
    objects: tuple[PostReviewObjectVerdict, ...]

    @property
    def qualified(self) -> tuple[PostReviewObjectVerdict, ...]:
        return tuple(row for row in self.objects if row.disposition == "qualified")

    @property
    def discarded(self) -> tuple[PostReviewObjectVerdict, ...]:
        return tuple(row for row in self.objects if row.disposition == "discarded")

    @property
    def qualified_count(self) -> int:
        return len(self.qualified)

    @property
    def passed(self) -> bool:
        return self.qualified_count >= self.approved_quota

    @property
    def qualified_object_refs(self) -> tuple[str, ...]:
        return tuple(row.object_ref for row in self.qualified)

    @property
    def qualified_publish_refs(self) -> tuple[str, ...]:
        return tuple(row.publish_ref for row in self.qualified)

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": "quwoquan_data.post_review_closure",
            "executionId": self.execution_id,
            "carrier": self.carrier,
            "approvedQuota": self.approved_quota,
            "objects": [
                {
                    "objectRef": row.object_ref,
                    "publishRef": row.publish_ref,
                    "disposition": row.disposition,
                    "issues": list(row.issues),
                }
                for row in self.objects
            ],
        }


def indexed_post_targets(execution_id: str) -> dict[str, str]:
    """Return the object-index routing projection used by review and publish."""
    from content.post import object_index as content_object

    return {
        ref: content_object.content_object_rel(execution_id, ref)
        for ref in content_object.iter_content_refs(execution_id)
    }


def resolve_post_review_closure(
    execution_id: str,
    *,
    carrier: str,
    object_targets: Mapping[str, str],
    object_issues: Mapping[str, Sequence[str]],
) -> PostReviewClosure:
    """Resolve every candidate to qualified/discarded using the spec quota."""
    normalized_carrier = str(carrier or "").strip()
    if normalized_carrier not in {"article", "image", "video"}:
        raise ValueError(f"post review carrier is invalid: {carrier!r}")
    target_refs = set(object_targets)
    unknown_issue_refs = set(object_issues) - target_refs
    if unknown_issue_refs:
        raise ValueError(
            "post review issues reference unknown objects: "
            + ", ".join(sorted(unknown_issue_refs))
        )
    rows: list[PostReviewObjectVerdict] = []
    publish_refs: set[str] = set()
    for ref, publish_ref in sorted(object_targets.items()):
        normalized_publish_ref = str(publish_ref or "").strip().strip("/")
        expected_prefix = f"posts/{normalized_carrier}/"
        if not normalized_publish_ref.startswith(expected_prefix):
            raise ValueError(
                f"post review publishRef carrier drift: {ref} -> {normalized_publish_ref}"
            )
        if normalized_publish_ref in publish_refs:
            raise ValueError(f"post review publishRef is duplicated: {normalized_publish_ref}")
        publish_refs.add(normalized_publish_ref)
        issues = tuple(
            dict.fromkeys(
                str(issue).strip()
                for issue in object_issues.get(ref, ())
                if str(issue).strip()
            )
        )
        rows.append(
            PostReviewObjectVerdict(
                object_ref=ref,
                publish_ref=normalized_publish_ref,
                disposition="discarded" if issues else "qualified",
                issues=issues,
            )
        )
    closure = PostReviewClosure(
        execution_id=execution_id,
        carrier=normalized_carrier,
        approved_quota=spec_contract.approved_quota(execution_id),
        objects=tuple(rows),
    )
    assert_valid(
        closure.to_payload(),
        "execution",
        "post_review_closure",
        label=f"post_review_closure:{execution_id}",
    )
    return closure


def write_post_review_closure(
    closure: PostReviewClosure,
    *,
    root: Path | None = None,
) -> Path:
    target = (root or execution_root(closure.execution_id)) / POST_REVIEW_CLOSURE_REF
    write_json(target, closure.to_payload())
    return target


def load_post_review_closure(
    execution_id: str,
    *,
    root: Path | None = None,
    expected_object_targets: Mapping[str, str] | None = None,
) -> PostReviewClosure:
    """Load and re-derive all closure invariants; never accept a stale quota."""
    path = (root or execution_root(execution_id)) / POST_REVIEW_CLOSURE_REF
    if not path.is_file():
        raise FileNotFoundError(f"post review closure is missing: {path}")
    payload = read_json(path)
    assert_valid(
        payload,
        "execution",
        "post_review_closure",
        label=f"post_review_closure:{execution_id}",
    )
    if str(payload.get("executionId") or "") != execution_id:
        raise ValueError("post review closure executionId drift")
    approved_quota = spec_contract.approved_quota(execution_id)
    if payload.get("approvedQuota") != approved_quota:
        raise ValueError("post review closure approvedQuota drift from execution spec")
    carrier = str(payload.get("carrier") or "")
    objects: list[PostReviewObjectVerdict] = []
    seen_refs: set[str] = set()
    seen_publish_refs: set[str] = set()
    for raw in payload.get("objects") or []:
        ref = str(raw.get("objectRef") or "")
        publish_ref = str(raw.get("publishRef") or "")
        disposition = str(raw.get("disposition") or "")
        issues = tuple(str(issue) for issue in raw.get("issues") or [])
        if ref in seen_refs or publish_ref in seen_publish_refs:
            raise ValueError("post review closure contains duplicate object routing")
        if not publish_ref.startswith(f"posts/{carrier}/"):
            raise ValueError(
                f"post review closure publishRef carrier drift for object {ref}"
            )
        seen_refs.add(ref)
        seen_publish_refs.add(publish_ref)
        if (disposition == "qualified") != (not issues):
            raise ValueError(
                f"post review closure disposition/issues drift for object {ref}"
            )
        objects.append(
            PostReviewObjectVerdict(
                object_ref=ref,
                publish_ref=publish_ref,
                disposition=disposition,
                issues=issues,
            )
        )
    closure = PostReviewClosure(
        execution_id=execution_id,
        carrier=carrier,
        approved_quota=approved_quota,
        objects=tuple(objects),
    )
    if expected_object_targets is not None:
        actual_targets = {
            row.object_ref: row.publish_ref
            for row in closure.objects
        }
        normalized_expected = {
            str(ref): str(publish_ref).strip().strip("/")
            for ref, publish_ref in expected_object_targets.items()
        }
        if actual_targets != normalized_expected:
            raise ValueError("post review closure differs from content object index")
    if not closure.passed:
        raise ValueError(
            "post review closure quota shortfall: "
            f"qualified={closure.qualified_count} approvedQuota={approved_quota}"
        )
    return closure


__all__ = [
    "POST_REVIEW_CLOSURE_REF",
    "PostReviewClosure",
    "PostReviewObjectVerdict",
    "indexed_post_targets",
    "load_post_review_closure",
    "resolve_post_review_closure",
    "write_post_review_closure",
]
