#!/usr/bin/env bash
# 使用 env-package-backed Remote 启动入口，避免裸跑漏掉 runtime/release 合同。
set -euo pipefail

# 本 recovery 工作树已废弃：其构建派生物（native runtime package/handoff）随主仓
# 契约演进立即过期，曾直接导致启动配置静默失效被误判为云侧故障。
# 开发启动统一从主工作树经 canonical handoff 执行。
if [[ "$(cd "$(dirname "$0")/.." && pwd)" == *"quwoquan-recovery-"* ]]; then
  echo "GATE_BLOCK: 此工作树 (quwoquan-recovery-*) 已废弃，禁止从这里启动 App。" >&2
  echo "请用 git worktree list 定位 canonical 主工作树，再从其仓库根目录执行 ./quwoquan_app/run.sh。" >&2
  exit 1
fi

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$APP_DIR/.." && pwd)"
QWQ_OUTPUT_ROOT="${QWQ_OUTPUT_ROOT:-$ROOT_DIR/.qwq_output}"
QWQ_OUTPUT_ROOT="$(python3 - "$QWQ_OUTPUT_ROOT" <<'PY'
import pathlib
import sys

print(pathlib.Path(sys.argv[1]).expanduser().absolute())
PY
)"
export QWQ_OUTPUT_ROOT
# 依赖回放随后会把 HOME 切换到私有构建目录；先冻结仓库外 deployment authority，
# 避免 runtime-config 签名路径落入可写 source projection。output_paths 会再次校验。
QWQ_DEPLOY_WORK_ROOT="${QWQ_DEPLOY_WORK_ROOT:-${HOME}/.cache/quwoquan/deploy}"
export QWQ_DEPLOY_WORK_ROOT
ORIGINAL_LAUNCH_ARGUMENTS=("$@")
QWQ_DEV_LAUNCH_HERMETIC=0
for argument in "${ORIGINAL_LAUNCH_ARGUMENTS[@]}"; do
  if [[ "$argument" == "--hermetic" ]]; then
    QWQ_DEV_LAUNCH_HERMETIC=1
    break
  fi
done
# 开发默认直连当前 live worktree；--hermetic 与 app-content-uat 保留发布级流水线。
if [[ "$QWQ_DEV_LAUNCH_HERMETIC" == "0" \
   && "${QWQ_CANONICAL_LAUNCH_ACTOR:-}" != "app-content-uat" \
   && -z "${QWQ_WORKSPACE_SOURCE_CAPSULE_MANIFEST:-}" \
   && ( -e "$ROOT_DIR/.git" || -L "$ROOT_DIR/.git" ) ]]; then
  exec "$APP_DIR/scripts/device/dev_launch.sh" "${ORIGINAL_LAUNCH_ARGUMENTS[@]}"
fi

# Hermetic direct run.sh always re-execs from a frozen private source projection.
# app-content-uat already supplies its own candidate projection and therefore
# skips this workspace-only wrapper.
enter_workspace_launch_projection() {
  if [[ -n "${QWQ_WORKSPACE_SOURCE_CAPSULE_MANIFEST:-}" \
     || ( ! -e "$ROOT_DIR/.git" && ! -L "$ROOT_DIR/.git" ) ]]; then
    return 0
  fi
  # 依赖 bundle missing/stale 的一次性交互式自动同步。该标志只属于本 recovery 路径，
  # 与后文 iOS 重试的 DEPENDENCY_RETRY 状态机无关，也不共享任何变量。
  WORKSPACE_DEPENDENCY_AUTO_SYNC_USED=0
  WORKSPACE_ATTEMPT_BASE="$QWQ_OUTPUT_ROOT/env/repo/runs/$(date -u +%Y%m%dT%H%M%SZ)-$$-workspace-launch"
  WORKSPACE_ATTEMPT_ROOT="${WORKSPACE_ATTEMPT_BASE}-initial"
  WORKSPACE_PROJECTION_STATUS=0
  # stderr 直接继承：missing/stale typed blocker 行原样先于 recovery 说明输出；
  # stdout 捕获失败 envelope 供机器判别。
  if WORKSPACE_PROJECTION_JSON="$(
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}" \
      python3 "$APP_DIR/scripts/device/prepare_workspace_launch_projection.py" \
      --output-root "$QWQ_OUTPUT_ROOT" \
      --attempt-root "$WORKSPACE_ATTEMPT_ROOT"
  )"; then
    :
  else
    WORKSPACE_PROJECTION_STATUS=$?
  fi
  if [[ "$WORKSPACE_PROJECTION_STATUS" -ne 0 ]]; then
    WORKSPACE_PROJECTION_ERROR_CODE="$(python3 - "$WORKSPACE_PROJECTION_JSON" <<'PY'
import json
import sys

try:
    payload = json.loads(sys.argv[1])
except ValueError:
    payload = None
if isinstance(payload, dict) and payload.get("status") == "failed":
    print(str(payload.get("errorCode") or ""))
PY
)" || WORKSPACE_PROJECTION_ERROR_CODE=""
    # 恢复必须同时满足：missing/stale 码、双 TTY、live workspace 外层入口、且本进程未同步过。
    case "$WORKSPACE_PROJECTION_ERROR_CODE" in
      APP.DEPENDENCY.bundle_missing)
        WORKSPACE_DEPENDENCY_AUTO_SYNC_REASON="缺失"
        ;;
      APP.DEPENDENCY.bundle_stale)
        WORKSPACE_DEPENDENCY_AUTO_SYNC_REASON="过期"
        ;;
      *)
        WORKSPACE_DEPENDENCY_AUTO_SYNC_REASON=""
        ;;
    esac
    if [[ -z "$WORKSPACE_DEPENDENCY_AUTO_SYNC_REASON" \
       || "$WORKSPACE_DEPENDENCY_AUTO_SYNC_USED" != "0" \
       || ! ( -t 0 && -t 2 ) \
       || -n "${QWQ_WORKSPACE_SOURCE_CAPSULE_MANIFEST:-}" \
       || ( ! -e "$ROOT_DIR/.git" && ! -L "$ROOT_DIR/.git" ) ]]; then
      echo "[run] APP.LAUNCH.workspace_entrypoint_inactive: unable to freeze a private workspace launch projection." >&2
      exit 2
    fi
    WORKSPACE_DEPENDENCY_AUTO_SYNC_USED=1
    echo "[run] 检测到依赖 bundle 已${WORKSPACE_DEPENDENCY_AUTO_SYNC_REASON}（${WORKSPACE_PROJECTION_ERROR_CODE}）：现在执行一次 canonical 依赖同步 stackctl app-dependency-sync，完成后自动重试一次启动投影。" >&2
    WORKSPACE_DEPENDENCY_SYNC_REPORT="$(mktemp "${TMPDIR:-/tmp}/qwq-app-dependency-sync-report.XXXXXX")"
    WORKSPACE_DEPENDENCY_SYNC_STATUS=0
    if PYTHONDONTWRITEBYTECODE=1 \
      python3 "$ROOT_DIR/quwoquan_ops/cli/stackctl.py" --output-format json app-dependency-sync \
      >"$WORKSPACE_DEPENDENCY_SYNC_REPORT"; then
      :
    else
      WORKSPACE_DEPENDENCY_SYNC_STATUS=$?
    fi
    WORKSPACE_DEPENDENCY_SYNC_PARSE_STATUS=0
    if WORKSPACE_DEPENDENCY_SYNC_ATTEMPT_ID="$(
      python3 - "$WORKSPACE_DEPENDENCY_SYNC_REPORT" "$WORKSPACE_DEPENDENCY_SYNC_STATUS" <<'PY'
import json
import pathlib
import re
import sys

report = pathlib.Path(sys.argv[1])
command_status = int(sys.argv[2])
try:
    encoded = report.read_text(encoding="utf-8")
    if not encoded.strip():
        raise ValueError("empty sync JSON")
    payload = json.loads(encoded)
except (OSError, UnicodeError, ValueError):
    raise SystemExit(3)
if not isinstance(payload, dict):
    raise SystemExit(3)
exit_code = payload.get("exitCode")
summary = payload.get("summary")
details = payload.get("details")

def sanitized(value: str) -> str:
    text = " ".join(value.splitlines()).strip()
    lowered = text.casefold()
    if any(
        marker in lowered
        for marker in (
            "-----begin private key-----",
            "privatekey",
            "private_key",
            "private-key",
            "trustedpublickeys",
            "trusted_public_keys",
            "trusted-public-keys",
            "runtime-config-trust.json",
        )
    ):
        return "[REDACTED dependency diagnostic]"
    text = re.sub(
        r"(?i)\b(authorization|password|passwd|token|secret|api[_-]?key)\b"
        r"\s*[:=]\s*(?:bearer\s+)?[^\s,;]+",
        r"\1=[REDACTED]",
        text,
    )
    return text or "[empty dependency diagnostic]"

def emit_details() -> None:
    values = (
        details
        if isinstance(details, list) and all(isinstance(item, str) for item in details)
        else []
    )
    values = values or [
        summary
        if isinstance(summary, str) and summary
        else "APP.DEPENDENCY.sync_blocked: no details reported"
    ]
    for item in values:
        print("[run] dependency sync detail: " + sanitized(item), file=sys.stderr)

if (
    not isinstance(exit_code, int)
    or isinstance(exit_code, bool)
    or not isinstance(summary, str)
    or not isinstance(details, list)
    or not all(isinstance(item, str) for item in details)
):
    emit_details()
    print(
        "[run] APP.DEPENDENCY.sync_result_invalid: dependency sync JSON envelope is invalid.",
        file=sys.stderr,
    )
    raise SystemExit(2)

activation = payload.get("activation")
committed = (
    exit_code == 0
    and isinstance(activation, dict)
    and activation.get("status") == "committed"
    and isinstance(activation.get("attemptId"), str)
    and bool(activation["attemptId"])
)
if command_status != 0 or exit_code != 0:
    emit_details()
    if command_status != exit_code:
        print(
            "[run] APP.DEPENDENCY.sync_result_exit_mismatch: "
            f"process={command_status} result={exit_code}",
            file=sys.stderr,
        )
    raise SystemExit(2)
if not committed:
    emit_details()
    print(
        "[run] APP.DEPENDENCY.sync_activation_uncommitted: "
        "dependency sync did not report a committed activation.",
        file=sys.stderr,
    )
    raise SystemExit(2)
print(activation["attemptId"])
PY
    )"; then
      :
    else
      WORKSPACE_DEPENDENCY_SYNC_PARSE_STATUS=$?
      WORKSPACE_DEPENDENCY_SYNC_ATTEMPT_ID=""
    fi
    if ! rm -f -- "$WORKSPACE_DEPENDENCY_SYNC_REPORT"; then
      echo "[run] APP.DEPENDENCY.sync_report_cleanup_warning: unable to remove temporary sync report." >&2
    fi
    unset WORKSPACE_DEPENDENCY_SYNC_REPORT
    if [[ "$WORKSPACE_DEPENDENCY_SYNC_PARSE_STATUS" -ne 0 ]]; then
      if [[ "$WORKSPACE_DEPENDENCY_SYNC_PARSE_STATUS" -eq 3 ]]; then
        echo "[run] ${WORKSPACE_PROJECTION_ERROR_CODE}: canonical dependency sync returned invalid or empty JSON; workspace launch stays blocked." >&2
      fi
      echo "[run] APP.LAUNCH.workspace_entrypoint_inactive: unable to freeze a private workspace launch projection." >&2
      exit 2
    fi
    # 独立读回：fresh Python 进程经 canonical loader 验证 active 指针确实指向本次 sync。
    if ! WORKSPACE_DEPENDENCY_ACTIVE_ATTEMPT_ID="$(
      PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}" \
        QWQ_OUTPUT_ROOT="$QWQ_OUTPUT_ROOT" \
        python3 - "$ROOT_DIR" <<'PY'
import pathlib
import sys

from quwoquan_ops.cli.lib.package_reuse.dependency_bundle import (
    load_active_dependency_bundle,
)

bundle = load_active_dependency_bundle(repo_root=pathlib.Path(sys.argv[1]))
print(str(bundle.active.get("attemptId") or ""))
PY
    )"; then
      echo "[run] ${WORKSPACE_PROJECTION_ERROR_CODE}: post-sync dependency bundle readback failed; not retrying." >&2
      echo "[run] APP.LAUNCH.workspace_entrypoint_inactive: unable to freeze a private workspace launch projection." >&2
      exit 2
    fi
    if [[ -z "$WORKSPACE_DEPENDENCY_SYNC_ATTEMPT_ID" \
       || "$WORKSPACE_DEPENDENCY_ACTIVE_ATTEMPT_ID" != "$WORKSPACE_DEPENDENCY_SYNC_ATTEMPT_ID" ]]; then
      echo "[run] ${WORKSPACE_PROJECTION_ERROR_CODE}: post-sync active attempt mismatch; not retrying." >&2
      echo "[run] APP.LAUNCH.workspace_entrypoint_inactive: unable to freeze a private workspace launch projection." >&2
      exit 2
    fi
    echo "[run] 依赖同步已提交（attemptId=${WORKSPACE_DEPENDENCY_SYNC_ATTEMPT_ID}），重试一次 workspace 启动投影。" >&2
    WORKSPACE_ATTEMPT_ROOT="${WORKSPACE_ATTEMPT_BASE}-retry"
    if WORKSPACE_PROJECTION_JSON="$(
      PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}" \
        python3 "$APP_DIR/scripts/device/prepare_workspace_launch_projection.py" \
        --output-root "$QWQ_OUTPUT_ROOT" \
        --attempt-root "$WORKSPACE_ATTEMPT_ROOT"
    )"; then
      :
    else
      echo "[run] APP.LAUNCH.workspace_entrypoint_inactive: unable to freeze a private workspace launch projection." >&2
      exit 2
    fi
  fi
  WORKSPACE_PROJECTION_EXPORTS="$(python3 - "$WORKSPACE_PROJECTION_JSON" <<'PY'
import json
import shlex
import sys

payload = json.loads(sys.argv[1])
for field in (
    "projectionRoot",
    "sourceCapsuleManifest",
    "sourceRevision",
    "sourceCapsuleDigest",
):
    if not str(payload.get(field) or ""):
        raise SystemExit(f"workspace projection is missing {field}")
print(
    "QWQ_WORKSPACE_PROJECTION_ROOT="
    + shlex.quote(payload["projectionRoot"])
)
print(
    "QWQ_WORKSPACE_SOURCE_CAPSULE_MANIFEST="
    + shlex.quote(payload["sourceCapsuleManifest"])
)
print(
    "QWQ_WORKSPACE_SOURCE_REVISION="
    + shlex.quote(payload["sourceRevision"])
)
print(
    "QWQ_WORKSPACE_SOURCE_CAPSULE_DIGEST="
    + shlex.quote(payload["sourceCapsuleDigest"])
)
PY
)"
  eval "$WORKSPACE_PROJECTION_EXPORTS"
  export QWQ_WORKSPACE_SOURCE_CAPSULE_MANIFEST
  export QWQ_WORKSPACE_SOURCE_REVISION QWQ_WORKSPACE_SOURCE_CAPSULE_DIGEST
  PROJECTED_APP_DIR="$QWQ_WORKSPACE_PROJECTION_ROOT/quwoquan_app"
  exec "$PROJECTED_APP_DIR/run.sh" "${ORIGINAL_LAUNCH_ARGUMENTS[@]}"
}
if [[ -n "${QWQ_WORKSPACE_SOURCE_CAPSULE_MANIFEST:-}" ]]; then
  if ! PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}" \
    python3 - \
      "$QWQ_OUTPUT_ROOT" "$ROOT_DIR" \
      "$QWQ_WORKSPACE_SOURCE_CAPSULE_MANIFEST" <<'PY'
import pathlib
import sys

from quwoquan_app.scripts.device.prepare_workspace_launch_projection import (
    verify_workspace_launch_projection,
)

