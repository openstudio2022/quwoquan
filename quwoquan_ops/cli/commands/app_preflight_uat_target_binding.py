"""App content UAT 的 TargetUatBinding exact-byte 构造。"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

def _target_uat_binding_for_execution(
    *,
    stackctl: Any,
    evidence_root: Path,
    preflight: Mapping[str, Any],
    runtime_binding: Mapping[str, Any],
    launch_binding: Mapping[str, Any],
    uat_profile: Mapping[str, Any],
    device_id: str,
) -> tuple[dict[str, Any], dict[str, str]]:
    from quwoquan_ops.cli.lib.target_uat_binding import (
        build_target_uat_binding,
        canonical_target_uat_binding_bytes,
        target_uat_binding_digest,
        write_create_once_target_uat_binding,
    )

    target = str(runtime_binding["target"])
    release_id = str(runtime_binding["releaseId"])
    activation = preflight.get("activationEnvelope")
    if not isinstance(activation, Mapping):
        raise ValueError("canonical Data activation envelope is missing")
    def evidence_ref(value: object, *, label: str) -> str:
        raw = str(value or "").strip()
        if not raw:
            raise ValueError(f"{label} exact-byte reference is missing")
        candidate = Path(raw).expanduser()
        resolved = (
            candidate.resolve()
            if candidate.is_absolute()
            else (evidence_root / candidate).resolve()
        )
        try:
            relative = resolved.relative_to(evidence_root).as_posix()
        except ValueError as exc:
            raise ValueError(f"{label} escapes QWQ_OUTPUT_ROOT") from exc
        if resolved.is_symlink() or not resolved.is_file():
            raise ValueError(f"{label} exact bytes are missing or unsafe")
        return relative

    def verify_file_digest(ref: str, digest: str, *, label: str) -> None:
        if not digest:
            raise ValueError(f"{label} exact-byte digest is missing")
        observed = "sha256:" + hashlib.sha256((evidence_root / ref).read_bytes()).hexdigest()
        if observed != digest:
            raise ValueError(f"{label} exact-byte digest drifted")

    activation_ref = evidence_ref(
        activation.get("importReportRef"), label="active CAS"
    )
    activation_digest = str(activation.get("importReportDigest") or "")
    readback_ref = evidence_ref(
        preflight.get("readinessReceiptRef"), label="readback"
    )
    readback_digest = str(preflight.get("readinessReceiptDigest") or "")
    provider_ref = evidence_ref(
        launch_binding.get("contractGraphRef"), label="Provider ContractGraph"
    )
    provider_digest = str(launch_binding.get("contractGraphDigest") or "")
    for ref, digest, label in (
        (activation_ref, activation_digest, "active CAS"),
        (provider_ref, provider_digest, "Provider ContractGraph"),
    ):
        verify_file_digest(ref, digest, label=label)
    if not readback_digest:
        raise ValueError("readback exact-byte digest is missing")
    readback_payload = stackctl._read_json_object(str(evidence_root / readback_ref))
    if stackctl._canonical_document_checksum(readback_payload) != readback_digest:
        raise ValueError("readback canonical digest drifted")
    runner_source_paths = (
        "quwoquan_ops/cli/commands/app_preflight_uat.py",
        "quwoquan_ops/cli/smoke/environment_patrol_smoke/app_uat_case_execution.py",
        "quwoquan_ops/cli/smoke/environment_patrol_smoke/evidence.py",
        "quwoquan_app/test/user_acceptance/journeys/release_bound_sample_matrix/"
        "release_bound_sample_matrix__user_acceptance_test.dart",
        "quwoquan_app/test/support/runtime/patrol/release_uat_sample_plan.dart",
        "quwoquan_app/test/support/runtime/patrol/patrol_app_uat_case_evidence.dart",
        "quwoquan_ops/cli/commands/app_preflight_uat_orchestration.py",
        "quwoquan_ops/cli/commands/app_preflight_uat_target_binding.py",
    )
    runner_source_path = runner_source_paths[3]
    runner_hasher = hashlib.sha256()
    for source_path in runner_source_paths:
        encoded_path = source_path.encode("utf-8")
        encoded_source = (stackctl.ROOT / source_path).read_bytes()
        runner_hasher.update(len(encoded_path).to_bytes(4, "big"))
        runner_hasher.update(encoded_path)
        runner_hasher.update(len(encoded_source).to_bytes(8, "big"))
        runner_hasher.update(encoded_source)
    runner_digest = "sha256:" + runner_hasher.hexdigest()
    profile = str(uat_profile.get("profile") or "")
    registered = profile in {"promotable", "production"}
    binding = build_target_uat_binding(
        runtime_binding,
        launch_binding,
        {
            "releaseId": release_id,
            "releaseUatSamplePlanRef": str(
                preflight.get("releaseUatSamplePlanRef") or ""
            ),
            "releaseUatSamplePlanDigest": str(
                preflight.get("releaseUatSamplePlanDigest") or ""
            ),
        },
        active_cas={"ref": activation_ref, "digest": activation_digest},
        readback={"ref": readback_ref, "digest": readback_digest},
        artifact_class="production_behavior",
        build_mode="debug",
        build_profile="nonprod",
        provider={
            "identity": "first-party-https",
            "class": "first_party",
            "type": "https",
            "registered": registered,
            "conformanceEvidence": {
                "ref": provider_ref,
                "digest": provider_digest,
            },
        },
        device={
            "identity": device_id,
            "class": str(uat_profile.get("deviceClass") or ""),
            "registered": bool(uat_profile.get("deviceRegistered")),
        },
        runner={
            "identity": "app-content-uat",
            "sourcePath": runner_source_path,
            "digest": runner_digest,
            "registered": registered,
        },
        profile=profile,
        non_promotable=bool(uat_profile.get("nonPromotable")),
        created_at=str(
            (
                stackctl._read_json_object(str(launch_binding["launchAttemptRef"]))
                .get("transitions", [{}])[0]
                .get("at")
            )
            or ""
        ),
    )
    written = write_create_once_target_uat_binding(
        output_root=evidence_root,
        binding=binding,
    )
    if (
        written.digest != target_uat_binding_digest(binding)
        or written.path.read_bytes() != canonical_target_uat_binding_bytes(binding)
    ):
        raise ValueError("TargetUatBinding exact bytes drifted after create-once write")
    return binding, {"ref": written.ref, "digest": written.digest}
