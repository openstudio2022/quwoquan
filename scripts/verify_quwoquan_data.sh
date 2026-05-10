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

retry_cmd() {
  local attempts=0
  until "$@"; do
    attempts=$((attempts + 1))
    if [[ "$attempts" -ge 3 ]]; then
      return 1
    fi
    sleep "$attempts"
  done
}

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
  min_article_topics: 6
  min_image_topics: 1
  min_candidate_sources_per_task: 1
  min_article_publish_topics: 6
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
    - real_west_lake_article_002
    - real_west_lake_article_003
    - real_west_lake_article_004
    - real_west_lake_article_005
    - real_west_lake_article_006
  image:
    - real_west_lake_image_001
EOF

python3 quwoquan_data/tools/cli.py tree validate --tree all
python3 quwoquan_data/tools/cli.py crawl spec-discovery --spec "$SPEC"
python3 quwoquan_data/tools/cli.py crawl status --spec "$SPEC"

retry_cmd python3 quwoquan_data/tools/cli.py crawl fetch-source --spec "$SPEC" --topic real_west_lake_article_001 --task-type article --source-id real_west_lake_article_001_source_001 --url "https://zh.wikivoyage.org/wiki/%E6%9D%AD%E5%B7%9E" --title "第一次逛杭州，先把西湖这条线走顺" --query "杭州 西湖 旅行指南 步行" --snippet "中文 Wikivoyage 杭州词条把西湖、湖滨和步行节奏写成了旅行指南，适合重组为第一次来杭州的西湖长文。" --rights-status clear --watermark-status clean
retry_cmd python3 quwoquan_data/tools/cli.py crawl fetch-source --spec "$SPEC" --topic real_west_lake_article_002 --task-type article --source-id real_west_lake_article_002_source_001 --url "https://zh.wikivoyage.org/wiki/%E6%9D%AD%E5%B7%9E" --title "想把雷峰塔和南线湖景留给一下午" --query "杭州 西湖 雷峰塔 南线 散步" --snippet "杭州词条里的西湖南线、湖滨和步行节奏，适合与雷峰塔页面拼成一篇南线长文。" --rights-status clear --watermark-status clean
retry_cmd python3 quwoquan_data/tools/cli.py crawl fetch-source --spec "$SPEC" --topic real_west_lake_article_002 --task-type article --source-id real_west_lake_article_002_source_002 --url "https://zh.wikipedia.org/wiki/%E9%9B%B7%E5%B3%B0%E5%A1%94" --title "雷峰塔与南线塔景" --query "雷峰塔 西湖 南线" --snippet "雷峰塔词条补足塔影、旧塔新塔和南线回望湖面的线索，适合和杭州旅行页一起重组。" --rights-status clear --watermark-status clean
retry_cmd python3 quwoquan_data/tools/cli.py crawl fetch-source --spec "$SPEC" --topic real_west_lake_article_003 --task-type article --source-id real_west_lake_article_003_source_001 --url "https://zh.wikivoyage.org/wiki/%E6%9D%AD%E5%B7%9E" --title "第一次来西湖，不必一次追完十景" --query "西湖十景 初次游览 路线" --snippet "杭州旅行页里的西湖和湖滨节奏，适合与十景词条一起整理成第一次来西湖的取舍建议。" --rights-status clear --watermark-status clean
retry_cmd python3 quwoquan_data/tools/cli.py crawl fetch-source --spec "$SPEC" --topic real_west_lake_article_003 --task-type article --source-id real_west_lake_article_003_source_002 --url "https://zh.wikipedia.org/wiki/%E8%A5%BF%E6%B9%96%E5%8D%81%E6%99%AF" --title "西湖十景与经典看景顺序" --query "西湖十景 经典看景" --snippet "西湖十景词条把最经典的画面线索和名字梳理得很集中，适合支撑一篇第一次来西湖的长文。" --rights-status clear --watermark-status clean
retry_cmd python3 quwoquan_data/tools/cli.py crawl fetch-source --spec "$SPEC" --topic real_west_lake_article_004 --task-type article --source-id real_west_lake_article_004_source_001 --url "https://zh.wikivoyage.org/wiki/%E6%9D%AD%E5%B7%9E" --title "想把苏堤走舒服，就把脚步放慢" --query "苏堤 西湖 散步 杭州" --snippet "杭州旅行页适合作为苏堤步行文章的路线底稿，再用苏堤词条补足长堤与湖面的信息。" --rights-status clear --watermark-status clean
retry_cmd python3 quwoquan_data/tools/cli.py crawl fetch-source --spec "$SPEC" --topic real_west_lake_article_004 --task-type article --source-id real_west_lake_article_004_source_002 --url "https://zh.wikipedia.org/wiki/%E8%8B%8F%E5%A0%A4" --title "苏堤与湖面步行线" --query "苏堤 西湖 步行线" --snippet "苏堤词条补足长堤、南北贯通和沿线看湖的线索，适合和杭州词条一起重组。" --rights-status clear --watermark-status clean
retry_cmd python3 quwoquan_data/tools/cli.py crawl fetch-source --spec "$SPEC" --topic real_west_lake_article_005 --task-type article --source-id real_west_lake_article_005_source_001 --url "https://zh.wikivoyage.org/wiki/%E6%9D%AD%E5%B7%9E" --title "清晨沿着白堤走，西湖会更耐看" --query "白堤 西湖 清晨 散步" --snippet "杭州旅行页里的西湖步行节奏，适合和白堤页面拼成一篇更轻更慢的清晨散步稿。" --rights-status clear --watermark-status clean
retry_cmd python3 quwoquan_data/tools/cli.py crawl fetch-source --spec "$SPEC" --topic real_west_lake_article_005 --task-type article --source-id real_west_lake_article_005_source_002 --url "https://zh.wikipedia.org/wiki/%E7%99%BD%E5%A0%A4" --title "白堤与断桥一侧的湖面" --query "白堤 断桥 西湖" --snippet "白堤词条更适合补足清晨沿湖、堤岸步行和断桥一侧的看景方式。" --rights-status clear --watermark-status clean
retry_cmd python3 quwoquan_data/tools/cli.py crawl fetch-source --spec "$SPEC" --topic real_west_lake_article_006 --task-type article --source-id real_west_lake_article_006_source_001 --url "https://zh.wikivoyage.org/wiki/%E6%9D%AD%E5%B7%9E" --title "如果想坐船看湖，就把时间留给三潭印月" --query "三潭印月 西湖 坐船 杭州" --snippet "杭州旅行页里的游船、湖滨和沿湖停留点，适合和三潭印月页面组合成一篇坐船看湖的西湖长文。" --rights-status clear --watermark-status clean
retry_cmd python3 quwoquan_data/tools/cli.py crawl fetch-source --spec "$SPEC" --topic real_west_lake_article_006 --task-type article --source-id real_west_lake_article_006_source_002 --url "https://zh.wikipedia.org/wiki/%E4%B8%89%E6%BD%AD%E5%8D%B0%E6%9C%88" --title "三潭印月与船上视角" --query "三潭印月 西湖 游船" --snippet "三潭印月词条补足岛上视角、船程和经典湖景画面，适合支撑坐船看湖的内容。" --rights-status clear --watermark-status clean
retry_cmd python3 quwoquan_data/tools/cli.py crawl fetch-source --spec "$SPEC" --topic real_west_lake_image_001 --task-type image --source-id real_west_lake_image_source_001 --url "https://commons.wikimedia.org/wiki/File:West_Lake_-_Hangzhou,_China.jpg" --title "雷峰塔视角下的西湖开阔湖面" --query "West Lake Hangzhou Commons image" --snippet "真实来源基于 Wikimedia Commons 文件页，来源页明确写出作者、拍摄时间和 CC BY-SA 3.0 授权。" --rights-status clear --watermark-status clean

