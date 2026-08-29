"""Package-bound Product Ops experiment policy activation for local targets.

The activation is a real authenticated public command.  It never seeds a
database, writes a service-private config, or persists the short-lived bearer.
"""

from __future__ import annotations

import hashlib
import json
import re
import ssl
import time
from typing import Any
from urllib import error, request

from .deployment_candidate_manifest import load_candidate_manifest
from .local_environment_auth import mint_local_product_ops_operator_token
from .output_paths import active_deployment_candidate
from .port_manifest import load_port_manifest, profile_ports
from .public_domain_tls import root_certificate_path
from .redis_stream_probe import RedisStreamProbeError, stream_field_values


COLLECTION_PATH = "/control-plane/product/experiments"
_ADMISSION_NOT_READY_CODE = "GATEWAY.MIDDLEWARE.upstream_unavailable"
_ADMISSION_NOT_READY_REQUIRED_FIELDS = frozenset(
    {
        "code",
        "origin",
        "nature",
        "userMessage",
        "debugMessage",
        "module",
        "kind",
        "reason",
        "location",
        "context",
        "recovery",
    }
)
_SAFE_TYPED_FAILURE_FIELDS = (
    "code",
    "origin",
    "nature",
    "module",
    "kind",
    "reason",
)
# 真相源：product-ops contracts/product_ops/experiment/storage.yaml 与
# experiment/infrastructure/messaging/publisher.go 的
# ExperimentPolicyActivatedStream。该流带 7 天 retention（XTRIM MINID +
# key EXPIRE），authoritative 策略存储（Postgres）则永续；reused 激活不
# 发布新事件，因此长驻卷会出现「策略在、事实流空」，必须显式验证可见性。
ACTIVATION_FACT_STREAM = "events.ops.experiment_policy_activated"
SEARCH_POLICY_ID = "search_ranking"
RECOMMENDATION_POLICY_ID = "rec_model_vs_rule"
SPEC_REFS = (
    "specs/feature-tree/product-ops-growth/experiment-bucketing-and-rollout/spec.md#sit-001",
    "specs/feature-tree/product-ops-growth/experiment-bucketing-and-rollout/bucketing-strategy-engine/spec.md#gwt-001",
)
_NONPROD_TARGETS = {
    "alpha": "alpha-local",
    "beta": "beta-local",
    "gamma": "gamma-local",
}
_POLICY_RECIPES: tuple[dict[str, Any], ...] = (
    {
        "id": SEARCH_POLICY_ID,
        "key": SEARCH_POLICY_ID,
        "status": "running",
        "variants": [
            {"key": "control", "allocationBasisPoints": 5000},
            {"key": "term_heat", "allocationBasisPoints": 5000},
        ],
        "audienceRule": {"kind": "all"},
    },
    {
        "id": RECOMMENDATION_POLICY_ID,
        "key": RECOMMENDATION_POLICY_ID,
        "status": "running",
        "variants": [
            {"key": "rule", "allocationBasisPoints": 5000},
            {"key": "model", "allocationBasisPoints": 5000},
        ],
        "audienceRule": {"kind": "all"},
    },
)


def _test_live_policy_recipes() -> tuple[dict[str, Any], ...]:
    """Project canonical policies for a non-promotable runtime without a model release.

    Test-live still activates the policy through Product Ops.  It does not let
    Recommendation invent a rule fallback when the canonical model registry is
    empty.  The model bucket remains authored with zero allocation so the wire
    shape stays identical and a later, explicit rollout can enable it only
    after a real model release exists.
    """

    return tuple(
        (
            {
                **recipe,
                "variants": [
                    {"key": "rule", "allocationBasisPoints": 10_000},
                    {"key": "model", "allocationBasisPoints": 0},
                ],
            }
            if recipe["id"] == RECOMMENDATION_POLICY_ID
            else recipe
        )
        for recipe in _POLICY_RECIPES
    )


