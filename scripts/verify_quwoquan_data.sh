#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[verify] quwoquan_data"

python3 quwoquan_data/tools/qwq_data/cli.py labels validate
python3 quwoquan_data/tools/qwq_data/cli.py tree validate --tree all
python3 quwoquan_data/tools/qwq_data/cli.py catalog stats --type 地点/景点
python3 quwoquan_data/tools/qwq_data/cli.py relations validate
python3 quwoquan_data/tools/qwq_data/cli.py materials extract --topic 旅行/攻略/杭州西湖城市漫游
python3 quwoquan_data/tools/qwq_data/cli.py crawl plan --run-id smoke --topic 旅行/攻略/杭州西湖城市漫游
python3 quwoquan_data/tools/qwq_data/cli.py crawl expand --run-id smoke --topic 旅行/攻略/杭州西湖城市漫游
python3 quwoquan_data/tools/qwq_data/cli.py bundle build --bundle m1_dry_run_smoke --topic 旅行/攻略/杭州西湖城市漫游
python3 quwoquan_data/tools/qwq_data/cli.py dry-run --bundle m1_dry_run_smoke
python3 quwoquan_data/tools/qwq_data/cli.py report coverage --bundle m1_dry_run_smoke
python3 -m unittest discover -s quwoquan_data/tests

echo "[verify] OK: quwoquan_data"
