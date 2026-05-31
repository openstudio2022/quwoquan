#!/usr/bin/env python3
"""为川西 v2 batch 写入 gate_download 合规的 curated sources。"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_ROOT))

from _common.paths import batch_command_root, ensure_batch_layout, ensure_task_layout  # noqa: E402
from cold_start.chuanxi_catalog_v2 import CHUANXI_V2_ALL_ENTITIES, CHUANXI_V2_TASK_ID  # noqa: E402
from cold_start.chuanxi_v2_shared import V2_BATCHES, entities_for_batch  # noqa: E402
from cold_start.chuanxi_v2_source_corpus import curated_sources_for_entity, source_frontmatter  # noqa: E402
from cold_start.seed_chuanxi_batch import _seed_entity_images  # noqa: E402
from download.gate import gate_download  # noqa: E402


def seed_download(task_id: str, batch_id: str, *, all_entities: bool = False) -> list[str]:
    ensure_task_layout(task_id)
    ensure_batch_layout(task_id, batch_id, "download")

    if all_entities or batch_id == "entity_intro":
        names = {row["name"] for row in CHUANXI_V2_ALL_ENTITIES}
    else:
        names = entities_for_batch(batch_id)

    entity_index = {row["name"]: i for i, row in enumerate(CHUANXI_V2_ALL_ENTITIES)}
    sources_root = batch_command_root(task_id, batch_id, "download") / "sources"
    sources_root.mkdir(parents=True, exist_ok=True)
    for stale in sources_root.iterdir():
        if stale.is_dir() and stale.name not in names:
            shutil.rmtree(stale)

    for name in sorted(names):
        ent_dir = batch_command_root(task_id, batch_id, "download") / "sources" / name
        for source in curated_sources_for_entity(name):
            src_dir = ent_dir / source["source_id"]
            src_dir.mkdir(parents=True, exist_ok=True)
            (src_dir / "source.md").write_text(
                source_frontmatter(source, name), encoding="utf-8"
            )
        idx = entity_index.get(name, 0)
        _seed_entity_images(task_id, batch_id, name, idx, 5)

    return sorted(names)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed curated download sources for 川西 v2")
    parser.add_argument("--task", default=CHUANXI_V2_TASK_ID)
    parser.add_argument("--batch", choices=V2_BATCHES)
    parser.add_argument("--all-batches", action="store_true")
    parser.add_argument("--all-entities", action="store_true")
    args = parser.parse_args()

    batches = list(V2_BATCHES) if args.all_batches else [args.batch]
    if not batches or batches == [None]:
        parser.error("specify --batch or --all-batches")

    for batch_id in batches:
        names = seed_download(args.task, batch_id, all_entities=args.all_entities)
        issues = gate_download(args.task, batch_id)
        if issues:
            print(f"[download-v2] batch={batch_id} FAILED: {issues}", file=sys.stderr)
            sys.exit(1)
        print(f"[download-v2] batch={batch_id} entities={len(names)} gate=PASS")

    print("[download-v2] done")


if __name__ == "__main__":
    main()
