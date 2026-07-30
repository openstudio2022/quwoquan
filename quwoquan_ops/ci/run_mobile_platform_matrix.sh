#!/usr/bin/env bash
set -euo pipefail

: "${MOBILE_PLATFORM:?MOBILE_PLATFORM is required}"
: "${MOBILE_DEVICE_ID:?MOBILE_DEVICE_ID is required}"
: "${MOBILE_MATRIX_ENV_JSON:?MOBILE_MATRIX_ENV_JSON is required}"
: "${MOBILE_MATRIX_KIND:?MOBILE_MATRIX_KIND is required}"

if [[ "$MOBILE_PLATFORM" != "android" && "$MOBILE_PLATFORM" != "ios" ]]; then
  echo "::error::unsupported mobile platform: $MOBILE_PLATFORM"
  exit 2
fi

if [[ "$MOBILE_PLATFORM" == "android" ]]; then
  export ANDROID_DEVICE_ID="$MOBILE_DEVICE_ID"
else
  export IOS_DEVICE_ID="$MOBILE_DEVICE_ID"
fi
unset ASSISTANT_MATRIX_ALL_DEVICES CHAT_AVATAR_MATRIX_ALL_DEVICES

ENV_NAMES="$(MOBILE_MATRIX_ENV_JSON_VALUE="$MOBILE_MATRIX_ENV_JSON" python3 - <<'PY'
import json
import os

payload = json.loads(os.environ["MOBILE_MATRIX_ENV_JSON_VALUE"])
if not isinstance(payload, list) or not payload:
    raise SystemExit("GATE_BLOCK: mobile environment matrix must be a non-empty JSON list")
print("\n".join(str(item).strip() for item in payload if str(item).strip()))
PY
)"
MATRIX_KINDS="$(MOBILE_MATRIX_KIND_VALUE="$MOBILE_MATRIX_KIND" python3 - <<'PY'
import json
import os

raw = os.environ["MOBILE_MATRIX_KIND_VALUE"].strip()
if not raw:
    items = ["assistant"]
elif raw.startswith("["):
    items = [str(item).strip() for item in json.loads(raw) if str(item).strip()]
else:
    items = [item.strip() for item in raw.split(",") if item.strip()]
print("\n".join(items or ["assistant"]))
PY
)"

resolve_patrol_target() {
  python3 - "$1" <<'PY'
import json
import sys
from pathlib import Path

journey_id = sys.argv[1]
suites = json.loads(
    Path("quwoquan_ops/environments/gamma/validation_suites.json").read_text(
        encoding="utf-8"
    )
)
journey = suites["uiJourneys"].get(journey_id)
if not isinstance(journey, dict):
    raise SystemExit(f"{journey_id} is not registered")
if journey.get("runner") != "patrol":
    raise SystemExit(f"{journey_id} must use patrol")
target = str(journey.get("target") or "").strip()
if not target:
    raise SystemExit(f"{journey_id} target is missing")
print(target)
PY
}

resolve_topology_public_bases() {
  python3 - "$1" <<'PY'
import sys
from quwoquan_ops.cli import stackctl

target_name = sys.argv[1]
topology = stackctl.load_environment_topology()
target = stackctl.get_target(topology, target_name)
bases = target.get("publicBases") or {}
keys = ("api", "productOps", "mediaAvatar", "mediaImage", "mediaVideo", "mediaUpload", "rtc")
missing = [key for key in keys if not str(bases.get(key) or "").strip()]
if missing:
    raise SystemExit(f"{target_name} publicBases missing: " + ", ".join(missing))
print("\t".join(str(bases[key]).strip() for key in keys))
PY
}

failures=0
prod_closure_requested=0
prod_closure_selected_platform_seen=0
if [[ $'\n'"${ENV_NAMES}"$'\n' == *$'\nprod\n'* ]] &&
   [[ $'\n'"${MATRIX_KINDS}"$'\n' == *$'\naccount-closure\n'* ]]; then
  prod_closure_requested=1
fi

