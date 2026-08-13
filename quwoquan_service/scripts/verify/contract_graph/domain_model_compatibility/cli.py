"""Compare a candidate ContractGraph with the last immutable Prod-full graph.

The gate deliberately keeps model versions out of the wire.  ``model_version``
is read only from each object-local ``object.yaml`` document embedded in the
ContractGraph; when absent, the initial version is ``1.0``.  The tool computes
the required version and reports a mismatch, but never rewrites authoring
sources.

Exit codes:
  0: the compatibility gate passed;
  1: input/evidence is malformed;
  2: the candidate is well formed but release-blocked.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from .evidence import _load_migration_plan, _load_window, _validate_baseline_receipt
from .graph_view import GraphView
from .primitives import InputError, _read_json
from .report import _write_report, build_report


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-receipt", required=True, type=Path)
    parser.add_argument("--baseline-graph", required=True, type=Path)
    parser.add_argument("--current-graph", required=True, type=Path)
    parser.add_argument("--compatibility-window", type=Path)
    parser.add_argument("--storage-migration-plan", type=Path)
    parser.add_argument("--report", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        baseline_graph = GraphView.load(args.baseline_graph)
        current_graph = GraphView.load(args.current_graph)
        readback = _read_json(args.baseline_receipt)
        receipt = _validate_baseline_receipt(readback, baseline_graph.digest)
        window, window_digest = _load_window(
            args.compatibility_window, baseline_graph.digest
        )
        migrations, migration_digest = _load_migration_plan(
            args.storage_migration_plan, current_graph.digest
        )
        report = build_report(
            baseline_graph,
            current_graph,
            receipt,
            window,
            window_digest,
            migrations,
            migration_digest,
        )
        _write_report(args.report, report)
    except InputError as error:
        print(f"GATE_BLOCK input: {error}", file=sys.stderr)
        return 1
    if report["status"] != "passed":
        print(
            f"GATE_BLOCK compatibility: {len(report['issues'])} issue(s); report={args.report}",
            file=sys.stderr,
        )
        return 2
    print(f"PASS domain model compatibility: report={args.report}")
    return 0
