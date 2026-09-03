# Version-controlled carrier for the explicit opt-in user-zsh PATH injection.
# The generated ~/.config/quwoquan projection exports pinned toolchain and
# exact entrypoint byte identities before sourcing this file. This carrier
# only projects PATH, rehashes, and verifies literal external command
# resolution; it never installs aliases/functions, changes ZDOTDIR, or writes
# a terminal receipt.

_qwq_user_zsh_fail() {
  print -u2 -- "GATE_BLOCK: APP.LAUNCH.workspace_entrypoint_inactive; $1"
  return 2
}

# %N 在函数体内展开会得到函数名；必须在文件顶层（被 source 时）捕获载体路径。
_qwq_user_zsh_carrier_source="${(%):-%N}"

_qwq_user_zsh_sha256() {
  local workspace_python="$1"
  local candidate="$2"
  "$workspace_python" -I -c \
    'import hashlib,sys; print("sha256:" + hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' \
    "$candidate"
}

_qwq_user_zsh_validate_file() {
  local candidate="$1"
  local expected_digest="$2"
  local label="$3"
  local executable="$4"
  local actual_digest

  [[ -n "$expected_digest" ]] ||
    _qwq_user_zsh_fail "$label exact digest is missing" || return
  [[ -f "$candidate" && ! -L "$candidate" && -r "$candidate" ]] ||
    _qwq_user_zsh_fail "$label is not a readable regular non-symlink file: $candidate" || return
  if (( executable )) && [[ ! -x "$candidate" ]]; then
    _qwq_user_zsh_fail "$label is not executable: $candidate" || return
  fi
  [[ "${candidate:A}" == "$candidate" ]] ||
    _qwq_user_zsh_fail "$label is not at its canonical physical path: $candidate" || return
  actual_digest="$(_qwq_user_zsh_sha256 "$QWQ_WORKSPACE_PYTHON" "$candidate")" ||
    _qwq_user_zsh_fail "$label digest could not be computed" || return
  [[ "$actual_digest" == "$expected_digest" ]] ||
    _qwq_user_zsh_fail "$label bytes drifted: $candidate" || return
}

