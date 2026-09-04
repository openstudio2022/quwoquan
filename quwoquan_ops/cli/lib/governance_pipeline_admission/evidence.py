"""Read-only canonical governance evidence bundle assembler and consumer."""
from __future__ import annotations

import base64
import errno
import hashlib
import json
import os
import stat
import subprocess
import threading
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..evidence_fingerprint import (
    build_evidence_fingerprint,
    canonical_digest,
    canonical_json_bytes,
    snapshot_path,
    validate_evidence_fingerprint,
    workspace_digests,
)
from ..feature_tree.content_addressed_writer import _safe_directory_fd
from . import adapters
from . import contract as governance_contract
from .contract import (
    REPO_ROOT,
    ContractError,
    EvidenceAdapterError,
    validate_exact_fields,
)

BUNDLE_SCHEMA_ID = "governance-pipeline-evidence-bundle"
BUNDLE_SCHEMA_VERSION = 2


def _detail(error: BaseException) -> str:
    return " ".join(str(error).replace("\x00", "\\x00").split()) or type(error).__name__


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _verification_time(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ContractError("verification time must be timezone-aware")
    return current.astimezone(timezone.utc)


def _verified_at(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _now() -> str:
    return _verified_at(_verification_time())


def _absent(
    result: str = "not_executed", *, detail: str | None = None,
    verification_time: datetime,
) -> dict[str, Any]:
    return {
        "status": "absent", "schema_valid": True, "fresh": True,
        "fingerprint_match": True, "result": result, "provider_kind": "absent",
        "release_evidence_eligible": False, "detail": detail, "receipt_ref": None,
        "receipt_bytes_sha256": None, "verified_at": _verified_at(verification_time),
        "provider_timestamp": None, "candidate_id": None, "scope_id": None,
        "verifier_id": None,
    }


def _failed(
    error: BaseException | str, *, result: str = "absent",
    verification_time: datetime,
) -> dict[str, Any]:
    detail = error if isinstance(error, str) else _detail(error)
    if isinstance(error, EvidenceAdapterError):
        schema_valid = error.schema_valid
        fresh = error.fresh
        fingerprint_match = error.fingerprint_match
    else:
        normalized = detail.casefold()
        if "stale" in normalized or "freshness" in normalized or "generated in the future" in normalized:
            schema_valid, fresh, fingerprint_match = True, False, True
        elif any(token in normalized for token in (
            "fingerprint", "identity", "candidate/scope", "exact bytes changed",
            "digest drifted", "source bytes drifted",
        )):
            schema_valid, fresh, fingerprint_match = True, True, False
        else:
            schema_valid, fresh, fingerprint_match = False, True, True
    return {
        "status": "failed", "schema_valid": schema_valid, "fresh": fresh,
        "fingerprint_match": fingerprint_match, "result": result,
        "provider_kind": "absent", "release_evidence_eligible": False,
        "detail": detail, "receipt_ref": None, "receipt_bytes_sha256": None,
        "verified_at": _verified_at(verification_time), "provider_timestamp": None,
        "candidate_id": None, "scope_id": None, "verifier_id": None,
    }


def _bundle_location(
    raw: str | Path, contract: Mapping[str, Any],
) -> tuple[str, Path]:
    repository = Path(os.path.abspath(REPO_ROOT))
    canonical_root = repository / str(
        contract["current_repository_evidence"]["evidence_bundle_root"]
    )
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = repository / candidate
    lexical = Path(os.path.abspath(candidate))
    try:
        relative = lexical.relative_to(canonical_root)
    except ValueError as error:
        raise ContractError(
            "evidence bundle path must stay under canonical governance-pipeline run root"
        ) from error
    if (
        len(relative.parts) != 2
        or relative.parts[0] in {"", ".", ".."}
        or relative.name != "bundle.json"
    ):
        raise ContractError("evidence bundle path must be <run-id>/bundle.json")
    return relative.parts[0], lexical


def _canonical_run_root_fd(
    contract: Mapping[str, Any], *, create: bool,
) -> int:
    repository = Path(os.path.abspath(REPO_ROOT))
    root = repository / str(
        contract["current_repository_evidence"]["evidence_bundle_root"]
    )
    try:
        return _safe_directory_fd(
            root, repository_root=repository, physical_root=repository, create=create,
        )
    except (OSError, ValueError) as error:
        raise ContractError(
            f"canonical governance-pipeline run root is unsafe: {_detail(error)}"
        ) from error


def _run_directory_fd(root_fd: int, run_id: str, *, create: bool) -> int:
    if not run_id or "/" in run_id or run_id in {".", ".."}:
        raise ContractError("run_id must be one safe path segment")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        return os.open(run_id, flags, dir_fd=root_fd)
    except FileNotFoundError:
        if not create:
            raise ContractError("evidence bundle run directory does not exist")
        try:
            os.mkdir(run_id, 0o755, dir_fd=root_fd)
        except FileExistsError:
            pass
        try:
            return os.open(run_id, flags, dir_fd=root_fd)
        except OSError as error:
            raise ContractError(
                f"evidence bundle run directory is unsafe: {_detail(error)}"
            ) from error
    except OSError as error:
        raise ContractError(
            f"evidence bundle run directory is unsafe: {_detail(error)}"
        ) from error


def _read_bundle_at(run_fd: int) -> tuple[bytes, os.stat_result]:
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    try:
        descriptor = os.open("bundle.json", flags, dir_fd=run_fd)
    except OSError as error:
        raise ContractError(f"evidence bundle could not be read: {_detail(error)}") from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ContractError("evidence bundle must be one regular single-link file")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 64 * 1024)
            if not chunk:
                return b"".join(chunks), metadata
            chunks.append(chunk)
    finally:
        os.close(descriptor)


def _same_object(left: os.stat_result, right: os.stat_result) -> bool:
    return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)


