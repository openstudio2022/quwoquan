#!/usr/bin/env bash
# train_pipeline.sh — Local-reproducible training pipeline.
# Chains: sample_joiner → train → evaluate → promote-gate → register
#
# Usage:
#   bash scripts/ml/train_pipeline.sh --scenario content_feed
#   bash scripts/ml/train_pipeline.sh --scenario content_feed --dry-run
#   bash scripts/ml/train_pipeline.sh --scenario content_feed --production
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCENARIO="${SCENARIO:-content_feed}"
MONGODB_URI="${MONGODB_URI:-mongodb://127.0.0.1:27017/?directConnection=true}"
DB="${DB:-quwoquan_content}"
OUT_DIR="${MODEL_OUT_DIR:-/tmp/rec_models}"
DRY_RUN=false
PRODUCTION=false
LIMIT=50000
NUM_BOOST_ROUND=100

while [[ $# -gt 0 ]]; do
  case $1 in
    --scenario) SCENARIO="$2"; shift 2 ;;
    --mongodb-uri) MONGODB_URI="$2"; shift 2 ;;
    --db) DB="$2"; shift 2 ;;
    --out-dir) OUT_DIR="$2"; shift 2 ;;
    --dry-run) DRY_RUN=true; shift ;;
    --production) PRODUCTION=true; shift ;;
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

PROD_FLAG=""
if $PRODUCTION; then
  PROD_FLAG="--production"
fi

export MONGODB_URI DB

echo "============================================"
echo "[pipeline] Scenario: $SCENARIO"
echo "[pipeline] MongoDB:  $MONGODB_URI / $DB"
echo "[pipeline] Output:   $OUT_DIR"
echo "============================================"

echo ""
echo ">>> Step 0/6: Seed Data Bootstrap (dry-run only)"
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
echo ">>> Step 1/6: Sample Joiner"
python3 "$SCRIPT_DIR/sample_joiner.py" \
  --scenario "$SCENARIO" \
  --mongodb-uri "$MONGODB_URI" \
  --db "$DB" \
  --limit "$LIMIT" \
  --clean

echo ""
echo ">>> Step 2/6: Train LightGBM"
python3 "$SCRIPT_DIR/train.py" \
  --scenario "$SCENARIO" \
  --mongodb-uri "$MONGODB_URI" \
  --db "$DB" \
  --out-dir "$OUT_DIR" \
  --num-boost-round "$NUM_BOOST_ROUND" \
  --min-samples "$MIN_SAMPLES" \
  $PROD_FLAG

echo ""
echo ">>> Step 3/6: Train Multi-Objective"
python3 "$SCRIPT_DIR/train_multiobjective.py" \
  --scenario "$SCENARIO" \
  --mongodb-uri "$MONGODB_URI" \
  --db "$DB" \
  --out-dir "$OUT_DIR" \
  --num-boost-round "$NUM_BOOST_ROUND" \
  --min-samples "$MIN_SAMPLES" \
  $PROD_FLAG

echo ""
echo ">>> Step 4/6: Evaluate"
python3 "$SCRIPT_DIR/evaluate.py" \
  --scenario "$SCENARIO" \
  --mongodb-uri "$MONGODB_URI" \
  --db "$DB"
python3 "$SCRIPT_DIR/evaluate.py" \
  --scenario "${SCENARIO}_multiobjective" \
  --mongodb-uri "$MONGODB_URI" \
  --db "$DB"

GATE_FLAGS=""
if $DRY_RUN; then
  GATE_FLAGS="--dry-run"
fi

echo ""
echo ">>> Step 5/6: Evaluate Gate"
python3 "$SCRIPT_DIR/evaluate_gate.py" \
  --scenario "$SCENARIO" \
  --mongodb-uri "$MONGODB_URI" \
  --db "$DB" \
  --out "eval_report_${SCENARIO}.json" \
  $GATE_FLAGS || {
    echo "[pipeline] GATE BLOCKED — model did not pass quality thresholds"
    exit 1
  }

python3 "$SCRIPT_DIR/evaluate_gate.py" \
  --scenario "${SCENARIO}_multiobjective" \
  --mongodb-uri "$MONGODB_URI" \
  --db "$DB" \
  --out "eval_report_${SCENARIO}_multiobjective.json" \
  $GATE_FLAGS || {
    echo "[pipeline] MULTIOBJECTIVE GATE BLOCKED — model did not pass quality thresholds"
    exit 1
  }

echo ""
echo "============================================"
echo "[pipeline] COMPLETE for scenario=$SCENARIO"
echo "============================================"
