"""Canonical request serialization for stackctl handoff and durable receipts."""

from __future__ import annotations

import dataclasses
import importlib
from enum import Enum
from typing import Any, Mapping

from .api import (
    BusinessObjectRef,
    BusinessCaseRunner,
    CaseRef,
    CapabilityRef,
    CapabilityRequest,
    OutputRef,
    RequestId,
)
from .model import canonical_digest


REQUEST_SCHEMA = "qwq.test_data_request.v1"
CASE_REQUEST_SCHEMA = "qwq.test_data_case_request.v1"


def request_graph_document(
    roots: tuple[CapabilityRequest[Any, Any], ...],
) -> dict[str, Any]:
    graph = collect_request_graph(roots)
    stable_ids = _stable_request_ids(roots)
    nodes = [
        _request_document(graph[key], stable_ids)
        for key in sorted(graph, key=lambda item: stable_ids[item])
    ]
    payload = {
        "schema": REQUEST_SCHEMA,
        "roots": [stable_ids[request.request_id.value] for request in roots],
        "requests": nodes,
    }
    return {**payload, "requestDigest": canonical_digest(payload)}


def case_request_document(cases: tuple[CaseRef[Any], ...]) -> dict[str, Any]:
    if not cases:
        raise ValueError("test-data case request requires at least one selected case")
    roots = tuple(case.request for case in cases)
    graph = collect_request_graph(roots)
    stable_ids = _stable_request_ids(roots)
    payload = {
        "schema": CASE_REQUEST_SCHEMA,
        "cases": [_case_document(case, stable_ids) for case in cases],
        "requests": [
            _request_document(graph[key], stable_ids)
            for key in sorted(graph, key=lambda item: stable_ids[item])
        ],
    }
    return {**payload, "requestDigest": canonical_digest(payload)}


def collect_request_graph(
    roots: tuple[CapabilityRequest[Any, Any], ...],
) -> dict[str, CapabilityRequest[Any, Any]]:
    result: dict[str, CapabilityRequest[Any, Any]] = {}

    def visit(request: CapabilityRequest[Any, Any]) -> None:
        key = request.request_id.value
        existing = result.get(key)
        if existing is not None and existing != request:
            raise ValueError(f"request identity collision: {key}")
        if existing is not None:
            return
        result[key] = request
        for dependency in _iter_refs(request.params):
            if dependency.request is None:
                raise ValueError("output dependency is detached from its request")
            if dependency.request.request_id != dependency.request_id:
                raise ValueError("output dependency request identity mismatch")
            visit(dependency.request)

    for root in roots:
        visit(root)
    return result


def load_request_graph(
    document: Mapping[str, Any],
) -> tuple[CapabilityRequest[Any, Any], ...]:
    if document.get("schema") != REQUEST_SCHEMA:
        raise ValueError("test-data request schema mismatch")
    unsigned = {key: value for key, value in document.items() if key != "requestDigest"}
    if document.get("requestDigest") != canonical_digest(unsigned):
        raise ValueError("test-data request digest mismatch")
    rows = document.get("requests")
    roots = document.get("roots")
    if not isinstance(rows, list) or not isinstance(roots, list):
        raise ValueError("test-data request graph is incomplete")
    row_by_id = {
        str(row.get("requestId")): row
        for row in rows
        if isinstance(row, Mapping) and str(row.get("requestId") or "")
    }
    if len(row_by_id) != len(rows):
        raise ValueError("test-data request identities must be unique")
    built: dict[str, CapabilityRequest[Any, Any]] = {}
    building: set[str] = set()

    def build(request_id: str) -> CapabilityRequest[Any, Any]:
        if request_id in built:
            return built[request_id]
        if request_id in building:
            raise ValueError("test-data request graph contains a cycle")
        row = row_by_id.get(request_id)
        if row is None:
            raise ValueError(f"missing request dependency: {request_id}")
        building.add(request_id)
        capability = _resolve_capability(
            str(row.get("ownerService") or ""),
            str(row.get("capabilityKey") or ""),
        )
        params = _decode_value(row.get("params"), capability.params_type, build)
        request = CapabilityRequest(
            capability=capability,
            params=params,
            request_id=RequestId(request_id),
        )
        built[request_id] = request
        building.remove(request_id)
        return request

    return tuple(build(str(root)) for root in roots)


