"""Target-scoped startup receipt for mutable Alpha/Beta/Gamma runtimes.

This receipt is deliberately separate from ``startup_attempt_receipt``.  A
mutable test-live runtime has no immutable candidate or OCI image composition,
so accepting it through the formal receipt schema would weaken release gates.

spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/multi-environment-instance-isolation/spec.md#gwt-001
"""

from __future__ import annotations

import json
import os
import re
import stat
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .data_execution_fleet import project_runtime_owned_ports
from .environment_topology import get_target, load_environment_topology
from .output_paths import env_runs_root, target_process_dir
from .port_manifest import load_port_manifest


SCHEMA = "stackctl.mutable_test_live_startup_attempt"
PLAN_SCHEMA = "stackctl.mutable_test_live_runtime"
STATUSES = ("prepared", "partial", "running", "stopped")
_TRANSITIONS = {
    None: {"prepared"},
    "prepared": {"partial", "stopped"},
    "partial": {"partial", "running", "stopped"},
    "running": {"stopped"},
    "stopped": {"prepared"},
}
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_SOURCE_REVISION = re.compile(r"[0-9a-f]{40,64}")
_ATTEMPT_ID = re.compile(r"[a-z0-9][a-z0-9._-]{7,127}")
_FIELDS = frozenset(
    {
        "schema",
        "launchPolicy",
        "nonPromotable",
        "contentBindingState",
        "attemptId",
        "environment",
        "target",
        "status",
        "workload",
        "composeProject",
        "composeDigest",
        "configurationDigest",
        "providerRuntimeDigest",
        "portProfile",
        "portBlock",
        "publishedPorts",
        "tlsProfile",
        "resolverHandoffDigest",
        "publicWebPackage",
        "sourceRevision",
        "workspaceStatusDigest",
        "mutableStateDigest",
        "runRoot",
        "startedAt",
        "updatedAt",
        "failure",
    }
)
_IDENTITY_FIELDS = (
    "environment",
    "target",
    "workload",
    "composeProject",
    "composeDigest",
    "configurationDigest",
    "providerRuntimeDigest",
    "portProfile",
    "portBlock",
    "publishedPorts",
    "tlsProfile",
    "resolverHandoffDigest",
    "publicWebPackage",
    "sourceRevision",
    "workspaceStatusDigest",
    "mutableStateDigest",
    "runRoot",
    "startedAt",
)


class UnsafeTestLiveStartupReceiptPath(ValueError):
    """The receipt path or one of its entries is not a regular local file."""


def test_live_startup_attempt_path(target: str) -> Path:
    return target_process_dir(target) / "test_live_startup_attempt.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _validate_timestamp(value: object, *, field: str) -> None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"test-live startup receipt {field} is invalid") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"test-live startup receipt {field} is invalid")


def _canonical_run_root(value: object, *, environment: str) -> str:
    raw = str(value or "").strip()
    path = Path(raw).expanduser()
    if not raw or not path.is_absolute() or ".." in path.parts:
        raise ValueError("test-live startup receipt runRoot is invalid")
    resolved = Path(os.path.abspath(path))
    expected_root = Path(os.path.abspath(env_runs_root(environment)))
    if not resolved.is_relative_to(expected_root):
        raise ValueError("test-live startup receipt runRoot escapes environment runs")
    return str(resolved)


def _published_endpoint_documents(value: object, *, label: str) -> list[dict[str, Any]]:
    if (
        isinstance(value, (str, bytes, bytearray, Mapping))
        or not isinstance(value, Sequence)
        or not value
    ):
        raise ValueError(f"{label} publishedPorts must be a non-empty list")
    endpoints: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise ValueError(f"{label} publishedPorts entries must be objects")
        endpoints.append(dict(item))
    return endpoints


