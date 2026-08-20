#!/usr/bin/env bash
# 使用 env-package-backed Remote 启动入口，避免裸跑漏掉 runtime/release 合同。
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$APP_DIR/.." && pwd)"
export PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-$ROOT_DIR/.qwq_output/env/repo/local/python-cache/app-launch}"
REQUESTED_ENVIRONMENT="${QWQ_ENVIRONMENT:-}"
REQUESTED_TARGET=""
RUN_MODE="content-live"
ENSURE_RUNTIME=0
LAUNCH_RECEIPT="${QWQ_APP_LAUNCH_RECEIPT:-}"
LAUNCH_LOG_REF="${QWQ_APP_LAUNCH_LOG_REF:-}"
FLUTTER_ARGUMENTS=()

print_usage() {
  cat <<'EOF'
Usage: ./run.sh [--env alpha|beta|gamma] [--target alpha-local|beta-local|gamma-local]
                [--mode content-live|ui-only] [--launch-receipt <path>]
                [--launch-log-ref <path>] [--ensure-runtime] -d <device>

content-live is the default and starts Flutter only after the selected canonical
content release passes runtime, release, API, media, Search and Recommendation delivery.
ui-only allows a non-promotable development launch without claiming content readiness.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)
      if [[ -z "${2:-}" ]]; then
        echo "[run] GATE_BLOCK: --env requires alpha|beta|gamma." >&2
        exit 2
      fi
      if [[ -n "$REQUESTED_ENVIRONMENT" && "$REQUESTED_ENVIRONMENT" != "$2" ]]; then
        echo "[run] GATE_BLOCK: --env conflicts with QWQ_ENVIRONMENT." >&2
        exit 2
      fi
      REQUESTED_ENVIRONMENT="$2"
      shift 2
      ;;
    --env=*)
      value="${1#*=}"
      if [[ -n "$REQUESTED_ENVIRONMENT" && "$REQUESTED_ENVIRONMENT" != "$value" ]]; then
        echo "[run] GATE_BLOCK: --env conflicts with QWQ_ENVIRONMENT." >&2
        exit 2
      fi
      REQUESTED_ENVIRONMENT="$value"
      shift
      ;;
    --target)
      if [[ -z "${2:-}" ]]; then
        echo "[run] GATE_BLOCK: --target requires alpha-local|beta-local|gamma-local." >&2
        exit 2
      fi
      REQUESTED_TARGET="$2"
      shift 2
      ;;
    --target=*)
      REQUESTED_TARGET="${1#*=}"
      shift
      ;;
    --mode)
      if [[ -z "${2:-}" ]]; then
        echo "[run] GATE_BLOCK: --mode requires content-live|ui-only." >&2
        exit 2
      fi
      RUN_MODE="$2"
      shift 2
      ;;
    --mode=*)
      RUN_MODE="${1#*=}"
      shift
      ;;
    --ensure-runtime)
      ENSURE_RUNTIME=1
      shift
      ;;
    --launch-receipt)
      LAUNCH_RECEIPT="${2:-}"
      [[ -n "$LAUNCH_RECEIPT" ]] || {
        echo "[run] GATE_BLOCK: --launch-receipt requires a path." >&2
        exit 2
      }
      shift 2
      ;;
    --launch-receipt=*)
      LAUNCH_RECEIPT="${1#*=}"
      shift
      ;;
    --launch-log-ref)
      LAUNCH_LOG_REF="${2:-}"
      [[ -n "$LAUNCH_LOG_REF" ]] || {
        echo "[run] GATE_BLOCK: --launch-log-ref requires a path." >&2
        exit 2
      }
      shift 2
      ;;
    --launch-log-ref=*)
      LAUNCH_LOG_REF="${1#*=}"
      shift
      ;;
    -h|--help)
      print_usage
      exit 0
      ;;
    *)
      FLUTTER_ARGUMENTS+=("$1")
      shift
      ;;
  esac
done
set -- "${FLUTTER_ARGUMENTS[@]}"

case "$RUN_MODE" in
  content-live|ui-only) ;;
  *)
    echo "[run] GATE_BLOCK: --mode requires content-live|ui-only." >&2
    exit 2
    ;;
esac

if [[ -n "$REQUESTED_TARGET" ]]; then
  case "$REQUESTED_TARGET" in
    alpha-local) TARGET_ENVIRONMENT=alpha ;;
    beta-local) TARGET_ENVIRONMENT=beta ;;
    gamma-local) TARGET_ENVIRONMENT=gamma ;;
    *)
      echo "[run] GATE_BLOCK: --target requires alpha-local|beta-local|gamma-local." >&2
      exit 2
      ;;
  esac
  if [[ -n "$REQUESTED_ENVIRONMENT" \
     && "$REQUESTED_ENVIRONMENT" != "$TARGET_ENVIRONMENT" ]]; then
    echo "[run] GATE_BLOCK: --target conflicts with the selected environment." >&2
    exit 2
  fi
  REQUESTED_ENVIRONMENT="$TARGET_ENVIRONMENT"
fi

export QWQ_ENVIRONMENT="${REQUESTED_ENVIRONMENT:-alpha}"
export QWQ_APP_RUNTIME_ENV="$QWQ_ENVIRONMENT"
case "$QWQ_APP_RUNTIME_ENV" in
  alpha|beta|gamma) ;;
  *)
    echo "[run] GATE_BLOCK: QWQ_ENVIRONMENT must be alpha|beta|gamma." >&2
    exit 2
    ;;
