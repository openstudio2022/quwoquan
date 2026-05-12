#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "quwoquan_data" / "tools"))

from common import read_ndjson  # noqa: E402
from normalization.io_contracts import (  # noqa: E402
    compiled_dir,
    entity_resolution_path,
    image_resolution_path,
    pending_resolution_path,
    source_resolution_path,
    stage_results_dir,
)
from normalization.validators import validate_output_file, validate_payload_against_schema  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="校验 normalization 批次输出")
    parser.add_argument("--batch-label", required=True)
    args = parser.parse_args()

    batch_label = str(args.batch_label).strip()
    errors: list[str] = []
    for stage in ("fetch", "extract", "review", "authority", "escalate"):
        result_dir = stage_results_dir(batch_label, stage)
        if not result_dir.exists():
            continue
        for path in sorted(result_dir.glob("*.json")):
            try:
                validate_output_file(stage, path)
            except Exception as exc:
                errors.append(f"{path}: {exc}")
    compiled = {
        "entity": (entity_resolution_path(batch_label), "entity_resolution_record.schema.json"),
        "image": (image_resolution_path(batch_label), "image_resolution_record.schema.json"),
    }
    for _, (path, schema_name) in compiled.items():
        if not path.exists():
            continue
        for index, row in enumerate(read_ndjson(path), start=1):
            try:
                validate_payload_against_schema(row, schema_name)
            except Exception as exc:
                errors.append(f"{path}:{index}: {exc}")
    for path in (source_resolution_path(batch_label), pending_resolution_path(batch_label), compiled_dir(batch_label) / "trace"):
        if isinstance(path, Path) and path.is_dir():
            continue
    if errors:
        print("FAIL: normalization outputs")
        for item in errors[:120]:
            print(f"- {item}")
        if len(errors) > 120:
            print(f"... and {len(errors) - 120} more")
        return 1
    print("OK: normalization outputs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

