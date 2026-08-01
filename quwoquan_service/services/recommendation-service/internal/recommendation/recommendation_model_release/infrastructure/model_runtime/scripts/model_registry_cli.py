#!/usr/bin/env python3
"""CLI facade for the single RecommendationModelRelease command track."""
from __future__ import annotations

import argparse
import json

from model_release_client import activate_release, stage_release


def _json_object(value: str) -> dict:
    parsed = json.loads(value)
    if not isinstance(parsed, dict) or not parsed:
        raise argparse.ArgumentTypeError("value must be a non-empty JSON object")
    return parsed


def cmd_stage(args: argparse.Namespace) -> dict:
    result = stage_release(
        release_id=args.release_id,
        scenario=args.scenario,
        artifact_uri=args.artifact_uri,
        model_digest=args.model_digest,
        feature_contract_digest=args.feature_contract_digest,
        verification_digest=args.verification_digest,
        evaluation_metrics=args.evaluation_metrics,
        idempotency_key=args.idempotency_key,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return result


def cmd_activate(args: argparse.Namespace) -> dict:
    result = activate_release(
        release_id=args.release_id,
        scenario=args.scenario,
        expected_active_release_id=args.expected_active_release_id,
        idempotency_key=args.idempotency_key,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="RecommendationModelRelease Stage/Activate facade"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    stage = sub.add_parser("stage", help="Stage one immutable verified release")
    stage.add_argument("--release-id", required=True)
    stage.add_argument("--scenario", required=True)
    stage.add_argument("--artifact-uri", required=True)
    stage.add_argument("--model-digest", required=True)
    stage.add_argument("--feature-contract-digest", required=True)
    stage.add_argument("--verification-digest", required=True)
    stage.add_argument("--evaluation-metrics", required=True, type=_json_object)
    stage.add_argument("--idempotency-key", default=None)
    stage.set_defaults(handler=cmd_stage)

    activate = sub.add_parser(
        "activate",
        help="CAS activate a staged or retired verified release",
    )
    activate.add_argument("--release-id", required=True)
    activate.add_argument("--scenario", required=True)
    activate.add_argument("--expected-active-release-id", default=None)
    activate.add_argument("--idempotency-key", default=None)
    activate.set_defaults(handler=cmd_activate)

    args = parser.parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
