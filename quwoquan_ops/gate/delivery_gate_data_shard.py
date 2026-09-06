#!/usr/bin/env python3
"""Delivery Gate 的 data `local_contract` 分片选择面。

分片由测试文件仓内相对路径的稳定摘要取模决定，不维护分片清单。写死清单时新增的
测试文件会落在所有片之外——每一片都判它「不属于我」，于是谁都不跑它，而每一片
仍然全绿。摘要取模让新文件必然落进恰好一片。
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
#: 每个受管测试树的 local_contract 根；默认 data 保持既有 gate_repo.sh 调用不变。
TEST_ROOTS = {
    "data": ("quwoquan_data", "tests", "local_contract"),
    "ops": ("quwoquan_ops", "tests", "local_contract"),
}
TEST_ROOT_PARTS = TEST_ROOTS["data"]
TEST_FILE_SUFFIX = "_local_contract_test.py"


def local_contract_test_files(repo_root: Path, scope: str = "data") -> list[str]:
    """指定 scope 下 `local_contract` 全部测试文件的仓内相对路径，字典序。"""
    test_root = repo_root.joinpath(*TEST_ROOTS[scope])
    return sorted(
        path.relative_to(repo_root).as_posix()
        for path in test_root.rglob("*" + TEST_FILE_SUFFIX)
    )


def shard_of(relative_path: str, total_shards: int) -> int:
    """测试文件所属分片下标。只取路径，因此与收集顺序和文件系统枚举顺序无关。"""
    digest = hashlib.sha256(relative_path.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % total_shards


def sharded_test_files(
    repo_root: Path, total_shards: int, shard_index: int, scope: str = "data",
) -> list[str]:
    files = local_contract_test_files(repo_root, scope)
    if total_shards == 1:
        return files
    return [path for path in files if shard_of(path, total_shards) == shard_index]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="列出属于指定分片的 local_contract 测试文件",
    )
    parser.add_argument(
        "--scope", choices=sorted(TEST_ROOTS), default="data",
        help="受管测试树；默认 data 保持既有调用不变",
    )
    parser.add_argument(
        "--total-shards",
        type=int,
        default=1,
        help="分片总数；1 表示不分片，列出全集",
    )
    parser.add_argument("--shard-index", type=int, default=0, help="分片下标，从 0 起")
    args = parser.parse_args(argv)

    if args.total_shards < 1:
        print(
            f"[data-shard] FAIL: --total-shards 必须 >= 1，收到 {args.total_shards}",
            file=sys.stderr,
        )
        return 2
    if not 0 <= args.shard_index < args.total_shards:
        print(
            f"[data-shard] FAIL: --shard-index 必须落在 [0, {args.total_shards})，"
            f"收到 {args.shard_index}",
            file=sys.stderr,
        )
        return 2

    selected = sharded_test_files(ROOT, args.total_shards, args.shard_index, args.scope)
    if not selected:
        print(
            f"[{args.scope}-shard] FAIL: 分片 {args.shard_index}/{args.total_shards} 为空——"
            "分片数超过测试文件数时该片没有任何判据可跑",
            file=sys.stderr,
        )
        return 2
    print("\n".join(selected))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
