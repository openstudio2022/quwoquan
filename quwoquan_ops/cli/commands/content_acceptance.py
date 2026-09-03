"""stackctl 内容验收域（content-readiness / content-uat / account-enforcement-uat）。

从 stackctl.py 逐字迁出：

- `register_content_readiness_parser` / `register_uat_parsers`：稳定再导出三个
  子命令的 argparse 表面；定义由同 package 的 `content_acceptance_parser`
  拥有，注册顺序保持不变；
- `command_content_readiness`：按 phase 的最小 typed capability 评估；
- `command_content_uat`：release-bound 首页 Patrol 真机验收（含 Data
  acceptance lease 的 acquire/revoke 闭环）；
- `command_account_enforcement_uat`：Gamma 账号治理真机阶段与 CaseResult 聚合；
- 仅被上述命令消费的专属 helper：`_content_release_uat_command` /
  `_run_data_acceptance_lease` / `_run_release_video_delivery_probe` /
  `_release_feed_post_expectations` / `_run_release_feed_readback_probe`。

data readiness 真相源家族（`_load_data_release_readiness` /
`_load_data_release_lifecycle_exit` / `_data_readiness_segment` /
`_canonical_document_checksum` 等）仍由 stackctl 命名空间拥有（app-content
留守域共用）；`_run_environment_integration_probe` / `_read_json_object` /
`command_health` / `command_doctor` 等亦同。测试经
``mock.patch.object(stackctl, ...)`` patch 上述符号与本模块符号，因此
函数体内一律经函数内延迟导入 `_stackctl` 属性访问（含本模块符号），
保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.lib.content_release_readiness import (
    ProbeOutcome,
    ProbeSource,
    ReadinessPhase,
    ShipReadinessReceipt,
)


from quwoquan_ops.cli.commands.content_acceptance_parser import (
    register_content_api_consumer_parser,
    register_content_readiness_parser,
    register_uat_parsers,
)


def _content_release_uat_command(
    *,
    target_name: str,
    release_uat_cases: Path,
    platform: str,
    device_ids: list[str],
    report_dir: Path,
) -> dict[str, Any]:
    """Build the release-bound Patrol command from the canonical environment topology."""
    import quwoquan_ops.cli.stackctl as _stackctl

    command = _stackctl._environment_page_smoke_profile_command(
        "gamma",
        target_name,
        report_dir,
    )
    if command is None:
        raise ValueError(f"content UAT topology is incomplete for {target_name}")
    argv = list(command["argv"])
    target_index = argv.index("--target") + 1
    argv[target_index] = _stackctl.RELEASE_HOMEPAGE_UAT_TEST_TARGET
    argv.extend(("--release-uat-cases", str(release_uat_cases), "--platform", platform))
    for device_id in device_ids:
        argv.extend(("--device-id", device_id))
    command["name"] = f"{target_name}-content-release-uat"
    command["argv"] = argv
    return command


def _run_release_video_delivery_probe(
    *,
    target: str,
    readiness_path: Path,
    report_dir: Path,
) -> tuple[dict[str, Any], Path]:
    """Prove release-bound HTTPS bytes, Range 206, duration and first frame."""
    import quwoquan_ops.cli.stackctl as _stackctl

    report_path = report_dir / "report.json"
    # Local gamma/alpha/beta serve media with the stackctl-managed root CA.
    # System trust alone fails self-signed chains; bind SSL_CERT_FILE so
    # urllib/ffprobe use the same public-domain trust as host probes.
    probe_env = dict(os.environ)
    if target in {"alpha-local", "beta-local", "gamma-local"}:
        try:
            probe_env["SSL_CERT_FILE"] = str(_stackctl.root_certificate_path(target))
            probe_env["REQUESTS_CA_BUNDLE"] = probe_env["SSL_CERT_FILE"]
            probe_env["CURL_CA_BUNDLE"] = probe_env["SSL_CERT_FILE"]
        except _stackctl.PublicDomainTlsError as exc:
            raise ValueError(
                f"release video delivery probe missing local root CA: {exc}"
            ) from exc
    result = _stackctl.run(
        [
            "python3",
            "quwoquan_ops/cli/smoke/verify_video_playback_canary.py",
            "--target",
            target,
            "--release-readiness",
            str(readiness_path),
            "--report",
            str(report_path),
        ],
        env=probe_env,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise ValueError(
            "release video delivery probe failed: "
            + (detail[:800] if detail else f"exit={result.returncode}")
        )
    evidence = _stackctl._read_json_object(str(report_path))
    if (
        evidence.get("schema") != "quwoquan_ops.release_video_delivery_evidence"
        or evidence.get("status") != "passed"
    ):
        raise ValueError(
            "release video delivery probe did not emit a passed typed report"
        )
    return evidence, report_path


# consumer 起就要求 `premium_stream` 有 release-bound 读回，与 receipt 校验器同源
# （environment-topology-and-packaging REQ-002）。实时探测一度只从 research 起校验，
# 于是同一件事有两套判断；这里收敛成唯一闭集。
_PREMIUM_BOUND_PHASES = frozenset(
    {
        ReadinessPhase.CONSUMER,
        ReadinessPhase.RESEARCH,
        ReadinessPhase.COMMERCIAL,
    }
)


def _release_feed_post_expectations(
    receipt: dict[str, Any],
    *,
    readiness_phase: ReadinessPhase,
) -> dict[str, set[str]]:
    """Return the immutable-release post IDs each live exact query must expose."""

    queries = {
        str(item.get("name") or ""): item
        for item in receipt.get("feedQueries") or []
        if isinstance(item, dict)
    }
    discovery_ids = {
        str(item).strip()
        for item in queries.get("discovery_work", {}).get("matchedPostIds") or []
        if str(item).strip()
    }
    video_ids = {
        str(item).strip()
        for item in queries.get("typed_video", {}).get("matchedPostIds") or []
        if str(item).strip()
    }
    premium_ids = {
        str(item).strip()
        for item in queries.get("premium_stream", {}).get("matchedPostIds") or []
        if str(item).strip()
    }
    premium_video_ids = premium_ids.intersection(video_ids)
    expectations = {
        "content_feed": discovery_ids,
        "video_book_feed": video_ids,
    }
    if readiness_phase in _PREMIUM_BOUND_PHASES:
        expectations["premium_feed"] = premium_video_ids
    empty = sorted(name for name, post_ids in expectations.items() if not post_ids)
    if empty:
        raise ValueError(
            "canonical Data readiness has no release-bound expectation for: "
            + ", ".join(empty)
        )
    return expectations


def _run_release_feed_readback_probe(
    *,
    target: str,
    receipt: dict[str, Any],
    readiness_path: Path,
    report_dir: Path,
    readiness_phase: ReadinessPhase,
) -> tuple[dict[str, Any], Path]:
    """Re-read live discovery/video/premium and bind results to receipt post IDs.

    research 相位语义反转（DEC-032）：匿名 feed 必须收敛为 no_active_release
    空页且不回显 release 身份——非空即隔离泄露。带凭证的 research 内容消费
    证据由 Data post-api verification（research consumer credential）单点拥有，
    本探针不重复。
    """
    import quwoquan_ops.cli.stackctl as _stackctl

    research = readiness_phase is ReadinessPhase.RESEARCH
    report_file = report_dir / "integration-probe.json"
    try:
        check, _output, findings = _stackctl._run_environment_integration_probe(
            _stackctl.load_environment_topology(),
            target,
            report_dir,
            require_non_empty_content_feed=not research,
            research_anonymous_convergence=research,
            release_post_expectations=(
                None
                if research
                else _stackctl._release_feed_post_expectations(
                    receipt,
                    readiness_phase=readiness_phase,
                )
            ),
            release_readiness_path=readiness_path,
            only_checks=(
                "content_feed",
                "video_book_feed",
                *(
                    ("premium_feed",)
                    if readiness_phase in _PREMIUM_BOUND_PHASES
                    else ()
                ),
                # research 私有交付没有匿名可采样的公开图片 slice；私有媒体
                # 的拒绝与短签取回由 Data research isolation 证据覆盖。
                *(("media_sample",) if not research else ()),
            ),
            probe_name="release-bound-feed-readback",
        )
    except RuntimeError as exc:
        raise ValueError(f"local TLS trust is unavailable: {exc}") from exc
    report = _stackctl._read_json_object(str(report_file))
    if not bool(check.get("ok")) or findings or report.get("status") != "passed":
        details = findings or ["release-bound feed readback did not pass"]
        raise ValueError("; ".join(str(item) for item in details))
    return report, report_file


def command_content_api_consumer(args: argparse.Namespace) -> dict[str, Any]:
    """Run the strict read-only content API matrix from explicit authorities."""

    import quwoquan_ops.cli.stackctl as _stackctl
    from quwoquan_ops.cli.lib.content_api_consumer import ContentApiConsumerError

    try:
        return _stackctl.run_content_api_consumer(
            target=args.target,
            release_id=args.release_id,
            import_run_id=args.import_run_id,
            verify_run_id=args.verify_run_id,
            manifest_digest=args.manifest_digest,
            sample_plan_ref=args.sample_plan_ref,
            sample_plan_digest=args.sample_plan_digest,
            data_readiness_ref=args.data_readiness_ref,
            data_readiness_digest=args.data_readiness_digest,
            consumer_health_ref=args.consumer_health_ref,
            consumer_health_digest=args.consumer_health_digest,
            report_dir=Path(args.report_dir),
            output_root=_stackctl.output_root(),
        )
    except (ContentApiConsumerError, OSError, ValueError) as exc:
        return {
            "exitCode": 2,
            "summary": "content API consumer is GATE_BLOCK",
            "details": [str(exc)],
            "reportDir": str(args.report_dir),
        }


def command_content_readiness(args: argparse.Namespace) -> dict[str, Any]:
    """Assess one release phase against its minimal, typed capability set.

    This is deliberately not a global doctor and is never an execution-create
    precondition.  It is called when an environment is actually about to import,
    serve consumers, or claim commercial observability.
    """
    import quwoquan_ops.cli.stackctl as _stackctl

    phase = ReadinessPhase(args.phase)
    policy = _stackctl.load_content_release_readiness_policy()
    requirement = policy.requirement_for(phase=phase, environment=args.env)
    report_dir = (
        Path(args.report_dir)
        if getattr(args, "report_dir", "")
        else _stackctl.repo_run_dir(
            "content-readiness", target=f"{args.env}-{phase.value}"
        )
    )
    started_monotonic, started_at = _stackctl._start_timing()
    health = _stackctl.command_health(
        argparse.Namespace(
            command="health",
            target=requirement.target,
            scope=requirement.health_scope,
            workload=requirement.workload,
            # research 相位的匿名 feed 正确形态是 no_active_release 空页
            # （DEC-032 收敛）：health 的 content-consumer scope 在 research
            # 下改跑匿名收敛断言，非空断言只对公开 serving 相位成立。
            require_non_empty_content_feed=phase
            in {
                ReadinessPhase.CONSUMER,
                ReadinessPhase.COMMERCIAL,
            },
            research_anonymous_convergence=(
                phase is ReadinessPhase.RESEARCH
                and bool(str(getattr(args, "verify_run_id", "") or "").strip())
            ),
            output_format="json",
            report_dir=str(report_dir / "health"),
        )
    )
    details = list(health.get("details", [])) if int(health["exitCode"]) != 0 else []
    if phase is ReadinessPhase.IMPORT:
        # import 门只消费 policy 声明能力（content_api/content_media/
        # content_services）的探针结论。health 附带的 user availability 聚合
        # 里 release_active 层描述的是「当前 serving release 的已验证证据」，
        # 而首个 release 的导入正是为了创造这份证据（bootstrap），不得把
        # 导入后才存在的 readiness receipt 倒置为导入前置。
        details = [
            item for item in details if not str(item).startswith("user availability/")
        ]
    if phase is ReadinessPhase.RESEARCH:
        # research readiness 的消费主体是受保护内部研究身份（API 面），App
        # 设备消费面显式 deferred（DEC-031 / OPEN-015）：device lease 与
        # content-live 心跳不构成 research 准入，release binding 层保留。
        details = [
            item
            for item in details
            if not str(item).startswith("user availability/device")
            and not str(item).startswith("user availability/content_live")
        ]
    executed_checks = [
        item
        for item in _stackctl._read_json_object(
            str(report_dir / "health" / "report.json")
        ).get("checks", [])
        if isinstance(item, dict)
        and str(item.get("name") or "")
        and not item.get("skipped")
    ]
    probes = [str(item["name"]) for item in executed_checks]
    executed_scopes = {str(item.get("scope") or "") for item in executed_checks}
    data_readiness_receipt: dict[str, Any] | None = None
    data_readiness_path: Path | None = None
    feed_readback_evidence: dict[str, Any] | None = None
    feed_readback_path: Path | None = None
    video_delivery_evidence: dict[str, Any] | None = None
    video_delivery_path: Path | None = None
    lifecycle_exit_receipt: dict[str, Any] | None = None
    lifecycle_exit_path: Path | None = None
    research_isolation: dict[str, Any] | None = None
    has_research_verify_receipt = phase is ReadinessPhase.RESEARCH and bool(
        str(getattr(args, "verify_run_id", "") or "").strip()
    )
    if (
        phase in {ReadinessPhase.CONSUMER, ReadinessPhase.COMMERCIAL}
        or has_research_verify_receipt
    ):
        try:
            data_readiness_receipt, data_readiness_path = (
                _stackctl._load_data_release_readiness(
                    environment=args.env,
                    release_id=getattr(args, "release_id", ""),
                    verify_run_id=getattr(args, "verify_run_id", ""),
                    manifest_digest=getattr(args, "manifest_digest", ""),
                    readiness_phase=phase,
                )
            )
            probes.append("canonical-data-release-readiness")
        except ValueError as exc:
            details.append(str(exc))
        if data_readiness_path is not None and data_readiness_receipt is not None:
            if phase is ReadinessPhase.COMMERCIAL:
                try:
                    lifecycle_exit_receipt, lifecycle_exit_path = (
                        _stackctl._load_data_release_lifecycle_exit(
                            environment=args.env,
                            release_id=getattr(args, "release_id", ""),
                            manifest_digest=getattr(args, "manifest_digest", ""),
                            readiness=data_readiness_receipt,
                            lifecycle_exit_ref=getattr(
                                args,
                                "lifecycle_exit_ref",
                                "",
                            ),
                        )
                    )
                    probes.append("canonical-data-release-lifecycle-exit")
                except ValueError as exc:
                    details.append(str(exc))
            try:
                feed_readback_evidence, feed_readback_path = (
                    _stackctl._run_release_feed_readback_probe(
                        target=requirement.target,
                        receipt=data_readiness_receipt,
                        readiness_path=data_readiness_path,
                        report_dir=report_dir / "release-feed-readback",
                        readiness_phase=phase,
                    )
                )
                probes.append("release-bound-feed-readback")
            except ValueError as exc:
                details.append(f"release-bound feed readback failed: {exc}")
            if phase is ReadinessPhase.COMMERCIAL:
                # 匿名视频播放 canary 只对公开 CDN 交付（commercial）成立；
                # research 私有交付（DEC-031）的视频证据是 Data 侧
                # researchMediaProbe 的匿名 401/403 拒绝 + isolation probe。
                try:
                    video_delivery_evidence, video_delivery_path = (
                        _stackctl._run_release_video_delivery_probe(
                            target=requirement.target,
                            readiness_path=data_readiness_path,
                            report_dir=report_dir / "release-video-delivery",
                        )
                    )
                    probes.append("release-video-delivery")
                except ValueError as exc:
                    details.append(str(exc))
    for capability in requirement.capabilities:
        binding = policy.probe_binding_for(capability)
        if (
            binding.source is ProbeSource.HEALTH_SCOPE
            and binding.health_scope not in executed_scopes
        ):
            details.append(
                f"capability {capability.value} declares probe scope "
                f"{binding.health_scope} but no probe executed for {requirement.target}"
            )
        if binding.source is ProbeSource.RESEARCH_ISOLATION:
            try:
                research_isolation = _stackctl.verify_research_content_isolation(
                    args.env,
                    release_id=str(getattr(args, "release_id", "") or "").strip(),
                    verify_run_id=str(getattr(args, "verify_run_id", "") or "").strip(),
                    manifest_digest=str(
                        getattr(args, "manifest_digest", "") or ""
                    ).strip(),
                    data_readiness=data_readiness_receipt,
                    data_readiness_path=data_readiness_path,
                )
                probes.append("governed-research-content-isolation")
            except ValueError as exc:
                details.append(str(exc))
        if binding.source is ProbeSource.LOG_SINK_CONTROL:
            action = binding.control_action
            if not action:
                details.append(
                    f"capability {capability.value} has no log-sink control action"
                )
                continue
            log_sink_result = _stackctl.command_product_telemetry_log_sink(
                argparse.Namespace(
                    command="product-telemetry-log-sink",
                    target=requirement.target,
                    action=action,
                    output_format="json",
                    report_dir=str(report_dir / "product-telemetry-log-sink"),
                )
            )
            probes.append(f"product-telemetry-log-sink:{action}")
            if int(log_sink_result["exitCode"]) != 0:
                details.extend(
                    f"capability {capability.value}: {item}"
                    for item in log_sink_result.get("details", [])
                )
    if phase is ReadinessPhase.COMMERCIAL:
        doctor = _stackctl.command_doctor(
            argparse.Namespace(
                command="doctor",
                target=requirement.target,
                output_format="json",
                report_dir=str(report_dir / "commercial-prerequisites"),
            )
        )
        if int(doctor["exitCode"]) != 0:
            details.extend(str(item) for item in doctor.get("details", []))
    outcome = ProbeOutcome.PASS if not details else ProbeOutcome.GATE_BLOCK
    timing = _stackctl._finish_timing(started_monotonic, started_at)
    receipt = ShipReadinessReceipt(
        policy_id=policy.policy_id,
        phase=phase,
        environment=requirement.environment,
        target=requirement.target,
        workload=requirement.workload,
        outcome=outcome,
        capabilities=requirement.capabilities,
        probes=tuple(probes),
        report_dir=_stackctl.relpath(report_dir),
    )
    payload = {
        "schema": "quwoquan_ops.ship_readiness_receipt",
        "policyId": receipt.policy_id,
        "phase": receipt.phase.value,
        "environment": receipt.environment,
        "target": receipt.target,
        "workload": receipt.workload,
        "outcome": receipt.outcome.value,
        "capabilities": [item.value for item in receipt.capabilities],
        "probes": list(receipt.probes),
        "reportDir": receipt.report_dir,
        "dataRelease": {
            "releaseId": getattr(args, "release_id", ""),
            "verifyRunId": getattr(args, "verify_run_id", ""),
            "manifestDigest": getattr(args, "manifest_digest", ""),
            "receiptRef": _stackctl.relpath(data_readiness_path)
            if data_readiness_path
            else "",
            "receipt": data_readiness_receipt,
            "lifecycleExitRef": (
                str(getattr(args, "lifecycle_exit_ref", "")).strip()
                if lifecycle_exit_path
                else ""
            ),
            "lifecycleExit": lifecycle_exit_receipt,
            "feedReadbackEvidenceRef": (
                _stackctl.relpath(feed_readback_path) if feed_readback_path else ""
            ),
            "feedReadback": feed_readback_evidence,
            "videoDeliveryEvidenceRef": (
                _stackctl.relpath(video_delivery_path) if video_delivery_path else ""
            ),
            "videoDelivery": video_delivery_evidence,
        },
        "researchContentIsolation": research_isolation,
        **timing,
    }
    _stackctl.write_json(report_dir / "report.json", payload)
    _stackctl.write_json(report_dir / "findings.json", {"issues": details})
    _stackctl._write_summary_bundle(
        report_dir,
        command="content-readiness",
        target=requirement.target,
        status="ok" if outcome is ProbeOutcome.PASS else "blocked",
        summary=(
            f"content readiness {phase.value}/{args.env} passed"
            if outcome is ProbeOutcome.PASS
            else f"content readiness {phase.value}/{args.env} is GATE_BLOCK"
        ),
        details=details or ["all required capabilities are available"],
        extra={
            "policyId": policy.policy_id,
            "phase": phase.value,
            "outcome": outcome.value,
            "dataRelease": payload["dataRelease"],
        },
        timing=timing,
    )
    return {
        **payload,
        "exitCode": 0 if outcome is ProbeOutcome.PASS else 2,
        "summary": (
            f"content readiness {phase.value}/{args.env} passed"
            if outcome is ProbeOutcome.PASS
            else f"content readiness {phase.value}/{args.env} is GATE_BLOCK"
        ),
        "details": details or ["all required capabilities are available"],
    }


def command_content_uat(args: argparse.Namespace) -> dict[str, Any]:
    """Run the release-bound homepage Patrol suite against Gamma consumer APIs."""
    import quwoquan_ops.cli.stackctl as _stackctl

    report_dir = _stackctl.resolve_report_dir(args, "gamma", args.target)
    started_monotonic, started_at = _stackctl._start_timing()
    cases_path = Path(args.release_uat_cases).expanduser()
    allowed_root = _stackctl.env_runs_root("gamma") / "data-release"
    release_id = ""
    import_run_id = ""
    lease_acquire: dict[str, Any] | None = None
    try:
        resolved_cases = cases_path.resolve(strict=True)
        case_ref = resolved_cases.relative_to(allowed_root.resolve(strict=True))
        if (
            len(case_ref.parts) != 3
            or case_ref.parts[2] != "homepage_verification_cases.json"
        ):
            raise ValueError(
                "release UAT cases must be exactly "
                "<releaseId>/<importRunId>/homepage_verification_cases.json"
            )
        release_id, import_run_id, _filename = case_ref.parts
        verify_run_id = _stackctl._data_readiness_segment(
            str(getattr(args, "data_verify_run_id", "")),
            label="dataVerifyRunId",
        )
        lease_id = _stackctl._data_readiness_segment(
            str(getattr(args, "acceptance_lease_id", "")),
            label="acceptanceLeaseId",
        )
        command = _stackctl._content_release_uat_command(
            target_name=args.target,
            release_uat_cases=resolved_cases,
            platform=args.platform,
            device_ids=list(args.device_id),
            report_dir=report_dir,
        )
        lease_acquire = _stackctl._run_data_acceptance_lease(
            action="acquire",
            environment="gamma",
            release_id=release_id,
            import_run_id=import_run_id,
            verify_run_id=verify_run_id,
            lease_id=lease_id,
        )
    except (OSError, ValueError) as exc:
        timing = _stackctl._finish_timing(started_monotonic, started_at)
        details = [str(exc)]
        payload = {
            "command": "content-uat",
            "target": args.target,
            "status": ProbeOutcome.GATE_BLOCK.value,
            "releaseUatCases": str(cases_path),
            "details": details,
            **timing,
        }
        _stackctl.write_json(report_dir / "report.json", payload)
        _stackctl.write_json(report_dir / "findings.json", {"issues": details})
        _stackctl._write_summary_bundle(
            report_dir,
            command="content-uat",
            target=args.target,
            status="gate_block",
            summary="content UAT is GATE_BLOCK",
            details=details,
            timing=timing,
        )
        return {
            "exitCode": 2,
            "summary": "content UAT is GATE_BLOCK",
            "details": details,
            "reportDir": _stackctl.relpath(report_dir),
            **timing,
        }

    result = _stackctl.run(command["argv"], cwd=command["cwd"], env=command.get("env"))
    runner_report = _stackctl._read_json_object(
        str(_stackctl.ROOT / str(command["reportPath"]))
    )
    runner_status = str(runner_report.get("status") or "failed")
    lease_revoke: dict[str, Any] | None = None
    lease_revoke_error = ""
    try:
        lease_revoke = _stackctl._run_data_acceptance_lease(
            action="revoke",
            environment="gamma",
            release_id=release_id,
            lease_id=str(lease_acquire["leaseId"]),
            acquire_event_ref=str(lease_acquire["eventRef"]),
        )
    except ValueError as exc:
        lease_revoke_error = str(exc)
    status = (
        "ok"
        if result.returncode == 0 and runner_status == "passed"
        else (
            "gate_block"
            if result.returncode == 2 or runner_status == "gate_block"
            else "failed"
        )
    )
    details = _stackctl._command_details(result)
    if lease_revoke_error:
        status = "gate_block"
        details.append(
            "acceptance lease revoke failed; release remains protected: "
            + lease_revoke_error
        )
    timing = _stackctl._finish_timing(started_monotonic, started_at)
    payload = {
        "command": "content-uat",
        "target": args.target,
        "status": status,
        "releaseUatCases": _stackctl.relpath(resolved_cases),
        "runnerReport": command["reportPath"],
        "runnerStatus": runner_status,
        "acceptanceLease": {
            "acquireEventRef": str((lease_acquire or {}).get("eventRef") or ""),
            "revokeEventRef": str((lease_revoke or {}).get("eventRef") or ""),
            "closed": lease_revoke is not None,
        },
        "details": details,
        **timing,
    }
    _stackctl.write_json(report_dir / "report.json", payload)
    _stackctl.write_json(
        report_dir / "findings.json", {"issues": details if status != "ok" else []}
    )
    _stackctl._write_summary_bundle(
        report_dir,
        command="content-uat",
        target=args.target,
        status=status,
        summary=(
            "content UAT passed"
            if status == "ok"
            else "content UAT is GATE_BLOCK"
            if status == "gate_block"
            else "content UAT failed"
        ),
        details=details,
        extra={
            "releaseUatCases": _stackctl.relpath(resolved_cases),
            "runnerReport": command["reportPath"],
            "runnerStatus": runner_status,
            "acceptanceLease": payload["acceptanceLease"],
        },
        timing=timing,
    )
    return {
        "exitCode": 0 if status == "ok" else 2 if status == "gate_block" else 1,
        "summary": (
            "content UAT passed"
            if status == "ok"
            else "content UAT is GATE_BLOCK"
            if status == "gate_block"
            else "content UAT failed"
        ),
        "details": details,
        "reportDir": _stackctl.relpath(report_dir),
        **timing,
    }


def command_account_enforcement_uat(args: argparse.Namespace) -> dict[str, Any]:
    """Run one controlled App phase or aggregate the immutable Gamma CaseResult."""
    import quwoquan_ops.cli.stackctl as _stackctl

    report_dir = _stackctl.resolve_report_dir(args, "gamma", args.target)
    started_monotonic, started_at = _stackctl._start_timing()
    action = str(args.action)
    if action == "verify":
        child_report = report_dir / "case-result.json"
        journey_receipt = str(args.journey_receipt).strip() or str(
            report_dir / "journey-receipt.json"
        )
        suspended_device_report = str(args.suspended_device_report).strip() or str(
            report_dir / "suspended-device-report.json"
        )
        restored_device_report = str(args.restored_device_report).strip() or str(
            report_dir / "restored-device-report.json"
        )
        command = [
            "python3",
            _stackctl.ACCOUNT_ENFORCEMENT_GAMMA_UAT_VALIDATOR,
            "--manifest",
            str(args.manifest),
            "--run-id",
            str(args.run_id),
            "--candidate-digest",
            str(args.candidate_digest),
            "--journey-receipt",
            journey_receipt,
            "--suspended-device-report",
            suspended_device_report,
            "--restored-device-report",
            restored_device_report,
            "--report",
            str(child_report),
        ]
    else:
        phase = action.removeprefix("device-")
        child_report = report_dir / f"{phase}-device-report.json"
        command = [
            "python3",
            _stackctl.ACCOUNT_ENFORCEMENT_GAMMA_DEVICE_RUNNER,
            "--manifest",
            str(args.manifest),
            "--phase",
            phase,
            "--candidate-digest",
            str(args.candidate_digest),
            "--report",
            str(child_report),
        ]
        for device_id in list(args.device_id):
            normalized = str(device_id).strip()
            if normalized:
                command.extend(("--device-id", normalized))

    result = _stackctl.run(command, cwd=_stackctl.ROOT)
    child_payload = _stackctl._read_json_object(str(child_report))
    child_status = str(child_payload.get("status") or "failed")
    status = (
        "ok"
        if result.returncode == 0 and child_status == "passed"
        else "gate_block"
        if result.returncode == 2 or child_status == "gate_block"
        else "failed"
    )
    details = _stackctl._command_details(result)
    if not child_payload:
        details.append("account-enforcement child report is missing or unreadable")
    timing = _stackctl._finish_timing(started_monotonic, started_at)
    payload = {
        "command": "account-enforcement-uat",
        "target": args.target,
        "action": action,
        "status": status,
        "candidateDigest": str(args.candidate_digest),
        "childReport": _stackctl.relpath(child_report),
        "childStatus": child_status,
        "details": details,
        **timing,
    }
    _stackctl.write_json(report_dir / "report.json", payload)
    _stackctl.write_json(
        report_dir / "findings.json",
        {"issues": details if status != "ok" else []},
    )
    summary = (
        f"account-enforcement UAT {action} passed"
        if status == "ok"
        else f"account-enforcement UAT {action} is GATE_BLOCK"
        if status == "gate_block"
        else f"account-enforcement UAT {action} failed"
    )
    _stackctl._write_summary_bundle(
        report_dir,
        command="account-enforcement-uat",
        target=args.target,
        status=status,
        summary=summary,
        details=details,
        extra={
            "action": action,
            "candidateDigest": str(args.candidate_digest),
            "childReport": _stackctl.relpath(child_report),
            "childStatus": child_status,
        },
        timing=timing,
    )
    return {
        "exitCode": 0 if status == "ok" else 2 if status == "gate_block" else 1,
        "summary": summary,
        "details": details,
        "reportDir": _stackctl.relpath(report_dir),
        **timing,
    }


def _run_data_acceptance_lease(
    *,
    action: str,
    environment: str,
    release_id: str,
    lease_id: str,
    import_run_id: str = "",
    verify_run_id: str = "",
    acquire_event_ref: str = "",
) -> dict[str, Any]:
    """Invoke the Data-owned lease writer; stackctl never writes its schema."""
    import quwoquan_ops.cli.stackctl as _stackctl

    argv = [
        "python3",
        "-B",
        "quwoquan_data/scripts/cli.py",
        "release",
        "acceptance-lease",
        action,
        "--env",
        environment,
        "--release-id",
        release_id,
        "--lease-id",
        lease_id,
    ]
    if action == "acquire":
        argv.extend(
            (
                "--import-run-id",
                import_run_id,
                "--verify-run-id",
                verify_run_id,
            )
        )
    elif action == "revoke":
        argv.extend(("--acquire-event-ref", acquire_event_ref))
    else:
        raise ValueError("acceptance lease action must be acquire or revoke")
    result = _stackctl.run(argv, cwd=_stackctl.ROOT)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise ValueError(
            "Data acceptance lease command failed: "
            + (detail[:800] if detail else f"exit={result.returncode}")
        )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("Data acceptance lease command returned invalid JSON") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("schema") != "quwoquan_data.release_acceptance_lease_event"
        or payload.get("action") != action
        or payload.get("environment") != environment
        or payload.get("releaseId") != release_id
        or payload.get("leaseId") != lease_id
        or not str(payload.get("eventRef") or "")
    ):
        raise ValueError(
            "Data acceptance lease command returned identity-drifted evidence"
        )
    return payload
