#!/usr/bin/env bash
# 获取与基镜像 ES 版本严格一致的 analysis-ik / analysis-pinyin 插件 zip。
#
# 仅从版本控制 supply-chain.json 声明的官方发布源下载，并校验固定 SHA-256。
# 禁止回退 mutable 8.x HEAD；官方源不可达时 fail-closed。
# 产物落在本目录，供 Dockerfile COPY；zip 不入 git（.gitignore）。
set -euo pipefail

ES_VERSION="${ES_VERSION:-8.13.4}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

download() {
  local name="$1"
  local url="$2"
  local checksum="$3"
  local target="${SCRIPT_DIR}/elasticsearch-${name}-${ES_VERSION}.zip"
  if [[ -f "${target}" ]] && echo "${checksum}  ${target}" | shasum -a 256 -c - >/dev/null; then
    echo "verified: ${target}"
    return
  fi
  local temporary="${target}.download"
  rm -f "${temporary}"
  curl -fL --retry 2 --connect-timeout 15 -o "${temporary}" "${url}"
  echo "${checksum}  ${temporary}" | shasum -a 256 -c -
  mv "${temporary}" "${target}"
  echo "downloaded and verified: ${target}"
}

download \
  analysis-ik \
  "https://release.infinilabs.com/analysis-ik/stable/elasticsearch-analysis-ik-${ES_VERSION}.zip" \
  "9fa37bad9da16a7d5b256bb5d3542eec5300b041c539c461fa9c24c4c41abd09"
download \
  analysis-pinyin \
  "https://release.infinilabs.com/analysis-pinyin/stable/elasticsearch-analysis-pinyin-${ES_VERSION}.zip" \
  "3623d000644ed84ff6928bbdbe394343f2af66465afc6cba2606eeb95826d147"
shasum -a 256 "${SCRIPT_DIR}"/elasticsearch-*-"${ES_VERSION}".zip
