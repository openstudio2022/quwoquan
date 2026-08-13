"""stackctl deploy 发布输入与 SLO 读数域: release manifest 校验、
prevalidation manifest、rollout contract 与 Prometheus SLO 读取。

从 stackctl.py 逐字迁出（改写规则与 down_domain 相同）:
- manifest/attestation: `_validate_release_artifacts` / `_release_transport_tag` /
  `_deployable_release_manifest` / `_materialize_prevalidation_release_manifest` /
  `_prevalidation_release_manifest` / `_verify_release_registry_attestations`;
- rollout: `_prod_rollout_contract` / `_emit_prod_rollout_canary_traffic` /
  `_resolve_prod_rollout_stage` / `_prod_rollout_workloads`;
- SLO: `_prometheus_query_value` / `_read_prometheus_slo` / `_slo_settle_seconds` /
  `_read_recommendation_slo` / `_decision_from_slo_output`。

测试经 ``mock.patch.object(stackctl, ...)`` patch 本模块符号与协作符号，
因此函数体内一律经函数内延迟导入 `_stackctl` 属性访问（含本模块符号互调），
保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import concurrent
import concurrent.futures
import hashlib
import json
import re
import subprocess
import time
import urllib
import urllib.error
import urllib.parse
import urllib.request

from pathlib import Path
from typing import Any


def _validate_release_artifacts(
    manifest: dict[str, Any],
    *,
    artifact_root: Path,
) -> None:
    import quwoquan_ops.cli.stackctl as _stackctl

    if set(_stackctl.finalize_mainline_release_artifact.REQUIRED_RELEASE_EVIDENCE) != (
        _stackctl._REQUIRED_RELEASE_EVIDENCE
    ):
        raise RuntimeError("release evidence set differs from the canonical contract")
    try:
        _stackctl.finalize_mainline_release_artifact.validate_manifest_files(
            artifact_root,
            manifest,
        )
    except ValueError as error:
        raise RuntimeError(f"release evidence files are invalid: {error}") from error


def _release_transport_tag(manifest: dict[str, Any]) -> str:
    tags: set[str] = set()
    for service, descriptor in manifest["images"].items():
        repository = str(descriptor["repository"])
        transport_ref = str(descriptor["transportRef"])
        prefix = repository + ":"
        if not transport_ref.startswith(prefix):
            raise RuntimeError(
                f"release evidence image transport reference is invalid: {service}"
            )
        tags.add(transport_ref.removeprefix(prefix))
    if len(tags) != 1:
        raise RuntimeError("release evidence images must share one transport tag")
    return next(iter(tags))


def _deployable_release_manifest(
    path_value: str,
    *,
    candidate_digest: str,
) -> tuple[Path, str, dict[str, Any]]:
    import quwoquan_ops.cli.stackctl as _stackctl

    path = Path(path_value).expanduser().resolve()
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"release manifest unreadable: {error}") from error
    if not isinstance(manifest, dict):
        raise RuntimeError("release manifest must be an object")
    try:
        _stackctl.finalize_mainline_release_artifact.validate_manifest(
            manifest,
            allowed_statuses={"deployable"},
        )
    except ValueError as error:
        raise RuntimeError(f"release evidence manifest is not deployable: {error}") from error
    declared_digest = str(manifest["artifactDigest"])
    if candidate_digest != str(manifest["candidateId"]):
        raise RuntimeError("release candidate digest does not match reviewed evidence")
    source = manifest.get("source")
    source_sha = str(source.get("gitSha") or "") if isinstance(source, dict) else ""
    head = _stackctl.run(["git", "rev-parse", "HEAD"])
    if head.returncode != 0 or source_sha != head.stdout.strip():
        raise RuntimeError(
            "release manifest source SHA does not match checked-out deployment code"
        )
    governance_path = path.parent / "governance-receipt.json"
    try:
        governance = json.loads(governance_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"release governance receipt is missing or invalid: {error}") from error
    if (
        not isinstance(governance, dict)
        or governance.get("schema") != "prod-release-governance-receipt"
        or governance.get("repository") != (manifest.get("source") or {}).get("repository")
        or governance.get("gitSha") != source_sha
        or governance.get("artifactDigest") != declared_digest
        or not governance.get("approvers")
        or len(set(governance.get("distinctPrincipals") or [])) < 2
    ):
        raise RuntimeError("release governance receipt does not bind this reviewed artifact")
    _stackctl._validate_release_artifacts(manifest, artifact_root=path.parent)
    return path, declared_digest, manifest


def _materialize_prevalidation_release_manifest(path_value: str) -> Path:
    import quwoquan_ops.cli.stackctl as _stackctl

    if not path_value.startswith("oci://"):
        return Path(path_value).expanduser().resolve()
    image_ref = path_value.removeprefix("oci://").strip()
    match = re.fullmatch(
        r"ghcr\.io/[a-z0-9._/-]+/release-artifact@(sha256:([0-9a-f]{64}))",
        image_ref,
    )
    if match is None:
        raise RuntimeError(
            "prevalidation OCI release artifact must be a GHCR digest ref"
        )
    destination = _stackctl.deployment_target_path(
        "prod-hosted", "release-artifacts", match.group(2)
    )
    fetch = _stackctl.run(
        [
            "python3",
            "quwoquan_ops/cli/prod/fetch_mainline_release_artifact.py",
            "--ref",
            image_ref,
            "--output-dir",
            str(destination),
        ]
    )
    if fetch.returncode != 0:
        raise RuntimeError(
            "immutable OCI release artifact fetch failed: "
            + (fetch.stderr.strip() or fetch.stdout.strip())
        )
    return destination / "manifest.json"


def _prevalidation_release_manifest(
    path_value: str,
) -> tuple[Path, str, dict[str, Any], str, str]:
    """Validate a Service Pipeline artifact without entering release governance.

    Prevalidation deliberately does not require/read a governance receipt: it is
    non-promotable and cannot write a hosted release receipt.  It still requires
    the exact reviewed main source, a clean checkout, GHCR digest refs, SBOM/
    provenance references, and byte-identical config snapshots.
    """
    import quwoquan_ops.cli.stackctl as _stackctl

    path = _stackctl._materialize_prevalidation_release_manifest(path_value)
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"release manifest unreadable: {error}") from error
    if not isinstance(manifest, dict):
        raise RuntimeError("release manifest must be an object")
    try:
        _stackctl.finalize_mainline_release_artifact.validate_manifest(
            manifest,
            allowed_statuses={"deployable"},
        )
        _stackctl.finalize_mainline_release_artifact.validate_manifest_files(
            path.parent,
            manifest,
        )
    except ValueError as error:
        raise RuntimeError(
            f"prevalidation requires canonical deployable release evidence: {error}"
        ) from error
    declared_digest = str(manifest["artifactDigest"])
    source = manifest.get("source")
    source_sha = str(source.get("gitSha") or "") if isinstance(source, dict) else ""
    repository = str(source.get("repository") or "") if isinstance(source, dict) else ""
    workflow_run_id = (
        str(source.get("workflowRunId") or "") if isinstance(source, dict) else ""
    )
    if (
        re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", source_sha) is None
        or not repository
        or not workflow_run_id
    ):
        raise RuntimeError("release manifest source is not a Service Pipeline commit")
    image_transport_tag = _stackctl._release_transport_tag(manifest)
    candidate_digest = str(manifest["candidateId"])
    required_images = manifest["requiredEvidence"]["images"]
    images = manifest.get("images")
    if (
        not isinstance(required_images, list)
        or not required_images
        or not isinstance(images, dict)
        or set(required_images) != set(images)
    ):
        raise RuntimeError("release manifest image set is incomplete")
    access = _stackctl.load_json_yaml(
        _stackctl.ROOT / "quwoquan_ops/environments/prod/access-isolation.yaml"
    )
    prevalidation = access.get("prevalidation") if isinstance(access, dict) else None
    projected = prevalidation.get("planes") if isinstance(prevalidation, dict) else None
    required_prevalidation_images = {
        str(service)
        for plane in (projected or {}).values()
        if isinstance(plane, dict)
        for key in ("startupServices", "imageAndConfigOnlyServices")
        for service in (plane.get(key) or [])
    }
    if not required_prevalidation_images.issubset(set(required_images)):
        missing = sorted(required_prevalidation_images - set(required_images))
        raise RuntimeError(f"release manifest misses prevalidation images: {missing}")
    expected_prefix = f"ghcr.io/{repository.strip('/').lower()}/"
    for service in required_images:
        image = images.get(service)
        if not isinstance(image, dict):
            raise RuntimeError(f"release manifest image is invalid: {service}")
        digest = str(image.get("digest") or "")
        image_repository = str(image.get("repository") or "")
        ref = str(image.get("ref") or "")
        if (
            not image_repository.lower().startswith(expected_prefix)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None
            or ref != f"{image_repository}@{digest}"
            or ":latest" in ref
        ):
            raise RuntimeError(f"release image is not a GHCR digest ref: {service}")
        attestations = image.get("attestations")
        if not isinstance(attestations, dict) or not all(
            attestations.get(kind) == f"oci://{ref}#{kind}"
            for kind in ("spdxSbom", "slsaProvenance")
        ):
            raise RuntimeError(f"release manifest attestations are incomplete: {service}")
    head = _stackctl.run(["git", "rev-parse", "HEAD"])
    if head.returncode != 0 or head.stdout.strip() != source_sha:
        raise RuntimeError("release manifest source SHA does not match checked-out code")
    dirty = _stackctl.run(["git", "status", "--porcelain", "--untracked-files=normal"])
    if dirty.returncode != 0 or dirty.stdout.strip():
        raise RuntimeError("prod-hosted prevalidation refuses an uncommitted worktree")
    reviewed_main = _stackctl.run(["git", "merge-base", "--is-ancestor", source_sha, "origin/main"])
    if reviewed_main.returncode != 0:
        raise RuntimeError("release manifest source is not present on reviewed origin/main")
    return path, declared_digest, manifest, image_transport_tag, candidate_digest


def _verify_release_registry_attestations(
    manifest: dict[str, Any], *, deadline_epoch: int
) -> None:
    import quwoquan_ops.cli.stackctl as _stackctl

    images = manifest.get("images")
    if not isinstance(images, dict):
        raise RuntimeError("release manifest images are missing")
    source = manifest.get("source")
    repository = str(source.get("repository") or "") if isinstance(source, dict) else ""
    signer_workflow = f"{repository}/.github/workflows/service_pipeline.yml"
    verification_inputs: list[tuple[str, str]] = []
    for service, image in images.items():
        if not isinstance(image, dict):
            raise RuntimeError(f"release manifest image is invalid: {service}")
        verification_inputs.append((str(service), str(image.get("ref") or "")))

    def verify_one(service: str, ref: str) -> None:
        try:
            _stackctl.oci_supply_chain.verify_oci_supply_chain(
                ref,
                repository=repository,
                signer_workflow=signer_workflow,
                timeout_seconds=_stackctl._remaining_deadline_seconds(
                    deadline_epoch, "Prod registry signed-attestation verification"
                ),
            )
        except (
            OSError,
            ValueError,
            RuntimeError,
            subprocess.TimeoutExpired,
        ) as error:
            raise RuntimeError(
                f"OCI signed SBOM/provenance verification failed for {service}: {error}"
            ) from error

    failures: list[str] = []
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=min(8, max(1, len(verification_inputs))),
        thread_name_prefix="prod-oci-attestation",
    ) as executor:
        futures = {
            executor.submit(verify_one, service, ref): service
            for service, ref in verification_inputs
        }
        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()
            except RuntimeError as error:
                failures.append(str(error))
    if failures:
        raise RuntimeError("; ".join(sorted(failures)))


def _prod_rollout_contract(
    rollout_stage: str,
    *,
    expected_candidate_digest: str = "",
) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    policy_path = _stackctl.ROOT / "quwoquan_ops" / "environments" / "prod" / "rollout" / "routing_policy.yaml"
    try:
        policy_bytes = policy_path.read_bytes()
    except OSError as error:
        raise RuntimeError("production rollout policy is unavailable") from error
    payload = _stackctl.load_json_yaml(policy_path)
    policy = payload.get("policy") if isinstance(payload, dict) else None
    if not isinstance(policy, dict) or not policy.get("enabled"):
        raise RuntimeError("production rollout policy must be enabled")
    if rollout_stage not in {"canary", "5", "20", "50", "100"}:
        raise RuntimeError(f"unsupported production rollout stage: {rollout_stage}")
    if policy.get("subjectKind") != "device_actor":
        raise RuntimeError("production rollout subjectKind must be device_actor")
    for field in ("campaignId", "candidateDigest", "allocationKeyId"):
        if not str(policy.get(field) or "").strip():
            raise RuntimeError(f"production rollout policy requires {field}")
    if expected_candidate_digest and policy["candidateDigest"] != expected_candidate_digest:
        raise RuntimeError(
            "production rollout candidateDigest does not match the deployment candidate"
        )
    canary = policy.get("syntheticCanary")
    if not isinstance(canary, dict):
        raise RuntimeError("production rollout policy requires syntheticCanary")
    headers = canary.get("headers")
    requests = int(canary.get("requests") or 0)
    path = str(canary.get("path") or "").strip()
    if (
        not isinstance(headers, dict)
        or requests < 100
        or not path.startswith("/")
    ):
        raise RuntimeError("production rollout synthetic canary contract is incomplete")
    stages = policy.get("stages")
    stage_policy = stages.get(rollout_stage) if isinstance(stages, dict) else None
    if not isinstance(stage_policy, dict):
        raise RuntimeError(
            f"production rollout policy is missing stage {rollout_stage}"
        )
    expected_basis_points = {
        "canary": 0,
        "5": 500,
        "20": 2000,
        "50": 5000,
        "100": 10000,
    }[rollout_stage]
    if stage_policy.get("basisPoints") != expected_basis_points:
        raise RuntimeError(
            f"production rollout stage {rollout_stage} basisPoints is invalid"
        )
    return {
        **canary,
        "rolloutStage": rollout_stage,
        "expectedRoute": "stable" if rollout_stage == "100" else "candidate",
        "campaignId": policy["campaignId"],
        "candidateDigest": policy["candidateDigest"],
        "allocationKeyId": policy["allocationKeyId"],
        "basisPoints": expected_basis_points,
        "routingPolicyDigest": "sha256:" + hashlib.sha256(policy_bytes).hexdigest(),
        "platforms": stage_policy.get("platforms"),
        "appVersions": stage_policy.get("appVersions"),
        "regions": stage_policy.get("regions"),
        "carriers": stage_policy.get("carriers"),
    }


def _emit_prod_rollout_canary_traffic(
    canary: dict[str, Any], *, deadline_epoch: int
) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    topology = _stackctl.load_environment_topology()
    api_base = str(
        ((((topology or {}).get("targets") or {}).get("prod-hosted") or {}).get("publicBases") or {}).get("api")
        or ""
    ).rstrip("/")
    if not api_base.startswith("https://"):
        raise RuntimeError("prod synthetic canary requires HTTPS api public base")
    path = str(canary["path"])
    requests = int(canary["requests"])
    interval_ms = int(canary.get("intervalMs") or 0)
    headers = {str(key): str(value) for key, value in canary["headers"].items()}
    started = time.monotonic()
    for index in range(requests):
        request_timeout = min(
            5.0,
            _stackctl._remaining_deadline_seconds(deadline_epoch, "Prod canary traffic"),
        )
        request = urllib.request.Request(
            f"{api_base}{path}",
            headers={**headers, "User-Agent": "quwoquan-release-canary/1"},
        )
        try:
            with urllib.request.urlopen(
                request, timeout=max(0.05, request_timeout)
            ) as response:
                if response.status < 200 or response.status >= 300:
                    raise RuntimeError(
                        f"synthetic canary request {index + 1} returned {response.status}"
                    )
        except OSError as error:
            raise RuntimeError(
                f"synthetic canary request {index + 1}/{requests} failed: {error}"
            ) from error
        if interval_ms > 0 and index + 1 < requests:
            sleep_seconds = interval_ms / 1000
            remaining = _stackctl._remaining_deadline_seconds(
                deadline_epoch, "Prod canary traffic"
            )
            if sleep_seconds >= remaining:
                raise RuntimeError("Prod canary interval would cross promotion cutoff")
            time.sleep(sleep_seconds)
    return {
        "source": "prod-public-api",
        "path": path,
        "requests": requests,
        "headers": sorted(headers),
        "durationMs": int((time.monotonic() - started) * 1000),
    }


def _prometheus_query_value(
    base_url: str, expression: str, *, deadline_epoch: int
) -> float:
    import quwoquan_ops.cli.stackctl as _stackctl

    request_url = f"{base_url.rstrip('/')}/api/v1/query?{urllib.parse.urlencode({'query': expression})}"
    request = urllib.request.Request(request_url, headers={"Accept": "application/json"})
    try:
        timeout = min(
            5.0,
            _stackctl._remaining_deadline_seconds(deadline_epoch, "Prometheus SLO readback"),
        )
        with urllib.request.urlopen(request, timeout=max(0.05, timeout)) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Prometheus SLO readback request failed: {error}") from error
    if payload.get("status") != "success":
        raise RuntimeError(f"Prometheus SLO readback returned non-success: {payload.get('error', 'unknown error')}")
    results = ((payload.get("data") or {}).get("result") or [])
    if len(results) != 1:
        raise RuntimeError(f"Prometheus SLO readback expected one sample, got {len(results)}")
    value = (results[0].get("value") or [])
    if len(value) != 2:
        raise RuntimeError("Prometheus SLO readback sample is malformed")
    try:
        return float(value[1])
    except (TypeError, ValueError) as error:
        raise RuntimeError("Prometheus SLO readback value is not numeric") from error


def _read_prometheus_slo(
    base_url: str,
    service: str,
    *,
    deadline_epoch: int,
    window_override: str = "",
) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    policy_path = _stackctl.ROOT / "quwoquan_ops/policies/config-release/slo_thresholds.yaml"
    policy = _stackctl.load_json_yaml(policy_path)
    if not isinstance(policy, dict) or not isinstance(policy.get("readback"), dict):
        raise RuntimeError(f"invalid SLO readback policy: {policy_path}")
    readback_policy = policy["readback"]
    window = str(window_override or readback_policy.get("window") or "").strip()
    minimum_samples = int(readback_policy.get("minimum_samples") or 0)
    if not window or minimum_samples <= 0:
        raise RuntimeError(f"SLO readback policy requires window/minimum_samples: {policy_path}")
    labels: list[str] = []
    if service.strip():
        labels.append(f'service="{service.strip()}"')
    service_label = "{" + ",".join(labels) + "}"
    error_labels = [*labels, 'status=~"5.."']
    error_selector = "{" + ",".join(error_labels) + "}"
    queries = {
        "errorRate": (
            f"sum(rate(http_server_requests_total{error_selector}[{window}]))"
            f" / (sum(rate(http_server_requests_total{service_label}[{window}])) + 0.001)"
        ),
        "p95Ms": (
            f"histogram_quantile(0.95, sum(rate(http_server_duration_seconds_bucket"
            f"{service_label}[{window}])) by (le)) * 1000"
        ),
        "redisErrorRate": (
            f'sum(rate(redis_operations_total{{status="error"}}[{window}]))'
            f" / (sum(rate(redis_operations_total[{window}])) + 0.001)"
        ),
        "sampleCount": f"sum(increase(http_server_requests_total{service_label}[{window}]))",
    }
    values = {
        name: _stackctl._prometheus_query_value(
            base_url, expression, deadline_epoch=deadline_epoch
        )
        for name, expression in queries.items()
    }
    if values["sampleCount"] < minimum_samples:
        raise _stackctl._SloSamplesInsufficient(
            f"Prometheus SLO readback has insufficient samples: "
            f"{values['sampleCount']} < {minimum_samples}"
        )
    result: dict[str, Any] = {
        "source": "prometheus",
        "baseUrl": base_url.rstrip("/"),
        "queriedAt": _stackctl.utc_now(),
        "window": window,
        "minimumSamples": minimum_samples,
        "queries": queries,
        "values": values,
    }
    recommendation = _stackctl._read_recommendation_slo(
        base_url,
        service,
        window,
        readback_policy.get("recommendation"),
        deadline_epoch=deadline_epoch,
    )
    if recommendation is not None:
        result["recommendation"] = recommendation
    return result


def _slo_settle_seconds(stage: str) -> int:
    import quwoquan_ops.cli.stackctl as _stackctl

    policy_path = _stackctl.ROOT / "quwoquan_ops/policies/config-release/slo_thresholds.yaml"
    policy = _stackctl.load_json_yaml(policy_path)
    readback = policy.get("readback") if isinstance(policy, dict) else None
    settle = readback.get("settle_seconds") if isinstance(readback, dict) else None
    if not isinstance(settle, dict):
        raise RuntimeError(f"SLO readback policy requires settle_seconds: {policy_path}")
    seconds = int(settle.get(stage) or 0)
    if seconds < 0:
        raise RuntimeError(f"SLO settle seconds cannot be negative for {stage}")
    return seconds


def _read_recommendation_slo(
    base_url: str,
    service: str,
    window: str,
    rec_policy: Any,
    *,
    deadline_epoch: int,
) -> dict[str, Any] | None:
    """N2-5：prod gray readback 纳入推荐业务指标（空 feed 率 / 负反馈率 / CTR）。

    仅对策略声明的推荐服务（content-service）生效；空 feed 率与负反馈率超
    critical 抛错阻断放量，CTR 在 impression 样本不足时诚实跳过（只观察不拦截）。
    """
    import quwoquan_ops.cli.stackctl as _stackctl

    if not isinstance(rec_policy, dict):
        return None
    if service.strip() != str(rec_policy.get("service") or "").strip():
        return None
    # 指标名与 runtime/recommendation/observability.go 的真实 emitter 对齐
    # （recommendation_alert_metric_existence 契约同源）；杜绝死查询。
    queries = {
        "emptyFeedRate": (
            f"sum(increase(rec_pipeline_empty_results_total[{window}]))"
            f" / (sum(increase(rec_pipeline_requests_total[{window}])) + 0.001)"
        ),
        "negativeFeedbackRate": (
            f"sum(increase(recommendation_feed_negative_feedback_total[{window}]))"
            f" / (sum(increase(recommendation_feed_impressed_total[{window}])) + 0.001)"
        ),
        "impressionCount": f"sum(increase(recommendation_feed_impressed_total[{window}]))",
        "ctr": (
            f'sum(increase(recommendation_feed_engagement_total{{action="click"}}[{window}]))'
            f" / (sum(increase(recommendation_feed_impressed_total[{window}])) + 0.001)"
        ),
    }
    values = {
        name: _stackctl._prometheus_query_value(
            base_url, expression, deadline_epoch=deadline_epoch
        )
        for name, expression in queries.items()
    }
    breaches: list[str] = []
    warnings: list[str] = []
    for metric, value_key in (
        ("empty_feed_rate", "emptyFeedRate"),
        ("negative_feedback_rate", "negativeFeedbackRate"),
    ):
        thresholds = rec_policy.get(metric)
        if not isinstance(thresholds, dict):
            continue
        critical = float(thresholds.get("critical") or 0)
        warn = float(thresholds.get("warn") or 0)
        value = values[value_key]
        if critical > 0 and value >= critical:
            breaches.append(f"{metric}={value:.4f} >= critical {critical}")
        elif warn > 0 and value >= warn:
            warnings.append(f"{metric}={value:.4f} >= warn {warn}")
    min_impressions = int(rec_policy.get("min_impressions") or 0)
    ctr_evaluated = values["impressionCount"] >= min_impressions > 0
    if ctr_evaluated:
        ctr_floor = float(rec_policy.get("ctr_floor_warn") or 0)
        if ctr_floor > 0 and values["ctr"] < ctr_floor:
            warnings.append(f"ctr={values['ctr']:.4f} < floor {ctr_floor}")
    if breaches:
        raise RuntimeError(
            "recommendation SLO readback breached critical thresholds: "
            + "; ".join(breaches)
        )
    return {
        "queries": queries,
        "values": values,
        "ctrEvaluated": ctr_evaluated,
        "warnings": warnings,
    }


def _decision_from_slo_output(output: str, rollout_stage: str) -> tuple[str, str]:
    if "decision=pause reason=insufficient_samples" in output:
        return "pause", "SLO sample evidence is insufficient; promotion remains paused"
    if "decision=pause" in output:
        if rollout_stage == "100":
            return "rollback", "100 rollout cannot remain paused on warning SLO"
        return "pause", "slo gate decision=pause"
    if "decision=rollback" in output:
        return "rollback", "slo gate decision=rollback"
    return "continue", ""


def _resolve_prod_rollout_stage(step: str, requested_stage: str = "") -> str:
    normalized_step = str(step).strip()
    try:
        percentage = int(normalized_step)
    except ValueError as error:
        raise ValueError(f"step 必须是 1..100 的整数，实际 {step!r}") from error
    step_to_stage = {0: "canary", 5: "5", 20: "20", 50: "50", 100: "100"}
    if percentage not in step_to_stage:
        raise ValueError("step 只允许 0/5/20/50/100")
    explicit_stage = str(requested_stage).strip()
    if explicit_stage:
        if explicit_stage != step_to_stage[percentage]:
            raise ValueError(
                f"stage={explicit_stage} 与 step={percentage} 不匹配"
            )
        return explicit_stage
    return step_to_stage[percentage]


def _prod_rollout_workloads() -> list[dict[str, Any]]:
    """Derive prod rollout workloads from service and external environment entries."""
    import quwoquan_ops.cli.stackctl as _stackctl

    try:
        topology = _stackctl.load_environment_topology()
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    prod = ((topology or {}).get("environments") or {}).get("prod") or {}
    for workload in prod.get("workloads") or []:
        deployment_ref = str(workload.get("deploymentRef") or "")
        out.append(
            {
                "name": workload.get("id"),
                "plane": workload.get("plane"),
                "deploymentRef": deployment_ref,
                "rolloutRef": deployment_ref,
            }
        )
    return out