esac
export QWQ_LAUNCH_TARGET="${REQUESTED_TARGET:-${QWQ_APP_RUNTIME_ENV}-local}"
export QWQ_APP_RUN_MODE="$RUN_MODE"
export QWQ_APP_BUILD_CONTEXT=runtime
export QWQ_APP_LAUNCH_POLICY=test_live

cd "$APP_DIR"

parse_flutter_device_id() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -d|--device-id)
        echo "${2:-}"
        return 0
        ;;
      --device-id=*)
        echo "${1#*=}"
        return 0
        ;;
    esac
    shift
  done
  return 0
}

for argument in "$@"; do
  case "$argument" in
    -t|--target|--target=*)
      echo "[run] GATE_BLOCK: raw Flutter entrypoint overrides are forbidden; use launcher --target before Flutter arguments."
      exit 2
      ;;
  esac
done

export QWQ_RUN_DEVICE_ID="$(parse_flutter_device_id "$@")"
DEVICE_ID="$QWQ_RUN_DEVICE_ID"

if [[ "$ENSURE_RUNTIME" == "1" ]]; then
  echo "[run] GATE_BLOCK: --ensure-runtime requires an explicit frozen candidate identity; the App launcher cannot infer or mutate it." >&2
  exit 2
fi

PREFLIGHT_PURPOSE=runtime
if [[ "$RUN_MODE" == "content-live" ]]; then
  PREFLIGHT_PURPOSE=content_live
fi

echo "[run] validating $PREFLIGHT_PURPOSE for $QWQ_LAUNCH_TARGET..."
if ! APP_CONTENT_PREFLIGHT_JSON="$(
  PYTHONDONTWRITEBYTECODE=1 python3 \
    "$ROOT_DIR/quwoquan_ops/cli/stackctl.py" --output-format json \
    app-debug-preflight --purpose "$PREFLIGHT_PURPOSE" \
    --target "$QWQ_LAUNCH_TARGET" --runtime-mode test_live
)"; then
  echo "$APP_CONTENT_PREFLIGHT_JSON" >&2
  exit 2
fi

APP_CONTENT_EXPORTS="$(
  python3 - "$APP_CONTENT_PREFLIGHT_JSON" "$RUN_MODE" "$QWQ_LAUNCH_TARGET" <<'PY'
import json
import shlex
import sys

payload = json.loads(sys.argv[1])
run_mode = sys.argv[2]
target = sys.argv[3]
purpose = "content_live" if run_mode == "content-live" else "runtime"
recovery_command = (
    "python3 quwoquan_ops/cli/stackctl.py --output-format json "
    f"app-debug-preflight --purpose {purpose} --target {target} "
    "--runtime-mode test_live"
)

if payload.get("purpose") != purpose:
    print(json.dumps({
        "contentLive": "blocked",
        "reason": "preflight purpose mismatch",
        "recoveryCommand": recovery_command,
    }, ensure_ascii=False), file=sys.stderr)
    raise SystemExit(2)

if run_mode == "content-live":
    content_binding = payload.get("contentBinding") or {}
    first_blocker = str(
        payload.get("firstBlocker")
        or next(iter(payload.get("details") or payload.get("warnings") or []), "")
        or "content-live readiness is not passed"
    )
    required = {
        "releaseId": str(payload.get("releaseId") or "").strip(),
        "verifyRunId": str(content_binding.get("verifyRunId") or "").strip(),
        "manifestDigest": str(payload.get("manifestDigest") or "").strip(),
        "readinessReceiptDigest": str(
            payload.get("readinessReceiptDigest") or ""
        ).strip(),
    }
    if (
        payload.get("status") != "passed"
        or payload.get("contentLive") != "passed"
        or any(not value for value in required.values())
    ):
        print(json.dumps({
            "contentLive": "gate_block",
            "reason": first_blocker,
            "recoveryCommand": str(
                payload.get("recoveryCommand") or recovery_command
            ),
        }, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
    for key, value in (
        ("QWQ_CONTENT_RELEASE_ID", required["releaseId"]),
        ("QWQ_CONTENT_VERIFY_RUN_ID", required["verifyRunId"]),
        ("QWQ_CONTENT_MANIFEST_DIGEST", required["manifestDigest"]),
        (
            "QWQ_CONTENT_READINESS_RECEIPT_DIGEST",
            required["readinessReceiptDigest"],
        ),
    ):
        print(f"export {key}={shlex.quote(value)}")
else:
    if (
        payload.get("status") not in {"passed", "warning"}
        or payload.get("nonPromotable") is not True
    ):
        print(json.dumps({
            "contentLive": "not_evaluated",
            "reason": str(payload.get("firstBlocker") or "runtime preflight blocked"),
            "recoveryCommand": recovery_command,
        }, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
    for warning in payload.get("warnings") or []:
        print(f"[run] WARN: {warning}", file=sys.stderr)
PY
)" || {
  echo "[run] GATE_BLOCK: selected launch mode preflight did not pass." >&2
  exit 2
}
eval "$APP_CONTENT_EXPORTS"

APP_CONTENT_DELIVERY_JSON='{}'
if [[ "$RUN_MODE" == "content-live" ]]; then
  if ! APP_CONTENT_DELIVERY_JSON="$(
    PYTHONDONTWRITEBYTECODE=1 python3 \
      "$ROOT_DIR/quwoquan_ops/cli/stackctl.py" --output-format json \
      verify --env "$QWQ_APP_RUNTIME_ENV" --target "$QWQ_LAUNCH_TARGET" \
      --kind content-delivery --profile integration \
      --data-release-id "$QWQ_CONTENT_RELEASE_ID" \
      --data-verify-run-id "$QWQ_CONTENT_VERIFY_RUN_ID" \
      --data-manifest-digest "$QWQ_CONTENT_MANIFEST_DIGEST"
  )"; then
    python3 - \
      "$APP_CONTENT_DELIVERY_JSON" "$QWQ_CONTENT_RELEASE_ID" \
      "$QWQ_APP_RUNTIME_ENV" <<'PY' >&2
import json
import sys

try:
    payload = json.loads(sys.argv[1])
except json.JSONDecodeError:
    payload = {}
first_blocker = str(
    next(iter(payload.get("details") or []), "content delivery verification failed")
)
recovery_command = (
    "python3 quwoquan_data/scripts/cli.py release supply-chain-drill "
    f"--release-id {sys.argv[2]} --env {sys.argv[3]} --profile delivery"
)
print(json.dumps({
    "contentLive": "gate_block",
    "reason": first_blocker,
    "recoveryCommand": recovery_command,
}, ensure_ascii=False))
PY
    exit 2
  fi
fi

echo "[run] verifying local Flutter package resolution..."
if ! flutter pub get --offline --enforce-lockfile; then
  echo "[run] FAIL: offline Flutter dependency resolution failed."
  echo "[run] This repo forbids implicit build-time network fetches. Run an explicit dependency sync only when intentionally changing third-party packages."
  exit 1
fi

if [[ -z "$DEVICE_ID" ]]; then
  echo "[run] GATE_BLOCK: pass -d/--device-id so runtime ports and the consumer lease bind to one device."
  exit 2
fi

if ! PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}" python3 - "$DEVICE_ID" <<'PY'
import sys

