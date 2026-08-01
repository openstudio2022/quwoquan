#!/usr/bin/env bash
# train_pipeline.sh — Local-reproducible training pipeline.
# Chains: sample_joiner → train/evaluate → immutable artifact upload → Stage.
#
# Usage:
#   bash services/recommendation-service/internal/recommendation/recommendation_model_release/infrastructure/model_runtime/scripts/train_pipeline.sh --scenario content_feed
#   bash services/recommendation-service/internal/recommendation/recommendation_model_release/infrastructure/model_runtime/scripts/train_pipeline.sh --scenario content_feed --dry-run
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCENARIO="${SCENARIO:-content_feed}"
MONGODB_URI="${MONGODB_URI:-mongodb://127.0.0.1:27017/?directConnection=true}"
DB="${DB:-quwoquan_recommendation}"
OUT_DIR="${MODEL_OUT_DIR:-/tmp/rec_models}"
DRY_RUN=false
LIMIT=50000
NUM_BOOST_ROUND=100

while [[ $# -gt 0 ]]; do
  case $1 in
    --scenario) SCENARIO="$2"; shift 2 ;;
    --mongodb-uri) MONGODB_URI="$2"; shift 2 ;;
    --db) DB="$2"; shift 2 ;;
    --out-dir) OUT_DIR="$2"; shift 2 ;;
    --dry-run) DRY_RUN=true; shift ;;
    --limit) LIMIT="$2"; shift 2 ;;
    --num-boost-round) NUM_BOOST_ROUND="$2"; shift 2 ;;
    *) echo "Unknown flag: $1" >&2; exit 1 ;;
  esac
done

MIN_SAMPLES=100
if $DRY_RUN; then
  LIMIT=200
  NUM_BOOST_ROUND=5
  MIN_SAMPLES=50
  if [[ "$DB" != *_dryrun ]]; then
    DB="${DB}_dryrun"
  fi
  echo "[pipeline] DRY-RUN mode: limit=$LIMIT, rounds=$NUM_BOOST_ROUND, min_samples=$MIN_SAMPLES"
fi

LOCAL_EVALUATION_FLAG=""
if $DRY_RUN; then
  LOCAL_EVALUATION_FLAG="--local-evaluation-only"
fi

export MONGODB_URI DB

echo "============================================"
echo "[pipeline] Scenario: $SCENARIO"
echo "[pipeline] MongoDB:  $MONGODB_URI / $DB"
echo "[pipeline] Output:   $OUT_DIR"
echo "============================================"

echo ""
echo ">>> Step 0/3: Seed Data Bootstrap (local evaluation only)"
if $DRY_RUN; then
  python3 "$SCRIPT_DIR/generate_seed_data.py" \
    --scenario "$SCENARIO" \
    --mongodb-uri "$MONGODB_URI" \
    --db "$DB" \
    --clean
  echo "[pipeline] Seed data injected"
else
  echo "[pipeline] Skipping seed bootstrap (not dry-run)"
fi

echo ""
echo ">>> Step 1/3: Sample Joiner"
python3 "$SCRIPT_DIR/sample_joiner.py" \
  --scenario "$SCENARIO" \
  --mongodb-uri "$MONGODB_URI" \
  --db "$DB" \
  --limit "$LIMIT" \
  --clean

echo ""
echo ">>> Step 2/3: Train, verify and Stage LightGBM"
python3 "$SCRIPT_DIR/train.py" \
  --scenario "$SCENARIO" \
  --mongodb-uri "$MONGODB_URI" \
  --db "$DB" \
  --out-dir "$OUT_DIR" \
  --num-boost-round "$NUM_BOOST_ROUND" \
  --min-samples "$MIN_SAMPLES" \
  $LOCAL_EVALUATION_FLAG

echo ""
echo ">>> Step 3/3: Train, verify and Stage Multi-Objective"
python3 "$SCRIPT_DIR/train_multiobjective.py" \
  --scenario "$SCENARIO" \
  --mongodb-uri "$MONGODB_URI" \
  --db "$DB" \
  --out-dir "$OUT_DIR" \
  --num-boost-round "$NUM_BOOST_ROUND" \
  --min-samples "$MIN_SAMPLES" \
  $LOCAL_EVALUATION_FLAG

echo ""
echo "============================================"
echo "[pipeline] COMPLETE for scenario=$SCENARIO"
echo "============================================"
