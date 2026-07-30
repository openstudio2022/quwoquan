#!/usr/bin/env python3
"""Keep every HomepageType consumer aligned with the shared enum.

HomepageType is declared once in `_shared/types.yaml`, but six hand-maintained
lists decide what actually happens to a value: the Go admission switch, the Dart
label map, the search location set, the wishlist config, the importer's
entity-type map and the intersection registry's objectTypeBindings. Nothing tied
them together, and they had already drifted far enough that eight of the declared
types rendered as a generic fallback label.

The gate deliberately separates two different questions:

* Coverage — the admission set, the label map and the intersection bindings must
  handle every declared type, otherwise a new value is rejected outright, shown
  as "对象", or silently treated as a person by the intersection surface.
* Containment — the wishlist, location and importer lists express product
  choices about a subset, so they may be smaller, but every entry must still be
  a declared type. That catches typos and values left behind after a rename.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
TYPES_PATH = ROOT / "quwoquan_service/contracts/metadata/_shared/types.yaml"
GO_PATH = (
    ROOT
    / "quwoquan_service/services/entity-service/internal/entity_homepage"
    / "homepage/domain/model/homepage.go"
)
LOADER_PATH = (
    ROOT
    / "quwoquan_service/services/entity-service/internal/entity_homepage"
    / "homepage/infrastructure/homepageimport/loader.go"
)
UI_CONFIG_PATH = (
    ROOT
    / "quwoquan_service/services/entity-service/contracts/entity_homepage"
    / "homepage/ui_config.yaml"
)
DART_LABEL_PATH = (
    ROOT / "quwoquan_app/lib/ui/entity/models/homepage_type_labels.dart"
)
DART_LOCATION_PATH = (
    ROOT / "quwoquan_app/lib/ui/search/providers/search_coordinator.dart"
)
INTERSECTION_REGISTRY_PATH = (
    ROOT
    / "quwoquan_service/services/recommendation-service/contracts/recommendation"
    / "recommendation_model_release/intersection_kind_registry.yaml"
)
ENUM_NAME = "HomepageType"

# 非 HomepageType 但共用同一 label 函数的前端伪类型；它们不参与闭集校验。
DART_LABEL_ALIASES = frozenset({"poi", "place", "author", "circle"})


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


def load_go_admission(path: Path) -> tuple[str, ...]:
    source = path.read_text(encoding="utf-8")
    match = re.search(
        r"var homepageTypes = \[\]string\{(?P<body>.*?)\n\}",
        source,
        re.DOTALL,
    )
    if match is None:
        raise ValueError(f"{path.relative_to(ROOT)} homepageTypes slice is missing")
    return tuple(re.findall(r'"([^"]+)"', match.group("body")))


def load_go_importer_targets(path: Path) -> tuple[str, ...]:
    source = path.read_text(encoding="utf-8")
    match = re.search(
        r"var entityTypeToHomepageType = map\[string\]string\{(?P<body>.*?)\n\}",
        source,
        re.DOTALL,
    )
    if match is None:
        raise ValueError(
            f"{path.relative_to(ROOT)} entityTypeToHomepageType map is missing"
        )
    return tuple(re.findall(r':\s*"([^"]+)"', match.group("body")))


def load_wishlist_types(path: Path) -> tuple[str, ...]:
    document = _load_mapping(path)
    values = document.get("homepage_wishlist_types")
    if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
        raise ValueError(
            f"{path.relative_to(ROOT)} homepage_wishlist_types must be a string list"
        )
    return tuple(values)


def load_dart_labelled(path: Path) -> tuple[str, ...]:
    source = path.read_text(encoding="utf-8")
    match = re.search(
        r"String homepageTypeLabel\(String type\) \{(?P<body>.*?)\n\}",
        source,
        re.DOTALL,
    )
    if match is None:
        raise ValueError(f"{path.relative_to(ROOT)} homepageTypeLabel is missing")
    return tuple(re.findall(r"'([^']+)'", match.group("body")))


def load_dart_location_types(path: Path) -> tuple[str, ...]:
    source = path.read_text(encoding="utf-8")
    match = re.search(
        r"_locationHomepageTypes = <String>\{(?P<body>.*?)\n\s*\};",
        source,
        re.DOTALL,
    )
    if match is None:
        raise ValueError(
            f"{path.relative_to(ROOT)} _locationHomepageTypes set is missing"
        )
    return tuple(re.findall(r"'([^']+)'", match.group("body")))


def load_intersection_bound_types(path: Path) -> tuple[str, ...]:
    document = _load_mapping(path)
    bindings = document.get("objectTypeBindings")
    if not isinstance(bindings, list):
        raise ValueError(
            f"{path.relative_to(ROOT)} objectTypeBindings must be a list"
        )
    bound: list[str] = []
    for entry in bindings:
        if not isinstance(entry, dict):
            raise ValueError(
                f"{path.relative_to(ROOT)} objectTypeBindings entries must be mappings"
            )
        object_type = entry.get("objectType")
        if not isinstance(object_type, str) or not object_type.strip():
            raise ValueError(
                f"{path.relative_to(ROOT)} objectTypeBindings entry misses objectType"
            )
        bound.append(object_type.strip())
    return tuple(bound)


def validate(
    *,
    shared_values: tuple[str, ...],
    go_admission: tuple[str, ...],
    dart_labelled: tuple[str, ...],
    wishlist_types: tuple[str, ...],
    location_types: tuple[str, ...],
    importer_targets: tuple[str, ...],
    intersection_bound_types: tuple[str, ...],
) -> list[str]:
    failures: list[str] = []
    if not shared_values:
        failures.append(f"metadata {ENUM_NAME} must not be empty")
    if len(shared_values) != len(set(shared_values)):
        failures.append(f"metadata {ENUM_NAME} contains duplicates")

    declared = set(shared_values)

    if go_admission != shared_values:
        failures.append(
            "Go admission set drift: "
            f"expected={list(shared_values)!r} actual={list(go_admission)!r}"
        )

    labelled = set(dart_labelled) - DART_LABEL_ALIASES
    missing_labels = sorted(declared - labelled)
    if missing_labels:
        failures.append(
            "homepageTypeLabel falls back to the generic label for: "
            + ", ".join(missing_labels)
        )
    stale_labels = sorted(labelled - declared)
    if stale_labels:
        failures.append(
            "homepageTypeLabel handles undeclared types: " + ", ".join(stale_labels)
        )

    for name, values in (
        ("homepage_wishlist_types", wishlist_types),
        ("_locationHomepageTypes", location_types),
        ("entityTypeToHomepageType", importer_targets),
    ):
        undeclared = sorted(set(values) - declared)
        if undeclared:
            failures.append(
                f"{name} references undeclared {ENUM_NAME} values: "
                + ", ".join(undeclared)
            )
        if len(values) != len(set(values)):
            failures.append(f"{name} contains duplicates")

    # objectTypeBindings 是交集侧 objectType→objectKind 的唯一真相源。缺登记不会报错，
    # 只会让该主页在交集里查表落空——历史上这正是 12 个类型被当成人物、点进去跳
    # 个人主页的原因。这里按覆盖校验，逼新增垂类在注册表登记而不是发 Go/Dart 版本。
    unbound = sorted(declared - set(intersection_bound_types))
    if unbound:
        failures.append(
            "intersection objectTypeBindings misses: " + ", ".join(unbound)
        )
    if len(intersection_bound_types) != len(set(intersection_bound_types)):
        failures.append("objectTypeBindings contains duplicates")
    return failures


def main() -> int:
    try:
        shared_values = load_shared_values(TYPES_PATH)
        failures = validate(
            shared_values=shared_values,
            go_admission=load_go_admission(GO_PATH),
            dart_labelled=load_dart_labelled(DART_LABEL_PATH),
            wishlist_types=load_wishlist_types(UI_CONFIG_PATH),
            location_types=load_dart_location_types(DART_LOCATION_PATH),
            importer_targets=load_go_importer_targets(LOADER_PATH),
            intersection_bound_types=load_intersection_bound_types(
                INTERSECTION_REGISTRY_PATH
            ),
        )
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"[homepage-type] FAIL: {exc}")
        return 1
    if failures:
        for failure in failures:
            print(f"[homepage-type] FAIL: {failure}")
        return 1
    print(f"[homepage-type] OK: types={len(shared_values)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
