"""Build a diagnostic, read-only projection over canonical App UAT evidence.

The projection binds exact plan, TargetUatBinding, and raw ReadinessCaseResult
bytes.  Business completeness gaps remain visible in ``coverage`` and ``issues``;
this module never writes any canonical input or acceptance fact.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlparse

from quwoquan_ops.cli.lib.target_uat_binding import validate_target_uat_binding

SCHEMA_PATH = (
    Path(__file__).absolute().parents[2]
    / "environments"
    / "evidence"
    / "app_uat_result_bundle.schema.json"
)
APP_UAT_RESULT_BUNDLE_SCHEMA = "quwoquan_ops.app_uat_result_bundle.v1"
SCHEMA = APP_UAT_RESULT_BUNDLE_SCHEMA
_ENTRIES = ("feed", "search", "recommendation", "direct_or_object_route")
_CARRIERS = ("homepage", "article", "image", "video")
_RAW_STATUSES = frozenset({"passed", "failed", "blocked", "skipped"})
_NON_PASSED = frozenset({"failed", "blocked", "skipped"})
_UAT_PROFILES = frozenset({"rehearsal", "promotable", "production"})
_DIGEST_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
_IDENTITY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_REF_SEGMENT_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_FORBIDDEN_KEYS = frozenset({
    "status", "verdict", "passed", "promotable", "promotionAuthority", "authority",
})
SlotKey = tuple[str, str, str, str, str, str, str, str, str, str]


class AppUatResultBundleError(ValueError):
    """Typed failure for malformed or unsafe projection inputs."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code


_INVALID = "OPS.APP_UAT_RESULT_BUNDLE.invalid"
_PATH_INVALID = "OPS.APP_UAT_RESULT_BUNDLE.path_invalid"
_DIGEST_DRIFT = "OPS.APP_UAT_RESULT_BUNDLE.digest_drift"


def _fail(code: str, detail: str) -> None:
    raise AppUatResultBundleError(code, detail)


def _text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        _fail(_INVALID, f"{field} must be a non-empty canonical string")
    return value


def _identity(value: object, *, field: str) -> str:
    text = _text(value, field=field)
    if _IDENTITY_RE.fullmatch(text) is None:
        _fail(_INVALID, f"{field} has invalid identity format")
    return text


def _digest(value: object, *, field: str) -> str:
    text = _text(value, field=field)
    if _DIGEST_RE.fullmatch(text) is None:
        _fail(_INVALID, f"{field} must be sha256:<64 lowercase hex>")
    return text


def _date_time(value: object, *, field: str) -> str:
    text = _text(value, field=field)
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as error:
        raise AppUatResultBundleError(_INVALID, f"{field} is not RFC3339") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail(_INVALID, f"{field} must include a UTC offset")
    return text


def _relative_ref(value: object, *, field: str) -> str:
    text = _text(value, field=field)
    path = PurePosixPath(text)
    if (
        len(text) > 512
        or text.startswith("/")
        or "\\" in text
        or path.as_posix() != text
        or any(part in {"", ".", ".."} or _REF_SEGMENT_RE.fullmatch(part) is None for part in path.parts)
    ):
        _fail(_PATH_INVALID, f"{field} must be a contained relative reference")
    return text


