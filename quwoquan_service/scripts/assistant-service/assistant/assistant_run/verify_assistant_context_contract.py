#!/usr/bin/env python3
"""Verify Xiaoqu assistant context/grounding metadata contracts."""
from __future__ import annotations

import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("FAIL: PyYAML required (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)


ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "quwoquan_app").is_dir() and (parent / "quwoquan_service").is_dir()
)
ASSISTANT_RUN = (
    ROOT
    / "quwoquan_service"
    / "services"
    / "assistant-service"
    / "contracts"
    / "assistant"
    / "assistant_run"
)
FIELDS_PATH = ASSISTANT_RUN / "fields.yaml"
OPERATIONS_PATH = ASSISTANT_RUN / "operations.yaml"


def load_yaml(path: Path) -> dict:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return raw


def field_map(entity: dict) -> dict[str, dict]:
    fields = entity.get("fields")
    if not isinstance(fields, list):
        return {}
    out: dict[str, dict] = {}
    for item in fields:
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            out[item["name"]] = item
    return out


def route_map(operations: dict) -> dict[str, dict]:
    routes = operations.get("api_routes")
    if not isinstance(routes, list):
        return {}
    out: dict[str, dict] = {}
    for route in routes:
        if isinstance(route, dict) and isinstance(route.get("operation"), str):
            out[route["operation"]] = route
    return out


def assert_field(
    failures: list[str],
    entities: dict,
    entity_name: str,
    field_name: str,
    expected_type: str | None = None,
) -> None:
    entity = entities.get(entity_name)
    if not isinstance(entity, dict):
        failures.append(f"missing entity {entity_name}")
        return
    fields = field_map(entity)
    field = fields.get(field_name)
    if not isinstance(field, dict):
        failures.append(f"{entity_name}: missing field {field_name}")
        return
    if expected_type is not None and field.get("type") != expected_type:
        failures.append(
            f"{entity_name}.{field_name}: type {field.get('type')!r}, want {expected_type!r}"
        )


def assert_absent_field(
    failures: list[str],
    entities: dict,
    entity_name: str,
    field_name: str,
) -> None:
    entity = entities.get(entity_name)
    if not isinstance(entity, dict):
        return
    if field_name in field_map(entity):
        failures.append(f"{entity_name}: must not accept {field_name}")


def main() -> int:
    failures: list[str] = []
    fields = load_yaml(FIELDS_PATH)
    operations = load_yaml(OPERATIONS_PATH)

    entities = fields.get("types")
    if not isinstance(entities, dict):
        print("FAIL: assistant_run/fields.yaml missing types mapping", file=sys.stderr)
        return 1

    required_entities = [
        "AssistantContextSnapshot",
        "AssistantObjectGroundingView",
        "AssistantUserActionGroundingView",
        "AssistantIntersectionEvidenceRef",
        "AssistantConsentMatrix",
        "AssistantIntersectionEvidenceRef",
        "AssistantSearchCitationView",
        "CitationDestination",
    ]
    for entity_name in required_entities:
        if entity_name not in entities:
            failures.append(f"missing entity {entity_name}")

<<<<<<< Updated upstream:quwoquan_service/scripts/assistant-service/assistant/assistant_run/verify_assistant_context_contract.py
    assert_field(failures, entities, "AssistantContextSnapshot", "pageObjects", "[]AssistantObjectGroundingView")
    assert_field(failures, entities, "AssistantContextSnapshot", "consentMatrix", "AssistantConsentMatrix")
    assert_field(failures, entities, "AssistantContextSnapshot", "userActions", "[]AssistantUserActionGroundingView")
=======
    assert_field(failures, entities, "AssistantContextSnapshot", "capturedAt", "datetime")
    assert_field(failures, entities, "AssistantContextSnapshot", "pageType", "string")
>>>>>>> Stashed changes:quwoquan_service/scripts/contract/verify_assistant_context_contract.py
    assert_field(
        failures,
        entities,
        "AssistantContextSnapshot",
<<<<<<< Updated upstream:quwoquan_service/scripts/assistant-service/assistant/assistant_run/verify_assistant_context_contract.py
        "intersectionEvidenceRefs",
        "[]AssistantIntersectionEvidenceRef",
    )
    assert_field(failures, entities, "AssistantObjectGroundingView", "objectTypeRef", "string")
    assert_field(failures, entities, "AssistantConsentMatrix", "canReadCurrentPage", "bool")

    context_fields = field_map(entities.get("AssistantContextSnapshot") or {})
    expected_context_fields = {
        "capturedAt",
        "pageType",
        "pageObjects",
        "userActions",
        "intersectionEvidenceRefs",
        "consentMatrix",
    }
    if set(context_fields) != expected_context_fields:
        failures.append(
            "AssistantContextSnapshot fields must stay minimal: "
            f"got {sorted(context_fields)}, want {sorted(expected_context_fields)}"
        )
    consent_fields = field_map(entities.get("AssistantConsentMatrix") or {})
    if set(consent_fields) != {"canReadCurrentPage"}:
        failures.append(
            "AssistantConsentMatrix may only declare current-page read consent; "
            "conversation and proactive-delivery consent belong to their own objects"
        )
=======
        "pageObjects",
        "[]AssistantObjectGroundingView",
    )
    assert_field(
        failures,
        entities,
        "AssistantContextSnapshot",
        "userActions",
        "[]AssistantUserActionGroundingView",
    )
    assert_field(
        failures,
        entities,
        "AssistantContextSnapshot",
        "intersectionEvidenceRefs",
        "[]AssistantIntersectionEvidenceRef",
    )
    assert_field(
        failures,
        entities,
        "AssistantContextSnapshot",
        "consentMatrix",
        "AssistantConsentMatrix",
    )
    assert_absent_field(
        failures,
        entities,
        "AssistantContextSnapshot",
        "conversationGrounding",
    )
    assert_field(failures, entities, "AssistantObjectGroundingView", "objectTypeRef", "string")
    assert_field(failures, entities, "AssistantConsentMatrix", "canReadCurrentPage", "bool")
    assert_absent_field(
        failures,
        entities,
        "AssistantConsentMatrix",
        "canReadConversation",
    )
    assert_absent_field(
        failures,
        entities,
        "AssistantConsentMatrix",
        "canDeliverProactively",
    )
>>>>>>> Stashed changes:quwoquan_service/scripts/contract/verify_assistant_context_contract.py

    for citation_field in ("destination", "score", "recallSource", "objectTypeRef"):
        assert_field(failures, entities, "AssistantSearchCitationView", citation_field)
    assert_field(failures, entities, "CitationDestination", "url", "string")

    routes = route_map(operations)
    expected_request_entities = {
        "SearchXiaoquResults": "AssistantSearchXiaoquRequestWire",
        "ReportPageContext": "AssistantReportPageContextRequestWire",
    }
    for operation, expected_entity in expected_request_entities.items():
        route = routes.get(operation)
        if not isinstance(route, dict):
            failures.append(f"operations.yaml missing operation {operation}")
            continue
        request_entity = route.get("request_entity")
        if request_entity != expected_entity:
            failures.append(
                f"{operation}: request_entity {request_entity!r}, "
                f"want {expected_entity!r}"
            )
            continue
        assert_field(
            failures,
            entities,
            expected_entity,
            "contextSnapshot",
            "AssistantContextSnapshot",
        )

    if failures:
        print(
            "verify_assistant_context_contract: FAIL\n  " + "\n  ".join(failures),
            file=sys.stderr,
        )
        return 1

    print("verify_assistant_context_contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