python3 quwoquan_data/tools/cli.py crawl compose-topic --spec "$SPEC" --topic real_west_lake_article_001 --targets alpha,gamma --dry-run
python3 quwoquan_data/tools/cli.py crawl compose-topic --spec "$SPEC" --topic real_west_lake_article_002 --targets alpha,gamma --dry-run
python3 quwoquan_data/tools/cli.py crawl compose-topic --spec "$SPEC" --topic real_west_lake_article_003 --targets alpha,gamma --dry-run
python3 quwoquan_data/tools/cli.py crawl compose-topic --spec "$SPEC" --topic real_west_lake_article_004 --targets alpha,gamma --dry-run
python3 quwoquan_data/tools/cli.py crawl compose-topic --spec "$SPEC" --topic real_west_lake_article_005 --targets alpha,gamma --dry-run
python3 quwoquan_data/tools/cli.py crawl compose-topic --spec "$SPEC" --topic real_west_lake_article_006 --targets alpha,gamma --dry-run
python3 quwoquan_data/tools/cli.py crawl compose-topic --spec "$SPEC" --topic real_west_lake_image_001 --targets alpha,gamma --dry-run
python3 quwoquan_data/tools/cli.py crawl audit-topic --spec "$SPEC" --topic real_west_lake_article_001
python3 quwoquan_data/tools/cli.py crawl audit-topic --spec "$SPEC" --topic real_west_lake_article_002
python3 quwoquan_data/tools/cli.py crawl audit-topic --spec "$SPEC" --topic real_west_lake_article_003
python3 quwoquan_data/tools/cli.py crawl audit-topic --spec "$SPEC" --topic real_west_lake_article_004
python3 quwoquan_data/tools/cli.py crawl audit-topic --spec "$SPEC" --topic real_west_lake_article_005
python3 quwoquan_data/tools/cli.py crawl audit-topic --spec "$SPEC" --topic real_west_lake_article_006
python3 quwoquan_data/tools/cli.py crawl audit-topic --spec "$SPEC" --topic real_west_lake_image_001
python3 quwoquan_data/tools/cli.py crawl status --spec "$SPEC"

python3 scripts/verify_quwoquan_data_source_authenticity.py
python3 scripts/verify_markdown_article_no_article_document.py
python3 scripts/verify_quwoquan_data_post_packages.py
python3 -m unittest discover -s quwoquan_data/tests
(cd quwoquan_app && flutter test test/ui/content/markdown/qwq_markdown_generated_package_test.dart)

echo "[verify] OK: quwoquan_data"
