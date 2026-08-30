# Shared helpers for the Cursor workspace ZDOTDIR projection.
# This file is sourced into the current zsh; it must never start another shell.

typeset -g _QWQ_WORKSPACE_BRIDGE_ZDOTDIR="${${(%):-%N}:A:h}"
typeset -g _QWQ_WORKSPACE_FACADE_DIR="${_QWQ_WORKSPACE_BRIDGE_ZDOTDIR:h}"
typeset -g _QWQ_WORKSPACE_REPO_ROOT="${_QWQ_WORKSPACE_FACADE_DIR:h:h:h:h:A}"

function _qwq_workspace_stage_begin() {
  local stage_name="$1"
  local wrapper_path="$2"
  local user_zdotdir="${QWQ_WORKSPACE_ORIGINAL_ZDOTDIR:-$HOME}"

  if [[ -z "$user_zdotdir" || "$user_zdotdir" == '${env:ZDOTDIR}' ]]; then
    user_zdotdir="$HOME"
  fi
  if [[ "${user_zdotdir:A}" == "${_QWQ_WORKSPACE_BRIDGE_ZDOTDIR:A}" ]]; then
    user_zdotdir="$HOME"
  fi

  typeset -g _QWQ_WORKSPACE_STAGE_USER_ZDOTDIR="$user_zdotdir"
  typeset -g _QWQ_WORKSPACE_STAGE_RC="${user_zdotdir}/${stage_name}"
  if [[ ! -r "$_QWQ_WORKSPACE_STAGE_RC" \
        || "${_QWQ_WORKSPACE_STAGE_RC:A}" == "${wrapper_path:A}" ]]; then
    _QWQ_WORKSPACE_STAGE_RC=""
  fi
  ZDOTDIR="$user_zdotdir"
  export ZDOTDIR
}

function _qwq_workspace_restore_path() {
  local facade_bin="${QWQ_WORKSPACE_FLUTTER_FACADE_BIN:-${_QWQ_WORKSPACE_FACADE_DIR}/bin}"
  local real_flutter="${QWQ_REAL_FLUTTER:-}"
  local pod_executable="${QWQ_COCOAPODS_EXECUTABLE:-}"
  local real_flutter_bin="${real_flutter:A:h}"
  local pod_bin="${pod_executable:A:h}"
  local entry entry_key
  local -A seen_path
  local -a remaining_path

  QWQ_WORKSPACE_FLUTTER_FACADE_BIN="$facade_bin"
  export QWQ_WORKSPACE_FLUTTER_FACADE_BIN
  seen_path=()
  remaining_path=()
  for entry in "${path[@]}"; do
    [[ -n "$entry" ]] || continue
    entry_key="${entry:A}"
    [[ "$entry_key" == "${facade_bin:A}" || \
        "$entry_key" == "$real_flutter_bin" || \
        "$entry_key" == "$pod_bin" || \
        -n "${seen_path[$entry_key]:-}" ]] && continue
    seen_path[$entry_key]=1
    remaining_path+=("$entry")
  done
  path=("$facade_bin" "$real_flutter_bin" "$pod_bin" "${remaining_path[@]}")
  export PATH
  rehash
}

function _qwq_workspace_is_final_stage() {
  local stage_name="$1"
  if [[ -o login ]]; then
    [[ "$stage_name" == ".zlogin" ]]
    return
  fi
  if [[ -o interactive ]]; then
    [[ "$stage_name" == ".zshrc" ]]
    return
  fi
  [[ "$stage_name" == ".zshenv" ]]
}

function _qwq_workspace_final_fail() {
  print -u2 -- \
    "GATE_BLOCK: APP.LAUNCH.workspace_entrypoint_inactive; $1"
  exit 2
}