class ExperimentPolicyActivationError(RuntimeError):
    """Redacted local policy activation failure."""


class ExperimentPolicyTransportError(ExperimentPolicyActivationError):
    """Connection-level failure before any HTTP status was produced.

    这一类失败允许在幂等 command 上重试：目标进程尚未监听
    （bootstrap 与 product-ops 启动竞态）、连接被拒绝或被重置。除
    servicekit 的完整 typed admission-not-ready envelope 外，凡拿到
    HTTP 状态码的业务失败（4xx/5xx、非 JSON 响应）都必须 fail-fast。
    """


def activate_test_live_experiment_policies(
    *,
    environment: str,
    target: str,
    product_ops_published_port: int,
    attempt_id: str,
    configuration_digest: str,
    timeout_seconds: float = 45.0,
) -> dict[str, Any]:
    """Activate the canonical policies for one mutable non-production runtime.

    The loopback endpoint is the Product Ops service's authenticated public
    HTTP adapter.  Binding it to the target's authored published port keeps the
    bootstrap independent from API Edge/Recommendation readiness without
    bypassing the Product Ops command, aggregate, transaction or outbox.
    """

    _require_nonprod_target(environment, target)
    expected_attempt_prefix = f"{environment}-test-live-"
    if re.fullmatch(
        re.escape(expected_attempt_prefix) + r"[0-9a-f]{32}",
        attempt_id,
    ) is None:
        raise ExperimentPolicyActivationError(
            "test_live experiment policy activation attempt identity is invalid"
        )
    if re.fullmatch(r"sha256:[0-9a-f]{64}", configuration_digest) is None:
        raise ExperimentPolicyActivationError(
            "test_live experiment policy activation configuration digest is invalid"
        )
    if isinstance(product_ops_published_port, bool) or not isinstance(
        product_ops_published_port, int
    ):
        raise ExperimentPolicyActivationError(
            "test_live Product Ops published port is invalid"
        )
    try:
        expected_port = profile_ports(
            load_port_manifest(),
            target,
        )["product-ops-service"]
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise ExperimentPolicyActivationError(
            "test_live Product Ops published port cannot be derived"
        ) from exc
    if product_ops_published_port != expected_port:
        raise ExperimentPolicyActivationError(
            "test_live Product Ops published port does not match the target"
        )

    token = mint_local_product_ops_operator_token(environment, target)
    deadline = time.monotonic() + max(1.0, timeout_seconds)
    runtime_identity_digest = "sha256:" + hashlib.sha256(
        (attempt_id + "\0" + configuration_digest).encode("utf-8")
    ).hexdigest()
    activated = _activate_policy_recipes(
        recipes=_test_live_policy_recipes(),
        allow_rollout=True,
        target=target,
        binding_id=runtime_identity_digest,
        idempotency_prefix="test-live-runtime-policy",
        product_ops_base_url=f"http://127.0.0.1:{product_ops_published_port}",
        token=token,
        cafile=None,
        deadline=deadline,
    )
    return {
        "schema": "qwq.test_live_experiment_policy_activation_receipt",
        "status": "passed",
        "launchPolicy": "test_live",
        "nonPromotable": True,
        "target": target,
        "environment": environment,
        "attemptId": attempt_id,
        "configurationDigest": configuration_digest,
        "runtimeIdentityDigest": runtime_identity_digest,
        **_activation_result(activated),
        "specRefs": list(SPEC_REFS),
        "caseResult": {
            "schema": "qwq.case_result",
            "caseId": f"{target}-test-live-experiment-policy-activation",
            "status": "passed",
            "executed": len(activated),
            "skipped": 0,
            "specRefs": list(SPEC_REFS),
        },
    }


