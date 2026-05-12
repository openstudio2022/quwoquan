#!/usr/bin/env bash
# 四川全量批次：县级切片目录重建 → 实体/标签 → 门禁 → spec → 全量轻量下载 → 分批 hydrate/process/publish → 报告
#
# 环境变量（可选）:
#   RUN_FULL_RESET=1          先执行 reset_quwoquan_data_runtime_full.sh（默认 0）
#   SICHUAN_SKIP_CATALOG_BUILD=1  跳过 Overpass 目录构建（沿用已有 FULL_CATALOG / SLICE_REPORT）
#   MIN_KEPT / MIN_ROWS       目录门禁下限（默认 1000）
#   SICHUAN_DEEP_TOPIC_CAP    深链路累计 topic 上限（默认 120，避免一次跑满千级站点）
#   SICHUAN_FULL_SPEC_ID      spec_id（默认 sichuan_province_full_batch_001）
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RUNTIME="${QWQ_RUNTIME_ROOT:-$ROOT/quwoquan_data/runtime}"
export QWQ_DATA_ROOT="${QWQ_DATA_ROOT:-$ROOT/quwoquan_data}"
export QWQ_RUNTIME_ROOT="$RUNTIME"
export QWQ_REPO_ROOT="${QWQ_REPO_ROOT:-$ROOT}"

DOC_ROOT="$ROOT/specs/feature-tree/runtime/runtime-data-engineering/geo-content-trinity"
COUNTY_CONFIG="$DOC_ROOT/config/geo_catalog_config.sichuan.county.yaml"
NAMING="$DOC_ROOT/config/entity_naming_rules.yaml"
WORKFLOW_DOC="$DOC_ROOT/workflow.md"
COMMAND_DOC="$DOC_ROOT/command-matrix.md"
SPEC_DOC="$DOC_ROOT/spec.md"
DESIGN_DOC="$DOC_ROOT/design.md"
ACCEPTANCE_DOC="$DOC_ROOT/acceptance.yaml"

FULL_CATALOG="$RUNTIME/seed/sichuan_chuanxi_attractions_catalog.ndjson"
SLICE_REPORT="$RUNTIME/out/reports/sichuan_geo_catalog_slice_report.json"
ALT_SLICE_REPORT="$RUNTIME/seed/sichuan_chuanxi_attractions_catalog.slice_report.json"
SPEC_ID="${SICHUAN_FULL_SPEC_ID:-sichuan_province_full_batch_001}"
SPEC_PATH="$RUNTIME/specs/${SPEC_ID}.yaml"
MIN_KEPT="${MIN_KEPT:-1000}"
MIN_ROWS="${MIN_ROWS:-1000}"
SICHUAN_DEEP_TOPIC_CAP="${SICHUAN_DEEP_TOPIC_CAP:-120}"
REPORT_JSONL="$RUNTIME/out/reports/sichuan_full_batch_run.jsonl"

if [[ "${RUN_FULL_RESET:-0}" == "1" ]]; then
  echo "[sichuan-full-batch] reset runtime"
  bash "$ROOT/scripts/reset_quwoquan_data_runtime_full.sh"
fi

echo "[sichuan-full-batch] baseline"
python3 quwoquan_data/tools/cli.py data baseline \
  --spec-doc "$SPEC_DOC" \
  --design-doc "$DESIGN_DOC" \
  --acceptance-doc "$ACCEPTANCE_DOC" \
  --workflow-doc "$WORKFLOW_DOC" \
  --command-matrix-doc "$COMMAND_DOC" \
  --catalog-config "$COUNTY_CONFIG" \
  --naming-rules "$NAMING" \
  --schema-files \
    quwoquan_data/schema/geo_catalog_row.schema.json \
    quwoquan_data/schema/entity_catalog_row.schema.json \
    quwoquan_data/schema/tag_catalog_row.schema.json \
    quwoquan_data/schema/authority_pool_row.schema.json \
    quwoquan_data/schema/source_pool_row.schema.json

mkdir -p "$(dirname "$FULL_CATALOG")" "$(dirname "$SLICE_REPORT")" "$(dirname "$REPORT_JSONL")"
: >"$REPORT_JSONL"

if [[ "${SICHUAN_SKIP_CATALOG_BUILD:-0}" != "1" ]]; then
  echo "[sichuan-full-batch] build geo catalog (county slices, Overpass)"
  python3 quwoquan_data/tools/cli.py data build-entities-tags \
    --catalog-config "$COUNTY_CONFIG" \
    --catalog-output "$FULL_CATALOG" \
    --report-out "$SLICE_REPORT"
else
  echo "[sichuan-full-batch] skip Overpass catalog build; rebuild entity/tag from existing catalog NDJSON"
  python3 quwoquan_data/tools/cli.py data build-entities-tags --catalog "$FULL_CATALOG"
fi

if [[ ! -f "$SLICE_REPORT" && -f "$ALT_SLICE_REPORT" ]]; then
  SLICE_REPORT="$ALT_SLICE_REPORT"
fi

