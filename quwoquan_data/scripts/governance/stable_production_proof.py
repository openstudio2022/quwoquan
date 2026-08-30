"""Schema-bound OPEN-006 proof request and read-only retirement projection."""
from __future__ import annotations

import json
import os
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.execution import stable_production_proof as stable
from content.execution.stable_production_proof import StableProductionProofError
from content.execution.operational_fingerprint import operational_fingerprint
from core.paths import REPO_ROOT
from core.schema import assert_valid

REQUEST_SCHEMA = "quwoquan_data.stable_production_proof_request"
RETIREMENT_PRECHECK_SCHEMA = "quwoquan_data.legacy_retirement_precheck"
RETIREMENT_INVENTORY_SCHEMA = "quwoquan_data.legacy_orchestration_retirement_inventory"
RETIREMENT_INVENTORY_RELATIVE = "quwoquan_data/control_plane/execution/legacy_orchestration_retirement.json"
RETIREMENT_PRECHECK_STATES = ("operationally_retired",)


def _decode_json_object(raw: bytes, label: str) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        document: dict[str, Any] = {}
        for key, value in pairs:
            if key in document:
                raise StableProductionProofError(
                    f"{label} contains duplicate JSON key {key!r}"
                )
            document[key] = value
        return document

    try:
        text = raw.decode("utf-8")
        decoder = json.JSONDecoder(
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda value: (_ for _ in ()).throw(
                StableProductionProofError(
                    f"{label} contains invalid JSON constant {value}"
                )
            ),
        )
        value, end = decoder.raw_decode(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StableProductionProofError(f"{label} must be UTF-8 JSON") from exc
    if text[end:].strip() or not isinstance(value, dict):
        raise StableProductionProofError(f"{label} must contain one JSON object")
    return value


def load_stable_production_proof_request(path: Path) -> dict[str, Any]:
    request_path = Path(path).expanduser()
    try:
        if request_path.is_symlink():
            raise OSError("symbolic request files are not accepted")
        raw = stable._read_regular_nofollow(request_path.resolve(strict=True))
    except OSError as exc:
        raise StableProductionProofError(
            f"stable production proof request is unavailable: {exc}"
        ) from exc
    request = _decode_json_object(raw, "stable production proof request")
    assert_valid(
        request,
        "execution",
        "stable_production_proof_request",
        label="stable-production-proof request",
    )
    if request.get("schema") != REQUEST_SCHEMA:
        raise StableProductionProofError("stable production proof request schema drifted")
    return request


def evaluate_stable_production_proof_request(
    *, request: Mapping[str, Any], artifact_root: Path | None = None
) -> dict[str, Any]:
    assert_valid(
        dict(request),
        "execution",
        "stable_production_proof_request",
        label="stable-production-proof request",
    )
    if request.get("schema") != REQUEST_SCHEMA:
        raise StableProductionProofError("stable production proof request schema drifted")
    expected = operational_fingerprint()
    if request.get("fingerprint") != expected:
        raise StableProductionProofError(
            f"stable operational fingerprint drifted: expected {expected}, got {request.get('fingerprint')}"
        )
    request_root = request.get("artifactRoot")
    if request_root is not None and artifact_root is not None:
        raise StableProductionProofError(
            "artifactRoot must be supplied by the request or CLI argument, not both"
        )
    selected_root = artifact_root if artifact_root is not None else request_root
    if selected_root is None:
        raise StableProductionProofError(
            "artifactRoot is missing; provide request.artifactRoot or --artifact-root"
        )
    return stable.evaluate_stable_production_proof(
        artifact_root=Path(str(selected_root)),
        expected_fingerprint=request.get("fingerprint", ""),
        proof_units=request.get("proofUnits", []),
    )


def _canonical_bytes(document: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(document), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8") + b"\n"


def write_local_run_evidence_create_once(
    *, output: Path, document: Mapping[str, Any]
) -> Path:
    destination = Path(output).expanduser()
    body = _canonical_bytes(document)
    try:
        if destination.is_symlink():
            raise StableProductionProofError(
                f"create-once output is a symbolic link: {destination}"
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        parent = destination.parent.resolve(strict=True)
        if not stat.S_ISDIR(parent.stat().st_mode):
            raise StableProductionProofError(
                f"create-once output parent is not a directory: {destination.parent}"
            )
        descriptor = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except FileExistsError:
        existing = stable._read_regular_nofollow(destination)
        if existing != body:
            raise StableProductionProofError(
                f"create-once output collision: {destination}"
            ) from None
        return destination
    except OSError as exc:
        raise StableProductionProofError(
            f"create-once output cannot be written safely: {destination}: {exc}"
        ) from exc
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        try:
            destination.unlink()
        except OSError:
            pass
        raise
    return destination


def _inventory_binding(path: Path, raw_path: Path) -> dict[str, str]:
    try:
        ref = path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        ref = raw_path.as_posix()
    return {"ref": ref, "exactByteDigest": stable.exact_byte_digest(path)}


def load_retirement_inventory(path: Path) -> tuple[dict[str, Any], dict[str, str]]:
    inventory_path = Path(path).expanduser()
    try:
        if inventory_path.is_symlink():
            raise OSError("symbolic inventory files are not accepted")
        resolved = inventory_path.resolve(strict=True)
        raw = stable._read_regular_nofollow(resolved)
    except OSError as exc:
        raise StableProductionProofError(
            f"retirement inventory is unavailable: {exc}"
        ) from exc
    inventory = _decode_json_object(raw, "retirement inventory")
    expected_keys = {
        "schema",
        "state",
        "deleteFamilies",
        "preserveProtocolKernels",
        "forbiddenCompatibility",
    }
    if set(inventory) != expected_keys:
        raise StableProductionProofError("retirement inventory fields mismatch")
    expected = {
        "schema": RETIREMENT_INVENTORY_SCHEMA,
        "deleteFamilies": ["agent", "queue", "controller", "recovery", "campaign"],
        "preserveProtocolKernels": ["closure", "runtime_evidence", "scale"],
        "forbiddenCompatibility": ["alias", "dual_read", "dual_write", "shim"],
    }
    for key, value in expected.items():
        if inventory.get(key) != value:
            raise StableProductionProofError(f"retirement inventory {key} drifted")
    state = inventory.get("state")
    if state not in {"pre_delete", "operationally_retired", "retired"}:
        raise StableProductionProofError("retirement inventory state is invalid")
    return inventory, _inventory_binding(resolved, inventory_path)


def evaluate_legacy_retirement_precheck(
    *,
    artifact_root: Path | None,
    expected_fingerprint: str | None,
    stable_production_proof_ref: object,
    retirement_inventory: Path,
) -> dict[str, Any]:
    missing: list[str] = []
    proof: dict[str, Any] | None = None
    proof_binding: dict[str, str] | None = None
    proof_error: str | None = None
    if artifact_root is None:
        missing.append("artifact root for the stable production proof exact ref")
    if expected_fingerprint is None:
        missing.append("current pre-delete fingerprint")
    if stable_production_proof_ref is None:
        missing.append("stable production proof exact ref and digest")
    if not missing:
        try:
            root = stable._safe_root(Path(artifact_root))
            fingerprint = stable._digest(expected_fingerprint, "expectedFingerprint")
            proof, proof_binding = stable._load_exact_json(
                root, stable_production_proof_ref, "stableProductionProof"
            )
            assert_valid(
                proof,
                "execution",
                "stable_production_proof_set",
                label="stableProductionProof",
            )
            if proof.get("schema") != stable.SCHEMA or proof.get("verdict") != "pass":
                raise StableProductionProofError(
                    "stable production proof result is not a passing canonical proof set"
                )
            if proof.get("expectedFingerprint") != fingerprint:
                raise StableProductionProofError(
                    "stable production proof does not bind the current pre-delete fingerprint"
                )
        except (OSError, ValueError) as exc:
            proof = None
            proof_binding = None
            proof_error = str(exc)
            missing.append("current stable production proof for exactly three independent four-carrier units")

    inventory: dict[str, Any] | None = None
    inventory_ref: dict[str, str] | None = None
    inventory_error: str | None = None
    try:
        inventory, inventory_ref = load_retirement_inventory(retirement_inventory)
    except (OSError, ValueError) as exc:
        inventory_error = str(exc)
        missing.append("current legacy orchestration retirement inventory")

    inventory_state = inventory.get("state") if inventory is not None else "unavailable"
    if inventory is not None and inventory_state not in RETIREMENT_PRECHECK_STATES:
        missing.append("retirement inventory state operationally_retired")
    missing = list(dict.fromkeys(missing))
    eligibility = "eligible" if not missing else "not_eligible"
    summary = (
        "Pre-delete retirement prerequisites are current and complete; this read-only "
        "result does not change inventory state or delete anything."
        if eligibility == "eligible"
        else "Not eligible for pre-delete retirement. Missing or invalid prerequisites: "
        + "; ".join(missing)
        + ". No inventory state was changed and nothing was deleted."
    )
    result = {
        "schema": RETIREMENT_PRECHECK_SCHEMA,
        "openItemRef": stable.OPEN_ITEM_REF,
        "phase": "pre_delete",
        "eligibility": eligibility,
        "stableProductionProof": (
            {
                "exactRef": proof_binding,
                "schema": proof["schema"],
                "expectedFingerprint": proof["expectedFingerprint"],
                "releaseIds": proof["releaseIds"],
                "proofUnitCount": proof["proofUnitCount"],
                "executionCount": proof["executionCount"],
                "verdict": proof["verdict"],
            }
            if proof is not None and proof_binding is not None
            else None
        ),
        "retirementInventory": (
            {"state": inventory_state, "exactRef": inventory_ref}
            if inventory is not None and inventory_ref is not None
            else None
        ),
        "missingPrerequisites": missing,
        "typedBlocker": (
            None
            if eligibility == "eligible"
            else {
                "code": "DATA.LEGACY_RETIREMENT.PRECHECK_NOT_ELIGIBLE",
                "message": summary,
                "causes": [
                    value for value in (proof_error, inventory_error) if value is not None
                ],
            }
        ),
        "humanSummary": summary,
        "stateChanged": False,
        "deletedRefs": [],
    }
    assert_valid(
        result,
        "execution",
        "legacy_retirement_precheck",
        label="legacy-retirement-precheck",
    )
    return result


__all__ = [
    "REQUEST_SCHEMA",
    "RETIREMENT_INVENTORY_RELATIVE",
    "RETIREMENT_INVENTORY_SCHEMA",
    "RETIREMENT_PRECHECK_SCHEMA",
    "StableProductionProofError",
    "evaluate_legacy_retirement_precheck",
    "evaluate_stable_production_proof_request",
    "load_retirement_inventory",
    "load_stable_production_proof_request",
    "write_local_run_evidence_create_once",
]
