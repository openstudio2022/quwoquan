#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FULL_MODE="${1:-}"

required_docs=(
  "specs/feature-tree/runtime/runtime-media/video-end-to-end-commercial-matrix.md"
  "specs/feature-tree/runtime/runtime-media/image-end-to-end-commercial-matrix.md"
  "specs/feature-tree/runtime/runtime-media/t4-release-rehearsal.md"
  "specs/feature-tree/runtime/runtime-media/observability-and-rollback.md"
  "specs/feature-tree/runtime/runtime-media/capacity-validation.md"
  "specs/feature-tree/runtime/runtime-media/automation-gates.md"
  "specs/feature-tree/runtime/runtime-client-foundation/local-cache-architecture/spec.md"
  "specs/feature-tree/runtime/runtime-client-foundation/local-cache-architecture/object-cache-policy.yaml"
  "specs/feature-tree/runtime/runtime-client-foundation/local-cache-architecture/cache-management-runbook.md"
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
  python3 "${ROOT_DIR}/quwoquan_ops/gate/verify_runtime_media_t4_evidence.py" \
    --evidence "${evidence_path}"
fi

echo "[runtime-media] go test runtime/sync internal/application chat-service/tests/local_contract"
(
  cd "${ROOT_DIR}/quwoquan_service"
  go test ./runtime/sync ./services/chat-service/internal/application ./services/chat-service/tests/local_contract
)

echo "[runtime-media] go test user-service avatar sync contract"
(
  cd "${ROOT_DIR}/quwoquan_service"
  go test ./services/user-service/tests/api_integration -run TestUpdateProfile_AvatarVersionAndSyncPatch
)



echo "[runtime-media] image delivery policy static gates"
python3 "${ROOT_DIR}/quwoquan_app/scripts/media/verify_app_network_image_surface.py"
python3 "${ROOT_DIR}/quwoquan_app/scripts/media/verify_app_avatar_rendering_policy.py"
python3 "${ROOT_DIR}/quwoquan_app/scripts/chat/verify_chat_mock_remote_parity.py"
python3 "${ROOT_DIR}/quwoquan_app/scripts/media/verify_app_media_url_policy.py"
python3 "${ROOT_DIR}/quwoquan_service/scripts/media/verify_media_variant_registry_metadata.py"
python3 "${ROOT_DIR}/quwoquan_ops/gate/verify_media_delivery_contract.py"

echo "[runtime-media] video delivery and playback failure contracts"
(
  cd "${ROOT_DIR}/quwoquan_app"
  python3 scripts/env/run_flutter_test_guarded.py \
    test/local_contract/core/media/media_delivery_reference__local_contract_test.dart \
    test/local_contract/core/media/media_load_failure_cache__local_contract_test.dart \
    test/local_contract/core/media/media_playback_failure__local_contract_test.dart \
    test/local_contract/ui/components/media/video/video_player_widget__delivery_binding__local_contract_test.dart \
    test/local_contract/ui/components/media/video/video_player_widget__failure_experience__local_contract_test.dart
)
(
  cd "${ROOT_DIR}"
  python3 -m unittest \
    quwoquan_ops.tests.local_contract.test_environment_patrol_smoke__local_contract_test \
    quwoquan_ops.tests.local_contract.test_local_gamma_media__local_contract_test \
    quwoquan_ops.tests.local_contract.test_local_target_tls__local_contract_test \
    quwoquan_ops.tests.local_contract.test_runtime_media_t4_evidence__local_contract_test \
    quwoquan_ops.tests.local_contract.test_video_playback_canary__local_contract_test
)
(
  cd "${ROOT_DIR}/quwoquan_service"
  go test ./services/content-service/internal/application/post
)

echo "[runtime-media] alpha HTTPS media fixture surface gate"
QWQ_ALPHA_LOCAL_PUBLIC_HOST_SETUP=skip bash "${ROOT_DIR}/quwoquan_ops/cli/alpha/start_alpha_mock_stack.sh" up
python3 "${ROOT_DIR}/quwoquan_ops/gate/verify_alpha_media_fixture_surface.py"

echo "[runtime-media] flutter test realtime/cache coverage"
(
  cd "${ROOT_DIR}/quwoquan_app"
  python3 scripts/env/run_flutter_test_guarded.py \
    test/local_contract/core/services/content_cache_services__local_contract_test.dart \
    test/local_contract/core/services/conversation_avatar_sync_contract__local_contract_test.dart \
    test/local_contract/ui/components/avatar/conversation_avatar__local_contract_test.dart \
    test/local_contract/cloud/realtime/realtime_avatar_sync_handler__local_contract_test.dart \
    test/local_contract/core/services/local_chat_search_sync_service__local_contract_test.dart \
    test/local_contract/ui/chat/widgets/chat_page_widget__local_contract_test.dart
)

if [[ "${FULL_MODE}" == "--full" ]]; then
  echo "[runtime-media] full gate passed with external T4 evidence: ${RUNTIME_MEDIA_T4_EVIDENCE}"
else
  echo "[runtime-media] local gate passed. Run gate-runtime-media-full with RUNTIME_MEDIA_T4_EVIDENCE for release-level closure."
fi
