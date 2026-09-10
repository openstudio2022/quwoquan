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
    "image-detail", "creator-avatar", "video-complete", "video-seek",
    "empty-state", "pagination-end", "login-unavailable", "write-unavailable", "private-unavailable",
)


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


def _launch(args: argparse.Namespace, runtime: Mapping[str, Any], projection: Mapping[str, Any],
            report_dir: Path, output_root: Path) -> dict[str, Any]:
    from quwoquan_ops.cli.commands.app_preflight_uat_launch import (
        FLUTTER_ANDROID_3_47_GRADLE_8_14_POLICY_ID, FLUTTER_IOS_3_47_COCOAPODS_1_16_POLICY_ID,
        write_app_content_launch_control,
    )
    from quwoquan_ops.cli.commands.app_preflight_uat_launch_binding import _app_content_launch_binding
    from quwoquan_ops.cli.commands.app_preflight_uat_support import _app_content_canonical_launch_command
    import quwoquan_ops.cli.stackctl as stackctl

    attempt = report_dir / "attempt-1" / "attempt.json"
    report = attempt.with_name("report.json")
    policy = FLUTTER_ANDROID_3_47_GRADLE_8_14_POLICY_ID if args.platform == "android" else FLUTTER_IOS_3_47_COCOAPODS_1_16_POLICY_ID
    control = write_app_content_launch_control(
        runtime_binding=runtime, projection=projection, output_root=output_root,
        control_path=attempt.with_name("control.json"), attempt_path=attempt, report_path=report,
        terminal_receipt_path=attempt.with_name("startup-terminal.json"), platform=args.platform,
        device_id=args.device_id, build_projection_policy_id=policy,
        build_projection_seal_path=attempt.with_name("build-projection-seal.json"), expected_build_projection_digest=None,
    )
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
        if not getattr(args, "dry_run", False):
            candidate = _candidate(args, stackctl.ROOT)
            runtime, projection = _prepare_launch(candidate, report_dir, output_root)
            binding = _launch(args, runtime, projection, report_dir, output_root)
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
