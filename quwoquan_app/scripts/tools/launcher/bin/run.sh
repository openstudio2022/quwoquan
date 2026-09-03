#!/usr/bin/env bash
# canonical launcher 的全局 PATH wrapper：任意工作目录可调用 `run.sh`。
# 本文件不承载任何参数、状态或判定；逻辑唯一归属仓库内 quwoquan_app/run.sh。
set -euo pipefail
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)/run.sh" "$@"
