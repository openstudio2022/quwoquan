#!/usr/bin/env python3
"""生成川西冷启动 v2 batch_manifest.ndjson 与各 batch compose brief 输入。"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_ROOT))

from _common.io import write_ndjson  # noqa: E402
from _common.paths import batch_inputs_dir, task_root  # noqa: E402
from cold_start.chuanxi_catalog_v2 import (  # noqa: E402
    CHUANXI_V2_TASK_ID,
    ArticleSpec,
    build_all_article_specs,
    build_batch_manifest_rows,
)
from plan.brief import resolve_compose_brief, write_brief  # noqa: E402
from template.registry import TemplateRegistry  # noqa: E402
from template.router import RouteRequest  # noqa: E402


def spec_to_route_request(spec: ArticleSpec) -> RouteRequest:
    return RouteRequest(
        vertical="travel",
        subject_kind=spec.subject_kind,
        subject_type=spec.subject_type,
        intent=spec.intent,
        audience=spec.audience,
        region=spec.region,
        season=spec.season,
    )


def generate_manifest(task_id: str = CHUANXI_V2_TASK_ID) -> Path:
    rows = build_batch_manifest_rows()
    out = task_root(task_id) / "batch_manifest.ndjson"
    out.parent.mkdir(parents=True, exist_ok=True)
    write_ndjson(out, rows)
    return out


def generate_compose_briefs(task_id: str = CHUANXI_V2_TASK_ID) -> int:
    registry = TemplateRegistry.load()
    count = 0
    for spec in build_all_article_specs():
        brief = resolve_compose_brief(
            registry,
            spec_to_route_request(spec),
            title=spec.title,
            entity_refs=list(spec.entity_refs),
        )
        out = batch_inputs_dir(task_id, spec.batch, "produce", "compose") / f"{spec.ref}.json"
        write_brief(out, brief)
        count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate 川西冷启动_v2 manifest and compose briefs")
    parser.add_argument("--task", default=CHUANXI_V2_TASK_ID)
    parser.add_argument("--manifest-only", action="store_true")
    parser.add_argument("--briefs-only", action="store_true")
    args = parser.parse_args()

    specs = build_all_article_specs()
    print(f"[v2-manifest] article specs: {len(specs)}")
    print(f"[v2-manifest] by batch: {dict(Counter(s.batch for s in specs))}")

    if not args.briefs_only:
        manifest_path = generate_manifest(args.task)
        print(f"[v2-manifest] wrote {manifest_path}")

    if not args.manifest_only:
        brief_count = generate_compose_briefs(args.task)
        print(f"[v2-manifest] wrote {brief_count} compose brief inputs")


if __name__ == "__main__":
    main()
