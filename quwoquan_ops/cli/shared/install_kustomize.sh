#!/usr/bin/env bash
set -euo pipefail

KUSTOMIZE_VERSION="${KUSTOMIZE_VERSION:-v5.8.1}"
KUSTOMIZE_REPO_TAG="kustomize/${KUSTOMIZE_VERSION}"
INSTALL_DIR="${KUSTOMIZE_INSTALL_DIR:-${RUNNER_TEMP:-$HOME/.local/bin}/kustomize-bin}"

os="$(uname -s | tr '[:upper:]' '[:lower:]')"
arch="$(uname -m)"

case "${arch}" in
  x86_64 | amd64)
    arch="amd64"
    ;;
  arm64 | aarch64)
    arch="arm64"
    ;;
  *)
    echo "unsupported architecture: ${arch}" >&2
    exit 2
    ;;
esac

case "${os}" in
  linux | darwin)
    ;;
  *)
    echo "unsupported operating system: ${os}" >&2
    exit 2
    ;;
esac

archive_name="kustomize_${KUSTOMIZE_VERSION}_${os}_${arch}.tar.gz"
release_base_url="https://github.com/kubernetes-sigs/kustomize/releases/download/${KUSTOMIZE_REPO_TAG}"
checksum_url="${release_base_url}/checksums.txt"
archive_url="${release_base_url}/${archive_name}"
work_dir="$(mktemp -d)"

cleanup() {
  rm -rf "${work_dir}"
}
trap cleanup EXIT

download() {
  local url="$1"
  local output="$2"
  curl \
    --fail \
    --location \
    --retry 5 \
    --retry-delay 2 \
    --retry-all-errors \
    --connect-timeout 15 \
    --max-time 300 \
    --silent \
    --show-error \
    "${url}" \
    --output "${output}"
}

echo "Installing kustomize ${KUSTOMIZE_VERSION} for ${os}/${arch}"
download "${checksum_url}" "${work_dir}/checksums.txt"
download "${archive_url}" "${work_dir}/${archive_name}"

expected_sha="$(awk -v name="${archive_name}" '$2 == name { print $1 }' "${work_dir}/checksums.txt")"
if [ -z "${expected_sha}" ]; then
  echo "failed to resolve checksum for ${archive_name}" >&2
  exit 2
fi

actual_sha="$(shasum -a 256 "${work_dir}/${archive_name}" | awk '{ print $1 }')"
if [ "${actual_sha}" != "${expected_sha}" ]; then
  echo "checksum mismatch for ${archive_name}" >&2
  echo "expected: ${expected_sha}" >&2
  echo "actual:   ${actual_sha}" >&2
  exit 2
fi

tar -xzf "${work_dir}/${archive_name}" -C "${work_dir}"

mkdir -p "${INSTALL_DIR}"
install -m 0755 "${work_dir}/kustomize" "${INSTALL_DIR}/kustomize"

if [ -n "${GITHUB_PATH:-}" ]; then
  echo "${INSTALL_DIR}" >> "${GITHUB_PATH}"
fi

if [ -n "${GITHUB_OUTPUT:-}" ]; then
  echo "kustomize_path=${INSTALL_DIR}/kustomize" >> "${GITHUB_OUTPUT}"
fi

"${INSTALL_DIR}/kustomize" version
