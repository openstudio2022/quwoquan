#!/bin/sh
# Cursor macOS integrated terminal 的 workspace-owned profile carrier。
set -eu

_qwq_profile_fail() {
  printf '%s\n' \
    "GATE_BLOCK: APP.LAUNCH.workspace_entrypoint_inactive; $1" >&2
  exit 2
}

[ -z "${QWQ_CURSOR_TERMINAL_PROFILE_ACTIVE:-}" ] || \
  _qwq_profile_fail "recursive workspace terminal profile launch"
launcher_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P) || \
  _qwq_profile_fail "launcher directory is unavailable"
facade_dir=$launcher_dir
repo_physical=$(CDPATH= cd -- "$facade_dir/../../../.." && pwd -P) || \
  _qwq_profile_fail "launcher repository is unavailable"
workspace_uri=${QWQ_TERMINAL_WORKSPACE_URI:-}
case "$workspace_uri" in
  ''|'${workspaceFolder}'|*'${workspaceFolder}'*)
    _qwq_profile_fail "workspace URI was not expanded by Cursor"
    ;;
esac
workspace_logical=$workspace_uri
case "$workspace_logical" in
  file://*) workspace_logical=${workspace_logical#file://} ;;
esac
case "$workspace_logical" in
  /*) ;;
  *) _qwq_profile_fail "workspace root is not an absolute path" ;;
esac
workspace_physical=$(CDPATH= cd -- "$workspace_logical" && pwd -P) || \
  _qwq_profile_fail "workspace root is unavailable"
[ "$workspace_physical" = "$repo_physical" ] || \
  _qwq_profile_fail "workspace root differs from launcher repository"
cwd_physical=$(pwd -P) || _qwq_profile_fail "terminal cwd is unavailable"
[ "$cwd_physical" = "$workspace_physical" ] || \
  _qwq_profile_fail "terminal physical cwd differs from workspace root"

facade_bin=$facade_dir/bin
projection_dir=$facade_dir/zsh_projection
original_zdotdir=${ZDOTDIR:-$HOME}
if [ "$original_zdotdir" = "$projection_dir" ]; then
  original_zdotdir=${QWQ_WORKSPACE_ORIGINAL_ZDOTDIR:-$HOME}
fi
if [ -z "$original_zdotdir" ] || [ "$original_zdotdir" = '${env:ZDOTDIR}' ]; then
  original_zdotdir=$HOME
fi
terminal_surface=${QWQ_TERMINAL_SURFACE:-folder-new-terminal}
if [ -z "$terminal_surface" ] || [ "$terminal_surface" = unknown ]; then
  terminal_surface=folder-new-terminal
fi
case "$terminal_surface" in
  folder-new-terminal|agents-window) ;;
  *) _qwq_profile_fail "terminal surface is outside the closed set" ;;
esac

real_flutter=${QWQ_REAL_FLUTTER:-}
[ -x "$real_flutter" ] || \
  _qwq_profile_fail "projected real Flutter identity is unavailable"
real_flutter_bin=$(CDPATH= cd -- "$(dirname -- "$real_flutter")" && pwd -P) || \
  _qwq_profile_fail "projected real Flutter bin is unavailable"
[ "$real_flutter_bin/$(basename -- "$real_flutter")" != "$facade_bin/flutter" ] || \
  _qwq_profile_fail "projected real Flutter identity is recursive"
pod_executable=${QWQ_COCOAPODS_EXECUTABLE:-}
[ -x "$pod_executable" ] || \
  _qwq_profile_fail "projected CocoaPods identity is unavailable"
pod_bin=$(CDPATH= cd -- "$(dirname -- "$pod_executable")" && pwd -P) || \
  _qwq_profile_fail "projected CocoaPods bin is unavailable"

remaining_path=
old_ifs=$IFS
IFS=:
for entry in ${PATH:-}; do
  [ -n "$entry" ] || continue
  [ "$entry" = "$facade_bin" ] && continue
  [ "$entry" = "$real_flutter_bin" ] && continue
  [ "$entry" = "$pod_bin" ] && continue
  case ":$remaining_path:" in
    *":$entry:"*) continue ;;
  esac
  if [ -n "$remaining_path" ]; then
    remaining_path=$remaining_path:$entry
  else
    remaining_path=$entry
  fi
done
IFS=$old_ifs
PATH=$facade_bin:$real_flutter_bin:$pod_bin
if [ -n "$remaining_path" ]; then
  PATH=$PATH:$remaining_path
fi

export QWQ_CURSOR_TERMINAL_PROFILE_ACTIVE=1
export QWQ_TERMINAL_SHELL_PID=$$
export QWQ_TERMINAL_SURFACE=$terminal_surface
export QWQ_TERMINAL_WORKSPACE_LOGICAL_ROOT=$workspace_logical
export QWQ_TERMINAL_WORKSPACE_PHYSICAL_ROOT=$workspace_physical
export QWQ_WORKSPACE_FLUTTER_FACADE_BIN=$facade_bin
export QWQ_WORKSPACE_ORIGINAL_ZDOTDIR=$original_zdotdir
export ZDOTDIR=$projection_dir
export PATH

# carrier 只准备初始投影；最终校验与 receipt 由 user startup 最终 stage 完成。
exec /bin/zsh "$@"
