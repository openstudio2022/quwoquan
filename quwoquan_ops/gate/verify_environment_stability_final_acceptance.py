#!/usr/bin/env python3
"""Calculate one fail-closed final environment-stability acceptance receipt."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.environment_stability_final_acceptance import (  # noqa: E402
    FinalAcceptanceInputs,
    evaluate_final_acceptance,
    write_final_acceptance,
)
from quwoquan_ops.cli.lib.output_paths import repo_run_dir  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate explicit typed receipts for one immutable release candidate. "
            "Missing inputs produce a typed GATE_BLOCK receipt."
        )
    )
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--candidate-manifest", type=Path)
    parser.add_argument("--pilot-release-attestation", type=Path)
    parser.add_argument("--pilot-rollback-attestation", type=Path)
    for environment in ("alpha", "beta", "gamma"):
        parser.add_argument(f"--content-lifecycle-{environment}", type=Path)
    parser.add_argument("--local-env-green-matrix", type=Path)
    parser.add_argument("--ios-recovery-uat", type=Path)
    parser.add_argument("--android-recovery-uat", type=Path)
    parser.add_argument("--nightly-artifact", type=Path)
    parser.add_argument("--prod-sim-receipt", type=Path)
    parser.add_argument("--prod-rollout-readback", type=Path)
    parser.add_argument("--prod-rollback-readback", type=Path)
    parser.add_argument("--prod-soak-readback", type=Path)
    parser.add_argument(
        "--max-age-seconds",
        type=int,
        default=86_400,
        help="Maximum authoritative receipt age; default: 86400",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help=(
            "Typed result path; default is a unique "
            ".qwq_output/env/repo/runs/final-acceptance run"
        ),
    )
    return parser


def _inputs(args: argparse.Namespace) -> FinalAcceptanceInputs:
    return FinalAcceptanceInputs(
        artifact_root=args.artifact_root,
        candidate_manifest=args.candidate_manifest,
        pilot_release_attestation=args.pilot_release_attestation,
        pilot_rollback_attestation=args.pilot_rollback_attestation,
        content_lifecycle_alpha=args.content_lifecycle_alpha,
        content_lifecycle_beta=args.content_lifecycle_beta,
        content_lifecycle_gamma=args.content_lifecycle_gamma,
        local_env_green_matrix=args.local_env_green_matrix,
        ios_recovery_uat=args.ios_recovery_uat,
        android_recovery_uat=args.android_recovery_uat,
        nightly_artifact=args.nightly_artifact,
        prod_sim_receipt=args.prod_sim_receipt,
        prod_rollout_readback=args.prod_rollout_readback,
        prod_rollback_readback=args.prod_rollback_readback,
        prod_soak_readback=args.prod_soak_readback,
    )


def main() -> int:
    args = _parser().parse_args()
    output = args.output or (
        repo_run_dir(
            "environment-stability-final-acceptance",
            target="release",
        )
        / "receipt.json"
    )
    try:
        payload = evaluate_final_acceptance(
            _inputs(args),
            max_age_seconds=args.max_age_seconds,
        )
        write_final_acceptance(output, payload)
    except (OSError, ValueError) as exc:
        print(
            f"GATE_BLOCK: final acceptance could not be calculated: {exc}",
            file=sys.stderr,
        )
        return 2
    print(f"{payload['verdict']}: {output.resolve()}")
    return 0 if payload["verdict"] == "PROMOTABLE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
