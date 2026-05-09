#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[verify] quwoquan_data"

TMP_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMP_ROOT"' EXIT

RUNTIME_ROOT="$TMP_ROOT/runtime"
export QWQ_DATA_ROOT="$ROOT/quwoquan_data"
export QWQ_RUNTIME_ROOT="$RUNTIME_ROOT"

python3 - <<'PY'
from pathlib import Path
import shutil
import os

fixture_root = Path(os.environ["QWQ_DATA_ROOT"]) / "tests" / "fixtures" / "runtime_seed"
runtime_root = Path(os.environ["QWQ_RUNTIME_ROOT"])
for child in ("trees",):
    source = fixture_root / child
    target = runtime_root / child
    if source.exists():
        shutil.copytree(source, target, dirs_exist_ok=True)
for child in ("runs", "publish", "out", "downloads"):
    (runtime_root / child).mkdir(parents=True, exist_ok=True)
PY

SPEC="$RUNTIME_ROOT/specs/real_public_examples_001.yaml"
mkdir -p "$(dirname "$SPEC")"
cat > "$SPEC" <<'EOF'
spec_id: real_public_examples_001
query: 杭州西湖 真实公开来源 样例
search_provider: native_fetch
entity_refs:
  - trees/entities/地点/西湖.yaml
  - trees/entities/住宿/西湖亲子友好酒店.yaml
  - trees/entities/本地生活/龙井路咖啡.yaml
tag_refs:
  - trees/tags/主题/城市漫游.yaml
  - trees/tags/场景/周末一日.yaml
  - trees/tags/人群/亲子.yaml
  - trees/tags/质量/高置信.yaml
  - trees/tags/主题/湖景.yaml
target_envs:
  - alpha
  - gamma
creator_refs:
  article:
    - fixture_user_travel
  image:
    - fixture_user_photo
publish_policy:
  visibility: public
  assistant_use_policy: inherit
discovery_policy:
  min_article_topics: 1
  min_image_topics: 1
  min_candidate_sources_per_task: 1
  min_article_publish_topics: 1
  min_image_publish_topics: 1
article_lane:
  allow_domains:
    - zh.wikivoyage.org
    - zh.wikipedia.org
    - commons.wikimedia.org
    - upload.wikimedia.org
image_lane:
  allow_domains:
    - commons.wikimedia.org
    - upload.wikimedia.org
sample_topics:
  article:
    - real_west_lake_article_001
  image:
    - real_west_lake_image_001
EOF

python3 quwoquan_data/tools/cli.py tree validate --tree all
python3 quwoquan_data/tools/cli.py crawl spec-discovery --spec "$SPEC"
python3 quwoquan_data/tools/cli.py crawl status --spec "$SPEC"

python3 quwoquan_data/tools/cli.py crawl fetch-source --spec "$SPEC" --topic real_west_lake_article_001 --task-type article --source-id real_west_lake_article_source_001 --url "https://zh.wikivoyage.org/wiki/%E6%9D%AD%E5%B7%9E" --title "第一次逛杭州，先把西湖这条线走顺" --query "杭州 西湖 旅行指南 步行" --snippet "中文 Wikivoyage 杭州词条把西湖、湖滨和城市步行节奏写成了旅行指南，更适合重组为用户可读长文。" --rights-status clear --watermark-status clean
python3 quwoquan_data/tools/cli.py crawl fetch-source --spec "$SPEC" --topic real_west_lake_image_001 --task-type image --source-id real_west_lake_image_source_001 --url "https://commons.wikimedia.org/wiki/File:West_Lake_-_Hangzhou,_China.jpg" --title "雷峰塔视角下的西湖开阔湖面" --query "West Lake Hangzhou Commons image" --snippet "真实来源基于 Wikimedia Commons 文件页，来源页明确写出作者、拍摄时间和 CC BY-SA 3.0 授权。" --rights-status clear --watermark-status clean

python3 quwoquan_data/tools/cli.py crawl run-topic --spec "$SPEC" --topic real_west_lake_article_001 --targets alpha,gamma --dry-run
python3 quwoquan_data/tools/cli.py crawl run-topic --spec "$SPEC" --topic real_west_lake_image_001 --targets alpha,gamma --dry-run
python3 quwoquan_data/tools/cli.py crawl status --spec "$SPEC"

python3 scripts/verify_quwoquan_data_source_authenticity.py
python3 scripts/verify_markdown_article_no_article_document.py
python3 scripts/verify_quwoquan_data_post_packages.py
python3 -m unittest discover -s quwoquan_data/tests
(cd quwoquan_app && flutter test test/ui/content/markdown/qwq_markdown_generated_package_test.dart)

echo "[verify] OK: quwoquan_data"
