#!/usr/bin/env python3
"""Keep object-relation edge types identical across metadata and typed consumers.

`edgeType` used to be an unconstrained String, and the vocabulary had silently
split into two disjoint halves: the materializer only ever wrote
semantic_co_mention / tag_overlap / geo_proximity, while the app switch only
recognised author_of / posted_to_circle / ... . Each side consumed its own half
without failing, so the "shared fact source for object pages" was never actually
shared. This gate makes that class of drift impossible to merge.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
TYPES_PATH = ROOT / "quwoquan_service/contracts/metadata/_shared/types.yaml"
GO_PATH = ROOT / "quwoquan_service/runtime/recommendation/object_relation_edge_type.go"
DART_PATH = ROOT / "quwoquan_app/lib/core/models/object_relation_edge_type.dart"
DART_LABEL_PATH = (
    ROOT / "quwoquan_app/lib/components/object_page/object_page_sections.dart"
)
ENUM_NAME = "ObjectRelationEdgeType"


def _load_mapping(path: Path) -> dict[str, object]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.relative_to(ROOT)} root must be a mapping")
    return value


def load_shared_values(path: Path) -> tuple[str, ...]:
    document = _load_mapping(path)
    enums = document.get("enums")
    if not isinstance(enums, dict):
        raise ValueError(f"{path.relative_to(ROOT)} enums must be a mapping")
    values = enums.get(ENUM_NAME)
    if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
        raise ValueError(f"{path.relative_to(ROOT)} {ENUM_NAME} must be a string list")
    return tuple(values)


def load_go_values(path: Path) -> tuple[str, ...]:
    """Read the ordered slice rather than the const block.

    The slice is what callers iterate over for BSON `$in` filters, so a constant
    that exists but is missing from the slice is still a real gap.
    """
    source = path.read_text(encoding="utf-8")
    constants = dict(
        re.findall(
            rf"\bEdgeType(\w+)\s+{ENUM_NAME}\s*=\s*\"([^\"]+)\"",
            source,
        )
    )
    slice_match = re.search(
        rf"objectRelationEdgeTypes\s*=\s*\[\]{ENUM_NAME}\{{(?P<body>.*?)\n\}}",
        source,
        re.DOTALL,
    )
    if slice_match is None:
        raise ValueError(
            f"{path.relative_to(ROOT)} objectRelationEdgeTypes slice is missing"
        )
    ordered: list[str] = []
    for name in re.findall(r"\bEdgeType(\w+),", slice_match.group("body")):
        if name not in constants:
            raise ValueError(
                f"{path.relative_to(ROOT)} EdgeType{name} is listed but not declared"
            )
        ordered.append(constants[name])
    unlisted = sorted(set(constants.values()) - set(ordered))
    if unlisted:
        raise ValueError(
            f"{path.relative_to(ROOT)} declares constants absent from the ordered "
            f"slice: {', '.join(unlisted)}"
        )
    return tuple(ordered)


def load_dart_values(path: Path) -> tuple[str, ...]:
    source = path.read_text(encoding="utf-8")
    match = re.search(
        rf"enum {ENUM_NAME} \{{(?P<body>.*?)\n\s*const {ENUM_NAME}",
        source,
        re.DOTALL,
    )
    if match is None:
        raise ValueError(f"{path.relative_to(ROOT)} {ENUM_NAME} is missing")
    return tuple(re.findall(r"\b\w+\('([^']+)'\)[,;]", match.group("body")))


def load_dart_labelled_values(path: Path) -> tuple[str, ...]:
    """Every enum member handled in the presentation switch.

    Dart exhaustiveness already fails the build on a missing arm, but this keeps
    the failure explainable at gate time instead of only inside a flutter build.
    """
    source = path.read_text(encoding="utf-8")
    return tuple(re.findall(rf"{ENUM_NAME}\.(\w+) =>", source))


def _dart_member_name(wire: str) -> str:
    head, *rest = wire.split("_")
    return head + "".join(part.capitalize() for part in rest)


def validate(
    *,
    shared_values: tuple[str, ...],
    go_values: tuple[str, ...],
    dart_values: tuple[str, ...],
    dart_labelled: tuple[str, ...],
) -> list[str]:
    failures: list[str] = []
    if len(shared_values) != len(set(shared_values)):
        failures.append(f"metadata {ENUM_NAME} contains duplicates")
    if not shared_values:
        failures.append(f"metadata {ENUM_NAME} must not be empty")
    for consumer, values in (("Go", go_values), ("Dart", dart_values)):
        if values != shared_values:
            failures.append(
                f"{consumer} {ENUM_NAME} drift: "
                f"expected={list(shared_values)!r} actual={list(values)!r}"
            )
    expected_labels = {_dart_member_name(value) for value in shared_values}
    missing_labels = sorted(expected_labels - set(dart_labelled))
    if missing_labels:
        failures.append(
            "object page relation label switch is missing arms for: "
            + ", ".join(missing_labels)
        )
    return failures


def main() -> int:
    try:
        shared_values = load_shared_values(TYPES_PATH)
        failures = validate(
            shared_values=shared_values,
            go_values=load_go_values(GO_PATH),
            dart_values=load_dart_values(DART_PATH),
            dart_labelled=load_dart_labelled_values(DART_LABEL_PATH),
        )
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"[object-relation-edge-type] FAIL: {exc}")
        return 1
    if failures:
        for failure in failures:
            print(f"[object-relation-edge-type] FAIL: {failure}")
        return 1
    print(f"[object-relation-edge-type] OK: types={len(shared_values)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