def load_case_requests(
    document: Mapping[str, Any],
) -> tuple[CaseRef[Any], ...]:
    if document.get("schema") != CASE_REQUEST_SCHEMA:
        raise ValueError("test-data case request schema mismatch")
    unsigned = {key: value for key, value in document.items() if key != "requestDigest"}
    if document.get("requestDigest") != canonical_digest(unsigned):
        raise ValueError("test-data case request digest mismatch")
    rows = document.get("requests")
    case_rows = document.get("cases")
    if not isinstance(rows, list) or not isinstance(case_rows, list) or not case_rows:
        raise ValueError("test-data case request is incomplete")
    row_by_id = {
        str(row.get("requestId")): row
        for row in rows
        if isinstance(row, Mapping) and str(row.get("requestId") or "")
    }
    if len(row_by_id) != len(rows):
        raise ValueError("test-data request identities must be unique")
    built: dict[str, CapabilityRequest[Any, Any]] = {}
    building: set[str] = set()

    def build(request_id: str) -> CapabilityRequest[Any, Any]:
        if request_id in built:
            return built[request_id]
        if request_id in building:
            raise ValueError("test-data request graph contains a cycle")
        row = row_by_id.get(request_id)
        if row is None:
            raise ValueError(f"missing request dependency: {request_id}")
        building.add(request_id)
        capability = _resolve_capability(
            str(row.get("ownerService") or ""),
            str(row.get("capabilityKey") or ""),
        )
        params = _decode_value(row.get("params"), capability.params_type, build)
        request = CapabilityRequest(
            capability=capability,
            params=params,
            request_id=RequestId(request_id),
        )
        built[request_id] = request
        building.remove(request_id)
        return request

    cases: list[CaseRef[Any]] = []
    seen_case_ids: set[str] = set()
    for row in case_rows:
        if not isinstance(row, Mapping):
            raise TypeError("serialized test-data case must be an object")
        if set(row) != {
            "caseId",
            "caseIdModule",
            "caseIdType",
            "rootRequestId",
            "runnerModule",
            "runnerType",
        }:
            raise TypeError("serialized test-data case fields mismatch")
        enum_type = _resolve_symbol(
            str(row["caseIdModule"]),
            str(row["caseIdType"]),
        )
        if not isinstance(enum_type, type) or not issubclass(enum_type, Enum):
            raise TypeError("serialized case ID type must be an Enum")
        case_id = enum_type(row["caseId"])
        stable_case_id = str(case_id.value)
        if stable_case_id in seen_case_ids:
            raise ValueError("selected test-data case identities must be unique")
        seen_case_ids.add(stable_case_id)
        runner_type = _resolve_symbol(
            str(row["runnerModule"]),
            str(row["runnerType"]),
        )
        if not isinstance(runner_type, type) or not issubclass(
            runner_type,
            BusinessCaseRunner,
        ):
            raise TypeError("serialized business runner type is invalid")
        cases.append(
            CaseRef(
                case_id=case_id,
                request=build(str(row["rootRequestId"])),
                runner_type=runner_type,
            )
        )
    if set(built) != set(row_by_id):
        raise ValueError("test-data case request contains unreachable request nodes")
    return tuple(cases)


def _stable_request_ids(
    roots: tuple[CapabilityRequest[Any, Any], ...],
) -> dict[str, str]:
    """Assign deterministic wire identities without sharing mutable requests.

    ``CapabilityRef.bind`` intentionally creates an opaque in-process identity:
    two cases with identical params still represent two isolated attempts.  A
    random UUID must not, however, leak into the durable request digest.  The
    serializer therefore numbers nodes by deterministic root/dependency walk
    order while preserving repeated request objects as shared graph nodes.
    """

    stable: dict[str, str] = {}

    def visit(request: CapabilityRequest[Any, Any]) -> None:
        current = request.request_id.value
        if current in stable:
            return
        stable[current] = f"request-{len(stable) + 1:06d}"
        for dependency in _iter_refs(request.params):
            if dependency.request is None:
                raise ValueError("output dependency is detached from its request")
            visit(dependency.request)

    for root in roots:
        visit(root)
    return stable


def _request_document(
    request: CapabilityRequest[Any, Any],
    stable_ids: Mapping[str, str],
) -> dict[str, Any]:
    return {
        "requestId": stable_ids[request.request_id.value],
        "capabilityKey": request.capability.key.value,
        "ownerService": request.capability.owner_service,
        "params": _encode_value(request.params, stable_ids),
    }


def _case_document(
    case: CaseRef[Any],
    stable_ids: Mapping[str, str],
) -> dict[str, Any]:
    case_id_type = type(case.case_id)
    runner_type = case.runner_type
    if "<locals>" in case_id_type.__qualname__ or "<locals>" in runner_type.__qualname__:
        raise ValueError("test-data case identities and runners must be module-level types")
    return {
        "caseId": case.case_id.value,
        "caseIdModule": case_id_type.__module__,
        "caseIdType": case_id_type.__qualname__,
        "rootRequestId": stable_ids[case.request.request_id.value],
        "runnerModule": runner_type.__module__,
        "runnerType": runner_type.__qualname__,
    }


