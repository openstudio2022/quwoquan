"""Current reviewed-qualified closure for homepage executions."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from content.execution.workspace import execution_root
from content.homepage.homepage_release_validation import validate_entity_pages
from core.io import read_json
from core.schema import assert_valid


@dataclass(frozen=True, slots=True)
class HomepageReviewClosure:
    execution_id: str
    qualified_refs: tuple[str, ...]
    discarded: Mapping[str, tuple[str, ...]]

    @property
    def qualified_count(self) -> int:
        return len(self.qualified_refs)


def _attestation_issues(
    execution_id: str,
    *,
    label: str,
    object_root: Path,
) -> list[str]:
    path = object_root / "5.review/attestation.json"
    try:
        payload = read_json(path)
        if not isinstance(payload, dict):
            raise TypeError("review attestation must be an object")
        assert_valid(
            payload,
            "content",
            "review_attestation",
            label=path.as_posix(),
        )
    except (OSError, TypeError, ValueError) as exc:
        return [f"{label}: current 5.review attestation is invalid ({exc})"]
    expected = {
        "executionId": execution_id,
        "executionBinding": "frozen",
        "objectRef": f"/entity/{label}",
        "decision": "approved",
    }
    drift = [field for field, value in expected.items() if payload.get(field) != value]
    if drift:
        return [f"{label}: current 5.review attestation drift ({', '.join(drift)})"]
    for field in ("deterministicGate", "independentReviewer", "mediaRefReview"):
        binding = payload.get(field)
        if not isinstance(binding, Mapping) or binding.get("status") != "passed":
            return [f"{label}: current 5.review {field} is not passed"]
    return []


def load_homepage_review_closure(
    execution_id: str,
    *,
    root: Path | None = None,
) -> HomepageReviewClosure:
    """Derive the publishable homepage set from current object and review bytes."""

    work_package = root or execution_root(execution_id)
    entities_root = work_package / "entities"
    objects: list[tuple[str, Path]] = []
    for stage_dir in sorted(entities_root.rglob("1.download")):
        object_root = stage_dir.parent
        relative = object_root.relative_to(entities_root)
        if len(relative.parts) != 3:
            raise ValueError(
                f"homepage object path must be domain/type/name: {relative.as_posix()}"
            )
        label = "/".join(relative.parts)
        objects.append((label, object_root))
    if len({label for label, _object_root in objects}) != len(objects):
        raise ValueError("homepage object tree contains duplicate identities")

    validation_spec = {
        "scope": {
            "coverageTargets": [
                {
                    "entityType": "/".join(label.split("/")[:2]),
                    "name": label.split("/", 2)[2],
                }
                for label, _object_root in objects
            ]
        }
    }
    validation_issues = (
        validate_entity_pages(execution_id, validation_spec) if objects else []
    )
    per_object: dict[str, list[str]] = {label: [] for label, _root in objects}
    execution_issues: list[str] = []
    for issue in validation_issues:
        normalized = str(issue)
        owner = next(
            (label for label in per_object if normalized.startswith(f"{label}:")),
            "",
        )
        if owner:
            per_object[owner].append(normalized)
        else:
            execution_issues.append(normalized)
    for label, object_root in objects:
        per_object[label].extend(
            _attestation_issues(
                execution_id,
                label=label,
                object_root=object_root,
            )
        )
    discarded = {
        label: tuple(issues)
        for label, issues in per_object.items()
        if issues
    }
    if execution_issues:
        discarded["<execution>"] = tuple(execution_issues)
    qualified = (
        ()
        if execution_issues
        else tuple(label for label, _root in objects if not per_object[label])
    )
    return HomepageReviewClosure(
        execution_id=execution_id,
        qualified_refs=qualified,
        discarded=discarded,
    )


__all__ = ["HomepageReviewClosure", "load_homepage_review_closure"]
