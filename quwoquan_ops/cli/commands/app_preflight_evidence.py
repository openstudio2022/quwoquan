"""stackctl app 预检域 candidate/test-live 内容证据解析与 release readback 探针。

从 commands/app_preflight.py 逐字迁出(该模块保留三命令主干与 argparse 表面,
本家族随内容证据职责聚合到本模块):

- `_resolve_active_app_content_evidence`:active candidate 到 Research /
  Commercial 精确证据的解析;
- `_resolve_test_live_app_content_evidence`:validated mutable binding 的
  test-live 证据解析(不询问 active candidate 状态);
- `_app_content_uat_sample_plan`:immutable ReleaseUatSamplePlan 与 readiness
  readback 的 fail-closed 消费;
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
import json
from pathlib import Path
from typing import Any, Mapping

from quwoquan_ops.cli.lib.content_release_readiness import ReadinessPhase


def _read_exact_json_object(path: Path, *, label: str) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} is missing or unsafe")
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not readable JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value, raw


def _payload_tree_digest(payload_root: Path) -> str:
    """Return Data's canonical sha256-path-blob-merkle for exact payload bytes."""

    entries: list[bytes] = []
    for path in sorted(payload_root.rglob("*")):
        if path.is_symlink():
            raise ValueError("active candidate Data release payload contains a symlink")
        if not path.is_file():
            continue
        relative = path.relative_to(payload_root).as_posix()
        raw = path.read_bytes()
        blob_digest = "sha256:" + hashlib.sha256(raw).hexdigest()
        entries.append(
            hashlib.sha256(
                b"blob\0"
                + relative.encode("utf-8")
                + b"\0"
                + blob_digest.encode("ascii")
                + b"\0"
                + str(len(raw)).encode("ascii")
            ).digest()
        )
    if not entries:
        return "sha256:" + hashlib.sha256(b"").hexdigest()
    level = entries
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [
            hashlib.sha256(b"node\0" + level[index] + level[index + 1]).digest()
            for index in range(0, len(level), 2)
        ]
    return "sha256:" + level[0].hex()


def _load_active_release_uat_contract(
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    """Load the exact ReleaseUatSamplePlan owned by one candidate release."""
    import quwoquan_ops.cli.stackctl as _stackctl
    from quwoquan_ops.cli.lib.app_content_uat_plan import (
        load_release_uat_sample_plan,
    )

    release_id = str(candidate.get("releaseId") or "").strip()
    manifest_digest = str(candidate.get("releaseDigest") or "").strip()
    attestation_ref = str(candidate.get("attestationRef") or "").strip()
    attestation_digest = str(candidate.get("attestationDigest") or "").strip()
    if (
        not release_id
        or _stackctl._DATA_READINESS_DIGEST_RE.fullmatch(manifest_digest) is None
        or not attestation_ref
        or _stackctl._DATA_READINESS_DIGEST_RE.fullmatch(attestation_digest) is None
    ):
        raise ValueError("active candidate Data release identity is incomplete")

    attestation_source = Path(attestation_ref).expanduser()
    if attestation_source.is_symlink():
        raise ValueError("active candidate Data release attestation is unsafe")
    attestation_path = attestation_source.resolve()
    if (
        attestation_path.name != "release.json"
        or attestation_path.parent.name != "attestations"
    ):
        raise ValueError("active candidate Data release attestation path is not canonical")
    release_root = attestation_path.parents[1]
    if attestation_path != release_root / "attestations/release.json":
        raise ValueError("active candidate Data release attestation path drifted")
    attestation, attestation_raw = _read_exact_json_object(
        attestation_path,
        label="active candidate Data release attestation",
    )
    actual_attestation_digest = "sha256:" + hashlib.sha256(attestation_raw).hexdigest()
    if actual_attestation_digest != attestation_digest:
        raise ValueError("active candidate Data release attestation digest drifted")
    if (
        attestation.get("schema") != "quwoquan_data.release_attestation"
        or attestation.get("releaseId") != release_id
        or attestation.get("payloadSha256") != manifest_digest
    ):
        raise ValueError("active candidate Data release attestation identity drifted")

    header_path = release_root / "payload/release.json"
    release_header, release_header_raw = _read_exact_json_object(
        header_path,
        label="active candidate Data release header",
    )
    if (
        release_header.get("releaseId") != release_id
        or release_header.get("releaseClass") != attestation.get("releaseClass")
        or release_header.get("productLifecycleState")
        != attestation.get("productLifecycleState")
        or (
            "canonicalMerkle" in release_header
            and release_header.get("canonicalMerkle")
            != attestation.get("canonicalMerkle")
        )
    ):
        raise ValueError("active candidate Data release header identity drifted")
    if _payload_tree_digest(header_path.parent) != manifest_digest:
        raise ValueError("active candidate Data release payload digest drifted")
    sample_plan, sample_plan_ref, sample_plan_digest = load_release_uat_sample_plan(
        release_root=header_path.parent,
        release_header=release_header,
    )
    return {
        "releaseRoot": str(release_root),
        "releasePayloadSha256": manifest_digest,
        "releaseHeader": release_header,
        "releaseHeaderRef": str(header_path),
        "releaseHeaderDigest": "sha256:"
        + hashlib.sha256(release_header_raw).hexdigest(),
        "releaseUatSamplePlan": sample_plan,
        "releaseUatSamplePlanRef": sample_plan_ref,
        "releaseUatSamplePlanDigest": sample_plan_digest,
    }


def _release_readback_path(readiness: Mapping[str, Any], field: str) -> Path:
    import quwoquan_ops.cli.stackctl as _stackctl

    ref = str(readiness.get(field) or "").strip()
    if not ref:
        raise ValueError(f"release readiness {field} is missing")
    evidence_root = _stackctl.output_root().expanduser().resolve()
    candidate = Path(ref).expanduser()
    path = candidate.resolve() if candidate.is_absolute() else (evidence_root / candidate).resolve()
    try:
        path.relative_to(evidence_root)
    except ValueError as exc:
        raise ValueError(f"release readiness {field} escapes QWQ_OUTPUT_ROOT") from exc
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"release readiness {field} is missing or unsafe")
    return path