def _verify_bundle_binding(
    contract: Mapping[str, Any], *, run_id: str,
    root_stat: os.stat_result, run_stat: os.stat_result,
    file_stat: os.stat_result, exact_bytes: bytes,
) -> None:
    check_root_fd = _canonical_run_root_fd(contract, create=False)
    check_run_fd: int | None = None
    try:
        if not _same_object(root_stat, os.fstat(check_root_fd)):
            raise ContractError("canonical governance-pipeline run root was replaced")
        check_run_fd = _run_directory_fd(check_root_fd, run_id, create=False)
        if not _same_object(run_stat, os.fstat(check_run_fd)):
            raise ContractError("evidence bundle run directory was replaced")
        checked_bytes, checked_stat = _read_bundle_at(check_run_fd)
        if not _same_object(file_stat, checked_stat) or checked_bytes != exact_bytes:
            raise ContractError("evidence bundle was replaced during verification")
    finally:
        if check_run_fd is not None:
            os.close(check_run_fd)
        os.close(check_root_fd)


def _write_bundle_create_once(run_fd: int, content: bytes) -> os.stat_result:
    temporary_name = (
        f".bundle.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex}.tmp"
    )
    descriptor: int | None = None
    temporary_created = False
    try:
        try:
            existing, metadata = _read_bundle_at(run_fd)
        except ContractError as error:
            if not isinstance(error.__cause__, FileNotFoundError):
                raise
        else:
            if existing != content:
                raise ContractError("evidence bundle create-once content conflict")
            return metadata
        descriptor = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o644,
            dir_fd=run_fd,
        )
        temporary_created = True
        view = memoryview(content)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError(errno.EIO, "evidence bundle temporary file short write")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        try:
            os.link(
                temporary_name, "bundle.json", src_dir_fd=run_fd,
                dst_dir_fd=run_fd, follow_symlinks=False,
            )
            os.fsync(run_fd)
        except FileExistsError:
            pass
        os.unlink(temporary_name, dir_fd=run_fd)
        temporary_created = False
        exact, metadata = _read_bundle_at(run_fd)
        if exact != content:
            raise ContractError("evidence bundle create-once content conflict")
        return metadata
    except ContractError:
        raise
    except OSError as error:
        raise ContractError(f"evidence bundle create-once failed: {_detail(error)}") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary_created:
            try:
                os.unlink(temporary_name, dir_fd=run_fd)
            except FileNotFoundError:
                pass


def _read_regular(path: Path, *, label: str) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise ContractError(f"{label} could not be read: {_detail(error)}") from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ContractError(f"{label} must be one regular single-link file")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            return handle.read()
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _repo_ref(raw: str, *, label: str, allowed_roots: tuple[str, ...] = (".qwq_output/",)) -> tuple[str, Path, bytes]:
    if not isinstance(raw, str) or not raw or Path(raw).is_absolute() or ".." in Path(raw).parts:
        raise ContractError(f"{label} must be a repository-relative path")
    normalized = Path(raw).as_posix()
    if not any(normalized.startswith(root) for root in allowed_roots):
        raise ContractError(f"{label} is outside allowed receipt roots")
    path = (REPO_ROOT / normalized).resolve()
    try:
        path.relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise ContractError(f"{label} escapes repository") from error
    return normalized, path, _read_regular(path, label=label)


def _portable_bundle_receipt(provider_id: str, receipt_ref: str, raw: bytes) -> dict[str, Any]:
    value = {
        "provider_id": provider_id,
        "receipt_ref": receipt_ref,
        "exact_bytes_base64": base64.b64encode(raw).decode("ascii"),
    }
    validate_exact_fields(value, "bundle_receipt")
    return value


def _bundle_receipt(provider_id: str, receipt_ref: str, raw: bytes) -> dict[str, Any]:
    value = {
        "provider_id": provider_id,
        "receipt_ref": receipt_ref,
        "exact_bytes_base64": base64.b64encode(raw).decode("ascii"),
    }
    validate_exact_fields(value, "bundle_receipt")
    return value