while IFS= read -r env_name; do
  [[ -n "$env_name" ]] || continue
  fail_fast=0
  while IFS= read -r matrix_kind; do
    [[ -n "$matrix_kind" ]] || continue
    echo "::group::Run ${env_name}/${matrix_kind} on ${MOBILE_PLATFORM} (leased device)"
    export API_CONTRACT_ENV="$env_name"
    set +e
    if [[ "$matrix_kind" == "chat-avatar" ]]; then
      python3 quwoquan_ops/tests/acceptance/user_acceptance/service_ops/chat-service/ci/run_chat_avatar_device_matrix_ci.py \
        --platform "$MOBILE_PLATFORM"
      matrix_exit_code=$?
    elif [[ "$matrix_kind" == "user-profile" ]]; then
      if [[ "$env_name" != "gamma" ]]; then
        echo "::error::user-profile device journey is only defined for gamma; received env=${env_name}"
        matrix_exit_code=2
      else
        profile_target="$(resolve_patrol_target user_profile_journey_patrol)"
        bash quwoquan_app/scripts/gamma/run_local_gamma_t4.sh \
          --platform "$MOBILE_PLATFORM" \
          --device-id "$MOBILE_DEVICE_ID" \
          --target "$profile_target" \
          --report "$QWQ_OUTPUT_ROOT/env/gamma/runs/device-matrix/user-profile-${MOBILE_PLATFORM}.json"
        matrix_exit_code=$?
      fi
    elif [[ "$matrix_kind" == "account-closure" ]]; then
      closure_target="$(resolve_patrol_target account_closure_patrol)"
      closure_install_id="account-closure-${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}-${MOBILE_PLATFORM}-$(date +%s)-{device}"
      if [[ "$env_name" == "gamma" ]]; then
        bash quwoquan_app/scripts/gamma/run_local_gamma_t4.sh \
          --platform "$MOBILE_PLATFORM" \
          --device-id "$MOBILE_DEVICE_ID" \
          --target "$closure_target" \
          --patrol-install-id "$closure_install_id" \
          --report "$QWQ_OUTPUT_ROOT/env/gamma/runs/device-matrix/account-closure-${MOBILE_PLATFORM}.json"
        matrix_exit_code=$?
      elif [[ "$env_name" == "prod" ]]; then
        if [[ "$MOBILE_PLATFORM" != "${ACCOUNT_CLOSURE_PROD_PLATFORM:-ios}" ]]; then
          echo "::notice::Skip destructive Prod account closure on ${MOBILE_PLATFORM}; selected platform=${ACCOUNT_CLOSURE_PROD_PLATFORM:-ios}"
          matrix_exit_code=0
        else
          prod_closure_selected_platform_seen=1
          if [[ "${EVENT_NAME:-}" != "workflow_dispatch" || "${ACCOUNT_CLOSURE_DISPOSABLE_ACK:-}" != "true" ]]; then
            echo "::error::Prod account closure requires workflow_dispatch and account_closure_disposable_ack=true"
            matrix_exit_code=2
          elif [[ -z "${ACCOUNT_CLOSURE_PROD_DEVICE_ID:-}" ]]; then
            echo "::error::Prod account closure requires one explicit account_closure_prod_device_id"
            matrix_exit_code=2
          elif [[ "$ACCOUNT_CLOSURE_PROD_DEVICE_ID" != "$MOBILE_DEVICE_ID" ]]; then
            echo "::error::Prod account closure device must be the device held by this job's lease"
            matrix_exit_code=2
          else
            missing_prod_secret=0
            for required_name in \
              PROD_ACCOUNT_CLOSURE_TEST_AUTH_TOKEN \
              PROD_ACCOUNT_CLOSURE_TEST_REFRESH_TOKEN \
              PROD_ACCOUNT_CLOSURE_OWNER_ID \
              PROD_ACCOUNT_CLOSURE_PERSONA_ID; do
              if [[ -z "${!required_name:-}" ]]; then
                echo "::error::Production environment secret ${required_name} is required"
                missing_prod_secret=1
              fi
            done
            if [[ "$missing_prod_secret" -ne 0 ]]; then
              matrix_exit_code=2
            else
              IFS=$'\t' read -r \
                prod_api_base \
                prod_product_ops_base \
                prod_media_avatar_base \
                prod_media_image_base \
                prod_media_video_base \
                prod_media_upload_base \
                prod_rtc_base < <(resolve_topology_public_bases prod-hosted)
              TEST_AUTH_TOKEN="$PROD_ACCOUNT_CLOSURE_TEST_AUTH_TOKEN" \
              TEST_REFRESH_TOKEN="$PROD_ACCOUNT_CLOSURE_TEST_REFRESH_TOKEN" \
              APP_CURRENT_OWNER_ID="$PROD_ACCOUNT_CLOSURE_OWNER_ID" \
              APP_CURRENT_PERSONA_ID="$PROD_ACCOUNT_CLOSURE_PERSONA_ID" \
              python3 quwoquan_ops/cli/smoke/run_environment_patrol_smoke.py \
                --env-name prod-hosted \
                --runtime-env prod \
                --api-contract-env prod \
                --target "$closure_target" \
                --patrol-install-id "$closure_install_id" \
                --account-closure-disposable-ack \
                --platform "$MOBILE_PLATFORM" \
                --device-id "$MOBILE_DEVICE_ID" \
                --gateway-base-url "$prod_api_base" \
                --product-ops-base-url "$prod_product_ops_base" \
                --media-avatar-base-url "$prod_media_avatar_base" \
                --media-image-base-url "$prod_media_image_base" \
                --media-video-base-url "$prod_media_video_base" \
                --media-upload-base-url "$prod_media_upload_base" \
                --rtc-media-connection-url "$prod_rtc_base" \
                --report "$QWQ_OUTPUT_ROOT/env/prod/runs/device-matrix/account-closure-${MOBILE_PLATFORM}.json"
              matrix_exit_code=$?
            fi
          fi
        fi
      else
        echo "::error::account-closure supports gamma or protected prod only; received env=${env_name}"
        matrix_exit_code=2
      fi
    elif [[ "$matrix_kind" == "media-publication" ]]; then
      python3 quwoquan_ops/tests/acceptance/user_acceptance/service_ops/content-service/ci/run_media_publication_device_matrix_ci.py \
        --environment "$env_name" \
        --platform "$MOBILE_PLATFORM" \
        --device-id "$MOBILE_DEVICE_ID"
      matrix_exit_code=$?
    elif [[ "$matrix_kind" == "environment-smoke" || "$matrix_kind" == "app-core-readback" ]]; then
      case "$env_name" in
        beta)
          smoke_target_name="beta-local"
          smoke_env_alias="local-beta"
          smoke_runtime_env="beta"
          ;;
        gamma)
          smoke_target_name="gamma-local"
          smoke_env_alias="local-gamma"
          smoke_runtime_env="gamma"
          ;;
        prod-sim)
          smoke_target_name="prod-sim"
          smoke_env_alias="local-prod-sim"
          smoke_runtime_env="prod"
          ;;
        *)
          echo "::error::${matrix_kind} does not support env=${env_name}; Alpha uses quwoquan_app/run.sh natural entry"
          smoke_target_name=""
          ;;
      esac
      if [[ -z "$smoke_target_name" || -z "${VIDEO_PLAYBACK_CANARY_WORK_ID:-}" ]]; then
        [[ -n "$smoke_target_name" ]] && echo "::error::VIDEO_PLAYBACK_CANARY_WORK_ID is required for ${matrix_kind}"
        matrix_exit_code=2
      else
        if [[ "$matrix_kind" == "app-core-readback" ]]; then
          smoke_target="test/user_acceptance/patrol/environment/app_core_readback__user_acceptance_test.dart"
          smoke_report_name="app-core-readback"
        else
          smoke_target="test/user_acceptance/patrol/environment/basic_viability__user_acceptance_test.dart"
          smoke_report_name="environment-smoke"
        fi
        IFS=$'\t' read -r \
          smoke_gateway_base_url \
          smoke_product_ops_base_url \
          smoke_media_avatar_base_url \
          smoke_media_image_base_url \
          smoke_media_video_base_url \
          smoke_media_upload_base_url \
          smoke_rtc_base_url < <(resolve_topology_public_bases "$smoke_target_name")
        python3 quwoquan_ops/cli/smoke/run_environment_patrol_smoke.py \
          --env-name "$smoke_env_alias" \
          --runtime-env "$smoke_runtime_env" \
          --api-contract-env "$smoke_runtime_env" \
          --target "$smoke_target" \
          --gateway-base-url "$smoke_gateway_base_url" \
          --product-ops-base-url "$smoke_product_ops_base_url" \
          --media-avatar-base-url "$smoke_media_avatar_base_url" \
          --media-image-base-url "$smoke_media_image_base_url" \
          --media-video-base-url "$smoke_media_video_base_url" \
          --media-upload-base-url "$smoke_media_upload_base_url" \
          --rtc-media-connection-url "$smoke_rtc_base_url" \
          --video-playback-canary-work-id "$VIDEO_PLAYBACK_CANARY_WORK_ID" \
          --platform "$MOBILE_PLATFORM" \
          --device-id "$MOBILE_DEVICE_ID" \
          --report "$QWQ_OUTPUT_ROOT/env/${env_name}/runs/device-matrix/${smoke_report_name}-${MOBILE_PLATFORM}.json"
        matrix_exit_code=$?
      fi
    else
      python3 quwoquan_ops/tests/acceptance/user_acceptance/service_ops/assistant-service/ci/run_assistant_device_matrix_ci.py \
        --platform "$MOBILE_PLATFORM"
      matrix_exit_code=$?
    fi
    set -e
    if [[ "$matrix_exit_code" -eq 86 ]]; then
      echo "::warning::${MOBILE_PLATFORM}/${env_name}/${matrix_kind} hit fail-fast category"
      failures=$((failures + 1))
      fail_fast=1
    elif [[ "$matrix_exit_code" -ne 0 ]]; then
      failures=$((failures + 1))
    fi
    echo "::endgroup::"
    [[ "$fail_fast" -eq 0 ]] || break
  done <<< "$MATRIX_KINDS"
  [[ "$fail_fast" -eq 0 ]] || break
done <<< "$ENV_NAMES"

if [[ "$prod_closure_requested" -eq 1 &&
      "$MOBILE_PLATFORM" == "${ACCOUNT_CLOSURE_PROD_PLATFORM:-ios}" &&
      "$prod_closure_selected_platform_seen" -ne 1 ]]; then
  echo "::error::Selected Prod account closure platform ${ACCOUNT_CLOSURE_PROD_PLATFORM:-ios} is unavailable"
  failures=$((failures + 1))
fi
if [[ "$failures" -ne 0 ]]; then
  echo "::error::Mobile ${MOBILE_PLATFORM} matrix encountered ${failures} failure(s)"
  exit 1
fi