def activate_search_experiment_policy(
    *,
    environment: str,
    target: str,
    product_ops_base_url: str,
    timeout_seconds: float = 45.0,
) -> dict[str, Any]:
    """Create or precisely reuse package-bound nonprod Search/Recommendation policies."""

    _require_nonprod_target(environment, target)
    active = active_deployment_candidate(target)
    if not isinstance(active, dict):
        raise ExperimentPolicyActivationError(
            "active immutable deployment candidate is required"
        )
    baseline_id = str(active.get("baselineId") or "").strip()
    manifest = load_candidate_manifest(
        environment,
        target,
        baseline_id,
        require_full=True,
    )
    token = mint_local_product_ops_operator_token(
        environment,
        target,
    )
    cafile = root_certificate_path(target)
    deadline = time.monotonic() + max(1.0, timeout_seconds)
    activated = _activate_policy_recipes(
        recipes=_POLICY_RECIPES,
        allow_rollout=False,
        target=target,
        binding_id=baseline_id,
        idempotency_prefix="runtime-policy",
        product_ops_base_url=product_ops_base_url,
        token=token,
        cafile=str(cafile),
        deadline=deadline,
    )
    return {
        "schema": "qwq.experiment_policy_activation_receipt",
        "status": "passed",
        "target": target,
        "environment": environment,
        "baselineId": baseline_id,
        "packageDigest": str(manifest.get("packageDigest") or ""),
        "sourceRevision": str(manifest.get("sourceRevision") or ""),
        **_activation_result(activated),
        "specRefs": list(SPEC_REFS),
        "caseResult": {
            "schema": "qwq.case_result",
            "caseId": f"{target}-search-experiment-policy-activation",
            "status": "passed",
            "executed": len(activated),
            "skipped": 0,
            "specRefs": list(SPEC_REFS),
        },
    }


def activate_search_experiment_policy_via_published_port(
    *,
    environment: str,
    target: str,
    timeout_seconds: float = 120.0,
) -> dict[str, Any]:
    """Cold-start policy owner bootstrap through the loopback published port.

    A brand-new target has no Product Ops ExperimentPolicyActivated fact and
    Recommendation intentionally refuses a full runtime without it, while the
    projected candidate topology chains product-ops -> service-core (healthy)
    -> recommendation (healthy) and deadlocks the first full compose up.  The
    bootstrap therefore activates the exact package-bound canonical policies
    against the Product Ops published loopback port before the full stack
    exists, mirroring the test_live policy owner bootstrap.  It is the same
    authenticated public command with the same idempotency identity as the
    post-up activation, never a DB seed or a Recommendation-private fallback.
    """

    _require_nonprod_target(environment, target)
    active = active_deployment_candidate(target)
    if not isinstance(active, dict):
        raise ExperimentPolicyActivationError(
            "active immutable deployment candidate is required"
        )
    baseline_id = str(active.get("baselineId") or "").strip()
    manifest = load_candidate_manifest(
        environment,
        target,
        baseline_id,
        require_full=True,
    )
    try:
        ports = profile_ports(load_port_manifest(), target)
        published_port = int(ports["product-ops-service"])
        redis_published_port = int(ports["redis"])
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise ExperimentPolicyActivationError(
            "Product Ops or Redis published port cannot be derived for the target"
        ) from exc
    token = mint_local_product_ops_operator_token(environment, target)
    deadline = time.monotonic() + max(1.0, timeout_seconds)
    activated = _activate_policy_recipes(
        recipes=_POLICY_RECIPES,
        allow_rollout=False,
        target=target,
        binding_id=baseline_id,
        idempotency_prefix="runtime-policy",
        product_ops_base_url=f"http://127.0.0.1:{published_port}",
        token=token,
        cafile=None,
        deadline=deadline,
    )
    stream_visibility = _ensure_activation_facts_visible(
        activated=activated,
        product_ops_base_url=f"http://127.0.0.1:{published_port}",
        token=token,
        redis_published_port=redis_published_port,
        deadline=deadline,
    )
    return {
        "schema": "qwq.experiment_policy_bootstrap_receipt",
        "status": "passed",
        "launchPolicy": "policy-owner-bootstrap",
        "target": target,
        "environment": environment,
        "baselineId": baseline_id,
        "packageDigest": str(manifest.get("packageDigest") or ""),
        "sourceRevision": str(manifest.get("sourceRevision") or ""),
        "productOpsPublishedPort": published_port,
        "streamVisibility": stream_visibility,
        **_activation_result(activated),
        "specRefs": list(SPEC_REFS),
        "caseResult": {
            "schema": "qwq.case_result",
            "caseId": f"{target}-experiment-policy-owner-bootstrap",
            "status": "passed",
            "executed": len(activated),
            "skipped": 0,
            "specRefs": list(SPEC_REFS),
        },
    }


