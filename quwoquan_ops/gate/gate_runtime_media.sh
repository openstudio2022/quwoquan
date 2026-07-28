#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FULL_MODE="${1:-}"

required_specs=(
  "specs/feature-tree/runtime/runtime-media/spec.md"
  "specs/feature-tree/runtime/runtime-media/design.md"
  "specs/feature-tree/runtime/runtime-media/media-upload-and-storage/spec.md"
  "specs/feature-tree/runtime/runtime-media/group-avatar-server-precompose-and-unified-sync-contract/spec.md"
  "specs/feature-tree/discovery-content/media-processing-helper-read/spec.md"
  "specs/feature-tree/discovery-content/media-processing-helper-read/design.md"
  "specs/feature-tree/runtime/runtime-client-foundation/local-cache-architecture/spec.md"
)

for relative_path in "${required_specs[@]}"; do
  if [[ ! -f "${ROOT_DIR}/${relative_path}" ]]; then
    echo "[runtime-media] FAIL: missing current feature spec/design: ${relative_path}"
    exit 2
  fi
done

PYTHONDONTWRITEBYTECODE=1 python3 \
  "${ROOT_DIR}/quwoquan_ops/cli/feature_tree.py" verify

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
    --evidence "${evidence_path}" \
    --require-matrix
fi

echo "[runtime-media] go test runtime/sync internal/application chat-service/tests/local_contract"
(
  cd "${ROOT_DIR}/quwoquan_service"
  go test ./runtime/sync ./services/chat-service/internal/chat/conversation/application ./services/chat-service/tests/local_contract/chat/conversation
)

echo "[runtime-media] go test user-service avatar sync contract"
(
  cd "${ROOT_DIR}/quwoquan_service"
  go test ./services/user-service/tests/api_integration/account/user_account -run TestUpdateProfile_AvatarVersionAndSyncPatch
)



echo "[runtime-media] image delivery policy static gates"
python3 "${ROOT_DIR}/quwoquan_app/scripts/media/verify_app_network_image_surface.py"
python3 "${ROOT_DIR}/quwoquan_app/scripts/media/verify_app_avatar_rendering_policy.py"
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
    test/local_contract/ui/components/media/video/video_player_widget__failure_experience__local_contract_test.dart \
    test/local_contract/ui/components/media/video/video_playback_session_seek__local_contract_test.dart \
    test/local_contract/ui/components/media/video/video_playback_timeline__local_contract_test.dart \
    test/local_contract/ui/discovery/widgets/works_immersive_viewer_widget__local_contract_test.dart \
    test/local_contract/cloud/content/video_preview_track_remote__local_contract_test.dart \
    test/local_contract/cloud/content/content_behavior_tracker__local_contract_test.dart
)
echo "[runtime-media] Android native first-frame / seek-settle / safe-dispose contracts"
(
  cd "${ROOT_DIR}/quwoquan_app/android"
  ./gradlew :video_player_android:testDebugUnitTest \
    --tests io.flutter.plugins.videoplayer.ExoPlayerEventListenerTest \
    --tests io.flutter.plugins.videoplayer.VideoPlayerTest \
    --tests io.flutter.plugins.videoplayer.PlatformVideoViewTest
)
(
  cd "${ROOT_DIR}"
  python3 -m unittest \
    quwoquan_ops.tests.local_contract.test_environment_patrol_smoke__local_contract_test \
    quwoquan_ops.tests.local_contract.test_local_gamma_media__local_contract_test \
    quwoquan_ops.tests.local_contract.test_runtime_media_t4_evidence__local_contract_test \
    quwoquan_ops.tests.local_contract.test_video_playback_canary__local_contract_test \
    quwoquan_ops.tests.local_contract.test_prod_rollout_stage__local_contract_test
)
(
  cd "${ROOT_DIR}/quwoquan_service"
  go test ./services/content-service/internal/content/post/application
  go test ./services/content-service/internal/content/post/application/behavior
  go test ./services/content-service/tests/api_integration/content/post \
    -run 'TestVideoPostProjectionCarriesAuthoritativeTimelineDescriptor|TestEffectivePlayRejectsScrubAndAcceptsForegroundEvidence'
)
DATA_PYTHON="${QWQ_PYTHON_CACHE_ROOT:-$HOME/.cache/quwoquan/python-envs}/quwoquan-data/bin/python"
if [[ ! -x "${DATA_PYTHON}" ]]; then
  python3 "${ROOT_DIR}/quwoquan_ops/cli/prepare_test_python.py"
fi
"${DATA_PYTHON}" -B -m pytest \
  -o "cache_dir=${ROOT_DIR}/.qwq_output/env/repo/local/tests/cache/pytest" \
  "${ROOT_DIR}/quwoquan_data/tests/local_contract/governance/test_media_probe__video_playback__functional__local_contract_test.py" \
  -q

echo "[runtime-media] Alpha Remote media health gate"
python3 "${ROOT_DIR}/quwoquan_ops/cli/stackctl.py" up \
  --target alpha-local \
  --skip-app \
  --workload content-release
python3 "${ROOT_DIR}/quwoquan_ops/cli/stackctl.py" health \
  --target alpha-local \
  --scope media

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
