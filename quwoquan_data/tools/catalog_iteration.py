"""
从已 hydrate 的 topics `source.md` 抽取 MediaWiki 风格内链 `[[标题]]`，合并入 article catalog NDJSON，
并可选择性调用 `crawl pool-bootstrap` 为新 topic 建池。

与 `/crawl` runtime 约定：`runs/{spec_id}/iteration_state.json` 记录轮次与稳定性。
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from common import RUNTIME_ROOT, now_iso, read_ndjson, read_yaml, write_json, write_ndjson

REPO_ROOT = Path(__file__).resolve().parents[2]
CLI_PATH = REPO_ROOT / "quwoquan_data" / "tools" / "cli.py"

MW_LINK = re.compile(r"\[\[([^\]#|]+)(?:\|[^\]]+)?\]\]")

GENERIC_TITLE_SKIP: frozenset[str] = frozenset(
    {
        "中国",
        "中华人民共和国",
        "中華人民共和國",
        "公园",
        "公園",
        "旅游",
        "旅遊",
        "旅行",
        "景区",
        "景區",
        "景点",
        "世界遺產",
        "世界遗产",
        "国家公园",
        "行政",
        "地理",
        "历史",
        "文化",
    }
)


def _norm_name(s: str) -> str:
    return s.strip().lower()


def source_md_paths(spec_id: str) -> list[Path]:
    root = RUNTIME_ROOT / "runs" / spec_id / "topics"
    if not root.is_dir():
        return []
    return sorted(root.glob("*/pages/*/source.md"))


def extract_titles_from_source_markdown(text: str) -> list[str]:
    titles: list[str] = []
    for m in MW_LINK.finditer(text):
        t = m.group(1).strip()
        if len(t) < 2:
            continue
        if t in GENERIC_TITLE_SKIP:
            continue
        titles.append(t)
    return titles


def propose_new_catalog_rows(spec_id: str, existing_names: set[str]) -> tuple[list[dict[str, Any]], set[str]]:
    """返回新行及对 existing_names 的增量（仅在调用方写入 catalog 时应用增量）。"""
    proposals: list[dict[str, Any]] = []
    round_seen: set[str] = set()
    found_names: set[str] = set()
    for md in source_md_paths(spec_id):
        try:
            text = md.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for title in extract_titles_from_source_markdown(text):
            key = _norm_name(title)
            if key in existing_names or key in round_seen:
                continue
            round_seen.add(key)
            tid = "iter_" + hashlib.sha256(title.encode("utf-8")).hexdigest()[:12]
            row: dict[str, Any] = {
                "topic_id": tid,
                "name": title,
                "wiki_title": title,
                "baike_item": title,
                "aliases": [],
                "core_tokens": [],
            }
            proposals.append(row)
            found_names.add(key)
    return proposals, found_names


def run_catalog_iteration(
    *,
    spec_path: Path,
    catalog_path: Path | None,
    max_rounds: int,
    stability_patience: int,
    dry_run: bool,
    skip_pool_bootstrap: bool,
) -> int:
    spec = read_yaml(spec_path)
    spec_id = str(spec.get("spec_id") or "").strip()
    if not spec_id:
        print("[catalog-iteration] FAIL: spec.spec_id 为空", file=sys.stderr)
        return 1

    cpath = catalog_path
    if cpath is None:
        cref = str(spec.get("article_topic_catalog_ref") or "").strip()
        if not cref:
            print(
                "[catalog-iteration] FAIL: 缺少 --catalog 且 spec.article_topic_catalog_ref 为空",
                file=sys.stderr,
            )
            return 1
        cpath = (RUNTIME_ROOT / cref).resolve()
    assert cpath is not None
    if not cpath.is_file():
        print(f"[catalog-iteration] FAIL: catalog 不存在 {cpath}", file=sys.stderr)
        return 1

    rows_in = read_ndjson(cpath)
    rows: list[dict[str, Any]] = [dict(r) for r in rows_in if isinstance(r, dict)]
    seen_names = {_norm_name(str(r.get("name") or "")) for r in rows if str(r.get("name") or "").strip()}
    seen_names.discard("")

    iteration_dir = RUNTIME_ROOT / "runs" / spec_id / "iteration"
    iteration_dir.mkdir(parents=True, exist_ok=True)
    state_path = iteration_dir / "iteration_state.json"
    spec_stem = spec_path.name if spec_path.is_file() else f"{spec_id}.yaml"

    if dry_run:
        proposals, _ = propose_new_catalog_rows(spec_id, set(seen_names))
        write_json(
            state_path,
            {
                "specId": spec_id,
                "round": 1,
                "newEntityCount": len(proposals),
                "emptyRoundStreak": 0,
                "generated_at": now_iso(),
                "catalogPath": str(cpath),
                "dryRun": True,
            },
        )
        print(
            f"[catalog-iteration] dry-run: would_add={len(proposals)} state={state_path}",
            file=sys.stderr,
        )
        return 0

    streak = 0

    for round_idx in range(1, max(1, max_rounds) + 1):
        proposals, new_keys = propose_new_catalog_rows(spec_id, seen_names)
        new_count = len(proposals)

        write_json(
            state_path,
            {
                "specId": spec_id,
                "round": round_idx,
                "newEntityCount": new_count,
                "emptyRoundStreak": streak,
                "generated_at": now_iso(),
                "catalogPath": str(cpath),
                "dryRun": dry_run,
            },
        )

        if new_count == 0:
            streak += 1
            print(
                f"[catalog-iteration] round={round_idx} new=0 streak={streak}/{stability_patience}",
                file=sys.stderr,
            )
            if streak >= max(1, stability_patience):
                print("[catalog-iteration] OK: 达到稳定停机条件", file=sys.stderr)
                return 0
            continue

        streak = 0
        print(f"[catalog-iteration] round={round_idx} new_entities={new_count}", file=sys.stderr)

        seen_names |= new_keys
        rows.extend(proposals)
        write_ndjson(cpath, rows)

        if not skip_pool_bootstrap and proposals:
            topic_arg = ",".join(p["topic_id"] for p in proposals[:120])
            cmd = [
                sys.executable,
                str(CLI_PATH),
                "crawl",
                "pool-bootstrap",
                "--spec",
                spec_stem,
                "--topics",
                topic_arg,
                "--merge",
            ]
            proc = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
            if proc.returncode != 0:
                print(proc.stderr or proc.stdout or "", file=sys.stderr)
                print(
                    f"[catalog-iteration] WARN: pool-bootstrap exit={proc.returncode}",
                    file=sys.stderr,
                )

    print("[catalog-iteration] OK: 已达 max_rounds", file=sys.stderr)
    return 0