def _require_nonprod_target(environment: str, target: str) -> None:
    if _NONPROD_TARGETS.get(environment) != target:
        raise ExperimentPolicyActivationError(
            "experiment policy activation is restricted to Alpha/Beta/Gamma local targets"
        )


def _activate_policy_recipes(
    *,
    recipes: tuple[dict[str, Any], ...],
    allow_rollout: bool,
    target: str,
    binding_id: str,
    idempotency_prefix: str,
    product_ops_base_url: str,
    token: str,
    cafile: str | None,
    deadline: float,
) -> list[dict[str, Any]]:
    return [
        _activate_one_policy(
            recipe=recipe,
            allow_rollout=allow_rollout,
            target=target,
            binding_id=binding_id,
            idempotency_prefix=idempotency_prefix,
            product_ops_base_url=product_ops_base_url,
            token=token,
            cafile=cafile,
            deadline=deadline,
        )
        for recipe in recipes
    ]


def _activation_result(activated: list[dict[str, Any]]) -> dict[str, Any]:
    search_policy = next(
        item["policy"] for item in activated if item["policy"]["id"] == SEARCH_POLICY_ID
    )
    operations = {str(item["operation"]) for item in activated}
    return {
        "operation": (
            "created"
            if "created" in operations
            else "rolled_out"
            if "rolled_out" in operations
            else "re_emitted"
            if "re_emitted" in operations
            else "reused"
        ),
        "policy": search_policy,
        "policies": [item["policy"] for item in activated],
        "policyOperations": {
            item["policy"]["id"]: item["operation"] for item in activated
        },
        "recipeDigests": {
            item["policy"]["id"]: item["recipeDigest"] for item in activated
        },
    }


def _ensure_activation_facts_visible(
    *,
    activated: list[dict[str, Any]],
    product_ops_base_url: str,
    token: str,
    redis_published_port: int,
    deadline: float,
    poll_interval_seconds: float = 1.0,
) -> dict[str, Any]:
    """Guarantee every activated policy has a visible fact in the Redis stream.

    reused readback 只证明 authoritative 策略（Postgres）存在，不保证下游
    可消费的 ``ExperimentPolicyActivated`` 事实仍在事实流里（流有 7 天
    retention，key 会整体过期）。缺失时经 product-ops 公开 rollout command
    做等值 re-emission（revision bump + 新事实经 outbox 派发），随后轮询
    直到事实可见；created / rolled_out 的事实已在 outbox，只需等待派发。
    禁止直写 Redis / Postgres。
    """

    expected = {str(item["policy"]["id"]) for item in activated}
    re_emitted: list[str] = []
    last_probe_error: RedisStreamProbeError | None = None
    while True:
        visible: set[str] | None
        try:
            visible = set(
                stream_field_values(
                    host="127.0.0.1",
                    port=redis_published_port,
                    stream=ACTIVATION_FACT_STREAM,
                    field="experimentId",
                )
            )
            last_probe_error = None
        except RedisStreamProbeError as error:
            visible = None
            last_probe_error = error
        if visible is not None:
            missing = sorted(expected - visible)
            if not missing:
                return {
                    "stream": ACTIVATION_FACT_STREAM,
                    "reEmittedPolicyIds": re_emitted,
                }
            for item in activated:
                policy_id = str(item["policy"]["id"])
                if (
                    policy_id not in missing
                    or item["operation"] != "reused"
                    or policy_id in re_emitted
                ):
                    continue
                item["policy"] = _re_emit_policy_activation(
                    policy_id=policy_id,
                    variants=item["policy"]["variants"],
                    product_ops_base_url=product_ops_base_url,
                    token=token,
                    deadline=deadline,
                )
                item["operation"] = "re_emitted"
                re_emitted.append(policy_id)
        if time.monotonic() >= deadline:
            raise ExperimentPolicyActivationError(
                "ExperimentPolicyActivated facts are not visible in "
                f"{ACTIVATION_FACT_STREAM}; a full-stack up would deadlock on "
                "the recommendation policy wait"
            ) from last_probe_error
        time.sleep(poll_interval_seconds)


