"""canonical bundled snapshot 的页面 UAT 编排；不读取在线 readiness。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from uuid import uuid4

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


def selected_offline_cases(args: argparse.Namespace) -> tuple[str, ...]:
    selected = getattr(args, "offline_cases", None)
    if selected is None:
        return OFFLINE_REQUIRED_CASES
    if (not isinstance(selected, (list, tuple)) or not selected or len(set(selected)) != len(selected)
            or any(case not in OFFLINE_REQUIRED_CASES for case in selected)):
        raise ValueError("APP.UAT.page_plan_invalid: diagnostic case selection is invalid")
    return tuple(case for case in OFFLINE_REQUIRED_CASES if case in selected)


def offline_case_spec_ref(case_id: str) -> str:
    if case_id not in OFFLINE_REQUIRED_CASES:
        raise ValueError("APP.UAT.page_plan_invalid: unknown required case")
    return OFFLINE_SPEC_REF if OFFLINE_REQUIRED_CASES.index(case_id) < OFFLINE_REQUIRED_CASES.index("login-cancel") else OFFLINE_SPEC_REF.replace("#gwt-007", "#gwt-008")


def offline_case_blocker(case_id: str) -> str:
    """编排缺口已接到 launcher-only relay；无 blocker 的格才进入 native 执行。"""
    if case_id not in OFFLINE_REQUIRED_CASES:
        raise ValueError("APP.UAT.page_plan_invalid: unknown required case")
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
    commit = str(candidate.get("commit") or "")
    tree = str(candidate.get("tree") or "")
    if len(commit) != 40 or len(tree) != 40:
        raise ValueError("APP.LAUNCH.receipt_invalid: candidate commit/tree identity is invalid")
    try:
        actual = subprocess.check_output(
            ["git", "rev-parse", "--verify", f"{commit}^{{tree}}"],
            cwd=repository,
            text=True,
        ).strip()
    except subprocess.CalledProcessError as exc:
        raise ValueError("APP.LAUNCH.receipt_invalid: candidate commit is unreadable") from exc
    if actual != tree:
        raise ValueError("APP.LAUNCH.receipt_invalid: candidate tree mismatch")


def _export_candidate_tree(
    *,
    commit: str,
    repository: Path,
    destination: Path,
    roots: Sequence[str],
) -> Path:
    if destination.exists() or destination.is_symlink():
        raise ValueError("APP.LAUNCH.receipt_invalid: candidate source checkout must be new")
    destination.mkdir(parents=True)
    existing: list[str] = []
    for root in roots:
        probe = subprocess.run(
            ["git", "cat-file", "-e", f"{commit}:{root}"],
            cwd=repository,
            capture_output=True,
            check=False,
        )
        if probe.returncode == 0:
            existing.append(str(root))
    if not existing:
        raise ValueError("APP.LAUNCH.receipt_invalid: candidate source roots missing")
    archive = subprocess.Popen(
        ["git", "archive", "--format=tar", commit, "--", *existing],
        cwd=repository,
        stdout=subprocess.PIPE,
    )
    try:
        extracted = subprocess.run(
            ["tar", "-x", "-C", str(destination)],
            stdin=archive.stdout,
            capture_output=True,
            check=False,
        )
    finally:
        if archive.stdout is not None:
            archive.stdout.close()
        archive.wait()
    if archive.returncode != 0 or extracted.returncode != 0:
        raise ValueError("APP.LAUNCH.receipt_invalid: candidate source export failed")
    return destination


_PROJECTION_SEAL_MARKERS = (
    "derived output rejected by policy",
    "symlink escapes build root",
    "partial build projection seal identity",
    "build projection seal failed",
)


def first_typed_blocker(error: object, *, fallback: str = "APP.UAT.page_artifact_binding_missing") -> str:
    text = str(error)
    if any(marker in text for marker in _PROJECTION_SEAL_MARKERS):
        return "APP.LAUNCH.projection_seal_rejected"
    code = getattr(error, "code", "")
    if isinstance(code, str) and re.fullmatch(r"[A-Z][A-Z0-9_]*(?:\.[A-Za-z0-9_]+){2,}", code):
        return code
    match = re.search(r"\b[A-Z][A-Z0-9_]*(?:\.[A-Za-z0-9_]+){2,}\b", text)
    return match.group(0) if match else fallback


def _prepare_launch(candidate: Mapping[str, Any], report_dir: Path, output_root: Path, platform: str = "ios-simulator") -> tuple[dict[str, Any], dict[str, Any]]:
    from quwoquan_ops.cli.lib.app_source_capsule import app_source_capsule_roots
    from quwoquan_ops.cli.lib.package_reuse import materialize_package_input_capsule, workspace_snapshot
    from quwoquan_ops.cli.commands.app_preflight_uat_launch import materialize_app_content_launch_projection
    import quwoquan_ops.cli.stackctl as stackctl

    graph = "quwoquan_service/generated/contract_graph.json"
    roots = (*app_source_capsule_roots(), graph)
    dependency_platform = "android" if platform.startswith("android") else "ios"
    _verify_source(candidate, stackctl.ROOT)
    checkout = _export_candidate_tree(
        commit=str(candidate["commit"]),
        repository=stackctl.ROOT,
        destination=(report_dir / "candidate-source").absolute(),
        roots=roots,
    )
    snapshot_kwargs = {
        "deployment_roots": roots,
        "dependency_platforms": (dependency_platform,),
        "source_revision": str(candidate["commit"]),
        "source_root": checkout,
        "source_tree": str(candidate["tree"]),
    }
    before = workspace_snapshot(**snapshot_kwargs)
    capsule = materialize_package_input_capsule(
        roots, capsule_root=(report_dir / "source-capsule").absolute(),
        dependency_platforms=(dependency_platform,),
        source_revision=str(candidate["commit"]),
        source_root=checkout,
        source_tree=str(candidate["tree"]),
    )
    after = workspace_snapshot(**snapshot_kwargs)
    if before != after:
        raise ValueError("APP.LAUNCH.receipt_invalid: source changed while freezing App capsule")
    graph_path = checkout / graph
    if not graph_path.is_file():
        raise ValueError("APP.LAUNCH.receipt_invalid: candidate contract graph missing")
    runtime = {
        "contentSource": "bundled_snapshot", "environment": "alpha", "target": "alpha-local",
        "candidateDigest": candidate["candidateId"], "sourceRevision": candidate["commit"],
        "sourceCapsuleBaselineId": capsule["baselineId"],
        "sourceCapsuleDigest": capsule["deploymentInputDigest"],
        "sourceCapsuleWorkspaceStatusDigest": capsule["workspaceStatusDigest"],
        "sourceCapsuleManifestRef": str(Path(capsule["capsuleRoot"]) / "manifest.json"),
        "contractGraphDigest": _sha(graph_path),
    }
    projection = materialize_app_content_launch_projection(
        runtime_binding=runtime, output_root=output_root,
        projection_root=report_dir / "source-projection", evidence_path=report_dir / "source-projection.json",
    )
    return runtime, projection


def _isolated_selection(args: argparse.Namespace, runtime: Mapping[str, Any],
                        projection: Mapping[str, Any], *, case_id: str,
                        generation: int, attempt_ref: str) -> dict[str, str] | None:
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
    if case_id not in OFFLINE_REQUIRED_CASES or generation <= 0:
        raise ValueError("APP.LAUNCH.receipt_invalid: invalid rehearsal case lifecycle")
    binding = "sha256:" + hashlib.sha256(json.dumps([
        "gwt008-observation", runtime["candidateDigest"], args.device_id,
        case_id, str(generation), attempt_ref, pin,
    ], separators=(",", ":")).encode()).hexdigest()
    selected_instance = f"{instance}-{case_id}" if case_id == "identity-restart" else f"{instance}-{case_id}-{generation}"
    return {"mode": "isolated", "instanceId": selected_instance,
            "snapshotDigest": pin, "caseId": case_id,
            "lifecycleGeneration": str(generation), "observationBinding": binding}


def _launch(args: argparse.Namespace, runtime: Mapping[str, Any], projection: Mapping[str, Any],
            report_dir: Path, output_root: Path, *, case_id: str = "login-success",
            generation: int = 1, expected_build_projection_digest: str | None = None) -> dict[str, Any]:
    from quwoquan_ops.cli.commands.app_preflight_uat_launch import (
        FLUTTER_ANDROID_3_47_GRADLE_8_14_POLICY_ID, FLUTTER_IOS_3_47_COCOAPODS_1_16_POLICY_ID,
        write_app_content_launch_control,
    )
    from quwoquan_ops.cli.commands.app_preflight_uat_launch_binding import _app_content_launch_binding
    from quwoquan_ops.cli.commands.app_preflight_uat_support import _app_content_canonical_launch_command
    import quwoquan_ops.cli.stackctl as stackctl

    if case_id not in OFFLINE_REQUIRED_CASES or type(generation) is not int or generation <= 0:
        raise ValueError("APP.LAUNCH.receipt_invalid: invalid case/generation")
    # UUID 只分配 fresh 输出路径，不充当 session、观察摘要或授权。
    attempt = report_dir / "case-launches" / case_id / f"generation-{generation}" / uuid4().hex / "attempt-1" / "attempt.json"
    selection = _isolated_selection(args, runtime, projection, case_id=case_id,
        generation=generation, attempt_ref=str(attempt.absolute()))
    report = attempt.with_name("report.json")
    policy = FLUTTER_ANDROID_3_47_GRADLE_8_14_POLICY_ID if args.platform == "android" else FLUTTER_IOS_3_47_COCOAPODS_1_16_POLICY_ID
    control = write_app_content_launch_control(
        runtime_binding=runtime, projection=projection, output_root=output_root,
        control_path=attempt.with_name("control.json"), attempt_path=attempt, report_path=report,
        terminal_receipt_path=attempt.with_name("startup-terminal.json"), platform=args.platform,
        device_id=args.device_id, build_projection_policy_id=policy,
        build_projection_seal_path=attempt.with_name("build-projection-seal.json"),
        expected_build_projection_digest=expected_build_projection_digest,
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
    # 只传公开进程身份，secret不进入环境；native将在启动时固定expected peer。
    if selection is not None and args.platform == 'ios-simulator':
        environment["QWQ_UAT_LAUNCHER_PID"] = str(os.getpid())
    if expected_build_projection_digest is not None and args.platform == "ios-simulator":
        # 复用密封投影的启动不再自己物化依赖，因此 CocoaPods 身份必须由 launcher
        # 冻结后传入；与 canonical hot-restart 重试同一条身份路径。
        from quwoquan_ops.cli.lib.app_dependency_toolchain import (
            COCOAPODS_ENVIRONMENT_KEYS, cocoapods_environment, resolve_cocoapods_identity,
        )
        frozen = cocoapods_environment(resolve_cocoapods_identity(), base=os.environ)
        environment["PATH"] = frozen["PATH"]
        environment.update({key: frozen[key] for key in COCOAPODS_ENVIRONMENT_KEYS})
    result = stackctl.run(command, cwd=app_root, env=environment)
    with attempt.with_name("canonical-launch.log").open("x", encoding="utf-8") as log:
        log.write((result.stdout or "") + (result.stderr or ""))
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
        selected = selected_offline_cases(args)
        diagnostic = getattr(args, "offline_cases", None) is not None
        if diagnostic:
            receipt.update(diagnostic=True, selectedCases=list(selected), profile="diagnostic")
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
            if diagnostic:
                selection = {"candidateDigest": candidate["candidateId"], "commitSha": candidate["commit"],
                    "platform": args.platform, "deviceId": args.device_id, "cases": list(selected)}
                selection["selectionDigest"] = "sha256:" + hashlib.sha256(json.dumps(selection, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
                receipt["diagnosticSelection"] = selection
            runtime, projection = _prepare_launch(
                candidate, report_dir, output_root, args.platform
            )
            binding = _launch(args, runtime, projection, report_dir, output_root,
                              case_id=selected[0], generation=1)
            from quwoquan_ops.cli.commands.app_preflight_uat_offline_pages import execute_offline_page_cases
            receipt.update(execute_offline_page_cases(
                args=args, candidate=candidate, launch=binding, projection=projection,
                report_dir=report_dir, output_root=output_root,
                # 每格 fresh 启动复用首次已密封的构建投影：私有依赖投影只允许 fresh
                # 目标，重投影会撞已存在的 pub cache/CocoaPods 状态；expected digest
                # 仍逐字节证明整棵树未漂移。
                launch_case=lambda case_id, generation: _launch(
                    args, runtime, projection, report_dir, output_root,
                    case_id=case_id, generation=generation,
                    expected_build_projection_digest=str(
                        binding["buildProjectionSeal"]["buildProjectionDigest"]
                    ),
                ),
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
