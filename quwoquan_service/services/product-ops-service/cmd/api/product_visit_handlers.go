package main

import (
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strings"

	"quwoquan_service/services/product-ops-service/internal/application"
)

func (s *productService) handleRecordVisit(w http.ResponseWriter, r *http.Request) {
	var body struct {
		TargetType string `json:"targetType"`
		TargetKey  string `json:"targetKey"`
		SessionID  string `json:"sessionId"`
		Source     string `json:"source"`
	}
	decoder := json.NewDecoder(r.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&body); err != nil {
		writeRuntimeError(w, r, http.StatusBadRequest, "请求处理失败", "invalid json body")
		return
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		writeRuntimeError(w, r, http.StatusBadRequest, "请求处理失败", "request body must contain exactly one JSON object")
		return
	}
	if strings.TrimSpace(body.TargetType) == "" || strings.TrimSpace(body.TargetKey) == "" {
		writeRuntimeError(w, r, http.StatusBadRequest, "请求处理失败", "targetType and targetKey are required")
		return
	}
	actorHash, ok := verifiedTelemetryActorHash(r)
	if !ok {
		writeRuntimeError(w, r, http.StatusUnauthorized, "请先登录", "verified telemetry actor is required")
		return
	}
	idempotencyKey := strings.TrimSpace(r.Header.Get("Idempotency-Key"))
	record, err := s.telemetry.RecordVisit(r.Context(), application.VisitInput{
		UserID:     actorHash,
		TargetType: body.TargetType,
		TargetKey:  body.TargetKey,
		SessionID:  body.SessionID,
		Source:     body.Source,
	}, idempotencyKey)
	if err != nil {
		if errors.Is(err, application.ErrVisitIdempotencyKeyRequired) {
			writeRuntimeError(w, r, http.StatusBadRequest, "请求处理失败", err.Error())
			return
		}
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, visitCommandResponse{
		TargetType: record.TargetType,
		TargetKey:  record.TargetKey,
		VisitCount: record.VisitCount,
		LastSeenAt: record.LastSeenAt,
		Replayed:   record.Replayed,
	})
}

// visitCommandResponse 是 RecordVisit 的强类型 wire 响应。
type visitCommandResponse struct {
	TargetType string `json:"targetType"`
	TargetKey  string `json:"targetKey"`
	VisitCount int    `json:"visitCount"`
	LastSeenAt string `json:"lastSeenAt,omitempty"`
	Replayed   bool   `json:"replayed,omitempty"`
}

func (s *productService) handleGetVisitStats(w http.ResponseWriter, r *http.Request) {
	stats, err := s.telemetry.GetVisitStats(r.Context(), application.VisitStatsQuery{
		TargetType: strings.TrimSpace(r.URL.Query().Get("targetType")),
		TargetKey:  strings.TrimSpace(r.URL.Query().Get("targetKey")),
	})
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, stats)
}

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
	workflows, err := s.store.ListWorkflows()
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	approvals, err := s.store.ListAllApprovals()
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	audits, err := s.store.ListAudits()
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	l1l4Cards, err := s.buildL1L4Cards()
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	pendingDualReview := 0
	for _, workflow := range workflows {
		if workflow.State == "dual_review" || workflow.State == "dual_approval_pending" {
			pendingDualReview++
		}
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"workflowCount":     len(workflows),
		"approvalCount":     len(approvals),
		"auditCount":        len(audits),
		"pendingDualReview": pendingDualReview,
		"activeObjectTypes": []string{
			"moderation_case",
			"recovery_case",
			"appeal_case",
			"experiment",
			"recommendation_policy",
			"entity_homepage",
			"circle_scenario",
			"assistant_comment",
			"campus_homepage",
		},
		"l1l4Cards": l1l4Cards,
	})
}
