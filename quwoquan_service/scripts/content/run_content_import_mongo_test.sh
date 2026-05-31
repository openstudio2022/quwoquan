#!/usr/bin/env bash
# 起一个一次性 mongod（独立 dbpath + 端口，不碰任何已有数据），
# 跑 content-service importer 的真实 mongo 写入路径测试，结束后销毁。
#
# 用法：bash quwoquan_service/scripts/content/run_content_import_mongo_test.sh
# 依赖：mongod（brew install mongodb-community）、go。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
IMPORT_DIR="${REPO_ROOT}/quwoquan_service/services/content-service/cmd/import"

if ! command -v mongod >/dev/null 2>&1; then
  echo "FAIL: mongod 未安装（brew install mongodb-community）" >&2
  exit 1
fi

PORT="${QWQ_TEST_MONGO_PORT:-37017}"
WORKDIR="$(mktemp -d -t qwq_mongo_import_test.XXXXXX)"
DBPATH="${WORKDIR}/db"
LOGPATH="${WORKDIR}/mongod.log"
mkdir -p "${DBPATH}"

MONGO_PID=""
cleanup() {
  if [ -n "${MONGO_PID}" ] && kill -0 "${MONGO_PID}" 2>/dev/null; then
    kill "${MONGO_PID}" 2>/dev/null || true
    wait "${MONGO_PID}" 2>/dev/null || true
  fi
  rm -rf "${WORKDIR}"
}
trap cleanup EXIT

echo "[mongo-test] 启动临时 mongod port=${PORT} dbpath=${DBPATH}"
mongod --dbpath "${DBPATH}" --port "${PORT}" --bind_ip 127.0.0.1 \
  --logpath "${LOGPATH}" --noauth >/dev/null 2>&1 &
MONGO_PID=$!

# 等待端口就绪
for i in $(seq 1 30); do
  if (echo > "/dev/tcp/127.0.0.1/${PORT}") 2>/dev/null; then
    break
  fi
  if ! kill -0 "${MONGO_PID}" 2>/dev/null; then
    echo "FAIL: mongod 启动失败，日志：" >&2
    cat "${LOGPATH}" >&2 || true
    exit 1
  fi
  sleep 0.5
done

export QWQ_TEST_MONGO_URI="mongodb://127.0.0.1:${PORT}"
echo "[mongo-test] QWQ_TEST_MONGO_URI=${QWQ_TEST_MONGO_URI}"

cd "${IMPORT_DIR}"
go test ./... -run 'Mongo|Load' -v -count=1
echo "[mongo-test] OK"
