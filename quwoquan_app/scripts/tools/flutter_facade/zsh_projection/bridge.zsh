# Shared helpers for the Cursor workspace ZDOTDIR projection.
# This file is sourced into the current zsh; it must never start another shell.

typeset -g _QWQ_WORKSPACE_BRIDGE_ZDOTDIR="${${(%):-%N}:A:h}"

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

function _qwq_workspace_stage_end() {
  local source_status="$1"
  local user_zdotdir="${ZDOTDIR:-$HOME}"
  local facade_bin="${QWQ_WORKSPACE_FLUTTER_FACADE_BIN:-}"
  local entry
  local -a remaining_path

  if [[ "${user_zdotdir:A}" == "${_QWQ_WORKSPACE_BRIDGE_ZDOTDIR:A}" ]]; then
    user_zdotdir="$_QWQ_WORKSPACE_STAGE_USER_ZDOTDIR"
  fi
  QWQ_WORKSPACE_ORIGINAL_ZDOTDIR="$user_zdotdir"
  export QWQ_WORKSPACE_ORIGINAL_ZDOTDIR
  ZDOTDIR="$_QWQ_WORKSPACE_BRIDGE_ZDOTDIR"
  export ZDOTDIR

  if [[ -n "$facade_bin" ]]; then
    remaining_path=()
    for entry in "${path[@]}"; do
      [[ "$entry" == "$facade_bin" ]] || remaining_path+=("$entry")
    done
    path=("$facade_bin" "${remaining_path[@]}")
    export PATH
  fi

  unset _QWQ_WORKSPACE_STAGE_RC _QWQ_WORKSPACE_STAGE_USER_ZDOTDIR \
    _QWQ_WORKSPACE_STAGE_STATUS
  return "$source_status"
}