from quwoquan_ops.cli.lib.dev_up import find_device

device_id = sys.argv[1].strip()
device = find_device(device_id, include_desktop=False)
if device is None:
    raise SystemExit(
        f"GATE_BLOCK: Flutter device {device_id!r} is not currently connected; "
        "boot or attach an iOS/Android device after runtime preflight."
    )
platform = str(device.get("targetPlatform") or "").strip().lower()
if platform != "ios" and not platform.startswith("android"):
    raise SystemExit(
        f"GATE_BLOCK: Flutter device {device_id!r} has unsupported platform {platform!r}; "
        "use an iOS or Android device for Remote runtime launch."
    )
PY
then
  echo "[run] GATE_BLOCK: a connected iOS/Android device is required after runtime preflight." >&2
  exit 2
fi

ANDROID_LOCAL_GATEWAY_BASE_URL=""
ANDROID_LOCAL_LEGAL_BASE_URL=""
ANDROID_LOCAL_MEDIA_AVATAR_BASE_URL=""
ANDROID_LOCAL_MEDIA_IMAGE_BASE_URL=""
ANDROID_LOCAL_MEDIA_VIDEO_BASE_URL=""
ANDROID_LOCAL_MEDIA_UPLOAD_BASE_URL=""
QWQ_ANDROID_LOCAL_PORTS=""
export QWQ_RUN_CONSUMER_ID="flutter-run-$$"
export QWQ_CONSUMER_LEASE_ACQUIRED=0
export QWQ_CONSUMER_LEASE_ID=""
export QWQ_ANDROID_REVERSE_OWNED_PORTS=""
export QWQ_ANDROID_VM_FORWARD_PREEXISTING=0

release_consumer_lease() {
  if command -v adb >/dev/null 2>&1 \
    && [[ "${QWQ_RUN_DEVICE_KIND:-}" == android* ]] \
    && [[ "$QWQ_ANDROID_VM_FORWARD_PREEXISTING" != "1" ]]; then
    current_vm_forward="$({ adb forward --list 2>/dev/null || true; } \
      | awk -v device="$DEVICE_ID" '$1 == device && $2 == "tcp:8888" { print $2; exit }')"
    if [[ "$current_vm_forward" == "tcp:8888" ]] \
      && ! adb -s "$DEVICE_ID" forward --remove tcp:8888 >/dev/null 2>&1; then
      echo "[run] WARN: failed to remove owned Flutter VM adb forward tcp:8888."
    fi
  fi
  if command -v adb >/dev/null 2>&1 \
    && [[ -n "$QWQ_ANDROID_REVERSE_OWNED_PORTS" ]]; then
    IFS=',' read -r -a reverse_ports <<< "$QWQ_ANDROID_REVERSE_OWNED_PORTS"
    for port in "${reverse_ports[@]}"; do
      [[ -z "$port" ]] && continue
      if ! adb -s "$DEVICE_ID" reverse --remove "tcp:$port" >/dev/null 2>&1; then
        echo "[run] WARN: failed to remove owned adb reverse tcp:$port."
      fi
    done
  fi
  if [[ "$QWQ_CONSUMER_LEASE_ACQUIRED" != "1" ]]; then
    return
  fi
  python3 "$ROOT_DIR/quwoquan_ops/cli/stackctl.py" consumer-lease release \
    --target "$QWQ_LAUNCH_TARGET" \
    --device "$DEVICE_ID" \
    --consumer "$QWQ_RUN_CONSUMER_ID" >/dev/null || \
    echo "[run] WARN: failed to release runtime consumer lease."
  QWQ_CONSUMER_LEASE_ACQUIRED=0
}

cleanup_run() {
  release_consumer_lease
  if [[ -n "${QWQ_APP_INSTANCE_STATE_FILE:-}" ]]; then
    rm -f -- "$QWQ_APP_INSTANCE_STATE_FILE"
  fi
}

trap cleanup_run EXIT