def _re_emit_policy_activation(
    *,
    policy_id: str,
    variants: list[dict[str, Any]],
    product_ops_base_url: str,
    token: str,
    deadline: float,
) -> dict[str, Any]:
    """Re-emit the activation fact through the public rollout command.

    等值 rollout（running -> running、variants 原样）是 contracts 允许的
    转移；它把 revision +1 并经 Postgres outbox 重新发布同 schema 的
    ``ExperimentPolicyActivated``。幂等键绑定当前 revision：同一 revision
    的补发重试安全，成功后 revision 变化，未来再次流过期仍可补发。
    """

    list_status, catalog = _request_json_with_transport_retry(
        method="GET",
        url=product_ops_base_url.rstrip("/") + COLLECTION_PATH,
        token=token,
        cafile=None,
        body=None,
        headers={},
        attempt_timeout_seconds=10.0,
        deadline=deadline,
    )
    if list_status != 200:
        raise ExperimentPolicyActivationError(
            f"experiment policy readback returned HTTP {list_status} for {policy_id}"
        )
    current = _select_policy(catalog, policy_id)
    current_revision = int(current["experimentRevision"])
    rollout_status, rollout_payload = _request_json_with_transport_retry(
        method="POST",
        url=(
            product_ops_base_url.rstrip("/")
            + COLLECTION_PATH
            + f"/{policy_id}:rollout"
        ),
        token=token,
        cafile=None,
        body={"status": "running", "variants": variants},
        headers={
            "If-Match": f'"{current_revision}"',
            "Idempotency-Key": (
                f"runtime-policy-reemit/{policy_id}/r{current_revision}"
            ),
        },
        attempt_timeout_seconds=10.0,
        deadline=deadline,
    )
    if rollout_status != 200:
        raise ExperimentPolicyActivationError(
            "experiment policy fact re-emission returned "
            f"HTTP {rollout_status} for {policy_id}"
        )
    if (
        rollout_payload.get("id") != policy_id
        or rollout_payload.get("status") != "running"
        or rollout_payload.get("variants") != variants
        or int(rollout_payload.get("experimentRevision") or 0) <= current_revision
    ):
        raise ExperimentPolicyActivationError(
            f"experiment policy fact re-emission result is invalid for {policy_id}"
        )
    return {
        "id": policy_id,
        "key": policy_id,
        "status": "running",
        "experimentRevision": int(rollout_payload["experimentRevision"]),
        "variants": rollout_payload["variants"],
    }


