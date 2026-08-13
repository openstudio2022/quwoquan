"""baseline 与 candidate 之间 query/command/storage 的兼容性比较。"""

from __future__ import annotations

from typing import Any, Mapping

from .graph_view import ChangeSet, FieldShape, GraphView, _field_map
from .primitives import REQUIRED_CONSTRAINTS, InputError, _canonical_bytes


def _authorization_signature(operation: Mapping[str, Any]) -> bytes:
    value = {
        "security": operation.get("security"),
        "authorization": operation.get("authorization"),
        "authMode": operation.get("authMode") or operation.get("auth_mode"),
        "principal": operation.get("principal"),
        "scopes": operation.get("scopes"),
        "permissions": operation.get("permissions"),
        "ownershipPolicy": operation.get("ownershipPolicy")
        or operation.get("ownership_policy"),
    }
    return _canonical_bytes(value)


def _operation_fields(
    graph: GraphView,
    operation: Mapping[str, Any],
    entity_key: str,
) -> dict[str, FieldShape]:
    inline = operation.get("fields")
    if isinstance(inline, list):
        return _field_map(inline, {}, str(operation.get("sourcePath") or "graphql"))
    entity = operation.get(entity_key)
    object_id = operation.get("objectId")
    if not isinstance(entity, str) or not entity or not isinstance(object_id, str):
        return {}
    if object_id not in graph.objects:
        raise InputError(
            f"operation {operation.get('id')} references unknown object {object_id}"
        )
    return graph.object_fields(object_id).get(entity, {})


def _compare_field_shapes(
    baseline: Mapping[str, FieldShape],
    current: Mapping[str, FieldShape],
    *,
    prefix: str,
    additions_are_compatible: bool = True,
) -> ChangeSet:
    changes = ChangeSet()
    for name in sorted(baseline):
        old = baseline[name]
        new = current.get(name)
        if new is None:
            changes.add("incompatible", f"{prefix}_field_removed", name)
            continue
        if old.type_name != new.type_name:
            changes.add(
                "incompatible",
                f"{prefix}_field_type_changed",
                f"{name}: {old.type_name} -> {new.type_name}",
            )
        if old.nullable and not new.nullable:
            changes.add(
                "incompatible", f"{prefix}_field_required_tightened", name
            )
        if old.enum_values and not set(old.enum_values).issubset(new.enum_values):
            removed = sorted(set(old.enum_values) - set(new.enum_values))
            changes.add(
                "incompatible",
                f"{prefix}_enum_tightened",
                f"{name}: removed {removed}",
            )
        elif set(new.enum_values) - set(old.enum_values):
            changes.add("compatible", f"{prefix}_enum_extended", name)
    if additions_are_compatible:
        for name in sorted(set(current) - set(baseline)):
            changes.add("compatible", f"{prefix}_field_added", name)
    return changes


def _compare_query_operation(
    baseline_graph: GraphView,
    current_graph: GraphView,
    old: Mapping[str, Any],
    new: Mapping[str, Any],
) -> ChangeSet:
    changes = ChangeSet()
    operation_id = str(old.get("id"))
    if old.get("channel") != new.get("channel"):
        changes.add("incompatible", "query_channel_changed", operation_id)
    if _authorization_signature(old) != _authorization_signature(new):
        changes.add("incompatible", "query_authorization_changed", operation_id)
    for key in ("method", "pathTemplate", "operationName"):
        if old.get(key) != new.get(key):
            changes.add("incompatible", f"query_{key}_changed", operation_id)
    if old.get("responseEntity") != new.get("responseEntity"):
        changes.add("incompatible", "query_response_type_changed", operation_id)
    old_fields = _operation_fields(baseline_graph, old, "responseEntity")
    new_fields = _operation_fields(current_graph, new, "responseEntity")
    changes.extend(
        _compare_field_shapes(old_fields, new_fields, prefix="query_response")
    )
    renamed_from = new.get("renamedFrom") or new.get("renamed_from")
    if renamed_from:
        changes.add("incompatible", "query_renamed", f"{renamed_from} -> {operation_id}")
    return changes