if [[ -n "$DEVICE_ID" ]]; then
  DEVICE_EXPORTS="$(
    PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}" python3 - \
      "$DEVICE_ID" "$QWQ_APP_RUNTIME_ENV" "$QWQ_LAUNCH_TARGET" <<'PY'
import hashlib
import os
import re
import shlex
import subprocess
import sys

from quwoquan_ops.cli.lib.dev_up import (
    detect_device_kind,
    enable_android_adb_reverse,
    find_device,
    load_environment_topology,
    resolve_app_endpoint_overrides,
)

device_id = sys.argv[1].strip()
environment = sys.argv[2].strip()
target = sys.argv[3].strip()
device = find_device(device_id, include_desktop=False) or {}
device_kind = detect_device_kind(
    device_id,
    target_platform=str(device.get("targetPlatform", "")),
    emulator=bool(device.get("emulator", False)) if device else None,
)
print(f"export QWQ_RUN_DEVICE_KIND={shlex.quote(device_kind)}")
if device_kind.startswith("android"):
    try:
        topology = load_environment_topology()
        overrides = resolve_app_endpoint_overrides(
            environment,
            device_kind,
            topology=topology,
        )
        before = subprocess.run(
            ["adb", "-s", device_id, "reverse", "--list"],
            check=False,
            capture_output=True,
            text=True,
        )
        if before.returncode != 0:
            raise RuntimeError("unable to read existing adb reverse mappings")
        preexisting_ports = {
            int(match.group(1))
            for match in re.finditer(r"tcp:(\d+)\s+tcp:\d+", before.stdout)
        }
        forwards = subprocess.run(
            ["adb", "forward", "--list"],
            check=False,
            capture_output=True,
            text=True,
        )
        if forwards.returncode != 0:
            raise RuntimeError("unable to read existing adb forward mappings")
        vm_forward_preexisting = any(
            fields[:2] == [device_id, "tcp:8888"]
            for fields in (line.split() for line in forwards.stdout.splitlines())
            if len(fields) >= 2
        )
        ports = enable_android_adb_reverse(device_id, target, topology=topology)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        if os.environ.get("QWQ_APP_RUN_MODE") == "content-live":
            raise SystemExit(
                f"content-live transport preparation failed: {exc}"
            )
        print(
            "[run] WARN: Android transport preparation is unavailable; "
            f"test_live continues with typed network recovery: {exc}",
            file=sys.stderr,
        )
        print("export QWQ_ANDROID_TRANSPORT_READY=0")
        raise SystemExit(0)
    port_list = ",".join(str(port) for port in ports)
    owned_port_list = ",".join(
        str(port) for port in ports if int(port) not in preexisting_ports
    )
    print("export QWQ_ANDROID_LOCAL_PORTS=" + shlex.quote(port_list))
    print("export QWQ_ANDROID_REVERSE_EXPECTED_PORTS=" + shlex.quote(port_list))
    print("export QWQ_ANDROID_REVERSE_ACTUAL_PORTS=" + shlex.quote(port_list))
    print("export QWQ_ANDROID_REVERSE_OWNED_PORTS=" + shlex.quote(owned_port_list))
    print(
        "export QWQ_ANDROID_VM_FORWARD_PREEXISTING="
        + ("1" if vm_forward_preexisting else "0")
    )
    print("export QWQ_ANDROID_REVERSE_RECEIPT_DIGEST=" + shlex.quote(
        "sha256:" + hashlib.sha256(
            f"{target}\0{device_id}\0{port_list}".encode("utf-8")
        ).hexdigest()
    ))
    print("export QWQ_ANDROID_LOCAL_TARGET=" + shlex.quote(target))
    print("export QWQ_ANDROID_TRANSPORT_READY=1")
    print("export ANDROID_LOCAL_GATEWAY_BASE_URL=" + shlex.quote(overrides["gatewayBaseUrl"]))
    print("export ANDROID_LOCAL_LEGAL_BASE_URL=" + shlex.quote(overrides["legalBaseUrl"]))
    print(
        "export ANDROID_LOCAL_MEDIA_AVATAR_BASE_URL="
        + shlex.quote(overrides["mediaAvatarBaseUrl"])
    )
    print(
        "export ANDROID_LOCAL_MEDIA_IMAGE_BASE_URL="
        + shlex.quote(overrides["mediaImageBaseUrl"])
    )
    print(
        "export ANDROID_LOCAL_MEDIA_VIDEO_BASE_URL="
        + shlex.quote(overrides["mediaVideoBaseUrl"])
    )
    print(
        "export ANDROID_LOCAL_MEDIA_UPLOAD_BASE_URL="
        + shlex.quote(overrides["mediaUploadBaseUrl"])
    )
PY
  )" || {
    echo "[run] GATE_BLOCK: failed to resolve device-specific Remote topology." >&2
    exit 2
  }
  eval "$DEVICE_EXPORTS"
fi

if [[ "${QWQ_RUN_DEVICE_KIND:-}" == ios-* ]]; then
  POD_EXECUTABLE="${QWQ_COCOAPODS_EXECUTABLE:-$(command -v pod || true)}"
  if [[ -z "$POD_EXECUTABLE" ]]; then
    echo "[run] APP.DEPENDENCY.cocoapods_missing: pod executable not found." >&2
    exit 1
  fi
  if ! POD_EXECUTABLE="$(PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 python3 - "$POD_EXECUTABLE" <<'PY'
import sys

from quwoquan_ops.cli.lib.app_dependency_toolchain import (
    AppDependencyToolchainError,
    resolve_cocoapods_executable,
)

try:
    print(resolve_cocoapods_executable(sys.argv[1]))
