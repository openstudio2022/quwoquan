#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

# CLI-first ratchet：拦截新增直跑业务入口脚本（必须经 qwq-data 暴露给 skill）
python3 quwoquan_data/scripts/verify/verify_cli_first.py
python3 quwoquan_data/scripts/cli.py template lint
python3 quwoquan_data/scripts/cli.py template creator-lint
python3 quwoquan_data/scripts/cli.py template rec-contract
python3 quwoquan_data/scripts/cli.py template region-season-lint
# 收紧扫描范围：只校验当前 schema 的 posts 根（旧遗留包通过 --scope all 单独审计）
python3 quwoquan_data/scripts/cli.py verify --scope current

echo "[verify-quwoquan-data] PASSED"
