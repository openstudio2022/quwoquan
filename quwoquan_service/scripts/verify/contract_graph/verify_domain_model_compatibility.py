#!/usr/bin/env python3
"""Compare a candidate ContractGraph with the last immutable Prod-full graph.

The gate deliberately keeps model versions out of the wire.  ``model_version``
is read only from each object-local ``object.yaml`` document embedded in the
ContractGraph; when absent, the initial version is ``1.0``.  The tool computes
the required version and reports a mismatch, but never rewrites authoring
sources.

Exit codes:
  0: the compatibility gate passed;
  1: input/evidence is malformed;
  2: the candidate is well formed but release-blocked.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


REPORT_SCHEMA = "domain-model-compatibility-report"
WINDOW_SCHEMA = "client-contract-compatibility-window"
MIGRATION_SCHEMA = "quiesced-storage-migration-plan"
HOSTED_READBACK_SCHEMA = "prod-hosted-release-receipt-readback"
HOSTED_RECEIPT_SCHEMA = "prod-hosted-release-receipt"
HOSTED_AUTHORITY = "prod-hosted-service-plane"
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
RECEIPT_ID_RE = re.compile(r"^[0-9a-f]{64}$")
MODEL_VERSION_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
COMPATIBILITY_LEVELS = {"none": 0, "compatible": 1, "incompatible": 2}
NULLABLE_CONSTRAINTS = {"NULLABLE"}
REQUIRED_CONSTRAINTS = {"NOT_NULL", "NOT_BLANK", "REQUIRED"}


class InputError(ValueError):
    """Raised when a release input cannot be trusted."""


def _reject_duplicate_keys(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InputError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _read_json(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise InputError(f"cannot read {path}: {error}") from error
    try:
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise InputError(f"invalid JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise InputError(f"{path} must contain one JSON object")
    return value


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _file_digest(path: Path) -> str:
    try:
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise InputError(f"cannot hash {path}: {error}") from error


def _digest_value(value: object, field_name: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise InputError(f"{field_name} must be canonical sha256:<hex>")
    return value


def _string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"{field_name} must be a non-empty string")
    return value.strip()


def _list(value: object, field_name: str) -> list[Any]:
    if not isinstance(value, list):
        raise InputError(f"{field_name} must be an array")
    return value


def _mapping(value: object, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InputError(f"{field_name} must be an object")
    return value


def _receipt_id(receipt: Mapping[str, Any]) -> str:
    unsigned = dict(receipt)
    unsigned.pop("receiptId", None)
    return hashlib.sha256(_canonical_bytes(unsigned)).hexdigest()


@dataclass(frozen=True, order=True)
class ModelVersion:
    major: int
    minor: int

    @classmethod
    def parse(cls, value: object, field_name: str) -> "ModelVersion":
        if not isinstance(value, str):
            raise InputError(f"{field_name} must be major.minor")
        match = MODEL_VERSION_RE.fullmatch(value)
        if match is None:
            raise InputError(f"{field_name} must be major.minor")
        return cls(int(match.group(1)), int(match.group(2)))

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}"

    def next_minor(self) -> "ModelVersion":
        return ModelVersion(self.major, self.minor + 1)

    def next_major(self) -> "ModelVersion":
        return ModelVersion(self.major + 1, 0)


@dataclass(frozen=True)
class FieldShape:
    name: str
    type_name: str
    nullable: bool
    has_default: bool
    enum_values: tuple[str, ...] = ()


@dataclass
class ChangeSet:
    level: str = "none"
    changes: list[dict[str, str]] = field(default_factory=list)

    def add(self, level: str, code: str, detail: str) -> None:
        if level not in COMPATIBILITY_LEVELS:
            raise AssertionError(level)
        if COMPATIBILITY_LEVELS[level] > COMPATIBILITY_LEVELS[self.level]:
            self.level = level
        self.changes.append({"level": level, "code": code, "detail": detail})

    def extend(self, other: "ChangeSet") -> None:
        for item in other.changes:
            self.add(item["level"], item["code"], item["detail"])


@dataclass
class GraphView:
    document: dict[str, Any]
    digest: str
    objects: dict[str, dict[str, Any]]
    operations: dict[str, dict[str, Any]]
    graphql_operations: dict[str, dict[str, Any]]
    documents: dict[str, dict[str, Any]]
    input_issues: list[str]

    @classmethod
    def load(cls, path: Path) -> "GraphView":
        document = _read_json(path)
        objects_list = _list(document.get("objects"), f"{path}.objects")
        operations_list = _list(document.get("operations"), f"{path}.operations")
        documents_list = _list(document.get("documents"), f"{path}.documents")
        objects = _index_records(objects_list, "id", f"{path}.objects")
        operations = _index_records(operations_list, "id", f"{path}.operations")
        documents = _index_records(documents_list, "path", f"{path}.documents")
        issues: list[str] = []
        graphql = _extract_graphql_operations(document, documents, issues)
        for operation_id in sorted(set(operations) & set(graphql)):
            issues.append(
                f"operation id is shared by REST and GraphQL contracts: {operation_id}"
            )
        return cls(
            document=document,
            digest=_file_digest(path),
            objects=objects,
            operations=operations,
            graphql_operations=graphql,
            documents=documents,
            input_issues=issues,
        )

    def object_document(self, object_id: str) -> dict[str, Any]:
        obj = self.objects.get(object_id)
        if obj is None:
            raise InputError(f"ContractGraph object is missing: {object_id}")
        path = _string(obj.get("sourcePath"), f"objects[{object_id}].sourcePath")
        document = self.documents.get(path)
        if document is None:
            raise InputError(f"ContractGraph source document is missing: {path}")
        return _mapping(document.get("content"), f"documents[{path}].content")

    def object_dir(self, object_id: str) -> str:
        source_path = _string(
            self.objects[object_id].get("sourcePath"),
            f"objects[{object_id}].sourcePath",
        )
        return source_path.rsplit("/", 1)[0]

    def model_version(self, object_id: str) -> ModelVersion:
        obj = self.objects[object_id]
        direct = obj.get("modelVersion")
        if direct is not None:
            return ModelVersion.parse(direct, f"objects[{object_id}].modelVersion")
        authored = self.object_document(object_id).get("model_version", "1.0")
        return ModelVersion.parse(
            authored,
            f"documents[{self.objects[object_id]['sourcePath']}].content.model_version",
        )

    def object_fields(self, object_id: str) -> dict[str, dict[str, FieldShape]]:
        obj = self.objects[object_id]
        object_name = _string(obj.get("name"), f"objects[{object_id}].name")
        path = self.object_dir(object_id) + "/fields.yaml"
        document = self.documents.get(path)
        if document is None:
            return {}
        content = _mapping(document.get("content"), f"documents[{path}].content")
        enum_catalog = _enum_catalog(self.documents, content)
        result: dict[str, dict[str, FieldShape]] = {}
        root_fields = content.get("fields")
        if isinstance(root_fields, list):
            result[object_name] = _field_map(root_fields, enum_catalog, path)
        types = content.get("types")
        if isinstance(types, dict):
            for type_name, definition in types.items():
                if not isinstance(type_name, str) or not isinstance(definition, dict):
                    continue
                fields = definition.get("fields")
                if isinstance(fields, list):
                    result[type_name] = _field_map(fields, enum_catalog, path)
        return result

    def error_catalog(self, object_id: str) -> dict[str, tuple[Any, ...]]:
        path = self.object_dir(object_id) + "/errors.yaml"
        document = self.documents.get(path)
        if document is None:
            return {}
        content = _mapping(document.get("content"), f"documents[{path}].content")
        errors = content.get("errors")
        if not isinstance(errors, list):
            return {}
        result: dict[str, tuple[Any, ...]] = {}
        for entry in errors:
            if not isinstance(entry, dict) or not isinstance(entry.get("code"), str):
                continue
            result[entry["code"]] = (
                entry.get("http_status"),
                entry.get("recovery_action"),
                entry.get("recovery_after_seconds"),
                entry.get("disruption_level"),
            )
        return result

    def storage_signature(self, object_id: str) -> dict[str, Any]:
        path = self.object_dir(object_id) + "/storage.yaml"
        document = self.documents.get(path)
        storage = (
            _mapping(document.get("content"), f"documents[{path}].content")
            if document is not None
            else {}
        )
        object_doc = self.object_document(object_id)
        identity = object_doc.get("identity")
        identity_fields = []
        if isinstance(identity, dict) and isinstance(identity.get("fields"), list):
            identity_fields = sorted(str(item) for item in identity["fields"])
        object_fields = self.object_fields(object_id)
        root_name = _string(
            self.objects[object_id].get("name"), f"objects[{object_id}].name"
        )
        persistent_fields: dict[str, FieldShape] = {}
        for name, shape in object_fields.get(root_name, {}).items():
            raw = _find_raw_field(self, object_id, name)
            role = raw.get("role") if isinstance(raw, dict) else None
            if role != "transport_only":
                persistent_fields[name] = shape
        return {
            "backend": storage.get("backend"),
            "role": storage.get("role"),
            "identityFields": identity_fields,
            "fields": persistent_fields,
            "tables": _storage_tables(storage.get("tables")),
            "collections": _storage_collections(storage.get("collections")),
        }


def _index_records(
    values: Sequence[Any], key_name: str, field_name: str
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, value in enumerate(values):
        if not isinstance(value, dict):
            raise InputError(f"{field_name}[{index}] must be an object")
        key = _string(value.get(key_name), f"{field_name}[{index}].{key_name}")
        if key in result:
            raise InputError(f"{field_name} contains duplicate {key_name}: {key}")
        result[key] = value
    return result


def _extract_graphql_operations(
    graph: Mapping[str, Any],
    documents: Mapping[str, Mapping[str, Any]],
    issues: list[str],
) -> dict[str, dict[str, Any]]:
    candidates: list[tuple[str, Any]] = []
    for key in ("graphqlOperations", "graphqlQueries"):
        if key in graph:
            candidates.append((key, graph[key]))
    for path, document in documents.items():
        if not (path.endswith("/graphql.yaml") or path == "_shared/graphql.yaml"):
            continue
        content = document.get("content")
        if not isinstance(content, dict):
            issues.append(f"{path}: GraphQL document content must be an object")
            continue
        for key in ("operations", "queries", "persisted_queries", "persistedQueries"):
            if key in content:
                candidates.append((f"{path}#{key}", content[key]))
    result: dict[str, dict[str, Any]] = {}
    for source, raw_items in candidates:
        if not isinstance(raw_items, list):
            issues.append(f"{source}: GraphQL operations must be an array")
            continue
        for index, raw in enumerate(raw_items):
            if not isinstance(raw, dict):
                issues.append(f"{source}[{index}]: GraphQL operation must be an object")
                continue
            operation_id = raw.get("id") or raw.get("operationId") or raw.get("operation_id")
            object_id = raw.get("objectId") or raw.get("object_id")
            response_entity = (
                raw.get("responseEntity")
                or raw.get("response_entity")
                or raw.get("responseType")
                or raw.get("resultType")
                or raw.get("slice")
            )
            if not isinstance(operation_id, str) or not operation_id:
                issues.append(f"{source}[{index}]: GraphQL operation id is required")
                continue
            if not isinstance(object_id, str) or not object_id:
                issues.append(
                    f"{source}[{index}] {operation_id}: GraphQL objectId is required"
                )
                continue
            if response_entity is None and not isinstance(raw.get("fields"), list):
                issues.append(
                    f"{source}[{index}] {operation_id}: response type or fields are required"
                )
                continue
            normalized = dict(raw)
            normalized.update(
                {
                    "id": operation_id,
                    "objectId": object_id,
                    "kind": "query",
                    "channel": "graphql",
                    "responseEntity": response_entity,
                    "sourcePath": source,
                }
            )
            if operation_id in result:
                issues.append(f"duplicate GraphQL operation id: {operation_id}")
                continue
            result[operation_id] = normalized
    return result


def _enum_catalog(
    documents: Mapping[str, Mapping[str, Any]],
    local_content: Mapping[str, Any],
) -> dict[str, tuple[str, ...]]:
    result: dict[str, tuple[str, ...]] = {}
    for path, document in documents.items():
        if not path.endswith("/types.yaml") and path != "_shared/types.yaml":
            continue
        content = document.get("content")
        if not isinstance(content, dict):
            continue
        for name, values in content.items():
            if isinstance(name, str) and isinstance(values, list):
                result[name] = tuple(sorted(str(value) for value in values))
    local_enums = local_content.get("enums")
    if isinstance(local_enums, dict):
        for name, definition in local_enums.items():
            values = definition.get("values") if isinstance(definition, dict) else None
            if isinstance(name, str) and isinstance(values, list):
                result[name] = tuple(sorted(str(value) for value in values))
    return result


def _field_map(
    fields: Sequence[Any],
    enum_catalog: Mapping[str, tuple[str, ...]],
    source_path: str,
) -> dict[str, FieldShape]:
    result: dict[str, FieldShape] = {}
    for index, raw in enumerate(fields):
        if not isinstance(raw, dict):
            raise InputError(f"{source_path}.fields[{index}] must be an object")
        name = _string(raw.get("name"), f"{source_path}.fields[{index}].name")
        type_name = _string(raw.get("type"), f"{source_path}.fields[{index}].type")
        constraints_raw = raw.get("constraints", [])
        if not isinstance(constraints_raw, list):
            raise InputError(f"{source_path}.fields[{index}].constraints must be an array")
        constraints = {str(value) for value in constraints_raw}
        nullable = bool(constraints & NULLABLE_CONSTRAINTS)
        if constraints & REQUIRED_CONSTRAINTS:
            nullable = False
        has_default = "default" in raw or any(
            value.startswith("DEFAULT_") for value in constraints
        )
        enum_ref = raw.get("enum_ref") or raw.get("enumRef")
        enum_values = enum_catalog.get(str(enum_ref), ()) if enum_ref else ()
        if name in result:
            raise InputError(f"{source_path} contains duplicate field: {name}")
        result[name] = FieldShape(
            name=name,
            type_name=type_name,
            nullable=nullable,
            has_default=has_default,
            enum_values=enum_values,
        )
    return result


def _find_raw_field(
    graph: GraphView, object_id: str, field_name: str
) -> dict[str, Any] | None:
    path = graph.object_dir(object_id) + "/fields.yaml"
    document = graph.documents.get(path)
    if document is None or not isinstance(document.get("content"), dict):
        return None
    fields = document["content"].get("fields")
    if not isinstance(fields, list):
        return None
    for field_value in fields:
        if isinstance(field_value, dict) and field_value.get("name") == field_name:
            return field_value
    return None


def _storage_tables(value: object) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for name, raw in value.items():
        if not isinstance(name, str) or not isinstance(raw, dict):
            continue
        columns: dict[str, dict[str, Any]] = {}
        for column in raw.get("columns", []):
            if isinstance(column, dict) and isinstance(column.get("name"), str):
                columns[column["name"]] = column
        result[name] = {
            "pk": tuple(raw.get("pk", [])) if isinstance(raw.get("pk"), list) else (),
            "columns": columns,
            "indexes": _index_signatures(raw.get("indexes")),
            "uniqueConstraints": _index_signatures(raw.get("unique_constraints")),
        }
    return result


def _storage_collections(value: object) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for name, raw in value.items():
        if isinstance(name, str) and isinstance(raw, dict):
            result[name] = {"indexes": _index_signatures(raw.get("indexes"))}
    return result


def _index_signatures(value: object) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for raw in value:
        if not isinstance(raw, dict) or not isinstance(raw.get("name"), str):
            continue
        keys = raw.get("keys") or raw.get("columns") or raw.get("key_order") or []
        if isinstance(keys, dict):
            key_shape: object = tuple(sorted((str(k), str(v)) for k, v in keys.items()))
            partition = tuple(sorted(str(k) for k, v in keys.items() if v == "hashed"))
        elif isinstance(keys, list):
            key_shape = tuple(str(item) for item in keys)
            partition = ()
        else:
            key_shape = str(keys)
            partition = ()
        result[raw["name"]] = {
            "keys": key_shape,
            "partition": partition,
            "unique": bool(raw.get("unique", False)),
        }
    return result


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


def _validate_baseline_receipt(
    readback: Mapping[str, Any], baseline_graph_digest: str
) -> dict[str, Any]:
    if readback.get("schema") != HOSTED_READBACK_SCHEMA:
        raise InputError(
            f"baseline receipt must be {HOSTED_READBACK_SCHEMA}; arbitrary local receipts are forbidden"
        )
    if readback.get("authority") != HOSTED_AUTHORITY:
        raise InputError("baseline receipt readback authority is invalid")
    receipt = _mapping(readback.get("receipt"), "baselineReceipt.receipt")
    if receipt.get("schema") != HOSTED_RECEIPT_SCHEMA:
        raise InputError("baseline hosted receipt schema is invalid")
    if receipt.get("authority") != HOSTED_AUTHORITY:
        raise InputError("baseline hosted receipt authority is invalid")
    if str(receipt.get("stage")) not in {"full", "100"}:
        raise InputError("baseline hosted receipt must be a Prod full/100 stage")
    if str(receipt.get("triggerStage")) not in {"full", "100"}:
        raise InputError("baseline hosted receipt triggerStage must be full/100")
    if receipt.get("decision") != "continue" or receipt.get("rollbackOutcome") != "not_triggered":
        raise InputError("baseline hosted receipt must be a successful non-rollback decision")
    receipt_id = receipt.get("receiptId")
    if not isinstance(receipt_id, str) or RECEIPT_ID_RE.fullmatch(receipt_id) is None:
        raise InputError("baseline hosted receiptId is invalid")
    if _receipt_id(receipt) != receipt_id:
        raise InputError("baseline hosted receiptId does not match immutable bytes")
    if readback.get("receiptRef") != f"receipt:hosted:{receipt_id}":
        raise InputError("baseline hosted receiptRef does not match receiptId")
    if _digest_value(receipt.get("contractGraphDigest"), "contractGraphDigest") != baseline_graph_digest:
        raise InputError("baseline ContractGraph bytes do not match hosted receipt digest")
    return dict(receipt)


def _load_window(
    path: Path | None, baseline_digest: str
) -> tuple[dict[str, dict[str, Any]], str | None]:
    if path is None:
        return {}, None
    document = _read_json(path)
    if document.get("schema") != WINDOW_SCHEMA:
        raise InputError(f"compatibility window schema must be {WINDOW_SCHEMA}")
    if _digest_value(document.get("baselineContractGraphDigest"), "baselineContractGraphDigest") != baseline_digest:
        raise InputError("compatibility window is stale for the baseline ContractGraph")
    minimum_builds = _mapping(document.get("minimumSupportedBuilds"), "minimumSupportedBuilds")
    if not minimum_builds or any(
        not isinstance(platform, str)
        or not isinstance(build, int)
        or isinstance(build, bool)
        or build < 1
        for platform, build in minimum_builds.items()
    ):
        raise InputError("minimumSupportedBuilds must contain positive integer platform builds")
    operations = _index_records(
        _list(document.get("operations"), "compatibilityWindow.operations"),
        "operationId",
        "compatibilityWindow.operations",
    )
    expected_platforms = set(minimum_builds)
    for operation_id, operation in operations.items():
        if not isinstance(operation.get("windowClosed"), bool):
            raise InputError(
                f"compatibilityWindow.operations[{operation_id}].windowClosed must be boolean"
            )
        usage_count = operation.get("usageCount")
        if (
            not isinstance(usage_count, int)
            or isinstance(usage_count, bool)
            or usage_count < 0
        ):
            raise InputError(
                f"compatibilityWindow.operations[{operation_id}].usageCount must be non-negative integer"
            )
        affected = _mapping(
            operation.get("affectedAppBuilds"),
            f"compatibilityWindow.operations[{operation_id}].affectedAppBuilds",
        )
        if set(affected) != expected_platforms:
            raise InputError(
                f"compatibilityWindow.operations[{operation_id}].affectedAppBuilds must cover exactly {sorted(expected_platforms)}"
            )
        for platform, builds in affected.items():
            if (
                not isinstance(builds, list)
                or any(
                    not isinstance(build, int)
                    or isinstance(build, bool)
                    or build < 1
                    for build in builds
                )
                or len(builds) != len(set(builds))
            ):
                raise InputError(
                    f"compatibilityWindow.operations[{operation_id}].affectedAppBuilds.{platform} must contain unique positive builds"
                )
    return operations, _file_digest(path)


def _load_migration_plan(
    path: Path | None, current_digest: str
) -> tuple[dict[str, dict[str, Any]], str | None]:
    if path is None:
        return {}, None
    document = _read_json(path)
    if document.get("schema") != MIGRATION_SCHEMA:
        raise InputError(f"storage migration schema must be {MIGRATION_SCHEMA}")
    if _digest_value(document.get("currentContractGraphDigest"), "currentContractGraphDigest") != current_digest:
        raise InputError("storage migration plan is stale for the current ContractGraph")
    objects = _index_records(
        _list(document.get("objects"), "storageMigration.objects"),
        "objectId",
        "storageMigration.objects",
    )
    return objects, _file_digest(path)


def _window_closed(
    operation_id: str,
    window: Mapping[str, Mapping[str, Any]],
) -> tuple[bool, dict[str, Any]]:
    evidence = window.get(operation_id)
    if evidence is None:
        return False, {"operationId": operation_id, "reason": "evidence_missing"}
    usage_count = evidence.get("usageCount")
    affected = evidence.get("affectedAppBuilds")
    builds_empty = isinstance(affected, dict) and all(
        isinstance(values, list) and not values for values in affected.values()
    )
    closed = (
        evidence.get("windowClosed") is True
        and isinstance(usage_count, int)
        and not isinstance(usage_count, bool)
        and usage_count == 0
        and builds_empty
    )
    return closed, {
        "operationId": operation_id,
        "windowClosed": evidence.get("windowClosed") is True,
        "usageCount": usage_count,
        "affectedAppBuilds": affected,
    }


def _migration_valid(
    object_id: str,
    plans: Mapping[str, Mapping[str, Any]],
) -> tuple[bool, str]:
    plan = plans.get(object_id)
    if plan is None:
        return False, "migration_plan_missing"
    required_true = (
        "commandsPaused",
        "backupVerified",
        "validationVerified",
        "atomicCutover",
        "singleReaderWriter",
    )
    if plan.get("mode") != "quiesced_atomic":
        return False, "migration_mode_must_be_quiesced_atomic"
    if any(plan.get(field_name) is not True for field_name in required_true):
        return False, "migration_quiescence_or_verification_missing"
    if plan.get("dualRead") is not False or plan.get("dualWrite") is not False:
        return False, "dual_read_or_dual_write_forbidden"
    for field_name in ("backupDigest", "validationDigest"):
        value = plan.get(field_name)
        if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
            return False, f"{field_name}_invalid"
    return True, "validated"


def _by_object(
    operations: Iterable[Mapping[str, Any]], kind: str
) -> dict[str, dict[str, Mapping[str, Any]]]:
    result: dict[str, dict[str, Mapping[str, Any]]] = {}
    for operation in operations:
        if operation.get("kind") != kind:
            continue
        object_id = operation.get("objectId")
        operation_id = operation.get("id")
        if not isinstance(object_id, str) or not isinstance(operation_id, str):
            raise InputError("operation id/objectId must be non-empty strings")
        result.setdefault(object_id, {})[operation_id] = operation
    return result


def _operation_changes(
    baseline_graph: GraphView,
    current_graph: GraphView,
    object_id: str,
    kind: str,
) -> tuple[ChangeSet, set[str]]:
    baseline_operations = list(baseline_graph.operations.values()) + list(
        baseline_graph.graphql_operations.values()
    )
    current_operations = list(current_graph.operations.values()) + list(
        current_graph.graphql_operations.values()
    )
    old_map = _by_object(baseline_operations, kind).get(object_id, {})
    new_map = _by_object(current_operations, kind).get(object_id, {})
    changes = ChangeSet()
    incompatible_operations: set[str] = set()
    noun = "query" if kind == "query" else "command"
    for operation_id in sorted(set(old_map) - set(new_map)):
        changes.add("incompatible", f"{noun}_operation_removed", operation_id)
        incompatible_operations.add(operation_id)
    for operation_id in sorted(set(new_map) - set(old_map)):
        changes.add("compatible", f"{noun}_operation_added", operation_id)
    for operation_id in sorted(set(old_map) & set(new_map)):
        if kind == "query":
            delta = _compare_query_operation(
                baseline_graph, current_graph, old_map[operation_id], new_map[operation_id]
            )
        else:
            delta = _compare_command_operation(
                baseline_graph, current_graph, old_map[operation_id], new_map[operation_id]
            )
        changes.extend(delta)
        if delta.level == "incompatible":
            incompatible_operations.add(operation_id)
    return changes, incompatible_operations


def build_report(
    baseline_graph: GraphView,
    current_graph: GraphView,
    baseline_receipt: Mapping[str, Any],
    compatibility_window: Mapping[str, Mapping[str, Any]],
    compatibility_window_digest: str | None,
    migration_plans: Mapping[str, Mapping[str, Any]],
    migration_plan_digest: str | None,
) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    for detail in baseline_graph.input_issues + current_graph.input_issues:
        issues.append({"code": "GRAPHQL.CONTRACT.INVALID", "detail": detail})
    object_reports: list[dict[str, Any]] = []
    all_object_ids = sorted(set(baseline_graph.objects) | set(current_graph.objects))
    for object_id in all_object_ids:
        if object_id not in baseline_graph.objects:
            current_version = current_graph.model_version(object_id)
            required_version = ModelVersion(1, 0)
            version_ok = current_version == required_version
            if not version_ok:
                issues.append(
                    {
                        "code": "MODEL_VERSION.NEW_OBJECT_INVALID",
                        "detail": f"{object_id}: expected 1.0, declared {current_version}",
                    }
                )
            object_reports.append(
                {
                    "objectId": object_id,
                    "baselineModelVersion": None,
                    "currentModelVersion": str(current_version),
                    "requiredModelVersion": str(required_version),
                    "changeImpact": {
                        "query": "compatible",
                        "command": "compatible",
                        "storage": "compatible",
                    },
                    "migrationMode": "additive",
                    "changes": [
                        {
                            "level": "compatible",
                            "code": "object_added",
                            "detail": object_id,
                        }
                    ],
                    "compatibilityWindow": [],
                    "versionDeclarationValid": version_ok,
                }
            )
            continue
        baseline_version = baseline_graph.model_version(object_id)
        if object_id not in current_graph.objects:
            required_version = baseline_version.next_major()
            issues.append(
                {
                    "code": "DOMAIN_MODEL.OBJECT_REMOVED",
                    "detail": f"{object_id}: object removal has no current owner for required {required_version}",
                }
            )
            object_reports.append(
                {
                    "objectId": object_id,
                    "baselineModelVersion": str(baseline_version),
                    "currentModelVersion": None,
                    "requiredModelVersion": str(required_version),
                    "changeImpact": {
                        "query": "incompatible",
                        "command": "incompatible",
                        "storage": "incompatible",
                    },
                    "migrationMode": "quiesced_atomic",
                    "changes": [
                        {
                            "level": "incompatible",
                            "code": "object_removed",
                            "detail": object_id,
                        }
                    ],
                    "compatibilityWindow": [],
                    "versionDeclarationValid": False,
                }
            )
            continue
        current_version = current_graph.model_version(object_id)
        query_changes, query_incompatible = _operation_changes(
            baseline_graph, current_graph, object_id, "query"
        )
        command_changes, command_incompatible = _operation_changes(
            baseline_graph, current_graph, object_id, "command"
        )
        storage_changes = _compare_storage(
            baseline_graph.storage_signature(object_id),
            current_graph.storage_signature(object_id),
        )
        overall_level = max(
            (query_changes.level, command_changes.level, storage_changes.level),
            key=COMPATIBILITY_LEVELS.__getitem__,
        )
        if overall_level == "incompatible":
            required_version = baseline_version.next_major()
        elif overall_level == "compatible":
            required_version = baseline_version.next_minor()
        else:
            required_version = baseline_version
        version_ok = current_version == required_version
        if not version_ok:
            issues.append(
                {
                    "code": "MODEL_VERSION.DECLARATION_MISMATCH",
                    "detail": (
                        f"{object_id}: declared {current_version}, required {required_version}; "
                        "the gate never rewrites object.yaml"
                    ),
                }
            )
        window_results: list[dict[str, Any]] = []
        for operation_id in sorted(query_incompatible | command_incompatible):
            closed, result = _window_closed(operation_id, compatibility_window)
            result["status"] = "closed" if closed else "blocked"
            window_results.append(result)
            if not closed:
                issues.append(
                    {
                        "code": "COMPATIBILITY_WINDOW.OPEN",
                        "detail": f"{object_id}/{operation_id}: minimum App support window is not closed",
                    }
                )
        migration_mode = (
            "quiesced_atomic"
            if storage_changes.level == "incompatible"
            else ("additive" if storage_changes.level == "compatible" else "none")
        )
        migration_status = "not_required"
        if storage_changes.level == "incompatible":
            migration_ok, migration_status = _migration_valid(object_id, migration_plans)
            if not migration_ok:
                issues.append(
                    {
                        "code": "STORAGE.MIGRATION.BLOCKED",
                        "detail": f"{object_id}: {migration_status}",
                    }
                )
        all_changes = sorted(
            query_changes.changes + command_changes.changes + storage_changes.changes,
            key=lambda item: (item["code"], item["detail"], item["level"]),
        )
        object_reports.append(
            {
                "objectId": object_id,
                "baselineModelVersion": str(baseline_version),
                "currentModelVersion": str(current_version),
                "requiredModelVersion": str(required_version),
                "changeImpact": {
                    "query": query_changes.level,
                    "command": command_changes.level,
                    "storage": storage_changes.level,
                },
                "migrationMode": migration_mode,
                "migrationEvidence": migration_status,
                "changes": all_changes,
                "compatibilityWindow": window_results,
                "versionDeclarationValid": version_ok,
            }
        )
    issues.sort(key=lambda item: (item["code"], item["detail"]))
    return {
        "schema": REPORT_SCHEMA,
        "status": "blocked" if issues else "passed",
        "baseline": {
            "authority": baseline_receipt.get("authority"),
            "stage": str(baseline_receipt.get("stage")),
            "receiptId": baseline_receipt.get("receiptId"),
            "committedGeneration": baseline_receipt.get("committedGeneration"),
            "contractGraphDigest": baseline_graph.digest,
        },
        "current": {"contractGraphDigest": current_graph.digest},
        "evidence": {
            "compatibilityWindowDigest": compatibility_window_digest,
            "storageMigrationPlanDigest": migration_plan_digest,
        },
        "objects": object_reports,
        "issues": issues,
        "invariants": {
            "wireModelVersion": "forbidden",
            "automaticSourceRewrite": False,
            "breakingStorageMigration": "quiesced_atomic",
            "dualRead": "forbidden",
            "dualWrite": "forbidden",
        },
    }


def _write_report(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_bytes(data)
        temporary.replace(path)
    except OSError as error:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise InputError(f"cannot write report {path}: {error}") from error


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-receipt", required=True, type=Path)
    parser.add_argument("--baseline-graph", required=True, type=Path)
    parser.add_argument("--current-graph", required=True, type=Path)
    parser.add_argument("--compatibility-window", type=Path)
    parser.add_argument("--storage-migration-plan", type=Path)
    parser.add_argument("--report", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        baseline_graph = GraphView.load(args.baseline_graph)
        current_graph = GraphView.load(args.current_graph)
        readback = _read_json(args.baseline_receipt)
        receipt = _validate_baseline_receipt(readback, baseline_graph.digest)
        window, window_digest = _load_window(
            args.compatibility_window, baseline_graph.digest
        )
        migrations, migration_digest = _load_migration_plan(
            args.storage_migration_plan, current_graph.digest
        )
        report = build_report(
            baseline_graph,
            current_graph,
            receipt,
            window,
            window_digest,
            migrations,
            migration_digest,
        )
        _write_report(args.report, report)
    except InputError as error:
        print(f"GATE_BLOCK input: {error}", file=sys.stderr)
        return 1
    if report["status"] != "passed":
        print(
            f"GATE_BLOCK compatibility: {len(report['issues'])} issue(s); report={args.report}",
            file=sys.stderr,
        )
        return 2
    print(f"PASS domain model compatibility: report={args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
