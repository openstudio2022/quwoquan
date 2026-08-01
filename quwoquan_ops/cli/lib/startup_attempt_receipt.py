"""Target-scoped transactional receipt for local runtime startup."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from quwoquan_ops.cli.lib.immutable_image_composition import (
    first_party_service_names,
    immutable_image_digest,
    local_release_image_environment_key,
)
from quwoquan_ops.cli.lib.output_paths import target_process_dir


SCHEMA = "stackctl-local-startup-attempt"
STATUSES = ("prepared", "partial", "running", "stopped")
_TRANSITIONS = {
    None: {"prepared"},
    "prepared": {"partial", "stopped"},
    "partial": {"partial", "running", "stopped"},
    "running": {"stopped"},
    "stopped": {"prepared"},
}
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


def startup_attempt_path(target: str) -> Path:
    return target_process_dir(target) / "startup_attempt.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"startup attempt receipt is unreadable: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        raise ValueError("startup attempt receipt schema mismatch")
    return value


def load_startup_attempt(target: str) -> dict[str, Any] | None:
    return _read(startup_attempt_path(target))


def _atomic_write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def image_composition_from_environment(
    environment: Mapping[str, str],
) -> dict[str, Any]:
    refs: dict[str, str] = {}
    for service in first_party_service_names():
        key = local_release_image_environment_key(service)
        ref = str(environment.get(key) or "").strip()
        if ref:
            refs[service] = ref
    if not refs:
        return {}
    return {
        "imageVersion": immutable_image_digest(refs),
        "images": {
            service: {"ref": ref}
            for service, ref in sorted(refs.items())
        },
    }


def transition_startup_attempt(
    *,
    env: str,
    target: str,
    attempt_id: str,
    status: str,
    workload: str = "",
    compose_project: str = "",
    candidate_digest: str = "",
    configuration_digest: str = "",
    image_transport_tag: str = "",
    image_composition: Mapping[str, Any] | None = None,
    run_root: str = "",
    failure: str = "",
    cleanup_failure: str = "",
) -> dict[str, Any]:
    if status not in STATUSES:
        raise ValueError(f"startup attempt status is invalid: {status}")
    path = startup_attempt_path(target)
    previous = _read(path)
    previous_status = str(previous.get("status")) if previous else None
    if status not in _TRANSITIONS.get(previous_status, set()):
        raise ValueError(
            f"startup attempt transition is invalid: {previous_status!r} -> {status!r}"
        )
    normalized_attempt = str(attempt_id or "").strip()
    if status == "prepared":
        if not normalized_attempt:
            raise ValueError("prepared startup attempt requires attemptId")
        started_at = _utc_now()
    else:
        if previous is None:
            raise ValueError("startup attempt transition requires an existing receipt")
        if normalized_attempt and normalized_attempt != previous.get("attemptId"):
            raise ValueError("startup attempt identity mismatch")
        normalized_attempt = str(previous["attemptId"])
        started_at = str(previous["startedAt"])

    def inherited(name: str, value: str) -> str:
        text = str(value or "").strip()
        if text:
            return text
        return str((previous or {}).get(name) or "").strip()

    normalized_composition = dict(image_composition or {})
    if not normalized_composition and previous:
        prior_composition = previous.get("imageComposition")
        if isinstance(prior_composition, dict):
            normalized_composition = dict(prior_composition)
    normalized_project = inherited("composeProject", compose_project)
    normalized_config = inherited("configurationDigest", configuration_digest)
    normalized_image = inherited("imageTransportTag", image_transport_tag)
    if status in {"partial", "running"}:
        if not normalized_project:
            raise ValueError(f"{status} startup attempt requires Compose project")
        if _DIGEST.fullmatch(normalized_config) is None:
            raise ValueError(f"{status} startup attempt requires configuration digest")
        if not normalized_composition:
            raise ValueError(f"{status} startup attempt requires image composition")
        derived_image = str(normalized_composition.get("imageVersion") or "")
        if normalized_image != derived_image:
            raise ValueError(f"{status} startup attempt image composition mismatch")

    payload = {
        "schema": SCHEMA,
        "attemptId": normalized_attempt,
        "env": inherited("env", env),
        "target": inherited("target", target),
        "status": status,
        "workload": inherited("workload", workload),
        "composeProject": normalized_project,
        "candidateDigest": inherited("candidateDigest", candidate_digest) or None,
        "configurationDigest": normalized_config,
        "imageTransportTag": normalized_image,
        "imageComposition": normalized_composition,
        "runRoot": inherited("runRoot", run_root),
        "startedAt": started_at,
        "updatedAt": _utc_now(),
        "failure": str(failure or "").strip() or None,
        "cleanupFailure": str(cleanup_failure or "").strip() or None,
    }
    if payload["env"] != env or payload["target"] != target:
        raise ValueError("startup attempt target identity mismatch")
    _atomic_write(path, payload)
    run_path_text = str(payload["runRoot"] or "").strip()
    if run_path_text:
        _atomic_write(Path(run_path_text) / "startup_attempt.json", payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--attempt-id", default="")
    parser.add_argument("--status", choices=STATUSES, required=True)
    parser.add_argument("--workload", default="")
    parser.add_argument("--compose-project", default="")
    parser.add_argument("--candidate-digest", default="")
    parser.add_argument("--configuration-digest", default="")
    parser.add_argument("--image-transport-tag", default="")
    parser.add_argument("--run-root", default="")
    parser.add_argument("--failure", default="")
    parser.add_argument("--cleanup-failure", default="")
    args = parser.parse_args()
    transition_startup_attempt(
        env=args.env,
        target=args.target,
        attempt_id=args.attempt_id,
        status=args.status,
        workload=args.workload,
        compose_project=args.compose_project,
        candidate_digest=args.candidate_digest,
        configuration_digest=args.configuration_digest,
        image_transport_tag=args.image_transport_tag,
        image_composition=image_composition_from_environment(os.environ),
        run_root=args.run_root,
        failure=args.failure,
        cleanup_failure=args.cleanup_failure,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
