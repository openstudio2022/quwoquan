#!/usr/bin/env python3
"""Observe-only hosted authority integration smoke; performs no governed mutation."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

sys.dont_write_bytecode = True
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "quwoquan_ops/cli"))
sys.path.insert(0, str(REPO_ROOT))

from lib.agent_governance_contract import validate_feature_context_manifest  # noqa: E402
from lib.hosted_authority import (  # noqa: E402
    EnvironmentTokenProvider,
    HostedAuthorityError,
    HostedAuthorityHttpClient,
    runtime_from_env,
)
from lib.objective_execution.hosted_provider import (  # noqa: E402
    HostedAuthorityProvider,
    HostedAuthorityVerifier,
    ObserveOnlyEffectAdapter,
)
from lib.readiness_case_result import validate_readiness_result_bundle  # noqa: E402
from lib.workflow_resolution import verify_receipt  # noqa: E402


def _json_object(path: Path, *, label: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _fresh_readiness(bundle: Mapping[str, Any], *, now: datetime, max_age_seconds: int) -> dict[str, Any]:
    validated = validate_readiness_result_bundle(bundle)
    generated = datetime.fromisoformat(str(validated["generatedAt"]).replace("Z", "+00:00"))
    if generated.tzinfo is None or generated.astimezone(timezone.utc) > now:
        raise ValueError("readiness generatedAt is invalid")
    age = (now - generated.astimezone(timezone.utc)).total_seconds()
    if age > max_age_seconds:
        raise ValueError("readiness is stale")
    return validated


def run_observe_only_smoke(
    *,
    resolver_receipt: Mapping[str, Any],
    owner_manifest: Mapping[str, Any],
    readiness_bundle: Mapping[str, Any],
    receipt_ref: str,
    client: HostedAuthorityHttpClient,
    trusted_public_keys: Mapping[str, bytes],
    now: datetime | None = None,
    readiness_max_age_seconds: int = 300,
) -> dict[str, Any]:
    """Verify the adapter chain without claiming authority or a real effect."""
    current = now or datetime.now(timezone.utc)
    resolved = verify_receipt(resolver_receipt)
    validated_manifest = dict(owner_manifest)
    validate_feature_context_manifest(validated_manifest)
    readiness = _fresh_readiness(
        readiness_bundle,
        now=current,
        max_age_seconds=readiness_max_age_seconds,
    )
    provider = HostedAuthorityProvider(client)
    readback = provider.readback(receipt_ref)
    if readback.status != "present" or readback.exact_bytes is None or readback.provider_receipt_ref is None:
        raise HostedAuthorityError(
            "HOSTED_AUTHORITY.SMOKE_READBACK_BLOCKED",
            readback.detail or f"authority readback status={readback.status}",
        )
    claims = HostedAuthorityVerifier(provider, trusted_public_keys).verify(
        readback.exact_bytes,
        readback.provider_receipt_ref,
    )
    effect = ObserveOnlyEffectAdapter()
    effect_id = "observe:smoke:" + str(resolver_receipt["receipt_digest"])
    effect.invoke(
        action="observe_objective", effect_id=effect_id,
        idempotency_key="smoke:" + str(resolver_receipt["receipt_digest"]),
        payload={"environment": "gamma", "mutation": False},
    )
    effect_readback = dict(
        effect.readback(effect_id=effect_id, idempotency_key="smoke:" + str(resolver_receipt["receipt_digest"]))
    )
    if effect_readback["status"] != "applied" or effect_readback["exact_match"] is not True:
        raise HostedAuthorityError("HOSTED_AUTHORITY.SMOKE_EFFECT_UNKNOWN", "observe effect readback is unknown")
    return {
        "result": "observed",
        "resolver_mode": resolver_receipt["input_mode"],
        "workflow": resolved["selected_workflow"],
        "owner_manifest_ref": resolver_receipt["owner_manifest_ref"],
        "owner": validated_manifest["resolved_owner"],
        "readiness_result_count": len(readiness["results"]),
        "provider_kind": provider.provider_kind,
        "provider_receipt_ref": readback.provider_receipt_ref,
        "authority_receipt_id": claims.get("receipt_id"),
        "signature_verified": True,
        "release_evidence_eligible": provider.release_evidence_eligible,
        "objective_effect": "observe-only-test",
        "mutation_performed": False,
        "review_consumer_available": (REPO_ROOT / "quwoquan_ops/cli/review_consolidator.py").is_file(),
        "handoff_consumer_available": (REPO_ROOT / "quwoquan_ops/cli/handoff_consumer.py").is_file(),
        "claim_limit": "does_not_prove_real_authority_or_governed_effect_completion",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resolver-receipt", required=True, type=Path)
    parser.add_argument("--owner-manifest", required=True, type=Path)
    parser.add_argument("--readiness-bundle", required=True, type=Path)
    parser.add_argument("--authority-receipt-ref", required=True)
    parser.add_argument("--readiness-max-age-seconds", type=int, default=300)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        runtime = runtime_from_env(REPO_ROOT, token_provider=EnvironmentTokenProvider())
        result = run_observe_only_smoke(
            resolver_receipt=_json_object(args.resolver_receipt, label="resolver receipt"),
            owner_manifest=_json_object(args.owner_manifest, label="owner manifest"),
            readiness_bundle=_json_object(args.readiness_bundle, label="readiness bundle"),
            receipt_ref=args.authority_receipt_ref,
            client=HostedAuthorityHttpClient(runtime.config, token_provider=runtime.token_provider),
            trusted_public_keys=runtime.trusted_public_keys,
            readiness_max_age_seconds=args.readiness_max_age_seconds,
        )
    except HostedAuthorityError as error:
        result = error.as_dict()
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        result = {
            "result": "typed_blocker",
            "code": "HOSTED_AUTHORITY.SMOKE_INPUT_INVALID",
            "terminal": "blocked",
            "retry_allowed": False,
            "detail": " ".join(str(error).replace("\x00", "\\x00").split()),
        }
    json.dump(result, sys.stdout, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0 if result.get("result") == "observed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
