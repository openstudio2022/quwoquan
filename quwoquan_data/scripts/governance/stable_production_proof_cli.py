"""Read-only canonical CLI for OPEN-006 proof and retirement precheck."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from governance.stable_production_proof import (
    RETIREMENT_INVENTORY_RELATIVE,
    StableProductionProofError,
    evaluate_legacy_retirement_precheck,
    evaluate_stable_production_proof_request,
    load_stable_production_proof_request,
    write_local_run_evidence_create_once,
)
from core.paths import DATA_LOCAL_ROOT


def _artifact_root(args: argparse.Namespace) -> Path | None:
    value = getattr(args, "artifact_root", None)
    return Path(value) if value else None


def _output(args: argparse.Namespace, result: dict[str, object]) -> None:
    output = getattr(args, "output", None)
    if output:
        destination = Path(output).expanduser()
        local_run_root = (DATA_LOCAL_ROOT / "runs").resolve()
        try:
            destination.resolve(strict=False).relative_to(local_run_root)
        except ValueError as exc:
            raise StableProductionProofError(
                f"--output must be under local run evidence root {local_run_root}"
            ) from exc
        write_local_run_evidence_create_once(output=destination, document=result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def handle_stable_production_proof(args: argparse.Namespace) -> None:
    try:
        request = load_stable_production_proof_request(Path(args.request))
        result = evaluate_stable_production_proof_request(
            request=request, artifact_root=_artifact_root(args)
        )
        _output(args, result)
    except (OSError, ValueError) as exc:
        raise SystemExit(
            "[governance stable-production-proof] GATE_BLOCK "
            "DATA.STABLE_PRODUCTION_PROOF.CURRENT_EVIDENCE_REQUIRED: "
            "current evidence for exactly three proof units is required: " + str(exc)
        ) from exc


def handle_legacy_retirement_precheck(args: argparse.Namespace) -> None:
    proof_ref = (
        {
            "ref": str(args.stable_proof_ref),
            "exactByteDigest": str(args.stable_proof_digest),
        }
        if args.stable_proof_ref and args.stable_proof_digest
        else None
    )
    try:
        result = evaluate_legacy_retirement_precheck(
            artifact_root=_artifact_root(args),
            expected_fingerprint=args.fingerprint,
            stable_production_proof_ref=proof_ref,
            retirement_inventory=Path(args.retirement_inventory),
        )
        _output(args, result)
    except (OSError, ValueError) as exc:
        raise SystemExit(
            "[governance legacy-retirement-precheck] GATE_BLOCK "
            "DATA.LEGACY_RETIREMENT.PRECHECK_INPUT_INVALID: " + str(exc)
        ) from exc
    if result["eligibility"] != "eligible":
        raise SystemExit(1)


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--request", required=True, help="显式 schema-bound JSON；不发现 latest evidence"
    )
    parser.add_argument(
        "--artifact-root",
        help="仅当 request 未内嵌 artifactRoot 时提供证据根；两者不可同时提供",
    )


def register_stable_production_proof_parsers(
    subparsers: argparse._SubParsersAction,
) -> None:
    stable = subparsers.add_parser(
        "stable-production-proof",
        help="只读 stdout 求值显式三 unit、十二 execution 稳产 proof request",
    )
    _common(stable)
    stable.set_defaults(handler=handle_stable_production_proof)

    precheck = subparsers.add_parser(
        "legacy-retirement-precheck",
        help="只读汇总稳产 proof 与 retirement inventory；绝不删除或改 state",
    )
    precheck.add_argument("--artifact-root")
    precheck.add_argument("--fingerprint")
    precheck.add_argument("--stable-proof-ref")
    precheck.add_argument("--stable-proof-digest")
    precheck.add_argument(
        "--output",
        help=(
            "可选 create-once 输出，必须位于 "
            ".qwq_output/data/local/runs/**；缺省只输出 stdout"
        ),
    )
    precheck.add_argument(
        "--retirement-inventory",
        default=RETIREMENT_INVENTORY_RELATIVE,
    )
    precheck.set_defaults(handler=handle_legacy_retirement_precheck)


__all__ = [
    "handle_legacy_retirement_precheck",
    "handle_stable_production_proof",
    "register_stable_production_proof_parsers",
]
