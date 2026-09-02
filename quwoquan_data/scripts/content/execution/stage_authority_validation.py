"""Current stage receipt 的只读深层 authority validator。"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any


def validate_stage_receipt_authority(
    execution_id: str, receipt: Mapping[str, Any] | str | Path, *,
    verify_current_workflow: bool = True,
) -> dict[str, Any]:
    from content.execution import stage_authority as kernel
    return _validate(kernel, execution_id, receipt, verify_current_workflow=verify_current_workflow)


def validate_release_authority(
    execution_id: str, context: Mapping[str, Any]
) -> dict[str, str]:
    from content.execution import stage_authority as kernel
    return _validate_release(kernel, execution_id, context)


def _receipt_path(
    kernel: Any, execution_id: str, receipt: Mapping[str, Any] | str | Path
) -> tuple[Path, dict[str, Any]]:
    root = kernel._execution_root(execution_id)
    if isinstance(receipt, Mapping):
        sequence = int(receipt.get("sequence") or 0)
        stage = str(receipt.get("stage") or "")
        return root / "_shared/receipts" / f"{sequence:03d}-{stage}.json", dict(receipt)
    path = Path(receipt)
    if not path.is_absolute():
        path = root / path
    try:
        path.resolve(strict=True).relative_to(root.resolve(strict=True))
    except (FileNotFoundError, ValueError) as exc:
        raise kernel.StageAuthorityError(
            "receipt path must be a current execution-contained file"
        ) from exc
    return path, kernel._load_json(path, label="stage receipt")


def _validate_release(
    kernel: Any, execution_id: str, context: Mapping[str, Any]
) -> dict[str, str]:
    from content.release.canonical.release_attestation import (
        ReleaseAttestation, ReleaseAttestationError,
    )
    from content.release.canonical.release_header import (
        ReleaseHeaderError, validate_release_header,
    )
    from content.release.canonical.release_uat_sample_plan import (
        ReleaseUatSamplePlanError, exact_document_sha256,
        validate_release_uat_sample_plan,
    )

    release_id = str(context.get("releaseId") or "")
    release_digest = str(context.get("releaseDigest") or "")
    release_root = kernel.paths.RELEASE_ROOT / release_id
    locations = {
        "header": release_root / "payload/release.json",
        "attestation": release_root / "attestations/release.json",
        "desired": release_root / "payload/desired_state.json",
        "sample": release_root / "payload/uat/sample_plan.json",
    }
    documents = {
        name: kernel._load_json(path, label=f"release {name}")
        for name, path in locations.items()
    }
    try:
        header = validate_release_header(documents["header"], label="stage release header")
        ReleaseAttestation.from_document(documents["attestation"])
        kernel.assert_valid(
            documents["desired"], "release", "release_desired_state",
            label="release desired state",
        )
        validate_release_uat_sample_plan(documents["sample"])
    except (
        ReleaseHeaderError, ReleaseAttestationError,
        ReleaseUatSamplePlanError, ValueError,
    ) as exc:
        raise kernel.StageAuthorityError(
            f"release canonical closure rejected: {exc}"
        ) from exc
    if (
        header.get("releaseId") != release_id
        or documents["attestation"].get("releaseId") != release_id
        or documents["desired"].get("releaseId") != release_id
        or documents["sample"].get("releaseId") != release_id
        or documents["sample"].get("releaseDigest") != release_digest
        or header.get("samplePlanRef") != "uat/sample_plan.json"
        or header.get("samplePlanDigest") != exact_document_sha256(documents["sample"])
    ):
        raise kernel.StageAuthorityError(
            "release header/attestation/desired/sample identity drifted"
        )
    execution_ids = header.get("executionIds")
    if not isinstance(execution_ids, list) or execution_id not in execution_ids:
        raise kernel.StageAuthorityError(
            "release header does not include current execution"
        )
    publish = kernel._load_json(
        kernel._execution_root(execution_id) / "publish_ref.json",
        label="execution publish result",
    )
    kernel.assert_valid(publish, "execution", "publish_ref", label="execution publish result")
    if publish.get("executionId") != execution_id:
        raise kernel.StageAuthorityError(
            "release execution publish result identity drifted"
        )
    published = publish.get("publishedRefs")
    desired_refs = documents["desired"].get("desiredRefs")
    if not isinstance(published, Mapping) or not isinstance(desired_refs, Mapping):
        raise kernel.StageAuthorityError("release publish/desired refs are invalid")
    published_count = 0
    for kind in ("entities", "posts"):
        values = published.get(kind)
        desired_values = desired_refs.get(kind)
        if not isinstance(values, list) or not isinstance(desired_values, list):
            raise kernel.StageAuthorityError("release publish/desired refs are invalid")
        published_count += len(values)
        if not set(map(str, values)) <= set(map(str, desired_values)):
            raise kernel.StageAuthorityError(
                "execution publish result did not enter immutable release"
            )
    if published_count < 1:
        raise kernel.StageAuthorityError(
            "release stage requires non-empty execution publish closure"
        )
    return {"releaseId": release_id, "releaseDigest": release_digest}


def _validate(
    kernel: Any, execution_id: str, receipt: Mapping[str, Any] | str | Path, *,
    verify_current_workflow: bool,
) -> dict[str, Any]:
    path, value = _receipt_path(kernel, execution_id, receipt)
    kernel.assert_valid(value, "execution", "stage_receipt", label=f"stage receipt:{path}")
    sequence = int(value.get("sequence") or 0)
    stage = str(value.get("stage") or "")
    expected_path = (
        kernel._execution_root(execution_id) / "_shared/receipts"
        / f"{sequence:03d}-{stage}.json"
    )
    if (
        path.resolve(strict=True) != expected_path.resolve(strict=True)
        or value.get("executionId") != execution_id
        or sequence < 1
        or sequence > len(kernel.RECEIPT_STAGES)
        or kernel.RECEIPT_STAGES[sequence - 1] != stage
    ):
        raise kernel.StageAuthorityError(
            "stage receipt current path/order/identity drifted"
        )
    authority = value.get("authority")
    if not isinstance(authority, Mapping):
        raise kernel.StageAuthorityError("stage receipt authority is invalid")
    expected_dir = kernel._authority_dir(execution_id, sequence, stage)
    open_path = kernel._resolve_binding(execution_id, authority["openRequest"])
    gate_path = kernel._resolve_binding(execution_id, authority["machineGate"])
    if (
        open_path != (expected_dir / "open.json").resolve(strict=True)
        or gate_path != (expected_dir / "gate.json").resolve(strict=True)
    ):
        raise kernel.StageAuthorityError(
            "stage receipt authority refs are not canonical"
        )
    open_request = kernel._load_json(open_path, label="stage receipt open request")
    gate = kernel._load_json(gate_path, label="stage receipt machine gate")
    kernel.assert_valid(
        open_request, "execution", "stage_open_request",
        label="stage receipt open request",
    )
    kernel.assert_valid(
        gate, "execution", "stage_gate_receipt",
        label="stage receipt machine gate",
    )
    identity = (execution_id, stage, sequence)
    if any(
        (document.get("executionId"), document.get("stage"), document.get("sequence"))
        != identity
        for document in (open_request, gate)
    ):
        raise kernel.StageAuthorityError("receipt/open/gate stage identity drifted")
    if (
        gate.get("openRequest") != authority.get("openRequest")
        or gate.get("workflowContract") != open_request.get("workflowContract")
        or authority.get("workflowContract") != open_request.get("workflowContract")
        or gate.get("semanticResult") != authority.get("semanticResult")
        or gate.get("artifacts") != authority.get("artifacts")
        or gate.get("releaseBinding") != authority.get("releaseBinding")
        or gate.get("acceptanceBinding") != authority.get("acceptanceBinding")
        or gate.get("gateContextDigest")
        != kernel._sha256(kernel._canonical_bytes(gate.get("gateContext")))
    ):
        raise kernel.StageAuthorityError(
            "stage receipt authority exact closure drifted"
        )
    if verify_current_workflow:
        kernel._validate_workflow(open_request["workflowContract"])
    predecessor = open_request.get("predecessor")
    if sequence == 1:
        if (
            predecessor is not None
            or open_request.get("initArtifacts")
            != kernel._validate_init_artifacts(execution_id)
        ):
            raise kernel.StageAuthorityError("0.plan open authority closure drifted")
    else:
        predecessor_path = (
            kernel._execution_root(execution_id) / "_shared/receipts"
            / f"{sequence - 1:03d}-{kernel.RECEIPT_STAGES[sequence - 2]}.json"
        )
        if (
            not isinstance(predecessor, Mapping)
            or kernel._resolve_binding(execution_id, predecessor)
            != predecessor_path.resolve(strict=True)
        ):
            raise kernel.StageAuthorityError(
                "stage receipt fixed predecessor drifted"
            )
    semantic = gate.get("semanticResult")
    if stage in kernel.SEMANTIC_STAGES:
        if not isinstance(semantic, Mapping):
            raise kernel.StageAuthorityError(
                f"{stage} receipt lacks canonical semantic result"
            )
        try:
            kernel.read_stage_semantic_result(
                execution_id, stage, binding=semantic,
                verify_current_workflow=verify_current_workflow,
            )
        except kernel.StageSemanticError as exc:
            raise kernel.StageAuthorityError(
                f"stage receipt semantic closure rejected: {exc}"
            ) from exc
    elif semantic is not None:
        raise kernel.StageAuthorityError(
            f"{stage} receipt must not bind a semantic result"
        )
    artifacts = gate.get("artifacts")
    if not isinstance(artifacts, list):
        raise kernel.StageAuthorityError(
            "stage receipt artifact closure is invalid"
        )
    for artifact in artifacts:
        kernel._resolve_binding(execution_id, artifact)
    kernel._validate_required_artifact_closure(execution_id, stage, artifacts)
    context = gate.get("gateContext")
    if not isinstance(context, Mapping):
        raise kernel.StageAuthorityError("stage receipt gate context is invalid")
    from content.execution.stage_gate_registry import normalize_context, registry_argv
    try:
        normalized = normalize_context(stage, context)
        expected_commands = registry_argv(execution_id, stage, normalized)
    except ValueError as exc:
        raise kernel.StageAuthorityError(
            f"stage receipt canonical registry rejected: {exc}"
        ) from exc
    commands = gate.get("commands")
    if (
        not isinstance(commands, list)
        or [
            (item.get("commandId"), tuple(item.get("argv", ())))
            for item in commands
        ]
        != [
            (command_id, argv)
            for command_id, argv in expected_commands[: len(commands)]
        ]
        or (
            value.get("verdict") == "pass"
            and any(int(item.get("exitCode", 1)) != 0 for item in commands)
        )
    ):
        raise kernel.StageAuthorityError(
            "stage receipt canonical command/verdict closure drifted"
        )
    release_binding = gate.get("releaseBinding")
    if stage in {"release", "ship"}:
        expected_release = _validate_release(
            kernel, execution_id, normalized
        )
        if release_binding != expected_release:
            raise kernel.StageAuthorityError(
                "stage receipt immutable release binding drifted"
            )
    elif release_binding is not None:
        raise kernel.StageAuthorityError(
            f"{stage} receipt must not bind release authority"
        )
    if stage == "ship":
        acceptance = kernel._validate_acceptance(normalized)
        if gate.get("acceptanceBinding") != acceptance:
            raise kernel.StageAuthorityError(
                "ship receipt EnvironmentAcceptanceFact binding drifted"
            )
        release_predecessor = kernel._load_json(
            kernel._execution_root(execution_id)
            / "_shared/receipts/009-release.json",
            label="ship release predecessor",
        )
        if (
            (release_predecessor.get("authority") or {}).get("releaseBinding")
            != release_binding
        ):
            raise kernel.StageAuthorityError(
                "ship releaseBinding differs from release predecessor"
            )
    elif gate.get("acceptanceBinding") is not None:
        raise kernel.StageAuthorityError(
            f"{stage} receipt must not bind acceptance authority"
        )
    issues = kernel._normalize_typed_issues(stage, value.get("typedIssues"))
    derived = (
        kernel.derive_stage_semantic_issues(
            execution_id, stage, binding=semantic,
            verify_current_workflow=verify_current_workflow,
        )
        if semantic is not None else []
    )
    failed = [
        item for item in commands if int(item.get("exitCode", 1)) != 0
    ]
    if value.get("verdict") == "pass" and (issues or derived or failed):
        raise kernel.StageAuthorityError(
            "pass receipt contradicts machine-derived stage verdict"
        )
    if value.get("verdict") == "blocked" and not issues:
        raise kernel.StageAuthorityError(
            "blocked receipt lacks typed issue authority"
        )
    if value.get("verdict") == "pass":
        expected_next = (
            kernel.RECEIPT_STAGES[sequence]
            if sequence < len(kernel.RECEIPT_STAGES) else "END"
        )
    else:
        expected_next = issues[0]["recoveryStage"]
    if value.get("next") != expected_next:
        raise kernel.StageAuthorityError("stage receipt fixed next drifted")
    return value


__all__ = ["validate_release_authority", "validate_stage_receipt_authority"]
