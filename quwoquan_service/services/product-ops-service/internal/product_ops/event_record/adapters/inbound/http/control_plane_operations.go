package httpadapter

import "net/http"

func (s *OperationsHandler) handleListWorkflows(w http.ResponseWriter, r *http.Request) {
	items, err := s.controlPlane.ListProductWorkflows()
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (s *OperationsHandler) handleListAudits(w http.ResponseWriter, r *http.Request) {
	items, err := s.controlPlane.ListProductAudits()
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (s *OperationsHandler) handleListApprovals(w http.ResponseWriter, r *http.Request) {
	items, err := s.controlPlane.ListProductApprovals()
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (s *OperationsHandler) handleProjectionSummary(w http.ResponseWriter, r *http.Request) {
	summary, err := s.controlPlane.GetProductProjectionSummary()
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, summary)
}
