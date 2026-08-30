"""Canonical HTTP route binding for hosted human authority."""
from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path
import yaml

CANONICAL_OPERATIONS_RELATIVE_PATH = Path(
    "quwoquan_service/control-plane/platform-ops/contracts/platform_ops/"
    "human_authority/operations.yaml"
)
_DOCUMENT_KEYS = frozenset({"description", "api_routes", "contract_test"})
_CONTRACT_TEST_KEYS = frozenset({"coverage_requirements"})
_ROUTE_KEYS = frozenset(
    {
        "method",
        "path",
        "operation",
        "actor",
        "security",
        "authorization",
        "reliability",
        "error_codes",
        "privacy",
        "telemetry",
        "slo",
        "commercial",
        "application",
        "request_entity",
        "request_body_kind",
        "response_entity",
        "response_body_kind",
        "request_bindings",
    }
)
_ROUTE_REQUIRED_KEYS = frozenset(
    {
        "method",
        "path",
        "operation",
        "actor",
        "security",
        "authorization",
        "reliability",
        "error_codes",
        "privacy",
        "telemetry",
        "slo",
        "commercial",
        "application",
    }
)
_QUERY_OPERATION = "ReadHumanAuthorizationReceipt"
_CONSUME_OPERATION = "ConsumeHumanAuthorizationReceipt"
_REVOKE_OPERATION = "RevokeHumanAuthorizationReceipt"


class HostedAuthorityWireError(ValueError):
    """The canonical operations contract cannot produce one unambiguous wire."""


