#!/usr/bin/env python3
"""阻止预制长文重新使用 articleDocument 作为内容真相源。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
DATA_ROOT = Path(os.getenv("QWQ_DATA_ROOT", ROOT / "quwoquan_data")).resolve()
RUNTIME_ROOT = Path(os.getenv("QWQ_RUNTIME_ROOT", DATA_ROOT / "runtime")).resolve()
SCAN_ROOTS = [
    ROOT / "quwoquan_service/contracts/metadata/content/test_fixtures/scenarios",
    RUNTIME_ROOT / "publish",
    RUNTIME_ROOT / "out",
]


def iter_json_payloads(path: Path) -> list[tuple[str, Any]]:
    if path.suffix == ".ndjson":
        rows: list[tuple[str, Any]] = []
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if line.strip():
                rows.append((f"{path}:{index}", json.loads(line)))
        return rows
    return [(str(path), json.loads(path.read_text(encoding="utf-8")))]


def is_article_post_payload(value: dict[str, Any]) -> bool:
    return value.get("contentType") == "article" and any(
        field in value
        for field in (
            "type",
            "sourcePostId",
            "authorId",
            "articleRenderProfile",
            "articleDocument",
        )
    )


def walk(value: Any, location: str, failures: list[str]) -> None:
    if isinstance(value, dict):
        if is_article_post_payload(value):
            if "articleDocument" in value:
                failures.append(f"{location}: article contains articleDocument")
            if not str(value.get("articleMarkdown", "")).strip():
                failures.append(f"{location}: article missing articleMarkdown")
            if not isinstance(value.get("articleRenderProfile"), dict):
                failures.append(f"{location}: article missing articleRenderProfile")
        for key, child in value.items():
            walk(child, f"{location}.{key}", failures)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            walk(child, f"{location}[{index}]", failures)


def main() -> int:
    failures: list[str] = []
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if path.suffix not in {".json", ".ndjson"}:
                continue
            for location, payload in iter_json_payloads(path):
                walk(payload, location, failures)
    if failures:
        print("FAIL: Markdown article articleDocument gate")
        for failure in failures[:80]:
            print(f"- {failure}")
        if len(failures) > 80:
            print(f"... and {len(failures) - 80} more")
        return 1
    print("OK: Markdown article articleDocument gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
