#!/usr/bin/env bash
# Verify CDN_DOMAIN is injected for non-alpha environments.
# Used in CI/CD to prevent shipping builds without CDN image processing.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

ENV="${APP_RUNTIME_ENV:-alpha}"
CDN="${CDN_DOMAIN:-}"

if [[ "$ENV" == "alpha" ]]; then
  echo "[CDN-DOMAIN] ENV=alpha, CDN_DOMAIN check skipped (local dev)"
  exit 0
fi

if [[ -z "$CDN" ]]; then
  echo "FAIL: CDN_DOMAIN is not set but APP_RUNTIME_ENV=$ENV"
  echo "  Image processing will be disabled; mobile clients will load full-size images."
  echo "  Set CDN_DOMAIN=your-cdn.example.com before building."
  exit 1
fi

echo "[CDN-DOMAIN] ENV=$ENV CDN_DOMAIN=$CDN — OK"
