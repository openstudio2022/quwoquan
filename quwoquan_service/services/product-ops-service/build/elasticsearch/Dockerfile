# 统一搜索读库 Elasticsearch 镜像：官方基镜像 + 中文检索插件。
#
# 设计裁决（specs/feature-tree/global-search-experience/design.md#dec-002）：
# 中文检索采用 analysis-ik（ik_max_word 索引 / ik_smart 查询）与 analysis-pinyin
# （仅 title/name 类短字段），放弃 OpenSearch 可移植假设。
#
# 插件 zip 由 Docker build 从 supply-chain.json 声明的 infinilabs 官方源下载，
# 并以固定 SHA-256 校验；禁止 mutable source fallback。
# 升级 ES 时同步升级两个插件并经 read/write alias 分离的零停机流程重建索引
# （analyzer 变更无法原地生效）。
#
# 构建（本地 gamma-local，Apple Silicon 需 SVE workaround）：
#   bash fetch_plugins.sh
#   docker build --build-arg PLUGIN_CLI_JAVA_OPTS="-XX:UseSVE=0" \
#     -t quwoquan/elasticsearch-cjk:8.13.4 \
#     quwoquan_service/services/product-ops-service/build/elasticsearch
# 发布（beta/gamma/prod）：推送私有 registry 后以 digest pin 回填
#   deploy/local-elasticsearch.compose.yaml 与 quwoquan_ops/environments/prod/access-isolation.yaml。
FROM docker.elastic.co/elasticsearch/elasticsearch@sha256:5af05323c9bfc52fcee63a47c682412a6ef5955ac85966f045a68ba8623db2e1

ARG ANALYSIS_IK_URL="https://release.infinilabs.com/analysis-ik/stable/elasticsearch-analysis-ik-8.13.4.zip"
ARG ANALYSIS_IK_SHA256="9fa37bad9da16a7d5b256bb5d3542eec5300b041c539c461fa9c24c4c41abd09"
ARG ANALYSIS_PINYIN_URL="https://release.infinilabs.com/analysis-pinyin/stable/elasticsearch-analysis-pinyin-8.13.4.zip"
ARG ANALYSIS_PINYIN_SHA256="3623d000644ed84ff6928bbdbe394343f2af66465afc6cba2606eeb95826d147"

# PLUGIN_CLI_JAVA_OPTS 只在构建期生效，不写入镜像环境：aarch64 宿主（Apple M 系列）
# 需要 -XX:UseSVE=0 规避 JDK SVE 探测崩溃（与 compose 的 cliJavaOpts 同一 workaround），
# 该选项在 amd64 JVM 上不可识别，因此不得 ENV 持久化。
ARG PLUGIN_CLI_JAVA_OPTS=""
ARG TARGETARCH

RUN curl --fail --location --retry 2 --connect-timeout 15 \
      --output /tmp/analysis-ik.zip "${ANALYSIS_IK_URL}" && \
    curl --fail --location --retry 2 --connect-timeout 15 \
      --output /tmp/analysis-pinyin.zip "${ANALYSIS_PINYIN_URL}" && \
    echo "${ANALYSIS_IK_SHA256}  /tmp/analysis-ik.zip" | sha256sum --check --strict && \
    echo "${ANALYSIS_PINYIN_SHA256}  /tmp/analysis-pinyin.zip" | sha256sum --check --strict && \
    cli_java_opts="${PLUGIN_CLI_JAVA_OPTS}" && \
    if [ -z "${cli_java_opts}" ] && [ "${TARGETARCH}" = "arm64" ]; then \
      cli_java_opts="-XX:UseSVE=0"; \
    fi && \
    CLI_JAVA_OPTS="${cli_java_opts}" bin/elasticsearch-plugin install --batch "file:///tmp/analysis-ik.zip" && \
    CLI_JAVA_OPTS="${cli_java_opts}" bin/elasticsearch-plugin install --batch "file:///tmp/analysis-pinyin.zip"
