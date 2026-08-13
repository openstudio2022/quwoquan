#!/usr/bin/env python3
"""
助手 / App 搜索弱类型只减不增门禁。

口径（手写助手，排除生成体目录）：
  - bucket assistant_handwritten: quwoquan_app/lib/service/assistant_service/**/*.dart
    排除 **/assistant/generated/** 与 *.g.dart
  - bucket core_search_repository: 单文件 search_repository.dart

指标（每个 bucket，与基线比较，三者互不重叠）：
  - map_string_dynamic: `Map<String, dynamic>` 站点数
  - map_string_object_optional: `Map<String, Object?>` 站点数
  - bare_dynamic: 不属于上述 Map 的独立 `dynamic` 站点数（形参、返回值、
    字段、泛型实参）

为什么 `Map<String, Object?>` 也是棘轮桶而不是目标形态：`Object?` 只把 value
的静态类型从「关闭检查」换成「顶层类型」，数据仍是无 schema 的匿名 Map、仍靠
字符串 key 访问，一个字段拼错在编译期同样不可见。它曾被登记为 informational
指标，这等于给 `dynamic -> Object?` 的机械改写留了一条把棘轮读数改好看的通道。
真正的收敛只有一条路：把匿名 Map 换成 metadata-owned 具名 DTO / sealed type。
`Map<String, Object?>` 仅允许驻留在两类边界——serde（fromJson/toJson 的 wire
层）与契约里登记为开放扩展槽（`type: any` / extension map）的字段——这两类
边界的存量由本桶锁定只减不增，收敛为具名 DTO 时随之下降。

注释与文档注释中的匹配被排除：它们不是类型声明，改注释不该动门禁读数。

历史口径修正记录：
  - 最初的口径用两个独立正则统计文本出现次数，`dynamic_keyword` 把每个
    `Map<String, dynamic>` 里的 `dynamic` 又数了一遍：基线 209/373 里有 209
    是重复计数。现口径先扣掉 Map 内的 `dynamic`。
  - `bare_dynamic` 归零不可达：`fromJson(Map<String, dynamic>)` 是 Dart 生态
    与本仓 codegen 自身的标准签名，手写代码与生成 DTO 交互时必然出现。

退出条件见基线 `_governance.expires_when`。

行为：
  - 默认：与 quwoquan_ops/policies/gates/assistant_search_weak_typing_baseline.json 比较，
    任一指标 **严格大于** 基线 → exit 1（回归）。
  - --write-baseline：用当前扫描覆盖基线文件（有意收口或 bump 基线时用）。

退出码：0 成功；1 回归或基线缺失；2 参数/IO 错误。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path


def _find_repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "quwoquan_app").is_dir() and (candidate / "quwoquan_service").is_dir():
            return candidate
    raise RuntimeError("cannot locate quwoquan repo root")

ROOT = _find_repo_root()
LIB = ROOT / "quwoquan_app" / "lib"
DEFAULT_BASELINE = ROOT / "quwoquan_ops" / "policies" / "gates" / "assistant_search_weak_typing_baseline.json"

MAP_RE = re.compile(r"Map<String,\s*dynamic>")
MAP_OBJECT_OPT_RE = re.compile(r"Map<String,\s*Object\?>")
DYNAMIC_RE = re.compile(r"\bdynamic\b")

SEARCH_REPO_FILE = (
    LIB
    / "service"
    / "search_service"
    / "search"
    / "search_index_view"
    / "application"
    / "search_repository.dart"
)


@dataclass
class BucketCounts:
    map_string_dynamic: int
    map_string_object_optional: int
    bare_dynamic: int


METRICS = ("map_string_dynamic", "map_string_object_optional", "bare_dynamic")


def _read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def _strip_comments(text: str) -> str:
    """Drop `//` line comments and `/* */` blocks.

    A `dynamic` inside a comment is not a type declaration; counting it means
    rewording a doc comment moves the ratchet.
    """

    without_blocks = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", without_blocks)


def count_text(text: str) -> BucketCounts:
    """Count the three disjoint weak-typing buckets in one source text."""

    code = _strip_comments(text)
    maps = len(MAP_RE.findall(code))
    # Every `Map<String, dynamic>` contains exactly one `dynamic`; subtracting
    # them keeps the metrics disjoint so each one names distinct debt.
    bare = len(DYNAMIC_RE.findall(code)) - maps
    return BucketCounts(
        map_string_dynamic=maps,
        map_string_object_optional=len(MAP_OBJECT_OPT_RE.findall(code)),
        bare_dynamic=bare,
    )


def scan_assistant_handwritten() -> BucketCounts:
    base = LIB / "service" / "assistant_service"
    if not base.is_dir():
        raise SystemExit(
            f"ERROR: assistant service root not found: {base.relative_to(ROOT)}\n"
            "搬迁后请把 assistant_handwritten bucket 指向新位置，不要让门禁静默归零。"
        )
    total = BucketCounts(0, 0, 0)
    for path in base.rglob("*.dart"):
        if path.name.endswith(".g.dart"):
            continue
        try:
            rel = path.relative_to(LIB)
        except ValueError:
            continue
        if "generated" in rel.parts:
            continue
        counts = count_text(_read_text(path))
        total.map_string_dynamic += counts.map_string_dynamic
        total.map_string_object_optional += counts.map_string_object_optional
        total.bare_dynamic += counts.bare_dynamic
    return total


def scan_search_repository() -> BucketCounts:
    if not SEARCH_REPO_FILE.is_file():
        # 文件缺失必须阻断：静默返回 0 会让搬迁后的 bucket 永久达标，门禁空转。
        raise SystemExit(
            f"ERROR: search repository not found: {SEARCH_REPO_FILE.relative_to(ROOT)}\n"
            "搬迁后请把 SEARCH_REPO_FILE 指向新位置，不要让 bucket 静默归零。"
        )
    return count_text(_read_text(SEARCH_REPO_FILE))


def current_snapshot() -> dict[str, dict[str, int]]:
    return {
        "assistant_handwritten": asdict(scan_assistant_handwritten()),
        "core_search_repository": asdict(scan_search_repository()),
    }


def load_baseline(path: Path) -> dict[str, dict[str, int]] | None:
    if not path.is_file():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    buckets = raw.get("buckets")
    if not isinstance(buckets, dict):
        return None
    out: dict[str, dict[str, int]] = {}
    for k, v in buckets.items():
        if isinstance(v, dict) and all(isinstance(v.get(x), int) for x in METRICS):
            out[str(k)] = {metric: int(v[metric]) for metric in METRICS}
    return out if out else None


def regressions(
    baseline: dict[str, dict[str, int]],
    current: dict[str, dict[str, int]],
) -> list[str]:
    msgs: list[str] = []
    all_keys = sorted(set(baseline) | set(current))
    empty = {metric: 0 for metric in METRICS}
    for key in all_keys:
        b = baseline.get(key, empty)
        c = current.get(key, empty)
        for metric in METRICS:
            if c[metric] > b[metric]:
                msgs.append(
                    f"{key}.{metric}: baseline={b[metric]} current={c[metric]} (regression +{c[metric] - b[metric]})"
                )
            elif c[metric] < b[metric]:
                msgs.append(
                    f"{key}.{metric}: baseline={b[metric]} current={c[metric]} "
                    f"(stale budget -{b[metric] - c[metric]})"
                )
    return msgs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--baseline",
        type=Path,
        default=DEFAULT_BASELINE,
        help="Path to baseline JSON",
    )
    ap.add_argument(
        "--write-baseline",
        action="store_true",
        help="Overwrite baseline file with current counts",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help="Print current snapshot JSON to stdout",
    )
    args = ap.parse_args()
    baseline_path: Path = args.baseline

    if args.json:
        print(
            json.dumps(
                {"buckets": current_snapshot()},
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    current = current_snapshot()

    if args.write_baseline:
        existing_governance: dict[str, object] | None = None
        if baseline_path.is_file():
            try:
                existing = json.loads(baseline_path.read_text(encoding="utf-8"))
                governance = existing.get("_governance")
                if isinstance(governance, dict):
                    existing_governance = governance
            except (OSError, json.JSONDecodeError):
                pass
        if existing_governance is None:
            print(
                "ERROR: refusing to rewrite baseline without _governance",
                file=sys.stderr,
            )
            return 1
        payload = {
            "_governance": existing_governance,
            "buckets": current,
            "notes": "Ratchet: any increase in map_string_dynamic, map_string_object_optional or bare_dynamic per bucket fails CI until baseline is intentionally updated.",
        }
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote baseline: {baseline_path}", file=sys.stderr)
        return 0

    baseline = load_baseline(baseline_path)
    if baseline is None:
        print(
            f"ERROR: missing or invalid baseline: {baseline_path}\n"
            "Run: python3 quwoquan_ops/tests/acceptance/user_acceptance/service_ops/assistant-service/gate/verify_assistant_search_weak_typing_ratchet.py --write-baseline",
            file=sys.stderr,
        )
        return 1

    bad = regressions(baseline, current)
    if bad:
        print("assistant/search weak typing RATCHET FAIL (baseline drift):", file=sys.stderr)
        for line in bad:
            print(f"  {line}", file=sys.stderr)
        print(
            "\nIf the increase is intentional, update the baseline with --write-baseline in a dedicated commit.",
            file=sys.stderr,
        )
        return 1

    print(
        "verify_assistant_search_weak_typing_ratchet: ok (no regression vs baseline)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
