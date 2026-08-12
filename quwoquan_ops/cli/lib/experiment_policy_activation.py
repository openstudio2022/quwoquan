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


COLLECTION_PATH = "/control-plane/product/experiments"
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
    create_status = 0
    create_payload: dict[str, Any] = {}
    while True:
        try:
            create_status, create_payload = _request_json(
                method="POST",
                url=product_ops_base_url.rstrip("/") + COLLECTION_PATH,
                token=token,
                cafile=cafile,
                body=recipe,
                headers={"Idempotency-Key": idempotency_key},
                timeout_seconds=min(5.0, max(1.0, deadline - time.monotonic())),
            )
            break
        except ExperimentPolicyActivationError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.5)
    if create_status not in {201, 409}:
        raise ExperimentPolicyActivationError(
            f"experiment policy create returned HTTP {create_status} for {policy_id}"
        )
    list_status, catalog = _request_json(
        method="GET",
        url=product_ops_base_url.rstrip("/") + COLLECTION_PATH,
        token=token,
        cafile=cafile,
        body=None,
        headers={},
        timeout_seconds=min(10.0, max(1.0, deadline - time.monotonic())),
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
        raise ExperimentPolicyActivationError(
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
