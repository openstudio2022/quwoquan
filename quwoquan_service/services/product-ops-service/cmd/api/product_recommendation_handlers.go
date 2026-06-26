package main

import (
	"net/http"

	"quwoquan_service/runtime/controlplane"
)

func (s *productService) handleListRecommendationPolicies(w http.ResponseWriter, r *http.Request) {
	items, err := s.store.ListDocuments("recommendation_policies")
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (s *productService) handleSimulateRecommendationPolicy(w http.ResponseWriter, r *http.Request) {
	policyID := segmentBetween(r.URL.Path, "/v1/control-plane/product/recommendation/policies/", ":simulate")
	policy, ok, err := s.getRecommendationPolicy(policyID)
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	if !ok {
		writeRuntimeError(w, r, http.StatusNotFound, "请求处理失败", "recommendation policy not found")
		return
	}
	before := documentFromStruct(policy)
	policy.Status = "simulated"
	policy.UpdatedAt = nowRFC3339()
	if err := s.putDocument("recommendation_policies", policy.ID, policy); err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	_ = s.store.UpsertWorkflow(controlplane.WorkflowState{
		ObjectType: "recommendation_policy",
		ObjectID:   policy.ID,
		WorkflowID: "recommendation_policy_v1",
		State:      "simulated",
		History: []controlplane.WorkflowTransition{{
			From:   "draft",
			To:     "simulated",
			Action: "simulate",
			Actor:  actorFromRequest(r),
			At:     nowRFC3339(),
		}},
		UpdatedAt: nowRFC3339(),
	})
	_ = s.store.AppendAudit(controlplane.AuditEvent{
		AuditID:     "recommendation_policy_activated",
		ObjectType:  "recommendation_policy",
		ObjectID:    policy.ID,
		Action:      "simulate",
		DangerLevel: "high",
		Actor:       actorFromRequest(r),
		Environment: environmentFromRequest(r),
		RequestID:   requestIDFromRequest(r),
		TraceID:     traceIDFromRequest(r),
		Before:      before,
		After:       documentFromStruct(policy),
	})
	writeJSON(w, http.StatusOK, policy)
}

func (s *productService) handleActivateRecommendationPolicy(w http.ResponseWriter, r *http.Request) {
	policyID := segmentBetween(r.URL.Path, "/v1/control-plane/product/recommendation/policies/", ":activate")
	policy, ok, err := s.getRecommendationPolicy(policyID)
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	if !ok {
		writeRuntimeError(w, r, http.StatusNotFound, "请求处理失败", "recommendation policy not found")
		return
	}
	before := documentFromStruct(policy)
	policy.Status = "active"
	policy.UpdatedAt = nowRFC3339()
	if err := s.putDocument("recommendation_policies", policy.ID, policy); err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	_ = s.store.AppendApproval(controlplane.ApprovalDecision{
		ObjectType: "recommendation_policy",
		ObjectID:   policy.ID,
		Mode:       "single",
		Actor:      actorFromRequest(r),
		Decision:   "activate",
	})
	workflow := controlplane.WorkflowState{
		ObjectType: "recommendation_policy",
		ObjectID:   policy.ID,
		WorkflowID: "recommendation_policy_v1",
		State:      "active",
		History: []controlplane.WorkflowTransition{{
			From:   "canary",
			To:     "active",
			Action: "activate",
			Actor:  actorFromRequest(r),
			At:     nowRFC3339(),
		}},
		UpdatedAt: nowRFC3339(),
	}
	_ = s.store.UpsertWorkflow(workflow)
	_ = s.store.AppendAudit(controlplane.AuditEvent{
		AuditID:       "recommendation_policy_activated",
		ObjectType:    "recommendation_policy",
		ObjectID:      policy.ID,
		Action:        "activate",
		DangerLevel:   "high",
		Actor:         actorFromRequest(r),
		Environment:   environmentFromRequest(r),
		RequestID:     requestIDFromRequest(r),
		TraceID:       traceIDFromRequest(r),
		WorkflowRef:   workflow.WorkflowID,
		RollbackToken: "rbk-" + policy.ID,
		Before:        before,
		After:         documentFromStruct(policy),
		Metadata:      map[string]any{"guardrailSnapshot": policy.GuardrailSnapshot},
	})
	writeJSON(w, http.StatusOK, policy)
}
