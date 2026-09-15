"""canonical bundled snapshot 的页面 UAT 编排；不读取在线 readiness。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.lib.app_launch_manifest_contract import load_launch_manifest_contract
from quwoquan_ops.cli.lib.readiness_case_result import write_create_once_json

OFFLINE_SPEC_REF = "specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007"
OFFLINE_REQUIRED_CASES = (
    "default-entry", "homepage-recommendation", "premium-video-book", "article-detail",
    "image-detail", "homepage-video-playback", "homepage-tab-roundtrip", "creator-avatar", "video-complete", "video-seek",
    "empty-state", "pagination-end", "login-cancel", "login-success", "login-error",
    "private-continuation", "local-write", "otp-expiry", "identity-restart",
    "network-refusal", "otp-refusal", "push-refusal", "remote-refusal", "outbox-refusal",
)


def offline_case_spec_ref(case_id: str) -> str:
    if case_id not in OFFLINE_REQUIRED_CASES:
        raise ValueError("APP.UAT.page_plan_invalid: unknown required case")
    return OFFLINE_SPEC_REF if OFFLINE_REQUIRED_CASES.index(case_id) < OFFLINE_REQUIRED_CASES.index("login-cancel") else OFFLINE_SPEC_REF.replace("#gwt-007", "#gwt-008")


def offline_case_blocker(case_id: str) -> str:
    """缺真实接缝仍留在同一 required 集合，绝不以观察截图签发成功。"""
    if case_id in {"login-success", "login-error"}:
        return "APP.UAT.page_artifact_binding_missing: authorized rehearsal identity input source is absent"
    if case_id in {"private-continuation", "local-write"}:
        return "APP.UAT.page_artifact_binding_missing: local action query/readback seam is absent"
    if case_id == "otp-expiry":
        return "APP.UAT.page_artifact_binding_missing: real 300-second challenge observation is absent"
    if case_id == "identity-restart":
        return "APP.UAT.page_artifact_binding_missing: cross-process launch attempt and identity binding is absent"
    if case_id.endswith("-refusal"):
        return "APP.UAT.page_artifact_binding_missing: actual external side-effect refusal observation is absent"
    return ""


def content_source_for_target(target: str) -> str:
    contract = load_launch_manifest_contract()
    environment = contract["target_environment"].get(target)
    if environment is None:
        raise ValueError("unsupported App content UAT target: " + target)
    return str(contract["content_source_policy"][environment])


def _sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _candidate(args: argparse.Namespace, repository: Path) -> dict[str, Any]:
    from quwoquan_ops.ci.scoped_candidate.core import _SCHEMA, _load_exact_ref, exact_digest, store_root

    raw = str(getattr(args, "candidate", "") or "")
    if not raw:
        raise ValueError("APP.LAUNCH.receipt_absent: --candidate <store-relative ref>=<sha256:digest> is required")
    ref, digest = raw.rsplit("=", 1)
    root = store_root(repository=repository, policy_path=repository / "quwoquan_ops/policies/scoped_candidate_policy.yaml")
    candidate, _ = _load_exact_ref(root, {"ref": ref, "digest": digest}, "candidate")
    if (candidate.get("schema") != _SCHEMA
            or candidate.get("candidateId") != exact_digest({k: v for k, v in candidate.items() if k != "candidateId"})):
        raise ValueError("APP.LAUNCH.receipt_invalid: exact candidate identity drifted")
    _verify_source(candidate, repository)
    return candidate


def _verify_source(candidate: Mapping[str, Any], repository: Path) -> None:
    def git(*arguments: str) -> str:
        return subprocess.check_output(["git", *arguments], cwd=repository, text=True).strip()

    if git("rev-parse", "HEAD") != candidate.get("commit") or git("rev-parse", "HEAD^{tree}") != candidate.get("tree"):
        raise ValueError("APP.LAUNCH.receipt_invalid: candidate commit/tree differs from current source")
    result = subprocess.run(["git", "diff", "--quiet", str(candidate["commit"]), "--"], cwd=repository, check=False)
    if result.returncode != 0:
        raise ValueError("APP.LAUNCH.receipt_invalid: tracked source changed after candidate freeze")
    # 不按扩展名或整个 failures 目录豁免：新增源码、配置与资产都属于候选漂移。
    untracked = git("ls-files", "--others", "--exclude-standard", "-z").split("\0")
    unexpected = [path for path in untracked if path and not _known_diagnostic_image(path)]
    if unexpected:
        raise ValueError("APP.LAUNCH.receipt_invalid: untracked source after candidate freeze: " + ", ".join(unexpected))


def _known_diagnostic_image(path: str) -> bool:
    prefix = "quwoquan_app/test/local_contract/design_system/feedback/error_states/failures/"
    name = path.removeprefix(prefix)
    return path.startswith(prefix) and re.fullmatch(
        r"app_page_error_state_(?:dark|light)_(?:masterImage|testImage|isolatedDiff|maskedDiff)\.png", name
    ) is not None


def first_typed_blocker(error: object, *, fallback: str = "APP.UAT.page_artifact_binding_missing") -> str:
    code = getattr(error, "code", "")
    if isinstance(code, str) and re.fullmatch(r"[A-Z][A-Z0-9_]*(?:\.[A-Za-z0-9_]+){2,}", code):
        return code
    match = re.search(r"\b[A-Z][A-Z0-9_]*(?:\.[A-Za-z0-9_]+){2,}\b", str(error))
    return match.group(0) if match else fallback


def _prepare_launch(candidate: Mapping[str, Any], report_dir: Path, output_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    from quwoquan_ops.cli.lib.app_source_capsule import app_source_capsule_roots
    from quwoquan_ops.cli.lib.package_reuse import materialize_package_input_capsule, workspace_snapshot
    from quwoquan_ops.cli.commands.app_preflight_uat_launch import materialize_app_content_launch_projection
    import quwoquan_ops.cli.stackctl as stackctl

    graph = "quwoquan_service/generated/contract_graph.json"
    roots = (*app_source_capsule_roots(), graph)
    before = workspace_snapshot(deployment_roots=roots)
    capsule = materialize_package_input_capsule(roots, capsule_root=(report_dir / "source-capsule").absolute())
    after = workspace_snapshot(deployment_roots=roots)
    if before != after:
        raise ValueError("APP.LAUNCH.receipt_invalid: source changed while freezing App capsule")
    _verify_source(candidate, stackctl.ROOT)
    runtime = {
        "contentSource": "bundled_snapshot", "environment": "alpha", "target": "alpha-local",
        "candidateDigest": candidate["candidateId"], "sourceRevision": candidate["commit"],
        "sourceCapsuleBaselineId": capsule["baselineId"],
        "sourceCapsuleDigest": capsule["deploymentInputDigest"],
        "sourceCapsuleWorkspaceStatusDigest": capsule["workspaceStatusDigest"],
        "sourceCapsuleManifestRef": str(Path(capsule["capsuleRoot"]) / "manifest.json"),
        "contractGraphDigest": _sha(stackctl.ROOT / graph),
    }
    projection = materialize_app_content_launch_projection(
        runtime_binding=runtime, output_root=output_root,
        projection_root=report_dir / "source-projection", evidence_path=report_dir / "source-projection.json",
    )
    return runtime, projection


def _isolated_selection(args: argparse.Namespace, runtime: Mapping[str, Any],
                        projection: Mapping[str, Any]) -> dict[str, str] | None:
    """只投影已获准调用的选择；pin来自已验证capsule，不签发授权或信任。"""
    requested = getattr(args, "isolated_rehearsal", False)
    instance = getattr(args, "rehearsal_instance_id", "")
    if type(requested) is not bool or not isinstance(instance, str):
        raise ValueError("APP.LAUNCH.receipt_invalid: invalid isolated request")
    if not requested:
        if instance:
            raise ValueError("APP.LAUNCH.receipt_invalid: instance requires explicit isolated request")
        return None
    from quwoquan_ops.cli.lib.app_launch_manifest_contract import load_launch_manifest_contract
    from quwoquan_ops.cli.lib.app_launch_manifest_schema import _validate_schema_value
    from quwoquan_ops.cli.commands.app_preflight_uat_launch import verify_app_content_launch_projection
    contract = load_launch_manifest_contract()
    schema = contract["app_content_uat_launch_control"]["selection"]["fields"]["instanceId"]
    if instance == "default" or _validate_schema_value(instance, schema, field_path="instanceId", contract=contract):
        raise ValueError("APP.LAUNCH.receipt_invalid: isolated instance must be explicit and non-default")
    if (runtime.get("environment"), runtime.get("target"), runtime.get("contentSource")) != ("alpha", "alpha-local", "bundled_snapshot"):
        raise ValueError("APP.LAUNCH.receipt_invalid: isolated selection requires offline Alpha")
    root = Path(projection["sourceProjectionRoot"])
    evidence = verify_app_content_launch_projection(
        projection_root=root, evidence_path=Path(projection["sourceProjectionEvidenceRef"]), reject_unmanifested=True,
    )
    for field in ("candidateDigest", "sourceRevision", "sourceCapsuleDigest", "contentSource"):
        if not runtime.get(field) or evidence.get(field) != runtime[field]:
            raise ValueError("APP.LAUNCH.receipt_invalid: isolated source identity drifted: " + field)
    manifest = root / "quwoquan_app/assets/content/alpha/manifest.json"
    identity = manifest.with_name("bundle_identity.json")
    pin = _sha(manifest)
    if json.loads(identity.read_bytes()).get("manifestDigest") != pin:
        raise ValueError("APP.LAUNCH.receipt_invalid: isolated snapshot identity drifted")
    return {"mode": "isolated", "instanceId": instance, "snapshotDigest": pin}


def _launch(args: argparse.Namespace, runtime: Mapping[str, Any], projection: Mapping[str, Any],
            report_dir: Path, output_root: Path) -> dict[str, Any]:
    from quwoquan_ops.cli.commands.app_preflight_uat_launch import (
        FLUTTER_ANDROID_3_47_GRADLE_8_14_POLICY_ID, FLUTTER_IOS_3_47_COCOAPODS_1_16_POLICY_ID,
        write_app_content_launch_control,
    )
    from quwoquan_ops.cli.commands.app_preflight_uat_launch_binding import _app_content_launch_binding
    from quwoquan_ops.cli.commands.app_preflight_uat_support import _app_content_canonical_launch_command
    import quwoquan_ops.cli.stackctl as stackctl

    selection = _isolated_selection(args, runtime, projection)
    attempt = report_dir / "attempt-1" / "attempt.json"
    report = attempt.with_name("report.json")
    policy = FLUTTER_ANDROID_3_47_GRADLE_8_14_POLICY_ID if args.platform == "android" else FLUTTER_IOS_3_47_COCOAPODS_1_16_POLICY_ID
    control = write_app_content_launch_control(
        runtime_binding=runtime, projection=projection, output_root=output_root,
        control_path=attempt.with_name("control.json"), attempt_path=attempt, report_path=report,
        terminal_receipt_path=attempt.with_name("startup-terminal.json"), platform=args.platform,
        device_id=args.device_id, build_projection_policy_id=policy,
        build_projection_seal_path=attempt.with_name("build-projection-seal.json"), expected_build_projection_digest=None,
        rehearsal_space_selection=selection,
    )
    if selection is not None:
        from quwoquan_app.scripts.device.build_launcher_handoff import verified_rehearsal_selection
        verified = verified_rehearsal_selection(
            control_ref=control["controlRef"], control_digest=control["controlDigest"], output_root=str(output_root),
            source_root=Path(projection["sourceProjectionRoot"]), environment="alpha", target="alpha-local",
            device_id=args.device_id, candidate_digest=runtime["candidateDigest"],
            attempt_ref=str(attempt.absolute()), report_ref=str(report.absolute()),
            capsule_ref=projection["sourceCapsuleManifestRef"], source_revision=runtime["sourceRevision"],
            source_digest=runtime["sourceCapsuleDigest"], require_isolated=True,
        )
        if verified != selection:
            raise ValueError("APP.LAUNCH.receipt_invalid: isolated selection forwarding drifted")
    app_root = Path(projection["sourceProjectionRoot"]) / "quwoquan_app"
    command, environment = _app_content_canonical_launch_command(
        environment="alpha", target="alpha-local", device_id=args.device_id,
        attempt_path=attempt, report_path=report, output_root=output_root, app_root=app_root, launch_control=control,
    )
    result = stackctl.run(command, cwd=app_root, env=environment)
    (report_dir / "canonical-launch.log").write_text((result.stdout or "") + (result.stderr or ""), encoding="utf-8")
    if result.returncode:
        output = (result.stdout or "") + "\n" + (result.stderr or "")
        raise ValueError(first_typed_blocker(output, fallback="APP.LAUNCH.receipt_invalid")
                         + f": canonical offline launch failed, exit={result.returncode}")
    return _app_content_launch_binding(
        runtime_binding=runtime, report_ref=report, attempt_ref=attempt, platform=args.platform,
        device_id=args.device_id, launch_provenance="canonical_launcher", launch_projection=projection,
    )


def run_offline_app_content_uat(*, args: argparse.Namespace, report_dir: Path, output_root: Path,
                                issues: list[str]) -> dict[str, Any]:
    """规划与执行共用同一来源；实际设备证据缺失始终阻断。"""
    import quwoquan_ops.cli.stackctl as stackctl

    receipt: dict[str, Any] = {
        "schema": "quwoquan_ops.app_content_uat_receipt", "targets": ["alpha-local"],
        "contentSource": "bundled_snapshot", "profile": "rehearsal", "nonPromotable": True,
        "preconditions": ["exact_candidate", "signed_bundled_snapshot", "managed_device"],
        "requiredCases": list(OFFLINE_REQUIRED_CASES), "rawResultRefs": {}, "runs": [],
        "status": "planned", "exitCode": 0, "firstBlocker": "", "details": list(issues),
        "summary": "Offline App content UAT is planned", "reportDir": str(report_dir),
    }
    try:
        if issues:
            raise ValueError(issues[0])
        if args.platform not in {"android", "ios-simulator"}:
            raise ValueError("APP.LAUNCH.receipt_invalid: offline UAT requires a rehearsal simulator/emulator")
        receipt["blockedCases"] = [{"caseId": case, "specRef": offline_case_spec_ref(case),
                                    "firstBlocker": offline_case_blocker(case)}
                                   for case in OFFLINE_REQUIRED_CASES if offline_case_blocker(case)]
        if getattr(args, "dry_run", False) and receipt["blockedCases"]:
            raise ValueError(receipt["blockedCases"][0]["firstBlocker"])
        if not getattr(args, "dry_run", False):
            candidate = _candidate(args, stackctl.ROOT)
            runtime, projection = _prepare_launch(candidate, report_dir, output_root)
            binding = _launch(args, runtime, projection, report_dir, output_root)
            if getattr(args, "isolated_rehearsal", False):
                raise ValueError("APP.UAT.page_artifact_binding_missing: isolated AUT three-storage consumption observation is absent; native input remains blocked")
            from quwoquan_ops.cli.commands.app_preflight_uat_offline_pages import execute_offline_page_cases
            receipt.update(execute_offline_page_cases(
                args=args, candidate=candidate, launch=binding, projection=projection,
                report_dir=report_dir, output_root=output_root,
            ))
            _verify_source(candidate, stackctl.ROOT)
    except (OSError, RuntimeError, TypeError, ValueError, KeyError) as error:
        detail = str(error)
        receipt.update(status="gate_block", exitCode=2,
                       firstBlocker=receipt.get("firstBlocker") or first_typed_blocker(error),
                       details=[*receipt.get("details", []), detail], summary="Offline App content UAT is GATE_BLOCK")
    if not getattr(args, "dry_run", False):
        write_create_once_json(report_dir / "receipt.json", receipt)
    return receipt
