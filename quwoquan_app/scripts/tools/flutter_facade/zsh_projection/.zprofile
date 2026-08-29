builtin source "${${(%):-%N}:A:h}/bridge.zsh"
_qwq_workspace_stage_begin ".zprofile" "${${(%):-%N}:A}"
typeset -g _QWQ_WORKSPACE_STAGE_STATUS=0
if [[ -n "$_QWQ_WORKSPACE_STAGE_RC" ]]; then
  builtin source "$_QWQ_WORKSPACE_STAGE_RC" || _QWQ_WORKSPACE_STAGE_STATUS=$?
fi
builtin source "${${(%):-%N}:A:h}/bridge.zsh"
_qwq_workspace_stage_end "$_QWQ_WORKSPACE_STAGE_STATUS"
return $?