verify_workspace_launch_projection(
    output_root=pathlib.Path(sys.argv[1]),
    projection_root=pathlib.Path(sys.argv[2]),
    source_capsule_manifest=pathlib.Path(sys.argv[3]),
)
PY
  then
    echo "[run] APP.LAUNCH.workspace_entrypoint_inactive: private workspace projection verification failed." >&2
    exit 2
  fi
  export QWQ_PACKAGE_SOURCE_CAPSULE_MANIFEST="$QWQ_WORKSPACE_SOURCE_CAPSULE_MANIFEST"
fi
# bytecode 缓存统一落 local/cache/**：local/<target>/ 只允许 process/ 与 cache/，
# 直接写 local/python-cache/<name> 会被 verify_output_layout 判为非法布局。
export PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-$QWQ_OUTPUT_ROOT/env/repo/local/cache/python/app-launch}"
REQUESTED_ENVIRONMENT="${QWQ_ENVIRONMENT:-}"
REQUESTED_TARGET=""
REQUESTED_DEVICE_ID=""
# workspace surface（IDE attach）无命令行 --mode 通道，
# mode 与环境同构经 QWQ_RUN_MODE 选择；显式 --mode 参数覆盖环境值。
RUN_MODE="${QWQ_RUN_MODE:-content-live}"
# launch surface（launch provenance）只记录启动来源，不改变任何行为分支；
# 值域是 app_artifact_manifest.launch_provenances 闭集中本入口可达的子集，
# 子集与闭集的一致性由 local_contract 断言。
LAUNCH_PROVENANCE="${QWQ_APP_LAUNCH_PROVENANCE:-canonical_launcher}"
case "$LAUNCH_PROVENANCE" in
  canonical_launcher|workspace_ide_debug) ;;
  *)
    echo "[run] APP.LAUNCH.launch_surface_unsupported: '$LAUNCH_PROVENANCE'; supported provenance is canonical_launcher or workspace_ide_debug." >&2
    exit 2
    ;;
esac
ENSURE_RUNTIME=0
LAUNCH_RECEIPT="${QWQ_APP_LAUNCH_RECEIPT:-}"
LAUNCH_LOG_REF="${QWQ_APP_LAUNCH_LOG_REF:-}"
TEST_LIVE_REPORT_OVERRIDE="${QWQ_APP_TEST_LIVE_REPORT:-}"
CANONICAL_LAUNCH_CONTROL="${QWQ_CANONICAL_LAUNCH_CONTROL:-}"
CANONICAL_LAUNCH_CONTROL_DIGEST="${QWQ_CANONICAL_LAUNCH_CONTROL_DIGEST:-}"
STARTUP_TERMINAL_RECEIPT="${QWQ_APP_STARTUP_TERMINAL_RECEIPT:-}"
EXIT_AFTER_LAUNCH=0
IDE_VM_SERVICE_INFO_FILE=""
IDE_VM_SERVICE_ALLOWED_ROOT=""
RUNTIME_CONFIG_MATERIAL_ROOT=""
RUNTIME_CONFIG_TRUST_PATH=""
TEARDOWN_RECEIPT=""
QWQ_BUILD_PROJECTION_SEAL_DIGEST=""
QWQ_BUILD_PROJECTION_SEAL_REF=""
QWQ_PREBUILD_BUILD_PROJECTION_DIGEST=""
QWQ_CANONICAL_EXPECTED_BUILD_PROJECTION_DIGEST=""
QWQ_DEPENDENCY_PROJECTION_EXPECTATION_REF=""
QWQ_DEPENDENCY_PROJECTION_EXPECTATION_DIGEST=""
QWQ_DEPENDENCY_PROJECTION_PREBUILD_READBACK_REF=""
QWQ_DEPENDENCY_PROJECTION_PREBUILD_READBACK_DIGEST=""
QWQ_DEPENDENCY_PROJECTION_POSTBUILD_READBACK_REF=""
QWQ_DEPENDENCY_PROJECTION_POSTBUILD_READBACK_DIGEST=""
FLUTTER_ARGUMENTS=()
PRELAUNCH_WARNINGS=()
TEARDOWN_WARNINGS=()

record_prelaunch_warning() {
  local warning="${1//$'\n'/ }"
  [[ -n "$warning" ]] || return 0
  local existing
  for existing in "${PRELAUNCH_WARNINGS[@]:-}"; do
    [[ "$existing" != "$warning" ]] || return 0
  done
  PRELAUNCH_WARNINGS+=("$warning")
  echo "[run] WARN: $warning" >&2
}

record_teardown_warning() {
  local warning="${1//$'\n'/ }"
  [[ -n "$warning" ]] || return 0
  TEARDOWN_WARNINGS+=("$warning")
  echo "[run] WARN: $warning" >&2
}

seal_app_content_projection_build() {
  local phase="${1:-}"
  [[ -n "$TEST_LIVE_REPORT_OVERRIDE" ]] || return 0
  local seal_exports
  if ! seal_exports="$(
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}" \
      python3 - \
      "$phase" \
      "$QWQ_CANONICAL_SOURCE_CAPSULE_MANIFEST_REF" \
      "$ROOT_DIR" \
      "$QWQ_CANONICAL_BUILD_PROJECTION_POLICY_ID" \
      "$QWQ_CANONICAL_EXPECTED_BUILD_PROJECTION_DIGEST" \
      "$QWQ_OUTPUT_ROOT" \
      "$QWQ_CANONICAL_BUILD_PROJECTION_SEAL_REF" <<'PY'
import pathlib
import shlex
import sys

from quwoquan_ops.cli.commands.app_preflight_uat_launch import (
    seal_projection_build,
    write_app_content_projection_build_seal,
)

(
    phase,
    manifest_ref,
    projection_root,
    policy_id,
    expected_digest,
    output_root,
    seal_ref,
) = sys.argv[1:]
if phase not in {"predependency", "prebuild", "evidence"}:
    raise SystemExit("build projection seal phase is invalid")
seal = seal_projection_build(
    pathlib.Path(manifest_ref),
    pathlib.Path(projection_root),
    policy_id=policy_id,
    expected_build_projection_digest=(
        (expected_digest or None) if phase != "evidence" else None
    ),
)
if phase == "predependency":
    pass
elif phase == "prebuild":
    print(
        "QWQ_PREBUILD_BUILD_PROJECTION_DIGEST="
        + shlex.quote(seal.build_projection_digest)
    )
else:
    evidence = write_app_content_projection_build_seal(
        seal=seal,
        output_root=pathlib.Path(output_root),
        seal_path=pathlib.Path(seal_ref),
    )
    print(
        "QWQ_BUILD_PROJECTION_SEAL_DIGEST="
        + shlex.quote(str(evidence["buildProjectionSealDigest"]))
    )
    print(
        "QWQ_BUILD_PROJECTION_SEAL_REF="
        + shlex.quote(str(evidence["buildProjectionSealRef"]))
    )
PY
  2>&1)"; then
    local first_launch_blocker=""
    if [[ "$phase" == "evidence" \
       && "${FLUTTER_RUN_EXIT_CODE:-0}" != "0" \
       && -n "$LAUNCH_RECEIPT" ]]; then
      first_launch_blocker="$(
        python3 - "$LAUNCH_RECEIPT" <<'PY' 2>/dev/null || true
import pathlib
import sys

from quwoquan_ops.cli.lib.app_launch_attempt import (
    LAUNCH_BLOCKERS,
    read_app_launch_attempt,
)

try:
    receipt = read_app_launch_attempt(pathlib.Path(sys.argv[1]))
except (OSError, TypeError, ValueError):
    raise SystemExit(0) from None
blocker = str(receipt.get("firstBlocker") or "")
if blocker in LAUNCH_BLOCKERS:
    print(blocker)
PY
      )"
    fi
    if [[ -n "$first_launch_blocker" ]]; then
      echo "[run] $first_launch_blocker: supervisor attempt failed; postbuild projection seal failure is secondary." >&2
      echo "[run] APP.LAUNCH.receipt_invalid: secondary build projection seal failure during $phase." >&2
    else
      echo "[run] APP.LAUNCH.receipt_invalid: build projection seal failed during $phase." >&2
    fi
    if [[ -n "$seal_exports" ]]; then
      echo "[run] build projection seal detail: ${seal_exports//$'\n'/ }" >&2
    fi
    return 2
  fi
  eval "$seal_exports"
  export QWQ_PREBUILD_BUILD_PROJECTION_DIGEST
  export QWQ_BUILD_PROJECTION_SEAL_DIGEST QWQ_BUILD_PROJECTION_SEAL_REF
}

verify_dependency_projection_after_command() {
  local phase="${1:-}"
  local readback_root=""
  local readback_exports=""
  if [[ "$phase" != "prebuild" && "$phase" != "postbuild" ]]; then
    echo "[run] APP.DEPENDENCY.projection_expectation_invalid: dependency readback phase is invalid." >&2
    return 2
  fi
  if [[ -z "$QWQ_DEPENDENCY_PROJECTION_EXPECTATION_REF" \
     || -z "$QWQ_DEPENDENCY_PROJECTION_EXPECTATION_DIGEST" ]]; then
    echo "[run] APP.DEPENDENCY.projection_expectation_invalid: dependency expectation identity is absent." >&2
    return 2
  fi
  if ! readback_root="$(
    mktemp -d "$DEPENDENCY_PRIVATE_STATE_ROOT/dependency-projection-${phase}-readback.XXXXXX"
  )"; then
    echo "[run] APP.DEPENDENCY.projection_expectation_invalid: unable to allocate fresh dependency readback evidence." >&2
    return 2
  fi
  if ! readback_exports="$(
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}" \
      python3 "$APP_DIR/scripts/device/verify_flutter_dependencies.py" \
      --projection-root "$ROOT_DIR" \
      --expectation "$QWQ_DEPENDENCY_PROJECTION_EXPECTATION_REF" \
      --expectation-digest "$QWQ_DEPENDENCY_PROJECTION_EXPECTATION_DIGEST" \
      --readback-output "$readback_root/readback.json" \
      --phase "$phase" \
      --environment-owner production
  )"; then
    echo "[run] APP.DEPENDENCY.projection_cas_drift: dependency projection changed during $phase verification." >&2
    if [[ -n "$readback_exports" ]]; then
      echo "[run] dependency projection detail: ${readback_exports//$'\n'/ }" >&2
    fi
    return 2
  fi
  eval "$readback_exports"
  export QWQ_DEPENDENCY_PROJECTION_PREBUILD_READBACK_REF
  export QWQ_DEPENDENCY_PROJECTION_PREBUILD_READBACK_DIGEST
  export QWQ_DEPENDENCY_PROJECTION_POSTBUILD_READBACK_REF
  export QWQ_DEPENDENCY_PROJECTION_POSTBUILD_READBACK_DIGEST
}

verify_cocoapods_launch_identity() {
  local identity_exports=""
  if ! identity_exports="$(
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}" \
      python3 - 2>&1 <<'PY'
import os
import shlex

from quwoquan_ops.cli.lib.app_dependency_toolchain import (
    validate_cocoapods_child_environment,
)

identity, environment = validate_cocoapods_child_environment(os.environ)
for key, value in {
    **identity.as_environment(),
    "PATH": environment["PATH"],
}.items():
    print(f"export {key}={shlex.quote(value)}")
PY
  )"; then
    if [[ -n "$identity_exports" ]]; then
      echo "[run] ${identity_exports//$'\n'/ }" >&2
    else
      echo "[run] APP.DEPENDENCY.cocoapods_mixed: CocoaPods identity validation failed." >&2
    fi
    return 2
  fi
  eval "$identity_exports"
  export PATH QWQ_COCOAPODS_EXECUTABLE QWQ_COCOAPODS_VERSION
  export QWQ_COCOAPODS_EXECUTABLE_DIGEST
  export QWQ_COCOAPODS_RUNTIME_ENVIRONMENT_DIGEST
  export QWQ_COCOAPODS_COMMAND_RESOLUTION_DIGEST
  export QWQ_COCOAPODS_BINDING_SEAL
}