def _compare_command_operation(
    baseline_graph: GraphView,
    current_graph: GraphView,
    old: Mapping[str, Any],
    new: Mapping[str, Any],
) -> ChangeSet:
    changes = ChangeSet()
    operation_id = str(old.get("id"))
    for key in ("method", "pathTemplate", "requestEntity", "requestBodyKind"):
        if old.get(key) != new.get(key):
            changes.add("incompatible", f"command_{key}_changed", operation_id)
    if _authorization_signature(old) != _authorization_signature(new):
        changes.add("incompatible", "command_authorization_changed", operation_id)
    old_request = _operation_fields(baseline_graph, old, "requestEntity")
    new_request = _operation_fields(current_graph, new, "requestEntity")
    changes.extend(
        _compare_field_shapes(old_request, new_request, prefix="command_request")
    )
    old_reliability = old.get("reliability")
    new_reliability = new.get("reliability")
    old_idempotency = (
        old_reliability.get("idempotency") if isinstance(old_reliability, dict) else None
    )
    new_idempotency = (
        new_reliability.get("idempotency") if isinstance(new_reliability, dict) else None
    )
    if old_idempotency != new_idempotency:
        changes.add("incompatible", "command_idempotency_changed", operation_id)
    old_codes = set(old.get("errorCodes") or [])
    new_codes = set(new.get("errorCodes") or [])
    for code in sorted(old_codes - new_codes):
        changes.add("incompatible", "command_error_removed", str(code))
    old_catalog = baseline_graph.error_catalog(str(old.get("objectId")))
    new_catalog = current_graph.error_catalog(str(new.get("objectId")))
    for code in sorted(old_codes & new_codes):
        if old_catalog.get(str(code)) != new_catalog.get(str(code)):
            changes.add("incompatible", "command_error_recovery_changed", str(code))
    for code in sorted(new_codes - old_codes):
        changes.add("compatible", "command_error_added", str(code))
    return changes


def _compare_storage(baseline: Mapping[str, Any], current: Mapping[str, Any]) -> ChangeSet:
    changes = ChangeSet()
    for key in ("backend", "role", "identityFields"):
        if baseline.get(key) != current.get(key):
            changes.add("incompatible", f"storage_{key}_changed", key)
    changes.extend(
        _compare_storage_fields(
            baseline.get("fields", {}), current.get("fields", {}), prefix="storage"
        )
    )
    old_tables = baseline.get("tables", {})
    new_tables = current.get("tables", {})
    for name in sorted(set(old_tables) - set(new_tables)):
        changes.add("incompatible", "storage_table_removed", name)
    for name in sorted(set(new_tables) - set(old_tables)):
        table = new_tables[name]
        blocking = any(
            _column_required_without_default(column)
            for column in table.get("columns", {}).values()
        )
        changes.add(
            "incompatible" if blocking else "compatible",
            "storage_table_added_required" if blocking else "storage_table_added",
            name,
        )
    for name in sorted(set(old_tables) & set(new_tables)):
        old_table = old_tables[name]
        new_table = new_tables[name]
        if old_table.get("pk") != new_table.get("pk"):
            changes.add("incompatible", "storage_primary_key_changed", name)
        changes.extend(
            _compare_columns(
                old_table.get("columns", {}),
                new_table.get("columns", {}),
                table=name,
            )
        )
        changes.extend(
            _compare_indexes(
                old_table.get("indexes", {}),
                new_table.get("indexes", {}),
                owner=name,
            )
        )
        changes.extend(
            _compare_indexes(
                old_table.get("uniqueConstraints", {}),
                new_table.get("uniqueConstraints", {}),
                owner=name,
                all_unique=True,
            )
        )
    old_collections = baseline.get("collections", {})
    new_collections = current.get("collections", {})
    for name in sorted(set(old_collections) - set(new_collections)):
        changes.add("incompatible", "storage_collection_removed", name)
    for name in sorted(set(new_collections) - set(old_collections)):
        changes.add("compatible", "storage_collection_added", name)
    for name in sorted(set(old_collections) & set(new_collections)):
        changes.extend(
            _compare_indexes(
                old_collections[name].get("indexes", {}),
                new_collections[name].get("indexes", {}),
                owner=name,
            )
        )
    return changes