def validate_test_live_startup_attempt(
    value: object,
    *,
    expected_environment: str = "",
    expected_target: str = "",
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _FIELDS:
        raise ValueError("test-live startup receipt fields mismatch")
    if value.get("schema") != SCHEMA:
        raise ValueError("test-live startup receipt schema mismatch")
    if (
        value.get("launchPolicy") != "test_live"
        or value.get("nonPromotable") is not True
        or value.get("contentBindingState") != "unbound"
    ):
        raise ValueError("test-live startup receipt promotion boundary mismatch")

    environment = str(value.get("environment") or "").strip()
    target = str(value.get("target") or "").strip()
    if environment not in {"alpha", "beta", "gamma"} or target != f"{environment}-local":
        raise ValueError("test-live startup receipt target identity mismatch")
    if expected_environment and environment != expected_environment:
        raise ValueError("test-live startup receipt environment mismatch")
    if expected_target and target != expected_target:
        raise ValueError("test-live startup receipt target mismatch")
    if value.get("workload") != "full":
        raise ValueError("test-live startup receipt workload must be full")
    if value.get("status") not in STATUSES:
        raise ValueError("test-live startup receipt status is invalid")
    if _ATTEMPT_ID.fullmatch(str(value.get("attemptId") or "")) is None:
        raise ValueError("test-live startup receipt attemptId is invalid")
    if value.get("composeProject") != f"quwoquan_{environment}_test_live":
        raise ValueError("test-live startup receipt Compose project mismatch")
    if value.get("portProfile") != target:
        raise ValueError("test-live startup receipt port profile mismatch")

    for field in (
        "composeDigest",
        "configurationDigest",
        "providerRuntimeDigest",
        "resolverHandoffDigest",
        "workspaceStatusDigest",
        "mutableStateDigest",
    ):
        if _DIGEST.fullmatch(str(value.get(field) or "")) is None:
            raise ValueError(f"test-live startup receipt {field} is invalid")
    if _SOURCE_REVISION.fullmatch(str(value.get("sourceRevision") or "")) is None:
        raise ValueError("test-live startup receipt sourceRevision is invalid")
    if not str(value.get("tlsProfile") or "").strip():
        raise ValueError("test-live startup receipt tlsProfile is required")
    public_web_package = value.get("publicWebPackage")
    target_topology = get_target(load_environment_topology(), target)
    public_bases = target_topology.get("publicBases")
    expected_public_origin = (
        str(public_bases.get("publicWeb") or "").rstrip("/")
        if isinstance(public_bases, Mapping)
        else ""
    )
    if (
        not isinstance(public_web_package, dict)
        or set(public_web_package)
        != {
            "environment",
            "packageVersion",
            "manifestDigest",
            "contentDigest",
            "publicOrigin",
        }
        or public_web_package.get("environment") != environment
        or not str(public_web_package.get("packageVersion") or "").strip()
        or "/" in str(public_web_package.get("packageVersion") or "")
        or _DIGEST.fullmatch(
            str(public_web_package.get("manifestDigest") or "")
        )
        is None
        or _DIGEST.fullmatch(str(public_web_package.get("contentDigest") or ""))
        is None
        or public_web_package.get("publicOrigin") != expected_public_origin
    ):
        raise ValueError("test-live startup receipt publicWebPackage is invalid")

    block = value.get("portBlock")
    if (
        not isinstance(block, dict)
        or set(block) != {"start", "end"}
        or not isinstance(block.get("start"), int)
        or isinstance(block.get("start"), bool)
        or not isinstance(block.get("end"), int)
        or isinstance(block.get("end"), bool)
        or block["start"] < 1
        or block["end"] <= block["start"]
    ):
        raise ValueError("test-live startup receipt portBlock is invalid")
    manifest = load_port_manifest()
    profile = manifest.get("profiles", {}).get(target)
    if not isinstance(profile, Mapping) or block != {
        "start": profile.get("blockStart"),
        "end": profile.get("blockEnd"),
    }:
        raise ValueError("test-live startup receipt portBlock is not canonical")
    ports = _published_endpoint_documents(
        value.get("publishedPorts"),
        label="test-live startup receipt",
    )
    try:
        project_runtime_owned_ports(
            port_profile=target,
            published_ports=ports,
            manifest=manifest,
        )
    except ValueError as exc:
        raise ValueError(
            f"test-live startup receipt publishedPorts are invalid: {exc}"
        ) from exc
    stable_ports = sorted(
        ports,
        key=lambda endpoint: (
            int(endpoint["hostPort"]),
            str(endpoint["protocol"]),
            str(endpoint["role"]),
        ),
    )
    if ports != stable_ports:
        raise ValueError("test-live startup receipt publishedPorts order is not canonical")

    canonical_run_root = _canonical_run_root(
        value.get("runRoot"),
        environment=environment,
    )
    if value.get("runRoot") != canonical_run_root:
        raise ValueError("test-live startup receipt runRoot is not canonical")
    _validate_timestamp(value.get("startedAt"), field="startedAt")
    _validate_timestamp(value.get("updatedAt"), field="updatedAt")
    if value.get("failure") is not None and not isinstance(value.get("failure"), str):
        raise ValueError("test-live startup receipt failure is invalid")
    return dict(value)


def _identity_from_plan(
    plan: Mapping[str, Any],
    *,
    environment: str,
    target: str,
    run_root: str | Path,
) -> dict[str, Any]:
    if plan.get("schema") != PLAN_SCHEMA:
        raise ValueError("test-live startup runtime plan schema mismatch")
    if plan.get("environment") != environment or plan.get("target") != target:
        raise ValueError("test-live startup runtime plan target mismatch")
    workspace = plan.get("workspaceIdentity")
    if not isinstance(workspace, Mapping):
        raise ValueError("test-live startup runtime plan workspace identity is missing")
    return {
        "environment": environment,
        "target": target,
        "workload": "full",
        "composeProject": plan.get("composeProject"),
        "composeDigest": plan.get("composeDigest"),
        "configurationDigest": plan.get("configurationDigest"),
        "providerRuntimeDigest": plan.get("providerRuntimeDigest"),
        "portProfile": plan.get("portProfile"),
        "portBlock": dict(plan.get("portBlock") or {}),
        "publishedPorts": _published_endpoint_documents(
            plan.get("publishedPorts"),
            label="test-live startup runtime plan",
        ),
        "tlsProfile": plan.get("tlsProfile"),
        "resolverHandoffDigest": plan.get("resolverHandoffDigest"),
        "publicWebPackage": dict(plan.get("publicWebPackage") or {}),
        "sourceRevision": workspace.get("sourceRevision"),
        "workspaceStatusDigest": workspace.get("workspaceStatusDigest"),
        "mutableStateDigest": workspace.get("mutableStateDigest"),
        "runRoot": _canonical_run_root(run_root, environment=environment),
    }


def _read(path: Path) -> dict[str, Any] | None:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(metadata.st_mode) or path.is_symlink():
        raise UnsafeTestLiveStartupReceiptPath(
            "test-live startup receipt is a symlink or non-regular file"
        )
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"test-live startup receipt is unreadable: {exc}") from exc
    return validate_test_live_startup_attempt(value)


