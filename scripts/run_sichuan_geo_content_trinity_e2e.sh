#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RUNTIME="${QWQ_RUNTIME_ROOT:-$ROOT/quwoquan_data/runtime}"
export QWQ_DATA_ROOT="${QWQ_DATA_ROOT:-$ROOT/quwoquan_data}"
export QWQ_RUNTIME_ROOT="$RUNTIME"
export QWQ_REPO_ROOT="${QWQ_REPO_ROOT:-$ROOT}"

DOC_ROOT="$ROOT/specs/feature-tree/runtime/runtime-data-engineering/geo-content-trinity"
CONFIG="$DOC_ROOT/config/geo_catalog_config.sichuan.yaml"
NAMING="$DOC_ROOT/config/entity_naming_rules.yaml"
WORKFLOW_DOC="$DOC_ROOT/workflow.md"
COMMAND_DOC="$DOC_ROOT/command-matrix.md"
SPEC_DOC="$DOC_ROOT/spec.md"
DESIGN_DOC="$DOC_ROOT/design.md"
ACCEPTANCE_DOC="$DOC_ROOT/acceptance.yaml"
SEED_FILE="$DOC_ROOT/samples/sichuan_geo_content_e2e_seed.ndjson"
SAMPLE_CATALOG_SEED="$DOC_ROOT/samples/sichuan_geo_content_e2e_catalog.ndjson"

FULL_CATALOG="$RUNTIME/seed/sichuan_geo_content_e2e_catalog.ndjson"
SLICE_REPORT="$RUNTIME/out/reports/sichuan_geo_content_e2e_slice_report.json"
SAMPLE_ENTITY_CATALOG="$RUNTIME/seed/sichuan_geo_content_e2e_sample_entities.ndjson"
SAMPLE_ARTICLE_CATALOG="$RUNTIME/seed/sichuan_geo_content_e2e_article_topics.ndjson"
SPEC_ID="sichuan_geo_content_e2e_sample_001"
SPEC_PATH="$RUNTIME/specs/${SPEC_ID}.yaml"

TOPICS_CSV="poi_way_299409723,poi_way_412705835,poi_node_620388965"

echo "[sichuan-e2e] reset runtime"
bash "$ROOT/scripts/reset_quwoquan_data_runtime_full.sh"

echo "[sichuan-e2e] baseline check"
python3 quwoquan_data/tools/cli.py data baseline \
  --spec-doc "$SPEC_DOC" \
  --design-doc "$DESIGN_DOC" \
  --acceptance-doc "$ACCEPTANCE_DOC" \
  --workflow-doc "$WORKFLOW_DOC" \
  --command-matrix-doc "$COMMAND_DOC" \
  --catalog-config "$CONFIG" \
  --naming-rules "$NAMING" \
  --schema-files \
    quwoquan_data/schema/geo_catalog_row.schema.json \
    quwoquan_data/schema/entity_catalog_row.schema.json \
    quwoquan_data/schema/tag_catalog_row.schema.json \
    quwoquan_data/schema/authority_pool_row.schema.json \
    quwoquan_data/schema/source_pool_row.schema.json

echo "[sichuan-e2e] install sample catalog seed"
mkdir -p "$(dirname "$FULL_CATALOG")" "$(dirname "$SLICE_REPORT")"
cp "$SAMPLE_CATALOG_SEED" "$FULL_CATALOG"
FULL_CATALOG="$FULL_CATALOG" SLICE_REPORT="$SLICE_REPORT" python3 - <<'PY'
from pathlib import Path
import json
import os

catalog_path = Path(os.environ["FULL_CATALOG"])
report_path = Path(os.environ["SLICE_REPORT"])
rows = [json.loads(line) for line in catalog_path.read_text(encoding="utf-8").splitlines() if line.strip()]
report = {
    "schemaVersion": "quwoquan_data.geo_catalog_slice_report",
    "generatedAt": "seeded",
    "configPath": "specs/feature-tree/runtime/runtime-data-engineering/geo-content-trinity/samples/sichuan_geo_content_e2e_catalog.ndjson",
    "outputPath": "quwoquan_data/runtime/seed/sichuan_geo_content_e2e_catalog.ndjson",
    "scopeName": "四川样例",
    "rawCount": len(rows),
    "keptCount": len(rows),
    "nameDedupedCount": 0,
    "slices": [
        {
            "sliceName": "四川样例",
            "rawCount": len(rows),
            "areaProbeCount": -1,
            "rejectCounts": {},
            "keptPreDedupe": len(rows),
        }
    ],
}
report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

echo "[sichuan-e2e] derive sample catalogs and spec inputs"
TOPICS_CSV="$TOPICS_CSV" SAMPLE_ENTITY_CATALOG="$SAMPLE_ENTITY_CATALOG" SAMPLE_ARTICLE_CATALOG="$SAMPLE_ARTICLE_CATALOG" FULL_CATALOG="$FULL_CATALOG" RUNTIME="$RUNTIME" SPEC_ID="$SPEC_ID" python3 - <<'PY'
import json
import os
from pathlib import Path

runtime = Path(os.environ["RUNTIME"])
full_catalog = Path(os.environ["FULL_CATALOG"])
sample_entity_catalog = Path(os.environ["SAMPLE_ENTITY_CATALOG"])
sample_article_catalog = Path(os.environ["SAMPLE_ARTICLE_CATALOG"])
topics = [x.strip() for x in os.environ["TOPICS_CSV"].split(",") if x.strip()]
image_topics = {"poi_node_620388965"}
article_topics = set(topics) - image_topics

