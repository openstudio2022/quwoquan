"""Canonical ``ReadinessCaseResult`` validation and create-once JSON storage.

This module intentionally owns no readiness-case selection. Producers must
bring an already resolved object/spec/case/execution slot and this library only
enforces the metadata wire plus exact-byte, create-once persistence.
"""

from __future__ import annotations

import json
import os
import stat
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

try:
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError:  # stackctl's minimal runtime uses the strict stdlib fallback below
    Draft202012Validator = None  # type: ignore[assignment]
    FormatChecker = None  # type: ignore[assignment]


ROOT = Path(__file__).resolve().parents[3]
READINESS_RESULT_BUNDLE_SCHEMA = (
    ROOT
    / "quwoquan_service/contracts/metadata/_schemas/readiness_result_bundle.schema.json"
)


class ReadinessCaseResultError(ValueError):
    """A canonical result is invalid or conflicts with create-once storage."""


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    """Return deterministic JSON bytes for one canonical document."""

    try:
        return json.dumps(
            dict(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ReadinessCaseResultError(f"canonical JSON encoding failed: {exc}") from exc


def _load_schema() -> dict[str, Any]:
    try:
        value = json.loads(READINESS_RESULT_BUNDLE_SCHEMA.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReadinessCaseResultError(
            f"canonical readiness schema is unavailable: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise ReadinessCaseResultError("canonical readiness schema root is invalid")
    return value


def _resolve_ref(root: Mapping[str, Any], reference: str) -> Mapping[str, Any]:
    if not reference.startswith("#/"):
        raise ReadinessCaseResultError(f"unsupported readiness schema ref: {reference}")
    value: object = root
    for part in reference[2:].split("/"):
        if not isinstance(value, Mapping) or part not in value:
            raise ReadinessCaseResultError(f"unresolved readiness schema ref: {reference}")
        value = value[part]
    if not isinstance(value, Mapping):
        raise ReadinessCaseResultError(f"invalid readiness schema ref: {reference}")
    return value


def _fallback_validate(
    instance: object,
    schema: Mapping[str, Any],
    *,
    root: Mapping[str, Any],
    location: str,
) -> None:
    reference = schema.get("$ref")
    if isinstance(reference, str):
        _fallback_validate(
            instance, _resolve_ref(root, reference), root=root, location=location
        )
        return
    expected_type = schema.get("type")
    type_matches = {
        "object": isinstance(instance, Mapping),
        "array": isinstance(instance, list),
        "string": isinstance(instance, str),
        "boolean": isinstance(instance, bool),
        "integer": isinstance(instance, int) and not isinstance(instance, bool),
        "number": isinstance(instance, (int, float)) and not isinstance(instance, bool),
    }
    if isinstance(expected_type, str) and not type_matches.get(expected_type, False):
        raise ReadinessCaseResultError(
            f"ReadinessResultBundle schema violation at {location}: expected {expected_type}"
        )
    if "const" in schema and instance != schema["const"]:
        raise ReadinessCaseResultError(
            f"ReadinessResultBundle schema violation at {location}: const mismatch"
        )
    enum = schema.get("enum")
    if isinstance(enum, list) and instance not in enum:
        raise ReadinessCaseResultError(
            f"ReadinessResultBundle schema violation at {location}: value is outside enum"
        )
    if isinstance(instance, str):
        minimum = schema.get("minLength")
        maximum = schema.get("maxLength")
        pattern = schema.get("pattern")
        if isinstance(minimum, int) and len(instance) < minimum:
            raise ReadinessCaseResultError(
                f"ReadinessResultBundle schema violation at {location}: string is too short"
            )
        if isinstance(maximum, int) and len(instance) > maximum:
            raise ReadinessCaseResultError(
                f"ReadinessResultBundle schema violation at {location}: string is too long"
            )
        if isinstance(pattern, str) and __import__("re").search(pattern, instance) is None:
            raise ReadinessCaseResultError(
                f"ReadinessResultBundle schema violation at {location}: pattern mismatch"
            )
        if schema.get("format") == "date-time":
            normalized = instance[:-1] + "+00:00" if instance.endswith("Z") else instance
            try:
                parsed = __import__("datetime").datetime.fromisoformat(normalized)
            except ValueError as exc:
                raise ReadinessCaseResultError(
                    f"ReadinessResultBundle schema violation at {location}: invalid date-time"
                ) from exc
            if parsed.tzinfo is None:
                raise ReadinessCaseResultError(
                    f"ReadinessResultBundle schema violation at {location}: date-time lacks timezone"
                )
    if isinstance(instance, Mapping):
        required = schema.get("required")
        if isinstance(required, list):
            missing = [field for field in required if field not in instance]
            if missing:
                raise ReadinessCaseResultError(
                    f"ReadinessResultBundle schema violation at {location}: missing {missing}"
                )
        properties = schema.get("properties")
        if isinstance(properties, Mapping):
            if schema.get("additionalProperties") is False:
                unknown = sorted(set(instance) - set(properties))
                if unknown:
                    raise ReadinessCaseResultError(
                        f"ReadinessResultBundle schema violation at {location}: unknown {unknown}"
                    )
            for key, child in properties.items():
                if key in instance and isinstance(child, Mapping):
                    _fallback_validate(
                        instance[key], child, root=root, location=f"{location}.{key}"
                    )
    if isinstance(instance, list) and isinstance(schema.get("items"), Mapping):
        for index, item in enumerate(instance):
            _fallback_validate(
                item, schema["items"], root=root, location=f"{location}.{index}"
            )
    for child in schema.get("allOf", []):
        if isinstance(child, Mapping):
            _fallback_validate(instance, child, root=root, location=location)
    condition = schema.get("if")
    if isinstance(condition, Mapping):
        try:
            _fallback_validate(instance, condition, root=root, location=location)
        except ReadinessCaseResultError:
            branch = schema.get("else")
        else:
            branch = schema.get("then")
        if isinstance(branch, Mapping):
            _fallback_validate(instance, branch, root=root, location=location)
    forbidden = schema.get("not")
    if isinstance(forbidden, Mapping):
        try:
            _fallback_validate(instance, forbidden, root=root, location=location)
        except ReadinessCaseResultError:
            pass
        else:
            raise ReadinessCaseResultError(
                f"ReadinessResultBundle schema violation at {location}: forbidden shape"
            )
    alternatives = schema.get("oneOf")
    if isinstance(alternatives, list):
        matches = 0
        for alternative in alternatives:
            if not isinstance(alternative, Mapping):
                continue
            try:
                _fallback_validate(instance, alternative, root=root, location=location)
            except ReadinessCaseResultError:
                continue
            matches += 1
        if matches != 1:
            raise ReadinessCaseResultError(
                f"ReadinessResultBundle schema violation at {location}: oneOf matched {matches}"
            )


def validate_readiness_result_bundle(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one strict canonical bundle with the metadata JSON schema."""

    if not isinstance(value, Mapping):
        raise ReadinessCaseResultError("ReadinessResultBundle must be an object")
    normalized = dict(value)
    schema = _load_schema()
    if Draft202012Validator is not None and FormatChecker is not None:
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        errors = sorted(validator.iter_errors(normalized), key=lambda item: list(item.path))
        if errors:
            first = errors[0]
            location = ".".join(str(part) for part in first.absolute_path) or "$"
            raise ReadinessCaseResultError(
                f"ReadinessResultBundle schema violation at {location}: {first.message}"
            )
    else:
        _fallback_validate(normalized, schema, root=schema, location="$")
    return normalized


def validate_readiness_case_result(
    value: Mapping[str, Any], *, generated_at: str
) -> dict[str, Any]:
    """Validate one raw result through the canonical bundle item authority."""

    if not isinstance(value, Mapping):
        raise ReadinessCaseResultError("ReadinessCaseResult must be an object")
    normalized = dict(value)
    validate_readiness_result_bundle(
        {"generatedAt": generated_at, "results": [normalized]}
    )
    return normalized


def build_readiness_result_bundle(
    results: Sequence[Mapping[str, Any]], *, generated_at: str
) -> dict[str, Any]:
    """Build a canonical bundle without inventing an aggregate verdict."""

    bundle = {
        "generatedAt": generated_at,
        "results": [dict(result) for result in results],
    }
    return validate_readiness_result_bundle(bundle)


def _read_existing_regular(path: Path) -> bytes:
    try:
        before = path.lstat()
    except OSError as exc:
        raise ReadinessCaseResultError(
            "create-once destination is unavailable"
        ) from exc
    if path.is_symlink() or not stat.S_ISREG(before.st_mode):
        raise ReadinessCaseResultError(
            "create-once destination is not a regular non-symlink file"
        )
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        try:
            chunks: list[bytes] = []
            while True:
                chunk = os.read(descriptor, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise ReadinessCaseResultError(
            "create-once destination cannot be read safely"
        ) from exc
    encoded = b"".join(chunks)
    if (
        after.st_dev != before.st_dev
        or after.st_ino != before.st_ino
        or after.st_size != before.st_size
        or after.st_mtime_ns != before.st_mtime_ns
        or len(encoded) != before.st_size
    ):
        raise ReadinessCaseResultError(
            "create-once destination changed during read"
        )
    return encoded


def _ensure_physical_parent(path: Path) -> None:
    parent = path.parent
    missing: list[Path] = []
    current = parent
    while not current.exists() and not current.is_symlink():
        missing.append(current)
        if current.parent == current:
            break
        current = current.parent
    if current.is_symlink() or not current.is_dir():
        raise ReadinessCaseResultError(
            "create-once destination parent is missing, symlinked, or unsafe"
        )
    for directory in reversed(missing):
        try:
            directory.mkdir()
        except FileExistsError:
            pass
        if directory.is_symlink() or not directory.is_dir():
            raise ReadinessCaseResultError(
                "create-once destination parent became unsafe"
            )
    current = parent
    while current != current.parent:
        if current.is_symlink():
            raise ReadinessCaseResultError(
                "create-once destination cannot traverse a symlink"
            )
        current = current.parent


def write_create_once_json(path: Path, value: Mapping[str, Any]) -> Path:
    """Create canonical bytes once; only exact-byte replay is idempotent."""

    destination = Path(os.path.abspath(path.expanduser()))
    encoded = canonical_json_bytes(value)
    _ensure_physical_parent(destination)
    if destination.exists() or destination.is_symlink():
        if _read_existing_regular(destination) == encoded:
            return destination
        raise ReadinessCaseResultError(
            "create-once destination already contains different bytes"
        )

    descriptor: int | None = None
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
        )
        temporary = Path(temporary_name)
        os.fchmod(descriptor, 0o644)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, destination, follow_symlinks=False)
        except FileExistsError:
            if _read_existing_regular(destination) == encoded:
                return destination
            raise ReadinessCaseResultError(
                "create-once destination concurrently received different bytes"
            )
        directory_fd = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination


__all__ = [
    "READINESS_RESULT_BUNDLE_SCHEMA",
    "ReadinessCaseResultError",
    "build_readiness_result_bundle",
    "canonical_json_bytes",
    "validate_readiness_case_result",
    "validate_readiness_result_bundle",
    "write_create_once_json",
]
