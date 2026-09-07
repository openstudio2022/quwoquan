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


#: lane 门禁在 ubuntu-latest 上无法执行的 ops 合同（缺 macOS/Flutter/Go/证书等宿主能力）。
#: 声明式、文件级、只减不增；gate_repo.sh 全量执行时不读取它。
LANE_GATE_OPS_EXCLUSIONS = Path("quwoquan_ops/policies/gates/lane_gate_ops_contract_exclusions.yaml")


def lane_gate_excluded_files(repo_root: Path) -> frozenset[str]:
    """读取 lane 门禁的 ops 合同排除清单；每条必须指向真实文件并声明缺失的宿主能力。"""
    import yaml

    path = repo_root / LANE_GATE_OPS_EXCLUSIONS
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    entries = payload.get("exclusions") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        raise ValueError(f"{LANE_GATE_OPS_EXCLUSIONS}: exclusions 必须是列表")
    excluded: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or set(entry) != {"path", "missing_host_capability"}:
            raise ValueError(f"{LANE_GATE_OPS_EXCLUSIONS}: exclusions[{index}] 字段必须恰为 path + missing_host_capability")
        relative = str(entry["path"])
        if not relative.startswith("quwoquan_ops/tests/local_contract/") or not relative.endswith(TEST_FILE_SUFFIX):
            raise ValueError(f"{LANE_GATE_OPS_EXCLUSIONS}: {relative} 不是 ops local_contract 测试文件路径")
        if not (repo_root / relative).is_file():
            raise ValueError(f"{LANE_GATE_OPS_EXCLUSIONS}: {relative} 不存在；排除清单只能指向真实文件")
        if not str(entry["missing_host_capability"]).strip():
            raise ValueError(f"{LANE_GATE_OPS_EXCLUSIONS}: {relative} 缺 missing_host_capability")
        if relative in excluded:
            raise ValueError(f"{LANE_GATE_OPS_EXCLUSIONS}: {relative} 重复登记")
        excluded.add(relative)
    return frozenset(excluded)


def local_contract_test_files(
    repo_root: Path, scope: str = "data", *, lane_gate: bool = False,
) -> list[str]:
    """指定 scope 下 `local_contract` 全部测试文件的仓内相对路径，字典序。

    `lane_gate=True` 时按声明式排除清单去掉 ubuntu-latest 无法执行的 ops 合同；
    只对 ops scope 有意义，data scope 不接受该开关。
    """
    if lane_gate and scope != "ops":
        raise ValueError("lane_gate 排除只适用于 ops scope")
    test_root = repo_root.joinpath(*TEST_ROOTS[scope])
    files = sorted(
        path.relative_to(repo_root).as_posix()
        for path in test_root.rglob("*" + TEST_FILE_SUFFIX)
    )
    if not lane_gate:
        return files
    excluded = lane_gate_excluded_files(repo_root)
    return [path for path in files if path not in excluded]


def shard_of(relative_path: str, total_shards: int) -> int:
    """测试文件所属分片下标。只取路径，因此与收集顺序和文件系统枚举顺序无关。"""
    digest = hashlib.sha256(relative_path.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % total_shards


def sharded_test_files(
    repo_root: Path, total_shards: int, shard_index: int, scope: str = "data",
    *, lane_gate: bool = False,
) -> list[str]:
    files = local_contract_test_files(repo_root, scope, lane_gate=lane_gate)
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
    parser.add_argument(
        "--lane-gate", action="store_true",
        help="按 lane_gate_ops_contract_exclusions.yaml 排除 ubuntu-latest 无法执行的 ops 合同（仅 --scope ops）",
    )
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

    try:
        selected = sharded_test_files(
            ROOT, args.total_shards, args.shard_index, args.scope, lane_gate=args.lane_gate,
        )
    except ValueError as error:
        print(f"[{args.scope}-shard] FAIL: {error}", file=sys.stderr)
        return 2
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
