#!/usr/bin/env python3
"""Verify governance admission evaluator and report current fail-closed terminal."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "quwoquan_ops/cli"))
sys.path.insert(0, str(ROOT))

from lib.governance_pipeline_admission import (  # noqa: E402
    contract_failure,
    current_repository_input,
    inspect,
    load_contract,
)


def _detail(error: BaseException) -> str:
    return " ".join(str(error).replace("\x00", "\\x00").split()) or type(error).__name__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--evidence-bundle",
        help="canonical bundle under .qwq_output/env/repo/runs/governance-pipeline/**",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        contract = load_contract()
    except Exception as error:
        terminal = contract_failure(_detail(error))
        print(
            "[governance-pipeline-admission] GATE_BLOCK: "
            f"code={terminal['error_code']} terminal={terminal['terminal']} "
            f"recovery={terminal['recovery']} detail={terminal['detail']}",
            file=sys.stderr,
        )
        return 1
    if args.evidence_bundle is None:
        boundaries = contract["authority_boundaries"]
        if any(boundaries.get(field) is not False for field in (
            "evaluator_mutation", "creates_authority", "production_ready_claim",
            "commercial_ready_claim", "hotl_admitted_claim", "prod_mutation", "hotl_mutation",
        )) or contract["admission_policy"]["current_max_write_concurrency"] > 1:
            print("[governance-pipeline-admission] GATE_BLOCK: evaluator safety contract drifted", file=sys.stderr)
            return 1
        print(
            "[governance-pipeline-admission] EVALUATOR_SELF_CHECK_ONLY_NON_ADMISSION: "
            "no bundle supplied; safety shape verified, no evidence admission was evaluated"
        )
        return 0
    try:
        result = inspect(current_repository_input(contract, evidence_bundle=args.evidence_bundle))
    except Exception as error:
        print(
            "[governance-pipeline-admission] GATE_BLOCK: "
            f"code=GPA.INPUT_CONTRACT_INVALID terminal=blocked detail={_detail(error)}",
            file=sys.stderr,
        )
        return 1
    if result["status"] == "blocked":
        print(
            "[governance-pipeline-admission] GATE_BLOCK: "
            f"code={result['error_code']} terminal=blocked first_blocker={result['blockers'][0]} "
            f"all_blockers={','.join(result['blockers'])} detail={result['detail']}",
            file=sys.stderr,
        )
        return 1
    if result["status"] != "not_admitted" or result["allowed_mode"] != "manual":
        print("[governance-pipeline-admission] GATE_BLOCK: current Story bundle must remain exact not_admitted/manual without authenticated activation", file=sys.stderr)
        return 1
    if any(result[field] is not False for field in (
        "production_ready", "commercial_ready", "hotl_admitted", "mutation_allowed",
        "prod_mutation_allowed", "hotl_mutation_allowed",
    )) or result["max_write_concurrency"] > 1:
        print("[governance-pipeline-admission] GATE_BLOCK: zero-authority safety projection drifted", file=sys.stderr)
        return 1
    print(
        f"[governance-pipeline-admission] EXPECTED_NOT_ADMITTED: status={result['status']} "
        f"mode={result['allowed_mode']} first_blocker={result['blockers'][0]} "
        f"all_blockers={','.join(result['blockers'])}"
    )
    print(
        "[governance-pipeline-admission] BUNDLE_VERIFIED_EXPECTED_FAIL_CLOSED: exit=0 validates exact bundle non-admission only; "
        "production/commercial/HOTL claims remain false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
