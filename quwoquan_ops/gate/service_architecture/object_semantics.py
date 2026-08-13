"""对象契约语义规则：kind-aware 访问面、lifecycle 声明与 DEC-011 入口归属。"""
from __future__ import annotations

import re
from typing import Any

from .constants import (
    CANONICAL_EVENT_REF_RE,
    GENERIC_OBJECT_DESCRIPTION_RE,
    LIFECYCLE_CONSUMER_IDEMPOTENCY,
    LIFECYCLE_CONSUMER_KINDS,
    LIFECYCLE_ONLY_ENTRYPOINT_KINDS,
    OBJECT_ACCESS_BY_KIND,
    OBJECT_VERSION_SOURCE_BY_KIND,
    PROCESS_MANAGER_PUBLIC_QUERY_ACCESS,
)


def object_contract_semantic_issues(document: dict[str, Any]) -> list[str]:
    """Validate kind-specific object meaning beyond JSON shape validation."""

    issues: list[str] = []
    kind = str(document.get("kind") or "")
    description = str(document.get("description") or "").strip()
    if GENERIC_OBJECT_DESCRIPTION_RE.search(description):
        issues.append("description is a generic domain-object-contract placeholder")

    identity = document.get("identity") or {}
    version_source = str(identity.get("version_source") or "")
    allowed_version_sources = OBJECT_VERSION_SOURCE_BY_KIND.get(kind, set())
    if version_source not in allowed_version_sources:
        issues.append(
            f"kind={kind} requires identity.version_source in "
            f"{sorted(allowed_version_sources)}, got {version_source!r}"
        )

    access = document.get("access") or {}
    for field, expected in OBJECT_ACCESS_BY_KIND.get(kind, {}).items():
        actual = access.get(field)
        allowed = expected if isinstance(expected, set) else {expected}
        if actual not in allowed:
            issues.append(
                f"kind={kind} requires access.{field} in {sorted(allowed)}, "
                f"got {actual!r}"
            )
    if (
        kind == "process_manager"
        and access.get("cross_context") != "event_only"
        and access.get("queries") != PROCESS_MANAGER_PUBLIC_QUERY_ACCESS
    ):
        issues.append(
            "kind=process_manager exposed through a public contract requires "
            f"access.queries={PROCESS_MANAGER_PUBLIC_QUERY_ACCESS!r} so callers can "
            f"read process state, got {access.get('queries')!r}"
        )

    business_rules = document.get("business_rules")
    if not isinstance(business_rules, list) or not business_rules:
        issues.append("business_rules must be a non-empty list")
    else:
        for index, rule in enumerate(business_rules):
            if isinstance(rule, str) and len(rule.strip()) >= 8:
                continue
            if isinstance(rule, dict):
                rule_id = str(rule.get("id") or "")
                rule_description = str(rule.get("description") or "").strip()
                if re.fullmatch(r"[a-z][a-z0-9_]*", rule_id) and len(
                    rule_description
                ) >= 8:
                    continue
            issues.append(
                f"business_rules[{index}] must be a substantive string or "
                "an {id, description} rule"
            )
    return issues


def snake_to_pascal(value: str) -> str:
    return "".join(part[:1].upper() + part[1:] for part in value.split("_") if part)


