#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[verify] quwoquan_data"

python3 quwoquan_data/tools/cli.py tree validate --tree all
python3 quwoquan_data/tools/cli.py batch plan-retrieval --plan quwoquan_data/batch_plans/west_lake_loop_001.yaml
python3 quwoquan_data/tools/cli.py batch status --plan quwoquan_data/batch_plans/west_lake_loop_001.yaml
python3 quwoquan_data/tools/cli.py batch plan-retrieval --plan quwoquan_data/batch_plans/west_lake_image_001.yaml
python3 quwoquan_data/tools/cli.py batch status --plan quwoquan_data/batch_plans/west_lake_image_001.yaml
python3 quwoquan_data/tools/cli.py batch run --plan quwoquan_data/batch_plans/west_lake_image_001.yaml --targets alpha,gamma --dry-run
python3 quwoquan_data/tools/cli.py batch plan-retrieval --plan quwoquan_data/batch_plans/west_lake_article_001.yaml
python3 quwoquan_data/tools/cli.py batch status --plan quwoquan_data/batch_plans/west_lake_article_001.yaml
python3 quwoquan_data/tools/cli.py batch run --plan quwoquan_data/batch_plans/west_lake_article_001.yaml --targets alpha,gamma --dry-run
python3 -m unittest discover -s quwoquan_data/tests

echo "[verify] OK: quwoquan_data"
