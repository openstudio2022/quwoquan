#!/usr/bin/env bash
# 本地 L2 契约测试（content-service，基于 MongoDB）
#
# 用途：提交前在本地完整跑通 L2 测试，避免 CI 失败。
#
# 用法：
#   ./scripts/run_l2_content_tests.sh              # 使用默认 localhost:27017
#   MONGO_PORT=27018 ./scripts/run_l2_content_tests.sh   # 指定端口
#
# 前置条件（任选其一）：
#   A) Docker + docker compose：  cd quwoquan_service && docker compose up -d mongodb
#   B) Docker 单容器：            docker run -d -p 27017:27017 --name mongo-l2 mongo:7-jammy
#   C) 本机 MongoDB：             brew services start mongodb-community  # macOS
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../" && pwd)"
cd "$ROOT"

MONGO_PORT="${MONGO_PORT:-27017}"
MONGO_URI="mongodb://localhost:${MONGO_PORT}"

# 检测 MongoDB 是否可达（简单 ping）
check_mongo() {
  if command -v mongosh &>/dev/null; then
    mongosh --quiet "$MONGO_URI" --eval "db.adminCommand('ping')" &>/dev/null && return 0
  fi
  # 无 mongosh 时尝试 nc 检测端口
  if command -v nc &>/dev/null; then
    nc -z localhost "$MONGO_PORT" 2>/dev/null && return 0
  fi
  return 1
}

echo "[L2] content-service 契约测试（MongoDB @ localhost:${MONGO_PORT}）"

if ! check_mongo; then
  echo "[L2] FAIL: MongoDB 未在 localhost:${MONGO_PORT} 运行"
  echo ""
  echo "  请先启动 MongoDB，任选其一："
  echo "    • docker compose:  cd quwoquan_service && docker compose up -d mongodb"
  echo "    • docker 单容器:   docker run -d -p 27017:27017 --name mongo-l2 mongo:7-jammy"
  echo "    • macOS Homebrew:  brew services start mongodb-community"
  echo ""
  echo "  或指定端口: MONGO_PORT=27018 ./scripts/run_l2_content_tests.sh"
  exit 1
fi

echo "[L2] MongoDB 已就绪，运行测试..."
cd quwoquan_service
TEST_MONGO_URI="$MONGO_URI" go test ./services/content-service/... -v -count=1 -timeout=120s
