#!/usr/bin/env bash
set -euo pipefail

readonly DEFAULT_READY_ATTEMPTS=60
readonly DEFAULT_READY_DELAY_SECONDS=1
readonly MONGO_IMAGE="mongo:7-jammy"
readonly MONGO_CONTAINER="qwq-rec-mongo"
readonly MONGO_URI="mongodb://127.0.0.1:27017/?directConnection=true"
started_by_this_run=false

ready_attempts="${QWQ_CI_MONGO_READY_ATTEMPTS:-$DEFAULT_READY_ATTEMPTS}"
ready_delay_seconds="${QWQ_CI_MONGO_READY_DELAY_SECONDS:-$DEFAULT_READY_DELAY_SECONDS}"

require_bounded_integer() {
  local name="$1" value="$2" minimum="$3" maximum="$4"
  if [[ ! "$value" =~ ^[0-9]+$ ]]; then
    echo "GATE_BLOCK: CI.DEPENDENCY.MONGO_BOUND_INVALID name=$name value=$value allowed=${minimum}-${maximum}" >&2
    exit 2
  fi
  local decimal_value=$((10#$value))
  if (( decimal_value < minimum || decimal_value > maximum )); then
    echo "GATE_BLOCK: CI.DEPENDENCY.MONGO_BOUND_INVALID name=$name value=$value allowed=${minimum}-${maximum}" >&2
    exit 2
  fi
}

require_bounded_integer readyAttempts "$ready_attempts" 1 "$DEFAULT_READY_ATTEMPTS"
require_bounded_integer readyDelaySeconds "$ready_delay_seconds" 0 "$DEFAULT_READY_DELAY_SECONDS"

cleanup_failed_container() {
  if [[ "$started_by_this_run" == true ]]; then
    docker logs "$MONGO_CONTAINER" >&2 || true
    docker rm -f "$MONGO_CONTAINER" >/dev/null 2>&1 || true
  fi
}

block() {
  local reason="$1"
  cleanup_failed_container
  echo "GATE_BLOCK: CI.DEPENDENCY.${reason} image=$MONGO_IMAGE container=$MONGO_CONTAINER fix=inspect-docker-log-and-rerun-exact-job" >&2
  exit 2
}

if docker inspect "$MONGO_CONTAINER" >/dev/null 2>&1; then
  block "MONGO_CONTAINER_ALREADY_EXISTS"
fi

if ! docker run -d --name "$MONGO_CONTAINER" -p 127.0.0.1:27017:27017 "$MONGO_IMAGE" \
  --replSet rs0 --bind_ip_all; then
  block "MONGO_START_FAILED"
fi
started_by_this_run=true

ping_ready=false
for _ in $(seq 1 "$ready_attempts"); do
  if docker exec "$MONGO_CONTAINER" mongosh --quiet \
    --eval 'db.runCommand({ping:1}).ok' | grep -qx '1'; then
    ping_ready=true
    break
  fi
  sleep "$ready_delay_seconds"
done
if [[ "$ping_ready" != true ]]; then
  block "MONGO_PING_TIMEOUT"
fi

if ! docker exec "$MONGO_CONTAINER" mongosh --quiet --eval \
  'rs.initiate({_id:"rs0",members:[{_id:0,host:"127.0.0.1:27017"}]})'; then
  block "MONGO_REPLICA_INIT_FAILED"
fi

primary_ready=false
for _ in $(seq 1 "$ready_attempts"); do
  if docker exec "$MONGO_CONTAINER" mongosh --quiet \
    --eval 'db.hello().isWritablePrimary' | grep -qx 'true'; then
    primary_ready=true
    break
  fi
  sleep "$ready_delay_seconds"
done
if [[ "$primary_ready" != true ]]; then
  block "MONGO_PRIMARY_TIMEOUT"
fi

if [[ -n "${GITHUB_ENV:-}" ]]; then
  printf 'QWQ_TEST_MONGO_URI=%s\n' "$MONGO_URI" >> "$GITHUB_ENV"
fi
echo "[ci-dependency] recommendation MongoDB replica set is writable"
