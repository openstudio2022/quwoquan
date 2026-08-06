"""Run the package-bound generic substitute conformance harness."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.provider_conformance.generic_protocol_substitute_conformance import (
    ConformanceBlocked,
    diagnostic_payload,
    emit_markers,
    execute_offline_local_contract,
    execute_supported_scenes,
    load_runtime_context,
)


def _write_diagnostic(payload: dict[str, object]) -> None:
    result_ref = os.environ.get("QWQ_PROVIDER_CONFORMANCE_RESULT_PATH", "").strip()
    if not result_ref:
        return
    result_path = Path(result_ref)
    if not result_path.parent.is_dir():
        return
    path = result_path.with_name(f"{result_path.stem}.generic-protocol-diagnostic.json")
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    try:
        if os.environ.get("QWQ_PROVIDER_CONFORMANCE_LAYER", "").strip() == "local_contract":
            execute_offline_local_contract()
            return 0
        context = load_runtime_context()
        run = execute_supported_scenes(context)
        _write_diagnostic(diagnostic_payload(context, run))
        emit_markers(
            run,
            expected_assertions=tuple(
                json.loads(os.environ["QWQ_PROVIDER_CONFORMANCE_ASSERTION_IDS"])
            ),
        )
    except (ConformanceBlocked, OSError, RuntimeError, ValueError) as exc:
        print(f"generic_provider_conformance: GATE_BLOCK: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