print_usage() {
  cat <<'EOF'
Usage: run.sh [--env alpha|beta|gamma] [--target alpha-local|beta-local|gamma-local]
              [--mode content-live|ui-only] [--launch-receipt <path>]
              [--launch-log-ref <path>] [--ensure-runtime] [-d <device>]

Defaults to --env alpha. Without -d in an interactive TTY, a numbered device list is
shown for one-time selection; non-TTY invocations must pass -d explicitly.

Both test_live modes continue through a real build, install, activation and launch when
service, Provider, content or observability readiness is unavailable. content-live
observes the real Remote outcome after launch; every test_live result is non-promotable.
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
    --hermetic)
      shift
      ;;
    --ensure-runtime)
      ENSURE_RUNTIME=1
      shift
      ;;
    -d|--device-id|--device)
      value="${2:-}"
      if [[ -z "$value" ]]; then
        echo "[run] GATE_BLOCK: $1 requires a device id." >&2
        exit 2
      fi
      if [[ -n "$REQUESTED_DEVICE_ID" && "$REQUESTED_DEVICE_ID" != "$value" ]]; then
        echo "[run] GATE_BLOCK: conflicting device selectors are forbidden." >&2
        exit 2
      fi
      REQUESTED_DEVICE_ID="$value"
      shift 2
      ;;
    --device-id=*|--device=*)
      value="${1#*=}"
      if [[ -z "$value" ]]; then
        echo "[run] GATE_BLOCK: --device-id requires a device id." >&2
        exit 2
      fi
      if [[ -n "$REQUESTED_DEVICE_ID" && "$REQUESTED_DEVICE_ID" != "$value" ]]; then
        echo "[run] GATE_BLOCK: conflicting device selectors are forbidden." >&2
        exit 2
      fi
      REQUESTED_DEVICE_ID="$value"
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
    --test-live-report)
      TEST_LIVE_REPORT_OVERRIDE="${2:-}"
      [[ -n "$TEST_LIVE_REPORT_OVERRIDE" ]] || {
        echo "[run] GATE_BLOCK: --test-live-report requires a path." >&2
        exit 2
      }
      shift 2
      ;;
    --test-live-report=*)
      TEST_LIVE_REPORT_OVERRIDE="${1#*=}"
      shift
      ;;
    --exit-after-launch)
      EXIT_AFTER_LAUNCH=1
      shift
      ;;
    --ide-vm-service-info)
      IDE_VM_SERVICE_INFO_FILE="${2:-}"
      [[ -n "$IDE_VM_SERVICE_INFO_FILE" ]] || {
        echo "[run] GATE_BLOCK: --ide-vm-service-info requires an absolute path." >&2
        exit 2
      }
      shift 2
      ;;
    --ide-vm-service-info=*)
      IDE_VM_SERVICE_INFO_FILE="${1#*=}"
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
if (( ${#FLUTTER_ARGUMENTS[@]} == 0 )); then
  set --
else
  set -- "${FLUTTER_ARGUMENTS[@]}"
fi
if [[ "$EXIT_AFTER_LAUNCH" == "1" || -n "$TEST_LIVE_REPORT_OVERRIDE" ]]; then
  if [[ "${QWQ_CANONICAL_LAUNCH_ACTOR:-}" != "app-content-uat" ]]; then
    echo "[run] APP.LAUNCH.launch_surface_unsupported: bounded launch/report controls are reserved for the canonical app-content-uat actor." >&2
    exit 2
  fi
  if [[ -z "$LAUNCH_RECEIPT" || -z "$TEST_LIVE_REPORT_OVERRIDE" ]]; then
    echo "[run] APP.LAUNCH.receipt_absent: app-content-uat requires explicit attempt and report paths." >&2
    exit 2
  fi
  if [[ -z "$CANONICAL_LAUNCH_CONTROL" || -z "$CANONICAL_LAUNCH_CONTROL_DIGEST" ]]; then
    echo "[run] APP.LAUNCH.launch_surface_unsupported: app-content-uat requires a private canonical launch control." >&2
    exit 2
  fi
  if ! CANONICAL_LAUNCH_EXPORTS="$(
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}" \
    python3 - \
    "$QWQ_OUTPUT_ROOT" \
    "$ROOT_DIR" \
    "$CANONICAL_LAUNCH_CONTROL" \
    "$CANONICAL_LAUNCH_CONTROL_DIGEST" \
    "$LAUNCH_RECEIPT" \
    "$TEST_LIVE_REPORT_OVERRIDE" \
    "${QWQ_PACKAGE_SOURCE_CAPSULE_MANIFEST:-}" <<'PY'
import hashlib
import json
import os
import pathlib
import re
import shlex
import stat
import sys

root = pathlib.Path(sys.argv[1]).expanduser().resolve()
source_root = pathlib.Path(sys.argv[2]).expanduser().resolve()
control_path = pathlib.Path(sys.argv[3]).expanduser()
declared_control_digest = sys.argv[4]
attempt_arg, report_arg, source_capsule_arg = sys.argv[5:]
if (
    not control_path.is_absolute()
    or control_path.is_symlink()
    or not control_path.is_file()
    or stat.S_IMODE(control_path.stat().st_mode) & 0o077
):
    raise SystemExit("canonical launch control is missing or not private")
try:
    control_path.resolve().relative_to(root)
except ValueError:
    raise SystemExit("canonical launch control escapes QWQ_OUTPUT_ROOT") from None
control = json.loads(control_path.read_text(encoding="utf-8"))
fields = {
    "schema", "actor", "environment", "target", "platform", "deviceId",
    "candidateDigest", "packageDigest", "sourceRevision", "sourceCapsuleDigest",
    "sourceCapsuleManifestDigest", "sourceCapsuleManifestRef",
    "sourceProjectionRoot", "sourceProjectionEvidenceDigest",
    "sourceProjectionEvidenceRef", "buildProjectionPolicyId",
    "buildProjectionSealRef", "expectedBuildProjectionDigest",
    "launchAttemptRef", "launchReportRef", "startupTerminalReceiptRef",
}
if not isinstance(control, dict) or set(control) != fields:
    raise SystemExit("canonical launch control fields mismatch")
encoded = json.dumps(
    control, ensure_ascii=False, sort_keys=True, separators=(",", ":")
).encode("utf-8")
actual_control_digest = "sha256:" + hashlib.sha256(encoded).hexdigest()
if actual_control_digest != declared_control_digest:
    raise SystemExit("canonical launch control digest mismatch")
if control.get("schema") != "quwoquan_ops.app_content_uat_launch_control.v1":
    raise SystemExit("canonical launch control schema mismatch")
if control.get("actor") != "app-content-uat":
    raise SystemExit("canonical launch control actor mismatch")
policy_by_platform = {
    "android": "flutter-android-3.47-gradle-8.14-agp-8.11.1",
    "android-physical": "flutter-android-3.47-gradle-8.14-agp-8.11.1",
    "ios-simulator": "flutter-ios-3.47-cocoapods-1.16.2",
    "ios-physical": "flutter-ios-3.47-cocoapods-1.16.2",
}
if policy_by_platform.get(control.get("platform")) != control.get(
    "buildProjectionPolicyId"
):
    raise SystemExit("canonical launch build projection policy mismatch")
expected_build_digest = control.get("expectedBuildProjectionDigest")
if expected_build_digest is not None and re.fullmatch(
    r"sha256:[0-9a-f]{64}", str(expected_build_digest)
) is None:
    raise SystemExit("canonical launch expected build projection digest is invalid")
for field in (
    "candidateDigest", "packageDigest", "sourceCapsuleDigest",
    "sourceCapsuleManifestDigest", "sourceProjectionEvidenceDigest",
):
    if re.fullmatch(r"sha256:[0-9a-f]{64}", str(control.get(field) or "")) is None:
        raise SystemExit(f"canonical launch control {field} is invalid")
if pathlib.Path(str(control.get("sourceProjectionRoot") or "")).resolve() != source_root:
    raise SystemExit("canonical launch source projection differs from run.sh root")
source_capsule = pathlib.Path(str(control.get("sourceCapsuleManifestRef") or ""))
if source_capsule_arg != str(source_capsule) or source_capsule.is_symlink() or not source_capsule.is_file():
    raise SystemExit("canonical launch source capsule reference drifted")
for label, raw, expected in (
    ("attempt", attempt_arg, control.get("launchAttemptRef")),
    ("report", report_arg, control.get("launchReportRef")),
    ("safe-terminal", control.get("startupTerminalReceiptRef"), control.get("startupTerminalReceiptRef")),
    ("build-projection-seal", control.get("buildProjectionSealRef"), control.get("buildProjectionSealRef")),
):
    candidate = pathlib.Path(raw).expanduser()
    if not candidate.is_absolute() or str(candidate) != str(expected):
        raise SystemExit(f"{label} path must be absolute")
    absolute = pathlib.Path(candidate.absolute())
    if absolute.exists() or absolute.is_symlink():
        raise SystemExit(f"{label} path must be fresh")
    try:
        absolute.resolve(strict=False).relative_to(root)
    except ValueError:
        raise SystemExit(f"{label} path must stay inside QWQ_OUTPUT_ROOT") from None
evidence_path = pathlib.Path(str(control.get("sourceProjectionEvidenceRef") or ""))
if evidence_path.is_symlink() or not evidence_path.is_file():
    raise SystemExit("canonical launch source projection evidence is missing")
evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
evidence_digest = "sha256:" + hashlib.sha256(json.dumps(
    evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":")
).encode("utf-8")).hexdigest()
if evidence_digest != control.get("sourceProjectionEvidenceDigest"):
    raise SystemExit("canonical launch source projection evidence drifted")
for name, value in {
    "QWQ_CANONICAL_CANDIDATE_DIGEST": control["candidateDigest"],
    "QWQ_CANONICAL_CANDIDATE_PACKAGE_DIGEST": control["packageDigest"],
    "QWQ_CANONICAL_SOURCE_PROJECTION_EVIDENCE_DIGEST": control["sourceProjectionEvidenceDigest"],
    "QWQ_CANONICAL_SOURCE_PROJECTION_EVIDENCE_REF": control["sourceProjectionEvidenceRef"],
    "QWQ_CANONICAL_SOURCE_CAPSULE_MANIFEST_DIGEST": control["sourceCapsuleManifestDigest"],
    "QWQ_CANONICAL_SOURCE_CAPSULE_MANIFEST_REF": control["sourceCapsuleManifestRef"],
    "QWQ_CANONICAL_BUILD_PROJECTION_POLICY_ID": control["buildProjectionPolicyId"],
    "QWQ_CANONICAL_BUILD_PROJECTION_SEAL_REF": control["buildProjectionSealRef"],
    "QWQ_CANONICAL_EXPECTED_BUILD_PROJECTION_DIGEST": expected_build_digest or "",
    "QWQ_PACKAGE_SOURCE_REVISION": control["sourceRevision"],
    "QWQ_PACKAGE_SOURCE_TREE_DIGEST": control["sourceCapsuleDigest"],
    "QWQ_CANONICAL_CONTROL_ENVIRONMENT": control["environment"],
    "QWQ_CANONICAL_CONTROL_TARGET": control["target"],
    "QWQ_CANONICAL_CONTROL_PLATFORM": control["platform"],
    "QWQ_CANONICAL_CONTROL_DEVICE_ID": control["deviceId"],
    "QWQ_APP_STARTUP_TERMINAL_RECEIPT": control["startupTerminalReceiptRef"],
}.items():
    print(name + "=" + shlex.quote(str(value)))
PY
  )"; then
    echo "[run] APP.LAUNCH.receipt_invalid: app-content-uat evidence paths are unsafe or stale." >&2
    exit 2
  fi
  eval "$CANONICAL_LAUNCH_EXPORTS"
  export QWQ_APP_STARTUP_TERMINAL_RECEIPT
  export QWQ_PACKAGE_SOURCE_REVISION QWQ_PACKAGE_SOURCE_TREE_DIGEST
  STARTUP_TERMINAL_RECEIPT="$QWQ_APP_STARTUP_TERMINAL_RECEIPT"
fi
if [[ "$LAUNCH_PROVENANCE" == "workspace_ide_debug" ]]; then
  if [[ -z "$IDE_VM_SERVICE_INFO_FILE" ]]; then
    echo "[run] APP.LAUNCH.workspace_entrypoint_inactive: workspace_ide_debug requires the controlled IDE projection." >&2
    exit 2
  fi
elif [[ -n "$IDE_VM_SERVICE_INFO_FILE" ]]; then
  echo "[run] APP.LAUNCH.launch_surface_unsupported: IDE VM service output is only valid for workspace_ide_debug." >&2
  exit 2
fi
if ! python3 - "$APP_DIR/scripts/device" "$@" <<'PY'
import sys

sys.path.insert(0, sys.argv[1])
from canonical_app_instance.arguments import (
    CanonicalExecutorError,
    sanitize_attach_arguments,
)

try:
    sanitize_attach_arguments(tuple(sys.argv[2:]))
except CanonicalExecutorError as error:
    print(f"[run] GATE_BLOCK: {error}", file=sys.stderr)
    raise SystemExit(2) from None
PY
then
  exit 2
fi

case "$RUN_MODE" in
  content-live|ui-only) ;;
  *)
    echo "[run] GATE_BLOCK: --mode / QWQ_RUN_MODE requires content-live|ui-only." >&2
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
export QWQ_APP_BUILD_PROFILE=nonprod
export QWQ_LAUNCH_TARGET="${REQUESTED_TARGET:-${QWQ_APP_RUNTIME_ENV}-local}"
export QWQ_APP_RUN_MODE="$RUN_MODE"
export QWQ_APP_BUILD_CONTEXT=runtime
export QWQ_APP_LAUNCH_POLICY=test_live
if [[ -n "$TEST_LIVE_REPORT_OVERRIDE" \
   && ( "$QWQ_CANONICAL_CONTROL_ENVIRONMENT" != "$QWQ_APP_RUNTIME_ENV" \
     || "$QWQ_CANONICAL_CONTROL_TARGET" != "$QWQ_LAUNCH_TARGET" ) ]]; then
  echo "[run] APP.LAUNCH.receipt_invalid: canonical launch control target/environment drifted." >&2
  exit 2
fi

ACTIVATION_TIMEOUT_SECONDS="${QWQ_APP_ACTIVATION_TIMEOUT_SECONDS:-30}"
LAUNCH_TIMEOUT_SECONDS="${QWQ_APP_LAUNCH_TIMEOUT_SECONDS:-900}"
if ! python3 - "$ACTIVATION_TIMEOUT_SECONDS" "$LAUNCH_TIMEOUT_SECONDS" <<'PY'
import math
import sys

for value in sys.argv[1:]:
    try:
        seconds = float(value)
    except ValueError:
        raise SystemExit(2) from None
    if not math.isfinite(seconds) or seconds <= 0:
        raise SystemExit(2)
PY
then
  echo "[run] GATE_BLOCK: activation and launch timeouts must be positive finite numbers." >&2
  exit 2
fi

# Cheap argument, launch-control and timeout validation must remain observable
# even when the managed dependency bundle is absent or stale. Only a valid
# launch attempt is frozen and re-executed from the private workspace source.
enter_workspace_launch_projection "${ORIGINAL_LAUNCH_ARGUMENTS[@]}"

if [[ "$LAUNCH_PROVENANCE" == "workspace_ide_debug" ]]; then
  if ! IDE_VM_SERVICE_ALLOWED_ROOT="$(
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}" \
      python3 - \
      "${QWQ_WORKSPACE_SOURCE_CAPSULE_MANIFEST:-}" "$ROOT_DIR" \
      "$QWQ_OUTPUT_ROOT" "$IDE_VM_SERVICE_INFO_FILE" <<'PY'
import pathlib
import sys

from quwoquan_app.scripts.device.canonical_app_instance.vm_service_info_file import (
    validate_private_vm_service_info_file,
    workspace_projection_vm_service_allowed_root,
)

allowed_root = workspace_projection_vm_service_allowed_root(
    source_capsule_manifest=pathlib.Path(sys.argv[1]),
    projection_root=pathlib.Path(sys.argv[2]),
    output_root=pathlib.Path(sys.argv[3]),
)
validate_private_vm_service_info_file(
    pathlib.Path(sys.argv[4]),
    allowed_root=allowed_root,
)
print(allowed_root)
PY
  )"; then
    echo "[run] APP.LAUNCH.workspace_entrypoint_inactive: IDE VM service output is not bound to the original workspace projection handoff." >&2
    exit 2
  fi
fi

cd "$APP_DIR"

for argument in "$@"; do
  case "$argument" in
    -t|--target|--target=*)
      echo "[run] GATE_BLOCK: raw Flutter entrypoint overrides are forbidden; use launcher --target before Flutter arguments."
      exit 2
      ;;
  esac
done

export QWQ_RUN_DEVICE_ID="$REQUESTED_DEVICE_ID"
DEVICE_ID="$QWQ_RUN_DEVICE_ID"
if [[ -n "$TEST_LIVE_REPORT_OVERRIDE" \
   && "$QWQ_CANONICAL_CONTROL_DEVICE_ID" != "$DEVICE_ID" ]]; then
  echo "[run] APP.LAUNCH.receipt_invalid: canonical launch control device drifted." >&2
  exit 2
fi

if [[ "$ENSURE_RUNTIME" == "1" ]]; then
  echo "[run] GATE_BLOCK: --ensure-runtime requires an explicit frozen candidate identity; the App launcher cannot infer or mutate it." >&2
  exit 2
fi

# App 运行模式到 preflight purpose 的映射只有一处实现，见
# quwoquan_ops/cli/lib/app_debug_preflight_handoff.py。
if ! PREFLIGHT_PURPOSE="$(
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}" \
    python3 -c 'import sys
from quwoquan_ops.cli.lib.app_debug_preflight_handoff import (
    app_debug_preflight_purpose,
)

try:
    sys.stdout.write(app_debug_preflight_purpose(sys.argv[1]))
except ValueError as error:
    sys.stdout.write(str(error))
    raise SystemExit(2) from None' "$RUN_MODE"
)"; then
  echo "[run] GATE_BLOCK: $PREFLIGHT_PURPOSE" >&2
  exit 2
fi

# managed dispatcher 入口：严格准备由 stackctl app-managed-prepare 单独完成，
# launcher 只 exact readback 私有 receipt 并复用其 trust/preflight/binding 结论。
# 未设 QWQ_MANAGED_FLUTTER_ENTRY 时本块零调用，direct run.sh 行为完全不变。
QWQ_MANAGED_PREPARATION_ACTIVE=0
# 本次前台进程是 consumer identity 的唯一 authority；ambient 不得覆盖。
QWQ_RUN_CONSUMER_ID="flutter-run-$$"
QWQ_CONSUMER_LEASE_ACQUIRED=0
QWQ_CONSUMER_LEASE_ID=""
QWQ_ANDROID_REVERSE_OWNED_PORTS=""
QWQ_MANAGED_DEVICE_TRUST_PLATFORM=""
QWQ_MANAGED_TRUST_CLEANUP_REQUIRED=0
QWQ_MANAGED_LEASE_CLEANUP_REQUIRED=0
export QWQ_RUN_CONSUMER_ID QWQ_CONSUMER_LEASE_ACQUIRED
export QWQ_CONSUMER_LEASE_ID QWQ_ANDROID_REVERSE_OWNED_PORTS
export QWQ_MANAGED_DEVICE_TRUST_PLATFORM QWQ_MANAGED_TRUST_CLEANUP_REQUIRED
export QWQ_MANAGED_LEASE_CLEANUP_REQUIRED

