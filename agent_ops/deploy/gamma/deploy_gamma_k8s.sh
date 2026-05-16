#!/usr/bin/env bash
set -euo pipefail
export DEPLOY_ENV=gamma
exec "$(dirname "${BASH_SOURCE[0]}")/../shared/deploy_integration_k8s.sh" "$@"
