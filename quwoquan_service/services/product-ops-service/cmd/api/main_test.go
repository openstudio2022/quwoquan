package main

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"testing"

	"quwoquan_service/runtime/controlplane"
)

func TestExperimentEndpoints(t *testing.T) {
	service := newProductService(controlplane.NewFileStore(filepath.Join(t.TempDir(), "product-ops-state.json")))
	if err := service.seed(); err != nil {
		t.Fatalf("seed service: %v", err)
	}
	server := newServerMux(service)

	assignReq := httptest.NewRequest(http.MethodPost, "/v1/ops/experiments/discovery_feed_v3/assign", bytes.NewBufferString(`{"subjectKey":"user-1"}`))
	assignReq.Header.Set("Content-Type", "application/json")
	assignResp := httptest.NewRecorder()
	server.ServeHTTP(assignResp, assignReq)
	if assignResp.Code != http.StatusOK {
		t.Fatalf("assign bucket status=%d body=%s", assignResp.Code, assignResp.Body.String())
	}

	var assignment map[string]any
	if err := json.Unmarshal(assignResp.Body.Bytes(), &assignment); err != nil {
		t.Fatalf("unmarshal assign response: %v", err)
	}
	if assignment["experimentId"] != "discovery_feed_v3" {
		t.Fatalf("unexpected experimentId: %v", assignment["experimentId"])
	}
	if assignment["bucket"] == "" {
		t.Fatalf("bucket should not be empty: %v", assignment)
	}

	statsReq := httptest.NewRequest(http.MethodGet, "/v1/ops/experiments/discovery_feed_v3/stats", nil)
	statsResp := httptest.NewRecorder()
	server.ServeHTTP(statsResp, statsReq)
	if statsResp.Code != http.StatusOK {
		t.Fatalf("stats status=%d body=%s", statsResp.Code, statsResp.Body.String())
	}

	var stats map[string]any
	if err := json.Unmarshal(statsResp.Body.Bytes(), &stats); err != nil {
		t.Fatalf("unmarshal stats response: %v", err)
	}
	if stats["assignedSubjects"] != float64(1) {
		t.Fatalf("expected assignedSubjects=1, got %v", stats["assignedSubjects"])
	}
}

func TestVisitEndpoints(t *testing.T) {
	service := newProductService(controlplane.NewFileStore(filepath.Join(t.TempDir(), "product-ops-state.json")))
	if err := service.seed(); err != nil {
		t.Fatalf("seed service: %v", err)
	}
	server := newServerMux(service)

	for range 2 {
		recordReq := httptest.NewRequest(http.MethodPost, "/v1/ops/visits", bytes.NewBufferString(`{"targetType":"page","targetKey":"platform-onboarding","userId":"user-1"}`))
		recordReq.Header.Set("Content-Type", "application/json")
		recordResp := httptest.NewRecorder()
		server.ServeHTTP(recordResp, recordReq)
		if recordResp.Code != http.StatusOK {
			t.Fatalf("record visit status=%d body=%s", recordResp.Code, recordResp.Body.String())
		}
	}

	statsReq := httptest.NewRequest(http.MethodGet, "/v1/ops/visits/stats?targetType=page&targetKey=platform-onboarding", nil)
	statsResp := httptest.NewRecorder()
	server.ServeHTTP(statsResp, statsReq)
	if statsResp.Code != http.StatusOK {
		t.Fatalf("visit stats status=%d body=%s", statsResp.Code, statsResp.Body.String())
	}

	var stats struct {
		TotalVisits float64 `json:"totalVisits"`
		Items       []struct {
			TargetKey  string `json:"targetKey"`
			VisitCount int    `json:"visitCount"`
		} `json:"items"`
	}
	if err := json.Unmarshal(statsResp.Body.Bytes(), &stats); err != nil {
		t.Fatalf("unmarshal visit stats response: %v", err)
	}
	if stats.TotalVisits != 2 {
		t.Fatalf("expected totalVisits=2, got %v", stats.TotalVisits)
	}
	if len(stats.Items) != 1 || stats.Items[0].VisitCount != 2 {
		t.Fatalf("unexpected visit items: %+v", stats.Items)
	}
}

