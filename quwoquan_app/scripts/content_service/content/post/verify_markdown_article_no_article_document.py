#!/usr/bin/env python3
"""校验长文真相源：wire 内嵌 Markdown，数据对象使用同目录 article.md。"""

from __future__ import annotations


import sys
from pathlib import Path

sys.dont_write_bytecode = True

_SCRIPTS_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "scripts" and (parent / "_common" / "paths.py").is_file()
)
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from _common.paths import APP_ROOT, REPO_ROOT, SCRIPTS_ROOT

import json
import os
from pathlib import Path
from typing import Any


ROOT = REPO_ROOT
DATA_ROOT = Path(os.getenv("QWQ_DATA_ROOT", ROOT / "quwoquan_data")).resolve()
OUTPUT_ROOT = Path(os.getenv("QWQ_OUTPUT_ROOT", ROOT / ".qwq_output")).resolve()
PUBLISH_ROOT = Path(os.getenv("QWQ_PUBLISH_ROOT", DATA_ROOT / "publish")).resolve()
SCAN_ROOTS = [
    ROOT / "quwoquan_service/services/content-service/tests/support/contract_fixtures/scenarios",
    PUBLISH_ROOT,
    OUTPUT_ROOT / "data" / "tasks",
    OUTPUT_ROOT / "data" / "releases",
]


def iter_json_payloads(path: Path) -> list[tuple[str, Any]]:
    if path.suffix == ".ndjson":
        rows: list[tuple[str, Any]] = []
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if line.strip():
                rows.append((f"{path}:{index}", json.loads(line)))
        return rows
    return [(str(path), json.loads(path.read_text(encoding="utf-8")))]


DATA_POST_SCHEMAS = {
    "quwoquan_data.post_manifest",
    "quwoquan_data.post_object",
}


def is_article(value: dict[str, Any]) -> bool:
    return value.get("contentType") == "article"


def is_embedded_article_post(value: dict[str, Any]) -> bool:
    """识别 Content Service wire/fixture，排除数据任务 envelope。"""
    if not is_article(value) or value.get("schema") in DATA_POST_SCHEMAS:
        return False
    return bool(
        str(value.get("postId") or value.get("sourcePostId") or "").strip()
        or (
            value.get("type") == "article"
            and str(value.get("id") or "").strip()
        )
    )


def validate_article(
    value: dict[str, Any],
    *,
    location: str,
    source_path: Path,
    is_document_root: bool,
) -> list[str]:
    if not is_article(value):
        return []

    failures: list[str] = []
    if "articleDocument" in value:
        failures.append(f"{location}: article contains articleDocument")

    schema = value.get("schema")
    if is_document_root and schema in DATA_POST_SCHEMAS:
        if source_path.name != "manifest.json":
            failures.append(f"{location}: data article must use manifest.json")
        article_path = source_path.with_name("article.md")
        if not article_path.is_file() or not article_path.read_text(
            encoding="utf-8"
        ).strip():
            failures.append(f"{location}: data article missing non-empty article.md")
        if schema == "quwoquan_data.post_object" and value.get(
            "finalContentRef"
        ) != "article.md":
            failures.append(
                f"{location}: canonical article finalContentRef must be article.md"
            )
        if not isinstance(value.get("articleRenderProfile"), dict):
            failures.append(f"{location}: article missing articleRenderProfile")
    elif is_embedded_article_post(value):
        if not str(value.get("articleMarkdown", "")).strip():
            failures.append(f"{location}: article missing articleMarkdown")
        if not isinstance(value.get("articleRenderProfile"), dict):
            failures.append(f"{location}: article missing articleRenderProfile")
    return failures


def walk(
    value: Any,
    location: str,
    source_path: Path,
    failures: list[str],
    *,
    is_document_root: bool = False,
) -> None:
    if isinstance(value, dict):
        failures.extend(
            validate_article(
                value,
                location=location,
                source_path=source_path,
                is_document_root=is_document_root,
            )
        )
        for key, child in value.items():
            walk(child, f"{location}.{key}", source_path, failures)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            walk(child, f"{location}[{index}]", source_path, failures)


def main() -> int:
    failures: list[str] = []
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if path.suffix not in {".json", ".ndjson"}:
                continue
            for location, payload in iter_json_payloads(path):
                walk(
                    payload,
                    location,
                    path,
                    failures,
                    is_document_root=True,
                )
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