def camel_to_snake(value: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()


def lifecycle_authored_consumers(
    document: dict[str, Any],
) -> tuple[list[dict[str, str]], list[str]]:
    """Return structurally valid object-local lifecycle consumer declarations.

    These declarations may replace a standalone ``runtime_entrypoints`` entry
    only for an object with no HTTP route.  Shape validation remains strict so
    an arbitrary lifecycle mapping cannot satisfy the architecture gate.
    """

    lifecycle = document.get("lifecycle")
    if lifecycle is None:
        return [], []
    if not isinstance(lifecycle, dict):
        return [], ["lifecycle must be a mapping"]
    raw_consumers = lifecycle.get("event_consumers")
    if raw_consumers is None:
        return [], []
    issues: list[str] = []
    source_events = lifecycle.get("source_events")
    if not isinstance(source_events, list) or not source_events:
        issues.append(
            "lifecycle entrypoint requires a non-empty source_events string list"
        )
    else:
        normalized_source_events = [
            event.strip() if isinstance(event, str) else ""
            for event in source_events
        ]
        invalid_source_events = [
            index
            for index, event in enumerate(normalized_source_events)
            if not CANONICAL_EVENT_REF_RE.fullmatch(event)
        ]
        if invalid_source_events:
            issues.append(
                "lifecycle.source_events must use canonical "
                "domain.object.EventName refs; invalid indexes="
                f"{invalid_source_events}"
            )
        if len(set(normalized_source_events)) != len(normalized_source_events):
            issues.append("lifecycle.source_events must be unique")
    if not isinstance(raw_consumers, list) or not raw_consumers:
        issues.append("lifecycle.event_consumers must be a non-empty list")
        return [], issues

    consumers: list[dict[str, str]] = []
    required = {"name", "kind", "facet", "method", "idempotency"}
    for index, raw in enumerate(raw_consumers):
        if not isinstance(raw, dict):
            issues.append(f"lifecycle.event_consumers[{index}] must be a mapping")
            continue
        unknown = set(raw) - required
        missing = required - set(raw)
        if unknown:
            issues.append(
                f"lifecycle.event_consumers[{index}] has unknown fields: "
                f"{sorted(unknown)}"
            )
        if missing:
            issues.append(
                f"lifecycle.event_consumers[{index}] is missing fields: "
                f"{sorted(missing)}"
            )
            continue
        consumer = {field: str(raw.get(field) or "").strip() for field in required}
        if not re.fullmatch(r"[A-Z][A-Za-z0-9]+", consumer["name"]):
            issues.append(
                f"lifecycle.event_consumers[{index}].name is not canonical"
            )
        if consumer["kind"] not in LIFECYCLE_CONSUMER_KINDS:
            issues.append(
                f"lifecycle.event_consumers[{index}].kind must be one of "
                f"{sorted(LIFECYCLE_CONSUMER_KINDS)}"
            )
        if not re.fullmatch(
            r"[A-Z][A-Za-z0-9]*(?:Facade|Projector|Projection|Appender|Consumer|"
            r"Coordinator|Recorder|Orchestrator|Handler)",
            consumer["facet"],
        ):
            issues.append(
                f"lifecycle.event_consumers[{index}].facet is not canonical"
            )
        if not re.fullmatch(r"[a-z][A-Za-z0-9]*", consumer["method"]):
            issues.append(
                f"lifecycle.event_consumers[{index}].method is not canonical"
            )
        if consumer["idempotency"] not in LIFECYCLE_CONSUMER_IDEMPOTENCY:
            issues.append(
                f"lifecycle.event_consumers[{index}].idempotency must be one of "
                f"{sorted(LIFECYCLE_CONSUMER_IDEMPOTENCY)}"
            )
        consumers.append(consumer)
    return consumers, issues


def object_entrypoint_mode(
    object_kind: str,
    api_routes: list[Any],
    runtime_entrypoints: list[Any],
    lifecycle_consumers: list[dict[str, str]],
) -> tuple[str | None, list[str]]:
    """Resolve the single DEC-011 entrypoint owner for one object."""

    if api_routes and runtime_entrypoints:
        return None, [
            (
                "canonical object must not own both HTTP api_routes and "
                "runtime_entrypoints"
            )
        ]
    if api_routes:
        return "http", []
    if runtime_entrypoints:
        return "runtime", []
    if lifecycle_consumers:
        if object_kind not in LIFECYCLE_ONLY_ENTRYPOINT_KINDS:
            return None, [
                (
                    f"kind={object_kind} cannot use lifecycle consumers as its only "
                    "entrypoint; lifecycle-only entrypoints require "
                    f"{sorted(LIFECYCLE_ONLY_ENTRYPOINT_KINDS)}"
                )
            ]
        return "lifecycle", []
    return None, [
        (
            "canonical object must own an HTTP operation, typed runtime entrypoint, "
            "or object-local lifecycle consumer handler"
        )
    ]