except AppDependencyToolchainError as error:
    raise SystemExit(f"APP.DEPENDENCY.cocoapods_mixed: {error}") from error
PY
  )"; then
    exit 1
  fi
  if ! (cd "$APP_DIR/ios" && "$POD_EXECUTABLE" install --deployment); then
    echo "[run] APP.DEPENDENCY.lock_drift: pod install --deployment failed." >&2
    exit 1
  fi
  PODFILE_LOCK="$APP_DIR/ios/Podfile.lock"
  PODS_MANIFEST_LOCK="$APP_DIR/ios/Pods/Manifest.lock"
  if [[ ! -f "$PODS_MANIFEST_LOCK" ]]; then
    echo "[run] FAIL: missing $PODS_MANIFEST_LOCK."
    echo "[run] iOS dependencies must be pre-vendored locally; do not rely on implicit CocoaPods downloads at launch time."
    exit 1
  fi

  if ! cmp -s "$PODFILE_LOCK" "$PODS_MANIFEST_LOCK"; then
    echo "[run] FAIL: CocoaPods lock drift detected between Podfile.lock and Pods/Manifest.lock."
    echo "[run] Resolve pod changes explicitly before launching; alpha startup must not repair dependencies over the network."
    exit 1
  fi
fi

if [[ "${QWQ_RUN_DEVICE_KIND:-}" == "ios-simulator" \
   || "${QWQ_RUN_DEVICE_KIND:-}" == android* ]]; then
  RUNTIME_STACKCTL_PYTHON="$(
    bash "$APP_DIR/scripts/ios/build_resolve_stackctl_python.sh"
  )" || {
    echo "[run] GATE_BLOCK: a compatible Python is required for device system trust." >&2
    exit 2
  }
  DEVICE_TRUST_PLATFORM="$QWQ_RUN_DEVICE_KIND"
  if [[ "$DEVICE_TRUST_PLATFORM" == "android_emulator" ]]; then
    DEVICE_TRUST_PLATFORM="android-emulator"
  fi
  DEVICE_TRUST_COMMAND=(
    "$RUNTIME_STACKCTL_PYTHON" "$ROOT_DIR/quwoquan_ops/cli/stackctl.py"
    --output-format json device-trust --target "$QWQ_LAUNCH_TARGET"
    --platform "$DEVICE_TRUST_PLATFORM" --action install --device "$DEVICE_ID"
    --lease-id "canonical-launcher:${DEVICE_ID}"
  )
  if [[ "${QWQ_RUN_DEVICE_KIND:-}" == "ios-simulator" ]]; then
    DEVICE_TRUST_COMMAND+=(--defer-endpoint-probe)
  elif [[ "${QWQ_RUN_DEVICE_KIND:-}" == android* ]]; then
    DEVICE_TRUST_COMMAND+=(--allow-unprovisioned-system-trust)
  fi
  if ! PYTHONDONTWRITEBYTECODE=1 "${DEVICE_TRUST_COMMAND[@]}" >/dev/null; then
    if [[ "$RUN_MODE" == "content-live" ]]; then
      echo "[run] GATE_BLOCK: content-live requires target-bound device trust." >&2
      exit 2
    fi
    echo "[run] WARN: target-bound device trust is unavailable; ui-only remains nonPromotable." >&2
  fi
fi

if [[ "${QWQ_RUN_DEVICE_KIND:-}" == android* ]]; then
  export ANDROID_SERIAL="$DEVICE_ID"
  if [[ -z "$QWQ_ANDROID_LOCAL_PORTS" ]]; then
    if [[ "$RUN_MODE" == "content-live" ]]; then
      echo "[run] GATE_BLOCK: content-live requires complete Android reverse ports." >&2
      exit 2
    fi
    echo "[run] WARN: Android reverse ports are unavailable; ui-only remains nonPromotable." >&2
  fi
fi

if [[ "${QWQ_RUN_DEVICE_KIND:-}" == "ios-simulator" \
   || ("${QWQ_RUN_DEVICE_KIND:-}" == android* \
      && -n "$QWQ_ANDROID_LOCAL_PORTS") ]]; then
  # run.sh 走 flutter run（Debug）；lease 身份必须与实际安装的
  # 环境 × BuildMode applicationId/bundle id 单轨一致，禁止字面值。
  QWQ_DEBUG_APP_ID_PLATFORM="android"
  if [[ "${QWQ_RUN_DEVICE_KIND:-}" == "ios-simulator" ]]; then
    QWQ_DEBUG_APP_ID_PLATFORM="ios"
  fi
  QWQ_DEBUG_APP_ID="$(
    PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}" PYTHONDONTWRITEBYTECODE=1 \
      "$RUNTIME_STACKCTL_PYTHON" -c "from quwoquan_ops.cli.lib.app_identity import application_id_for; import sys; print(application_id_for(sys.argv[1], sys.argv[2], 'debug'))" \
      "$QWQ_DEBUG_APP_ID_PLATFORM" "$QWQ_APP_RUNTIME_ENV"
  )" || {
    echo "[run] GATE_BLOCK: failed to derive the debug application id for $QWQ_APP_RUNTIME_ENV." >&2
    exit 2
  }
  LEASE_COMMAND=(
    "$RUNTIME_STACKCTL_PYTHON" "$ROOT_DIR/quwoquan_ops/cli/stackctl.py"
    --output-format json consumer-lease acquire
    --target "$QWQ_LAUNCH_TARGET"
    --device "$DEVICE_ID"
    --consumer "$QWQ_RUN_CONSUMER_ID"
  )
  if [[ "${QWQ_RUN_DEVICE_KIND:-}" == "ios-simulator" ]]; then
    LEASE_COMMAND+=(
      --platform ios-simulator
      --bundle-id "$QWQ_DEBUG_APP_ID"
      --ports ""
    )
  else
    LEASE_COMMAND+=(
      --platform android
      --package-name "$QWQ_DEBUG_APP_ID"
      --ports "$QWQ_ANDROID_LOCAL_PORTS"
    )
  fi
  if LEASE_JSON="$(PYTHONDONTWRITEBYTECODE=1 "${LEASE_COMMAND[@]}")"; then
    QWQ_CONSUMER_LEASE_ID="$(
    python3 - "$LEASE_JSON" <<'PY'
