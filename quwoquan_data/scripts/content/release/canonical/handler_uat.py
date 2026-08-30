"""CLI handlers for release UAT authority and exit proof operations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from content.release.canonical.m1000_four_environment_proof import (
    M1000FourEnvironmentProofError,
    evaluate_m1000_four_environment_proof,
)
from content.release.canonical.release_uat_sampling_authority import (
    ReleaseUatSamplingAuthorityError,
    project_release_uat_sampling_authority,
    write_release_uat_sampling_authority_projection,
)
from core.io import read_json


def handle_project_uat_sampling_authority(args: argparse.Namespace) -> None:
    """Project exact external strategy/readbacks without creating authority facts."""
    try:
        result = project_release_uat_sampling_authority(
            artifact_root=Path(str(args.artifact_root)).expanduser(),
            release_id=str(args.release_id),
            release_digest=str(args.release_digest),
            strategy_binding={
                "ref": str(args.strategy_ref),
                "digest": str(args.strategy_digest),
            },
            product_owner_readback={
                "ref": str(args.product_readback_ref),
                "digest": str(args.product_readback_digest),
            },
            quality_owner_readback={
                "ref": str(args.quality_readback_ref),
                "digest": str(args.quality_readback_digest),
            },
        )
        output = str(getattr(args, "output", "") or "").strip()
        if output:
            write_release_uat_sampling_authority_projection(Path(output), result)
    except (
        FileNotFoundError,
        OSError,
        ReleaseUatSamplingAuthorityError,
        TypeError,
        ValueError,
    ) as exc:
        raise SystemExit(
            f"[release project-uat-sampling-authority] GATE_BLOCK {exc}"
        ) from exc
    print(json.dumps(result, ensure_ascii=False, indent=2))


def handle_m1000_four_environment_proof(args: argparse.Namespace) -> None:
    """Run the read-only explicit M1000 four-environment exit evaluator."""
    try:
        request = read_json(Path(str(args.request)).expanduser())
        if not isinstance(request, dict):
            raise M1000FourEnvironmentProofError(
                "request JSON root must be an object"
            )
        result = evaluate_m1000_four_environment_proof(
            artifact_root=Path(str(args.artifact_root)).expanduser(),
            request=request,
        )
    except (
        FileNotFoundError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        raise SystemExit(
            f"[release prove-m1000-four-env] GATE_BLOCK {exc}"
        ) from exc
    print(json.dumps(result, ensure_ascii=False, indent=2))


__all__ = [
    "handle_m1000_four_environment_proof",
    "handle_project_uat_sampling_authority",
]