def _compare_storage_fields(
    baseline: Mapping[str, FieldShape],
    current: Mapping[str, FieldShape],
    *,
    prefix: str,
) -> ChangeSet:
    changes = ChangeSet()
    for name in sorted(baseline):
        old = baseline[name]
        new = current.get(name)
        if new is None:
            changes.add("incompatible", f"{prefix}_field_removed", name)
            continue
        if old.type_name != new.type_name:
            changes.add("incompatible", f"{prefix}_field_type_changed", name)
        if old.nullable and not new.nullable and not new.has_default:
            changes.add("incompatible", f"{prefix}_field_required_without_default", name)
    for name in sorted(set(current) - set(baseline)):
        new = current[name]
        blocking = not new.nullable and not new.has_default
        changes.add(
            "incompatible" if blocking else "compatible",
            f"{prefix}_field_added_required" if blocking else f"{prefix}_field_added",
            name,
        )
    return changes


def _column_required_without_default(column: Mapping[str, Any]) -> bool:
    constraints = column.get("constraints")
    values = {str(item) for item in constraints} if isinstance(constraints, list) else set()
    required = bool(values & REQUIRED_CONSTRAINTS)
    return required and "default" not in column and not any(
        item.startswith("DEFAULT_") for item in values
    )


def _compare_columns(
    baseline: Mapping[str, Mapping[str, Any]],
    current: Mapping[str, Mapping[str, Any]],
    *,
    table: str,
) -> ChangeSet:
    changes = ChangeSet()
    for name in sorted(baseline):
        old = baseline[name]
        new = current.get(name)
        if new is None:
            changes.add("incompatible", "storage_column_removed", f"{table}.{name}")
            continue
        if old.get("type") != new.get("type"):
            changes.add("incompatible", "storage_column_type_changed", f"{table}.{name}")
        if not _column_required_without_default(old) and _column_required_without_default(new):
            changes.add(
                "incompatible",
                "storage_column_required_without_default",
                f"{table}.{name}",
            )
    for name in sorted(set(current) - set(baseline)):
        blocking = _column_required_without_default(current[name])
        changes.add(
            "incompatible" if blocking else "compatible",
            "storage_column_added_required" if blocking else "storage_column_added",
            f"{table}.{name}",
        )
    return changes


def _compare_indexes(
    baseline: Mapping[str, Mapping[str, Any]],
    current: Mapping[str, Mapping[str, Any]],
    *,
    owner: str,
    all_unique: bool = False,
) -> ChangeSet:
    changes = ChangeSet()
    for name in sorted(set(baseline) & set(current)):
        old, new = baseline[name], current[name]
        old_unique = all_unique or bool(old.get("unique"))
        new_unique = all_unique or bool(new.get("unique"))
        if old_unique != new_unique:
            changes.add("incompatible", "storage_index_uniqueness_changed", f"{owner}.{name}")
        if old.get("partition") != new.get("partition"):
            changes.add("incompatible", "storage_partition_key_changed", f"{owner}.{name}")
        if old.get("keys") != new.get("keys"):
            changes.add(
                "incompatible" if old_unique or new_unique else "compatible",
                "storage_unique_index_keys_changed"
                if old_unique or new_unique
                else "storage_non_unique_index_keys_changed",
                f"{owner}.{name}",
            )
    for name in sorted(set(current) - set(baseline)):
        new = current[name]
        unique = all_unique or bool(new.get("unique"))
        changes.add(
            "incompatible" if unique else "compatible",
            "storage_unique_index_added" if unique else "storage_non_unique_index_added",
            f"{owner}.{name}",
        )
    for name in sorted(set(baseline) - set(current)):
        old = baseline[name]
        unique = all_unique or bool(old.get("unique"))
        changes.add(
            "incompatible" if unique else "compatible",
            "storage_unique_index_removed" if unique else "storage_non_unique_index_removed",
            f"{owner}.{name}",
        )
    return changes