import json
import sys

lease_id = str((json.loads(sys.argv[1]).get("lease") or {}).get("leaseId") or "")
if not lease_id:
    raise SystemExit("consumer lease response is missing leaseId")
print(lease_id)
PY
    )"
    export QWQ_CONSUMER_LEASE_ID
    QWQ_CONSUMER_LEASE_ACQUIRED=1
  else
    if [[ "$RUN_MODE" == "content-live" ]]; then
      echo "[run] GATE_BLOCK: content-live requires a runtime consumer lease." >&2
      exit 2
    fi
    echo "[run] WARN: runtime consumer lease is unavailable; ui-only remains nonPromotable." >&2
  fi
fi

HANDOFF_CMD=(
  python3 "$APP_DIR/scripts/device/build_launcher_handoff.py"
  --env "$QWQ_APP_RUNTIME_ENV"
  --target "$QWQ_LAUNCH_TARGET"
  --launch-mode canonical_launcher
  --launch-policy test_live
  --app-instance-id "$QWQ_APP_RUNTIME_ENV-run"
  --app-instance-namespace "$QWQ_APP_RUNTIME_ENV-run"
)
if [[ -n "$ANDROID_LOCAL_GATEWAY_BASE_URL" ]]; then
  HANDOFF_CMD+=(--gateway-base-url "$ANDROID_LOCAL_GATEWAY_BASE_URL")
fi
if [[ -n "$ANDROID_LOCAL_LEGAL_BASE_URL" ]]; then
  HANDOFF_CMD+=(--legal-base-url "$ANDROID_LOCAL_LEGAL_BASE_URL")
fi
if [[ -n "$ANDROID_LOCAL_MEDIA_AVATAR_BASE_URL" ]]; then
  HANDOFF_CMD+=(--media-avatar-base-url "$ANDROID_LOCAL_MEDIA_AVATAR_BASE_URL")
fi
if [[ -n "$ANDROID_LOCAL_MEDIA_IMAGE_BASE_URL" ]]; then
  HANDOFF_CMD+=(--media-image-base-url "$ANDROID_LOCAL_MEDIA_IMAGE_BASE_URL")
fi
if [[ -n "$ANDROID_LOCAL_MEDIA_VIDEO_BASE_URL" ]]; then
  HANDOFF_CMD+=(--media-video-base-url "$ANDROID_LOCAL_MEDIA_VIDEO_BASE_URL")
fi
if [[ -n "$ANDROID_LOCAL_MEDIA_UPLOAD_BASE_URL" ]]; then
  HANDOFF_CMD+=(--media-upload-base-url "$ANDROID_LOCAL_MEDIA_UPLOAD_BASE_URL")
fi
if [[ "${QWQ_RUN_DEVICE_KIND:-}" == android* \
   && "$QWQ_CONSUMER_LEASE_ACQUIRED" == "1" ]]; then
  HANDOFF_CMD+=(
    --transport-required
    --reverse-expected-ports "$QWQ_ANDROID_REVERSE_EXPECTED_PORTS"
    --reverse-actual-ports "$QWQ_ANDROID_REVERSE_ACTUAL_PORTS"
    --reverse-receipt-digest "$QWQ_ANDROID_REVERSE_RECEIPT_DIGEST"
    --consumer-lease-id "$QWQ_CONSUMER_LEASE_ID"
  )
fi

HANDOFF_JSON="$("${HANDOFF_CMD[@]}")"
HANDOFF_EXPORTS="$(
  python3 - "$HANDOFF_JSON" <<'PY'
import json
import shlex
import sys