cleanup_managed_handoff_resources() {
  if [[ "${QWQ_MANAGED_TRUST_CLEANUP_REQUIRED:-0}" == "1" \
     && -n "${QWQ_MANAGED_DEVICE_TRUST_PLATFORM:-}" \
     && -n "${QWQ_CONSUMER_LEASE_ID:-}" ]]; then
    if ! PYTHONDONTWRITEBYTECODE=1 \
      python3 "$ROOT_DIR/quwoquan_ops/cli/stackctl.py" device-trust \
      --target "$QWQ_LAUNCH_TARGET" \
      --platform "$QWQ_MANAGED_DEVICE_TRUST_PLATFORM" \
      --action release --device "$DEVICE_ID" \
      --lease-id "$QWQ_CONSUMER_LEASE_ID" >/dev/null; then
      record_teardown_warning "failed to release managed device trust lease."
    fi
    QWQ_MANAGED_TRUST_CLEANUP_REQUIRED=0
  fi
  if command -v adb >/dev/null 2>&1 \
    && [[ -n "${QWQ_ANDROID_REVERSE_OWNED_PORTS:-}" ]]; then
    IFS=',' read -r -a managed_reverse_ports <<< "$QWQ_ANDROID_REVERSE_OWNED_PORTS"
    for port in "${managed_reverse_ports[@]}"; do
      [[ -n "$port" ]] || continue
      if ! adb -s "$DEVICE_ID" reverse --remove "tcp:$port" >/dev/null 2>&1; then
        record_teardown_warning "failed to remove owned adb reverse tcp:$port."
      fi
    done
    QWQ_ANDROID_REVERSE_OWNED_PORTS=""
  fi
  if [[ "${QWQ_MANAGED_LEASE_CLEANUP_REQUIRED:-0}" == "1" \
     || "${QWQ_CONSUMER_LEASE_ACQUIRED:-0}" == "1" ]]; then
    if [[ "${QWQ_MANAGED_PREPARATION_ACTIVE:-0}" == "1" \
       && ( "$QWQ_CONSUMER_LEASE_ID" != "$QWQ_MANAGED_CONSUMER_LEASE_ID" \
         || "$QWQ_RUN_CONSUMER_ID" != "$QWQ_MANAGED_CONSUMER_ID" ) ]]; then
      record_teardown_warning "managed lease cleanup identity drifted; refusing unrelated release."
      return
    fi
    if ! PYTHONDONTWRITEBYTECODE=1 \
      python3 "$ROOT_DIR/quwoquan_ops/cli/stackctl.py" consumer-lease release \
      --target "$QWQ_LAUNCH_TARGET" --device "$DEVICE_ID" \
      --consumer "$QWQ_RUN_CONSUMER_ID" >/dev/null; then
      record_teardown_warning "failed to release runtime consumer lease."
    fi
    QWQ_MANAGED_LEASE_CLEANUP_REQUIRED=0
    QWQ_CONSUMER_LEASE_ACQUIRED=0
  fi
}

# preparation 在 run.sh 接管前即可创建 stable-consumer lease；trap 必须先于命令安装，
# receipt command/readback 任一失败都至少按该 consumer 归还 lease。
managed_prelaunch_cleanup() {
  local exit_code=$?
  trap - EXIT
  set +e
  cleanup_managed_handoff_resources
  exit "$exit_code"
}

if [[ "${QWQ_MANAGED_FLUTTER_ENTRY:-}" == "1" ]]; then
  if [[ -z "$DEVICE_ID" ]]; then
    echo "[run] APP.PREPARATION.receipt_invalid: managed flutter entry requires an explicit --device id." >&2
    exit 2
  fi
  echo "[run] managed preparation for $QWQ_LAUNCH_TARGET on $DEVICE_ID..."
  QWQ_MANAGED_LEASE_CLEANUP_REQUIRED=1
  export QWQ_MANAGED_LEASE_CLEANUP_REQUIRED
  trap managed_prelaunch_cleanup EXIT
  if ! MANAGED_PREPARE_JSON="$(
    PYTHONDONTWRITEBYTECODE=1 python3 \
      "$ROOT_DIR/quwoquan_ops/cli/stackctl.py" --output-format json \
      app-managed-prepare --target "$QWQ_LAUNCH_TARGET" --device "$DEVICE_ID" \
      --consumer-id "$QWQ_RUN_CONSUMER_ID"
  )"; then
    MANAGED_PREPARE_BLOCKER="$(
      python3 - "$MANAGED_PREPARE_JSON" <<'PY'
import json
import sys

try:
    payload = json.loads(sys.argv[1])
except ValueError:
    payload = {}
for item in payload.get("details") or []:
    print("[run] managed preparation detail: " + str(item).replace("\n", " "), file=sys.stderr)
print(str(payload.get("firstBlocker") or "APP.PREPARATION.receipt_invalid"))
PY
    )" || MANAGED_PREPARE_BLOCKER="APP.PREPARATION.receipt_invalid"
    echo "[run] GATE_BLOCK: $MANAGED_PREPARE_BLOCKER: managed preparation did not reach prepared." >&2
    exit 2
  fi
  QWQ_CONSUMER_LEASE_ACQUIRED=1
  export QWQ_CONSUMER_LEASE_ACQUIRED
  if ! MANAGED_PREPARE_EXPORTS="$(
    PYTHONDONTWRITEBYTECODE=1 python3 - \
      "$MANAGED_PREPARE_JSON" "$QWQ_LAUNCH_TARGET" "$QWQ_APP_RUNTIME_ENV" \
      "$DEVICE_ID" "$PREFLIGHT_PURPOSE" "$QWQ_RUN_CONSUMER_ID" <<'PY'
import hashlib
import json
import os
import pathlib
import re
import shlex
import sys

command_json, target, environment, device_id, preflight_purpose, consumer_id = sys.argv[1:7]
digest_pattern = re.compile(r"^sha256:[0-9a-f]{64}$")
port_pattern = re.compile(r"^[1-9][0-9]*(?:,[1-9][0-9]*)*$")


def require_nonempty_string(value, label):
    if not isinstance(value, str) or not value.strip():
        raise SystemExit(f"managed preparation {label} must be a non-empty string")
    return value


def require_digest(value, label, *, allow_empty=False):
    if allow_empty and value == "":
        return value
    if not isinstance(value, str) or digest_pattern.fullmatch(value) is None:
        raise SystemExit(f"managed preparation {label} must be a canonical sha256 identity")
    return value


def file_digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def exact_regular_file(raw_ref, label):
    if not isinstance(raw_ref, str) or not raw_ref:
        raise SystemExit(f"managed preparation {label} reference is empty")
    path = pathlib.Path(raw_ref)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise SystemExit(f"managed preparation {label} reference is unsafe")
    return path


try:
    command_payload = json.loads(command_json)
except ValueError:
    raise SystemExit("managed preparation command output is not JSON")
if not isinstance(command_payload, dict) or set(command_payload) != {
    "exitCode", "summary", "status", "firstBlocker", "receiptPath",
    "receiptDigest", "details", "warnings", "reportDir", "startedAt",
    "endedAt", "durationMs",
}:
    raise SystemExit("managed preparation command envelope field set drifted")
if (
    type(command_payload.get("exitCode")) is not int
    or command_payload["exitCode"] != 0
    or command_payload.get("status") != "prepared"
    or command_payload.get("firstBlocker") != ""
    or not isinstance(command_payload.get("details"), list)
    or not isinstance(command_payload.get("warnings"), list)
):
    raise SystemExit("managed preparation command envelope is not strictly prepared")
receipt_path = exact_regular_file(command_payload.get("receiptPath"), "receipt")
declared_digest = require_digest(command_payload.get("receiptDigest"), "receiptDigest")
receipt_bytes = receipt_path.read_bytes()
if "sha256:" + hashlib.sha256(receipt_bytes).hexdigest() != declared_digest:
    raise SystemExit("managed preparation receipt digest mismatch")
try:
    receipt = json.loads(receipt_bytes)
except (UnicodeError, ValueError):
    raise SystemExit("managed preparation receipt is not UTF-8 JSON")
expected_fields = {
    "schema", "target", "environment", "platform", "deviceId", "runtimeIdentity",
    "consumerId", "consumerLeaseId", "androidReversePorts", "androidReverseOwnedPorts",
    "deviceTrustReceiptRef", "deviceTrustReceiptDigest", "contentBinding",
    "strictPreflightReceiptRef", "strictPreflightReceiptDigest",
    "strictContentPreflightReceiptRef", "strictContentPreflightReceiptDigest",
    "createdAt", "status", "firstBlocker",
}
if not isinstance(receipt, dict) or set(receipt) != expected_fields:
    raise SystemExit("managed preparation receipt field set drifted")
for field, expected in (
    ("schema", "quwoquan_ops.app_managed_preparation.v1"),
    ("target", target),
    ("environment", environment),
    ("deviceId", device_id),
    ("consumerId", consumer_id),
    ("status", "prepared"),
    ("firstBlocker", ""),
):
    if receipt.get(field) != expected:
        raise SystemExit(f"managed preparation receipt {field} mismatch")
platform = receipt.get("platform")
if platform not in {"android", "ios"}:
    raise SystemExit("managed preparation receipt platform is outside the closed set")
runtime = receipt.get("runtimeIdentity")
runtime_fields = {
    "startupAttemptId", "composeProject", "composeDigest", "configurationDigest",
    "providerRuntimeDigest", "reused", "replaced",
}
if not isinstance(runtime, dict) or set(runtime) != runtime_fields:
    raise SystemExit("managed preparation runtimeIdentity field set drifted")
for field in ("startupAttemptId", "composeProject"):
    require_nonempty_string(runtime.get(field), f"runtimeIdentity.{field}")
for field in ("composeDigest", "configurationDigest", "providerRuntimeDigest"):
    require_digest(runtime.get(field), f"runtimeIdentity.{field}")
if any(type(runtime.get(field)) is not bool for field in ("reused", "replaced")):
    raise SystemExit("managed preparation runtimeIdentity booleans are invalid")
lease_id = require_digest(receipt.get("consumerLeaseId"), "consumerLeaseId")
reverse_ports = receipt.get("androidReversePorts")
owned_ports = receipt.get("androidReverseOwnedPorts")
if not isinstance(reverse_ports, str) or not isinstance(owned_ports, str):
    raise SystemExit("managed preparation Android reverse fields must be strings")
if platform == "android":
    if port_pattern.fullmatch(reverse_ports) is None:
        raise SystemExit("managed preparation Android transport ports are invalid")
    canonical_reverse = ",".join(
        str(value) for value in sorted({int(value) for value in reverse_ports.split(",")})
    )
    if reverse_ports != canonical_reverse:
        raise SystemExit("managed preparation Android transport ports are not canonical")
    if owned_ports and port_pattern.fullmatch(owned_ports) is None:
        raise SystemExit("managed preparation owned Android reverse ports are invalid")
    canonical_owned = ",".join(
        str(value) for value in sorted({int(value) for value in owned_ports.split(",")})
    ) if owned_ports else ""
    if owned_ports != canonical_owned:
        raise SystemExit("managed preparation owned Android reverse ports are not canonical")
    if owned_ports and not set(owned_ports.split(",")) <= set(reverse_ports.split(",")):
        raise SystemExit("managed preparation owned ports exceed transport ports")
elif reverse_ports or owned_ports:
    raise SystemExit("managed preparation iOS receipt carries Android reverse ports")
trust_ref_raw = receipt.get("deviceTrustReceiptRef")
trust_digest = receipt.get("deviceTrustReceiptDigest")
if not isinstance(trust_ref_raw, str) or not isinstance(trust_digest, str):
    raise SystemExit("managed preparation trust fields must be strings")
if bool(trust_ref_raw) != bool(trust_digest):
    raise SystemExit("managed preparation trust reference/digest pairing is invalid")
trust_platform = ""
if trust_ref_raw:
    trust_ref = exact_regular_file(trust_ref_raw, "device trust receipt")
    require_digest(trust_digest, "deviceTrustReceiptDigest")
    if file_digest(trust_ref) != trust_digest:
        raise SystemExit("managed preparation device trust digest mismatch")
    try:
        trust_receipt = json.loads(trust_ref.read_bytes())
    except (UnicodeError, ValueError):
        raise SystemExit("managed device trust receipt is not UTF-8 JSON")
    if (
        not isinstance(trust_receipt, dict)
        or trust_receipt.get("target") != target
        or trust_receipt.get("device") != device_id
        or trust_receipt.get("status") != "installed"
        or trust_receipt.get("systemTrustStore") is not True
        or lease_id not in {
            str(value) for value in trust_receipt.get("leases") or []
        }
    ):
        raise SystemExit("managed device trust receipt does not bind this lease")
    trust_platform = trust_receipt.get("platform")
    if trust_platform not in {"ios-simulator", "android-emulator"}:
        raise SystemExit("managed device trust receipt platform is invalid")
    if (platform == "ios") != (trust_platform == "ios-simulator"):
        raise SystemExit("managed device trust platform does not match preparation")
else:
    require_digest(trust_digest, "deviceTrustReceiptDigest", allow_empty=True)
binding = receipt.get("contentBinding")
binding_fields = {
    "releaseId", "verifyRunId", "manifestDigest", "readinessPhase",
    "readinessReceiptRef", "readinessReceiptDigest",
}
if not isinstance(binding, dict) or set(binding) != binding_fields:
    raise SystemExit("managed preparation content binding field set drifted")
for field in ("releaseId", "verifyRunId"):
    require_nonempty_string(binding.get(field), f"contentBinding.{field}")
require_digest(binding.get("manifestDigest"), "contentBinding.manifestDigest")
if binding.get("readinessPhase") != "research":
    raise SystemExit("managed preparation content binding is not research readiness")
readiness_ref = exact_regular_file(
    binding.get("readinessReceiptRef"), "content readiness receipt"
)
readiness_digest = require_digest(
    binding.get("readinessReceiptDigest"), "contentBinding.readinessReceiptDigest"
)
readiness_bytes = readiness_ref.read_bytes()
if "sha256:" + hashlib.sha256(readiness_bytes).hexdigest() != readiness_digest:
    raise SystemExit("managed preparation content readiness byte digest mismatch")
try:
    readiness_receipt = json.loads(readiness_bytes)
except (UnicodeError, ValueError):
    raise SystemExit("managed content readiness receipt is not UTF-8 JSON")
if (
    not isinstance(readiness_receipt, dict)
    or readiness_receipt.get("releaseId") != binding["releaseId"]
    or readiness_receipt.get("verifyRunId") != binding["verifyRunId"]
    or readiness_receipt.get("manifestDigest") != binding["manifestDigest"]
    or readiness_receipt.get("readinessPhase") != "research"
    or readiness_receipt.get("passed") is not True
):
    raise SystemExit("managed content readiness receipt identity drifted")


def normalized_readiness_ref(value, label):
    require_nonempty_string(value, label)
    path = pathlib.Path(value)
    if not path.is_absolute():
        path = pathlib.Path(os.environ["QWQ_OUTPUT_ROOT"]) / path
    return path.absolute()


created_at = require_nonempty_string(receipt.get("createdAt"), "createdAt")
try:
    import datetime as dt
    parsed_created_at = dt.datetime.fromisoformat(created_at.replace("Z", "+00:00"))
except ValueError:
    raise SystemExit("managed preparation createdAt is not RFC3339")
if parsed_created_at.tzinfo is None or parsed_created_at.utcoffset() != dt.timedelta(0):
    raise SystemExit("managed preparation createdAt is not UTC")
strict_debug_ref = exact_regular_file(
    receipt.get("strictPreflightReceiptRef"), "strict debug preflight receipt"
)
strict_debug_digest = require_digest(
    receipt.get("strictPreflightReceiptDigest"), "strictPreflightReceiptDigest"
)
strict_debug_bytes = strict_debug_ref.read_bytes()
if "sha256:" + hashlib.sha256(strict_debug_bytes).hexdigest() != strict_debug_digest:
    raise SystemExit("managed preparation strict debug preflight digest mismatch")
try:
    debug_envelope = json.loads(strict_debug_bytes)
except (UnicodeError, ValueError):
    raise SystemExit("managed strict debug preflight envelope is not UTF-8 JSON")
if not isinstance(debug_envelope, dict) or set(debug_envelope) != {
    "schema", "purpose", "target", "payload"
}:
    raise SystemExit("managed strict debug preflight envelope field set drifted")
