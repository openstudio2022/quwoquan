#!/usr/bin/env bash
set -euo pipefail

# The commit hook is intentionally L0 only.  Delivery Gate owns full
# local-contract shards; this keeps local commits bounded while preserving the
# repository-wide static invariants that can be checked without a build.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

export QWQ_OUTPUT_ROOT="$ROOT/.qwq_output"
export PYTHONDONTWRITEBYTECODE=1

python3 quwoquan_ops/gate/verify_git_branch_policy.py
git diff --cached --check
python3 quwoquan_ops/gate/scaffold/verify_test_directory_layout.py
python3 quwoquan_ops/gate/scaffold/verify_test_no_fake.py
python3 quwoquan_ops/gate/verify_output_layout.py
