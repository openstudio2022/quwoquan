"""Project canonical app-content UAT blockers and promotability."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.lib.app_launch_attempt import (
    LAUNCH_BLOCKERS,
    read_app_launch_attempt,
)

APP_CONTENT_UAT_RECEIPT_INVALID = "APP.LAUNCH.receipt_invalid"
_APP_ERROR_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]*(?:\.[A-Za-z0-9_]+){2,}$")
_OPERATION_ID_RE = re.compile(r"^[a-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+$")
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def app_content_uat_non_promotable(
    *,
    profile: str,
    device_class: str,
    registered: bool,
) -> bool:
    """Project promotability only from the explicit UAT profile/device facts."""

    if profile == "rehearsal":
        if device_class not in {"simulator", "emulator"}:
            raise ValueError(
                "app-content-uat rehearsal profile requires a simulator or emulator"
            )
        return True
    if profile in {"promotable", "production"}:
        if device_class != "physical" or registered is not True:
            raise ValueError(
                f"app-content-uat {profile} profile requires a registered physical device"
            )
        return False
    raise ValueError("app-content-uat UAT profile is unsupported")


def _read_registered_device_lease(
    lease_ref: str | Path,
    *,
    platform: str,
    device_id: str,
) -> dict[str, Any]:
    """Read registration only from one actively-held canonical device lease."""

    path = Path(lease_ref).expanduser().absolute()
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ValueError("APP.UAT.device_registration_missing: device lease is unavailable") from exc
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) & 0o077
    ):
        raise ValueError("APP.UAT.device_registration_invalid: device lease is unsafe")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("APP.UAT.device_registration_invalid: device lease is unreadable") from exc
    if not isinstance(payload, Mapping):
        raise ValueError("APP.UAT.device_registration_invalid: device lease is malformed")
    owner_ref = payload.get("leaseOwnerRef")
    if not isinstance(owner_ref, str) or not owner_ref or owner_ref != owner_ref.strip():
        raise ValueError("APP.UAT.device_registration_invalid: active lease owner is missing")
    owner_path = Path(owner_ref).expanduser()
    if not owner_path.is_absolute() or owner_path.name != "owner.json":
        raise ValueError("APP.UAT.device_registration_invalid: active lease owner is invalid")
    try:
        owner_metadata = owner_path.lstat()
        owner = json.loads(owner_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("APP.UAT.device_registration_invalid: active lease owner is unavailable") from exc
    host_digest = str(payload.get("hostDigest") or "")
    device_digest = str(payload.get("deviceIdDigest") or "")
    expected_lease_key = hashlib.sha256(
        f"{payload.get('platform')}\0{host_digest}\0{device_digest}".encode("utf-8")
    ).hexdigest()
    if (
        owner_path.is_symlink()
        or not stat.S_ISREG(owner_metadata.st_mode)
        or stat.S_IMODE(owner_metadata.st_mode) & 0o077
        or owner_path.parent.name != f"{payload.get('platform')}-{expected_lease_key}"
        or not isinstance(owner, Mapping)
        or _DIGEST_RE.fullmatch(str(owner.get("tokenDigest") or "")) is None
        or not hmac.compare_digest(
            str(owner.get("leaseId") or ""), str(payload.get("leaseId") or "")
        )
    ):
        raise ValueError("APP.UAT.device_registration_invalid: device lease is not actively held")
    expected_platform = "ios" if platform == "ios-physical" else "android"
    expected_target = "ios" if expected_platform == "ios" else "android"
    expected_device_digest = "sha256:" + hashlib.sha256(
        ("quwoquan-mobile-device\0" + device_id).encode("utf-8")
    ).hexdigest()
    expected_runner = f"mobile-{expected_platform}"
    if (
        payload.get("status") != "held"
        or payload.get("platform") != expected_platform
        or payload.get("deviceClass") != "physical"
        or payload.get("deviceRegistered") is not True
        or payload.get("deviceIdDigest") != expected_device_digest
        or payload.get("runnerLabel") != expected_runner
        or not str(payload.get("targetPlatform") or "").strip().lower().startswith(
            expected_target
        )
        or _DIGEST_RE.fullmatch(str(payload.get("hostDigest") or "")) is None
        or _DIGEST_RE.fullmatch(str(payload.get("leaseId") or "")) is None
    ):
        raise ValueError(
            "APP.UAT.device_registration_invalid: device lease does not bind one registered physical device"
        )
    return dict(payload)


def app_content_uat_cli_profile(
    *,
    platform: str,
    device_id: str,
    device_registration_ref: str | Path = "",
) -> dict[str, Any]:
    """Resolve an explicit UAT profile from platform plus registered device facts."""

    normalized_platform = str(platform or "").strip().lower()
    if normalized_platform == "ios-simulator":
        profile = "rehearsal"
        device_class = "simulator"
        registered = False
    elif normalized_platform == "android":
        profile = "rehearsal"
        device_class = "emulator"
        registered = False
    elif normalized_platform in {"android-physical", "ios-physical"}:
        if not str(device_registration_ref or "").strip():
            raise ValueError(
                "APP.UAT.device_registration_missing: promotable physical UAT requires --device-registration-ref"
            )
        _read_registered_device_lease(
            device_registration_ref,
            platform=normalized_platform,
            device_id=device_id,
        )
        profile = "promotable"
        device_class = "physical"
        registered = True
    else:
        raise ValueError("app-content-uat platform is unsupported")
    return {
        "profile": profile,
        "deviceClass": device_class,
        "deviceRegistered": registered,
        "nonPromotable": app_content_uat_non_promotable(
            profile=profile,
            device_class=device_class,
            registered=registered,
        ),
    }


def _canonical_direct_code(value: object) -> str:
    return (
        value
        if isinstance(value, str)
        and value
        and value == value.strip()
        and value in LAUNCH_BLOCKERS
        else ""
    )


def _canonical_typed_code(
    value: object,
    *,
    contract_graph_digest: object = "",
) -> str:
    if not isinstance(value, Mapping):
        return ""
    code = _canonical_direct_code(value.get("errorCode"))
    if code:
        return code
    raw_code = value.get("errorCode")
    operation = value.get("sourceOperationId")
    status = value.get("httpStatus")
    if (
        isinstance(raw_code, str)
        and raw_code == raw_code.strip()
        and _APP_ERROR_CODE_RE.fullmatch(raw_code) is not None
        and isinstance(operation, str)
        and operation == operation.strip()
        and _OPERATION_ID_RE.fullmatch(operation) is not None
        and isinstance(contract_graph_digest, str)
        and _DIGEST_RE.fullmatch(contract_graph_digest) is not None
        and (
            status is None
            or (
                isinstance(status, int)
                and not isinstance(status, bool)
                and 100 <= status <= 599
            )
        )
    ):
        # app_preflight_uat_page_evidence has already verified this pair against
        # the exact candidate ContractGraph before projecting the digest here.
        return raw_code
    return ""


def _failed(record: Mapping[str, Any]) -> bool:
    status = record.get("status")
    exit_code = record.get("exitCode")
    return status in {"gate_block", "failed", "blocked"} or (
        isinstance(exit_code, int)
        and not isinstance(exit_code, bool)
        and exit_code != 0
    )


def _launch_attempt_blocker(run: Mapping[str, Any]) -> tuple[str, str]:
    embedded = run.get("launchAttemptEvidence")
    if isinstance(embedded, Mapping):
        code = _canonical_direct_code(embedded.get("firstBlocker"))
        if code:
            return code, "launch_attempt"
    reference = run.get("launchAttemptRef")
    if not isinstance(reference, str) or not reference or reference != reference.strip():
        binding = run.get("launchBinding")
        reference = (
            binding.get("launchAttemptRef")
            if isinstance(binding, Mapping)
            else ""
        )
    if not isinstance(reference, str) or not reference or reference != reference.strip():
        return "", ""
    try:
        attempt = read_app_launch_attempt(Path(reference))
    except (OSError, TypeError, ValueError):
        return "", ""
    code = _canonical_direct_code(attempt.get("firstBlocker"))
    return (code, "launch_attempt") if code else ("", "")


def _run_blocker(run: Mapping[str, Any]) -> tuple[str, str]:
    graph_digest = run.get("contractGraphDigest")
    evidence = run.get("evidence")
    if isinstance(evidence, Mapping):
        evidence_graph_digest = evidence.get("contractGraphDigest") or graph_digest
        for field in ("typedBlocker", "artifactBindingBlocker"):
            typed = evidence.get(field)
            code = _canonical_typed_code(
                typed,
                contract_graph_digest=evidence_graph_digest,
            )
            if not code and field == "typedBlocker" and isinstance(typed, Mapping):
                projected = typed.get("errorCode")
                operation = typed.get("sourceOperationId")
                if (
                    run.get("errorCode") == projected
                    and isinstance(projected, str)
                    and _APP_ERROR_CODE_RE.fullmatch(projected) is not None
                    and isinstance(operation, str)
                    and _OPERATION_ID_RE.fullmatch(operation) is not None
                ):
                    code = projected
            if code:
                return code, f"page_evidence.{field}"
    for field in ("typedBlocker", "artifactBindingBlocker"):
        typed = run.get(field)
        code = _canonical_typed_code(
            typed,
            contract_graph_digest=graph_digest,
        )
        if not code and isinstance(typed, Mapping):
            # The orchestrator only mirrors errorCode after the page-evidence
            # boundary validated this exact typed blocker. Preserve that closed
            # projection even when a test double omits its graph digest.
            projected = typed.get("errorCode")
            operation = typed.get("sourceOperationId")
            if (
                run.get("errorCode") == projected
                and isinstance(projected, str)
                and _APP_ERROR_CODE_RE.fullmatch(projected) is not None
                and isinstance(operation, str)
                and _OPERATION_ID_RE.fullmatch(operation) is not None
            ):
                code = projected
        if code:
            return code, f"run.{field}"
    for field in ("firstBlocker", "errorCode"):
        code = _canonical_direct_code(run.get(field))
        if code:
            return code, f"run.{field}"
    return "", ""


def first_canonical_app_blocker(
    *,
    status: str,
    preflights: Sequence[Mapping[str, Any]],
    runs: Sequence[Mapping[str, Any]],
) -> tuple[str, dict[str, Any]]:
    """Select one stable blocker while retaining child reports as raw evidence.

    Priority follows execution boundaries: failed preflight, failed launch attempt,
    then each failed page/run in execution order. Within one page run, its
    validated innermost typed evidence wins over a generic run-level code.
    """

    for index, preflight in enumerate(preflights):
        if not _failed(preflight):
            continue
        code = _canonical_direct_code(preflight.get("firstBlocker"))
        if code:
            return code, {"source": "preflight", "index": index, "fallback": False}

    for index, run in enumerate(runs):
        if not _failed(run):
            continue
        if run.get("suite") not in {"canonical-launch", "canonical-hot-restart"}:
            continue
        code, source = _launch_attempt_blocker(run)
        if code:
            return code, {"source": source, "index": index, "fallback": False}

    for index, run in enumerate(runs):
        if not _failed(run):
            continue
        code, source = _run_blocker(run)
        if code:
            return code, {"source": source, "index": index, "fallback": False}

    if status == "gate_block":
        return APP_CONTENT_UAT_RECEIPT_INVALID, {
            "source": "parent_receipt_validation",
            "fallback": True,
            "reason": "gate_block_without_canonical_child_code",
        }
    return "", {"source": "none", "fallback": False}


__all__ = [
    "APP_CONTENT_UAT_RECEIPT_INVALID",
    "app_content_uat_cli_profile",
    "app_content_uat_non_promotable",
    "first_canonical_app_blocker",
]