def _exact_digest(encoded: bytes) -> str:
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _decode_object(encoded: bytes, *, label: str) -> dict[str, Any]:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                _fail(_INVALID, f"{label} has duplicate JSON key {key!r}")
            result[key] = value
        return result

    try:
        text = encoded.decode("utf-8")
        decoder = json.JSONDecoder(
            object_pairs_hook=unique,
            parse_constant=lambda value: (_ for _ in ()).throw(
                AppUatResultBundleError(_INVALID, f"{label} has invalid JSON constant {value}")
            ),
        )
        document, end = decoder.raw_decode(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AppUatResultBundleError(_INVALID, f"{label} is not UTF-8 JSON") from error
    if text[end:].strip():
        _fail(_INVALID, f"{label} has trailing JSON content")
    if not isinstance(document, dict):
        _fail(_INVALID, f"{label} must contain one object")
    return document


def _root(root: Path) -> Path:
    candidate = root.expanduser().absolute()
    try:
        metadata = candidate.lstat()
    except OSError as error:
        raise AppUatResultBundleError(_PATH_INVALID, "evidence root is unavailable") from error
    if candidate.is_symlink() or not stat.S_ISDIR(metadata.st_mode) or candidate.resolve(strict=True) != candidate:
        _fail(_PATH_INVALID, "evidence root must be a real non-symlink directory")
    return candidate


def _secure_read(root: Path, ref: str, *, label: str) -> bytes:
    root = _root(root)
    reference = PurePosixPath(_relative_ref(ref, field=f"{label}.ref"))
    parent = root
    for part in reference.parts[:-1]:
        parent /= part
        try:
            metadata = parent.lstat()
        except OSError as error:
            raise AppUatResultBundleError(_PATH_INVALID, f"{label} parent is unavailable") from error
        if parent.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
            _fail(_PATH_INVALID, f"{label} path contains a symlink or non-directory")
    path = parent / reference.name
    try:
        before = path.lstat()
    except OSError as error:
        raise AppUatResultBundleError(_PATH_INVALID, f"{label} is unavailable") from error
    if path.is_symlink() or not stat.S_ISREG(before.st_mode):
        _fail(_PATH_INVALID, f"{label} must be a regular non-symlink file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise AppUatResultBundleError(_PATH_INVALID, f"{label} cannot be read safely") from error
    try:
        opened = os.fstat(descriptor)
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if (
        (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        != (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
        or (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    ):
        _fail(_PATH_INVALID, f"{label} changed during read")
    return b"".join(chunks)


def _source(source: Mapping[str, Any], *, label: str) -> tuple[str, str]:
    if not isinstance(source, Mapping) or set(source) != {"ref", "digest"}:
        _fail(_INVALID, f"{label} must contain exactly ref and digest")
    return _relative_ref(source["ref"], field=f"{label}.ref"), _digest(source["digest"], field=f"{label}.digest")


def _read_source(root: Path, source: Mapping[str, Any], *, label: str) -> tuple[str, str, dict[str, Any]]:
    ref, digest = _source(source, label=label)
    encoded = _secure_read(root, ref, label=label)
    if _exact_digest(encoded) != digest:
        _fail(_DIGEST_DRIFT, f"{label} exact bytes drifted")
    return ref, digest, _decode_object(encoded, label=label)


def _load_schema(path: Path) -> dict[str, Any]:
    try:
        return _decode_object(path.read_bytes(), label=f"schema {path}")
    except OSError as error:
        raise AppUatResultBundleError(_INVALID, f"schema unavailable: {path}") from error


def _schema_refs(value: object) -> list[str]:
    refs: list[str] = []
    if isinstance(value, Mapping):
        ref = value.get("$ref")
        if isinstance(ref, str):
            refs.append(ref)
        for child in value.values():
            refs.extend(_schema_refs(child))
    elif isinstance(value, list):
        for child in value:
            refs.extend(_schema_refs(child))
    return refs


def _local_schema_registry(schema_path: Path) -> tuple[dict[str, Any], Any]:
    from referencing import Registry, Resource

    root_path = schema_path.resolve(strict=True)
    schema_root = root_path.parent
    pending = [root_path]
    loaded: dict[str, dict[str, Any]] = {}
    while pending:
        current_path = pending.pop()
        current_uri = current_path.as_uri()
        if current_uri in loaded:
            continue
        current_schema = _load_schema(current_path)
        current_schema["$id"] = current_uri
        loaded[current_uri] = current_schema
        for ref in _schema_refs(current_schema):
            if ref.startswith("#"):
                continue
            parsed = urlparse(ref)
            if parsed.scheme or parsed.netloc or parsed.path.startswith("/"):
                _fail(_INVALID, f"schema {current_path} has non-local $ref {ref!r}")
            try:
                target = (current_path.parent / unquote(parsed.path)).resolve(strict=True)
                target.relative_to(schema_root)
            except (OSError, ValueError) as error:
                raise AppUatResultBundleError(
                    _INVALID, f"schema {current_path} has unavailable or escaped $ref {ref!r}"
                ) from error
            pending.append(target)

    registry = Registry()
    for uri, schema in loaded.items():
        registry = registry.with_resource(uri, Resource.from_contents(schema))
    return loaded[root_path.as_uri()], registry


def _jsonschema_validate(document: Mapping[str, Any], schema_path: Path, *, label: str) -> None:
    try:
        from jsonschema import Draft202012Validator, FormatChecker
        import referencing  # noqa: F401
    except ImportError:
        return
    schema, registry = _local_schema_registry(schema_path)
    errors = sorted(
        Draft202012Validator(
            schema, format_checker=FormatChecker(), registry=registry
        ).iter_errors(document),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        error = errors[0]
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        _fail(_INVALID, f"{label} schema invalid at {location}: {error.message}")


def _plan_samples(plan: Mapping[str, Any]) -> list[dict[str, str]]:
    raw_samples = plan.get("samples")
    if not isinstance(raw_samples, list) or not raw_samples:
        _fail(_INVALID, "sample plan samples must be non-empty")
    samples: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    seen_object_ids: set[str] = set()
    seen_object_refs: set[str] = set()
    for index, raw in enumerate(raw_samples):
        if not isinstance(raw, Mapping) or set(raw) != {
            "sampleId", "carrier", "objectId", "objectRef", "objectDigest",
        }:
            _fail(_INVALID, f"samplePlan.samples[{index}] fields are invalid")
        sample_id = _identity(raw.get("sampleId"), field=f"samplePlan.samples[{index}].sampleId")
        carrier = _text(raw.get("carrier"), field=f"samplePlan.samples[{index}].carrier")
        object_id = _text(raw.get("objectId"), field=f"samplePlan.samples[{index}].objectId")
        object_ref = _relative_ref(raw.get("objectRef"), field=f"samplePlan.samples[{index}].objectRef")
        object_digest = _digest(raw.get("objectDigest"), field=f"samplePlan.samples[{index}].objectDigest")
        if (
            carrier not in _CARRIERS
            or sample_id in seen_ids
            or object_id in seen_object_ids
            or object_ref in seen_object_refs
        ):
            _fail(_INVALID, "sample plan sample/object id or ref is duplicated")
        expected_prefix = "objects/entities/" if carrier == "homepage" else f"objects/posts/{carrier}/"
        if not object_ref.startswith(expected_prefix):
            _fail(_INVALID, f"samplePlan.samples[{index}].objectRef is not carrier-bound")
        seen_ids.add(sample_id)
        seen_object_ids.add(object_id)
        seen_object_refs.add(object_ref)
        samples.append({
            "sampleId": sample_id,
            "carrier": carrier,
            "objectId": object_id,
            "objectRef": object_ref,
            "objectDigest": object_digest,
        })
    if plan.get("sampleCount") != len(samples):
        _fail(_INVALID, "sample plan sampleCount drifted")
    return sorted(samples, key=lambda sample: sample["sampleId"])


def _plan_cells(plan: Mapping[str, Any]) -> list[dict[str, str]]:
    if plan.get("schema") != "quwoquan_data.release_uat_sample_plan":
        _fail(_INVALID, "sample plan schema is invalid")
    _identity(plan.get("releaseId"), field="samplePlan.releaseId")
    _digest(plan.get("releaseDigest"), field="samplePlan.releaseDigest")
    matrix = plan.get("entryCarrierCells")
    if not isinstance(matrix, list) or len(matrix) != 16:
        _fail(_INVALID, "sample plan must contain exactly 16 entryCarrierCells")
    cells: list[dict[str, str]] = []
    observed: set[tuple[str, str]] = set()
    for index, raw_cell in enumerate(matrix):
        if not isinstance(raw_cell, Mapping):
            _fail(_INVALID, f"entryCarrierCells[{index}] is invalid")
        allowed = {"entry", "carrier", "applicability", "specRef", "runnerClass", "reasonCode"}
        if not set(raw_cell).issubset(allowed):
            _fail(_INVALID, f"entryCarrierCells[{index}] has unknown fields")
        entry = _text(raw_cell.get("entry"), field=f"entryCarrierCells[{index}].entry")
        carrier = _text(raw_cell.get("carrier"), field=f"entryCarrierCells[{index}].carrier")
        if entry not in _ENTRIES or carrier not in _CARRIERS or (entry, carrier) in observed:
            _fail(_INVALID, "sample plan matrix axes are duplicated or unknown")
        observed.add((entry, carrier))
        applicability = _text(raw_cell.get("applicability"), field=f"entryCarrierCells[{index}].applicability")
        if applicability == "required":
            if "reasonCode" in raw_cell:
                _fail(_INVALID, "required matrix cell cannot contain reasonCode")
            cells.append({
                "entry": entry,
                "carrier": carrier,
                "applicability": applicability,
                "specRef": _text(raw_cell.get("specRef"), field=f"entryCarrierCells[{index}].specRef"),
                "runner": _identity(raw_cell.get("runnerClass"), field=f"entryCarrierCells[{index}].runnerClass"),
            })
        elif applicability == "not_applicable":
            if "specRef" in raw_cell or "runnerClass" in raw_cell:
                _fail(_INVALID, "not_applicable matrix cell cannot contain specRef or runnerClass")
            cells.append({
                "entry": entry,
                "carrier": carrier,
                "applicability": applicability,
                "reason": _text(raw_cell.get("reasonCode"), field=f"entryCarrierCells[{index}].reasonCode"),
            })
        else:
            _fail(_INVALID, "matrix cell applicability is unknown")
    if observed != {(entry, carrier) for entry in _ENTRIES for carrier in _CARRIERS}:
        _fail(_INVALID, "sample plan must contain the complete 16-cell matrix")
    return sorted(cells, key=lambda cell: (_ENTRIES.index(cell["entry"]), _CARRIERS.index(cell["carrier"])))


def _binding_profile(binding: Mapping[str, Any]) -> str:
    profile = _text(binding.get("profile"), field="binding.profile")
    if profile not in _UAT_PROFILES:
        _fail(_INVALID, "binding profile is unknown")
    return profile


def _binding_provider(binding: Mapping[str, Any]) -> str:
    provider = binding.get("provider")
    if not isinstance(provider, Mapping):
        _fail(_INVALID, "binding.provider must be the strict nested provider object")
    return _identity(provider.get("identity"), field="binding.provider.identity")


def _binding_device(binding: Mapping[str, Any]) -> str:
    device = binding.get("device")
    if not isinstance(device, Mapping):
        _fail(_INVALID, "binding.device must be the strict nested device object")
    return _identity(device.get("identity"), field="binding.device.identity")


def _slot_key(
    *, target: str, platform: str, provider: str, device: str, profile: str,
    object_id: str, entry: str, carrier: str, spec_ref: str, runner: str,
) -> SlotKey:
    return (
        target, platform, provider, device, profile, object_id,
        entry, carrier, spec_ref, runner,
    )


def _slot_id(key: SlotKey) -> str:
    encoded = json.dumps(key, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return "slot-" + hashlib.sha256(encoded).hexdigest()[:24]


def _identity_fields(key: SlotKey) -> dict[str, str]:
    return {
        "slotId": _slot_id(key), "target": key[0], "platform": key[1], "provider": key[2],
        "device": key[3], "profile": key[4], "objectId": key[5],
        "entry": key[6], "carrier": key[7], "specRef": key[8], "runner": key[9],
    }


def _raw_key(raw: Mapping[str, Any]) -> SlotKey:
    return _slot_key(
        target=_identity(raw.get("deploymentTarget"), field="raw.deploymentTarget"),
        platform=_identity(raw.get("platform"), field="raw.platform"),
        provider=_identity(raw.get("provider"), field="raw.provider"),
        device=_identity(raw.get("deviceIdentity", raw.get("deviceId")), field="raw.deviceIdentity"),
        profile=_identity(raw.get("uatProfile", raw.get("profile")), field="raw.uatProfile"),
        object_id=_text(raw.get("objectId"), field="raw.objectId"),
        entry=_text(raw.get("entrySurface"), field="raw.entrySurface"),
        carrier=_text(raw.get("carrier"), field="raw.carrier"),
        spec_ref=_text(raw.get("specRef"), field="raw.specRef"),
        runner=_identity(raw.get("runnerIdentity"), field="raw.runnerIdentity"),
    )


def _validate_raw_shape(raw: Mapping[str, Any], *, schema_path: Path) -> None:
    _jsonschema_validate({"generatedAt": "2000-01-01T00:00:00Z", "results": [dict(raw)]}, schema_path, label="raw ReadinessCaseResult")
    if raw.get("producer") != "app" or raw.get("layer") != "user_acceptance":
        _fail(_INVALID, "raw result is not App user_acceptance evidence")
    if raw.get("status") not in _RAW_STATUSES:
        _fail(_INVALID, "raw result outcome is unknown")


def _issue(code: str, *, slot_id: str | None = None, ref: str | None = None) -> dict[str, str]:
    value = {"code": code}
    if slot_id is not None:
        value["slotId"] = slot_id
    if ref is not None:
        value["ref"] = ref
    return value


def build_app_uat_result_bundle(
    *,
    evidence_root: Path,
    sample_plan: Mapping[str, Any],
    target_bindings: Sequence[Mapping[str, Any]],
    raw_results: Sequence[Mapping[str, Any]],
    generated_at: str,
    readiness_schema_path: Path | None = None,
) -> dict[str, Any]:
    """Rebuild one diagnostic projection from explicit exact-byte references."""

    root = _root(evidence_root)
    plan_ref, plan_digest, plan = _read_source(root, sample_plan, label="samplePlan")
    repo_root = Path(__file__).absolute().parents[3]
    _jsonschema_validate(
        plan,
        repo_root / "quwoquan_data/schema/release/release_uat_sample_plan.schema.json",
        label="samplePlan",
    )
    plan_cells = _plan_cells(plan)
    plan_samples = _plan_samples(plan)
    release_id = _identity(plan.get("releaseId"), field="samplePlan.releaseId")
    release_digest = _digest(plan.get("releaseDigest"), field="samplePlan.releaseDigest")

    binding_rows: list[dict[str, str]] = []
    bindings_by_digest: dict[str, dict[str, Any]] = {}
    binding_schema_path = repo_root / "quwoquan_ops/environments/evidence/target_uat_binding.schema.json"
    for index, source in enumerate(target_bindings):
        ref, digest, binding = _read_source(root, source, label=f"targetBindings[{index}]")
        _jsonschema_validate(binding, binding_schema_path, label=f"targetBindings[{index}]")
        try:
            validate_target_uat_binding(binding)
        except ValueError as error:
            raise AppUatResultBundleError(_INVALID, f"targetBindings[{index}] is invalid: {error}") from error
        if binding.get("releaseId") != release_id:
            _fail(_INVALID, f"targetBindings[{index}] is cross-release")
        if binding.get("releaseUatSamplePlanRef") != plan_ref or binding.get("releaseUatSamplePlanDigest") != plan_digest:
            _fail(_INVALID, f"targetBindings[{index}] sample plan binding drifted")
        if digest in bindings_by_digest:
            _fail(_INVALID, "target binding digest is duplicated")
        profile = _binding_profile(binding)
        provider = _binding_provider(binding)
        device = _binding_device(binding)
        row = {
            "ref": ref, "digest": digest,
            "bindingId": _identity(binding.get("bindingId"), field="binding.bindingId"),
            "target": _identity(binding.get("target"), field="binding.target"),
            "platform": _identity(binding.get("platform"), field="binding.platform"),
            "provider": provider, "device": device, "profile": profile,
        }
        binding_rows.append(row)
        bindings_by_digest[digest] = {**binding, "_row": row}
    if not binding_rows:
        _fail(_INVALID, "at least one TargetUatBinding is required")
    if any(
        _digest(binding["releaseDigest"], field="binding.releaseDigest") != release_digest
        for binding in bindings_by_digest.values()
    ):
        _fail(_INVALID, "TargetUatBinding releaseDigest drifted from sample plan")

    expected: dict[SlotKey, dict[str, str]] = {}
    na_keys: dict[tuple[str, str, str, str, str, str, str], dict[str, str]] = {}
    na_rows: list[dict[str, str]] = []
    for binding in bindings_by_digest.values():
        row = binding["_row"]
        for cell in plan_cells:
            if cell["applicability"] == "required":
                for sample in plan_samples:
                    if sample["carrier"] != cell["carrier"]:
                        continue
                    key = _slot_key(
                        target=row["target"], platform=row["platform"], provider=row["provider"],
                        device=row["device"], profile=row["profile"], object_id=sample["objectId"],
                        entry=cell["entry"], carrier=cell["carrier"], spec_ref=cell["specRef"], runner=cell["runner"],
                    )
                    if key in expected:
                        _fail(_INVALID, "TargetUatBinding documents create duplicate required slot identity")
                    expected[key] = {
                        **_identity_fields(key),
                        "sampleId": sample["sampleId"],
                        "objectRef": sample["objectRef"],
                        "objectDigest": sample["objectDigest"],
                    }
            else:
                na_key = (
                    row["target"], row["platform"], row["provider"], row["device"],
                    row["profile"], cell["entry"], cell["carrier"],
                )
                if na_key in na_keys:
                    _fail(_INVALID, "TargetUatBinding documents create duplicate not-applicable identity")
                na_row = {
                    "target": row["target"], "platform": row["platform"], "provider": row["provider"],
                    "device": row["device"], "profile": row["profile"],
                    "entry": cell["entry"], "carrier": cell["carrier"], "reason": cell["reason"],
                }
                na_keys[na_key] = na_row
                na_rows.append(na_row)

    schema_path = readiness_schema_path or repo_root / "quwoquan_service/contracts/metadata/_schemas/readiness_result_bundle.schema.json"
    observed: defaultdict[SlotKey, list[dict[str, str]]] = defaultdict(list)
    issues: list[dict[str, str]] = []
    drifted = 0
    for index, source in enumerate(raw_results):
        ref, digest, raw = _read_source(root, source, label=f"rawResults[{index}]")
        _validate_raw_shape(raw, schema_path=schema_path)
        binding_digest = _digest(raw.get("targetUatBindingDigest"), field="raw.targetUatBindingDigest")
        binding = bindings_by_digest.get(binding_digest)
        if binding is None:
            drifted += 1
            issues.append(_issue("raw_binding_digest_drifted", ref=ref))
            continue
        row = binding["_row"]
        raw_release_digest = _digest(raw.get("releaseDigest"), field="raw.releaseDigest")
        key = _raw_key(raw)
        if raw.get("releaseId") != release_id or raw_release_digest != release_digest:
            drifted += 1
            issues.append(_issue("raw_release_drifted", slot_id=_slot_id(key), ref=ref))
            continue
        expected_binding_identity = (
            row["target"], row["platform"], row["provider"], row["device"], row["profile"],
        )
        if key[:5] != expected_binding_identity:
            drifted += 1
            issues.append(_issue("raw_target_binding_identity_drifted", slot_id=_slot_id(key), ref=ref))
            continue
        na_key = (key[0], key[1], key[2], key[3], key[4], key[6], key[7])
        if na_key in na_keys:
            drifted += 1
            issues.append(_issue("not_applicable_has_raw", ref=ref))
            continue
        expected_slot = expected.get(key)
        if expected_slot is None:
            drifted += 1
            issues.append(_issue("raw_slot_identity_drifted", slot_id=_slot_id(key), ref=ref))
            continue
        if raw.get("objectId") != expected_slot["objectId"]:
            drifted += 1
            issues.append(_issue("raw_object_identity_drifted", slot_id=_slot_id(key), ref=ref))
            continue
        observed[key].append({"ref": ref, "digest": digest, "rawStatus": str(raw["status"])})

    required_rows: list[dict[str, Any]] = []
    present = missing = duplicate = non_passed = 0
    for key in sorted(expected):
        raws = sorted(observed.get(key, []), key=lambda row: (row["ref"], row["digest"], row["rawStatus"]))
        slot_id = _slot_id(key)
        if not raws:
            missing += 1
            issues.append(_issue("required_slot_missing", slot_id=slot_id))
        else:
            present += 1
            if len(raws) > 1:
                duplicate += 1
                for raw in raws:
                    issues.append(_issue("required_slot_duplicate", slot_id=slot_id, ref=raw["ref"]))
            for raw in raws:
                if raw["rawStatus"] in _NON_PASSED:
                    non_passed += 1
                    issues.append(_issue("required_slot_non_passed", slot_id=slot_id, ref=raw["ref"]))
        required_rows.append({**expected[key], "rawResults": raws})

    document: dict[str, Any] = {
        "schema": APP_UAT_RESULT_BUNDLE_SCHEMA,
        "generatedAt": _date_time(generated_at, field="generatedAt"),
        "releaseId": release_id,
        "releaseDigest": release_digest,
        "samplePlan": {"ref": plan_ref, "digest": plan_digest},
        "targetBindings": sorted(binding_rows, key=lambda row: (row["target"], row["platform"], row["provider"], row["device"], row["profile"], row["bindingId"], row["ref"])),
        "requiredSlots": required_rows,
        "notApplicableCells": sorted(na_rows, key=lambda row: (row["target"], row["platform"], row["provider"], row["device"], row["profile"], row["entry"], row["carrier"])),
        "coverage": {
            "required": len(expected), "present": present, "missing": missing,
            "duplicate": duplicate, "nonPassed": non_passed, "drifted": drifted,
        },
        "issues": sorted(issues, key=lambda row: (row["code"], row.get("slotId", ""), row.get("ref", ""))),
    }
    return validate_app_uat_result_bundle(document)


def _walk_forbidden(value: object, *, path: str = "root") -> None:
    if isinstance(value, Mapping):
        forbidden = _FORBIDDEN_KEYS.intersection(value)
        if forbidden:
            _fail(_INVALID, f"{path} contains forbidden fields {sorted(forbidden)}")
        for key, child in value.items():
            _walk_forbidden(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _walk_forbidden(child, path=f"{path}[{index}]")


def validate_app_uat_result_bundle(document: Mapping[str, Any]) -> dict[str, Any]:
    """Strictly validate one projection without consulting canonical inputs."""

    if not isinstance(document, Mapping):
        _fail(_INVALID, "projection must be an object")
    value = dict(document)
    expected_fields = {
        "schema", "generatedAt", "releaseId", "releaseDigest", "samplePlan", "targetBindings",
        "requiredSlots", "notApplicableCells", "coverage", "issues",
    }
    if set(value) != expected_fields:
        _fail(_INVALID, "projection fields mismatch")
    _walk_forbidden(value)
    if value["schema"] != APP_UAT_RESULT_BUNDLE_SCHEMA:
        _fail(_INVALID, "projection schema is invalid")
    _date_time(value["generatedAt"], field="generatedAt")
    _identity(value["releaseId"], field="releaseId")
    _digest(value["releaseDigest"], field="releaseDigest")
    _source(value["samplePlan"], label="samplePlan")
    if not isinstance(value["targetBindings"], list) or not value["targetBindings"]:
        _fail(_INVALID, "targetBindings must be a non-empty array")
    binding_fields = {"ref", "digest", "bindingId", "target", "platform", "provider", "device", "profile"}
    binding_rows: list[dict[str, str]] = []
    for index, row in enumerate(value["targetBindings"]):
        if not isinstance(row, Mapping) or set(row) != binding_fields:
            _fail(_INVALID, f"targetBindings[{index}] fields mismatch")
        _relative_ref(row["ref"], field=f"targetBindings[{index}].ref")
        _digest(row["digest"], field=f"targetBindings[{index}].digest")
        for field in ("bindingId", "target", "platform", "provider", "device", "profile"):
            _identity(row[field], field=f"targetBindings[{index}].{field}")
        binding_rows.append(dict(row))
    if binding_rows != sorted(binding_rows, key=lambda row: (row["target"], row["platform"], row["provider"], row["device"], row["profile"], row["bindingId"], row["ref"])):
        _fail(_INVALID, "targetBindings are not deterministically sorted")

    if not isinstance(value["requiredSlots"], list) or not isinstance(value["notApplicableCells"], list):
        _fail(_INVALID, "slot projections must be arrays")
    observed_slots: set[SlotKey] = set()
    counted_present = counted_missing = counted_duplicate = counted_non_passed = 0
    required_rows: list[dict[str, Any]] = []
    for index, row in enumerate(value["requiredSlots"]):
        required_fields = {
            "slotId", "target", "platform", "provider", "device", "profile",
            "sampleId", "objectId", "objectRef", "objectDigest", "entry", "carrier",
            "specRef", "runner", "rawResults",
        }
        if not isinstance(row, Mapping) or set(row) != required_fields:
            _fail(_INVALID, f"requiredSlots[{index}] fields mismatch")
        key = _slot_key(
            target=_identity(row["target"], field="slot.target"), platform=_identity(row["platform"], field="slot.platform"),
            provider=_identity(row["provider"], field="slot.provider"), device=_identity(row["device"], field="slot.device"),
            profile=_identity(row["profile"], field="slot.profile"),
            object_id=_text(row["objectId"], field="slot.objectId"),
            entry=_text(row["entry"], field="slot.entry"), carrier=_text(row["carrier"], field="slot.carrier"),
            spec_ref=_text(row["specRef"], field="slot.specRef"), runner=_identity(row["runner"], field="slot.runner"),
        )
        _identity(row["sampleId"], field="slot.sampleId")
        _relative_ref(row["objectRef"], field="slot.objectRef")
        _digest(row["objectDigest"], field="slot.objectDigest")
        if row["slotId"] != _slot_id(key) or key in observed_slots:
            _fail(_INVALID, "required slot identity is duplicated or drifted")
        observed_slots.add(key)
        raws = row["rawResults"]
        if not isinstance(raws, list):
            _fail(_INVALID, "slot rawResults must be an array")
        seen_refs: set[str] = set()
        for raw_index, raw in enumerate(raws):
            if not isinstance(raw, Mapping) or set(raw) != {"ref", "digest", "rawStatus"}:
                _fail(_INVALID, f"slot rawResults[{raw_index}] fields mismatch")
            ref = _relative_ref(raw["ref"], field="raw ref")
            if ref in seen_refs:
                _fail(_INVALID, "slot raw refs are duplicated")
            seen_refs.add(ref)
            _digest(raw["digest"], field="raw digest")
            if raw["rawStatus"] not in _RAW_STATUSES:
                _fail(_INVALID, "raw outcome is unknown")
        if not raws:
            counted_missing += 1
        else:
            counted_present += 1
        if len(raws) > 1:
            counted_duplicate += 1
        counted_non_passed += sum(raw["rawStatus"] in _NON_PASSED for raw in raws)
        required_rows.append(dict(row))
    if required_rows != sorted(required_rows, key=lambda row: (row["target"], row["platform"], row["provider"], row["device"], row["profile"], row["objectId"], row["entry"], row["carrier"], row["specRef"], row["runner"])):
        _fail(_INVALID, "requiredSlots are not deterministically sorted")

    na_fields = {"target", "platform", "provider", "device", "profile", "entry", "carrier", "reason"}
    na_rows: list[dict[str, str]] = []
    for index, row in enumerate(value["notApplicableCells"]):
        if not isinstance(row, Mapping) or set(row) != na_fields:
            _fail(_INVALID, f"notApplicableCells[{index}] fields mismatch")
        for field in ("target", "platform", "provider", "device", "profile"):
            _identity(row[field], field=f"notApplicableCells[{index}].{field}")
        entry = _text(row["entry"], field=f"notApplicableCells[{index}].entry")
        carrier = _text(row["carrier"], field=f"notApplicableCells[{index}].carrier")
        if entry not in _ENTRIES or carrier not in _CARRIERS:
            _fail(_INVALID, f"notApplicableCells[{index}] axes are unknown")
        _text(row["reason"], field=f"notApplicableCells[{index}].reason")
        na_rows.append(dict(row))
    if na_rows != sorted(na_rows, key=lambda row: (row["target"], row["platform"], row["provider"], row["device"], row["profile"], row["entry"], row["carrier"])):
        _fail(_INVALID, "notApplicableCells are not deterministically sorted")

    coverage = value["coverage"]
    if not isinstance(coverage, Mapping) or set(coverage) != {"required", "present", "missing", "duplicate", "nonPassed", "drifted"}:
        _fail(_INVALID, "coverage fields mismatch")
    for field in coverage:
        if not isinstance(coverage[field], int) or isinstance(coverage[field], bool) or coverage[field] < 0:
            _fail(_INVALID, f"coverage.{field} must be a non-negative integer")
    expected_counts = {
        "required": len(value["requiredSlots"]), "present": counted_present, "missing": counted_missing,
        "duplicate": counted_duplicate, "nonPassed": counted_non_passed,
    }
    if any(coverage[field] != count for field, count in expected_counts.items()):
        _fail(_INVALID, "coverage counters drifted from requiredSlots")
    if not isinstance(value["issues"], list):
        _fail(_INVALID, "issues must be an array")
    issue_rows: list[dict[str, str]] = []
    for index, issue in enumerate(value["issues"]):
        if not isinstance(issue, Mapping) or "code" not in issue or not set(issue).issubset({"code", "slotId", "ref"}):
            _fail(_INVALID, f"issues[{index}] fields mismatch")
        _identity(issue["code"], field=f"issues[{index}].code")
        if "slotId" in issue:
            _identity(issue["slotId"], field=f"issues[{index}].slotId")
        if "ref" in issue:
            _relative_ref(issue["ref"], field=f"issues[{index}].ref")
        issue_rows.append(dict(issue))
    if issue_rows != sorted(issue_rows, key=lambda row: (row["code"], row.get("slotId", ""), row.get("ref", ""))):
        _fail(_INVALID, "issues are not deterministically sorted")
    return value


def canonical_projection_bytes(document: Mapping[str, Any]) -> bytes:
    validated = validate_app_uat_result_bundle(document)
    return (json.dumps(validated, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def document_digest(document: Mapping[str, Any]) -> str:
    return _exact_digest(canonical_projection_bytes(document))


def write_projection(*, evidence_root: Path, relative_path: str | Path, document: Mapping[str, Any]) -> Path:
    """Validate and atomically replace a rebuildable projection file."""

    root = _root(evidence_root)
    ref = _relative_ref(str(relative_path), field="projection output ref")
    destination = root.joinpath(*PurePosixPath(ref).parts)
    destination.parent.mkdir(parents=True, exist_ok=True)
    current = root
    for part in PurePosixPath(ref).parts[:-1]:
        current /= part
        if current.is_symlink() or not current.is_dir():
            _fail(_PATH_INVALID, "projection output parent is unsafe")
    if destination.is_symlink():
        _fail(_PATH_INVALID, "projection output cannot be a symlink")
    encoded = canonical_projection_bytes(document)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        directory_fd = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


validate = validate_app_uat_result_bundle

__all__ = [
    "APP_UAT_RESULT_BUNDLE_SCHEMA", "AppUatResultBundleError", "SCHEMA", "SCHEMA_PATH",
    "build_app_uat_result_bundle", "canonical_projection_bytes", "document_digest",
    "validate", "validate_app_uat_result_bundle", "write_projection",
]
