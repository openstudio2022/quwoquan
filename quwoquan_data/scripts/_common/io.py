"""JSON / NDJSON IO utilities."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any, *, indent: int = 2) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)
        f.write("\n")


def read_ndjson(path: Path) -> list[dict]:
    rows: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_ndjson(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_assistant_task(path: Path, *, step: str, input_dir: Path, result_dir: Path, refs: list[str]) -> None:
    """Write an assistant_tasks manifest pointing to inputs and expected result location."""
    manifest = {
        "step": step,
        "inputDir": str(input_dir),
        "resultDir": str(result_dir),
        "refs": refs,
        "totalItems": len(refs),
    }
    write_json(path, manifest)