def _atomic_write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.parent.is_symlink():
        raise UnsafeTestLiveStartupReceiptPath(
            "test-live startup receipt parent is a symlink"
        )
    try:
        current = path.lstat()
    except FileNotFoundError:
        current = None
    if current is not None and not stat.S_ISREG(current.st_mode):
        raise UnsafeTestLiveStartupReceiptPath(
            "test-live startup receipt is a symlink or non-regular file"
        )
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    descriptor = -1
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        encoded = (
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def load_test_live_startup_attempt(target: str) -> dict[str, Any] | None:
    value = _read(test_live_startup_attempt_path(target))
    if value is None:
        return None
    environment = target.removesuffix("-local")
    return validate_test_live_startup_attempt(
        value,
        expected_environment=environment,
        expected_target=target,
    )


def _read_untrusted(target: str) -> dict[str, Any] | None:
    """Decode the receipt without admitting it. Absent reads as ``None``."""
    path = test_live_startup_attempt_path(target)
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(metadata.st_mode) or path.is_symlink():
        raise UnsafeTestLiveStartupReceiptPath(
            "test-live startup receipt is a symlink or non-regular file"
        )
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"test-live startup receipt is unreadable: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(
            "test-live startup receipt is not a JSON object; "
            f"inspect and remove {path} manually"
        )
    return value


