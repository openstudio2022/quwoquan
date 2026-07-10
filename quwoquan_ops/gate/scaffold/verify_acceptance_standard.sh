#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

echo "[verify] acceptance standard (UAT/SIT/GWT/contract + three-layer test evidence)"

python3 quwoquan_ops/gate/scaffold/verify_test_specs.py
