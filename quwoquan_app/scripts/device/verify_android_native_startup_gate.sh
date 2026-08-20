#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
APP_DIR="${REPO_ROOT}/quwoquan_app"
DEVICE_ID="${1:-${ANDROID_SERIAL:-}}"
if [[ -z "${DEVICE_ID}" ]]; then
  echo "GATE_BLOCK: Android device ID is required." >&2
  exit 2
fi

HANDOFF_FILE="$(mktemp "${TMPDIR:-/tmp}/qwq-native-startup-handoff.XXXXXX.json")"
cleanup() {
  rm -f "${HANDOFF_FILE}"
}
trap cleanup EXIT

cd "${REPO_ROOT}"
python3 quwoquan_app/scripts/device/build_launcher_handoff.py \
  --env alpha \
  --target alpha-local \
  --launch-mode native_startup_instrumentation \
  >"${HANDOFF_FILE}"

eval "$(
  python3 - "${HANDOFF_FILE}" <<'PY'
import base64
import json
import shlex
import sys

handoff = json.load(open(sys.argv[1], encoding="utf-8"))
encoded_defines = ",".join(
    base64.b64encode(f"{key}={value}".encode()).decode()
    for key, value in handoff["dartDefines"].items()
)
values = {
    "QWQ_APP_RUNTIME_ENV": handoff["environment"],
    "QWQ_LAUNCH_TARGET": handoff["target"],
    "QWQ_DART_DEFINES_DIGEST": handoff["dartDefinesDigest"],
    "QWQ_EXPECTED_RUNTIME_CONFIG_DIGEST": handoff["runtimeConfigDigest"],
    "QWQ_EFFECTIVE_LAUNCH_MANIFEST_DIGEST": handoff[
        "effectiveLaunchManifestDigest"
    ],
    "GRADLE_DART_DEFINES": encoded_defines,
}
for key, value in values.items():
    print(f"export {key}={shlex.quote(str(value))}")
PY
)"

export ANDROID_SERIAL="${DEVICE_ID}"
export QWQ_RUN_DEVICE_ID="${DEVICE_ID}"
export QWQ_APP_BUILD_CONTEXT="package-only"

cd "${APP_DIR}/android"
./gradlew :app:connectedDebugAndroidTest \
  -Pandroid.testInstrumentationRunnerArguments.class=com.quwoquan.quwoquan_app.StartupGateHandoffInstrumentedTest,com.quwoquan.quwoquan_app.StartupLaunchResourceInstrumentedTest \
  -Pdart-defines="${GRADLE_DART_DEFINES}"