function _qwq_workspace_validate_and_write_receipt() {
  local facade_bin="${QWQ_WORKSPACE_FLUTTER_FACADE_BIN:-${_QWQ_WORKSPACE_FACADE_DIR}/bin}"
  local facade_executable="$facade_bin/flutter"
  local expected_pod="${QWQ_COCOAPODS_EXECUTABLE:-}"
  local flutter_command
  local pod_command
  local receipt_python="${QWQ_WORKSPACE_PYTHON:-}"
  local receipt_python_version="${QWQ_WORKSPACE_PYTHON_VERSION:-}"
  local inspected_python
  local shell_pid

  zmodload zsh/system || _qwq_workspace_final_fail \
    "cannot inspect final terminal shell PID"
  shell_pid="$sysparams[pid]"
  if [[ -z "${QWQ_CURSOR_TERMINAL_PROFILE_ACTIVE:-}" ]]; then
    return 0
  fi
  [[ "$shell_pid" == "${QWQ_TERMINAL_SHELL_PID:-}" ]] || \
    _qwq_workspace_final_fail "final startup stage ran outside the carrier shell PID"
  flutter_command="$(whence -p flutter 2>/dev/null)" || \
    _qwq_workspace_final_fail "final PATH does not resolve flutter"
  pod_command="$(whence -p pod 2>/dev/null)" || \
    _qwq_workspace_final_fail "final PATH does not resolve pod"
  [[ "${flutter_command:A}" == "${facade_executable:A}" ]] || \
    _qwq_workspace_final_fail "final flutter command does not resolve the workspace facade"
  [[ -n "$expected_pod" && "${pod_command:A}" == "${expected_pod:A}" ]] || \
    _qwq_workspace_final_fail "final pod command differs from projected CocoaPods identity"
  [[ -n "$receipt_python" && -x "$receipt_python" ]] || \
    _qwq_workspace_final_fail "projected workspace Python identity is unavailable"
  receipt_python="${receipt_python:A}"
  inspected_python="$(
    /usr/bin/env -i PATH=/usr/bin:/bin LC_ALL=C \
      "$receipt_python" -I -c \
      'import os,sys; print(f"{os.path.realpath(sys.executable)}|{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")'
  )" || _qwq_workspace_final_fail \
    "projected workspace Python identity cannot be inspected"
  [[ "$inspected_python" == "${receipt_python}|${receipt_python_version}" ]] || \
    _qwq_workspace_final_fail "projected workspace Python identity drifted"

  export QWQ_TERMINAL_FINAL_FLUTTER_COMMAND_REALPATH="${flutter_command:A}"
  export QWQ_TERMINAL_FINAL_POD_COMMAND_REALPATH="${pod_command:A}"
  (
    cd "$_QWQ_WORKSPACE_REPO_ROOT" || exit 2
    "$receipt_python" "$_QWQ_WORKSPACE_FACADE_DIR/terminal_surface_receipt.py" \
      --surface "${QWQ_TERMINAL_SURFACE:-folder-new-terminal}" \
      --shell-pid "$shell_pid" \
      --workspace-uri "${QWQ_TERMINAL_WORKSPACE_URI:-}" \
      --logical-root "${QWQ_TERMINAL_WORKSPACE_LOGICAL_ROOT:-}" \
      --physical-root "${QWQ_TERMINAL_WORKSPACE_PHYSICAL_ROOT:-}" >/dev/null
  ) || _qwq_workspace_final_fail "final terminal validation or receipt creation failed"
}

function _qwq_workspace_stage_end() {
  local source_status="$1"
  local stage_name="${2:-}"
  local user_zdotdir="${ZDOTDIR:-$HOME}"

  if [[ "${user_zdotdir:A}" == "${_QWQ_WORKSPACE_BRIDGE_ZDOTDIR:A}" ]]; then
    user_zdotdir="$_QWQ_WORKSPACE_STAGE_USER_ZDOTDIR"
  fi
  QWQ_WORKSPACE_ORIGINAL_ZDOTDIR="$user_zdotdir"
  export QWQ_WORKSPACE_ORIGINAL_ZDOTDIR
  ZDOTDIR="$_QWQ_WORKSPACE_BRIDGE_ZDOTDIR"
  export ZDOTDIR

  _qwq_workspace_restore_path
  if (( source_status == 0 )) && _qwq_workspace_is_final_stage "$stage_name"; then
    _qwq_workspace_validate_and_write_receipt
  fi

  unset _QWQ_WORKSPACE_STAGE_RC _QWQ_WORKSPACE_STAGE_USER_ZDOTDIR \
    _QWQ_WORKSPACE_STAGE_STATUS
  return "$source_status"
}
