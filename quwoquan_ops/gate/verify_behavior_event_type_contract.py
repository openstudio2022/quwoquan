#!/usr/bin/env python3
"""Keep behavior-event types identical across metadata and typed consumers."""

from __future__ import annotations

import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
TYPES_PATH = ROOT / "quwoquan_service/contracts/metadata/_shared/types.yaml"
BEHAVIORS_PATH = ROOT / "quwoquan_service/services/content-service/contracts/content/post/behaviors.yaml"
DART_PATH = (
    ROOT
    / "quwoquan_app/packages/quwoquan_cloud_contracts/lib/src/circle/"
    "behavior_fact_contracts.dart"
)
GO_PATH = (
    ROOT
    / "quwoquan_service/services/circle-service/internal/circle_management/"
    "circle_behavior_fact/domain/model/circle_behavior_fact.go"
)


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
    values = enums.get("BehaviorEventType")
    if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
        raise ValueError(
            f"{path.relative_to(ROOT)} BehaviorEventType must be a string list"
        )
    return tuple(values)


def load_content_event_values(path: Path) -> tuple[str, ...]:
    document = _load_mapping(path)
    events = document.get("behavior_events")
    if not isinstance(events, list):
        raise ValueError(f"{path.relative_to(ROOT)} behavior_events must be a list")
    values: list[str] = []
    for event in events:
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            raise ValueError(
                f"{path.relative_to(ROOT)} behavior event must declare string type"
            )
        values.append(event["type"])
    return tuple(values)


def load_dart_values(path: Path) -> tuple[str, ...]:
    source = path.read_text(encoding="utf-8")
    match = re.search(
        r"enum CircleBehaviorEventType \{(?P<body>.*?)\n\s*const CircleBehaviorEventType",
        source,
        re.DOTALL,
    )
    if match is None:
        raise ValueError(f"{path.relative_to(ROOT)} CircleBehaviorEventType is missing")
    return tuple(re.findall(r"\b\w+\('([^']+)'\)[,;]", match.group("body")))


def load_go_values(path: Path) -> tuple[str, ...]:
    source = path.read_text(encoding="utf-8")
    return tuple(
        re.findall(
            r"\bBehaviorEventType\w+\s+BehaviorEventType\s+=\s+\"([^\"]+)\"",
            source,
        )
    )


def validate(
    *,
    shared_values: tuple[str, ...],
    content_values: tuple[str, ...],
    dart_values: tuple[str, ...],
    go_values: tuple[str, ...],
) -> list[str]:
    failures: list[str] = []
    if len(shared_values) != len(set(shared_values)):
        failures.append("metadata BehaviorEventType contains duplicates")
    if len(content_values) != len(set(content_values)):
        failures.append("content behavior_events contains duplicate types")
    missing_content = sorted(set(content_values) - set(shared_values))
    if missing_content:
        failures.append(
            "content behavior type missing from metadata BehaviorEventType: "
            + ", ".join(missing_content)
        )
    for consumer, values in (("Dart", dart_values), ("Go", go_values)):
        if values != shared_values:
            failures.append(
                f"{consumer} CircleBehaviorEventType drift: "
                f"expected={list(shared_values)!r} actual={list(values)!r}"
            )
    return failures


def main() -> int:
    try:
        failures = validate(
            shared_values=load_shared_values(TYPES_PATH),
            content_values=load_content_event_values(BEHAVIORS_PATH),
            dart_values=load_dart_values(DART_PATH),
            go_values=load_go_values(GO_PATH),
        )
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"[behavior-event-contract] FAIL: {exc}")
        return 1
    if failures:
        for failure in failures:
            print(f"[behavior-event-contract] FAIL: {failure}")
        return 1
    print(
        "[behavior-event-contract] OK: "
        f"types={len(load_shared_values(TYPES_PATH))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
