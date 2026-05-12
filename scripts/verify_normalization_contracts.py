#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "quwoquan_data" / "tools"))

from normalization.io_contracts import INPUT_SCHEMA_BY_STAGE, OUTPUT_SCHEMA_BY_STAGE, schema_path  # noqa: E402
from normalization.validators import load_schema  # noqa: E402


def main() -> int:
    missing: list[str] = []
    for filename in set(INPUT_SCHEMA_BY_STAGE.values()) | set(OUTPUT_SCHEMA_BY_STAGE.values()):
        path = schema_path(filename)
        if not path.exists():
            missing.append(str(path))
            continue
        try:
            load_schema(filename)
        except Exception as exc:  # pragma: no cover - contract gate
            print(f"FAIL: schema 非法 {path}: {exc}")
            return 1
    if missing:
        print("FAIL: normalization contracts 缺少 schema 文件")
        for item in missing:
            print(f"- {item}")
        return 1
    print("OK: normalization contracts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