if (
    debug_envelope.get("schema") != "quwoquan_ops.app_debug_preflight"
    or debug_envelope.get("purpose") != preflight_purpose
    or debug_envelope.get("target") != target
):
    raise SystemExit("managed strict debug preflight envelope does not match this launch")
debug_payload = debug_envelope.get("payload")
if not isinstance(debug_payload, dict):
    raise SystemExit("managed strict debug preflight envelope carries no payload")
debug_binding = debug_payload.get("contentBinding")
debug_binding = debug_binding if isinstance(debug_binding, dict) else {}
if (
    debug_payload.get("purpose") != preflight_purpose
    or debug_payload.get("target") != target
    or debug_payload.get("status") != "passed"
    or debug_payload.get("firstBlocker") not in (None, "")
    or debug_payload.get("nonPromotable") is not True
    or str(debug_payload.get("releaseId") or "") != binding["releaseId"]
    or str(debug_payload.get("manifestDigest") or "") != binding["manifestDigest"]
    or str(debug_payload.get("readinessReceiptDigest") or "")
    != readiness_digest
    or normalized_readiness_ref(
        debug_payload.get("readinessReceiptRef"),
        "strict debug preflight readinessReceiptRef",
    )
    != readiness_ref
    or str(debug_binding.get("releaseId") or "") != binding["releaseId"]
    or str(debug_binding.get("verifyRunId") or "") != binding["verifyRunId"]
    or str(debug_binding.get("manifestDigest") or "") != binding["manifestDigest"]
    or str(debug_binding.get("readinessPhase") or "") != "research"
    or normalized_readiness_ref(
        debug_binding.get("readinessReceiptRef"),
        "strict debug preflight contentBinding.readinessReceiptRef",
    )
    != readiness_ref
    or str(debug_binding.get("readinessReceiptDigest") or "")
    != readiness_digest
):
    raise SystemExit("managed strict debug preflight payload drifted from the receipt")

strict_content_ref = exact_regular_file(
    receipt.get("strictContentPreflightReceiptRef"),
    "strict content preflight receipt",
)
strict_content_digest = require_digest(
    receipt.get("strictContentPreflightReceiptDigest"),
    "strictContentPreflightReceiptDigest",
)
strict_content_bytes = strict_content_ref.read_bytes()
if "sha256:" + hashlib.sha256(strict_content_bytes).hexdigest() != strict_content_digest:
    raise SystemExit("managed preparation strict content preflight digest mismatch")
try:
    content_envelope = json.loads(strict_content_bytes)
except (UnicodeError, ValueError):
    raise SystemExit("managed strict content preflight envelope is not UTF-8 JSON")
content_envelope_fields = {
    "schema", "target", "status", "releaseId", "manifestDigest",
    "readinessReceiptRef", "readinessReceiptDigest", "releaseProbe", "payload",
}
if not isinstance(content_envelope, dict) or set(content_envelope) != content_envelope_fields:
    raise SystemExit("managed strict content preflight envelope field set drifted")
content_payload = content_envelope.get("payload")
content_payload = content_payload if isinstance(content_payload, dict) else {}
release_probe = content_envelope.get("releaseProbe")
release_probe = release_probe if isinstance(release_probe, dict) else {}
media_checks = release_probe.get("mediaChecks")
media_checks = media_checks if isinstance(media_checks, dict) else {}
if (
    content_envelope.get("schema")
    != "quwoquan_ops.app_content_preflight_exact.v1"
    or content_envelope.get("target") != target
    or content_envelope.get("status") != "passed"
    or content_envelope.get("releaseId") != binding["releaseId"]
    or content_envelope.get("manifestDigest") != binding["manifestDigest"]
    or content_envelope.get("readinessReceiptRef") != str(readiness_ref)
    or content_envelope.get("readinessReceiptDigest") != readiness_digest
    or content_payload.get("schema") != "quwoquan_ops.app_content_preflight"
    or content_payload.get("target") != target
    or content_payload.get("status") != "passed"
    or str(content_payload.get("releaseId") or "") != binding["releaseId"]
    or str(content_payload.get("manifestDigest") or "") != binding["manifestDigest"]
    or normalized_readiness_ref(
        content_payload.get("readinessReceiptRef"),
        "strict content preflight readinessReceiptRef",
    )
    != readiness_ref
    or str(content_payload.get("readinessReceiptDigest") or "")
    != readiness_digest
    or content_payload.get("releaseProbe") != release_probe
    or release_probe.get("exitCode") != 0
    or type(release_probe.get("executedSampleCount")) is not int
    or release_probe["executedSampleCount"] <= 0
    or media_checks.get("automatic") is not True
):
    raise SystemExit("managed strict content preflight payload drifted from the receipt")
print("export QWQ_MANAGED_PREPARATION_RECEIPT=" + shlex.quote(str(receipt_path)))
print("export QWQ_MANAGED_PREPARATION_DIGEST=" + shlex.quote(declared_digest))
print("export QWQ_APP_DEBUG_PREFLIGHT_RECEIPT=" + shlex.quote(str(strict_debug_ref)))
print("export QWQ_MANAGED_CONSUMER_ID=" + shlex.quote(consumer_id))
print("export QWQ_MANAGED_CONSUMER_LEASE_ID=" + shlex.quote(lease_id))
print("export QWQ_MANAGED_ANDROID_REVERSE_PORTS=" + shlex.quote(reverse_ports))
print("export QWQ_MANAGED_ANDROID_REVERSE_OWNED_PORTS=" + shlex.quote(owned_ports))
print("export QWQ_MANAGED_DEVICE_TRUST_PLATFORM=" + shlex.quote(trust_platform))
print("export QWQ_CONTENT_RELEASE_ID=" + shlex.quote(binding["releaseId"]))
print("export QWQ_CONTENT_VERIFY_RUN_ID=" + shlex.quote(binding["verifyRunId"]))
print("export QWQ_CONTENT_MANIFEST_DIGEST=" + shlex.quote(binding["manifestDigest"]))
print("export QWQ_CONTENT_READINESS_RECEIPT_DIGEST=" + shlex.quote(readiness_digest))
PY
  )"; then
    echo "[run] APP.PREPARATION.receipt_invalid: managed preparation receipt readback failed." >&2
    exit 2
  fi
  eval "$MANAGED_PREPARE_EXPORTS"
  QWQ_CONSUMER_LEASE_ID="$QWQ_MANAGED_CONSUMER_LEASE_ID"
  QWQ_ANDROID_REVERSE_OWNED_PORTS="$QWQ_MANAGED_ANDROID_REVERSE_OWNED_PORTS"
  if [[ -n "$QWQ_MANAGED_DEVICE_TRUST_PLATFORM" ]]; then
    QWQ_MANAGED_TRUST_CLEANUP_REQUIRED=1
  fi
  export QWQ_CONSUMER_LEASE_ID QWQ_ANDROID_REVERSE_OWNED_PORTS
  export QWQ_MANAGED_DEVICE_TRUST_PLATFORM QWQ_MANAGED_TRUST_CLEANUP_REQUIRED
  if ! MANAGED_LEASE_STATUS_JSON="$(
    PYTHONDONTWRITEBYTECODE=1 python3 \
      "$ROOT_DIR/quwoquan_ops/cli/stackctl.py" --output-format json \
      consumer-lease status --target "$QWQ_LAUNCH_TARGET"
  )" || ! python3 - "$MANAGED_LEASE_STATUS_JSON" \
      "$QWQ_LAUNCH_TARGET" "$DEVICE_ID" "$QWQ_RUN_CONSUMER_ID" \
      "$QWQ_CONSUMER_LEASE_ID" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
target, device, consumer, lease_id = sys.argv[2:6]
if not isinstance(payload, dict) or payload.get("exitCode") != 0:
    raise SystemExit("consumer lease status readback failed")
matching = [
    lease
    for lease in payload.get("occupyingLeases") or []
    if isinstance(lease, dict)
    and lease.get("target") == target
    and lease.get("device") == device
    and lease.get("consumer") == consumer
    and lease.get("leaseId") == lease_id
    and not lease.get("releasedAt")
]
if len(matching) != 1:
    raise SystemExit("managed preparation consumer lease is not uniquely active")
PY
  then
    echo "[run] APP.PREPARATION.receipt_invalid: managed consumer lease readback failed." >&2
    exit 2
  fi
  QWQ_MANAGED_PREPARATION_ACTIVE=1
  export QWQ_MANAGED_PREPARATION_ACTIVE
  echo "[run] managed preparation receipt verified: $QWQ_MANAGED_PREPARATION_DIGEST"
fi

# 整个 attempt 只允许一个 preflight owner。上游编排方（dev-session）已执行时会
# 交出 exact receipt；launcher 只复用或显式阻断，绝不重复执行第二次 preflight。
APP_CONTENT_PREFLIGHT_JSON=""
if [[ -n "${QWQ_APP_DEBUG_PREFLIGHT_RECEIPT:-}" ]]; then
  if ! APP_CONTENT_PREFLIGHT_JSON="$(
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}" \
      python3 -c 'import sys
from quwoquan_ops.cli.lib.app_debug_preflight_handoff import (
    read_reusable_app_debug_preflight,
)

try:
    sys.stdout.write(
        read_reusable_app_debug_preflight(
            sys.argv[1], purpose=sys.argv[2], target=sys.argv[3]
        )
    )
except ValueError as error:
    sys.stdout.write(str(error))
    raise SystemExit(2) from None' \
      "$QWQ_APP_DEBUG_PREFLIGHT_RECEIPT" "$PREFLIGHT_PURPOSE" "$QWQ_LAUNCH_TARGET"
  )"; then
    echo "[run] GATE_BLOCK: $APP_CONTENT_PREFLIGHT_JSON" >&2
    exit 2
  fi
  echo "[run] reusing upstream $PREFLIGHT_PURPOSE preflight for $QWQ_LAUNCH_TARGET"
fi

if [[ -z "$APP_CONTENT_PREFLIGHT_JSON" ]]; then
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
fi

APP_CONTENT_EXPORTS="$(
  python3 - "$APP_CONTENT_PREFLIGHT_JSON" "$RUN_MODE" "$QWQ_LAUNCH_TARGET" \
    "$PREFLIGHT_PURPOSE" <<'PY'
import json
import shlex
import sys

payload = json.loads(sys.argv[1])
run_mode = sys.argv[2]
target = sys.argv[3]
purpose = sys.argv[4]
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

first_blocker = str(payload.get("firstBlocker") or "").strip()
if (
    payload.get("status") not in {"passed", "warning"}
    or payload.get("nonPromotable") is not True
    or first_blocker
):
    print(json.dumps({
        "contentLive": payload.get("contentLive", "not_evaluated"),
        "reason": first_blocker or "test_live preflight contract is invalid",
        "recoveryCommand": str(payload.get("recoveryCommand") or recovery_command),
    }, ensure_ascii=False), file=sys.stderr)
    raise SystemExit(2)

# content-live 在 test_live 下只把已存在的绑定身份传给后续观测；身份缺失是
# warning，不再在真实 compile/install/activation 前退出。
if run_mode == "content-live":
    content_binding = payload.get("contentBinding") or {}
    optional_identity = {
        "QWQ_CONTENT_RELEASE_ID": str(payload.get("releaseId") or "").strip(),
        "QWQ_CONTENT_VERIFY_RUN_ID": str(content_binding.get("verifyRunId") or "").strip(),
        "QWQ_CONTENT_MANIFEST_DIGEST": str(payload.get("manifestDigest") or "").strip(),
        "QWQ_CONTENT_READINESS_RECEIPT_DIGEST": str(
            payload.get("readinessReceiptDigest") or ""
        ).strip(),
    }
    for key, value in optional_identity.items():
        if value:
            print(f"export {key}={shlex.quote(value)}")
PY
)" || {
  echo "[run] GATE_BLOCK: selected launch mode preflight did not pass." >&2
  exit 2
}
eval "$APP_CONTENT_EXPORTS"
PREFLIGHT_WARNING_TEXT="$(
  python3 - "$APP_CONTENT_PREFLIGHT_JSON" <<'PY'
import json
import sys

for item in json.loads(sys.argv[1]).get("warnings") or []:
    print(str(item).replace("\n", " "))
PY
)"
while IFS= read -r preflight_warning; do
  [[ -n "$preflight_warning" ]] || continue
  record_prelaunch_warning "$preflight_warning"
done <<< "$PREFLIGHT_WARNING_TEXT"

APP_CONTENT_DELIVERY_JSON='{}'
if [[ "$RUN_MODE" == "content-live" ]]; then
  if [[ -n "${QWQ_CONTENT_RELEASE_ID:-}" \
     && -n "${QWQ_CONTENT_VERIFY_RUN_ID:-}" \
     && -n "${QWQ_CONTENT_MANIFEST_DIGEST:-}" ]]; then
    if ! APP_CONTENT_DELIVERY_JSON="$(
    PYTHONDONTWRITEBYTECODE=1 python3 \
      "$ROOT_DIR/quwoquan_ops/cli/stackctl.py" --output-format json \
      verify --env "$QWQ_APP_RUNTIME_ENV" --target "$QWQ_LAUNCH_TARGET" \
      --kind content-delivery --profile integration \
      --data-release-id "$QWQ_CONTENT_RELEASE_ID" \
      --data-verify-run-id "$QWQ_CONTENT_VERIFY_RUN_ID" \
      --data-manifest-digest "$QWQ_CONTENT_MANIFEST_DIGEST"
    )"; then
      CONTENT_DELIVERY_WARNING="$(python3 - \
        "$APP_CONTENT_DELIVERY_JSON" "$QWQ_CONTENT_RELEASE_ID" \
        "$QWQ_APP_RUNTIME_ENV" <<'PY'
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
    "contentLive": "warning",
    "reason": first_blocker,
    "recoveryCommand": recovery_command,
}, ensure_ascii=False))
PY
      )"
      record_prelaunch_warning "$CONTENT_DELIVERY_WARNING"
    fi
  else
    record_prelaunch_warning \
      "content delivery verification skipped because release binding identity is incomplete."
  fi
fi

if [[ -z "$DEVICE_ID" && -t 0 && -t 2 ]]; then
  # 无 -d 且处于交互 TTY：委托 canonical device authority（dev_up.pick_device）
  # 显示编号列表并接受一次选择。程序经 -c 传入而非 heredoc，
  # 保证 stdin 仍绑定当前 TTY 供选择读取。
  if ! DEVICE_ID="$(
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}" \
      python3 -c '
import pathlib
import sys

from quwoquan_ops.cli.lib.dev_up import discover_flutter_devices, pick_device

try:
    devices = discover_flutter_devices(
        pathlib.Path(sys.argv[1]),
        include_mobile=True,
        include_web=False,
        include_desktop=False,
    )
    print(pick_device(devices, label="[run]"))
except RuntimeError as error:
    print(str(error), file=sys.stderr)
    raise SystemExit(2)
' "$APP_DIR"
  )"; then
    echo "[run] GATE_BLOCK: interactive device selection failed; pass -d/--device-id." >&2
    exit 2
  fi
  export QWQ_RUN_DEVICE_ID="$DEVICE_ID"
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

DEPENDENCY_CAPSULE_MANIFEST="${QWQ_WORKSPACE_SOURCE_CAPSULE_MANIFEST:-${QWQ_PACKAGE_SOURCE_CAPSULE_MANIFEST:-}}"
if [[ -n "$TEST_LIVE_REPORT_OVERRIDE" ]]; then
  DEPENDENCY_CAPSULE_MANIFEST="$QWQ_CANONICAL_SOURCE_CAPSULE_MANIFEST_REF"
fi
if [[ -z "$DEPENDENCY_CAPSULE_MANIFEST" \
   || -L "$DEPENDENCY_CAPSULE_MANIFEST" \
   || ! -f "$DEPENDENCY_CAPSULE_MANIFEST" ]]; then
  echo "[run] APP.DEPENDENCY.bundle_missing: a verified source capsule is required." >&2
  exit 2