handoff = json.loads(sys.argv[1])
print("ENTRYPOINT=" + shlex.quote(handoff["entrypoint"]))
print("LAUNCH_MODE=" + shlex.quote(handoff["launchMode"]))
print("DART_DEFINES_DIGEST=" + shlex.quote(handoff["dartDefinesDigest"]))
print("RUNTIME_CONFIG_DIGEST=" + shlex.quote(handoff["runtimeConfigDigest"]))
print("EFFECTIVE_LAUNCH_MANIFEST_DIGEST=" + shlex.quote(
    handoff["effectiveLaunchManifestDigest"]
))
print("EFFECTIVE_LAUNCH_MANIFEST_JSON=" + shlex.quote(json.dumps(
    handoff["effectiveLaunchManifest"],
    ensure_ascii=False,
    separators=(",", ":"),
)))
print("RECOVERY_BASE_URL=" + shlex.quote(handoff["recoveryBaseUrl"]))
print("PUBLIC_WEB_BASE_URL=" + shlex.quote(handoff["publicWebBaseUrl"]))
print("APP_DOWNLOAD_BASE_URL=" + shlex.quote(handoff["appDownloadBaseUrl"]))
print("DEFINES_JSON=" + shlex.quote(json.dumps(
    handoff["dartDefines"],
    ensure_ascii=False,
    separators=(",", ":"),
)))
PY
)" || {
  echo "[run] GATE_BLOCK: failed to parse launcher handoff." >&2
  exit 2
}
eval "$HANDOFF_EXPORTS"
export QWQ_APP_LAUNCH_MODE="$LAUNCH_MODE"
export QWQ_LAUNCH_HANDOFF_JSON="$HANDOFF_JSON"
export QWQ_DART_DEFINES_DIGEST="$DART_DEFINES_DIGEST"
export QWQ_EXPECTED_RUNTIME_CONFIG_DIGEST="$RUNTIME_CONFIG_DIGEST"
export QWQ_EFFECTIVE_LAUNCH_MANIFEST_DIGEST="$EFFECTIVE_LAUNCH_MANIFEST_DIGEST"
export QWQ_APP_RECOVERY_BASE_URL="$RECOVERY_BASE_URL"
export QWQ_APP_PUBLIC_WEB_URL="$PUBLIC_WEB_BASE_URL"
export QWQ_APP_DOWNLOAD_BASE_URL="$APP_DOWNLOAD_BASE_URL"
if [[ "$QWQ_CONSUMER_LEASE_ACQUIRED" == "1" ]]; then
  LEASE_BIND_COMMAND=(
    "${LEASE_COMMAND[@]}"
    --handoff-digest "$EFFECTIVE_LAUNCH_MANIFEST_DIGEST"
  )
  if [[ -n "${QWQ_CONTENT_RELEASE_ID:-}" ]]; then
    LEASE_BIND_COMMAND+=(--release-id "$QWQ_CONTENT_RELEASE_ID")
  fi
  if [[ -n "${QWQ_CONTENT_MANIFEST_DIGEST:-}" ]]; then
    LEASE_BIND_COMMAND+=(--manifest-digest "$QWQ_CONTENT_MANIFEST_DIGEST")
  fi
  if [[ -n "${QWQ_CONTENT_READINESS_RECEIPT_DIGEST:-}" ]]; then
    LEASE_BIND_COMMAND+=(
      --readiness-receipt-digest "$QWQ_CONTENT_READINESS_RECEIPT_DIGEST"
    )
  fi
  if ! PYTHONDONTWRITEBYTECODE=1 "${LEASE_BIND_COMMAND[@]}" >/dev/null; then
    if [[ "$RUN_MODE" == "content-live" ]]; then
      echo "[run] GATE_BLOCK: content-live failed to bind the consumer lease to the verified handoff." >&2
      exit 2
    fi
    echo "[run] WARN: failed to bind the runtime consumer lease to the final handoff digest." >&2
  fi
fi
VERIFY_HANDOFF_CMD=(
  python3 "$APP_DIR/scripts/device/verify_flutter_run_defines.py"
  --env "$QWQ_APP_RUNTIME_ENV"
  --target "$QWQ_LAUNCH_TARGET"
  --entrypoint "$ENTRYPOINT"
  --defines-digest "$DART_DEFINES_DIGEST"
  --runtime-config-digest "$RUNTIME_CONFIG_DIGEST"
  --effective-launch-manifest-json "$EFFECTIVE_LAUNCH_MANIFEST_JSON"
  --effective-launch-manifest-digest "$EFFECTIVE_LAUNCH_MANIFEST_DIGEST"
  --defines-json "$DEFINES_JSON"
)
if [[ "${QWQ_RUN_DEVICE_KIND:-}" == android* \
   && "$QWQ_CONSUMER_LEASE_ACQUIRED" == "1" ]]; then
  VERIFY_HANDOFF_CMD+=(
    --transport-required
    --reverse-expected-ports "$QWQ_ANDROID_REVERSE_EXPECTED_PORTS"
    --reverse-actual-ports "$QWQ_ANDROID_REVERSE_ACTUAL_PORTS"
    --reverse-receipt-digest "$QWQ_ANDROID_REVERSE_RECEIPT_DIGEST"
    --consumer-lease-id "$QWQ_CONSUMER_LEASE_ID"
  )
fi
"${VERIFY_HANDOFF_CMD[@]}"

DART_DEFINES=()
while IFS= read -r line; do
  [[ -n "$line" ]] && DART_DEFINES+=("$line")
done < <(
  python3 - "$DEFINES_JSON" <<'PY'
import json
import sys
for key, value in json.loads(sys.argv[1]).items():
    print(f"--dart-define={key}={value}")
PY
)

set +e
if [[ -z "$LAUNCH_RECEIPT" ]]; then
  LAUNCH_RECEIPT="$ROOT_DIR/.qwq_output/env/repo/runs/$(date -u +%Y%m%dT%H%M%SZ)-$$-${QWQ_LAUNCH_TARGET}-app-launch/attempt.json"
fi
case "${QWQ_RUN_DEVICE_KIND:-}" in
  android*) LAUNCH_PLATFORM=android ;;
  ios*) LAUNCH_PLATFORM=ios ;;
  *)
    echo "[run] GATE_BLOCK: unsupported launch platform ${QWQ_RUN_DEVICE_KIND:-unknown}." >&2
    exit 2
    ;;
esac
SUPERVISOR_CMD=(
  python3 "$APP_DIR/scripts/device/supervise_app_launch.py"
  --receipt "$LAUNCH_RECEIPT"
  --environment "$QWQ_APP_RUNTIME_ENV"
  --target "$QWQ_LAUNCH_TARGET"
  --platform "$LAUNCH_PLATFORM"
  --build-mode debug
  --run-mode "$RUN_MODE"
  --device "$DEVICE_ID"
  --application-id "${QWQ_DEBUG_APP_ID:-}"
  --launch-digest "$EFFECTIVE_LAUNCH_MANIFEST_DIGEST"
  --timeout-seconds "${QWQ_APP_LAUNCH_TIMEOUT_SECONDS:-900}"
)
if [[ -n "$LAUNCH_LOG_REF" ]]; then
  SUPERVISOR_CMD+=(--log-ref "$LAUNCH_LOG_REF")