class _StrictSafeLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects aliases and duplicate mapping keys."""

    def compose_node(self, parent: yaml.Node | None, index: int | None) -> yaml.Node:
        if self.check_event(yaml.AliasEvent):
            event = self.peek_event()
            raise yaml.composer.ComposerError(
                "while composing canonical hosted authority operations",
                None,
                "YAML aliases are not allowed",
                event.start_mark,
            )
        return super().compose_node(parent, index)


def _construct_unique_mapping(
    loader: _StrictSafeLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[object, object]:
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as error:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable mapping key",
                key_node.start_mark,
            ) from error
        if duplicate:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_StrictSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


@dataclass(frozen=True, slots=True)
class HostedAuthorityWire:
    source_path: Path
    source_sha256: str
    query_path_template: str | None
    consume_path_template: str
    revoke_path_template: str


def _strict_document(raw: bytes) -> dict[str, object]:
    try:
        text = raw.decode("utf-8")
    except UnicodeError as error:
        raise HostedAuthorityWireError(
            "canonical hosted authority operations contract is not UTF-8"
        ) from error
    try:
        document = yaml.load(text, Loader=_StrictSafeLoader)
    except yaml.YAMLError as error:
        raise HostedAuthorityWireError(
            "canonical hosted authority operations contract is invalid YAML"
        ) from error
    if not isinstance(document, dict):
        raise HostedAuthorityWireError(
            "canonical hosted authority operations contract must be one object"
        )
    if any(not isinstance(key, str) for key in document):
        raise HostedAuthorityWireError(
            "canonical hosted authority operations contract keys must be strings"
        )
    keys = set(document)
    if keys != _DOCUMENT_KEYS:
        raise HostedAuthorityWireError(
            "canonical hosted authority operations contract has an invalid schema"
        )
    if not isinstance(document["description"], str) or not document["description"].strip():
        raise HostedAuthorityWireError(
            "canonical hosted authority operations contract has an invalid description"
        )
    contract_test = document["contract_test"]
    if not isinstance(contract_test, dict) or set(contract_test) != _CONTRACT_TEST_KEYS:
        raise HostedAuthorityWireError(
            "canonical hosted authority operations contract has an invalid contract_test"
        )
    coverage = contract_test["coverage_requirements"]
    if not isinstance(coverage, list) or any(
        not isinstance(requirement, str) or not requirement.strip()
        for requirement in coverage
    ):
        raise HostedAuthorityWireError(
            "canonical hosted authority contract_test coverage must be a string list"
        )
    return document


def _read_canonical_source(path: Path) -> bytes:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if not nofollow:
        raise HostedAuthorityWireError(
            "canonical hosted authority operations contract requires no-follow file support"
        )
    flags = (
        os.O_RDONLY
        | nofollow
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        before = path.lstat()
        descriptor = os.open(path, flags)
    except OSError as error:
        raise HostedAuthorityWireError(
            "canonical hosted authority operations contract is unavailable"
        ) from error
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or not stat.S_ISREG(opened.st_mode)
            or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
        ):
            raise HostedAuthorityWireError(
                "canonical hosted authority operations contract must be a regular non-symlink file"
            )
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    try:
        current = path.lstat()
    except OSError as error:
        raise HostedAuthorityWireError(
            "canonical hosted authority operations contract was replaced while being read"
        ) from error
    opened_identity = (
        opened.st_dev,
        opened.st_ino,
        opened.st_mode,
        opened.st_size,
        opened.st_mtime_ns,
        opened.st_ctime_ns,
    )
    if (
        opened_identity
        != (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        or opened_identity
        != (
            current.st_dev,
            current.st_ino,
            current.st_mode,
            current.st_size,
            current.st_mtime_ns,
            current.st_ctime_ns,
        )
        or sum(map(len, chunks)) != opened.st_size
    ):
        raise HostedAuthorityWireError(
            "canonical hosted authority operations contract changed while being read"
        )
    return b"".join(chunks)


def _route_index(document: dict[str, object]) -> dict[str, tuple[str, str]]:
    routes_value = document["api_routes"]
    if not isinstance(routes_value, list) or not routes_value:
        raise HostedAuthorityWireError(
            "canonical hosted authority operations contract has invalid api_routes"
        )
    routes: dict[str, tuple[str, str]] = {}
    for index, value in enumerate(routes_value):
        if not isinstance(value, dict):
            raise HostedAuthorityWireError(f"canonical api_routes[{index}] must be an object")
        if any(not isinstance(key, str) for key in value):
            raise HostedAuthorityWireError(f"canonical api_routes[{index}] keys must be strings")
        keys = set(value)
        if not _ROUTE_REQUIRED_KEYS <= keys or not keys <= _ROUTE_KEYS:
            raise HostedAuthorityWireError(f"canonical api_routes[{index}] has an invalid schema")
        method = value["method"]
        route_path = value["path"]
        operation = value["operation"]
        if not all(isinstance(item, str) and item for item in (method, route_path, operation)):
            raise HostedAuthorityWireError(
                f"canonical api_routes[{index}] method, path, and operation must be strings"
            )
        if not isinstance(value["actor"], str) or not value["actor"]:
            raise HostedAuthorityWireError(f"canonical api_routes[{index}].actor must be a string")
        for key in (
            "security",
            "authorization",
            "reliability",
            "privacy",
            "telemetry",
            "slo",
            "commercial",
            "application",
        ):
            if not isinstance(value[key], dict):
                raise HostedAuthorityWireError(
                    f"canonical api_routes[{index}].{key} must be an object"
                )
        if not isinstance(value["error_codes"], list) or any(
            not isinstance(code, str) or not code for code in value["error_codes"]
        ):
            raise HostedAuthorityWireError(
                f"canonical api_routes[{index}].error_codes must be a string list"
            )
        for key in ("request_entity", "request_body_kind", "response_entity", "response_body_kind"):
            if key in value and (not isinstance(value[key], str) or not value[key]):
                raise HostedAuthorityWireError(
                    f"canonical api_routes[{index}].{key} must be a string"
                )
        if "request_bindings" in value and not isinstance(value["request_bindings"], dict):
            raise HostedAuthorityWireError(
                f"canonical api_routes[{index}].request_bindings must be an object"
            )
        if operation in routes:
            raise HostedAuthorityWireError(f"canonical operation {operation} is ambiguous")
        routes[operation] = (method, route_path)
    return routes


def _single(routes: dict[str, tuple[str, str]], operation: str) -> tuple[str, str] | None:
    return routes.get(operation)


def _decision_path(route: tuple[str, str], *, operation: str, method: str, suffix: str) -> str:
    actual_method, path = route
    if actual_method != method:
        raise HostedAuthorityWireError(f"canonical operation {operation} must use {method}")
    if not path.startswith("/control-plane/platform/human-authority/receipts/"):
        raise HostedAuthorityWireError(
            f"canonical operation {operation} has an invalid authority path"
        )
    expected_path = "/control-plane/platform/human-authority/receipts/{decisionId}" + suffix
    if path != expected_path:
        raise HostedAuthorityWireError(
            f"canonical operation {operation} must use the exact decisionId authority path"
        )
    return path


def load_hosted_authority_wire(repo_root: Path) -> HostedAuthorityWire:
    """Load route templates from the sole backend authoring source."""
    path = (repo_root / CANONICAL_OPERATIONS_RELATIVE_PATH).absolute()
    raw = _read_canonical_source(path)
    document = _strict_document(raw)
    routes = _route_index(document)
    consume = _single(routes, _CONSUME_OPERATION)
    revoke = _single(routes, _REVOKE_OPERATION)
    if consume is None or revoke is None:
        raise HostedAuthorityWireError("canonical hosted authority command routes are incomplete")
    query = _single(routes, _QUERY_OPERATION)
    return HostedAuthorityWire(
        source_path=path,
        source_sha256="sha256:" + hashlib.sha256(raw).hexdigest(),
        query_path_template=(
            _decision_path(query, operation=_QUERY_OPERATION, method="GET", suffix="")
            if query is not None
            else None
        ),
        consume_path_template=_decision_path(
            consume, operation=_CONSUME_OPERATION, method="POST", suffix=":consume"
        ),
        revoke_path_template=_decision_path(
            revoke, operation=_REVOKE_OPERATION, method="POST", suffix=":revoke"
        ),
    )
