"""ContractGraph 的只读视图：模型版本、字段形状、错误目录与存储签名。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from .primitives import (
    COMPATIBILITY_LEVELS,
    InputError,
    MODEL_VERSION_RE,
    NULLABLE_CONSTRAINTS,
    REQUIRED_CONSTRAINTS,
    _file_digest,
    _list,
    _mapping,
    _read_json,
    _string,
)


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