fi
while IFS= read -r launch_warning; do
  [[ -z "$launch_warning" ]] || SUPERVISOR_CMD+=(--warning "$launch_warning")
done < <(
  python3 - "$APP_CONTENT_PREFLIGHT_JSON" <<'PY'
import json
import sys

for item in json.loads(sys.argv[1]).get("warnings") or []:
    print(str(item).replace("\n", " "))
PY
)
"${SUPERVISOR_CMD[@]}" -- \
  flutter run \
    --no-pub \
    --flavor "$QWQ_APP_RUNTIME_ENV" \
    --target "$ENTRYPOINT" \
    --host-vmservice-port=8888 \
    --dds-port=8889 \
    "${DART_DEFINES[@]}" \
    "$@"
FLUTTER_RUN_EXIT_CODE=$?
set -e

TEST_LIVE_REPORT_DIR="$ROOT_DIR/.qwq_output/env/repo/runs/$(date -u +%Y%m%dT%H%M%SZ)-$$-${QWQ_LAUNCH_TARGET}-flutter-test-live"
mkdir -p "$TEST_LIVE_REPORT_DIR"
TEST_LIVE_REPORT_PATH="$TEST_LIVE_REPORT_DIR/report.json"
python3 - \
  "$APP_CONTENT_PREFLIGHT_JSON" \
  "$FLUTTER_RUN_EXIT_CODE" \
  "$QWQ_APP_RUNTIME_ENV" \
  "$QWQ_LAUNCH_TARGET" \
  "$DEVICE_ID" \
  "${QWQ_RUN_DEVICE_KIND:-unknown}" \
  "$EFFECTIVE_LAUNCH_MANIFEST_DIGEST" \
  "$RUN_MODE" \
  "$APP_CONTENT_DELIVERY_JSON" \
  "$LAUNCH_RECEIPT" \
  "$TEST_LIVE_REPORT_PATH" <<'PY'
import json
import pathlib
import sys

(
    preflight_json,
    flutter_exit_code,
    environment,
    target,
    device_id,
    platform,
    handoff_digest,
    run_mode,
    delivery_json,
    launch_receipt_path,
    report_path,
) = sys.argv[1:]
preflight = json.loads(preflight_json)
delivery = json.loads(delivery_json)
exit_code = int(flutter_exit_code)
receipt = json.loads(pathlib.Path(launch_receipt_path).read_text(encoding="utf-8"))
if receipt.get("schema") != "app-launch-attempt":
    raise SystemExit("APP.LAUNCH.receipt_invalid: test_live report requires app-launch-attempt")
transition_states = [
    str(item.get("status") or "")
    for item in receipt.get("transitions") or []
    if isinstance(item, dict)
]
first_blocker = str(receipt.get("firstBlocker") or "")
launch_warnings = [str(item) for item in receipt.get("warnings") or []]
compile_status = (
    "compiled"
    if "compiled" in transition_states
    else "failed"
    if first_blocker == "APP.LAUNCH.compile_failed"
    else "not_reached"
)
install_status = (
    "installed"
    if "installed" in transition_states
    else "failed"
    if first_blocker == "APP.LAUNCH.install_failed"
    else "not_reached"
)
launch_status = (
    "launched"
    if "launched" in transition_states
    else "failed"
    if first_blocker == "APP.LAUNCH.launch_failed"
    else "not_reached"
)
runtime_status = (
    "degraded"
    if any(item.startswith("warning/runtime_degraded") for item in launch_warnings)
    else "not_evaluated"
)
runtime_checks = list(preflight.get("runtimeChecks") or [])
service_health = {
    str(check.get("name") or "unknown"): {
        "ready": bool(check.get("ready")),
        "statusCode": check.get("statusCode"),
    }
    for check in runtime_checks
}
provider_availability = {
    name: service_health.get(name, {"ready": False, "statusCode": None})
    for name in ("provider-protocol-substitute", "sms-provider-substitute")
}
report = {
    "schema": "quwoquan_app.test_live_launch",
    "environment": environment,
    "target": target,
    "deviceId": device_id,
    "platform": platform,
    "runMode": run_mode,
    "nonPromotable": True,
    "contentLive": preflight.get("contentLive", "not_evaluated"),
    "launchPolicy": "test_live",
    "compileStatus": compile_status,
    "installStatus": install_status,
    "launchStatus": launch_status,
    "runtimeStatus": runtime_status,
    "lifecycleStatus": receipt.get("status"),
    "firstBlocker": first_blocker,
    "exitCode": exit_code,
    "runtimeWarnings": list(dict.fromkeys([
        *list(preflight.get("warnings") or []),
        *launch_warnings,
    ])),
    "serviceHealth": service_health,
    "contentAvailability": preflight.get("contentAvailability")
    or {"state": "unbound"},
    "contentDelivery": {
        "status": "passed" if delivery.get("exitCode") == 0 else "not_evaluated",
        "counts": delivery.get("counts") or {},
    },
    "providerAvailability": provider_availability,
    "effectiveLaunchManifestDigest": handoff_digest,
    "launchAttemptId": receipt.get("attemptId"),
}
path = pathlib.Path(report_path)
path.write_text(
    json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
print(f"[run] test_live report: {path}")
PY

exit "$FLUTTER_RUN_EXIT_CODE"
