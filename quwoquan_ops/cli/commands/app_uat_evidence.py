"""stackctl Ops UAT authority-chain command wiring.

All inputs are explicit evidence-root-relative refs plus exact-byte digests.
The module never discovers ``latest`` and performs no environment or device
mutation.  Handler failures are returned as typed ``GATE_BLOCK`` payloads.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from quwoquan_ops.cli.commands.environment_acceptance_predecessor import (
    validate_predecessor_acceptance,
)
from quwoquan_ops.cli.lib.app_uat_result_bundle import (
    AppUatResultBundleError,
    build_app_uat_result_bundle,
    document_digest,
    write_projection,
)
from quwoquan_ops.cli.lib.environment_acceptance_fact import (
    EnvironmentAcceptanceFactError,
    build_environment_acceptance_fact,
    exact_byte_digest,
    write_environment_acceptance_fact,
)
from quwoquan_ops.cli.lib.target_uat_binding import (
    TargetUatBindingError,
    build_target_uat_binding,
    write_create_once_target_uat_binding,
)

_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_REF_SEGMENT_RE = re.compile(r"^[A-Za-z0-9._-]+$")


class AppUatEvidenceCommandError(ValueError):
    """Typed command-surface blocker before an Ops authority mutation."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code


def _block(code: str, detail: str) -> None:
    raise AppUatEvidenceCommandError(code, detail)


def _digest(value: object, *, field: str) -> str:
    if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
        _block("OPS.APP_UAT_EVIDENCE.invalid_digest", f"{field} must be canonical sha256")
    return value


