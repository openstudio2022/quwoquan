"""App launch metadata 的通用 schema、格式与 transport 值校验。"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import re
from typing import Any
from urllib.parse import urlparse


def is_digest_identity(value: object, contract: dict[str, Any]) -> bool:
    if not isinstance(value, str):
        return False
    algorithm = str(contract["digest_contract"]["algorithm"])
    digest_size = hashlib.new(algorithm).digest_size * 2
    return (
        re.fullmatch(
            rf"{re.escape(algorithm)}:[0-9a-f]{{{digest_size}}}", value
        )
        is not None
    )


def parse_rfc3339_utc(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.endswith("Z"):
        return None
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return None
    if parsed.tzinfo != timezone.utc:
        return None
    return parsed


def validate_schema_document(
    document: object,
    schema_name: str,
    *,
    contract: dict[str, Any],
    field_path: str,
) -> list[str]:
    if not isinstance(document, dict):
        return [f"{field_path} must be object"]
    schema = contract["schemas"][schema_name]
    fields = schema["fields"]
    issues: list[str] = []
    for field in schema["required_fields"]:
        if field not in document:
            issues.append(f"{field_path}.{field} is required")
    if not schema["additional_fields"]:
        for field in sorted(set(document) - set(fields)):
            issues.append(f"{field_path}.{field} is not declared by metadata")
    for field, value in document.items():
        field_contract = fields.get(field)
        if not isinstance(field_contract, dict):
            continue
        issues.extend(
            _validate_schema_value(
                value,
                field_contract,
                field_path=f"{field_path}.{field}",
                contract=contract,
            )
        )
    return issues


def canonical_ports(raw: str) -> str:
    values: set[int] = set()
    for value in raw.split(","):
        normalized = value.strip()
        if not normalized:
            continue
        if not normalized.isdigit() or int(normalized) <= 0 or int(normalized) > 65535:
            raise ValueError(f"invalid Android reverse port: {normalized}")
        values.add(int(normalized))
    if not values:
        raise ValueError("Android reverse ports are empty")
    return ",".join(str(value) for value in sorted(values))


def _validate_schema_value(
    value: object,
    field_contract: dict[str, Any],
    *,
    field_path: str,
    contract: dict[str, Any],
) -> list[str]:
    issues: list[str] = []
    expected_type = field_contract.get("type")
    type_matches = {
        "string": isinstance(value, str),
        "boolean": isinstance(value, bool),
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
    }.get(str(expected_type), False)
    if not type_matches:
        return [f"{field_path} must be {expected_type}"]
    if "const" in field_contract and value != field_contract["const"]:
        issues.append(f"{field_path} must equal {field_contract['const']}")
    allowed_values = field_contract.get("allowed_values")
    if isinstance(allowed_values, list) and value not in allowed_values:
        issues.append(f"{field_path} is not an allowed value")
    minimum_length = field_contract.get("min_length")
    if (
        isinstance(minimum_length, int)
        and isinstance(value, str)
        and len(value) < minimum_length
    ):
        issues.append(f"{field_path} is shorter than {minimum_length}")
    format_name = field_contract.get("format")
    if format_name == "sha256_identity" and not is_digest_identity(value, contract):
        issues.append(f"{field_path} must be a canonical digest identity")
    elif format_name == "optional_sha256_identity" and (
        value != "" and not is_digest_identity(value, contract)
    ):
        issues.append(f"{field_path} must be empty or a canonical digest identity")
    elif format_name == "git_object_sha" and (
        not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{40}", value) is None
    ):
        issues.append(f"{field_path} must be a lowercase 40-character Git SHA")
    elif format_name == "git_tree_digest" and (
        not isinstance(value, str)
        or re.fullmatch(r"(?:sha1:[0-9a-f]{40}|sha256:[0-9a-f]{64})", value)
        is None
    ):
        issues.append(f"{field_path} must be an immutable source tree digest")
    elif format_name == "rfc3339_utc" and parse_rfc3339_utc(value) is None:
        issues.append(f"{field_path} must be canonical RFC3339 UTC")
    elif format_name == "strict_base64_ed25519_signature":
        try:
            decoded_signature = base64.b64decode(str(value), validate=True)
        except ValueError:
            decoded_signature = b""
        if len(decoded_signature) != 64 or base64.b64encode(
            decoded_signature
        ).decode("ascii") != value:
            issues.append(f"{field_path} must be a canonical Ed25519 signature")
    elif format_name in {
        "https_origin",
        "https_url_no_query_fragment_credentials",
    } and not _validate_url_format(value, str(format_name)):
        issues.append(f"{field_path} must satisfy {format_name}")
    elif format_name not in {
        None,
        "sha256_identity",
        "optional_sha256_identity",
        "git_object_sha",
        "git_tree_digest",
        "rfc3339_utc",
        "strict_base64_ed25519_signature",
        "https_origin",
        "https_url_no_query_fragment_credentials",
    }:
        issues.append(f"{field_path} uses unsupported format {format_name}")
    value_type = field_contract.get("value_type")
    if value_type == "string" and isinstance(value, dict):
        if any(
            not isinstance(key, str) or not isinstance(item, str)
            for key, item in value.items()
        ):
            issues.append(f"{field_path} must contain string-only keys and values")
    nested_fields = field_contract.get("fields")
    if isinstance(nested_fields, dict) and isinstance(value, dict):
        nested_required = field_contract.get("required_fields", [])
        if not isinstance(nested_required, list):
            issues.append(f"metadata for {field_path} has invalid required_fields")
        else:
            for field in nested_required:
                if field not in value:
                    issues.append(f"{field_path}.{field} is required")
        if field_contract.get("additional_fields") is False:
            for field in sorted(set(value) - set(nested_fields)):
                issues.append(f"{field_path}.{field} is not declared by metadata")
        for field, nested_value in value.items():
            nested_contract = nested_fields.get(field)
            if isinstance(nested_contract, dict):
                issues.extend(
                    _validate_schema_value(
                        nested_value,
                        nested_contract,
                        field_path=f"{field_path}.{field}",
                        contract=contract,
                    )
                )
    item_contract = field_contract.get("items")
    if isinstance(item_contract, dict) and isinstance(value, list):
        for index, item in enumerate(value):
            issues.extend(
                _validate_schema_value(
                    item,
                    item_contract,
                    field_path=f"{field_path}[{index}]",
                    contract=contract,
                )
            )
    schema_ref = field_contract.get("schema_ref")
    if isinstance(schema_ref, str) and isinstance(value, dict):
        issues.extend(
            validate_schema_document(
                value,
                schema_ref,
                contract=contract,
                field_path=field_path,
            )
        )
    return issues


def _validate_url_format(value: object, format_name: str) -> bool:
    if not isinstance(value, str) or not value or value.strip() != value:
        return False
    parsed = urlparse(value)
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        return False
    if format_name == "https_origin":
        return parsed.path in {"", "/"} and not parsed.params
    if format_name == "https_url_no_query_fragment_credentials":
        return not parsed.params
    return False
