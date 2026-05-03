#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FULL_MODE="${1:-}"

required_docs=(
  "specs/feature-tree/runtime/runtime-media/video-end-to-end-commercial-matrix.md"
  "specs/feature-tree/runtime/runtime-media/t4-release-rehearsal.md"
  "specs/feature-tree/runtime/runtime-media/observability-and-rollback.md"
  "specs/feature-tree/runtime/runtime-media/capacity-validation.md"
  "specs/feature-tree/runtime/runtime-media/automation-gates.md"
)

for relative_path in "${required_docs[@]}"; do
  if [[ ! -f "${ROOT_DIR}/${relative_path}" ]]; then
    echo "[runtime-media] FAIL: missing required artifact: ${relative_path}"
    exit 2
  fi
done

if [[ "${FULL_MODE}" == "--full" ]]; then
  evidence_path="${RUNTIME_MEDIA_T4_EVIDENCE:-}"
  if [[ -z "${evidence_path}" ]]; then
    echo "[runtime-media] FAIL: RUNTIME_MEDIA_T4_EVIDENCE is required for full gate"
    exit 2
  fi
  if [[ ! -f "${ROOT_DIR}/${evidence_path}" && ! -f "${evidence_path}" ]]; then
    echo "[runtime-media] FAIL: T4 evidence file not found: ${evidence_path}"
    exit 2
  fi
fi

echo "[runtime-media] go test runtime/sync internal/application chat-service/tests"
(
  cd "${ROOT_DIR}/quwoquan_service"
  go test ./runtime/sync ./services/chat-service/internal/application ./services/chat-service/tests
)

echo "[runtime-media] go test user-service avatar sync contract"
(
  cd "${ROOT_DIR}/quwoquan_service"
  go test ./services/user-service/tests -run TestUpdateProfile_AvatarVersionAndSyncPatch
)



echo "[runtime-media] image delivery policy static gates"
python3 "${ROOT_DIR}/scripts/verify_app_network_image_surface.py"
python3 "${ROOT_DIR}/scripts/verify_app_media_url_policy.py"
python3 "${ROOT_DIR}/scripts/verify_media_variant_registry_metadata.py"

echo "[runtime-media] flutter test realtime/cache coverage"
(
  cd "${ROOT_DIR}/quwoquan_app"
  flutter test \
    test/cloud/realtime/realtime_avatar_sync_handler_test.dart \
    test/core/services/local_chat_search_sync_service_test.dart \
    test/ui/chat/widgets/chat_page_widget_test.dart
)

if [[ "${FULL_MODE}" == "--full" ]]; then
  echo "[runtime-media] full gate passed with external T4 evidence: ${RUNTIME_MEDIA_T4_EVIDENCE}"
else
  echo "[runtime-media] local gate passed. Run gate-runtime-media-full with RUNTIME_MEDIA_T4_EVIDENCE for release-level closure."
fi