def _encode_value(value: object, stable_ids: Mapping[str, str]) -> object:
    if isinstance(value, OutputRef):
        return {
            "$output": stable_ids[value.request_id.value],
            "fieldPath": list(value.field_path),
        }
    if isinstance(value, BusinessObjectRef):
        return {"objectType": value.object_type, "objectId": value.object_id}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _encode_value(getattr(value, field.name), stable_ids)
            for field in dataclasses.fields(value)
        }
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_encode_value(item, stable_ids) for item in value]
    if value is None or type(value) in {str, int, bool, float}:
        return value
    raise TypeError(f"unsupported request value: {type(value).__name__}")


def _decode_value(value: object, expected: object, build: object) -> object:
    from .api import _validate_value
    from typing import get_args, get_origin, get_type_hints
    import types

    origin = get_origin(expected)
    args = get_args(expected)
    if origin is OutputRef:
        if not isinstance(value, Mapping) or set(value) != {"$output", "fieldPath"}:
            raise TypeError("serialized OutputRef is invalid")
        dependency = build(str(value["$output"]))  # type: ignore[operator]
        ref = OutputRef(
            request_id=dependency.request_id,
            value_type=args[0],
            field_path=tuple(str(item) for item in value["fieldPath"]),
            request=dependency,
        )
        _validate_value(ref, expected, "serialized output")
        return ref
    if origin in (tuple, list):
        if not isinstance(value, list):
            raise TypeError("serialized sequence is invalid")
        item_types = args
        if origin is tuple and len(args) == 2 and args[1] is Ellipsis:
            item_types = tuple(args[0] for _ in value)
        if len(item_types) != len(value):
            raise TypeError("serialized tuple arity mismatch")
        result = tuple(
            _decode_value(item, item_type, build)
            for item, item_type in zip(value, item_types)
        )
        return result if origin is tuple else list(result)
    if origin in (types.UnionType,):
        if value is None and type(None) in args:
            return None
        for option in args:
            if option is type(None):
                continue
            try:
                return _decode_value(value, option, build)
            except (TypeError, ValueError):
                continue
        raise TypeError("serialized union value is invalid")
    if isinstance(expected, type) and issubclass(expected, Enum):
        return expected(value)
    if expected is BusinessObjectRef:
        if not isinstance(value, Mapping):
            raise TypeError("serialized business object reference is invalid")
        return BusinessObjectRef(str(value.get("objectType") or ""), str(value.get("objectId") or ""))
    if isinstance(expected, type) and dataclasses.is_dataclass(expected):
        if not isinstance(value, Mapping):
            raise TypeError(f"serialized {expected.__name__} must be an object")
        hints = get_type_hints(expected)
        expected_names = {field.name for field in dataclasses.fields(expected)}
        if set(value) != expected_names:
            raise TypeError(f"serialized {expected.__name__} fields mismatch")
        return expected(
            **{
                field.name: _decode_value(value[field.name], hints[field.name], build)
                for field in dataclasses.fields(expected)
            }
        )
    if isinstance(expected, type) and type(value) is expected:
        return value
    raise TypeError(f"serialized value does not match {expected!r}")


def _resolve_capability(owner_service: str, key: str) -> CapabilityRef[Any, Any]:
    if not owner_service or not owner_service.replace("_", "").isalnum():
        raise ValueError("serialized capability owner is invalid")
    module = importlib.import_module(
        f"quwoquan_ops.cli.lib.test_data.capabilities.{owner_service}"
    )
    matches = tuple(
        value
        for value in vars(module).values()
        if isinstance(value, CapabilityRef) and value.key.value == key
    )
    if len(matches) != 1:
        raise ValueError(f"unknown or ambiguous capability: {owner_service}/{key}")
    return matches[0]


def _resolve_symbol(module_name: str, qualname: str) -> object:
    if not module_name or not qualname or "<locals>" in qualname:
        raise ValueError("serialized Python type identity is invalid")
    module = importlib.import_module(module_name)
    value: object = module
    for component in qualname.split("."):
        if not component or component.startswith("_"):
            raise ValueError("serialized Python type identity is not public")
        value = getattr(value, component, None)
        if value is None:
            raise ValueError(f"serialized Python type is unavailable: {module_name}/{qualname}")
    return value


def _iter_refs(value: object):
    if isinstance(value, OutputRef):
        yield value
    elif dataclasses.is_dataclass(value) and not isinstance(value, type):
        for field in dataclasses.fields(value):
            yield from _iter_refs(getattr(value, field.name))
    elif isinstance(value, (tuple, list)):
        for item in value:
            yield from _iter_refs(item)
