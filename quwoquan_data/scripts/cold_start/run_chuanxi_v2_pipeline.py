#!/usr/bin/env python3
"""川西 v2 端到端重产：bootstrap → download → compose → materialize → verify → release。"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_ROOT))

from cold_start.bootstrap_chuanxi_v2_task import bootstrap_chuanxi_v2  # noqa: E402
from cold_start.chuanxi_catalog_v2 import CHUANXI_V2_RELEASE_ID, CHUANXI_V2_TASK_ID  # noqa: E402
from cold_start.chuanxi_v2_shared import GWT_REFS, V2_BATCHES  # noqa: E402
from cold_start.compose_chuanxi_v2_from_sources import compose_spec  # noqa: E402
from cold_start.seed_chuanxi_v2_download import seed_download  # noqa: E402
from cold_start.seed_pilots import _ensure_release_gate_stubs  # noqa: E402
from cold_start.chuanxi_catalog_v2 import build_all_article_specs  # noqa: E402
from cold_start.chuanxi_v2_shared import spec_by_ref  # noqa: E402
from produce.materialize import materialize_posts  # noqa: E402
from publish.assemble import assemble_release  # noqa: E402
from publish.gate import gate_publish  # noqa: E402
from _common.paths import batch_command_root, release_root  # noqa: E402
from verify_content_quality import verify_posts  # noqa: E402
from verify_content_semantics import verify_semantics  # noqa: E402
from download.gate import gate_download  # noqa: E402


def run_batch(task_id: str, batch_id: str, *, skip_bootstrap: bool = False) -> None:
    if not skip_bootstrap:
        bootstrap_chuanxi_v2()
    seed_download(task_id, batch_id, all_entities=(batch_id == "entity_intro"))
    dl_issues = gate_download(task_id, batch_id)
    if dl_issues:
        raise RuntimeError(f"download gate failed for {batch_id}: {dl_issues}")

    specs = [s for s in build_all_article_specs() if s.batch == batch_id]
    for spec in specs:
        compose_spec(spec, task_id)

    ct = "image" if batch_id == "images_p0" else "article"
    materialize_posts(task_id, batch_id, ct)

    posts_root = batch_command_root(task_id, batch_id, "produce") / "posts" / ct
    q_issues = verify_posts(posts_root)
    if q_issues:
        raise RuntimeError(f"content quality failed for {batch_id}: {q_issues[:5]}")
    s_issues = verify_semantics(posts_root, task_id, batch_id)
    if s_issues:
        raise RuntimeError(f"semantics failed for {batch_id}: {s_issues[:5]}")
    print(f"[pipeline-v2] batch={batch_id} OK")


def run_gwt(task_id: str) -> None:
    bootstrap_chuanxi_v2()
    batches = sorted({b for b, _, _ in GWT_REFS})
    for batch_id in batches:
        seed_download(task_id, batch_id, all_entities=(batch_id == "entity_intro"))
    for batch_id, content_type, ref in GWT_REFS:
        spec = spec_by_ref(ref)
        if spec is None:
            raise RuntimeError(f"missing spec for GWT ref {ref}")
        compose_spec(spec, task_id)
        materialize_posts(task_id, batch_id, content_type)
        posts_root = batch_command_root(task_id, batch_id, "produce") / "posts" / content_type / ref
        issues = verify_posts(posts_root) + verify_semantics(posts_root, task_id, batch_id)
        if issues:
            raise RuntimeError(f"GWT {ref} failed: {issues}")
    print("[pipeline-v2] GWT 6 samples OK")


def assemble_release_all(task_id: str) -> None:
    rel = release_root(CHUANXI_V2_RELEASE_ID)
    if rel.exists():
        shutil.rmtree(rel)
    assemble_release(task_id, CHUANXI_V2_RELEASE_ID)
    _ensure_release_gate_stubs(CHUANXI_V2_RELEASE_ID, task_id)
    issues = gate_publish(CHUANXI_V2_RELEASE_ID)
    if issues:
        raise RuntimeError(f"release gate failed: {issues}")
    print(f"[pipeline-v2] release={CHUANXI_V2_RELEASE_ID} assembled")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run 川西 v2 content pipeline")
    parser.add_argument("--batch", choices=V2_BATCHES)
    parser.add_argument("--all-batches", action="store_true")
    parser.add_argument("--gwt-only", action="store_true")
    parser.add_argument("--release", action="store_true")
    parser.add_argument("--skip-bootstrap", action="store_true")
    args = parser.parse_args()

    task_id = CHUANXI_V2_TASK_ID
    if args.gwt_only:
        run_gwt(task_id)
        if args.release:
            assemble_release_all(task_id)
        return

    if args.all_batches:
        for batch_id in V2_BATCHES:
            run_batch(task_id, batch_id, skip_bootstrap=(args.skip_bootstrap or batch_id != V2_BATCHES[0]))
        if args.release:
            assemble_release_all(task_id)
        return

    if args.batch:
        run_batch(task_id, args.batch, skip_bootstrap=args.skip_bootstrap)
        return

    parser.error("specify --batch, --all-batches, or --gwt-only")


if __name__ == "__main__":
    main()
