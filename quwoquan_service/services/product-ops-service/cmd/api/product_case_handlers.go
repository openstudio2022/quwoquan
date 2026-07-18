package main

import (
	"encoding/json"
	"net/http"
	"strings"

	"quwoquan_service/runtime/controlplane"
)

func (s *productService) handleListModerationCases(w http.ResponseWriter, r *http.Request) {
	items, err := s.store.ListDocuments("moderation_cases")
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (s *productService) handleGetModerationCase(w http.ResponseWriter, r *http.Request) {
	caseID := strings.TrimPrefix(r.URL.Path, "/control-plane/product/moderation/cases/")
	caseID = strings.TrimSuffix(caseID, ":startReview")
	caseID = strings.TrimSuffix(caseID, ":applyAction")
	caseID = strings.Trim(caseID, "/")
	item, ok, err := s.store.GetDocument("moderation_cases", caseID)
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	if !ok {
		writeRuntimeError(w, r, http.StatusNotFound, "请求处理失败", "moderation case not found")
		return
	}
	workflow, _, _ := s.store.GetWorkflow("moderation_case", caseID)
	approvals, _ := s.store.ListApprovals("moderation_case", caseID)
	writeJSON(w, http.StatusOK, map[string]any{
		"case":      item,
		"workflow":  workflow,
		"approvals": approvals,
	})
}

func (s *productService) handleStartModerationReview(w http.ResponseWriter, r *http.Request) {
	caseID := segmentBetween(r.URL.Path, "/control-plane/product/moderation/cases/", ":startReview")
	item, ok, err := s.store.GetDocument("moderation_cases", caseID)
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	if !ok {
		writeRuntimeError(w, r, http.StatusNotFound, "请求处理失败", "moderation case not found")
		return
	}
	before := cloneMap(item)
	item["status"] = "reviewing"
	item["updatedAt"] = nowRFC3339()
	if err := s.store.PutDocument("moderation_cases", caseID, item); err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	workflow := controlplane.WorkflowState{
		ObjectType: "moderation_case",
		ObjectID:   caseID,
		WorkflowID: "moderation_case_v1",
		State:      "reviewing",
		History: []controlplane.WorkflowTransition{{
			From:   "triaged",
			To:     "reviewing",
			Action: "start_review",
			Actor:  actorFromRequest(r),
			At:     nowRFC3339(),
		}},
		UpdatedAt: nowRFC3339(),
	}
	_ = s.store.UpsertWorkflow(workflow)
	_ = s.store.AppendAudit(controlplane.AuditEvent{
		AuditID:     "moderation_action_applied",
		ObjectType:  "moderation_case",
		ObjectID:    caseID,
		Action:      "start_review",
		DangerLevel: "high",
		Actor:       actorFromRequest(r),
		Environment: environmentFromRequest(r),
		RequestID:   requestIDFromRequest(r),
		TraceID:     traceIDFromRequest(r),
		WorkflowRef: workflow.WorkflowID,
		Before:      before,
		After:       item,
	})
	writeJSON(w, http.StatusOK, item)
}

func (s *productService) handleApplyEnforcementAction(w http.ResponseWriter, r *http.Request) {
	caseID := segmentBetween(r.URL.Path, "/control-plane/product/moderation/cases/", ":applyAction")
	var body struct {
		Action string `json:"action"`
		Actor  string `json:"actor"`
	}
	_ = json.NewDecoder(r.Body).Decode(&body)
	action := strings.TrimSpace(body.Action)
	if action == "" {
		action = "take_down"
	}
	actor := strings.TrimSpace(body.Actor)
	if actor == "" {
		actor = actorFromRequest(r)
	}
	item, ok, err := s.store.GetDocument("moderation_cases", caseID)
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	if !ok {
		writeRuntimeError(w, r, http.StatusNotFound, "请求处理失败", "moderation case not found")
		return
	}
	before := cloneMap(item)
	approvals, _ := s.store.ListApprovals("moderation_case", caseID)
	if !approvalExists(approvals, actor) {
		_ = s.store.AppendApproval(controlplane.ApprovalDecision{
			ObjectType: "moderation_case",
			ObjectID:   caseID,
			Mode:       "dual",
			Actor:      actor,
			Decision:   action,
		})
		approvals, _ = s.store.ListApprovals("moderation_case", caseID)
	}
	uniqueApprovers := distinctApprovalActors(approvals)
	state := "dual_approval_pending"
	item["status"] = state
	if len(uniqueApprovers) >= 2 {
		state = "action_applied"
		item["status"] = state
		item["resolution"] = action
	}
	item["updatedAt"] = nowRFC3339()
	if err := s.store.PutDocument("moderation_cases", caseID, item); err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	workflow := controlplane.WorkflowState{
		ObjectType: "moderation_case",
		ObjectID:   caseID,
		WorkflowID: "moderation_case_v1",
		State:      state,
		History: []controlplane.WorkflowTransition{{
			From:   "reviewing",
			To:     state,
			Action: action,
			Actor:  actor,
			At:     nowRFC3339(),
		}},
		UpdatedAt: nowRFC3339(),
	}
	_ = s.store.UpsertWorkflow(workflow)
	_ = s.store.AppendAudit(controlplane.AuditEvent{
		AuditID:     "moderation_action_applied",
		ObjectType:  "moderation_case",
		ObjectID:    caseID,
		Action:      action,
		DangerLevel: "high",
		Actor:       actor,
		Environment: environmentFromRequest(r),
		RequestID:   requestIDFromRequest(r),
		TraceID:     traceIDFromRequest(r),
		WorkflowRef: workflow.WorkflowID,
		Before:      before,
		After:       item,
		Metadata:    map[string]any{"approvalCount": len(uniqueApprovers)},
	})
	writeJSON(w, http.StatusOK, map[string]any{
		"case":          item,
		"approvalCount": len(uniqueApprovers),
		"pending":       state != "action_applied",
	})
}

func (s *productService) handleListRecoveryCases(w http.ResponseWriter, r *http.Request) {
	items, err := s.store.ListDocuments("recovery_cases")
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (s *productService) handleGetRecoveryCase(w http.ResponseWriter, r *http.Request) {
	caseID := strings.TrimPrefix(r.URL.Path, "/control-plane/product/recovery/cases/")
	caseID = strings.TrimSuffix(caseID, ":submitDecision")
	caseID = strings.Trim(caseID, "/")
	item, ok, err := s.store.GetDocument("recovery_cases", caseID)
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	if !ok {
		writeRuntimeError(w, r, http.StatusNotFound, "请求处理失败", "recovery case not found")
		return
	}
	workflow, _, _ := s.store.GetWorkflow("recovery_case", caseID)
	approvals, _ := s.store.ListApprovals("recovery_case", caseID)
	writeJSON(w, http.StatusOK, map[string]any{
		"case":      item,
		"workflow":  workflow,
		"approvals": approvals,
	})
}

func (s *productService) handleSubmitRecoveryDecision(w http.ResponseWriter, r *http.Request) {
	caseID := segmentBetween(r.URL.Path, "/control-plane/product/recovery/cases/", ":submitDecision")
	var body struct {
		Decision string `json:"decision"`
		Actor    string `json:"actor"`
	}
	_ = json.NewDecoder(r.Body).Decode(&body)
	decision := strings.TrimSpace(body.Decision)
	if decision == "" {
		decision = "recovered"
	}
	actor := strings.TrimSpace(body.Actor)
	if actor == "" {
		actor = actorFromRequest(r)
	}
	item, ok, err := s.store.GetDocument("recovery_cases", caseID)
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	if !ok {
		writeRuntimeError(w, r, http.StatusNotFound, "请求处理失败", "recovery case not found")
		return
	}
	before := cloneMap(item)
	approvals, _ := s.store.ListApprovals("recovery_case", caseID)
	if !approvalExists(approvals, actor) {
		_ = s.store.AppendApproval(controlplane.ApprovalDecision{
			ObjectType: "recovery_case",
			ObjectID:   caseID,
			Mode:       "dual",
			Actor:      actor,
			Decision:   decision,
		})
		approvals, _ = s.store.ListApprovals("recovery_case", caseID)
	}
	uniqueApprovers := distinctApprovalActors(approvals)
	state := "dual_review"
	if len(uniqueApprovers) >= 2 {
		state = decision
	}
	item["status"] = state
	item["decision"] = decision
	item["updatedAt"] = nowRFC3339()
	if err := s.store.PutDocument("recovery_cases", caseID, item); err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	workflow := controlplane.WorkflowState{
		ObjectType: "recovery_case",
		ObjectID:   caseID,
		WorkflowID: "recovery_case_v1",
		State:      state,
		History: []controlplane.WorkflowTransition{{
			From:   "evidence_verified",
			To:     state,
			Action: decision,
			Actor:  actor,
			At:     nowRFC3339(),
		}},
		UpdatedAt: nowRFC3339(),
	}
	_ = s.store.UpsertWorkflow(workflow)
	_ = s.store.AppendAudit(controlplane.AuditEvent{
		AuditID:     "recovery_decision_submitted",
		ObjectType:  "recovery_case",
		ObjectID:    caseID,
		Action:      decision,
		DangerLevel: "critical",
		Actor:       actor,
		Environment: environmentFromRequest(r),
		RequestID:   requestIDFromRequest(r),
		TraceID:     traceIDFromRequest(r),
		WorkflowRef: workflow.WorkflowID,
		Before:      before,
		After:       item,
		Metadata:    map[string]any{"approvalCount": len(uniqueApprovers)},
	})
	writeJSON(w, http.StatusOK, map[string]any{
		"case":          item,
		"approvalCount": len(uniqueApprovers),
		"pending":       state == "dual_review",
	})
}

func (s *productService) handleListAppealCases(w http.ResponseWriter, r *http.Request) {
	items, err := s.store.ListDocuments("appeal_cases")
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (s *productService) handleGetAppealCase(w http.ResponseWriter, r *http.Request) {
	caseID := strings.TrimPrefix(r.URL.Path, "/control-plane/product/appeal/cases/")
	caseID = strings.TrimSuffix(caseID, ":submitDecision")
	caseID = strings.Trim(caseID, "/")
	item, ok, err := s.store.GetDocument("appeal_cases", caseID)
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	if !ok {
		writeRuntimeError(w, r, http.StatusNotFound, "请求处理失败", "appeal case not found")
		return
	}
	workflow, _, _ := s.store.GetWorkflow("appeal_case", caseID)
	approvals, _ := s.store.ListApprovals("appeal_case", caseID)
	writeJSON(w, http.StatusOK, map[string]any{
		"case":      item,
		"workflow":  workflow,
		"approvals": approvals,
	})
}

func (s *productService) handleSubmitAppealDecision(w http.ResponseWriter, r *http.Request) {
	caseID := segmentBetween(r.URL.Path, "/control-plane/product/appeal/cases/", ":submitDecision")
	var body struct {
		Decision string `json:"decision"`
		Actor    string `json:"actor"`
	}
	_ = json.NewDecoder(r.Body).Decode(&body)
	decision := strings.TrimSpace(body.Decision)
	if decision == "" {
		decision = "approved"
	}
	actor := strings.TrimSpace(body.Actor)
	if actor == "" {
		actor = actorFromRequest(r)
	}
	item, ok, err := s.store.GetDocument("appeal_cases", caseID)
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	if !ok {
		writeRuntimeError(w, r, http.StatusNotFound, "请求处理失败", "appeal case not found")
		return
	}
	before := cloneMap(item)
	_ = s.store.AppendApproval(controlplane.ApprovalDecision{
		ObjectType: "appeal_case",
		ObjectID:   caseID,
		Mode:       "single",
		Actor:      actor,
		Decision:   decision,
	})
	item["status"] = decision
	item["decision"] = decision
	item["updatedAt"] = nowRFC3339()
	if err := s.store.PutDocument("appeal_cases", caseID, item); err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	workflow := controlplane.WorkflowState{
		ObjectType: "appeal_case",
		ObjectID:   caseID,
		WorkflowID: "appeal_case_v1",
		State:      decision,
		History: []controlplane.WorkflowTransition{{
			From:   "under_review",
			To:     decision,
			Action: decision,
			Actor:  actor,
			At:     nowRFC3339(),
		}},
		UpdatedAt: nowRFC3339(),
	}
	_ = s.store.UpsertWorkflow(workflow)
	_ = s.store.AppendAudit(controlplane.AuditEvent{
		AuditID:     "appeal_decision_submitted",
		ObjectType:  "appeal_case",
		ObjectID:    caseID,
		Action:      decision,
		DangerLevel: "high",
		Actor:       actor,
		Environment: environmentFromRequest(r),
		RequestID:   requestIDFromRequest(r),
		TraceID:     traceIDFromRequest(r),
		WorkflowRef: workflow.WorkflowID,
		Before:      before,
		After:       item,
		Metadata:    map[string]any{"evidenceRefs": item["evidenceRefs"]},
	})
	writeJSON(w, http.StatusOK, map[string]any{
		"case": item,
	})
}
