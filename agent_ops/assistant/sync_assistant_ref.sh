#!/usr/bin/env bash
# 小趣私人助手参考实现：从上游仓库克隆/更新 assistant_ref 下的 openclaw 与 nanobot。
# assistant_ref/ 已加入 .gitignore，不会提交到代码库。
# 使用方式：在工程根目录执行 ./scripts/sync_assistant_ref.sh 或 bash scripts/sync_assistant_ref.sh

set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REF_DIR="${ROOT}/assistant_ref"
OPENCLAW_URL="https://github.com/openclaw/openclaw.git"
NANOBOT_URL="https://github.com/HKUDS/nanobot.git"

mkdir -p "$REF_DIR"
cd "$REF_DIR"

if [[ -d openclaw/.git ]]; then
  echo "Updating openclaw..."
  (cd openclaw && git fetch --depth 1 origin main && git reset --hard origin/main)
else
  echo "Cloning openclaw..."
  git clone --depth 1 --branch main "$OPENCLAW_URL" openclaw
fi

if [[ -d nanobot/.git ]]; then
  echo "Updating nanobot..."
  (cd nanobot && git fetch --depth 1 origin main && git reset --hard origin/main)
else
  echo "Cloning nanobot..."
  git clone --depth 1 --branch main "$NANOBOT_URL" nanobot
fi

echo "Done. assistant_ref: openclaw + nanobot."