func TestControlPlaneWorkflowEndpoints(t *testing.T) {
	service := newProductService(controlplane.NewFileStore(filepath.Join(t.TempDir(), "product-ops-state.json")))
	if err := service.seed(); err != nil {
		t.Fatalf("seed service: %v", err)
	}
	server := newServerMux(service)

	reviewReq := httptest.NewRequest(http.MethodPost, "/v1/control-plane/product/moderation/cases/case_post_901:startReview", nil)
	reviewReq.Header.Set("X-Actor", "reviewer-1")
	reviewResp := httptest.NewRecorder()
	server.ServeHTTP(reviewResp, reviewReq)
	if reviewResp.Code != http.StatusOK {
		t.Fatalf("start review status=%d body=%s", reviewResp.Code, reviewResp.Body.String())
	}

	applyBody := bytes.NewBufferString(`{"action":"take_down","actor":"reviewer-1"}`)
	applyReq := httptest.NewRequest(http.MethodPost, "/v1/control-plane/product/moderation/cases/case_post_901:applyAction", applyBody)
	applyReq.Header.Set("Content-Type", "application/json")
	applyResp := httptest.NewRecorder()
	server.ServeHTTP(applyResp, applyReq)
	if applyResp.Code != http.StatusOK {
		t.Fatalf("apply action status=%d body=%s", applyResp.Code, applyResp.Body.String())
	}

	secondApplyBody := bytes.NewBufferString(`{"action":"take_down","actor":"reviewer-2"}`)
	secondApplyReq := httptest.NewRequest(http.MethodPost, "/v1/control-plane/product/moderation/cases/case_post_901:applyAction", secondApplyBody)
	secondApplyReq.Header.Set("Content-Type", "application/json")
	secondApplyResp := httptest.NewRecorder()
	server.ServeHTTP(secondApplyResp, secondApplyReq)
	if secondApplyResp.Code != http.StatusOK {
		t.Fatalf("second apply action status=%d body=%s", secondApplyResp.Code, secondApplyResp.Body.String())
	}

	recoveryBody := bytes.NewBufferString(`{"decision":"recovered","actor":"approver-1"}`)
	recoveryReq := httptest.NewRequest(http.MethodPost, "/v1/control-plane/product/recovery/cases/recovery_user_1827:submitDecision", recoveryBody)
	recoveryReq.Header.Set("Content-Type", "application/json")
	recoveryResp := httptest.NewRecorder()
	server.ServeHTTP(recoveryResp, recoveryReq)
	if recoveryResp.Code != http.StatusOK {
		t.Fatalf("submit recovery decision status=%d body=%s", recoveryResp.Code, recoveryResp.Body.String())
	}

	policyReq := httptest.NewRequest(http.MethodPost, "/v1/control-plane/product/recommendation/policies/policy_discovery_rank_v12:activate", nil)
	policyReq.Header.Set("X-Actor", "ops-approver")
	policyResp := httptest.NewRecorder()
	server.ServeHTTP(policyResp, policyReq)
	if policyResp.Code != http.StatusOK {
		t.Fatalf("activate recommendation policy status=%d body=%s", policyResp.Code, policyResp.Body.String())
	}

	appealBody := bytes.NewBufferString(`{"decision":"approved","actor":"appeal-reviewer"}`)
	appealReq := httptest.NewRequest(http.MethodPost, "/v1/control-plane/product/appeal/cases/appeal_case_301:submitDecision", appealBody)
	appealReq.Header.Set("Content-Type", "application/json")
	appealResp := httptest.NewRecorder()
	server.ServeHTTP(appealResp, appealReq)
	if appealResp.Code != http.StatusOK {
		t.Fatalf("submit appeal decision status=%d body=%s", appealResp.Code, appealResp.Body.String())
	}

	workflowReq := httptest.NewRequest(http.MethodGet, "/v1/control-plane/product/workflows", nil)
	workflowResp := httptest.NewRecorder()
	server.ServeHTTP(workflowResp, workflowReq)
	if workflowResp.Code != http.StatusOK {
		t.Fatalf("list workflows status=%d body=%s", workflowResp.Code, workflowResp.Body.String())
	}

	var workflowPayload struct {
		Items []map[string]any `json:"items"`
	}
	if err := json.Unmarshal(workflowResp.Body.Bytes(), &workflowPayload); err != nil {
		t.Fatalf("unmarshal workflows: %v", err)
	}
	if len(workflowPayload.Items) == 0 {
		t.Fatalf("expected workflows to be populated")
	}

	auditReq := httptest.NewRequest(http.MethodGet, "/v1/control-plane/product/audits", nil)
	auditResp := httptest.NewRecorder()
	server.ServeHTTP(auditResp, auditReq)
	if auditResp.Code != http.StatusOK {
		t.Fatalf("list audits status=%d body=%s", auditResp.Code, auditResp.Body.String())
	}

	var auditPayload struct {
		Items []map[string]any `json:"items"`
	}
	if err := json.Unmarshal(auditResp.Body.Bytes(), &auditPayload); err != nil {
		t.Fatalf("unmarshal audits: %v", err)
	}
	if len(auditPayload.Items) < 3 {
		t.Fatalf("expected audit events, got %+v", auditPayload.Items)
	}

	approvalReq := httptest.NewRequest(http.MethodGet, "/v1/control-plane/product/approvals", nil)
	approvalResp := httptest.NewRecorder()
	server.ServeHTTP(approvalResp, approvalReq)
	if approvalResp.Code != http.StatusOK {
		t.Fatalf("list approvals status=%d body=%s", approvalResp.Code, approvalResp.Body.String())
	}

	var approvalPayload struct {
		Items []map[string]any `json:"items"`
	}
	if err := json.Unmarshal(approvalResp.Body.Bytes(), &approvalPayload); err != nil {
		t.Fatalf("unmarshal approvals: %v", err)
	}
	if len(approvalPayload.Items) < 4 {
		t.Fatalf("expected approvals, got %+v", approvalPayload.Items)
	}

	summaryReq := httptest.NewRequest(http.MethodGet, "/v1/control-plane/product/projections/summary", nil)
	summaryResp := httptest.NewRecorder()
	server.ServeHTTP(summaryResp, summaryReq)
	if summaryResp.Code != http.StatusOK {
		t.Fatalf("projection summary status=%d body=%s", summaryResp.Code, summaryResp.Body.String())
	}

	var summaryPayload map[string]any
	if err := json.Unmarshal(summaryResp.Body.Bytes(), &summaryPayload); err != nil {
		t.Fatalf("unmarshal projection summary: %v", err)
	}
	if summaryPayload["workflowCount"] == nil || summaryPayload["approvalCount"] == nil {
		t.Fatalf("unexpected projection summary: %+v", summaryPayload)
	}
}