def _app_content_uat_sample_plan(
    *,
    release_contract: Mapping[str, Any],
    readiness: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the only Ops UAT plan from exact immutable Data bytes."""

    import quwoquan_ops.cli.stackctl as _stackctl

    header = release_contract.get("releaseHeader")
    sample_plan = release_contract.get("releaseUatSamplePlan")
    if not isinstance(header, Mapping) or not isinstance(sample_plan, Mapping):
        raise ValueError("active release UAT contract is incomplete")
    canonical_readiness = {
        key: value
        for key, value in readiness.items()
        if key not in {"appUatEnvelope", "appUatEnvelopeDigest"}
    }
    return _stackctl.build_app_content_uat_plan(
        canonical_readiness,
        release_header=header,
        release_uat_sample_plan=sample_plan,
        release_uat_sample_plan_digest=str(
            release_contract.get("releaseUatSamplePlanDigest") or ""
        ),
        release_payload_sha256=str(
            release_contract.get("releasePayloadSha256") or ""
        ),
    )


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
    if attestation_path.is_symlink():
        raise ValueError("active candidate Data release attestation is unsafe")
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
                or len(raw_search) != 4
                or not all(isinstance(item, Mapping) for item in raw_search)
            )
        )
        or not isinstance(raw_pagination, Mapping)
        or raw_pagination.get("pageSize") != 20
        or not isinstance(raw_pagination.get("expectedWorkIds"), list)
        or not raw_pagination["expectedWorkIds"]
        or not isinstance(raw_media, Mapping)
        or raw_media.get("automatic") is not True
        or (
            readiness_phase == ReadinessPhase.RESEARCH.value
            and (
                not isinstance(raw_media.get("homepageRecommendation"), Mapping)
                or not isinstance(raw_media.get("typedVideo"), Mapping)
                or not isinstance(raw_media.get("premiumVideo"), Mapping)
            )
        )
    ):
        raise ValueError("App content UAT plan is incomplete")
    video_work_ids = {
        str(item).strip()
        for item in raw_pagination["expectedWorkIds"]
        if str(item).strip()
    }
    if len(video_work_ids) != len(raw_pagination["expectedWorkIds"]):
        raise ValueError("App content UAT video page identities are invalid")
    sample_resolution = _stackctl.resolve_release_sample_requests(
        readiness_path=readiness_path,
        app_uat_plan=app_uat_plan,
        output_root=_stackctl.output_root(),
    )
    runtime_samples = {
        str(item.get("carrier") or ""): item
        for item in sample_resolution.get("samples") or []
        if isinstance(item, Mapping)
    }
    def _consumer_search_query(item: Mapping[str, Any]) -> str:
        kind = str(item.get("kind") or "")
        sample = runtime_samples.get(kind)
        if not isinstance(sample, Mapping):
            return str(item.get("query") or "").strip()
        object_ref = str(sample.get("objectRef") or "").strip("/")
        segments = [segment for segment in object_ref.split("/") if segment]
        if kind == "homepage":
            return segments[-1] if segments else str(item.get("query") or "").strip()
        return (
            segments[-2]
            if len(segments) >= 2
            else str(item.get("query") or "").strip()
        )

    search_canaries = (
        [
            {
                **dict(item),
                # Data owns immutable sample identities. Search consumes a
                # human-facing title derived from the immutable objectRef and
                # asserts the exact imported route identity separately.
                "query": _consumer_search_query(item),
                "expectedObjectId": str(
                    runtime_samples.get(str(item.get("kind") or ""), {}).get(
                        "readObjectId"
                    )
                    or item.get("expectedObjectId")
                    or ""
                ),
            }
            for item in raw_search
        ]
        if search_canaries_required and isinstance(raw_search, list)
        else []
    )
    runtime_video_ids = {
        str(item.get("readObjectId") or "")
        for item in sample_resolution.get("samples") or []
        if isinstance(item, Mapping)
        and item.get("carrier") == "video"
        and str(item.get("readObjectId") or "")
    }
    def _expected_ids(binding: object, *, label: str) -> set[str]:
        if not isinstance(binding, Mapping):
            raise ValueError(f"App content UAT {label} binding is missing")
        raw_ids = binding.get("expectedPostIds")
        if not isinstance(raw_ids, list):
            raise ValueError(f"App content UAT {label} expected IDs are missing")
        values = {str(value).strip() for value in raw_ids if str(value).strip()}
        if not values or len(values) != len(raw_ids):
            raise ValueError(f"App content UAT {label} expected IDs are invalid")
        return values

    def _readiness_feed_ids(name: str, *, label: str) -> set[str]:
        matches = [
            row
            for row in readiness.get("feedQueries") or []
            if isinstance(row, Mapping) and row.get("name") == name
        ]
        if len(matches) != 1:
            raise ValueError(f"App content UAT {label} readiness binding is missing")
        raw_ids = matches[0].get("matchedPostIds")
        if not isinstance(raw_ids, list):
            raise ValueError(f"App content UAT {label} expected IDs are missing")
        values = {str(value).strip() for value in raw_ids if str(value).strip()}
        if not values or len(values) != len(raw_ids):
            raise ValueError(f"App content UAT {label} expected IDs are invalid")
        return values

    strict_feed_bindings = readiness_phase == ReadinessPhase.RESEARCH.value
    discovery_ids = (
        _readiness_feed_ids("discovery_work", label="discovery feed")
        if strict_feed_bindings
        else set()
    )
    homepage_recommend_ids = (
        _expected_ids(
            raw_media.get("homepageRecommendation"),
            label="homepage recommendation",
        )
        if strict_feed_bindings
        else set()
    )
    typed_video_ids = (
        _expected_ids(raw_media.get("typedVideo"), label="typed video")
        if strict_feed_bindings
        else runtime_video_ids
    )
    premium_video_ids = (
        _expected_ids(raw_media.get("premiumVideo"), label="premium video")
        if strict_feed_bindings
        else runtime_video_ids
    )
    if not premium_video_ids.intersection(typed_video_ids):
        raise ValueError(
            "App content UAT premium video IDs do not intersect typed video IDs"
        )
    expected_video_count = sum(
        1
        for item in app_uat_plan.get("orderedSamples") or []
        if isinstance(item, Mapping) and item.get("carrier") == "video"
    )
    if not runtime_video_ids or len(runtime_video_ids) != expected_video_count:
        raise ValueError("App content UAT runtime video identities are invalid")
    sample_resolution = {
        **sample_resolution,
        "samples": list(sample_resolution.get("samples") or []),
    }
    research = readiness_phase == ReadinessPhase.RESEARCH.value
    research_consumer_token = ""
    research_consumer_attestation = ""
    if research:
        # research 相位匿名内容面已按 DEC-032 收敛为 no_active_release 空页，
        # release-bound 非空读回必须以 research consumer 凭证消费（凭证只在
        # 进程内存传递）。私有媒体没有匿名可采样的公开 slice，media_sample
        # 与 feed_media_slices 的公开 URL 读回不适用：媒体可显示证据由
        # isolation probe signedMedia 段与 App 端短签消费 CaseResult 承载。
        from quwoquan_ops.cli.lib.research_consumer_credential import (
            issue_research_consumer_credential,
        )

        environment = target.removesuffix("-local")
        credential = issue_research_consumer_credential(
            environment=environment,
            release_id=str(readiness.get("releaseId") or ""),
            verify_run_id=str(readiness.get("verifyRunId") or ""),
        )
        research_consumer_token = str(credential.get("bearerToken") or "")
        research_consumer_attestation = str(
            credential.get("attestationToken") or ""
        )
        if not research_consumer_token or not research_consumer_attestation:
            raise ValueError(
                "research consumer credential issuance returned an incomplete "
                "Bearer/attestation chain"
            )
    check, _output, findings = _stackctl._run_environment_integration_probe(
        _stackctl.load_environment_topology(),
        target,
        report_dir,
        require_non_empty_content_feed=True,
        research_consumer_token=research_consumer_token,
        research_consumer_attestation=research_consumer_attestation,
        release_post_expectations={
            **(
                {
                    "content_feed": discovery_ids,
                    "homepage_recommend": homepage_recommend_ids,
                }
                if strict_feed_bindings
                else {}
            ),
            "video_book_feed": typed_video_ids,
            "premium_feed": premium_video_ids,
        },
        release_search_canaries=search_canaries,
        release_samples=[
            {
                key: value
                for key, value in item.items()
                if key not in {"objectRef", "objectDigest"}
            }
            for item in sample_resolution.get("samples") or []
            if isinstance(item, Mapping)
        ],
        release_creator_profiles=[
            dict(item)
            for item in sample_resolution.get("creatorProfiles") or []
            if isinstance(item, Mapping)
        ],
        release_signed_media=[
            dict(item)
            for item in sample_resolution.get("strictMediaChecks") or []
            if isinstance(item, Mapping)
        ],
        release_readiness_path=readiness_path,
        video_page_size=20,
        only_checks=(
            *(
                ("content_feed", "homepage_recommend")
                if strict_feed_bindings
                else ()
            ),
            "video_book_feed",
            # App 视频书页真实消费 premium_stream 频道；typed_video 绿不代表
            # 视频书绿，设备 UAT 前必须同时证明 premium 池非空。
            "premium_feed",
            # feed items 非空不等于媒体可显示：设备 UAT 前逐 slice 字节读回
            # （research 私有交付无公开 slice，由短签消费证据承载）。
            *(("feed_media_slices",) if not research else ()),
            *(("global_search",) if search_canaries_required else ()),
            *(("media_sample",) if not research else ()),
            *(
                ("release_creator_profile", "release_signed_media")
                if research
                else ()
            ),
            *(
                ("release_sample", "author_posts_contract")
                if research and sample_resolution
                else (("release_sample",) if sample_resolution else ())
            ),
        ),
        probe_name="app-content-release-bound-search-and-video-page",
    )
    if not bool(check.get("ok")) or findings:
        raise ValueError(
            "; ".join(str(item) for item in findings)
            or "release-bound Search/video/media probe did not pass"
        )
    strict_execution: dict[str, Any] = {}
    if research and sample_resolution:
        strict_execution = _stackctl.validate_release_strict_probe(
            report=_stackctl._read_json_object(str(report_dir / "integration-probe.json")),
            resolved=sample_resolution,
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
        "strictExecution": strict_execution,
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