def _activate_one_policy(
    *,
    recipe: dict[str, Any],
    allow_rollout: bool,
    target: str,
    binding_id: str,
    idempotency_prefix: str,
    product_ops_base_url: str,
    token: str,
    cafile: str | None,
    deadline: float,
) -> dict[str, Any]:
    recipe_bytes = (
        json.dumps(
            recipe,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    recipe_digest = "sha256:" + hashlib.sha256(recipe_bytes).hexdigest()
    policy_id = str(recipe["id"])
    idempotency_key = (
        idempotency_prefix
        + "/"
        + target
        + "/"
        + binding_id.removeprefix("sha256:")[:16]
        + "/"
        + policy_id
        + "/"
        + recipe_digest.removeprefix("sha256:")[:24]
    )
    # create 携带 Idempotency-Key、readback 是只读 GET：两者对连接级失败
    # （进程尚未监听 / 连接被拒 / 连接被重置）重试都是安全的。
    # Compose healthcheck 只证明 /healthz liveness，所以冷启动时还可能收到
    # servicekit 在 OpenAdmission 前发射的规范 typed 503。该情形仅对
    # 原 body 和同一 Idempotency-Key 做 deadline 内重试；其他业务失败 fail-fast。
    create_status, create_payload = _request_json_with_create_startup_retry(
        method="POST",
        url=product_ops_base_url.rstrip("/") + COLLECTION_PATH,
        token=token,
        cafile=cafile,
        body=recipe,
        headers={"Idempotency-Key": idempotency_key},
        attempt_timeout_seconds=5.0,
        deadline=deadline,
    )
    if create_status not in {201, 409}:
        typed_failure = _safe_typed_failure_fingerprint(create_payload)
        typed_suffix = (
            "; typedFailure=" + json.dumps(
                typed_failure,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            if typed_failure
            else ""
        )
        raise ExperimentPolicyActivationError(
            "experiment policy create returned "
            f"HTTP {create_status} for {policy_id}{typed_suffix}"
        )
    list_status, catalog = _request_json_with_transport_retry(
        method="GET",
        url=product_ops_base_url.rstrip("/") + COLLECTION_PATH,
        token=token,
        cafile=cafile,
        body=None,
        headers={},
        attempt_timeout_seconds=10.0,
        deadline=deadline,
    )
    if list_status != 200:
        raise ExperimentPolicyActivationError(
            f"experiment policy readback returned HTTP {list_status} for {policy_id}"
        )
    try:
        policy = _select_and_validate_policy(catalog, recipe)
        operation = "created" if create_status == 201 else "reused"
    except ExperimentPolicyActivationError:
        if create_status != 409 or not allow_rollout:
            raise
        current = _select_policy(catalog, policy_id)
        rollout_status, rollout_payload = _request_json(
            method="POST",
            url=(
                product_ops_base_url.rstrip("/")
                + COLLECTION_PATH
                + f"/{policy_id}:rollout"
            ),
            token=token,
            cafile=cafile,
            body={"status": "running", "variants": recipe["variants"]},
            headers={
                "If-Match": f'"{current["experimentRevision"]}"',
                "Idempotency-Key": idempotency_key + "/rollout",
            },
            timeout_seconds=min(10.0, max(1.0, deadline - time.monotonic())),
        )
        if rollout_status != 200:
            raise ExperimentPolicyActivationError(
                f"experiment policy rollout returned HTTP {rollout_status} for {policy_id}"
            )
        readback_status, readback_catalog = _request_json(
            method="GET",
            url=product_ops_base_url.rstrip("/") + COLLECTION_PATH,
            token=token,
            cafile=cafile,
            body=None,
            headers={},
            timeout_seconds=min(10.0, max(1.0, deadline - time.monotonic())),
        )
        if readback_status != 200:
            raise ExperimentPolicyActivationError(
                f"experiment policy rollout readback returned HTTP {readback_status} for {policy_id}"
            )
        policy = _select_and_validate_policy(readback_catalog, recipe)
        if (
            rollout_payload.get("id") != policy_id
            or rollout_payload.get("status") != "running"
            or rollout_payload.get("experimentRevision")
            != policy["experimentRevision"]
            or rollout_payload.get("variants") != recipe["variants"]
        ):
            raise ExperimentPolicyActivationError(
                f"experiment policy rollout response differs from catalog readback for {policy_id}"
            )
        operation = "rolled_out"
    if create_status == 201:
        if (
            create_payload.get("id") != policy_id
            or create_payload.get("key") != policy_id
            or create_payload.get("status") != "running"
            or create_payload.get("experimentRevision") != policy["experimentRevision"]
        ):
            raise ExperimentPolicyActivationError(
                f"experiment policy create response differs from catalog readback for {policy_id}"
            )
    return {
        "operation": operation,
        "recipeDigest": recipe_digest,
        "policy": policy,
    }


def _select_and_validate_policy(
    catalog: dict[str, Any],
    recipe: dict[str, Any],
) -> dict[str, Any]:
    policy_id = str(recipe["id"])
    item = _select_policy(catalog, policy_id)
    if (
        item.get("key") != policy_id
        or item.get("status") != "running"
        or not isinstance(item.get("experimentRevision"), int)
        or int(item["experimentRevision"]) <= 0
        or item.get("variants") != recipe["variants"]
    ):
        raise ExperimentPolicyActivationError(
            f"existing {policy_id} policy differs from the canonical recipe"
        )
    return {
        "id": policy_id,
        "key": policy_id,
        "status": "running",
        "experimentRevision": int(item["experimentRevision"]),
        "variants": item["variants"],
    }


def _select_policy(catalog: dict[str, Any], policy_id: str) -> dict[str, Any]:
    items = catalog.get("items")
    if not isinstance(items, list):
        raise ExperimentPolicyActivationError(
            "experiment policy catalog has no typed items"
        )
    matches = [
        item
        for item in items
        if isinstance(item, dict) and item.get("id") == policy_id
    ]
    if len(matches) != 1:
        raise ExperimentPolicyActivationError(
            f"experiment policy catalog does not contain one {policy_id} policy"
        )
    item = matches[0]
    if (
        item.get("key") != policy_id
        or item.get("status") not in {"draft", "scheduled", "running", "paused"}
        or not isinstance(item.get("experimentRevision"), int)
        or int(item["experimentRevision"]) <= 0
        or not isinstance(item.get("variants"), list)
    ):
        raise ExperimentPolicyActivationError(
            f"existing {policy_id} policy identity is invalid"
        )
    return item


def _request_json_with_transport_retry(
    *,
    method: str,
    url: str,
    token: str,
    cafile: str | None,
    body: dict[str, Any] | None,
    headers: dict[str, str],
    attempt_timeout_seconds: float,
    deadline: float,
    retry_interval_seconds: float = 0.5,
) -> tuple[int, dict[str, Any]]:
    """Bounded retry for connection-level failures only.

    Policy owner bootstrap 在 product-ops 进程刚被拉起时立即激活，HTTP
    监听可能尚未就绪且 healthz 在 user-service 缺席时必然 unhealthy，
    所以唯一正确的等待信号就是「连接是否成立」。业务错误直接透传。
    """

    while True:
        try:
            return _request_json(
                method=method,
                url=url,
                token=token,
                cafile=cafile,
                body=body,
                headers=headers,
                timeout_seconds=min(
                    attempt_timeout_seconds,
                    max(1.0, deadline - time.monotonic()),
                ),
            )
        except ExperimentPolicyTransportError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(retry_interval_seconds)


def _request_json_with_create_startup_retry(
    *,
    method: str,
    url: str,
    token: str,
    cafile: str | None,
    body: dict[str, Any] | None,
    headers: dict[str, str],
    attempt_timeout_seconds: float,
    deadline: float,
) -> tuple[int, dict[str, Any]]:
    """Retry only servicekit's exact pre-admission 503 until the caller deadline."""

    while True:
        status, payload = _request_json_with_transport_retry(
            method=method,
            url=url,
            token=token,
            cafile=cafile,
            body=body,
            headers=headers,
            attempt_timeout_seconds=attempt_timeout_seconds,
            deadline=deadline,
        )
        if not _is_admission_not_ready(status, payload):
            return status, payload
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return status, payload
        # The exact same body/header objects are passed to the next request; in
        # particular the idempotency key cannot drift across the startup race.
        time.sleep(min(1.0, remaining))


def _is_admission_not_ready(status: int, payload: dict[str, Any]) -> bool:
    if not _ADMISSION_NOT_READY_REQUIRED_FIELDS.issubset(payload):
        return False
    recovery = payload.get("recovery")
    return (
        status == 503
        and payload.get("code") == _ADMISSION_NOT_READY_CODE
        and payload.get("origin") == "remoteDependency"
        and payload.get("module") == "GATEWAY"
        and payload.get("nature") == "transient"
        and payload.get("userMessage") == "服务暂不可用，请稍后重试"
        and payload.get("debugMessage") == "debug_message_redacted"
        and payload.get("kind") == "unavailable"
        and payload.get("reason") == "upstream_unavailable"
        and payload.get("location")
        == {
            "businessObject": "cloud_request",
            "functionModule": "runtime_errors",
        }
        and payload.get("context")
        == {
            "attributes": [
                {"key": "module", "value": "GATEWAY"},
                {"key": "reason", "value": "upstream_unavailable"},
            ]
        }
        and isinstance(recovery, dict)
        and recovery.get("action") == "retry"
        and recovery.get("afterSeconds") == 1
        and recovery.get("disruptionLevel") == "snackbar"
    )


def _safe_typed_failure_fingerprint(payload: dict[str, Any]) -> dict[str, Any]:
    """Project only bounded non-secret error classification fields.

    HTTP error bodies can contain correlation IDs, source locations or future
    provider details.  Startup receipts need the typed blocker identity, not
    the original response, so the projection is an explicit allowlist.
    """

    fingerprint = {
        field: payload[field]
        for field in _SAFE_TYPED_FAILURE_FIELDS
        if isinstance(payload.get(field), str) and payload[field]
    }
    recovery = payload.get("recovery")
    if isinstance(recovery, dict):
        safe_recovery: dict[str, Any] = {}
        if isinstance(recovery.get("action"), str) and recovery["action"]:
            safe_recovery["action"] = recovery["action"]
        after_seconds = recovery.get("afterSeconds")
        if isinstance(after_seconds, int) and not isinstance(after_seconds, bool):
            safe_recovery["afterSeconds"] = after_seconds
        disruption = recovery.get("disruptionLevel")
        if isinstance(disruption, str) and disruption:
            safe_recovery["disruptionLevel"] = disruption
        if safe_recovery:
            fingerprint["recovery"] = safe_recovery
    return fingerprint


def _request_json(
    *,
    method: str,
    url: str,
    token: str,
    cafile: str | None,
    body: dict[str, Any] | None,
    headers: dict[str, str],
    timeout_seconds: float,
) -> tuple[int, dict[str, Any]]:
    payload = (
        json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if body is not None
        else None
    )
    request_headers = {
        "Accept": "application/json",
        "Authorization": "Bearer " + token,
        **headers,
    }
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
    handlers: list[Any] = [request.ProxyHandler({})]
    if cafile is not None:
        context = ssl.create_default_context(cafile=cafile)
        handlers.append(request.HTTPSHandler(context=context))
    opener = request.build_opener(*handlers)
    req = request.Request(
        url,
        data=payload,
        headers=request_headers,
        method=method,
    )
    try:
        with opener.open(req, timeout=max(1.0, timeout_seconds)) as response:
            status = int(response.status)
            raw = response.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        status = int(exc.code)
        raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
    except Exception as exc:  # noqa: BLE001
        raise ExperimentPolicyTransportError(
            f"experiment policy request transport failed: {type(exc).__name__}"
        ) from exc
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ExperimentPolicyActivationError(
            f"experiment policy request returned non-JSON HTTP {status}"
        ) from exc
    if not isinstance(parsed, dict):
        raise ExperimentPolicyActivationError(
            f"experiment policy request returned non-object HTTP {status}"
        )
    return status, parsed
