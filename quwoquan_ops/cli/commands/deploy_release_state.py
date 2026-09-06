"""stackctl deploy 发布状态与 hosted release ledger 桥接域。

从 stackctl.py 逐字迁出（改写规则与 down_domain 相同）:
- release state: `_release_state_dir` / `_load_release_state` /
  `_load_release_state_path` / `_release_stage_from_state` /
  `_validate_release_transition`;
- candidate digest 与 artifact: `_required_release_candidate_digests` /
  `_archive_release_artifact`;
- hosted release ledger 桥: `_fetch_hosted_release_ledger_projection` /
  `_sync_release_ledger_projection` / `_hosted_receipt_id` /
  `_validate_hosted_release_readback` / `_run_hosted_release_ledger` /
  `_cache_hosted_release_readback` / `_check_exit_passed` /
  `_release_check_receipts` / `_commit_hosted_release_transition`。

测试经 ``mock.patch.object(stackctl, ...)`` patch 本模块符号与协作符号，
因此函数体内一律经函数内延迟导入 `_stackctl` 属性访问（含本模块符号互调），
保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile

from pathlib import Path
from typing import Any


def _release_state_dir() -> Path:
    # 这里只保存 hosted release ledger 的本机 readback cache；它绝不能作为发布真相。
    # 真实 ledger/receipt 只能经 prod service-plane SSH projection 写入并读回。
    import quwoquan_ops.cli.stackctl as _stackctl

    configured = os.environ.get("QWQ_PROD_RELEASE_STATE_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return _stackctl.target_process_dir("prod-hosted") / "release-state"


PROD_RELEASE_UNIT = "prod-stack"


def _load_release_state(service: str = PROD_RELEASE_UNIT) -> dict[str, str]:
    import quwoquan_ops.cli.stackctl as _stackctl

    return _stackctl._load_release_state_path(_stackctl._release_state_dir() / f"{service}.state")


def _load_release_state_path(state_path: Path) -> dict[str, str]:
    payload: dict[str, str] = {}
    if not state_path.exists():
        return payload
    for raw in state_path.read_text(encoding="utf-8").splitlines():
        if "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        payload[key.strip()] = value.strip()
    return payload


def _release_stage_from_state(state: dict[str, str]) -> str:
    if state.get("schema") != "prod-release-ledger":
        raise RuntimeError("release ledger schema is not canonical")
    stage = state.get("stage", "").strip()
    if stage:
        return stage
    raise RuntimeError("release ledger missing canonical stage")


def _validate_release_transition(
    state: dict[str, str],
    *,
    from_candidate_digest: str,
    to_candidate_digest: str,
    stage: str,
    prod_activation_admission_payload_digest: str = "",
) -> tuple[str, int]:
    import quwoquan_ops.cli.stackctl as _stackctl

    if not state:
        if stage != "canary":
            raise RuntimeError("release ledger must start at canary")
        return "advance", 0

    generation = int(state.get("generation") or 0)
    current_stage = _stackctl._release_stage_from_state(state)
    same_target = (
        state.get("from_candidate_digest") == from_candidate_digest
        and state.get("to_candidate_digest") == to_candidate_digest
    )
    if same_target:
        if (
            prod_activation_admission_payload_digest
            and state.get("prod_activation_admission_payload_digest")
            != prod_activation_admission_payload_digest
        ):
            raise RuntimeError(
                "release ledger authority drift: "
                "prod_activation_admission_payload_digest does not match"
            )
        if current_stage == stage:
            decision = state.get("decision", "continue")
            if decision == "continue":
                return "replay", generation
            if decision in {"pause", "rollback_failed"}:
                return "reevaluate", generation
            raise RuntimeError(
                f"release ledger stage is not replayable with decision={decision}"
            )
        if state.get("decision", "continue") != "continue":
            raise RuntimeError("paused or failed release cannot advance to the next stage")
        expected_next = {
            "canary": "5",
            "5": "20",
            "20": "50",
            "50": "100",
        }.get(current_stage)
        if expected_next != stage:
            raise RuntimeError(
                f"release ledger stage CAS conflict: {current_stage} cannot advance to {stage}"
            )
        return "advance", generation

    if stage != "canary":
        raise RuntimeError("new release target must start at canary")
    if state.get("to_candidate_digest") != from_candidate_digest:
        raise RuntimeError("new release source must equal current hosted target")
    if state.get("last_good_candidate_digest") != from_candidate_digest:
        raise RuntimeError("new release source must equal current last-good candidate")
    if current_stage != "100" or state.get("decision") != "continue":
        raise RuntimeError("new release requires a completed current hosted release")
    return "advance", generation


def _required_release_candidate_digests(
    args: argparse.Namespace,
    manifest: dict[str, Any],
) -> dict[str, str]:
    """Derive and validate the RTC candidate tuple attested by hosted receipts."""
    import quwoquan_ops.cli.stackctl as _stackctl

    graph_path = _stackctl.ROOT / "quwoquan_service/generated/contract_graph.json"
    if not graph_path.is_file():
        raise RuntimeError("hosted release receipt requires generated ContractGraph")
    graph_digest = "sha256:" + hashlib.sha256(graph_path.read_bytes()).hexdigest()
    artifacts = manifest.get("environmentArtifacts")
    prod_artifact = artifacts.get("prod") if isinstance(artifacts, dict) else None
    images = prod_artifact.get("images") if isinstance(prod_artifact, dict) else None
    rtc_image = images.get("rtc-service") if isinstance(images, dict) else None
    image_digest = str(rtc_image.get("digest") or "") if isinstance(rtc_image, dict) else ""
    governance = _stackctl._external_provider_governance()
    conformance = _stackctl._provider_conformance()
    compiled, governance_issues = governance.load_and_compile()
    if governance_issues:
        raise RuntimeError(
            "hosted release receipt provider binding is invalid: "
            + "; ".join(issue.render() for issue in governance_issues)
        )
    prod_bindings = (compiled.get("selectedBindings") or {}).get("prod") or {}
    rtc_binding = prod_bindings.get("rtc.room.transport")
    if not isinstance(rtc_binding, dict):
        raise RuntimeError("hosted release receipt cannot resolve prod RTC binding")
    binding_roots = conformance.compiled_capability_binding_roots(
        compiled,
        capability_id="rtc.room.transport",
    )
    config_digest = conformance.binding_config_digest(
        rtc_binding,
        binding_roots,
    )
    registry = governance.load_registry()
    livekit_adapter = next(
        (
            item
            for item in registry.get("adapters", [])
            if isinstance(item, dict)
            and item.get("adapter_id") == "infra.livekit_sfu"
        ),
        None,
    )
    if not isinstance(livekit_adapter, dict) or not str(
        livekit_adapter.get("implementation_path") or ""
    ):
        raise RuntimeError("hosted release receipt cannot resolve infra.livekit_sfu")
    implementation_path = _stackctl.ROOT / str(livekit_adapter["implementation_path"])
    adapter_digest = conformance.implementation_digest(implementation_path)
    fields = {
        "imageDigest": image_digest,
        "configDigest": config_digest,
        "contractGraphDigest": graph_digest,
        "adapterDigest": str(adapter_digest or ""),
    }
    invalid = [
        name
        for name, value in fields.items()
        if re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None
    ]
    if invalid:
        raise RuntimeError(
            "hosted release receipt cannot derive sha256 candidate digests for "
            + ", ".join(invalid)
        )
    requested = {
        "imageDigest": str(getattr(args, "release_image_digest", "") or "").strip(),
        "configDigest": str(getattr(args, "release_config_digest", "") or "").strip(),
        "contractGraphDigest": str(
            getattr(args, "contract_graph_digest", "") or ""
        ).strip(),
        "adapterDigest": str(getattr(args, "adapter_digest", "") or "").strip(),
    }
    mismatched = [
        name
        for name, value in requested.items()
        if value and value != fields[name]
    ]
    if mismatched:
        raise RuntimeError(
            "hosted release receipt candidate digest mismatch for "
            + ", ".join(mismatched)
        )
    return fields


def _archive_release_artifact(manifest_path: Path, artifact_digest: str) -> Path:
    import quwoquan_ops.cli.stackctl as _stackctl

    archive_root = _stackctl._release_state_dir() / "artifacts"
    archive_root.mkdir(parents=True, exist_ok=True)
    digest_id = artifact_digest.removeprefix("sha256:")
    if re.fullmatch(r"[0-9a-f]{64}", digest_id) is None:
        raise RuntimeError("release artifact digest is invalid")
    target = archive_root / digest_id
    source = manifest_path.parent
    if target.exists():
        archived_manifest = target / "manifest.json"
        if not archived_manifest.is_file():
            raise RuntimeError(f"release artifact archive is incomplete: {target}")
        archived = json.loads(archived_manifest.read_text(encoding="utf-8"))
        declared = str(archived.get("artifactDigest") or "") if isinstance(archived, dict) else ""
        if declared != artifact_digest:
            raise RuntimeError(f"release artifact archive digest collision: {target}")
        return target
    temporary = archive_root / f".{digest_id}.{os.getpid()}.tmp"
    shutil.copytree(source, temporary)
    os.replace(temporary, target)
    archives = sorted(
        (path for path in archive_root.iterdir() if path.is_dir() and not path.name.startswith(".")),
        key=lambda path: path.stat().st_mtime_ns,
        reverse=True,
    )
    for stale in archives[2:]:
        shutil.rmtree(stale)
    return target


def _fetch_hosted_release_ledger_projection(
    service: str,
    *,
    allow_uninitialized: bool,
    deadline_epoch: int = 0,
) -> tuple[dict[str, str], Path | None]:
    """Fetch a digest-verified state/receipt pair from the hosted authority."""
    import quwoquan_ops.cli.stackctl as _stackctl

    readback = _stackctl._run_hosted_release_ledger(
        service=service,
        action="fetch",
        deadline_epoch=deadline_epoch,
    )
    state = readback["state"]
    receipt = readback["receipt"]
    if not state:
        if allow_uninitialized:
            return {}, None
        raise RuntimeError("hosted release ledger is uninitialized")
    return _stackctl._cache_hosted_release_readback(service, state, receipt)


def _sync_release_ledger_projection(
    service: str,
    receipt_id: str,
    *,
    deadline_epoch: int = 0,
) -> Path:
    """Read back an already committed hosted receipt; never publish local state."""
    import quwoquan_ops.cli.stackctl as _stackctl

    hosted_state, hosted_receipt_path = _stackctl._fetch_hosted_release_ledger_projection(
        service,
        allow_uninitialized=False,
        deadline_epoch=deadline_epoch,
    )
    if hosted_receipt_path is None:
        raise RuntimeError("hosted release receipt readback is missing")
    if hosted_state.get("receipt_id") != receipt_id:
        raise RuntimeError("hosted release ledger readback does not match committed transition")
    return hosted_receipt_path


def _hosted_receipt_id(receipt: dict[str, Any]) -> str:
    unsigned = dict(receipt)
    unsigned.pop("receiptId", None)
    return hashlib.sha256(
        json.dumps(
            unsigned,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def _validate_hosted_release_readback(
    payload: object,
    *,
    service: str,
) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    if (
        not isinstance(payload, dict)
        or set(payload) != {"schema", "authority", "state", "receipt", "receiptRef"}
        or payload.get("schema") != "prod-hosted-release-readback"
        or payload.get("authority") != "prod-hosted-service-plane"
        or not isinstance(payload.get("state"), dict)
        or not isinstance(payload.get("receipt"), dict)
    ):
        raise RuntimeError("hosted release ledger returned an invalid readback")
    state = payload["state"]
    receipt = payload["receipt"]
    if not state and not receipt and payload.get("receiptRef") == "":
        return payload
    if (
        set(state) != _stackctl.hosted_release_ledger.STATE_FIELDS
        or set(receipt) != _stackctl.hosted_release_ledger.RECEIPT_FIELDS
    ):
        raise RuntimeError(
            "hosted release ledger state or receipt shape is not canonical"
        )
    receipt_id = str(receipt.get("receiptId") or "")
    for field in _stackctl.hosted_release_ledger.STAGE_RECEIPT_ID_FIELDS.values():
        history_receipt_id = state.get(field)
        if not isinstance(history_receipt_id, str) or (
            history_receipt_id
            and _stackctl.hosted_release_ledger.RECEIPT_ID_RE.fullmatch(history_receipt_id)
            is None
        ):
            raise RuntimeError(
                "hosted release ledger stage receipt history is invalid"
            )
    active_history_field = _stackctl.hosted_release_ledger.STAGE_RECEIPT_ID_FIELDS.get(
        state.get("trigger_stage", "")
    )
    if (
        active_history_field is None
        or state.get(active_history_field) != receipt_id
    ):
        raise RuntimeError(
            "hosted release ledger current receipt is not trigger-stage bound"
        )
    if (
        state.get("schema") != _stackctl.hosted_release_ledger.STATE_SCHEMA
        or state.get("authority") != _stackctl.hosted_release_ledger.AUTHORITY
        or state.get("service") != service
        or receipt.get("schema") != _stackctl.hosted_release_ledger.RECEIPT_SCHEMA
        or receipt.get("authority") != _stackctl.hosted_release_ledger.AUTHORITY
        or receipt.get("service") != service
        or re.fullmatch(r"[0-9a-f]{64}", receipt_id) is None
        or receipt_id != _stackctl._hosted_receipt_id(receipt)
        or state.get("receipt_id") != receipt_id
        or payload.get("receiptRef") != f"receipt:hosted:{receipt_id}"
        or str(receipt.get("committedGeneration")) != state.get("generation")
        or receipt.get("candidateMaterialId") != state.get("candidate_material_id")
        or receipt.get("prodActivationAdmissionRef") != state.get("prod_activation_admission_ref")
        or receipt.get("prodActivationAdmissionOciDigest") != state.get("prod_activation_admission_oci_digest")
        or receipt.get("prodActivationAdmissionPayloadDigest") != state.get("prod_activation_admission_payload_digest")
        or receipt.get("prodActivationAdmissionId") != state.get("prod_activation_admission_id")
        or receipt.get("candidateMaterialManifestRef") != state.get("candidate_material_manifest_ref")
        or receipt.get("candidateMaterialManifestOciDigest") != state.get("candidate_material_manifest_oci_digest")
        or receipt.get("candidateMaterialManifestPayloadDigest") != state.get("candidate_material_manifest_payload_digest")
        or receipt.get("previousReleasedRef") != state.get("previous_released_ref")
        or receipt.get("previousReleasedOciDigest") != state.get("previous_released_oci_digest")
        or receipt.get("previousReleasedPayloadDigest") != state.get("previous_released_payload_digest")
        or receipt.get("previousReleasedId") != state.get("previous_released_id")
        or receipt.get("fromCandidateDigest")
        != state.get("from_candidate_digest")
        or receipt.get("toCandidateDigest") != state.get("to_candidate_digest")
        or receipt.get("step") != state.get("step")
        or receipt.get("stage") != state.get("stage")
        or receipt.get("decision") != state.get("decision")
        or receipt.get("imageDigest") != state.get("image_digest")
        or receipt.get("configDigest") != state.get("config_digest")
        or receipt.get("contractGraphDigest") != state.get("contract_graph_digest")
        or receipt.get("adapterDigest") != state.get("adapter_digest")
        or receipt.get("rollbackOutcome") != state.get("rollback_outcome")
        or receipt.get("triggerStage") != state.get("trigger_stage")
        or receipt.get("fromServiceFactoryOciDigest")
        != state.get("from_service_factory_oci_digest")
        or receipt.get("toServiceFactoryOciDigest")
        != state.get("to_service_factory_oci_digest")
        or receipt.get("fromAppFactoryOciDigest")
        != state.get("from_app_factory_oci_digest")
        or receipt.get("toAppFactoryOciDigest")
        != state.get("to_app_factory_oci_digest")
        or receipt.get("lastGoodCandidateDigest")
        != state.get("last_good_candidate_digest")
        or receipt.get("verifiedAt") != state.get("updated_at")
    ):
        raise RuntimeError("hosted release ledger receipt digest or state binding is invalid")
    if service == _stackctl.PROD_RELEASE_UNIT and receipt.get("decision") == "continue":
        try:
            _stackctl.rollout_stage_promotion_evidence.validate_receipt_evidence(
                (receipt.get("sloReadback") or {}).get("promotionEvidence"),
                candidate_id=receipt.get("toCandidateDigest"),
                candidate_material_id=receipt.get("candidateMaterialId"),
                stage=receipt.get("triggerStage"),
            )
        except (ValueError, RuntimeError) as error:
            raise RuntimeError(
                "hosted release receipt promotion evidence is invalid"
            ) from error
    return payload


def _run_hosted_release_ledger(
    *,
    service: str,
    action: str,
    request: dict[str, Any] | None = None,
    receipt_id: str = "",
    deadline_epoch: int = 0,
) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    with tempfile.TemporaryDirectory(prefix="quwoquan-hosted-release-ledger-") as temporary:
        root = Path(temporary)
        output_path = root / "readback.json"
        command = [
            "bash",
            "quwoquan_ops/cli/prod/sync_prod_plane_stack.sh",
            "--plane",
            "service",
            "--operation",
            f"release-ledger-{action}",
            "--service",
            service,
            "--output-path",
            str(output_path),
        ]
        if action == "commit":
            if request is None:
                raise RuntimeError("hosted release ledger commit request is missing")
            request_path = root / "request.json"
            _stackctl.write_json(request_path, request)
            command.extend(("--request-path", str(request_path)))
        elif action == "receipt":
            command.extend(("--receipt-id", receipt_id))
        timeout_seconds = (
            _stackctl._remaining_deadline_seconds(
                deadline_epoch,
                "hosted release ledger authority I/O",
            )
            if deadline_epoch > 0
            else None
        )
        result = _stackctl.run(command, timeout_seconds=timeout_seconds)
        if result.returncode != 0:
            raise RuntimeError(
                f"hosted release ledger {action} failed: "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )
        try:
            payload = json.loads(output_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError("hosted release ledger readback is not valid JSON") from error
    if action == "receipt":
        if (
            not isinstance(payload, dict)
            or set(payload) != {"schema", "authority", "receipt", "receiptRef"}
            or payload.get("schema") != "prod-hosted-release-receipt-readback"
            or payload.get("authority") != "prod-hosted-service-plane"
            or not isinstance(payload.get("receipt"), dict)
        ):
            raise RuntimeError("hosted release receipt returned an invalid readback")
        receipt = payload["receipt"]
        actual_id = str(receipt.get("receiptId") or "")
        if (
            actual_id != receipt_id
            or actual_id != _stackctl._hosted_receipt_id(receipt)
            or payload.get("receiptRef") != f"receipt:hosted:{receipt_id}"
            or receipt.get("schema") != "prod-hosted-release-receipt"
            or receipt.get("authority") != "prod-hosted-service-plane"
            or receipt.get("service") != service
        ):
            raise RuntimeError("hosted release receipt digest is invalid")
        if service == _stackctl.PROD_RELEASE_UNIT and receipt.get("decision") == "continue":
            try:
                _stackctl.rollout_stage_promotion_evidence.validate_receipt_evidence(
                    (receipt.get("sloReadback") or {}).get("promotionEvidence"),
                    candidate_id=receipt.get("toCandidateDigest"),
                    candidate_material_id=receipt.get("candidateMaterialId"),
                    stage=receipt.get("triggerStage"),
                )
            except (ValueError, RuntimeError) as error:
                raise RuntimeError(
                    "hosted release receipt promotion evidence is invalid"
                ) from error
        return payload
    return _stackctl._validate_hosted_release_readback(payload, service=service)


def _cache_hosted_release_readback(
    service: str,
    state: dict[str, str],
    receipt: dict[str, Any],
) -> tuple[dict[str, str], Path]:
    """Persist a disposable local copy after hosted digest verification."""
    import quwoquan_ops.cli.stackctl as _stackctl

    receipt_id = str(receipt.get("receiptId") or "")
    validated = _stackctl._validate_hosted_release_readback(
        {
            "schema": _stackctl.hosted_release_ledger.READBACK_SCHEMA,
            "authority": _stackctl.hosted_release_ledger.AUTHORITY,
            "state": state,
            "receipt": receipt,
            "receiptRef": f"receipt:hosted:{receipt_id}",
        },
        service=service,
    )
    state = dict(validated["state"])
    receipt = dict(validated["receipt"])
    cache_dir = _stackctl._release_state_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    state_path = cache_dir / f"{service}.state"
    state_path.write_text(
        "\n".join(f"{key}={value}" for key, value in state.items()) + "\n",
        encoding="utf-8",
    )
    receipt_path = cache_dir / "receipts" / f"{receipt_id}.json"
    _stackctl.write_json(receipt_path, receipt)
    return state, receipt_path


def _check_exit_passed(item: dict[str, Any]) -> bool:
    exit_code = item.get("exitCode")
    return (
        isinstance(exit_code, int)
        and not isinstance(exit_code, bool)
        and exit_code == 0
    )


def _release_check_receipts(
    checks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    import quwoquan_ops.cli.stackctl as _stackctl

    receipts: list[dict[str, Any]] = []
    for index, item in enumerate(checks, start=1):
        explicit_name = str(item.get("name") or "").strip()
        if explicit_name.startswith("host:") and _stackctl.hosted_release_ledger.SAFE_VALUE_RE.fullmatch(
            explicit_name
        ):
            name = explicit_name
        else:
            name = f"post-check-{index}"
        receipts.append(
            {
                "name": name,
                "status": "passed" if _stackctl._check_exit_passed(item) else "failed",
                "receiptDigest": "sha256:"
                + hashlib.sha256(
                    json.dumps(
                        item,
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    ).encode("utf-8")
                ).hexdigest(),
            }
        )
    return receipts


def _commit_hosted_release_transition(
    *,
    service: str,
    from_candidate_digest: str,
    to_candidate_digest: str,
    step: str,
    stage: str,
    decision: str,
    candidate_material_id: str,
    expected_generation: int,
    receipt_id: str,
    slo_readback: dict[str, Any] | None,
    candidate_digests: dict[str, str],
    last_good_candidate_digest: str,
    post_deploy_checks: list[dict[str, Any]],
    rollback_outcome: str,
    rollback_evidence: dict[str, Any],
    from_service_factory_oci_digest: str,
    to_service_factory_oci_digest: str,
    from_app_factory_oci_digest: str,
    to_app_factory_oci_digest: str,
    prod_activation_admission: dict[str, str] | None = None,
    deadline_epoch: int = 0,
    trigger_stage: str = "",
) -> tuple[dict[str, str], Path]:
    import quwoquan_ops.cli.stackctl as _stackctl

    del receipt_id
    request = {
        "schema": "prod-hosted-release-transition-request",
        "service": service,
        "fromCandidateDigest": from_candidate_digest,
        "toCandidateDigest": to_candidate_digest,
        "step": step,
        "stage": stage,
        "triggerStage": trigger_stage or stage,
        "fromServiceFactoryOciDigest": from_service_factory_oci_digest,
        "toServiceFactoryOciDigest": to_service_factory_oci_digest,
        "fromAppFactoryOciDigest": from_app_factory_oci_digest,
        "toAppFactoryOciDigest": to_app_factory_oci_digest,
        "decision": decision,
        "rollbackOutcome": rollback_outcome,
        "rollbackEvidence": rollback_evidence,
        "candidateMaterialId": candidate_material_id,
        "prodActivationAdmissionRef": (prod_activation_admission or {}).get("prodActivationAdmissionRef", ""),
        "prodActivationAdmissionOciDigest": (prod_activation_admission or {}).get("prodActivationAdmissionOciDigest", ""),
        "prodActivationAdmissionPayloadDigest": (prod_activation_admission or {}).get("prodActivationAdmissionPayloadDigest", ""),
        "prodActivationAdmissionId": (prod_activation_admission or {}).get("prodActivationAdmissionId", ""),
        "candidateMaterialManifestRef": (prod_activation_admission or {}).get("candidateMaterialManifestRef", ""),
        "candidateMaterialManifestOciDigest": (prod_activation_admission or {}).get("candidateMaterialManifestOciDigest", ""),
        "candidateMaterialManifestPayloadDigest": (prod_activation_admission or {}).get("candidateMaterialManifestPayloadDigest", ""),
        "previousReleasedRef": (prod_activation_admission or {}).get("previousReleasedRef", ""),
        "previousReleasedOciDigest": (prod_activation_admission or {}).get("previousReleasedOciDigest", ""),
        "previousReleasedPayloadDigest": (prod_activation_admission or {}).get("previousReleasedPayloadDigest", ""),
        "previousReleasedId": (prod_activation_admission or {}).get("previousReleasedId", ""),
        "imageDigest": candidate_digests["imageDigest"],
        "configDigest": candidate_digests["configDigest"],
        "contractGraphDigest": candidate_digests["contractGraphDigest"],
        "adapterDigest": candidate_digests["adapterDigest"],
        "expectedGeneration": expected_generation,
        "sloReadback": slo_readback or {},
        "postChecks": _stackctl._release_check_receipts(post_deploy_checks),
        "lastGoodCandidateDigest": last_good_candidate_digest,
        "verifiedAt": _stackctl.utc_now(),
    }
    committed = _stackctl._run_hosted_release_ledger(
        service=service,
        action="commit",
        request=request,
        deadline_epoch=deadline_epoch,
    )
    # The hosted commit action fsyncs state/receipt and returns its own validated
    # readback. A second network fetch adds no authority and extends the Prod path.
    return _stackctl._cache_hosted_release_readback(
        service,
        committed["state"],
        committed["receipt"],
    )
