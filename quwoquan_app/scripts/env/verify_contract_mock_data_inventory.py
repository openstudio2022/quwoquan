#!/usr/bin/env python3
"""阻止测试侧新增对端侧 mock data 类的直接依赖。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BASELINE = ROOT / "quwoquan_ops" / "policies" / "gates" / "contract_mock_data_baseline.json"
TEST_ROOT = ROOT / "quwoquan_app" / "test"


def _scan(tokens: set[str]) -> dict[str, dict[str, int]]:
    current = {
        token: {"maxOccurrences": 0, "maxFiles": 0}
        for token in tokens
    }
    files_by_token = {token: set() for token in tokens}
    for path in TEST_ROOT.rglob("*.dart"):
        text = path.read_text(encoding="utf-8")
        for token in tokens:
            count = text.count(token)
            if not count:
                continue
            current[token]["maxOccurrences"] += count
            files_by_token[token].add(path.relative_to(ROOT).as_posix())
    for token in tokens:
        current[token]["maxFiles"] = len(files_by_token[token])
    return current


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-baseline", action="store_true")
    args = parser.parse_args()
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    tokens = data.get("tokens", {})
    current = _scan(set(tokens))
    if args.write_baseline:
        data["tokens"] = {
            token: current[token]
            for token in sorted(current)
        }
        BASELINE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"contract_mock_data_ratchet: wrote baseline tokens={len(current)}")
        return 0

    failures: list[str] = []
    for token, limits in tokens.items():
        occurrences = current[token]["maxOccurrences"]
        file_count = current[token]["maxFiles"]
        max_occurrences = int(limits.get("maxOccurrences", 0))
        max_files = int(limits.get("maxFiles", 0))
        if occurrences > max_occurrences or file_count > max_files:
            failures.append(
                f"{token}: occurrences={occurrences}/{max_occurrences}, "
                f"files={file_count}/{max_files}"
            )
    if failures:
        print("contract_mock_data_ratchet 校验失败:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        print("请将新增测试数据迁入 contracts/metadata/**/test_fixtures。", file=sys.stderr)
        return 1
    print("contract_mock_data_ratchet: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