fi

# Readiness and device validation intentionally precede SDK/dependency work.
# Once a launch is eligible, re-resolve the pinned real SDK even when the
# caller supplied QWQ_REAL_FLUTTER so IDE/facade state cannot select another
# executable or version.
if ! FLUTTER_IDENTITY_JSON="$(
  python3 "$APP_DIR/scripts/tools/flutter_facade/resolve_real_flutter.py" --format json
)"; then
  echo "[run] GATE_BLOCK: unable to resolve the pinned Flutter SDK identity." >&2
  exit 2
fi
FLUTTER_IDENTITY_EXPORTS="$(
  python3 - "$FLUTTER_IDENTITY_JSON" <<'PY'
import json
import shlex
import sys

identity = json.loads(sys.argv[1])
for field in ("executable", "flutterVersion", "commandResolutionDigest"):
    if not str(identity.get(field) or "").strip():
        raise SystemExit(f"Flutter command identity is missing {field}")
print("QWQ_REAL_FLUTTER=" + shlex.quote(identity["executable"]))
print("QWQ_FLUTTER_VERSION=" + shlex.quote(identity["flutterVersion"]))
print("QWQ_COMMAND_RESOLUTION_DIGEST=" + shlex.quote(
    identity["commandResolutionDigest"]
))
PY
)" || {
  echo "[run] GATE_BLOCK: invalid Flutter command identity." >&2
  exit 2
}
eval "$FLUTTER_IDENTITY_EXPORTS"
export QWQ_REAL_FLUTTER QWQ_FLUTTER_VERSION QWQ_COMMAND_RESOLUTION_DIGEST

ANDROID_LOCAL_GATEWAY_BASE_URL=""
ANDROID_LOCAL_LEGAL_BASE_URL=""
ANDROID_LOCAL_MEDIA_AVATAR_BASE_URL=""
ANDROID_LOCAL_MEDIA_IMAGE_BASE_URL=""
ANDROID_LOCAL_MEDIA_VIDEO_BASE_URL=""
ANDROID_LOCAL_MEDIA_UPLOAD_BASE_URL=""
QWQ_ANDROID_LOCAL_PORTS=""
QWQ_ANDROID_TRANSPORT_WARNING=""

release_consumer_lease() {
  cleanup_managed_handoff_resources
}

cleanup_run() {
  local original_exit_code="${1:-0}"
  trap - EXIT
  set +e
  release_consumer_lease
  if [[ -n "${QWQ_APP_INSTANCE_STATE_FILE:-}" ]]; then
    if ! rm -f -- "$QWQ_APP_INSTANCE_STATE_FILE"; then
      record_teardown_warning "failed to remove App instance state."
    fi
  fi
  if [[ -n "$RUNTIME_CONFIG_MATERIAL_ROOT" ]]; then
    if ! rm -rf -- "$RUNTIME_CONFIG_MATERIAL_ROOT"; then
      record_teardown_warning "failed to remove runtime configuration material."
    fi
  fi
  if [[ -n "$TEARDOWN_RECEIPT" ]]; then
    if ! python3 - \
      "$TEARDOWN_RECEIPT" "$LAUNCH_RECEIPT" "$original_exit_code" \
      "${TEARDOWN_WARNINGS[@]:-}" <<'PY'
import datetime as dt
import json
import os
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
launch_attempt_ref = sys.argv[2]
exit_code = int(sys.argv[3])
warnings = list(dict.fromkeys(item for item in sys.argv[4:] if item))
payload = {
    "schema": "quwoquan_app.launch_teardown.v1",
    "launchAttemptRef": launch_attempt_ref,
    "exitCode": exit_code,
    "status": "warning" if warnings else "passed",
    "warnings": warnings,
    "completedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
}
path.parent.mkdir(parents=True, exist_ok=True)
temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
descriptor = os.open(
    temporary,
    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
    0o600,
)
try:
    encoded = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    view = memoryview(encoded)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError("launch teardown receipt write made no progress")
        view = view[written:]
    os.fsync(descriptor)
finally:
    os.close(descriptor)
os.replace(temporary, path)
PY
    then
      echo "[run] WARN: failed to write launch teardown receipt." >&2
    fi
  fi
}

trap 'run_exit_code=$?; cleanup_run "$run_exit_code"; exit "$run_exit_code"' EXIT

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
managed_active = os.environ.get("QWQ_MANAGED_PREPARATION_ACTIVE") == "1"
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
        if managed_active:
            ports = [
                int(value)
                for value in os.environ.get(
                    "QWQ_MANAGED_ANDROID_REVERSE_PORTS", ""
                ).split(",")
                if value
            ]
            if not ports or any(port not in preexisting_ports for port in ports):
                raise RuntimeError(
                    "managed preparation reverse transport is no longer active"
                )
            owned_port_list = os.environ.get(
                "QWQ_MANAGED_ANDROID_REVERSE_OWNED_PORTS", ""
            )
        else:
            ports = enable_android_adb_reverse(device_id, target, topology=topology)
            owned_port_list = ",".join(
                str(port) for port in ports if int(port) not in preexisting_ports
            )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        if managed_active:
            print(
                f"APP.PREPARATION.receipt_invalid: managed Android transport drifted: {exc}",
                file=sys.stderr,
            )
            raise SystemExit(2)
        warning = (
            "Android transport preparation is unavailable; "
            f"test_live continues with typed network recovery: {exc}"
        )
        print("export QWQ_ANDROID_TRANSPORT_WARNING=" + shlex.quote(warning))
        print("export QWQ_ANDROID_TRANSPORT_READY=0")
        raise SystemExit(0)
    port_list = ",".join(str(port) for port in ports)
    print("export QWQ_ANDROID_LOCAL_PORTS=" + shlex.quote(port_list))
    print("export QWQ_ANDROID_REVERSE_EXPECTED_PORTS=" + shlex.quote(port_list))
    print("export QWQ_ANDROID_REVERSE_ACTUAL_PORTS=" + shlex.quote(port_list))
    print("export QWQ_ANDROID_REVERSE_OWNED_PORTS=" + shlex.quote(owned_port_list))
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
  if [[ -n "$QWQ_ANDROID_TRANSPORT_WARNING" ]]; then
    record_prelaunch_warning "$QWQ_ANDROID_TRANSPORT_WARNING"
  fi
fi

EXPECTED_PRIVATE_PUB_CACHE="$APP_DIR/.dart_tool/qwq_pub_cache"
if [[ "${QWQ_RUN_DEVICE_KIND:-}" == android* ]]; then
  DEPENDENCY_PRIVATE_STATE_ROOT="$APP_DIR/.dart_tool/qwq_android_dependency_state"
else
  DEPENDENCY_PRIVATE_STATE_ROOT="$APP_DIR/.dart_tool/qwq_ios_cocoapods_dependency"
fi
DEPENDENCY_RETRY=0
if [[ -z "$QWQ_CANONICAL_EXPECTED_BUILD_PROJECTION_DIGEST" ]]; then
  echo "[run] projecting the atomic App dependency bundle and replaying it offline..."
  DEPENDENCY_PATROL_ARGUMENT=""
  if [[ "${QWQ_CANONICAL_LAUNCH_ACTOR:-}" == "app-content-uat" ]]; then
    DEPENDENCY_PATROL_ARGUMENT="--include-patrol"
  fi
  if ! DEPENDENCY_EXPORTS="$(
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}" \
      python3 "$APP_DIR/scripts/device/prepare_flutter_dependencies.py" \
      --source-capsule-manifest "$DEPENDENCY_CAPSULE_MANIFEST" \
      --projection-root "$ROOT_DIR" \
      --private-state-root "$DEPENDENCY_PRIVATE_STATE_ROOT" \
      --device "$DEVICE_ID" \
      --flutter "$QWQ_REAL_FLUTTER" \
      --pod "${QWQ_COCOAPODS_EXECUTABLE:-}" \
      ${DEPENDENCY_PATROL_ARGUMENT:+"$DEPENDENCY_PATROL_ARGUMENT"}
  )"; then
    echo "[run] APP.DEPENDENCY.projection_failed: exact offline dependency replay failed." >&2
    exit 2
  fi
  eval "$DEPENDENCY_EXPORTS"
else
  DEPENDENCY_RETRY=1
  # iOS retry reuses attempt-1's fully sealed projection. Reconstruct only the
  # deterministic private environment; the expected build digest below proves
  # every dependency and build byte before any retry command can read it.
  export PUB_CACHE="$EXPECTED_PRIVATE_PUB_CACHE"
  if [[ "${QWQ_RUN_DEVICE_KIND:-}" == android* ]]; then
    unset ALL_PROXY all_proxy HTTP_PROXY http_proxy HTTPS_PROXY https_proxy NO_PROXY no_proxy
    export GRADLE_USER_HOME="$APP_DIR/.dart_tool/qwq_android_gradle_dependency/home"
    export HOME="$DEPENDENCY_PRIVATE_STATE_ROOT/flutter/production/home"
    export XDG_CONFIG_HOME="$DEPENDENCY_PRIVATE_STATE_ROOT/flutter/production/xdg-config"
    export XDG_CACHE_HOME="$DEPENDENCY_PRIVATE_STATE_ROOT/flutter/production/xdg-cache"
    export FLUTTER_SWIFT_PACKAGE_MANAGER=false
    export GIT_CONFIG_GLOBAL=/dev/null
    export GIT_CONFIG_NOSYSTEM=1
    export GIT_TERMINAL_PROMPT=0
  elif [[ "${QWQ_RUN_DEVICE_KIND:-}" == ios-* ]]; then
    unset ALL_PROXY all_proxy HTTP_PROXY http_proxy HTTPS_PROXY https_proxy NO_PROXY no_proxy
    export FLUTTER_SWIFT_PACKAGE_MANAGER=false
    export CP_HOME_DIR="$DEPENDENCY_PRIVATE_STATE_ROOT/production/home"
    export CP_CACHE_DIR="$DEPENDENCY_PRIVATE_STATE_ROOT/production/cache"
    export COCOAPODS_HOME="$CP_HOME_DIR"
    export HOME="$DEPENDENCY_PRIVATE_STATE_ROOT/production/user-home"
    export XDG_CONFIG_HOME="$HOME/.config"
    export XDG_CACHE_HOME="$HOME/.cache"
    export COCOAPODS_DISABLE_STATS=true
    export COCOAPODS_SKIP_UPDATE_MESSAGE=true
    export GIT_CONFIG_GLOBAL=/dev/null
    export GIT_CONFIG_NOSYSTEM=1
    export GIT_TERMINAL_PROMPT=0
  fi
  QWQ_DEPENDENCY_PROJECTION_EXPECTATION_REF="$DEPENDENCY_PRIVATE_STATE_ROOT/dependency-projection-expectation.json"
  if ! QWQ_DEPENDENCY_PROJECTION_EXPECTATION_DIGEST="$(
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}" \
      python3 - \
      "$ROOT_DIR" \
      "$QWQ_DEPENDENCY_PROJECTION_EXPECTATION_REF" <<'PY'
import hashlib
import pathlib
import sys

from quwoquan_ops.cli.lib.package_reuse.dependency_bundle_projection_verify import (
    load_dependency_projection_cas_evidence,
)

projection_root = pathlib.Path(sys.argv[1])
evidence_path = pathlib.Path(sys.argv[2])
try:
    encoded = evidence_path.read_bytes()
except OSError as error:
    raise SystemExit(
        f"APP.DEPENDENCY.projection_expectation_invalid: {error}"
    ) from None
digest = "sha256:" + hashlib.sha256(encoded).hexdigest()
load_dependency_projection_cas_evidence(
    projection_root=projection_root,
    evidence_path=evidence_path,
    expected_digest=digest,
)
print(digest)
PY
  )"; then
    echo "[run] APP.DEPENDENCY.projection_expectation_invalid: retry dependency expectation cannot be reloaded." >&2
    exit 2
  fi
  export QWQ_DEPENDENCY_PROJECTION_EXPECTATION_REF
  export QWQ_DEPENDENCY_PROJECTION_EXPECTATION_DIGEST
fi
if [[ "${QWQ_RUN_DEVICE_KIND:-}" == ios-* ]]; then
  # Both initial launches and retries must consume the exact attempt identity.
  # This verifier only checks and projects the sealed identity; it never resolves
  # ambient PATH as a replacement for a missing retry handoff.
  verify_cocoapods_launch_identity || exit 2
fi
if [[ "$PUB_CACHE" != "$EXPECTED_PRIVATE_PUB_CACHE" \
   || -L "$PUB_CACHE" || ! -d "$PUB_CACHE" ]]; then
  echo "[run] APP.LAUNCH.receipt_invalid: private projection PUB_CACHE identity drifted." >&2
  exit 2
fi
if [[ "${FLUTTER_SWIFT_PACKAGE_MANAGER:-}" != "false" \
   || -z "${HOME:-}" || -L "$HOME" || ! -d "$HOME" \
   || -z "${XDG_CONFIG_HOME:-}" || -L "$XDG_CONFIG_HOME" || ! -d "$XDG_CONFIG_HOME" \
   || -z "${XDG_CACHE_HOME:-}" || -L "$XDG_CACHE_HOME" || ! -d "$XDG_CACHE_HOME" \
   || "${GIT_CONFIG_GLOBAL:-}" != "/dev/null" \
   || "${GIT_CONFIG_NOSYSTEM:-}" != "1" \
   || "${GIT_TERMINAL_PROMPT:-}" != "0" ]]; then
  echo "[run] APP.LAUNCH.receipt_invalid: private Flutter configuration environment drifted." >&2
  exit 2