rows = [json.loads(line) for line in full_catalog.read_text(encoding="utf-8").splitlines() if line.strip()]
sample_rows = [row for row in rows if str(row.get("topic_id") or "").strip() in topics]
article_rows = [row for row in sample_rows if str(row.get("topic_id") or "").strip() in article_topics]
sample_entity_catalog.parent.mkdir(parents=True, exist_ok=True)
sample_entity_catalog.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in sample_rows), encoding="utf-8")
sample_article_catalog.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in article_rows), encoding="utf-8")

runs_dir = runtime / "runs" / os.environ["SPEC_ID"]
runs_dir.mkdir(parents=True, exist_ok=True)
PY

echo "[sichuan-e2e] build entity/tag catalogs from full catalog"
python3 quwoquan_data/tools/cli.py data build-entities-tags --catalog "$FULL_CATALOG"

echo "[sichuan-e2e] create instruction profile"
python3 quwoquan_data/tools/cli.py crawl instruction-build \
  --spec-id "$SPEC_ID" \
  --instruction "四川样例 E2E：杜甫草堂、四川博物院、都江堰与乐山大佛的图文闭环" \
  --tag-refs "trees/tags/主题/旅行攻略.yaml" \
  --verticals "travel" \
  --content-modes "article,image" \
  --regions "四川,成都,乐山"

echo "[sichuan-e2e] materialize selected_entities / selected_tags / spec"
SPEC_ID="$SPEC_ID" RUNTIME="$RUNTIME" SAMPLE_ARTICLE_CATALOG="$SAMPLE_ARTICLE_CATALOG" TOPICS_CSV="$TOPICS_CSV" python3 - <<'PY'
import json
import os
from pathlib import Path

import yaml

runtime = Path(os.environ["RUNTIME"])
spec_id = os.environ["SPEC_ID"]
sample_article_catalog = Path(os.environ["SAMPLE_ARTICLE_CATALOG"])
topics = [x.strip() for x in os.environ["TOPICS_CSV"].split(",") if x.strip()]
image_topics = ["poi_node_620388965"]

entity_catalog = runtime / "seed" / "entity_catalog" / "entities.ndjson"
tag_catalog = runtime / "seed" / "tag_catalog" / "tags.ndjson"
entities = [json.loads(line) for line in entity_catalog.read_text(encoding="utf-8").splitlines() if line.strip()]
tags = [json.loads(line) for line in tag_catalog.read_text(encoding="utf-8").splitlines() if line.strip()]
selected_entities = [row for row in entities if str(row.get("topicId") or "").strip() in topics]
selected_tags = [row for row in tags if str(row.get("tagRef") or "").strip() == "trees/tags/主题/旅行攻略.yaml"]

runs_dir = runtime / "runs" / spec_id
runs_dir.mkdir(parents=True, exist_ok=True)
(runs_dir / "selected_entities.ndjson").write_text(
    "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in selected_entities),
    encoding="utf-8",
)
(runs_dir / "selected_tags.ndjson").write_text(
    "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in selected_tags),
    encoding="utf-8",
)

payload = {
    "spec_id": spec_id,
  "query": "四川样例 E2E：杜甫草堂、都江堰与乐山大佛",
    "search_provider": "native_fetch",
    "article_topic_catalog_ref": sample_article_catalog.resolve().relative_to(runtime).as_posix(),
    "entity_refs": ["trees/entities/地点/成都.yaml", "trees/entities/地点/川西.yaml"],
    "tag_refs": ["trees/tags/主题/旅行攻略.yaml"],
    "target_envs": ["alpha", "gamma"],
    "creator_refs": {
        "article": ["fixture_user_travel", "fixture_user_article"],
        "image": ["fixture_user_photo"],
    },
    "publish_policy": {"visibility": "public", "assistant_use_policy": "inherit"},
    "discovery_policy": {
        "min_article_topics": 2,
        "min_image_topics": 1,
        "min_candidate_sources_per_task": 1,
        "min_article_publish_topics": 2,
        "min_image_publish_topics": 1,
    },
    "article_lane": {
        "allow_domains": [
            "zh.wikipedia.org",
            "zh.wikivoyage.org",
            "www.zhihu.com",
            "www.mafengwo.cn",
            "you.ctrip.com",
        ]
    },
    "image_lane": {
        "allow_domains": [
            "commons.wikimedia.org",
            "upload.wikimedia.org",
        ]
    },
    "sample_topics": {
        "article": [],
        "image": image_topics,
    },
    "extensions": {
        "topicCount": len(topics),
        "skipHydrateRecommended": False,
        "largeTopicMode": False,
        "suggestedBatchSize": len(topics),
    },
}

spec_path = runtime / "specs" / f"{spec_id}.yaml"
spec_path.parent.mkdir(parents=True, exist_ok=True)
spec_path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
PY

echo "[sichuan-e2e] download via fetch seed"
python3 quwoquan_data/tools/cli.py data download \
  --spec "$SPEC_PATH" \
  --fetch-seed "$SEED_FILE" \
  --skip-authority-sync \
  --skip-pool-bootstrap \
  --skip-content-discover \
  --skip-hydrate

echo "[sichuan-e2e] process content"
python3 quwoquan_data/tools/cli.py data process-content \
  --spec "$SPEC_PATH" \
  --topics "$TOPICS_CSV" \
  --targets "alpha,gamma"

echo "[sichuan-e2e] publish and verify"
python3 quwoquan_data/tools/cli.py data publish \
  --spec "$SPEC_PATH" \
  --topics "$TOPICS_CSV"

echo "[sichuan-e2e] verify catalog + entity consistency on current runtime"
python3 scripts/verify_geo_catalog_quality.py --catalog "$FULL_CATALOG" --report "$SLICE_REPORT"
python3 scripts/verify_catalog_entity_consistency.py --catalog "$FULL_CATALOG"

echo "[sichuan-e2e] final status"
python3 quwoquan_data/tools/cli.py crawl status --spec "$SPEC_PATH"