def _decode_bundle_receipt(value: object, *, expected_provider: str, label: str) -> tuple[str, bytes]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{label} bundle receipt missing")
    validate_exact_fields(value, "bundle_receipt")
    if value["provider_id"] != expected_provider:
        raise ContractError(f"{label} provider_id mismatch")
    if not isinstance(value["receipt_ref"], str) or not isinstance(value["exact_bytes_base64"], str):
        raise ContractError(f"{label} bundle receipt types invalid")
    try:
        raw = base64.b64decode(value["exact_bytes_base64"], validate=True)
    except ValueError as error:
        raise ContractError(f"{label} exact bytes base64 invalid") from error
    if label == "handoff":
        import handoff_consumer
        handoff_consumer.validate_published_bytes(
            str(value["receipt_ref"]), raw, validate_current=False
        )
        return str(value["receipt_ref"]), raw
    ref, _path, current = _repo_ref(value["receipt_ref"], label=f"{label} receipt")
    if current != raw:
        raise EvidenceAdapterError.identity(
            f"{label} exact bytes changed after assembly"
        )
    return ref, raw


def subject_fingerprint_receipt(contract: Mapping[str, Any]) -> dict[str, Any]:
    source = contract["current_repository_evidence"]
    managed = list(source["managed_identity_paths"])
    hosted = contract["hosted_authority_source"]
    for key in ("service_contract_refs", "adapter_implementation_refs", "service_implementation_refs", "portal_implementation_refs"):
        managed.extend(hosted[key])
    managed.extend([
        "quwoquan_ops/cli/lib/governance_pipeline_admission/contract.py",
        "quwoquan_ops/cli/lib/governance_pipeline_admission/evaluator.py",
        "quwoquan_ops/cli/lib/governance_pipeline_admission/evidence.py",
        "quwoquan_ops/cli/lib/governance_pipeline_admission/adapters.py",
        "quwoquan_ops/cli/lib/governance_pipeline_admission/read_only_local_readiness.py",
        "quwoquan_ops/cli/governance_pipeline_admission.py",
        "quwoquan_ops/gate/verify_governance_pipeline_admission.py",
    ])
    managed = sorted(set(managed))
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True, capture_output=True, check=True).stdout.strip()
    merge_base = head
    for base in ("dev1.0", "origin/dev1.0", "main", "origin/main"):
        result = subprocess.run(
            ["git", "merge-base", "HEAD", base],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            merge_base = result.stdout.strip()
            break
    adapter_identity = {
        key: snapshot_path(path, repo_root=REPO_ROOT)
        for key, path in {
            "assembler": "quwoquan_ops/cli/lib/governance_pipeline_admission/evidence.py",
            "adapters": "quwoquan_ops/cli/lib/governance_pipeline_admission/adapters.py",
            "local_readiness": "quwoquan_ops/cli/lib/governance_pipeline_admission/read_only_local_readiness.py",
        }.items()
    }
    return build_evidence_fingerprint(
        {
            "git": {"head_sha": head, "merge_base_sha": merge_base},
            "workspace": workspace_digests(managed, repo_root=REPO_ROOT),
            "assets": {
                "canonical_assets_digest": canonical_digest([snapshot_path(path, repo_root=REPO_ROOT) for path in managed]),
                "review_assets_digest": canonical_digest({"owner": contract["owner_story"], "layer_admission": contract["layer_admission"]}),
            },
            "execution": {
                "commands_digest": canonical_digest([]),
                "toolchain_digest": canonical_digest({"python": list(__import__("sys").version_info[:3])}),
                "provider_digest": canonical_digest({"adapters": contract["current_repository_evidence"]["provider_adapters"], "external": contract["current_repository_evidence"]["external_provider_interfaces"]}),
                "generator_digest": canonical_digest(adapter_identity),
            },
        },
        captured_by="governance_pipeline_admission",
        captured_metadata={"consumer": "governance_pipeline_admission"},
    )


def subject_fingerprint(contract: Mapping[str, Any]) -> str:
    return subject_fingerprint_receipt(contract)["digest"]


def _assert_timestamp(readback: dict[str, Any], *, layer: str, contract: Mapping[str, Any], now: datetime) -> None:
    if readback["status"] != "present":
        return
    try:
        verified = datetime.fromisoformat(str(readback["verified_at"]).replace("Z", "+00:00"))
        provider = datetime.fromisoformat(str(readback["provider_timestamp"]).replace("Z", "+00:00"))
    except ValueError as error:
        readback.update(schema_valid=False, fresh=False, detail=f"timestamp invalid: {error}")
        return
    if verified.tzinfo is None or provider.tzinfo is None or provider > verified or verified > now:
        readback.update(fresh=False, detail="provider/verified timestamp order invalid")
        return
    max_age = int(contract["layer_admission"][layer]["max_age_seconds"])
    if (now - provider).total_seconds() > max_age:
        readback.update(fresh=False, detail=f"provider evidence exceeds max_age_seconds={max_age}")


def _assert_layer_policy(readback: dict[str, Any], *, layer: str, subject: Mapping[str, Any], contract: Mapping[str, Any], now: datetime) -> dict[str, Any]:
    if readback["status"] != "present":
        return readback
    policy = contract["layer_admission"][layer]
    if readback["provider_kind"] not in policy["provider_kinds"] or readback["verifier_id"] != policy["verifier_id"]:
        readback.update(schema_valid=False, detail="provider kind/verifier identity is not allowed for layer")
    if readback["release_evidence_eligible"] is not policy["release_evidence_eligible"]:
        readback.update(schema_valid=False, detail="release evidence eligibility differs from layer contract")
    if readback["candidate_id"] != subject["candidate_id"] or readback["scope_id"] != subject["scope_id"]:
        readback.update(fingerprint_match=False, detail="candidate/scope binding mismatch")
    _assert_timestamp(readback, layer=layer, contract=contract, now=now)
    return readback


def _default_receipts() -> dict[str, Any]:
    return {
        "owner_manifest": None,
        "local_scope_ready": None, "local_release_ready": None,
        "review_plan": None, "named_evidence": {}, "review_consolidation": None,
        "handoff": None, "human_calibration": None, "objective_inspect": None,
        "hotl_inspect": None, "hosted_authority_source": None, "external": {},
    }


def assemble_evidence_bundle(
    contract: Mapping[str, Any], *, run_id: str, refs: Mapping[str, Any]
) -> Path:
    """Freeze exact provider-owned receipt bytes; never execute evidence or sign truth."""
    if not run_id or "/" in run_id or run_id in {".", ".."}:
        raise ContractError("run_id must be one safe path segment")
    if not isinstance(refs, Mapping):
        raise ContractError("bundle refs must be an object")
    allowed = set(_default_receipts())
    if set(refs) - allowed:
        raise ContractError(f"bundle refs contain unknown fields: {sorted(set(refs)-allowed)}")
    values = _default_receipts()
    source = contract["current_repository_evidence"]
    provider = source["provider_adapters"]
    singular = {
        "owner_manifest": provider["owner_manifest"]["provider_id"],
        "local_scope_ready": provider["local_readiness"]["provider_id"],
        "local_release_ready": provider["local_readiness"]["provider_id"],
        "review_plan": "review_plan_v4",
        "review_consolidation": provider["review_consolidation"]["provider_id"],
        "handoff": provider["handoff"]["provider_id"],
        "human_calibration": provider["human_calibration"]["provider_id"],
        "objective_inspect": provider["objective_inspect"]["provider_id"],
        "hotl_inspect": provider["hotl_inspect"]["provider_id"],
        "hosted_authority_source": provider["hosted_authority_source"]["provider_id"],
    }
    for key, provider_id in singular.items():
        raw_ref = refs.get(key)
        if raw_ref is None:
            continue
        if key == "handoff":
            import handoff_consumer
            from lib import handoff_store
            ref = str(raw_ref)
            try:
                raw = handoff_store.read(ref, repo_root=REPO_ROOT)
            except handoff_store.HandoffStoreError as error:
                raise ContractError(str(error)) from error
            handoff_consumer.validate_published_bytes(ref, raw, validate_current=False)
            values[key] = _portable_bundle_receipt(provider_id, ref, raw)
            continue
        ref, _path, raw = _repo_ref(str(raw_ref), label=key)
        values[key] = _bundle_receipt(provider_id, ref, raw)
    named = refs.get("named_evidence") or {}
    if not isinstance(named, Mapping):
        raise ContractError("named_evidence refs must be an object")
    values["named_evidence"] = {}
    for key, raw_ref in named.items():
        ref, _path, raw = _repo_ref(str(raw_ref), label=f"named_evidence.{key}")
        values["named_evidence"][str(key)] = _bundle_receipt(provider["named_evidence"]["provider_id"], ref, raw)
    external = refs.get("external") or {}
    if not isinstance(external, Mapping):
        raise ContractError("external refs must be an object")
    values["external"] = {}
    for layer, raw_ref in external.items():
        interface = contract["current_repository_evidence"]["external_provider_interfaces"].get(layer)
        if interface is None:
            raise ContractError(f"external layer has no canonical provider interface: {layer}")
        ref, _path, raw = _repo_ref(str(raw_ref), label=f"external.{layer}")
        values["external"][str(layer)] = _bundle_receipt(str(interface), ref, raw)
    fingerprint = subject_fingerprint_receipt(contract)
    bundle = {
        "schema_id": BUNDLE_SCHEMA_ID, "schema_version": BUNDLE_SCHEMA_VERSION,
        "subject_fingerprint": fingerprint["digest"],
        "subject_fingerprint_receipt": fingerprint,
        "assembled_at": _now(), "receipts": values,
    }
    validate_exact_fields(bundle, "evidence_bundle")
    validate_exact_fields(values, "evidence_bundle_receipts")
    content = canonical_json_bytes(bundle)
    root_fd = _canonical_run_root_fd(contract, create=True)
    run_fd: int | None = None
    try:
        root_stat = os.fstat(root_fd)
        run_fd = _run_directory_fd(root_fd, run_id, create=True)
        run_stat = os.fstat(run_fd)
        file_stat = _write_bundle_create_once(run_fd, content)
    finally:
        if run_fd is not None:
            os.close(run_fd)
        os.close(root_fd)
    _verify_bundle_binding(
        contract, run_id=run_id, root_stat=root_stat, run_stat=run_stat,
        file_stat=file_stat, exact_bytes=content,
    )
    repository = Path(os.path.abspath(REPO_ROOT))
    return repository / str(source["evidence_bundle_root"]) / run_id / "bundle.json"


def load_evidence_bundle(raw: str | Path, *, contract: Mapping[str, Any]) -> dict[str, Any]:
    run_id, _path = _bundle_location(raw, contract)
    root_fd = _canonical_run_root_fd(contract, create=False)
    run_fd: int | None = None
    try:
        root_stat = os.fstat(root_fd)
        run_fd = _run_directory_fd(root_fd, run_id, create=False)
        run_stat = os.fstat(run_fd)
        encoded, file_stat = _read_bundle_at(run_fd)
    finally:
        if run_fd is not None:
            os.close(run_fd)
        os.close(root_fd)
    try:
        value = json.loads(encoded.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ContractError(f"evidence bundle JSON invalid: {error}") from error
    if not isinstance(value, dict):
        raise ContractError("evidence bundle must be a JSON object")
    validate_exact_fields(value, "evidence_bundle")
    if value["schema_id"] != BUNDLE_SCHEMA_ID or value["schema_version"] != BUNDLE_SCHEMA_VERSION:
        raise ContractError("evidence bundle identity/version invalid")
    validate_exact_fields(value["receipts"], "evidence_bundle_receipts")
    actual = validate_evidence_fingerprint(value["subject_fingerprint_receipt"])
    current = subject_fingerprint_receipt(contract)
    for field in ("ref", "digest", "digest_payload"):
        if actual[field] != current[field]:
            raise EvidenceAdapterError.stale(
                f"evidence bundle managed source fingerprint stale: {field}"
            )
    if value["subject_fingerprint"] != actual["digest"]:
        raise EvidenceAdapterError.identity(
            "evidence bundle subject fingerprint mismatch"
        )
    _verify_bundle_binding(
        contract, run_id=run_id, root_stat=root_stat, run_stat=run_stat,
        file_stat=file_stat, exact_bytes=encoded,
    )
    return value


def _named_binding_context(
    bundle: Mapping[str, Any], contract: Mapping[str, Any],
) -> tuple[str, str, bytes, dict[str, Any]]:
    receipts = bundle["receipts"]
    if receipts["review_plan"] is None:
        raise EvidenceAdapterError.identity(
            "named evidence exact Review plan receipt missing"
        )
    if receipts["owner_manifest"] is None:
        raise EvidenceAdapterError.identity(
            "named evidence exact owner manifest receipt missing"
        )
    owner_ref, _owner_raw = _decode_bundle_receipt(
        receipts["owner_manifest"],
        expected_provider=contract["current_repository_evidence"]["provider_adapters"]["owner_manifest"]["provider_id"],
        label="named evidence owner_manifest",
    )
    plan_ref, plan_raw = _decode_bundle_receipt(
        receipts["review_plan"], expected_provider="review_plan_v4",
        label="named evidence review_plan",
    )
    try:
        plan = json.loads(plan_raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EvidenceAdapterError.schema(
            f"named evidence Review plan JSON invalid: {error}"
        ) from error
    if not isinstance(plan, dict):
        raise EvidenceAdapterError.schema(
            "named evidence Review plan must be a JSON object"
        )
    return owner_ref, plan_ref, plan_raw, plan


def _decode_and_bind_named_receipt(
    value: object, *, layer: str, expected_evidence_id: str,
    plan: dict[str, Any], owner_manifest_ref: str,
    subject: Mapping[str, Any], contract: Mapping[str, Any],
) -> tuple[str, bytes, dict[str, Any]]:
    ref, raw = _decode_bundle_receipt(
        value,
        expected_provider=contract["current_repository_evidence"]["provider_adapters"]["named_evidence"]["provider_id"],
        label=layer,
    )
    try:
        receipt = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EvidenceAdapterError.schema(
            f"{layer} named evidence JSON invalid: {error}"
        ) from error
    if not isinstance(receipt, dict):
        raise EvidenceAdapterError.schema(
            f"{layer} named evidence must be a JSON object"
        )
    import evidence_runner
    try:
        evidence_runner.validate_named_evidence_receipt(receipt)
    except Exception as error:
        raise EvidenceAdapterError.schema(
            str(error) or type(error).__name__
        ) from error
    try:
        governance_contract.validate_named_evidence_plan_binding(
            plan=plan, receipt=receipt, subject=subject,
            expected_owner_identity_ref=owner_manifest_ref,
            expected_candidate_evidence_ref=str((plan.get("candidate_evidence_identity") or {}).get("ref") or ""),
            contract=contract,
            label=f"{layer}:{expected_evidence_id}",
        )
    except EvidenceAdapterError:
        raise
    except ContractError as error:
        raise EvidenceAdapterError.identity(
            str(error) or type(error).__name__
        ) from error
    return ref, raw, receipt


def _named_receipts(bundle: Mapping[str, Any], contract: Mapping[str, Any], *, subject: Mapping[str, Any], now: datetime) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    named = bundle["receipts"]["named_evidence"]
    if not isinstance(named, Mapping):
        raise ContractError("named_evidence bundle field must be an object")
    mapping = contract["current_repository_evidence"]["named_evidence_layers"]
    context: tuple[str, str, bytes, dict[str, Any]] | None = None
    context_error: Exception | None = None
    if named:
        try:
            context = _named_binding_context(bundle, contract)
        except Exception as error:
            context_error = error
    for layer, descriptor in mapping.items():
        value = named.get(descriptor["evidence_id"])
        if value is None:
            output[layer] = _absent(
                detail=f"named evidence {descriptor['evidence_id']} missing",
                verification_time=now,
            )
            continue
        try:
            if context_error is not None:
                raise context_error
            if context is None:
                raise EvidenceAdapterError.identity(
                    "named evidence exact plan/owner binding unavailable"
                )
            owner_ref, _plan_ref, _plan_raw, plan = context
            ref, raw, receipt = _decode_and_bind_named_receipt(
                value, layer=layer,
                expected_evidence_id=str(descriptor["evidence_id"]),
                plan=plan, owner_manifest_ref=owner_ref, subject=subject,
                contract=contract,
            )
            if receipt["terminal"] != {"status": "PASS", "code": "EVIDENCE.PASSED", "failed_evidence": None}:
                raise ContractError("named evidence terminal is not PASS")
            item = next((item for item in receipt["evidence"] if item["id"] == descriptor["evidence_id"]), None)
            if item is None or item["exit_code"] != 0:
                raise ContractError("named evidence id/exit code is not qualifying")
            readback = adapters._readback(
                result=descriptor["qualifying_result"], provider_kind="local_runtime", release=False,
                receipt_ref=ref, raw=raw, provider_timestamp=str(item["finished_at"]),
                candidate_id=str(subject["candidate_id"]), scope_id=str(subject["scope_id"]),
                verifier_id=contract["layer_admission"][layer]["verifier_id"],
                verification_time=now,
            )
            output[layer] = _assert_layer_policy(readback, layer=layer, subject=subject, contract=contract, now=now)
        except Exception as error:
            output[layer] = _failed(error, verification_time=now)
    unknown = set(named) - {item["evidence_id"] for item in mapping.values()}
    if unknown:
        raise ContractError(f"named evidence ids are not canonical for governance: {sorted(unknown)}")
    return output


def current_repository_input(
    contract: Mapping[str, Any], *, evidence_bundle: str | Path | None = None,
    external_verifiers: Mapping[str, adapters.ExternalVerifier] | None = None,
    verification_time: datetime | None = None,
) -> dict[str, Any]:
    now = _verification_time(verification_time)
    fingerprint = subject_fingerprint(contract)
    subject = {"subject_id": "current-repository", "scope_id": "governance-pipeline", "candidate_id": "working-tree", "evidence_fingerprint": fingerprint}
    evidence = {
        name: _absent(
            detail=f"receipt for {name} missing", verification_time=now,
        )
        for name in contract["evidence_layers"]
    }
    if evidence_bundle is None:
        return {"subject": subject, "evidence": evidence, "human_calibration_readback": None, "activation_receipt": None}
    try:
        bundle = load_evidence_bundle(evidence_bundle, contract=contract)
    except Exception as error:
        failed = _failed(error, verification_time=now)
        evidence = {name: dict(failed) for name in contract["evidence_layers"]}
        return {
            "subject": subject, "evidence": evidence,
            "human_calibration_readback": None, "activation_receipt": None,
        }
    receipts = bundle["receipts"]
    # One bundle consumption has exactly one timezone-aware verification clock.
    manifest_ref: str | None = None
    try:
        manifest_ref, manifest_raw = _decode_bundle_receipt(receipts["owner_manifest"], expected_provider=contract["current_repository_evidence"]["provider_adapters"]["owner_manifest"]["provider_id"], label="owner_manifest")
        readback, _ = adapters.verify_owner_manifest(
            raw=manifest_raw, receipt_ref=manifest_ref,
            candidate_id=subject["candidate_id"], scope_id=subject["scope_id"],
            verification_time=now, contract=contract,
        )
        evidence["owner_manifest"] = _assert_layer_policy(readback, layer="owner_manifest", subject=subject, contract=contract, now=now)
    except Exception as error:
        evidence["owner_manifest"] = (
            _failed(error, verification_time=now)
            if receipts["owner_manifest"] is not None
            else _failed(
                "required owner manifest receipt missing", verification_time=now,
            )
        )
    for level in ("scope", "release"):
        layer = f"local_{level}_ready"
        try:
            if manifest_ref is None:
                raise ContractError("owner manifest ref unavailable")
            ref, raw = _decode_bundle_receipt(receipts[layer], expected_provider=contract["current_repository_evidence"]["provider_adapters"]["local_readiness"]["provider_id"], label=layer)
            readback = adapters.verify_local_readiness(
                level=level, raw=raw, receipt_ref=ref,
                owner_manifest_ref=manifest_ref, candidate_id=subject["candidate_id"],
                scope_id=subject["scope_id"], verification_time=now, contract=contract,
            )
            evidence[layer] = _assert_layer_policy(readback, layer=layer, subject=subject, contract=contract, now=now)
        except Exception as error:
            evidence[layer] = (
                _failed(error, verification_time=now)
                if receipts[layer] is not None
                else _absent(detail=f"{layer} receipt missing", verification_time=now)
            )
    try:
        owner_ref, plan_ref, plan_raw, plan = _named_binding_context(bundle, contract)
        named_receipts = receipts["named_evidence"]
        if not isinstance(named_receipts, Mapping):
            raise ContractError("named_evidence bundle field must be an object")
        bound_named: list[tuple[str, bytes]] = []
        for layer, descriptor in contract["current_repository_evidence"]["named_evidence_layers"].items():
            value = named_receipts.get(descriptor["evidence_id"])
            if value is None:
                continue
            evidence_ref, evidence_raw, _receipt = _decode_and_bind_named_receipt(
                value, layer=layer,
                expected_evidence_id=str(descriptor["evidence_id"]),
                plan=plan, owner_manifest_ref=owner_ref, subject=subject,
                contract=contract,
            )
            bound_named.append((evidence_ref, evidence_raw))
        if not bound_named:
            raise EvidenceAdapterError.identity(
                "Review named evidence exact receipt missing"
            )
        consolidation_ref, consolidation_raw = _decode_bundle_receipt(receipts["review_consolidation"], expected_provider=contract["current_repository_evidence"]["provider_adapters"]["review_consolidation"]["provider_id"], label="review_consolidation")
        consolidation = json.loads(consolidation_raw.decode("utf-8"))
        if not isinstance(consolidation, dict):
            raise ContractError("Review consolidation must be an object")
        bound_by_ref = {ref: raw for ref, raw in bound_named}
        consolidation_identities = consolidation.get("evidence_identities") or []
        if len(consolidation_identities) != 1:
            raise ContractError("Review consolidation must bind one exact named evidence receipt")
        evidence_ref = str(consolidation_identities[0].get("receipt_ref") or "")
        evidence_raw = bound_by_ref.get(evidence_ref)
        if evidence_raw is None:
            raise EvidenceAdapterError.identity(
                "Review consolidation exact evidence ref is not supplied"
            )
        reviewer_result_pairs: list[tuple[str, bytes]] = []
        for identity in consolidation.get("reviewer_result_identities") or []:
            if not isinstance(identity, Mapping):
                raise ContractError("Review consolidation reviewer identity invalid")
            result_ref, _result_path, result_raw = _repo_ref(
                str(identity.get("result_ref") or ""), label="reviewer_result"
            )
            reviewer_result_pairs.append((result_ref, result_raw))
        readback = adapters.verify_review(
            plan_raw=plan_raw, plan_ref=plan_ref, evidence_raw=evidence_raw,
            evidence_ref=evidence_ref, reviewer_result_pairs=reviewer_result_pairs,
            consolidation_raw=consolidation_raw,
            consolidation_ref=consolidation_ref, candidate_id=subject["candidate_id"],
            scope_id=subject["scope_id"], verification_time=now, contract=contract,
        )
        evidence["review_terminal"] = _assert_layer_policy(readback, layer="review_terminal", subject=subject, contract=contract, now=now)
    except Exception as error:
        review_supplied = (
            receipts["review_plan"] is not None
            or receipts["review_consolidation"] is not None
            or bool(receipts["named_evidence"])
        )
        evidence["review_terminal"] = (
            _failed(error, verification_time=now)
            if review_supplied
            else _absent(detail="Review receipts missing", verification_time=now)
        )
    evidence.update(_named_receipts(bundle, contract, subject=subject, now=now))
    try:
        ref, raw = _decode_bundle_receipt(receipts["handoff"], expected_provider=contract["current_repository_evidence"]["provider_adapters"]["handoff"]["provider_id"], label="handoff")
        readback = adapters.verify_handoff(
            raw=raw, receipt_ref=ref, candidate_id=subject["candidate_id"],
            scope_id=subject["scope_id"], verification_time=now, contract=contract,
        )
        evidence["handoff_freshness"] = _assert_layer_policy(readback, layer="handoff_freshness", subject=subject, contract=contract, now=now)
    except Exception as error:
        evidence["handoff_freshness"] = (
            _failed(error, verification_time=now)
            if receipts["handoff"] is not None
            else _absent(detail="handoff receipt missing", verification_time=now)
        )
    verifiers = dict(external_verifiers or {})
    human_readback = None
    try:
        ref, raw = _decode_bundle_receipt(receipts["human_calibration"], expected_provider=contract["current_repository_evidence"]["provider_adapters"]["human_calibration"]["provider_id"], label="human_calibration")
        decoded = json.loads(raw)
        if not isinstance(decoded, Mapping):
            raise ContractError("Human calibration readback must be an object")
        session_bytes_by_ref: dict[str, bytes] = {}
        for item in decoded.get("session_refs") or ():
            if not isinstance(item, Mapping) or not isinstance(item.get("ref"), str):
                raise ContractError("HAD.CALIBRATION_CONTRACT_INCOMPATIBLE: session ref missing")
            logical_ref = str(item["ref"])
            if logical_ref.startswith("sessions/"):
                stored_ref = (Path(ref).parent / logical_ref.removeprefix("sessions/")).as_posix()
            else:
                stored_ref = logical_ref
            _stored_ref, _session_path, session_raw = _repo_ref(stored_ref, label="Human calibration session", allowed_roots=(".qwq_output/",))
            session_bytes_by_ref[logical_ref] = session_raw
        readback, human_readback = adapters.verify_human_readback(
            raw=raw, receipt_ref=ref, candidate_id=subject["candidate_id"], scope_id=subject["scope_id"],
            evidence_fingerprint=subject["evidence_fingerprint"], session_bytes_by_ref=session_bytes_by_ref,
            provider_timestamp=str(decoded.get("generated_at", "")), verification_time=now,
            verifier=verifiers.get("human_calibration"), contract=contract,
        )
        evidence["human_calibration"] = _assert_layer_policy(readback, layer="human_calibration", subject=subject, contract=contract, now=now)
    except Exception as error:
        evidence["human_calibration"] = (
            _failed(error, verification_time=now)
            if receipts["human_calibration"] is not None
            else _absent(
                "not_observed", detail="Human calibration readback missing",
                verification_time=now,
            )
        )
    for layer, key, provider_key, verifier in (
        ("objective_readback", "objective_inspect", "objective_inspect", adapters.objective_readback),
        ("hotl_inspect", "hotl_inspect", "hotl_inspect", adapters.verify_hotl),
        ("hosted_authority_code", "hosted_authority_source", "hosted_authority_source", adapters.verify_hosted_source),
    ):
        try:
            ref, raw = _decode_bundle_receipt(receipts[key], expected_provider=contract["current_repository_evidence"]["provider_adapters"][provider_key]["provider_id"], label=key)
            readback = verifier(
                raw=raw, receipt_ref=ref, candidate_id=subject["candidate_id"],
                scope_id=subject["scope_id"], verification_time=now, contract=contract,
            )
            evidence[layer] = _assert_layer_policy(readback, layer=layer, subject=subject, contract=contract, now=now)
        except Exception as error:
            evidence[layer] = (
                _failed(error, verification_time=now)
                if receipts[key] is not None
                else _absent(
                    "code_absent" if layer == "hosted_authority_code" else "not_executed",
                    detail=f"{key} receipt missing", verification_time=now,
                )
            )
    external = receipts["external"]
    if not isinstance(external, Mapping):
        raise ContractError("external receipts must be an object")
    for layer, value in external.items():
        if layer not in contract["layer_admission"]:
            raise ContractError(f"external layer is unknown: {layer}")
        try:
            provider_id = contract["layer_admission"][layer]["provider_id"]
            ref, raw = _decode_bundle_receipt(value, expected_provider=provider_id, label=f"external.{layer}")
            readback = adapters.verify_external(
                layer=layer, raw=raw, receipt_ref=ref, verifier=verifiers.get(layer),
                subject=subject, verification_time=now, contract=contract,
            )
            evidence[layer] = _assert_layer_policy(readback, layer=layer, subject=subject, contract=contract, now=now)
        except Exception as error:
            evidence[layer] = _failed(error, verification_time=now)
    hosted_refs = contract["hosted_authority_source"]
    all_refs = [*hosted_refs["service_contract_refs"], *hosted_refs["adapter_implementation_refs"], *hosted_refs["service_implementation_refs"], *hosted_refs["portal_implementation_refs"]]
    if evidence["hosted_authority_code"]["status"] == "absent":
        missing = [ref for ref in all_refs if not (REPO_ROOT / ref).is_file()]
        evidence["hosted_authority_code"]["result"] = "code_absent" if missing else "code_present"
        evidence["hosted_authority_code"]["detail"] = "required source absent: " + ",".join(missing) if missing else "canonical code exists; provider inspect receipt missing"
    return {
        "subject": subject, "evidence": evidence,
        "human_calibration_readback": human_readback,
        "activation_receipt": None,
    }