fi
if [[ ! "$QWQ_DEPENDENCY_PROJECTION_EXPECTATION_REF" = /* \
   || ! -f "$QWQ_DEPENDENCY_PROJECTION_EXPECTATION_REF" \
   || ! "$QWQ_DEPENDENCY_PROJECTION_EXPECTATION_DIGEST" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  echo "[run] APP.DEPENDENCY.projection_expectation_invalid: dependency expectation identity is incomplete." >&2
  exit 2
fi
if [[ "$DEPENDENCY_RETRY" == "0" \
   && ( ! "$QWQ_DEPENDENCY_PROJECTION_PREBUILD_READBACK_REF" = /* \
     || ! -f "$QWQ_DEPENDENCY_PROJECTION_PREBUILD_READBACK_REF" \
     || ! "$QWQ_DEPENDENCY_PROJECTION_PREBUILD_READBACK_DIGEST" =~ ^sha256:[0-9a-f]{64}$ ) ]]; then
  echo "[run] APP.DEPENDENCY.projection_expectation_invalid: initial pre-build dependency readback is incomplete." >&2
  exit 2
fi
seal_app_content_projection_build predependency

# Dependency materialization is single-owned above. The UAT projection is
# inventoried only after pub/pod have finished and before Flutter may compile.
seal_app_content_projection_build prebuild
if [[ "$DEPENDENCY_RETRY" == "1" ]]; then
  # Verify the exact attempt-1 tree first. Only then may this retry add its own
  # fresh, new-process dependency readback immediately before Flutter executes.
  verify_dependency_projection_after_command prebuild || exit 2
fi

RUNTIME_STACKCTL_PYTHON="$(
  bash "$APP_DIR/scripts/ios/build_resolve_stackctl_python.sh"
)" || {
  echo "[run] GATE_BLOCK: a compatible Python is required for native activation." >&2
  exit 2
}

if [[ "${QWQ_RUN_DEVICE_KIND:-}" == android* ]]; then
  export ANDROID_SERIAL="$DEVICE_ID"
  if [[ -z "$QWQ_ANDROID_LOCAL_PORTS" ]]; then
    record_prelaunch_warning \
      "Android reverse ports are unavailable; test_live continues to a typed runtime outcome."
  fi
fi

QWQ_DEBUG_APP_ID_PLATFORM="android"
if [[ "${QWQ_RUN_DEVICE_KIND:-}" == ios-* ]]; then
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

if [[ "${QWQ_RUN_DEVICE_KIND:-}" == ios-* \
   || ("${QWQ_RUN_DEVICE_KIND:-}" == android* \
      && -n "$QWQ_ANDROID_LOCAL_PORTS") ]]; then
  if [[ "${QWQ_MANAGED_PREPARATION_ACTIVE:-0}" == "1" ]]; then
    if [[ "$QWQ_CONSUMER_LEASE_ACQUIRED" != "1" \
       || "$QWQ_CONSUMER_LEASE_ID" != "$QWQ_MANAGED_CONSUMER_LEASE_ID" \
       || "$QWQ_RUN_CONSUMER_ID" != "$QWQ_MANAGED_CONSUMER_ID" ]]; then
      echo "[run] APP.PREPARATION.receipt_invalid: managed consumer lease handoff drifted." >&2
      exit 2
    fi
    echo "[run] reusing managed preparation consumer lease: $QWQ_CONSUMER_LEASE_ID"
  else
    LEASE_COMMAND=(
      "$RUNTIME_STACKCTL_PYTHON" "$ROOT_DIR/quwoquan_ops/cli/stackctl.py"
      --output-format json consumer-lease acquire
      --target "$QWQ_LAUNCH_TARGET"
      --device "$DEVICE_ID"
      --consumer "$QWQ_RUN_CONSUMER_ID"
    )
    case "${QWQ_RUN_DEVICE_KIND:-}" in
      ios-simulator)
        LEASE_COMMAND+=(
          --platform ios-simulator
          --bundle-id "$QWQ_DEBUG_APP_ID"
          --ports ""
        )
        ;;
      ios-physical)
        LEASE_COMMAND+=(
          --platform ios-physical
          --bundle-id "$QWQ_DEBUG_APP_ID"
          --ports ""
        )
        ;;
      android*)
        LEASE_COMMAND+=(
          --platform android
          --package-name "$QWQ_DEBUG_APP_ID"
          --ports "$QWQ_ANDROID_LOCAL_PORTS"
        )
        ;;
    esac
    if LEASE_JSON="$(PYTHONDONTWRITEBYTECODE=1 "${LEASE_COMMAND[@]}")"; then
      QWQ_CONSUMER_LEASE_ID="$(
        python3 - "$LEASE_JSON" <<'PYLEASE'
import json
import re
import sys

lease_id = str((json.loads(sys.argv[1]).get("lease") or {}).get("leaseId") or "")
if re.fullmatch(r"sha256:[0-9a-f]{64}", lease_id) is None:
    raise SystemExit("consumer lease response is missing canonical leaseId")
print(lease_id)
PYLEASE
      )"
      export QWQ_CONSUMER_LEASE_ID
      QWQ_CONSUMER_LEASE_ACQUIRED=1
      QWQ_MANAGED_LEASE_CLEANUP_REQUIRED=1
    else
      record_prelaunch_warning \
        "runtime consumer lease is unavailable; test_live remains nonPromotable."
    fi
  fi
fi

# device trust 回执必须绑定真实 consumer lease（漂移修正：不再使用
# canonical-launcher 拼接出来的 fabricated lease 身份）。managed 入口的 trust
# 已由 app-managed-prepare 以其准备期 lease 安装并验证，这里直接复用。
if [[ "${QWQ_MANAGED_PREPARATION_ACTIVE:-0}" == "1" ]]; then
  echo "[run] reusing managed preparation device trust for $DEVICE_ID"
elif [[ "${QWQ_RUN_DEVICE_KIND:-}" == "ios-simulator" \
   || "${QWQ_RUN_DEVICE_KIND:-}" == android* ]]; then
  if [[ "$QWQ_CONSUMER_LEASE_ACQUIRED" == "1" ]]; then
    DEVICE_TRUST_PLATFORM="$QWQ_RUN_DEVICE_KIND"
    if [[ "$DEVICE_TRUST_PLATFORM" == "android_emulator" ]]; then
      DEVICE_TRUST_PLATFORM="android-emulator"
    fi
    DEVICE_TRUST_COMMAND=(
      "$RUNTIME_STACKCTL_PYTHON" "$ROOT_DIR/quwoquan_ops/cli/stackctl.py"
      --output-format json device-trust --target "$QWQ_LAUNCH_TARGET"
      --platform "$DEVICE_TRUST_PLATFORM" --action install --device "$DEVICE_ID"
      --lease-id "$QWQ_CONSUMER_LEASE_ID"
    )
    if [[ "${QWQ_RUN_DEVICE_KIND:-}" == "ios-simulator" ]]; then
      DEVICE_TRUST_COMMAND+=(--defer-endpoint-probe)
    elif [[ "${QWQ_RUN_DEVICE_KIND:-}" == android* ]]; then
      DEVICE_TRUST_COMMAND+=(--allow-unprovisioned-system-trust)
    fi
    if PYTHONDONTWRITEBYTECODE=1 "${DEVICE_TRUST_COMMAND[@]}" >/dev/null; then
      QWQ_MANAGED_DEVICE_TRUST_PLATFORM="$DEVICE_TRUST_PLATFORM"
      QWQ_MANAGED_TRUST_CLEANUP_REQUIRED=1
      export QWQ_MANAGED_DEVICE_TRUST_PLATFORM QWQ_MANAGED_TRUST_CLEANUP_REQUIRED
    else
      record_prelaunch_warning \
        "target-bound transport trust is unavailable; test_live continues to a typed runtime outcome."
    fi
  else
    record_prelaunch_warning \
      "target-bound transport trust is unavailable; test_live continues to a typed runtime outcome."
  fi
fi

RUNTIME_CONFIG_MATERIAL_ROOT="$(
  mktemp -d "${TMPDIR:-/tmp}/qwq-app-runtime-config.XXXXXX"
)" || {
  echo "[run] GATE_BLOCK: failed to create private runtime configuration material directory." >&2
  exit 2
}
chmod 0700 "$RUNTIME_CONFIG_MATERIAL_ROOT"
mkdir "$RUNTIME_CONFIG_MATERIAL_ROOT/qwq_runtime"
chmod 0700 "$RUNTIME_CONFIG_MATERIAL_ROOT/qwq_runtime"
RUNTIME_CONFIG_TRUST_PATH="$RUNTIME_CONFIG_MATERIAL_ROOT/qwq_runtime/runtime-config-trust.json"
export QWQ_APP_RUNTIME_CONFIG_TRUST_PATH="$RUNTIME_CONFIG_TRUST_PATH"
export QWQ_ANDROID_RUNTIME_CONFIG_ASSET_ROOT="$RUNTIME_CONFIG_MATERIAL_ROOT"
export QWQ_IOS_RUNTIME_CONFIG_TRUST_PATH="$RUNTIME_CONFIG_TRUST_PATH"

HANDOFF_CMD=(
  python3 "$APP_DIR/scripts/device/build_launcher_handoff.py"
  --env "$QWQ_APP_RUNTIME_ENV"
  --target "$QWQ_LAUNCH_TARGET"
  --launch-provenance "$LAUNCH_PROVENANCE"
  --launch-policy test_live
  --runtime-config-trust-output "$RUNTIME_CONFIG_TRUST_PATH"
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

if ! HANDOFF_JSON="$("${HANDOFF_CMD[@]}")"; then
  if [[ -n "$HANDOFF_JSON" ]]; then
    echo "$HANDOFF_JSON" >&2
  else
    echo "[run] GATE_BLOCK: launcher handoff generation failed without diagnostics." >&2
  fi
  exit 2
fi
HANDOFF_EXPORTS="$(
  python3 - "$HANDOFF_JSON" <<'PY'
import json
import shlex
import sys

handoff = json.loads(sys.argv[1])
print("ENTRYPOINT=" + shlex.quote(handoff["entrypoint"]))
print("LAUNCH_PROVENANCE=" + shlex.quote(handoff["launchProvenance"]))
print("RUNTIME_CONFIG_SUPPLY_MODE=" + shlex.quote(
    handoff["runtimeConfigSupplyMode"]
))
print("RUNTIME_CONFIG_PACKAGE_DIGEST=" + shlex.quote(
    handoff["runtimeConfigPackageDigest"]
))
print("RUNTIME_CONFIG_TRUST_ENVELOPE_DIGEST=" + shlex.quote(
    handoff["runtimeConfigTrustEnvelopeDigest"]
))
print("EFFECTIVE_LAUNCH_MANIFEST_DIGEST=" + shlex.quote(
    handoff["effectiveLaunchManifestDigest"]
))
PY
)" || {
  echo "[run] GATE_BLOCK: failed to parse launcher handoff." >&2
  exit 2
}
eval "$HANDOFF_EXPORTS"
export QWQ_APP_LAUNCH_PROVENANCE="$LAUNCH_PROVENANCE"
export QWQ_RUNTIME_CONFIG_SUPPLY_MODE="$RUNTIME_CONFIG_SUPPLY_MODE"
export QWQ_LAUNCH_HANDOFF_JSON="$HANDOFF_JSON"
export QWQ_RUNTIME_CONFIG_PACKAGE_DIGEST="$RUNTIME_CONFIG_PACKAGE_DIGEST"
export QWQ_RUNTIME_CONFIG_TRUST_ENVELOPE_DIGEST="$RUNTIME_CONFIG_TRUST_ENVELOPE_DIGEST"
export QWQ_EFFECTIVE_LAUNCH_MANIFEST_DIGEST="$EFFECTIVE_LAUNCH_MANIFEST_DIGEST"
if [[ "$QWQ_CONSUMER_LEASE_ACQUIRED" == "1" ]]; then
  LEASE_BIND_COMMAND=(
    "$RUNTIME_STACKCTL_PYTHON" "$ROOT_DIR/quwoquan_ops/cli/stackctl.py"
    --output-format json consumer-lease bind
    --target "$QWQ_LAUNCH_TARGET"
    --device "$DEVICE_ID"
    --consumer "$QWQ_RUN_CONSUMER_ID"
    --lease-id "$QWQ_CONSUMER_LEASE_ID"
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
    if [[ "${QWQ_MANAGED_PREPARATION_ACTIVE:-0}" == "1" ]]; then
      echo "[run] APP.PREPARATION.receipt_invalid: managed consumer lease final bind failed." >&2
      exit 2
    fi
    record_prelaunch_warning \
      "failed to bind the runtime consumer lease to the final handoff digest."
  fi
fi

set +e
if [[ -z "$LAUNCH_RECEIPT" ]]; then
  LAUNCH_RECEIPT="$QWQ_OUTPUT_ROOT/env/repo/runs/$(date -u +%Y%m%dT%H%M%SZ)-$$-${QWQ_LAUNCH_TARGET}-app-launch/attempt.json"
fi
if [[ -z "$STARTUP_TERMINAL_RECEIPT" ]]; then
  STARTUP_TERMINAL_RECEIPT="$(dirname "$LAUNCH_RECEIPT")/startup-terminal.json"
fi
if ! python3 - \
  "$QWQ_OUTPUT_ROOT" "$LAUNCH_RECEIPT" "$STARTUP_TERMINAL_RECEIPT" <<'PY'
import pathlib
import sys

output_root = pathlib.Path(sys.argv[1]).expanduser().absolute()
attempt_path = pathlib.Path(sys.argv[2]).expanduser()
terminal_path = pathlib.Path(sys.argv[3]).expanduser()
if not attempt_path.is_absolute() or not terminal_path.is_absolute():
    raise SystemExit("launch and startup terminal receipt paths must be absolute")
if attempt_path.parent != terminal_path.parent:
    raise SystemExit("startup terminal receipt must belong to the launch attempt")
if terminal_path.name != "startup-terminal.json":
    raise SystemExit("startup terminal receipt must use its canonical file name")
try:
    output_resolved = output_root.resolve(strict=True)
except OSError as error:
    raise SystemExit(f"QWQ_OUTPUT_ROOT is unavailable: {error}") from None
for label, path in (("launch", attempt_path), ("startup terminal", terminal_path)):
    if path.exists() or path.is_symlink():
        raise SystemExit(f"{label} receipt path must be fresh")
    if path.parent.resolve(strict=False) != path.parent.absolute():
        raise SystemExit(f"{label} receipt parent is unsafe")
    try:
        path.resolve(strict=False).relative_to(output_resolved)
    except ValueError:
        raise SystemExit(f"{label} receipt path escapes QWQ_OUTPUT_ROOT") from None
PY
then
  echo "[run] APP.LAUNCH.receipt_invalid: launch and startup terminal evidence paths are unsafe or stale." >&2
  exit 2
fi
export QWQ_APP_STARTUP_TERMINAL_RECEIPT="$STARTUP_TERMINAL_RECEIPT"
TEARDOWN_RECEIPT="$(dirname "$LAUNCH_RECEIPT")/teardown.json"
case "${QWQ_RUN_DEVICE_KIND:-}" in
  android*)
    LAUNCH_PLATFORM=android
    LAUNCH_ARTIFACT_PATH="$APP_DIR/build/app/outputs/flutter-apk/app-nonprod-debug.apk"
    ;;
  ios-simulator)
    LAUNCH_PLATFORM=ios
    LAUNCH_ARTIFACT_PATH="$APP_DIR/build/ios/iphonesimulator/Runner.app"
    ;;
  ios-physical)
    LAUNCH_PLATFORM=ios
    LAUNCH_ARTIFACT_PATH="$APP_DIR/build/ios/iphoneos/Runner.app"
    ;;
  *)
    echo "[run] GATE_BLOCK: unsupported launch platform ${QWQ_RUN_DEVICE_KIND:-unknown}." >&2
    exit 2
    ;;
esac
if [[ -n "$TEST_LIVE_REPORT_OVERRIDE" ]]; then
  CONTROL_EXPECTED_PLATFORM="$QWQ_RUN_DEVICE_KIND"
  [[ "$CONTROL_EXPECTED_PLATFORM" != "android_emulator" ]] || CONTROL_EXPECTED_PLATFORM=android
  [[ "$CONTROL_EXPECTED_PLATFORM" != "android_physical" ]] || CONTROL_EXPECTED_PLATFORM=android-physical
  if [[ "$QWQ_CANONICAL_CONTROL_PLATFORM" != "$CONTROL_EXPECTED_PLATFORM" ]]; then
    echo "[run] APP.LAUNCH.receipt_invalid: canonical launch control platform drifted." >&2
    exit 2
  fi
fi
SUPERVISOR_CMD=(
  python3 "$APP_DIR/scripts/device/supervise_app_launch.py"
  --receipt "$LAUNCH_RECEIPT"
  --environment "$QWQ_APP_RUNTIME_ENV"
  --target "$QWQ_LAUNCH_TARGET"
  --platform "$LAUNCH_PLATFORM"
  --build-profile "$QWQ_APP_BUILD_PROFILE"
  --build-mode debug
  --run-mode "$RUN_MODE"
  --device "$DEVICE_ID"
  --application-id "${QWQ_DEBUG_APP_ID:-}"
  --launch-provenance "$LAUNCH_PROVENANCE"
  --runtime-config-supply-mode "$RUNTIME_CONFIG_SUPPLY_MODE"
  --runtime-config-trust-envelope-digest "$RUNTIME_CONFIG_TRUST_ENVELOPE_DIGEST"
  --runtime-config-package-digest "$RUNTIME_CONFIG_PACKAGE_DIGEST"
  --flutter-version "$QWQ_FLUTTER_VERSION"
  --command-resolution-digest "$QWQ_COMMAND_RESOLUTION_DIGEST"
  --artifact-path "$LAUNCH_ARTIFACT_PATH"
  --launch-digest "$EFFECTIVE_LAUNCH_MANIFEST_DIGEST"
  --timeout-seconds "$LAUNCH_TIMEOUT_SECONDS"
)
SUPERVISOR_CMD+=(
  --require-safe-terminal
  --startup-terminal-receipt "$STARTUP_TERMINAL_RECEIPT"
)
if [[ "$EXIT_AFTER_LAUNCH" == "1" ]]; then
  SUPERVISOR_CMD+=(--exit-after-launch)
fi
if [[ -n "$LAUNCH_LOG_REF" ]]; then
  SUPERVISOR_CMD+=(--log-ref "$LAUNCH_LOG_REF")
fi
for launch_warning in "${PRELAUNCH_WARNINGS[@]:-}"; do
  [[ -z "$launch_warning" ]] || SUPERVISOR_CMD+=(--warning "$launch_warning")
done
RUN_INSTANCE_CMD=(
  python3 "$APP_DIR/scripts/device/run_app_instance.py"
  --device-kind "$QWQ_RUN_DEVICE_KIND"
  --device "$DEVICE_ID"
  --application-id "$QWQ_DEBUG_APP_ID"
  --entrypoint "$ENTRYPOINT"
  --activation-timeout-seconds "$ACTIVATION_TIMEOUT_SECONDS"
  --attach-timeout-seconds "$LAUNCH_TIMEOUT_SECONDS"
)
if [[ -n "$IDE_VM_SERVICE_INFO_FILE" ]]; then
  RUN_INSTANCE_CMD+=(
    --vm-service-info-file "$IDE_VM_SERVICE_INFO_FILE"
    --vm-service-info-allowed-root "$IDE_VM_SERVICE_ALLOWED_ROOT"
  )
fi
"${SUPERVISOR_CMD[@]}" -- "${RUN_INSTANCE_CMD[@]}" -- "$@"
FLUTTER_RUN_EXIT_CODE=$?
set -e

# Re-open every dependency domain in a new process after the real Flutter
# command. A compile/launch blocker remains primary when both layers fail.
if ! verify_dependency_projection_after_command postbuild; then
  if [[ "$FLUTTER_RUN_EXIT_CODE" != "0" ]]; then
    echo "[run] APP.DEPENDENCY.projection_cas_drift: postbuild dependency failure is secondary to the recorded launch attempt blocker." >&2
    exit "$FLUTTER_RUN_EXIT_CODE"
  fi
  exit 2
fi

# The process group is fully stopped when the supervisor returns. Seal the
# resulting tree at a fresh path so a permitted iOS retry can compare its
# pre-build tree with attempt-1 rather than trusting a stale source-only digest.
if ! seal_app_content_projection_build evidence; then
  if [[ "$FLUTTER_RUN_EXIT_CODE" != "0" ]]; then
    exit "$FLUTTER_RUN_EXIT_CODE"
  fi
  exit 2
fi

if [[ -n "$TEST_LIVE_REPORT_OVERRIDE" ]]; then
  TEST_LIVE_REPORT_PATH="$TEST_LIVE_REPORT_OVERRIDE"
  TEST_LIVE_REPORT_DIR="$(dirname "$TEST_LIVE_REPORT_PATH")"
else
  TEST_LIVE_REPORT_DIR="$QWQ_OUTPUT_ROOT/env/repo/runs/$(date -u +%Y%m%dT%H%M%SZ)-$$-${QWQ_LAUNCH_TARGET}-flutter-test-live"
  TEST_LIVE_REPORT_PATH="$TEST_LIVE_REPORT_DIR/report.json"
fi
mkdir -p "$TEST_LIVE_REPORT_DIR"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}" \
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
  "$HANDOFF_JSON" \
  "$TEST_LIVE_REPORT_PATH" \
  "$QWQ_OUTPUT_ROOT" \
  "${QWQ_CANONICAL_CANDIDATE_DIGEST:-}" \
  "${QWQ_CANONICAL_CANDIDATE_PACKAGE_DIGEST:-}" \
  "${QWQ_CANONICAL_SOURCE_CAPSULE_MANIFEST_DIGEST:-}" \
  "${QWQ_CANONICAL_SOURCE_PROJECTION_EVIDENCE_DIGEST:-}" \
  "${QWQ_CANONICAL_SOURCE_PROJECTION_EVIDENCE_REF:-}" \
  "$CANONICAL_LAUNCH_CONTROL_DIGEST" \
  "$CANONICAL_LAUNCH_CONTROL" \
  "$QWQ_BUILD_PROJECTION_SEAL_REF" \
  "$QWQ_BUILD_PROJECTION_SEAL_DIGEST" \
  "${QWQ_CANONICAL_BUILD_PROJECTION_POLICY_ID:-}" \
  "$QWQ_PREBUILD_BUILD_PROJECTION_DIGEST" \
  "${QWQ_CANONICAL_EXPECTED_BUILD_PROJECTION_DIGEST:-}" \
  "$QWQ_DEPENDENCY_PROJECTION_EXPECTATION_REF" \
  "$QWQ_DEPENDENCY_PROJECTION_EXPECTATION_DIGEST" \
  "$QWQ_DEPENDENCY_PROJECTION_PREBUILD_READBACK_REF" \
  "$QWQ_DEPENDENCY_PROJECTION_PREBUILD_READBACK_DIGEST" \
  "$QWQ_DEPENDENCY_PROJECTION_POSTBUILD_READBACK_REF" \
  "$QWQ_DEPENDENCY_PROJECTION_POSTBUILD_READBACK_DIGEST" <<'PY'
import hashlib
import json
import pathlib
import re
import sys

from quwoquan_ops.cli.lib.app_launch_attempt import (
    LAUNCH_BLOCKERS,
    read_app_launch_attempt,
)

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
    handoff_json,
    report_path,
    output_root,
    candidate_digest,
    candidate_package_digest,
    source_capsule_manifest_digest,
    source_projection_evidence_digest,
    source_projection_evidence_ref,
    canonical_launch_control_digest,
    canonical_launch_control_ref,
    build_projection_seal_ref,
    build_projection_seal_digest,
    build_projection_policy_id,
    prebuild_projection_digest,
    expected_build_projection_digest,
    dependency_projection_expectation_ref,
    dependency_projection_expectation_digest,
    dependency_projection_prebuild_readback_ref,
    dependency_projection_prebuild_readback_digest,
    dependency_projection_postbuild_readback_ref,
    dependency_projection_postbuild_readback_digest,
) = sys.argv[1:]
from quwoquan_ops.cli.commands.app_preflight_uat_launch import (
    write_app_content_launch_report,
)

preflight = json.loads(preflight_json)
delivery = json.loads(delivery_json)
handoff = json.loads(handoff_json)
exit_code = int(flutter_exit_code)
try:
    receipt = read_app_launch_attempt(pathlib.Path(launch_receipt_path))
except FileNotFoundError:
    raise SystemExit(
        "APP.LAUNCH.receipt_absent: supervisor produced no launch attempt receipt at "
        + launch_receipt_path
    ) from None
except OSError as error:
    raise SystemExit(
        f"APP.LAUNCH.receipt_unreadable: {launch_receipt_path}: {error}"
    ) from None
except (TypeError, ValueError) as error:
    raise SystemExit(
        f"APP.LAUNCH.receipt_invalid: {launch_receipt_path}: {error}"
    ) from None
transition_states = [
    str(item.get("status") or "")
    for item in receipt.get("transitions") or []
    if isinstance(item, dict)
]
artifact_digest = str(receipt.get("artifactDigest") or "")
if "compiled" in transition_states and re.fullmatch(
    r"sha256:[0-9a-f]{64}", artifact_digest
) is None:
    raise SystemExit(
        "APP.LAUNCH.receipt_invalid: compiled launch attempt requires exact artifactDigest"
    )
first_blocker = str(receipt.get("firstBlocker") or "")
if first_blocker and first_blocker not in LAUNCH_BLOCKERS:
    raise SystemExit(
        "APP.LAUNCH.receipt_invalid: launch attempt firstBlocker is not canonical"
    )
launch_warnings = [str(item) for item in receipt.get("warnings") or []]
terminal_identity = {
    "startupTerminalAttemptId": str(receipt.get("startupTerminalAttemptId") or ""),
    "startupTerminalEvidenceDigest": str(
        receipt.get("startupTerminalEvidenceDigest") or ""
    ),
    "startupTerminalEvidenceRef": str(
        receipt.get("startupTerminalEvidenceRef") or ""
    ),
}
if "launched" in transition_states and (
    not terminal_identity["startupTerminalAttemptId"]
    or re.fullmatch(
        r"sha256:[0-9a-f]{64}",
        terminal_identity["startupTerminalEvidenceDigest"],
    )
    is None
    or not terminal_identity["startupTerminalEvidenceRef"]
):
    raise SystemExit(
        "APP.LAUNCH.receipt_invalid: launched attempt lacks safe-terminal evidence"
    )
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
runtime_package = handoff.get("runtimeConfigPackage")
if not isinstance(runtime_package, dict):
    raise SystemExit(
        "APP.LAUNCH.receipt_invalid: launcher handoff runtime package is missing"
    )
canonical_attempt = json.dumps(
    receipt,
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
).encode("utf-8")
launch_attempt_digest = "sha256:" + hashlib.sha256(canonical_attempt).hexdigest()
projection_evidence = {}
if source_projection_evidence_ref:
    projection_evidence = json.loads(
        pathlib.Path(source_projection_evidence_ref).read_text(encoding="utf-8")
    )
    projection_evidence_actual_digest = "sha256:" + hashlib.sha256(json.dumps(
        projection_evidence,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    if projection_evidence_actual_digest != source_projection_evidence_digest:
        raise SystemExit(
            "APP.LAUNCH.receipt_invalid: source projection evidence drifted"
        )
build_projection_seal_fields = {
    "schema",
    "policyId",
    "sourceProjectionDigest",
    "sourceEntryCount",
    "derivedOutputDigest",
    "derivedOutputPolicyDigest",
    "derivedEntryCount",
    "buildProjectionDigest",
}
build_projection_seal = {}
if build_projection_seal_ref:
    build_projection_seal = json.loads(
        pathlib.Path(build_projection_seal_ref).read_text(encoding="utf-8")
    )
    actual_build_projection_seal_digest = "sha256:" + hashlib.sha256(json.dumps(
        build_projection_seal,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    if (
        not isinstance(build_projection_seal, dict)
        or set(build_projection_seal) != build_projection_seal_fields
        or actual_build_projection_seal_digest != build_projection_seal_digest
        or build_projection_seal.get("policyId") != build_projection_policy_id
        or build_projection_seal.get("sourceProjectionDigest")
        != projection_evidence.get("sourceProjectionDigest")
        or build_projection_seal.get("sourceEntryCount")
        != projection_evidence.get("sourceProjectionFileCount")
    ):
        raise SystemExit(
            "APP.LAUNCH.receipt_invalid: build projection seal evidence drifted"
        )
    for field in (
        "sourceProjectionDigest",
        "derivedOutputDigest",
        "derivedOutputPolicyDigest",
        "buildProjectionDigest",
    ):
        if re.fullmatch(
            r"sha256:[0-9a-f]{64}", str(build_projection_seal.get(field) or "")
        ) is None:
            raise SystemExit(
                f"APP.LAUNCH.receipt_invalid: build projection seal {field} is invalid"
            )
    if re.fullmatch(r"sha256:[0-9a-f]{64}", prebuild_projection_digest) is None:
        raise SystemExit(
            "APP.LAUNCH.receipt_invalid: pre-build projection digest is invalid"
        )
elif any(
    (
        build_projection_seal_digest,
        build_projection_policy_id,
        prebuild_projection_digest,
        expected_build_projection_digest,
    )
):
    raise SystemExit(
        "APP.LAUNCH.receipt_invalid: partial build projection seal identity"
    )
if expected_build_projection_digest and (
    expected_build_projection_digest != prebuild_projection_digest
):
    raise SystemExit(
        "APP.LAUNCH.receipt_invalid: retry build projection digest drifted"
    )
receipt_identity = {
    "launchProvenance": str(receipt.get("launchProvenance") or ""),
    "runtimeConfigSupplyMode": str(receipt.get("runtimeConfigSupplyMode") or ""),
    "runtimeConfigTrustEnvelopeDigest": str(
        receipt.get("runtimeConfigTrustEnvelopeDigest") or ""
    ),
    "runtimeConfigPackageDigest": str(
        receipt.get("runtimeConfigPackageDigest") or ""
    ),
    "effectiveLaunchManifestDigest": str(receipt.get("launchDigest") or ""),
}
handoff_identity = {
    "launchProvenance": str(handoff.get("launchProvenance") or ""),
    "runtimeConfigSupplyMode": str(handoff.get("runtimeConfigSupplyMode") or ""),
    "runtimeConfigTrustEnvelopeDigest": str(
        handoff.get("runtimeConfigTrustEnvelopeDigest") or ""
    ),
    "runtimeConfigPackageDigest": str(handoff.get("runtimeConfigPackageDigest") or ""),
    "effectiveLaunchManifestDigest": str(
        handoff.get("effectiveLaunchManifestDigest") or ""
    ),
}
if receipt_identity != handoff_identity:
    raise SystemExit(
        "APP.LAUNCH.receipt_invalid: launch attempt differs from canonical handoff"
    )
report = {
    "schema": "quwoquan_app.test_live_launch",
    "environment": environment,
    "target": target,
    "deviceId": device_id,
    "platform": receipt.get("platform"),
    "deviceKind": platform,
    "runMode": run_mode,
    "nonPromotable": True,
    "contentLive": preflight.get("contentLive", "not_evaluated"),
    "launchPolicy": "test_live",
    "compileStatus": compile_status,
    "installStatus": install_status,
    "launchStatus": launch_status,
    "runtimeStatus": receipt.get("runtimeHealthStatus")
    if receipt.get("runtimeHealthStatus") != "unobserved"
    else runtime_status,
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
    "launchProvenance": receipt_identity["launchProvenance"],
    "runtimeConfigSupplyMode": receipt_identity["runtimeConfigSupplyMode"],
    "runtimeConfigTrustEnvelopeDigest": receipt_identity[
        "runtimeConfigTrustEnvelopeDigest"
    ],
    "runtimeConfigPackageDigest": receipt_identity["runtimeConfigPackageDigest"],
    "applicationId": receipt.get("applicationId"),
    "sourceGitSha": runtime_package.get("sourceGitSha"),
    "sourceTreeDigest": runtime_package.get("sourceTreeDigest"),
    "launchAttemptId": receipt.get("attemptId"),
    "launchAttemptRef": launch_receipt_path,
    "launchAttemptDigest": launch_attempt_digest,
    "artifactDigest": artifact_digest,
    **terminal_identity,
    "candidateDigest": candidate_digest,
    "candidatePackageDigest": candidate_package_digest,
    "sourceCapsuleManifestDigest": source_capsule_manifest_digest,
    "sourceProjectionEvidenceDigest": source_projection_evidence_digest,
    "sourceProjectionEvidenceRef": source_projection_evidence_ref,
    "sourceProjectionDigest": projection_evidence.get(
        "sourceProjectionDigest", ""
    ),
    "sourceProjectionFileCount": projection_evidence.get(
        "sourceProjectionFileCount", 0
    ),
    "prebuildProjectionDigest": prebuild_projection_digest,
    "buildProjectionSeal": build_projection_seal,
    "buildProjectionSealDigest": build_projection_seal_digest,
    "buildProjectionSealRef": build_projection_seal_ref,
    "canonicalLaunchControlDigest": canonical_launch_control_digest,
    "canonicalLaunchControlRef": canonical_launch_control_ref,
    "dependencyProjectionExpectationRef": dependency_projection_expectation_ref,
    "dependencyProjectionExpectationDigest": dependency_projection_expectation_digest,
    "dependencyProjectionPrebuildReadbackRef": dependency_projection_prebuild_readback_ref,
    "dependencyProjectionPrebuildReadbackDigest": dependency_projection_prebuild_readback_digest,
    "dependencyProjectionPostbuildReadbackRef": dependency_projection_postbuild_readback_ref,
    "dependencyProjectionPostbuildReadbackDigest": dependency_projection_postbuild_readback_digest,
}
written_report = write_app_content_launch_report(
    report=report,
    output_root=pathlib.Path(output_root),
    report_path=pathlib.Path(report_path),
)
print(f"[run] test_live report: {written_report['launchReportRef']}")
PY

exit "$FLUTTER_RUN_EXIT_CODE"
