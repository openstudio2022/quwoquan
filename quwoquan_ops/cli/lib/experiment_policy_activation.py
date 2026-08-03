"""Package-bound Product Ops experiment policy activation for local targets.

The activation is a real authenticated public command.  It never seeds a
database, writes a service-private config, or persists the short-lived bearer.
"""

from __future__ import annotations

import hashlib
import json
import ssl
import time
from typing import Any
from urllib import error, request

from .deployment_candidate_manifest import load_candidate_manifest
from .local_environment_auth import mint_local_product_ops_operator_token
from .output_paths import active_deployment_candidate
from .public_domain_tls import root_certificate_path


COLLECTION_PATH = "/control-plane/product/experiments"
SEARCH_POLICY_ID = "search_ranking"
SPEC_REFS = (
    "specs/feature-tree/product-ops-growth/experiment-bucketing-and-rollout/spec.md#sit-001",
    "specs/feature-tree/product-ops-growth/experiment-bucketing-and-rollout/bucketing-strategy-engine/spec.md#gwt-001",
)
_NONPROD_TARGETS = {
    "alpha": "alpha-local",
    "beta": "beta-local",
    "gamma": "gamma-local",
}
_POLICY_RECIPE: dict[str, Any] = {
    "id": SEARCH_POLICY_ID,
    "key": SEARCH_POLICY_ID,
    "status": "running",
    "variants": [
        {"key": "control", "allocationBasisPoints": 5000},
        {"key": "term_heat", "allocationBasisPoints": 5000},
    ],
    "audienceRule": {"kind": "all"},
}


class ExperimentPolicyActivationError(RuntimeError):
    """Redacted local policy activation failure."""


def activate_search_experiment_policy(
    *,
    environment: str,
    target: str,
    product_ops_base_url: str,
    timeout_seconds: float = 45.0,
) -> dict[str, Any]:
    """Create or precisely reuse the package-bound nonprod Search policy."""

    if _NONPROD_TARGETS.get(environment) != target:
        raise ExperimentPolicyActivationError(
            "experiment policy activation is restricted to Alpha/Beta/Gamma local targets"
        )
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
    recipe_bytes = (
        json.dumps(
            _POLICY_RECIPE,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    recipe_digest = "sha256:" + hashlib.sha256(recipe_bytes).hexdigest()
    idempotency_key = (
        "runtime-policy/"
        + target
        + "/"
        + baseline_id.removeprefix("sha256:")[:16]
        + "/"
        + recipe_digest.removeprefix("sha256:")[:24]
    )
    token = mint_local_product_ops_operator_token(
        environment,
        target,
    )
    cafile = root_certificate_path(target)
    deadline = time.monotonic() + max(1.0, timeout_seconds)
    create_status = 0
    create_payload: dict[str, Any] = {}
    while True:
        try:
            create_status, create_payload = _request_json(
                method="POST",
                url=product_ops_base_url.rstrip("/") + COLLECTION_PATH,
                token=token,
                cafile=str(cafile),
                body=_POLICY_RECIPE,
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
            f"experiment policy create returned HTTP {create_status}"
        )
    list_status, catalog = _request_json(
        method="GET",
        url=product_ops_base_url.rstrip("/") + COLLECTION_PATH,
        token=token,
        cafile=str(cafile),
        body=None,
        headers={},
        timeout_seconds=min(10.0, max(1.0, deadline - time.monotonic())),
    )
    if list_status != 200:
        raise ExperimentPolicyActivationError(
            f"experiment policy readback returned HTTP {list_status}"
        )
    policy = _select_and_validate_policy(catalog)
    operation = "created" if create_status == 201 else "reused"
    if create_status == 201:
        if (
            create_payload.get("id") != SEARCH_POLICY_ID
            or create_payload.get("key") != SEARCH_POLICY_ID
            or create_payload.get("status") != "running"
            or create_payload.get("experimentRevision") != policy["experimentRevision"]
        ):
            raise ExperimentPolicyActivationError(
                "experiment policy create response differs from catalog readback"
            )
    return {
        "schema": "qwq.experiment_policy_activation_receipt",
        "status": "passed",
        "target": target,
        "environment": environment,
        "baselineId": baseline_id,
        "packageDigest": str(manifest.get("packageDigest") or ""),
        "sourceRevision": str(manifest.get("sourceRevision") or ""),
        "recipeDigest": recipe_digest,
        "operation": operation,
        "policy": policy,
        "specRefs": list(SPEC_REFS),
        "caseResult": {
            "schema": "qwq.case_result",
            "caseId": f"{target}-search-experiment-policy-activation",
            "status": "passed",
            "executed": 1,
            "skipped": 0,
            "specRefs": list(SPEC_REFS),
        },
    }


def _select_and_validate_policy(catalog: dict[str, Any]) -> dict[str, Any]:
    items = catalog.get("items")
    if not isinstance(items, list):
        raise ExperimentPolicyActivationError(
            "experiment policy catalog has no typed items"
        )
    matches = [
        item
        for item in items
        if isinstance(item, dict) and item.get("id") == SEARCH_POLICY_ID
    ]
    if len(matches) != 1:
        raise ExperimentPolicyActivationError(
            "experiment policy catalog does not contain one search_ranking policy"
        )
    item = matches[0]
    if (
        item.get("key") != SEARCH_POLICY_ID
        or item.get("status") != "running"
        or not isinstance(item.get("experimentRevision"), int)
        or int(item["experimentRevision"]) <= 0
        or item.get("variants") != _POLICY_RECIPE["variants"]
    ):
        raise ExperimentPolicyActivationError(
            "existing search_ranking policy differs from the canonical recipe"
        )
    return {
        "id": SEARCH_POLICY_ID,
        "key": SEARCH_POLICY_ID,
        "status": "running",
        "experimentRevision": int(item["experimentRevision"]),
        "variants": item["variants"],
    }


def _request_json(
    *,
    method: str,
    url: str,
    token: str,
    cafile: str,
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
    context = ssl.create_default_context(cafile=cafile)
    opener = request.build_opener(
        request.ProxyHandler({}),
        request.HTTPSHandler(context=context),
    )
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
