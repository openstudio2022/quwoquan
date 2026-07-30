package main

import "net/http"

func (s *productService) handleListWorkflows(w http.ResponseWriter, r *http.Request) {
	items, err := s.store.ListWorkflows()
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (s *productService) handleListAudits(w http.ResponseWriter, r *http.Request) {
	items, err := s.store.ListAudits()
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (s *productService) handleListApprovals(w http.ResponseWriter, r *http.Request) {
	items, err := s.store.ListAllApprovals()
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (s *productService) handleProjectionSummary(w http.ResponseWriter, r *http.Request) {
	summary, err := s.buildProjectionSummary()
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, summary)
}
