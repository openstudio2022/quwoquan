#!/usr/bin/env python3
"""校验地理目录候选层质量。"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

REPO_ROOT = Path(os.getenv("QWQ_REPO_ROOT", Path(__file__).resolve().parents[1])).resolve()
DATA_ROOT = Path(os.getenv("QWQ_DATA_ROOT", REPO_ROOT / "quwoquan_data")).resolve()
RUNTIME_ROOT = Path(os.getenv("QWQ_RUNTIME_ROOT", DATA_ROOT / "runtime")).resolve()
SEED_ROOT = RUNTIME_ROOT / "seed"
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_ASCII_SLOGAN_RE = re.compile(r"\bI\s*LOVE\b", re.I)
_MILITARY_EXHIBIT_RE = re.compile(r"^(歼|轰|运|米格|强击|战斗机|教练机|F|B|J|Y|H)[A-Za-z0-9\-]*\d+[A-Za-z0-9\-]*$")


def read_ndjson(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def has_cjk(value: str) -> bool:
    return bool(_CJK_RE.search(str(value or "")))


def looks_bad_name(name: str) -> str:
    stripped = str(name or "").strip()
    if not stripped:
        return "empty_name"
    if stripped in {"卐", "卍"}:
        return "banned_symbol"
    if _ASCII_SLOGAN_RE.search(stripped):
        return "ascii_slogan"
    if _MILITARY_EXHIBIT_RE.fullmatch(stripped):
        return "military_exhibit"
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="校验 geo catalog 质量")
    parser.add_argument("--catalog", default="", help="单个 catalog NDJSON；省略则扫描 runtime/seed")
    parser.add_argument("--report", default="", help="单个 slice report JSON")
    parser.add_argument(
        "--min-rows",
        type=int,
        default=0,
        help="NDJSON 行数下限（0=不检查）；按每个 catalog 文件分别校验",
    )
    parser.add_argument(
        "--min-kept",
        type=int,
        default=0,
        help="slice report 的 keptCount 下限（0=不检查）；需存在 report 且含 keptCount",
    )
    args = parser.parse_args()

    catalog_paths: list[Path]
    if str(args.catalog or "").strip():
        catalog_paths = [Path(args.catalog).resolve()]
    else:
        catalog_paths = sorted(SEED_ROOT.glob("*_catalog.ndjson"))
    if not catalog_paths:
        print("OK: geo catalog quality (no catalog files, skipped)")
        return 0

    errors: list[str] = []
    min_rows = int(getattr(args, "min_rows", 0) or 0)
    min_kept = int(getattr(args, "min_kept", 0) or 0)
    for catalog_path in catalog_paths:
        rows = read_ndjson(catalog_path)
        if min_rows > 0 and len(rows) < min_rows:
            errors.append(f"{catalog_path}: 行数 {len(rows)} < --min-rows {min_rows}")
        seen_ids: set[str] = set()
        for index, row in enumerate(rows, start=1):
            topic_id = str(row.get("topic_id") or "").strip()
            if not topic_id:
                errors.append(f"{catalog_path}:{index}: 缺少 topic_id")
                continue
            if topic_id in seen_ids:
                errors.append(f"{catalog_path}:{index}: 重复 topic_id {topic_id}")
            seen_ids.add(topic_id)

            name = str(row.get("name") or "").strip()
            bad_name = looks_bad_name(name)
            if bad_name:
                errors.append(f"{catalog_path}:{index}: 非法 name({bad_name}) {name}")

            display_locale = str(row.get("display_locale") or "zh").strip() or "zh"
            label_zh = str(row.get("label_zh") or "").strip()
            if display_locale != "en" and not label_zh:
                errors.append(f"{catalog_path}:{index}: display_locale={display_locale} 但缺少 label_zh")
            if display_locale != "en" and label_zh and not has_cjk(label_zh):
                errors.append(f"{catalog_path}:{index}: label_zh 非中文主标签 {label_zh}")

            entity_type_label_zh = str(row.get("entity_type_label_zh") or "").strip()
            if not entity_type_label_zh:
                errors.append(f"{catalog_path}:{index}: 缺少 entity_type_label_zh")

            tag_refs = row.get("tagRefs") or []
            if not isinstance(tag_refs, list) or not [x for x in tag_refs if str(x).strip()]:
                errors.append(f"{catalog_path}:{index}: 缺少 tagRefs")

            if "authority_status" not in row:
                errors.append(f"{catalog_path}:{index}: 缺少 authority_status")

        report_path = Path(args.report).resolve() if str(args.report or "").strip() else catalog_path.with_suffix(".slice_report.json")
        if report_path.exists():
            report = read_json(report_path)
            if min_kept > 0:
                kr = report.get("keptCount")
                if kr is None:
                    errors.append(f"{report_path}: 缺少 keptCount，无法校验 --min-kept {min_kept}")
                elif int(kr) < min_kept:
                    errors.append(
                        f"{report_path}: keptCount={kr} < --min-kept {min_kept}（catalog 行数 {len(rows)}）"
                    )
            slices = report.get("slices") or []
            if not isinstance(slices, list) or not slices:
                errors.append(f"{report_path}: 缺少 slices")
            for slice_row in slices:
                if not isinstance(slice_row, dict):
                    errors.append(f"{report_path}: 存在非法 slice 行")
                    continue
                slice_name = str(slice_row.get("sliceName") or "").strip()
                if not slice_name:
                    errors.append(f"{report_path}: slice 缺少 sliceName")
                if "rawCount" not in slice_row:
                    errors.append(f"{report_path}: slice {slice_name} 缺少 rawCount")
                if "areaProbeCount" not in slice_row:
                    errors.append(f"{report_path}: slice {slice_name} 缺少 areaProbeCount")
        else:
            errors.append(f"{catalog_path}: 缺少对应 slice report {report_path}")

    if errors:
        print("FAIL: geo catalog quality gate")
        for error in errors[:120]:
            print(f"- {error}")
        if len(errors) > 120:
            print(f"... and {len(errors) - 120} more")
        return 1

    print("OK: geo catalog quality gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
