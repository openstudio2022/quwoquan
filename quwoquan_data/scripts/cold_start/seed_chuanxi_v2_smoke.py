#!/usr/bin/env python3
"""川西 v2 模版化 smoke（仅 pipeline 联调，非可发布终稿）。

正常内容生产请使用 run_chuanxi_v2_pipeline.py。
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_ROOT))

from cold_start.bootstrap_chuanxi_v2_task import bootstrap_chuanxi_v2  # noqa: E402
from cold_start.chuanxi_catalog_v2 import CHUANXI_V2_RELEASE_ID, CHUANXI_V2_TASK_ID, build_all_article_specs  # noqa: E402
from cold_start.chuanxi_v2_shared import V2_BATCHES  # noqa: E402
from cold_start.compose_chuanxi_v2_from_sources import compose_spec  # noqa: E402
from cold_start.seed_chuanxi_v2_download import seed_download  # noqa: E402
from cold_start.seed_pilots import _ensure_release_gate_stubs  # noqa: E402
from produce.materialize import materialize_posts  # noqa: E402
from publish.assemble import assemble_release  # noqa: E402
from publish.gate import gate_publish  # noqa: E402
from _common.paths import release_root  # noqa: E402


def seed_chuanxi_v2_smoke(dry_run: bool = False) -> int:
    """Smoke = bootstrap + stub download + compose-from-sources + release（与终稿同路径，可过形式门禁）。"""
    count = bootstrap_chuanxi_v2(dry_run=dry_run)
    if dry_run:
        return count

    for batch_id in V2_BATCHES:
        seed_download(CHUANXI_V2_TASK_ID, batch_id, all_entities=(batch_id == "entity_intro"))
        for spec in build_all_article_specs():
            if spec.batch != batch_id:
                continue
            compose_spec(spec, CHUANXI_V2_TASK_ID)
        ct = "image" if batch_id == "images_p0" else "article"
        materialize_posts(CHUANXI_V2_TASK_ID, batch_id, ct)

    rel_root = release_root(CHUANXI_V2_RELEASE_ID)
    if rel_root.exists():
        shutil.rmtree(rel_root)
    assemble_release(CHUANXI_V2_TASK_ID, CHUANXI_V2_RELEASE_ID)
    _ensure_release_gate_stubs(CHUANXI_V2_RELEASE_ID, CHUANXI_V2_TASK_ID)
    issues = gate_publish(CHUANXI_V2_RELEASE_ID)
    if issues:
        raise RuntimeError(f"smoke release gate failed: {issues}")
    print(f"[smoke-v2] release={CHUANXI_V2_RELEASE_ID} posts={count}")
    return count


if __name__ == "__main__":
    n = seed_chuanxi_v2_smoke(dry_run="--dry-run" in sys.argv)
    sys.exit(0 if n else 1)
