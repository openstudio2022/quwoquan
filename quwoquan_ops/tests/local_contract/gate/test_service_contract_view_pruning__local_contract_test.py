# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/repository-layout-hygiene-and-retirement/spec.md#gwt-002
"""契约视图缓存的自动回收契约。

每个调用方都往同一个 cache 目录写自己命名的视图，却没有任何一方负责回收。实测一台
开发机上积压到 291 个视图、174GB，而 `.qwq_output` 按 AGENTS.md 只应存放可删除、可
重建的运行输出。回收必须同时满足两件事：长期不膨胀，以及绝不删掉并发进程正在读的
目录 —— 后者是这类清理最容易写错的地方。
"""
from __future__ import annotations

from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

sys.path.insert(0, str(ROOT / "quwoquan_service" / "scripts" / "contracts"))

import build_service_contract_view as builder  # noqa: E402


def make_view(parent: Path, name: str, *, age_minutes: float) -> Path:
    view = parent / name
    view.mkdir(parents=True)
    (view / builder.PROVENANCE_FILENAME).write_text("{}", encoding="utf-8")
    stamp = time.time() - age_minutes * 60
    import os

    os.utime(view, (stamp, stamp))
    return view


def cache_dir(tmp_path: Path) -> Path:
    parent = tmp_path.joinpath(*builder.ENV_OUTPUT_PARTS, "service-contract-view", "cache")
    parent.mkdir(parents=True)
    return parent


def test_stale_views_beyond_the_retained_window_are_reclaimed(tmp_path: Path) -> None:
    parent = cache_dir(tmp_path)
    stale = [
        make_view(parent, f"view-{index}", age_minutes=600 + index)
        for index in range(builder.RETAINED_VIEWS + 5)
    ]
    current = make_view(parent, "view-current", age_minutes=0)

    removed = builder.prune_sibling_views(current)

    assert current.is_dir()
    assert len(removed) == 5
    survivors = {path for path in stale if path.is_dir()}
    assert len(survivors) == builder.RETAINED_VIEWS


def test_recent_views_are_never_reclaimed_even_beyond_the_count(tmp_path: Path) -> None:
    """并发保护：另一个进程刚写完的视图不能被删掉脚下。

    仅按个数裁剪会在 `make gate` 并行跑多个消费者时删掉别人正在读的目录，表现为
    随机的文件缺失，且极难复现。
    """
    parent = cache_dir(tmp_path)
    recent = [
        make_view(parent, f"view-{index}", age_minutes=1)
        for index in range(builder.RETAINED_VIEWS + 5)
    ]
    current = make_view(parent, "view-current", age_minutes=0)

    assert builder.prune_sibling_views(current) == []
    assert all(path.is_dir() for path in recent)


def test_directories_without_provenance_are_left_alone(tmp_path: Path) -> None:
    """没有 provenance 标记的目录不是契约视图，回收不得越界。"""
    parent = cache_dir(tmp_path)
    for index in range(builder.RETAINED_VIEWS + 3):
        make_view(parent, f"view-{index}", age_minutes=900)
    foreign = parent / "someone-elses-output"
    foreign.mkdir()
    (foreign / "payload.bin").write_text("keep me", encoding="utf-8")
    stamp = time.time() - 900 * 60
    import os

    os.utime(foreign, (stamp, stamp))
    current = make_view(parent, "view-current", age_minutes=0)

    builder.prune_sibling_views(current)

    assert foreign.is_dir()
    assert (foreign / "payload.bin").is_file()


def test_outputs_outside_the_runtime_output_root_are_never_touched(tmp_path: Path) -> None:
    """显式 --output 到 .qwq_output 之外时，那是调用方自己的目录，不归我们回收。"""
    parent = tmp_path / "external" / "cache"
    parent.mkdir(parents=True)
    stale = [make_view(parent, f"view-{index}", age_minutes=900) for index in range(20)]
    current = make_view(parent, "view-current", age_minutes=0)

    assert builder.prune_sibling_views(current) == []
    assert all(path.is_dir() for path in stale)
