#!/usr/bin/env python3
"""Observe-only CLI for authenticated hosted human authority readback."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "quwoquan_ops/cli"))
sys.path.insert(0, str(REPO_ROOT))

from lib.hosted_authority import (  # noqa: E402
    EnvironmentTokenProvider,
    ExternalDependencyBlocker,
    HostedAuthorityError,
    HostedAuthorityHttpClient,
    runtime_from_env,
    verify_ed25519,
)


def _verified_release_eligibility(
    exact_body: bytes, *, transport_tls: bool, key_id: str, explicit_policy: bool
) -> bool:
    try:
        claims = json.loads(exact_body)
    except (UnicodeError, json.JSONDecodeError):
        return False
    return (
        isinstance(claims, dict)
        and transport_tls
        and explicit_policy
        and claims.get("testKey") is False
        and claims.get("releaseEligible") is True
        and not any(marker in key_id.lower() for marker in ("test", "fixture", "dev", "local"))
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    query = subparsers.add_parser("query")
    query.add_argument("--decision-id", required=True)
    return parser


def _query(decision_id: str) -> dict[str, object]:
    runtime = runtime_from_env(REPO_ROOT, token_provider=EnvironmentTokenProvider())
    client = HostedAuthorityHttpClient(runtime.config, token_provider=runtime.token_provider)
    response = client.query(decision_id)
    verify_ed25519(response.exact_body, response.envelope, runtime.trusted_public_keys)
    return {
        "result": "observed",
        "provider_kind": "hosted-human-authority",
        "provider_receipt_ref": response.envelope.provider_receipt_ref,
        "body_sha256": response.body_sha256,
        "exact_bytes_verified": True,
        "release_evidence_eligible": _verified_release_eligibility(
            response.exact_body,
            transport_tls=response.envelope.transport_tls,
            key_id=response.envelope.key_id,
            explicit_policy=runtime.config.explicit_release_policy,
        ),
        "mutation_performed": False,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = _query(args.decision_id)
    except (ExternalDependencyBlocker, HostedAuthorityError) as error:
        result = error.as_dict()
    json.dump(result, sys.stdout, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0 if result.get("result") == "observed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