echo "[sichuan-full-batch] gates: geo quality + trinity consistency"
python3 "$ROOT/scripts/verify_geo_catalog_quality.py" \
  --catalog "$FULL_CATALOG" \
  --report "$SLICE_REPORT" \
  --min-kept "$MIN_KEPT" \
  --min-rows "$MIN_ROWS"
python3 "$ROOT/scripts/verify_catalog_entity_consistency.py" --catalog "$FULL_CATALOG"

echo "[sichuan-full-batch] instruction → entities-by-tag → spec-build"
python3 quwoquan_data/tools/cli.py crawl instruction-build \
  --spec-id "$SPEC_ID" \
  --instruction "四川全量县级切片：地理目录→实体标签→百科与攻略 discovery；分批 hydrate/publish 验收" \
  --tag-refs "trees/tags/主题/旅行攻略.yaml" \
  --verticals "travel" \
  --content-modes "article,image" \
  --regions "四川"

python3 quwoquan_data/tools/cli.py crawl entities-by-tag \
  --spec-id "$SPEC_ID" \
  --tag-refs "trees/tags/主题/旅行攻略.yaml"

python3 quwoquan_data/tools/cli.py crawl spec-build --spec-id "$SPEC_ID"

echo "[sichuan-full-batch] full-stage download (skip hydrate)"
python3 quwoquan_data/tools/cli.py data download \
  --spec "$SPEC_PATH" \
  --skip-hydrate \
  --merge \
  --wiki-expand filtered

echo "[sichuan-full-batch] deep batches: hydrate → process-content → publish"
export SPEC_ID SPEC_PATH ROOT RUNTIME REPORT_JSONL SICHUAN_DEEP_TOPIC_CAP
python3 - <<'PY'
import json
import os
import subprocess
import time
from pathlib import Path

import yaml

spec_path = Path(os.environ["SPEC_PATH"])
spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
ext = spec.get("extensions") or {}
batch_size = int(ext.get("suggestedBatchSize") or 30)
cap = int(os.environ.get("SICHUAN_DEEP_TOPIC_CAP") or "120")

spec_id = os.environ["SPEC_ID"]
runtime = Path(os.environ["RUNTIME"])
topics_path = runtime / "seed" / "entity_catalog" / f"{spec_id}_topics.ndjson"
rows = [
    json.loads(line)
    for line in topics_path.read_text(encoding="utf-8").splitlines()
    if line.strip()
]
ids = [str(r.get("topic_id") or "").strip() for r in rows if str(r.get("topic_id") or "").strip()]
ids = ids[:cap]

chunks: list[list[str]] = []
for i in range(0, len(ids), batch_size):
    chunks.append(ids[i : i + batch_size])

root = Path(os.environ["ROOT"])
report = Path(os.environ["REPORT_JSONL"])

for idx, chunk in enumerate(chunks, start=1):
    topics_csv = ",".join(chunk)
    t0 = time.time()

    def run(argv: list[str]) -> int:
        return subprocess.call(argv, cwd=root)

    rc = run(
        [
            "python3",
            str(root / "quwoquan_data" / "tools" / "cli.py"),
            "data",
            "download",
            "--spec",
            str(spec_path),
            "--skip-authority-sync",
            "--skip-pool-bootstrap",
            "--skip-spec-discovery",
            "--skip-content-discover",
            "--topics",
            topics_csv,
        ]
    )
    if rc != 0:
        with report.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "stage": "download_hydrate",
                        "batch": idx,
                        "exitCode": rc,
                        "topics": chunk,
                        "elapsedSec": round(time.time() - t0, 2),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
        raise SystemExit(rc)

    rc = run(
        [
            "python3",
            str(root / "quwoquan_data" / "tools" / "cli.py"),
            "data",
            "process-content",
            "--spec",
            str(spec_path),
            "--topics",
            topics_csv,
            "--targets",
            "alpha,gamma",
        ]
    )
    if rc != 0:
        with report.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "stage": "process-content",
                        "batch": idx,
                        "exitCode": rc,
                        "topics": chunk,
                        "elapsedSec": round(time.time() - t0, 2),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
        raise SystemExit(rc)

    rc = run(
        [
            "python3",
            str(root / "quwoquan_data" / "tools" / "cli.py"),
            "data",
            "publish",
            "--spec",
            str(spec_path),
            "--topics",
            topics_csv,
        ]
    )
    elapsed = round(time.time() - t0, 2)
    with report.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "stage": "publish_batch_complete",
                    "batch": idx,
                    "exitCode": rc,
                    "topics": chunk,
                    "elapsedSec": elapsed,
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    if rc != 0:
        raise SystemExit(rc)

print(json.dumps({"ok": True, "deepBatches": len(chunks), "deepTopics": len(ids)}, ensure_ascii=False))
PY

echo "[sichuan-full-batch] verify authenticity + post packages (runtime-wide)"
python3 "$ROOT/scripts/verify_quwoquan_data_source_authenticity.py"
python3 "$ROOT/scripts/verify_quwoquan_data_post_packages.py"

echo "[sichuan-full-batch] status"
python3 quwoquan_data/tools/cli.py crawl status --spec "$SPEC_PATH"
echo "[sichuan-full-batch] report: $REPORT_JSONL"
