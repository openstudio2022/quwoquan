"""stackctl app 预检域 candidate/test-live 内容证据解析与 release readback 探针。

从 commands/app_preflight.py 逐字迁出(该模块保留三命令主干与 argparse 表面,
本家族随内容证据职责聚合到本模块):

- `_resolve_active_app_content_evidence`:active candidate 到 Research /
  Commercial 精确证据的解析;
- `_resolve_test_live_app_content_evidence`:validated mutable binding 的
  test-live 证据解析(不询问 active candidate 状态);
- `_app_content_uat_envelope`:release readiness canonical appUatEnvelope
  的 fail-closed 校验;
- `_app_content_readback_summary`:readiness feedQueries/counts 的 readback
  摘要投影;
- `_run_app_content_release_probe`:按 readiness phase 执行 20 条视频页、
  release media 与必需 Search 的 release-bound live readback 探针。

`command_app_content_preflight` 等命令入口在 `commands/app_preflight.py`;
data readiness 真相源家族在 `commands/app_preflight_shared.py` 与
`commands/app_preflight_readiness.py`。测试经 ``mock.patch.object(stackctl,
...)`` patch 本模块符号与协作符号,因此函数体内一律经函数内延迟导入
`_stackctl` 属性访问(含本模块符号互调),保持 monkeypatch 语义并避免
顶层循环 import。
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping

from quwoquan_ops.cli.lib.content_release_readiness import ReadinessPhase


def _resolve_active_app_content_evidence(
    target: str,
) -> tuple[dict[str, Any], dict[str, Any], Path, str]:
    """Resolve an active candidate to exact Research or Commercial evidence."""
    import quwoquan_ops.cli.stackctl as _stackctl

    topology = _stackctl.load_environment_topology()
    environment = str(_stackctl.get_target(topology, target)["env"])
    active = _stackctl.active_deployment_candidate(target)
    if active is None:
        raise ValueError("active immutable runtime candidate is missing")
    manifest_path = Path(str(active["candidateDir"])) / "manifest.json"
    manifest = _stackctl._read_json_object(str(manifest_path))
    release = manifest.get("release") if isinstance(manifest, dict) else None
    candidate = release.get("candidate") if isinstance(release, dict) else None
    if not isinstance(candidate, dict):
        raise ValueError("active candidate does not bind a Data candidate release")
    release_id = str(candidate.get("releaseId") or "").strip()
    manifest_digest = str(candidate.get("releaseDigest") or "").strip()
    attestation_ref = str(candidate.get("attestationRef") or "").strip()
    attestation_digest = str(candidate.get("attestationDigest") or "").strip()
    if not release_id or _stackctl._DATA_READINESS_DIGEST_RE.fullmatch(manifest_digest) is None:
        raise ValueError("active candidate Data release identity is incomplete")
    if not attestation_ref or _stackctl._DATA_READINESS_DIGEST_RE.fullmatch(attestation_digest) is None:
        raise ValueError("active candidate Data release attestation identity is incomplete")
    attestation_path = Path(attestation_ref).expanduser().resolve()
    if not attestation_path.is_file():
        raise ValueError("active candidate Data release attestation is missing")
    actual_attestation_digest = "sha256:" + hashlib.sha256(
        attestation_path.read_bytes()
    ).hexdigest()
    if actual_attestation_digest != attestation_digest:
        raise ValueError("active candidate Data release attestation digest drifted")
    attestation = _stackctl._read_json_object(str(attestation_path))
    release_class = str(attestation.get("releaseClass") or "").strip()
    lifecycle_state = str(
        attestation.get("productLifecycleState") or ""
    ).strip()
    if release_class != lifecycle_state or release_class not in {
        ReadinessPhase.RESEARCH.value,
        ReadinessPhase.COMMERCIAL.value,
    }:
        raise ValueError("active candidate Data release lifecycle is invalid")
    readiness_phase = ReadinessPhase(release_class)

    readiness_root = _stackctl.env_runs_root(environment) / "data-release" / release_id
    lifecycle_root = (
        _stackctl.env_runs_root(environment)
        / "release-lifecycle-exit"
        / release_id
    )
    readiness_errors: list[str] = []
    lifecycle_errors: list[str] = []
    readiness_receipts: list[tuple[dict[str, Any], Path]] = []
    for readiness_path in sorted(
        readiness_root.glob("*/release-readiness.json"), reverse=True
    ):
        try:
            receipt, canonical_path = _stackctl._load_data_release_readiness(
                environment=environment,
                release_id=release_id,
                verify_run_id=readiness_path.parent.name,
                manifest_digest=manifest_digest,
                readiness_phase=readiness_phase,
            )
        except ValueError as exc:
            readiness_errors.append(str(exc))
            continue
        readiness_receipts.append((receipt, canonical_path))
    if not readiness_receipts:
        detail = readiness_errors[0] if readiness_errors else "no receipt exists"
        raise ValueError(
            f"active release has no valid {readiness_phase.value} readiness receipt: "
            + detail
        )

    if readiness_phase is ReadinessPhase.RESEARCH:
        selected_readiness, selected_readiness_path = readiness_receipts[0]
        return manifest, selected_readiness, selected_readiness_path, ""

    # Prefer any commercial readiness that binds a lifecycle Exit. Post-lifecycle
    # commercial verifies sit on the replay import; lexicographic "latest" alone
    # can otherwise pick a pre-lifecycle sibling commercial receipt first.
    for selected_readiness, selected_readiness_path in readiness_receipts:
        for lifecycle_path in sorted(
            lifecycle_root.glob("*/lifecycle-exit.json"), reverse=True
        ):
            try:
                candidate_ref = lifecycle_path.resolve().relative_to(
                    _stackctl.output_root().expanduser().resolve()
                ).as_posix()
            except ValueError:
                lifecycle_errors.append("lifecycle receipt escapes QWQ_OUTPUT_ROOT")
                continue
            try:
                _stackctl._load_data_release_lifecycle_exit(
                    environment=environment,
                    release_id=release_id,
                    manifest_digest=manifest_digest,
                    readiness=selected_readiness,
                    lifecycle_exit_ref=candidate_ref,
                )
            except ValueError as exc:
                lifecycle_errors.append(str(exc))
                continue
            return manifest, selected_readiness, selected_readiness_path, candidate_ref

    detail = lifecycle_errors[0] if lifecycle_errors else "no receipt exists"
    raise ValueError(
        "active release has no valid rollback/replay lifecycle receipt: " + detail
    )


def _resolve_test_live_app_content_evidence(
    target: str,
    binding: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], Path, str]:
    """Resolve one validated mutable binding without consulting active candidate state."""
    import quwoquan_ops.cli.stackctl as _stackctl

    topology = _stackctl.load_environment_topology()
    environment = str(_stackctl.get_target(topology, target)["env"])
    expected = {
        "target": target,
        "environment": environment,
        "launchPolicy": "test_live",
        "nonPromotable": True,
        "contentBindingState": "bound",
    }
    if any(binding.get(field) != value for field, value in expected.items()):
        raise ValueError("test_live content binding runtime identity mismatch")
    release_id = str(binding.get("releaseId") or "").strip()
    verify_run_id = str(binding.get("verifyRunId") or "").strip()
    manifest_digest = str(binding.get("manifestDigest") or "").strip()
    readiness_phase = str(binding.get("readinessPhase") or "").strip()
    if readiness_phase not in {
        ReadinessPhase.CONSUMER.value,
        ReadinessPhase.RESEARCH.value,
        ReadinessPhase.COMMERCIAL.value,
    }:
        raise ValueError("test_live content binding readinessPhase is invalid")
    expected_ref = (
        Path("env")
        / environment
        / "runs/data-release"
        / release_id
        / verify_run_id
        / "release-readiness.json"
    ).as_posix()
    readiness_ref = str(binding.get("readinessReceiptRef") or "").strip()
    if readiness_ref != expected_ref:
        raise ValueError("test_live content binding readinessReceiptRef is not canonical")
    evidence_root = _stackctl.output_root().expanduser().resolve()
    readiness_path = (evidence_root / readiness_ref).resolve()
    try:
        readiness_path.relative_to(evidence_root)
    except ValueError as exc:
        raise ValueError("test_live content readiness escapes QWQ_OUTPUT_ROOT") from exc
    if readiness_path.is_symlink() or not readiness_path.is_file():
        raise ValueError("test_live content readiness receipt is missing")
    receipt_digest = "sha256:" + hashlib.sha256(readiness_path.read_bytes()).hexdigest()
    if receipt_digest != binding.get("readinessReceiptDigest"):
        raise ValueError("test_live content readiness receipt digest drift")
    readiness, canonical_path = _stackctl._load_data_release_readiness(
        environment=environment,
        release_id=release_id,
        verify_run_id=verify_run_id,
        manifest_digest=manifest_digest,
        readiness_phase=ReadinessPhase(readiness_phase),
    )
    if canonical_path.resolve() != readiness_path:
        raise ValueError("test_live content readiness canonical path drift")
    for field in (
        "releaseId",
        "verifyRunId",
        "manifestDigest",
        "readinessPhase",
        "activationEnvelope",
        "activationEnvelopeDigest",
        "appUatEnvelope",
        "appUatEnvelopeDigest",
    ):
        if binding.get(field) != readiness.get(field):
            raise ValueError(f"test_live content binding {field} drift")
    startup_identity = binding.get("startupIdentity")
    source_revision = (
        str(startup_identity.get("sourceRevision") or "")
        if isinstance(startup_identity, Mapping)
        else ""
    )
    return (
        {"baselineId": "", "sourceRevision": source_revision},
        readiness,
        readiness_path,
        str(binding.get("lifecycleExitRef") or "").strip(),
    )


def _app_content_uat_envelope(readiness: dict[str, Any]) -> dict[str, str]:
    import quwoquan_ops.cli.stackctl as _stackctl

    raw = readiness.get("appUatEnvelope")
    if not isinstance(raw, dict):
        raise ValueError("release readiness is missing canonical appUatEnvelope")
    required_fields = {
        key for key, _argument in _stackctl.APP_CONTENT_UAT_ENVELOPE_ARGUMENTS
    } | {"videoWorkId"}
    envelope = {key: str(raw.get(key) or "").strip() for key in required_fields}
    missing = sorted(key for key, value in envelope.items() if not value)
    if missing:
        raise ValueError(
            "release readiness appUatEnvelope is incomplete: "
            + ", ".join(missing)
        )
    if envelope["releaseId"] != str(readiness.get("releaseId") or "").strip():
        raise ValueError("release readiness appUatEnvelope releaseId mismatch")
    for key in ("releaseClass", "productLifecycleState"):
        if envelope[key] != str(readiness.get(key) or "").strip():
            raise ValueError(f"release readiness appUatEnvelope {key} mismatch")

    query_matches: dict[str, set[str]] = {}
    for query in readiness.get("feedQueries") or []:
        if not isinstance(query, dict):
            continue
        name = str(query.get("name") or "").strip()
        matches = query.get("matchedPostIds")
        if name and isinstance(matches, list):
            query_matches[name] = {
                str(item).strip() for item in matches if str(item).strip()
            }
    expected_queries = {
        "typed_article": envelope["articleWorkId"],
        "typed_image": envelope["imageWorkId"],
        "typed_video": envelope["videoWorkId"],
    }
    for query_name, work_id in expected_queries.items():
        if work_id not in query_matches.get(query_name, set()):
            raise ValueError(
                f"release readiness appUatEnvelope {query_name} is not exact-query bound"
            )
    if not query_matches.get("homepage_recommend"):
        raise ValueError("release readiness homepage recommendation is empty")
    readiness_phase = str(readiness.get("readinessPhase") or "").strip()
    if readiness_phase not in {
        ReadinessPhase.CONSUMER.value,
        ReadinessPhase.RESEARCH.value,
        ReadinessPhase.COMMERCIAL.value,
    }:
        raise ValueError("release readiness appUatEnvelope readinessPhase is invalid")
    if (
        readiness_phase
        in {ReadinessPhase.RESEARCH.value, ReadinessPhase.COMMERCIAL.value}
        and envelope["videoWorkId"]
        not in query_matches.get("premium_stream", set())
    ):
        raise ValueError(
            "release readiness appUatEnvelope video is not Premium-query bound"
        )
    return envelope


def _app_content_readback_summary(readiness: dict[str, Any]) -> dict[str, Any]:
    queries: list[dict[str, Any]] = []
    for query in readiness.get("feedQueries") or []:
        if not isinstance(query, dict):
            continue
        requests = []
        for request in query.get("requests") or []:
            if not isinstance(request, dict):
                continue
            requests.append(
                {
                    key: request.get(key)
                    for key in (
                        "requestId",
                        "traceId",
                        "status",
                        "durationMs",
                    )
                }
            )
        queries.append(
            {
                "name": str(query.get("name") or ""),
                "status": query.get("status"),
                "matchedPostIds": list(query.get("matchedPostIds") or []),
                "requests": requests,
            }
        )
    return {
        "counts": readiness.get("counts", {}),
        "postIds": list(readiness.get("postIds") or []),
        "creatorIds": list(readiness.get("creatorIds") or []),
        "feedQueries": queries,
    }


def _run_app_content_release_probe(
    *,
    target: str,
    readiness_path: Path,
    app_uat_plan: Mapping[str, Any],
    report_dir: Path,
) -> dict[str, Any]:
    """Verify the phase-scoped live content surface before device UAT."""
    import quwoquan_ops.cli.stackctl as _stackctl

    readiness = _stackctl._read_json_object(str(readiness_path))
    readiness_phase = str(readiness.get("readinessPhase") or "").strip()
    search_canaries_required = readiness_phase != ReadinessPhase.CONSUMER.value
    raw_search = app_uat_plan.get("searchCanaries")
    raw_pagination = app_uat_plan.get("videoPagination")
    raw_media = app_uat_plan.get("mediaChecks")
    if (
        (
            search_canaries_required
            and (
                not isinstance(raw_search, list)
                or len(raw_search) != 3
                or not all(isinstance(item, Mapping) for item in raw_search)
            )
        )
        or not isinstance(raw_pagination, Mapping)
        or raw_pagination.get("pageSize") != 20
        or not isinstance(raw_pagination.get("expectedWorkIds"), list)
        or not raw_pagination["expectedWorkIds"]
        or not isinstance(raw_media, Mapping)
        or raw_media.get("automatic") is not True
    ):
        raise ValueError("App content UAT plan is incomplete")
    video_work_ids = {
        str(item).strip()
        for item in raw_pagination["expectedWorkIds"]
        if str(item).strip()
    }
    if len(video_work_ids) != len(raw_pagination["expectedWorkIds"]):
        raise ValueError("App content UAT video page identities are invalid")
    search_canaries = (
        [dict(item) for item in raw_search]
        if search_canaries_required and isinstance(raw_search, list)
        else []
    )
    sample_resolution: dict[str, Any] = {}
    if isinstance(app_uat_plan.get("stratifiedSamples"), Mapping):
        sample_resolution = _stackctl.resolve_release_sample_requests(
            readiness_path=readiness_path,
            app_uat_plan=app_uat_plan,
            output_root=_stackctl.output_root(),
        )
    check, _output, findings = _stackctl._run_environment_integration_probe(
        _stackctl.load_environment_topology(),
        target,
        report_dir,
        require_non_empty_content_feed=True,
        release_post_expectations={"video_book_feed": video_work_ids},
        release_search_canaries=search_canaries,
        release_samples=list(sample_resolution.get("samples") or []),
        release_readiness_path=readiness_path,
        video_page_size=20,
        only_checks=(
            "video_book_feed",
            # App 视频书页真实消费 premium_stream 频道；typed_video 绿不代表
            # 视频书绿，设备 UAT 前必须同时证明 premium 池非空。
            "premium_feed",
            # feed items 非空不等于媒体可显示：设备 UAT 前逐 slice 字节读回。
            "feed_media_slices",
            *(("global_search",) if search_canaries_required else ()),
            "media_sample",
            *(("release_sample",) if sample_resolution else ()),
        ),
        probe_name="app-content-release-bound-search-and-video-page",
    )
    if not bool(check.get("ok")) or findings:
        raise ValueError(
            "; ".join(str(item) for item in findings)
            or "release-bound Search/video/media probe did not pass"
        )
    sample_execution: dict[str, Any] = {}
    if sample_resolution:
        sample_execution = _stackctl.validate_release_sample_probe(
            report=_stackctl._read_json_object(str(report_dir / "integration-probe.json")),
            resolved=sample_resolution,
            app_uat_plan_digest=_stackctl._canonical_document_checksum(dict(app_uat_plan)),
            readiness_receipt_digest=_stackctl._canonical_document_checksum(readiness),
        )
    return {
        "target": target,
        "suite": "release-bound-search-and-video-page",
        "exitCode": 0,
        "reportRef": str(check.get("reportPath") or ""),
        "readinessPhase": readiness_phase,
        "searchCanariesRequired": search_canaries_required,
        "searchCanaries": search_canaries,
        "videoPagination": dict(raw_pagination),
        "mediaChecks": dict(raw_media),
        "sampleExecution": sample_execution,
        "executedSampleCount": int(
            sample_execution.get("executedSampleCount") or 0
        ),
        "sampleExecutionDigest": (
            _stackctl._canonical_document_checksum(sample_execution)
            if sample_execution
            else ""
        ),
    }