def _ref(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        _block("OPS.APP_UAT_EVIDENCE.path_blocked", f"{field} must be non-empty")
    candidate = PurePosixPath(value)
    if (
        value.startswith("/")
        or "\\" in value
        or candidate.as_posix() != value
        or any(
            part in {"", ".", ".."} or _REF_SEGMENT_RE.fullmatch(part) is None
            for part in candidate.parts
        )
    ):
        _block(
            "OPS.APP_UAT_EVIDENCE.path_blocked",
            f"{field} must be a contained evidence-root-relative ref",
        )
    return value


def _root(value: str | Path, *, field: str) -> Path:
    candidate = Path(value).expanduser()
    candidate = candidate if candidate.is_absolute() else Path.cwd() / candidate
    candidate = Path(os.path.abspath(candidate))
    try:
        metadata = candidate.lstat()
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        raise AppUatEvidenceCommandError(
            "OPS.APP_UAT_EVIDENCE.path_blocked", f"{field} is unavailable"
        ) from error
    if candidate.is_symlink() or not stat.S_ISDIR(metadata.st_mode) or resolved != candidate:
        _block(
            "OPS.APP_UAT_EVIDENCE.path_blocked",
            f"{field} must be a real non-symlink directory",
        )
    return candidate


def _read_exact_json(
    *, evidence_root: Path, ref: str, digest: str, label: str
) -> dict[str, Any]:
    root = _root(evidence_root, field="evidenceRoot")
    relative = PurePosixPath(_ref(ref, field=f"{label}.ref"))
    current = root
    for part in relative.parts[:-1]:
        current /= part
        try:
            metadata = current.lstat()
        except OSError as error:
            raise AppUatEvidenceCommandError(
                "OPS.APP_UAT_EVIDENCE.path_blocked",
                f"{label} parent is unavailable",
            ) from error
        if current.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
            _block(
                "OPS.APP_UAT_EVIDENCE.path_blocked",
                f"{label} path contains a symlink or non-directory",
            )
    path = current / relative.name
    try:
        before = path.lstat()
    except OSError as error:
        raise AppUatEvidenceCommandError(
            "OPS.APP_UAT_EVIDENCE.path_blocked", f"{label} is unavailable"
        ) from error
    if path.is_symlink() or not stat.S_ISREG(before.st_mode):
        _block(
            "OPS.APP_UAT_EVIDENCE.path_blocked",
            f"{label} must be a regular non-symlink file",
        )
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = -1
    try:
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
    except OSError as error:
        raise AppUatEvidenceCommandError(
            "OPS.APP_UAT_EVIDENCE.path_blocked", f"{label} cannot be read safely"
        ) from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    encoded = b"".join(chunks)
    identity = (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
    if (
        identity
        != (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        or identity != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        or len(encoded) != opened.st_size
    ):
        _block("OPS.APP_UAT_EVIDENCE.path_blocked", f"{label} changed during read")
    actual = "sha256:" + hashlib.sha256(encoded).hexdigest()
    if actual != _digest(digest, field=f"{label}.digest"):
        _block(
            "OPS.APP_UAT_EVIDENCE.digest_drift",
            f"{label} exact bytes drifted: expected {digest}, got {actual}",
        )

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                _block(
                    "OPS.APP_UAT_EVIDENCE.invalid_json",
                    f"{label} contains duplicate JSON key {key!r}",
                )
            result[key] = value
        return result

    try:
        text = encoded.decode("utf-8")
        decoder = json.JSONDecoder(
            object_pairs_hook=unique,
            parse_constant=lambda value: _block(
                "OPS.APP_UAT_EVIDENCE.invalid_json",
                f"{label} contains invalid JSON constant {value}",
            ),
        )
        payload, end = decoder.raw_decode(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AppUatEvidenceCommandError(
            "OPS.APP_UAT_EVIDENCE.invalid_json", f"{label} is not UTF-8 JSON"
        ) from error
    if text[end:].strip() or not isinstance(payload, dict):
        _block(
            "OPS.APP_UAT_EVIDENCE.invalid_json",
            f"{label} must contain exactly one JSON object",
        )
    return payload


def _source(ref: str, digest: str, *, label: str) -> dict[str, str]:
    return {
        "ref": _ref(ref, field=f"{label}.ref"),
        "digest": _digest(digest, field=f"{label}.digest"),
    }


def _source_argument(raw: Sequence[str], *, label: str) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    for index, value in enumerate(raw):
        parts = value.split("=", 1)
        if len(parts) != 2:
            _block(
                "OPS.APP_UAT_EVIDENCE.invalid_argument",
                f"{label}[{index}] must be REF=sha256:<64 lowercase hex>",
            )
        sources.append(_source(parts[0], parts[1], label=f"{label}[{index}]"))
    if not sources:
        _block("OPS.APP_UAT_EVIDENCE.invalid_argument", f"{label} must be non-empty")
    return sources


def _profile_argument(raw: Sequence[str]) -> list[dict[str, str]]:
    profiles: list[dict[str, str]] = []
    for index, value in enumerate(raw):
        parts = value.split("=", 1)
        if len(parts) != 2 or not all(part for part in parts):
            _block(
                "OPS.APP_UAT_EVIDENCE.invalid_argument",
                f"requiredProfile[{index}] must be PLATFORM=DEVICE_PROFILE",
            )
        profiles.append({"platform": parts[0], "deviceProfile": parts[1]})
    if not profiles:
        _block(
            "OPS.APP_UAT_EVIDENCE.invalid_argument",
            "requiredProfile must be non-empty",
        )
    return profiles


def _target_binding_argument(raw: Sequence[str]) -> list[dict[str, str]]:
    bindings: list[dict[str, str]] = []
    for index, value in enumerate(raw):
        parts = value.split("=", 3)
        if len(parts) != 4:
            _block(
                "OPS.APP_UAT_EVIDENCE.invalid_argument",
                "targetBinding["
                f"{index}] must be PLATFORM=DEVICE_PROFILE=REF=sha256:<64 lowercase hex>",
            )
        platform, profile, ref, digest = parts
        source = _source(ref, digest, label=f"targetBinding[{index}]")
        bindings.append(
            {
                **source,
                "platform": platform,
                "deviceProfile": profile,
            }
        )
    if not bindings:
        _block(
            "OPS.APP_UAT_EVIDENCE.invalid_argument",
            "targetBinding must be non-empty",
        )
    return bindings


def _required_raw_argument(raw: Sequence[str]) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for index, value in enumerate(raw):
        parts = value.split("=", 3)
        if len(parts) != 4:
            _block(
                "OPS.APP_UAT_EVIDENCE.invalid_argument",
                "requiredRaw["
                f"{index}] must be SLOT_ID=STATUS=REF=sha256:<64 lowercase hex>",
            )
        slot_id, status, ref, digest = parts
        source = _source(ref, digest, label=f"requiredRaw[{index}]")
        results.append(
            {
                **source,
                "slotId": _digest(slot_id, field=f"requiredRaw[{index}].slotId"),
                "status": status,
            }
        )
    if not results:
        _block("OPS.APP_UAT_EVIDENCE.invalid_argument", "requiredRaw must be non-empty")
    return results


def _prod_release_facts(raw: str) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise AppUatEvidenceCommandError(
            "OPS.APP_UAT_EVIDENCE.invalid_argument",
            "prodReleaseFacts must be one JSON object",
        ) from error
    if not isinstance(value, dict):
        _block(
            "OPS.APP_UAT_EVIDENCE.invalid_argument",
            "prodReleaseFacts must be one JSON object",
        )
    return value


def _status(payload: Mapping[str, Any]) -> str:
    for field in ("status", "state", "phase", "lifecycleState"):
        observed = payload.get(field)
        if isinstance(observed, str) and observed:
            return observed
    return ""


def _require_complete(
    payload: Mapping[str, Any], *, label: str, allowed: frozenset[str]
) -> None:
    observed = _status(payload)
    if observed.lower() not in allowed:
        _block(
            "OPS.TARGET_UAT_BINDING.activation_incomplete",
            f"{label} must be complete before TargetUatBinding creation; got {observed!r}",
        )


def build_target_uat_binding_command(
    *, evidence_root: Path, output_root: Path, runtime_binding_ref: str,
    runtime_binding_digest: str, launch_binding_ref: str, launch_binding_digest: str,
    sample_plan_ref: str, sample_plan_digest: str, active_cas_ref: str,
    active_cas_digest: str, readback_ref: str, readback_digest: str,
    artifact_class: str, build_mode: str, build_profile: str,
    provider_identity: str, provider_class: str, provider_type: str,
    provider_registered: bool, provider_conformance_ref: str,
    provider_conformance_digest: str,
    device_identity: str, device_class: str, device_registered: bool,
    runner_identity: str, runner_source_path: str, runner_digest: str,
    runner_registered: bool, profile: str, non_promotable: bool, created_at: str,
) -> dict[str, Any]:
    """Pure command handler for explicit TargetUatBinding authoring."""

    root = _root(evidence_root, field="evidenceRoot")
    runtime = _read_exact_json(
        evidence_root=root, ref=runtime_binding_ref, digest=runtime_binding_digest,
        label="runtimeBinding",
    )
    launch = _read_exact_json(
        evidence_root=root, ref=launch_binding_ref, digest=launch_binding_digest,
        label="launchBinding",
    )
    plan = _read_exact_json(
        evidence_root=root, ref=sample_plan_ref, digest=sample_plan_digest,
        label="releaseUatSamplePlan",
    )
    activation = _read_exact_json(
        evidence_root=root, ref=active_cas_ref, digest=active_cas_digest,
        label="activeCas",
    )
    readback = _read_exact_json(
        evidence_root=root, ref=readback_ref, digest=readback_digest,
        label="readback",
    )
    _require_complete(
        activation, label="activeCas", allowed=frozenset({"active", "activated", "completed", "passed", "ready"}),
    )
    _require_complete(
        readback, label="readback", allowed=frozenset({"active", "activated", "completed", "passed", "ready"}),
    )
    if plan.get("schema") != "quwoquan_data.release_uat_sample_plan":
        _block("OPS.TARGET_UAT_BINDING.sample_plan_invalid", "ReleaseUatSamplePlan schema is invalid")
    if (
        plan.get("releaseId") != runtime.get("releaseId")
        or plan.get("releaseDigest") != runtime.get("manifestDigest")
    ):
        _block("OPS.TARGET_UAT_BINDING.stale", "ReleaseUatSamplePlan release identity drifted")
    for label, payload in (("activeCas", activation), ("readback", readback)):
        for field, expected in (
            ("environment", runtime.get("environment")),
            ("releaseId", runtime.get("releaseId")),
        ):
            observed = payload.get(field)
            if observed is not None and observed != expected:
                _block("OPS.TARGET_UAT_BINDING.stale", f"{label}.{field} drifted")
        observed_digest = payload.get("releaseDigest", payload.get("manifestDigest"))
        if observed_digest is not None and observed_digest != runtime.get("manifestDigest"):
            _block("OPS.TARGET_UAT_BINDING.stale", f"{label}.releaseDigest drifted")
        observed_target = payload.get("deploymentTarget", payload.get("target"))
        if observed_target is not None and observed_target != runtime.get("target"):
            _block("OPS.TARGET_UAT_BINDING.stale", f"{label}.target drifted")
    binding = build_target_uat_binding(
        runtime,
        launch,
        {
            "releaseId": plan.get("releaseId"),
            "releaseUatSamplePlanRef": _ref(sample_plan_ref, field="releaseUatSamplePlan.ref"),
            "releaseUatSamplePlanDigest": _digest(sample_plan_digest, field="releaseUatSamplePlan.digest"),
        },
        active_cas=_source(active_cas_ref, active_cas_digest, label="activeCas"),
        readback=_source(readback_ref, readback_digest, label="readback"),
        artifact_class=artifact_class,
        build_mode=build_mode,
        build_profile=build_profile,
        provider={
            "identity": provider_identity,
            "class": provider_class,
            "type": provider_type,
            "registered": provider_registered,
            "conformanceEvidence": _source(
                provider_conformance_ref,
                provider_conformance_digest,
                label="provider.conformanceEvidence",
            ),
        },
        device={"identity": device_identity, "class": device_class, "registered": device_registered},
        runner={
            "identity": runner_identity,
            "sourcePath": runner_source_path,
            "digest": runner_digest,
            "registered": runner_registered,
        },
        profile=profile,
        non_promotable=non_promotable,
        created_at=created_at,
    )
    binding_root = _root(output_root, field="bindingOutputRoot")
    try:
        binding_root.relative_to(root)
    except ValueError as error:
        raise AppUatEvidenceCommandError(
            "OPS.APP_UAT_EVIDENCE.path_blocked",
            "bindingOutputRoot must be contained by evidenceRoot",
        ) from error
    written = write_create_once_target_uat_binding(
        output_root=binding_root, binding=binding
    )
    return {
        "exitCode": 0,
        "summary": "TargetUatBinding created" if written.created else "TargetUatBinding exact replay verified",
        "details": [f"binding: {written.ref}"],
        "bindingRef": written.ref,
        "bindingDigest": written.digest,
        "bindingId": written.binding["bindingId"],
        "created": written.created,
    }


def build_app_uat_bundle_command(
    *, evidence_root: Path, sample_plan: Mapping[str, Any],
    target_bindings: Sequence[Mapping[str, Any]], raw_results: Sequence[Mapping[str, Any]],
    output_ref: str, generated_at: str,
) -> dict[str, Any]:
    """Pure read-only projection command; coverage is diagnostic, never a verdict."""

    root = _root(evidence_root, field="evidenceRoot")
    projection = build_app_uat_result_bundle(
        evidence_root=root,
        sample_plan=sample_plan,
        target_bindings=target_bindings,
        raw_results=raw_results,
        generated_at=generated_at,
    )
    output = write_projection(
        evidence_root=root, relative_path=_ref(output_ref, field="outputRef"), document=projection
    )
    return {
        "exitCode": 0,
        "summary": "AppUatResultBundle diagnostic projection rebuilt",
        "details": [f"projection: {output.relative_to(root).as_posix()}"],
        "bundleRef": output.relative_to(root).as_posix(),
        "bundleDigest": document_digest(projection),
        "coverage": projection["coverage"],
        "issues": projection["issues"],
    }


def build_environment_acceptance_append_command(
    *, evidence_root: Path, acceptance_root: Path, environment: str, target: str,
    release_id: str, release_digest: str, sample_plan_ref: str,
    sample_plan_digest: str, target_binding_refs: Sequence[Mapping[str, Any]],
    required_raw_results: Sequence[Mapping[str, Any]],
    required_target_profiles: Sequence[Mapping[str, str]],
    data_readiness: Mapping[str, str], active_cas: Mapping[str, str],
    lifecycle_exit: Mapping[str, str], provider_readiness: Mapping[str, str],
    observability_readiness: Mapping[str, str], rollback_readiness: Mapping[str, str],
    predecessor_ref: str | None, predecessor_digest: str | None,
    predecessor_fact_id: str | None,
    resource_finalization: Mapping[str, Sequence[Mapping[str, str]]],
    prod_release_facts: Mapping[str, Any] | None, created_at: str,
    source_fingerprint: str,
) -> dict[str, Any]:
    """Pure append handler; predecessor validation always precedes fact building."""

    root = _root(evidence_root, field="evidenceRoot")
    acceptance_store = _root(acceptance_root, field="acceptanceRoot")
    try:
        acceptance_store.relative_to(root)
    except ValueError as error:
        raise AppUatEvidenceCommandError(
            "OPS.APP_UAT_EVIDENCE.path_blocked",
            "acceptanceRoot must be contained by evidenceRoot",
        ) from error
    predecessor = validate_predecessor_acceptance(
        environment=environment,
        release_id=release_id,
        release_digest=release_digest,
        predecessor_ref=predecessor_ref,
        predecessor_digest=predecessor_digest,
        predecessor_fact_id=predecessor_fact_id,
        evidence_root=root,
    )
    fact = build_environment_acceptance_fact(
        evidence_root=root,
        environment=environment,
        target=target,
        release_id=release_id,
        release_digest=release_digest,
        sample_plan_ref=sample_plan_ref,
        sample_plan_digest=sample_plan_digest,
        target_binding_refs=target_binding_refs,
        required_raw_results=required_raw_results,
        required_target_profiles=required_target_profiles,
        data_readiness=data_readiness,
        active_cas=active_cas,
        lifecycle_exit=lifecycle_exit,
        provider_readiness=provider_readiness,
        observability_readiness=observability_readiness,
        rollback_readiness=rollback_readiness,
        predecessor_acceptance=predecessor,
        resource_finalization=resource_finalization,
        prod_release_facts=prod_release_facts,
        created_at=created_at,
        source_fingerprint=source_fingerprint,
    )
    output = write_environment_acceptance_fact(
        root=acceptance_store,
        fact=fact,
        evidence_root=root,
        required_target_profiles=required_target_profiles,
    )
    return {
        "exitCode": 0,
        "summary": "EnvironmentAcceptanceFact appended or exact replay verified",
        "details": [f"fact: {output}"],
        "factId": fact["factId"],
        "factRef": output.relative_to(root).as_posix(),
        "factDigest": exact_byte_digest(output),
    }


def _gate_block(error: Exception) -> dict[str, Any]:
    code = str(getattr(error, "code", "OPS.APP_UAT_EVIDENCE.gate_block"))
    return {
        "exitCode": 2,
        "status": "GATE_BLOCK",
        "summary": "Ops App UAT evidence command is GATE_BLOCK",
        "blockerCode": code,
        "details": [str(error)],
    }


def command_app_uat_target_bind(args: argparse.Namespace) -> dict[str, Any]:
    try:
        return build_target_uat_binding_command(
            evidence_root=Path(args.evidence_root), output_root=Path(args.binding_output_root),
            runtime_binding_ref=args.runtime_binding_ref, runtime_binding_digest=args.runtime_binding_digest,
            launch_binding_ref=args.launch_binding_ref, launch_binding_digest=args.launch_binding_digest,
            sample_plan_ref=args.sample_plan_ref, sample_plan_digest=args.sample_plan_digest,
            active_cas_ref=args.active_cas_ref, active_cas_digest=args.active_cas_digest,
            readback_ref=args.readback_ref, readback_digest=args.readback_digest,
            artifact_class=args.artifact_class, build_mode=args.build_mode,
            build_profile=args.build_profile,
            provider_identity=args.provider_identity,
            provider_class=args.provider_class,
            provider_type=args.provider_type,
            provider_registered=args.provider_registered,
            provider_conformance_ref=args.provider_conformance_ref,
            provider_conformance_digest=args.provider_conformance_digest,
            device_identity=args.device_identity,
            device_class=args.device_class, device_registered=args.device_registered,
            runner_identity=args.runner_identity, runner_source_path=args.runner_source_path,
            runner_digest=args.runner_digest, runner_registered=args.runner_registered,
            profile=args.profile,
            non_promotable=args.non_promotable, created_at=args.created_at,
        )
    except (AppUatEvidenceCommandError, TargetUatBindingError, OSError, TypeError, ValueError) as error:
        return _gate_block(error)


def command_app_uat_bundle(args: argparse.Namespace) -> dict[str, Any]:
    try:
        return build_app_uat_bundle_command(
            evidence_root=Path(args.evidence_root),
            sample_plan=_source(args.sample_plan_ref, args.sample_plan_digest, label="samplePlan"),
            target_bindings=_source_argument(args.target_binding, label="targetBinding"),
            raw_results=_source_argument(args.raw_result, label="rawResult"),
            output_ref=args.output_ref,
            generated_at=args.generated_at,
        )
    except (AppUatEvidenceCommandError, AppUatResultBundleError, OSError, TypeError, ValueError) as error:
        return _gate_block(error)


def command_environment_acceptance_append(args: argparse.Namespace) -> dict[str, Any]:
    try:
        return build_environment_acceptance_append_command(
            evidence_root=Path(args.evidence_root), acceptance_root=Path(args.acceptance_root),
            environment=args.environment, target=args.target, release_id=args.release_id,
            release_digest=args.release_digest, sample_plan_ref=args.sample_plan_ref,
            sample_plan_digest=args.sample_plan_digest,
            target_binding_refs=_target_binding_argument(args.target_binding),
            required_raw_results=_required_raw_argument(args.required_raw),
            required_target_profiles=_profile_argument(args.required_profile),
            data_readiness=_source(args.data_readiness_ref, args.data_readiness_digest, label="dataReadiness"),
            active_cas={
                "ref": args.active_cas_ref, "digest": args.active_cas_digest,
                "readbackRef": args.active_cas_readback_ref,
                "readbackDigest": args.active_cas_readback_digest,
                "releaseId": args.release_id, "releaseDigest": args.release_digest,
            },
            lifecycle_exit=_source(args.lifecycle_exit_ref, args.lifecycle_exit_digest, label="lifecycleExit"),
            provider_readiness=_source(args.provider_readiness_ref, args.provider_readiness_digest, label="providerReadiness"),
            observability_readiness=_source(args.observability_readiness_ref, args.observability_readiness_digest, label="observabilityReadiness"),
            rollback_readiness=_source(args.rollback_readiness_ref, args.rollback_readiness_digest, label="rollbackReadiness"),
            predecessor_ref=args.predecessor_ref or None,
            predecessor_digest=args.predecessor_digest or None,
            predecessor_fact_id=args.predecessor_fact_id or None,
            resource_finalization={
                "leaseRevocationRefs": _source_argument(
                    args.lease_revocation, label="leaseRevocation"
                ),
                "lockReleaseRefs": _source_argument(
                    args.lock_release, label="lockRelease"
                ),
                "gcProtectionRefs": _source_argument(
                    args.gc_protection, label="gcProtection"
                ),
            },
            prod_release_facts=_prod_release_facts(args.prod_release_facts),
            created_at=args.created_at, source_fingerprint=args.source_fingerprint,
        )
    except (AppUatEvidenceCommandError, EnvironmentAcceptanceFactError, OSError, TypeError, ValueError) as error:
        return _gate_block(error)


def _add_boolean(parser: argparse.ArgumentParser, name: str, *, destination: str) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(name, dest=destination, action="store_true")
    group.add_argument(f"--no-{name.removeprefix('--')}", dest=destination, action="store_false")


def register_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    bind = subparsers.add_parser(
        "app-uat-target-bind",
        help="从显式 ReleaseUatSamplePlan/CAS/readback/candidate/device refs create-once TargetUatBinding",
    )
    for name in (
        "evidence-root", "binding-output-root", "runtime-binding-ref", "runtime-binding-digest",
        "launch-binding-ref", "launch-binding-digest", "sample-plan-ref", "sample-plan-digest",
        "active-cas-ref", "active-cas-digest", "readback-ref", "readback-digest",
        "artifact-class", "build-mode", "build-profile", "provider-identity",
        "provider-class", "provider-type", "provider-conformance-ref",
        "provider-conformance-digest", "device-identity", "device-class",
        "runner-identity", "runner-source-path", "runner-digest", "profile", "created-at",
    ):
        bind.add_argument(f"--{name}", required=True)
    _add_boolean(bind, "--provider-registered", destination="provider_registered")
    _add_boolean(bind, "--device-registered", destination="device_registered")
    _add_boolean(bind, "--runner-registered", destination="runner_registered")
    _add_boolean(bind, "--non-promotable", destination="non_promotable")

    bundle = subparsers.add_parser(
        "app-uat-bundle", help="从显式 plan/binding/raw refs 构建无 verdict 的只读诊断投影"
    )
    for name in ("evidence-root", "sample-plan-ref", "sample-plan-digest", "output-ref", "generated-at"):
        bundle.add_argument(f"--{name}", required=True)
    bundle.add_argument("--target-binding", action="append", required=True)
    bundle.add_argument("--raw-result", action="append", required=True)

    append = subparsers.add_parser(
        "environment-acceptance-append",
        help="校验全部 direct raw/readiness/predecessor authority 后 create-once 追加 acceptance fact",
    )
    for name in (
        "evidence-root", "acceptance-root", "environment", "target", "release-id",
        "release-digest", "sample-plan-ref", "sample-plan-digest", "data-readiness-ref",
        "data-readiness-digest", "active-cas-ref", "active-cas-digest",
        "active-cas-readback-ref", "active-cas-readback-digest", "lifecycle-exit-ref",
        "lifecycle-exit-digest", "provider-readiness-ref", "provider-readiness-digest",
        "observability-readiness-ref", "observability-readiness-digest",
        "rollback-readiness-ref", "rollback-readiness-digest", "created-at",
        "source-fingerprint",
    ):
        append.add_argument(f"--{name}", required=True)
    append.add_argument("--target-binding", action="append", required=True)
    append.add_argument("--required-raw", action="append", required=True)
    append.add_argument("--required-profile", action="append", required=True)
    append.add_argument("--lease-revocation", action="append", required=True)
    append.add_argument("--lock-release", action="append", required=True)
    append.add_argument("--gc-protection", action="append", required=True)
    append.add_argument("--prod-release-facts", default="")
    append.add_argument("--predecessor-ref", default="")
    append.add_argument("--predecessor-digest", default="")
    append.add_argument("--predecessor-fact-id", default="")


COMMAND_HANDLERS: dict[str, Callable[[argparse.Namespace], dict[str, Any]]] = {
    "app-uat-target-bind": command_app_uat_target_bind,
    "app-uat-bundle": command_app_uat_bundle,
    "environment-acceptance-append": command_environment_acceptance_append,
}

__all__ = [
    "AppUatEvidenceCommandError",
    "COMMAND_HANDLERS",
    "build_app_uat_bundle_command",
    "build_environment_acceptance_append_command",
    "build_target_uat_binding_command",
    "command_app_uat_bundle",
    "command_app_uat_target_bind",
    "command_environment_acceptance_append",
    "register_parser",
]