def read_stale_test_live_startup_attempt(target: str) -> dict[str, Any] | None:
    """Return the receipt only when it exists and is inadmissible.

    An absent receipt and an admissible one both read as ``None``: the normal
    down path owns those, and reclaim must never touch a receipt that still
    validates. The returned document is untrusted and is only fit for archiving.
    """
    value = _read_untrusted(target)
    if value is None:
        return None
    environment = target.removesuffix("-local")
    try:
        validate_test_live_startup_attempt(
            value,
            expected_environment=environment,
            expected_target=target,
        )
    except ValueError:
        return value
    return None


def reclaim_stale_test_live_startup_attempt(target: str) -> dict[str, Any]:
    """Remove one inadmissible receipt and return what was removed.

    Re-checks admissibility immediately before unlinking so a receipt that
    became valid between audit and apply is never destroyed.
    """
    stale = read_stale_test_live_startup_attempt(target)
    if stale is None:
        raise ValueError(
            f"{target} holds no inadmissible test-live startup receipt to reclaim"
        )
    path = test_live_startup_attempt_path(target)
    try:
        os.unlink(path)
    except FileNotFoundError as exc:
        raise ValueError(
            f"test-live startup receipt vanished before reclaim: {path}"
        ) from exc
    return stale


def transition_test_live_startup_attempt(
    *,
    environment: str,
    target: str,
    attempt_id: str,
    status: str,
    runtime_plan: Mapping[str, Any] | None = None,
    run_root: str | Path = "",
    failure: str = "",
) -> dict[str, Any]:
    if status not in STATUSES:
        raise ValueError(f"test-live startup attempt status is invalid: {status}")
    path = test_live_startup_attempt_path(target)
    previous = _read(path)
    previous_status = str(previous.get("status")) if previous else None
    if status not in _TRANSITIONS.get(previous_status, set()):
        raise ValueError(
            "test-live startup attempt transition is invalid: "
            f"{previous_status!r} -> {status!r}"
        )
    normalized_attempt = str(attempt_id or "").strip()
    now = _utc_now()
    if status == "prepared":
        if runtime_plan is None:
            raise ValueError("prepared test-live startup attempt requires runtime plan")
        if previous is not None and normalized_attempt == previous.get("attemptId"):
            raise ValueError("prepared test-live startup attempt requires a new attemptId")
        identity = _identity_from_plan(
            runtime_plan,
            environment=environment,
            target=target,
            run_root=run_root,
        )
        started_at = now
    else:
        if previous is None:
            raise ValueError("test-live startup transition requires an existing receipt")
        if normalized_attempt != previous.get("attemptId"):
            raise ValueError("test-live startup attempt identity mismatch")
        if previous.get("environment") != environment or previous.get("target") != target:
            raise ValueError("test-live startup attempt target identity mismatch")
        identity = {field: previous[field] for field in _IDENTITY_FIELDS}
        started_at = str(previous["startedAt"])
        if runtime_plan is not None:
            supplied = _identity_from_plan(
                runtime_plan,
                environment=environment,
                target=target,
                run_root=run_root or previous["runRoot"],
            )
            for field, value in supplied.items():
                if value != identity[field]:
                    raise ValueError(
                        f"test-live startup attempt identity mismatch: {field}"
                    )

    payload = {
        "schema": SCHEMA,
        "launchPolicy": "test_live",
        "nonPromotable": True,
        "contentBindingState": "unbound",
        "attemptId": normalized_attempt,
        **identity,
        "status": status,
        "startedAt": started_at,
        "updatedAt": now,
        "failure": str(failure or "").strip() or None,
    }
    validated = validate_test_live_startup_attempt(
        payload,
        expected_environment=environment,
        expected_target=target,
    )
    _atomic_write(path, validated)
    return validated