_qwq_user_zsh_project_path() {
  local real_flutter="${QWQ_REAL_FLUTTER:-}"
  local pod_executable="${QWQ_COCOAPODS_EXECUTABLE:-}"
  local workspace_python="${QWQ_WORKSPACE_PYTHON:-}"
  local carrier="${_qwq_user_zsh_carrier_source}"
  local carrier_dir launcher_bin dispatcher wrapper
  local entry entry_key required_entry command_name command_kind command_path
  local -a required remaining
  local -A seen

  carrier="${carrier:A}"
  carrier_dir="${carrier:h}"
  launcher_bin="${carrier_dir:h}/launcher/bin"
  dispatcher="$launcher_bin/flutter"
  wrapper="$launcher_bin/run.sh"

  [[ -d "$launcher_bin" && ! -L "$launcher_bin" && -r "$launcher_bin" && -x "$launcher_bin" ]] ||
    _qwq_user_zsh_fail "canonical launcher bin is unavailable: $launcher_bin" || return
  [[ "${launcher_bin:A}" == "$launcher_bin" ]] ||
    _qwq_user_zsh_fail "canonical launcher bin is not at its physical path: $launcher_bin" || return
  [[ -f "$real_flutter" && ! -L "$real_flutter" && -x "$real_flutter" ]] ||
    _qwq_user_zsh_fail "user-zsh pinned Flutter identity is unavailable" || return
  [[ -f "$pod_executable" && ! -L "$pod_executable" && -x "$pod_executable" ]] ||
    _qwq_user_zsh_fail "user-zsh pinned CocoaPods identity is unavailable" || return
  [[ -f "$workspace_python" && ! -L "$workspace_python" && -x "$workspace_python" ]] ||
    _qwq_user_zsh_fail "user-zsh pinned workspace Python identity is unavailable" || return
  [[ "${real_flutter:A}" == "$real_flutter" ]] ||
    _qwq_user_zsh_fail "user-zsh pinned Flutter identity is not physical" || return
  [[ "${pod_executable:A}" == "$pod_executable" ]] ||
    _qwq_user_zsh_fail "user-zsh pinned CocoaPods identity is not physical" || return
  [[ "${workspace_python:A}" == "$workspace_python" ]] ||
    _qwq_user_zsh_fail "user-zsh pinned workspace Python identity is not physical" || return

  _qwq_user_zsh_validate_file \
    "$carrier" "${QWQ_USER_ZSH_CARRIER_DIGEST:-}" "user-zsh carrier" 0 || return
  _qwq_user_zsh_validate_file \
    "$dispatcher" "${QWQ_FLUTTER_DISPATCHER_DIGEST:-}" "Flutter dispatcher" 1 || return
  _qwq_user_zsh_validate_file \
    "$wrapper" "${QWQ_RUN_SH_WRAPPER_DIGEST:-}" "run.sh wrapper" 1 || return

  # 不允许 managed source 覆盖用户显式 alias/function；在改 PATH 前阻断，
  # 保持失败 shell 的原命令解析不被半激活投影改变。
  for command_name in flutter run.sh; do
    command_kind="$(builtin whence -w -- "$command_name" 2>/dev/null)"
    if [[ "$command_kind" == "$command_name: alias" ||
          "$command_kind" == "$command_name: function" ]]; then
      _qwq_user_zsh_fail "$command_name is not an external command before refresh: $command_kind" || return
    fi
  done

  # 受管前置目录（按序）：launcher bin（run.sh wrapper + flutter dispatcher）、
  # 钉定 Flutter SDK bin、钉定 CocoaPods bin、钉定 Python bin。重复 source 幂等。
  required=(
    "$launcher_bin"
    "${real_flutter:A:h}"
    "${pod_executable:A:h}"
    "${workspace_python:A:h}"
  )
  seen=()
  remaining=()
  for entry in "${path[@]}"; do
    [[ -n "$entry" ]] || continue
    entry_key="${entry:A}"
    for required_entry in "${required[@]}"; do
      [[ "$entry_key" == "$required_entry" ]] && continue 2
    done
    [[ -n "${seen[$entry_key]:-}" ]] && continue
    seen[$entry_key]=1
    remaining+=("$entry")
  done
  path=("${required[@]}" "${remaining[@]}")
  export PATH
  rehash

  # rehash 不会移除 alias/function；两条裸命令必须同时是 external command，
  # 且物理命中 launcher/bin。任何覆盖或 SDK 抢先都 fail closed。
  for command_name in flutter run.sh; do
    command_kind="$(builtin whence -w -- "$command_name" 2>/dev/null)"
    [[ "$command_kind" == "$command_name: command" ]] ||
      _qwq_user_zsh_fail "$command_name is not an external command after refresh: ${command_kind:-missing}" || return
    command_path="$(builtin whence -p -- "$command_name" 2>/dev/null)"
    [[ -n "$command_path" && -f "$command_path" && ! -L "$command_path" ]] ||
      _qwq_user_zsh_fail "$command_name external command is unavailable after refresh" || return
    [[ "${command_path:A}" == "$launcher_bin/$command_name" ]] ||
      _qwq_user_zsh_fail "$command_name resolves outside canonical launcher bin: $command_path" || return
  done
}

_qwq_user_zsh_project_path
_qwq_user_zsh_projection_status=$?
unset -f _qwq_user_zsh_project_path _qwq_user_zsh_validate_file
unset -f _qwq_user_zsh_sha256 _qwq_user_zsh_fail
unset _qwq_user_zsh_carrier_source
if (( _qwq_user_zsh_projection_status != 0 )); then
  unset _qwq_user_zsh_projection_status
  return 2
fi
unset _qwq_user_zsh_projection_status
