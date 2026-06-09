package main

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"testing"

	"quwoquan_service/runtime/controlplane"
	rthealth "quwoquan_service/runtime/health"
	"quwoquan_service/services/product-ops-service/internal/application"
	telemetrypersistence "quwoquan_service/services/product-ops-service/internal/infrastructure/persistence"
)

func newTestProductService(t *testing.T) *productService {
	t.Helper()
	return newProductService(
		controlplane.NewFileStore(filepath.Join(t.TempDir(), "product-ops-state.json")),
		application.NewTelemetryService(telemetrypersistence.NewMemoryTelemetryStore(), nil),
	)
}

func newTestServerMux(service *productService) *http.ServeMux {
	return newServerMux(service, rthealth.NewChecker())
}

func TestExperimentEndpoints(t *testing.T) {
	service := newTestProductService(t)
	if err := service.seed(); err != nil {
		t.Fatalf("seed service: %v", err)
	}
	server := newTestServerMux(service)

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
	service := newTestProductService(t)
	if err := service.seed(); err != nil {
		t.Fatalf("seed service: %v", err)
	}
	server := newTestServerMux(service)

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

func TestEventEndpoints(t *testing.T) {
	service := newTestProductService(t)
	if err := service.seed(); err != nil {
		t.Fatalf("seed service: %v", err)
	}
	server := newTestServerMux(service)

	body := bytes.NewBufferString(`{"events":[{"eventId":"evt-1","eventType":"experience","eventName":"page_open","eventVersion":"v1","priority":"P0","producer":"app","pageName":"home","surfaceId":"homeFeed","routeId":"home","occurredAt":"2026-04-01T00:00:00Z","payload":{"location":"/home"}},{"eventId":"evt-2","eventType":"analytics","eventName":"bottom_nav_tap","eventVersion":"v1","priority":"P1","producer":"app","pageName":"home","surfaceId":"homeFeed","routeId":"home","experimentBucket":"control","occurredAt":"2026-04-01T00:00:05Z"}]}`)
	req := httptest.NewRequest(http.MethodPost, "/v1/ops/events", body)
	req.Header.Set("Content-Type", "application/json")
	resp := httptest.NewRecorder()
	server.ServeHTTP(resp, req)
	if resp.Code != http.StatusOK {
		t.Fatalf("report events status=%d body=%s", resp.Code, resp.Body.String())
	}

	summaryReq := httptest.NewRequest(http.MethodGet, "/v1/ops/events/summary?pageName=home", nil)
	summaryResp := httptest.NewRecorder()
	server.ServeHTTP(summaryResp, summaryReq)
	if summaryResp.Code != http.StatusOK {
		t.Fatalf("event summary status=%d body=%s", summaryResp.Code, summaryResp.Body.String())
	}
	var summary struct {
		TotalCount int64                       `json:"totalCount"`
		Dimensions map[string]map[string]int64 `json:"dimensions"`
	}
	if err := json.Unmarshal(summaryResp.Body.Bytes(), &summary); err != nil {
		t.Fatalf("unmarshal event summary: %v", err)
	}
	if summary.TotalCount != 2 {
		t.Fatalf("expected totalCount=2, got %d", summary.TotalCount)
	}
	if got := summary.Dimensions["pageName"]["home"]; got != 2 {
		t.Fatalf("expected pageName.home=2, got %d", got)
	}

	drilldownReq := httptest.NewRequest(http.MethodGet, "/v1/ops/events/drilldown?eventType=analytics", nil)
	drilldownResp := httptest.NewRecorder()
	server.ServeHTTP(drilldownResp, drilldownReq)
	if drilldownResp.Code != http.StatusOK {
		t.Fatalf("event drilldown status=%d body=%s", drilldownResp.Code, drilldownResp.Body.String())
	}
	var drilldown struct {
		TotalCount int64 `json:"totalCount"`
		Items      []struct {
			EventID   string `json:"eventId"`
			EventName string `json:"eventName"`
		} `json:"items"`
	}
	if err := json.Unmarshal(drilldownResp.Body.Bytes(), &drilldown); err != nil {
		t.Fatalf("unmarshal event drilldown: %v", err)
	}
	if drilldown.TotalCount != 1 || len(drilldown.Items) != 1 || drilldown.Items[0].EventID != "evt-2" {
		t.Fatalf("unexpected drilldown payload: %+v", drilldown)
	}
}

func TestControlPlaneWorkflowEndpoints(t *testing.T) {
	service := newTestProductService(t)
	if err := service.seed(); err != nil {
		t.Fatalf("seed service: %v", err)
	}
	server := newTestServerMux(service)

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
	if cards, ok := summaryPayload["l1l4Cards"].([]any); !ok || len(cards) == 0 {
		t.Fatalf("expected l1l4 cards, got %+v", summaryPayload["l1l4Cards"])
	}
}

func TestL1L4MetricsEndpoint(t *testing.T) {
	service := newTestProductService(t)
	if err := service.seed(); err != nil {
		t.Fatalf("seed service: %v", err)
	}
	server := newTestServerMux(service)

	recordReq := httptest.NewRequest(http.MethodPost, "/v1/ops/events", bytes.NewBufferString(`{
		"events": [
			{"eventId":"evt-l3-latency","eventType":"experience","eventName":"page_return_perf","occurredAt":"2026-06-07T08:00:01Z","pageName":"home","surfaceId":"homeFeed","metrics":{"durationMs":1300}},
			{"eventId":"evt-l3-error","eventType":"experience","eventName":"request_failed","occurredAt":"2026-06-07T08:00:02Z","pageName":"home","surfaceId":"homeFeed","errorCode":"OPS.NETWORK.timeout"}
		]
	}`))
	recordReq.Header.Set("Content-Type", "application/json")
	recordResp := httptest.NewRecorder()
	server.ServeHTTP(recordResp, recordReq)
	if recordResp.Code != http.StatusOK {
		t.Fatalf("record metrics events status=%d body=%s", recordResp.Code, recordResp.Body.String())
	}

	req := httptest.NewRequest(http.MethodGet, "/v1/control-plane/product/metrics/l1l4?env=beta&level=L3", nil)
	resp := httptest.NewRecorder()
	server.ServeHTTP(resp, req)
	if resp.Code != http.StatusOK {
		t.Fatalf("l1l4 metrics status=%d body=%s", resp.Code, resp.Body.String())
	}

	var payload struct {
		Source    string `json:"source"`
		Freshness string `json:"freshness"`
		Window    string `json:"window"`
		Coverage  struct {
			TotalMetrics    int `json:"totalMetrics"`
			LiveMetrics     int `json:"liveMetrics"`
			FallbackMetrics int `json:"fallbackMetrics"`
			EventSignals    int `json:"eventSignals"`
		} `json:"coverage"`
		Alerts []struct {
			ID          string `json:"id"`
			State       string `json:"state"`
			Metric      string `json:"metric"`
			Source      string `json:"source"`
			RunbookID   string `json:"runbookId"`
			RunbookRoute string `json:"runbookRoute"`
			RepairEntry string `json:"repairEntry"`
			AlertID     string `json:"alertId"`
			Owner       string `json:"owner"`
		} `json:"alerts"`
		Items []struct {
			Level       string `json:"level"`
			Environment string `json:"environment"`
			Metric      string `json:"metric"`
			Source      string `json:"source"`
		} `json:"items"`
	}
	if err := json.Unmarshal(resp.Body.Bytes(), &payload); err != nil {
		t.Fatalf("unmarshal l1l4 metrics: %v", err)
	}
	if payload.Source == "" || payload.Freshness == "" || payload.Window == "" {
		t.Fatalf("expected live metadata, got %+v", payload)
	}
	if payload.Coverage.TotalMetrics == 0 {
		t.Fatalf("expected coverage totals, got %+v", payload.Coverage)
	}
	if len(payload.Items) == 0 {
		t.Fatalf("expected l1l4 metric items")
	}
	for _, item := range payload.Items {
		if item.Level != "L3" {
			t.Fatalf("expected only L3 items, got %+v", payload.Items)
		}
		if item.Environment != "beta" {
			t.Fatalf("expected beta environment, got %+v", payload.Items)
		}
		if item.Source == "" {
			t.Fatalf("expected metric source, got %+v", payload.Items)
		}
	}
	if len(payload.Alerts) == 0 {
		t.Fatalf("expected derived alerts, got %+v", payload)
	}
	if payload.Alerts[0].RunbookRoute == "" || payload.Alerts[0].RepairEntry == "" || payload.Alerts[0].AlertID == "" || payload.Alerts[0].Owner == "" {
		t.Fatalf("expected alert repair semantics, got %+v", payload.Alerts[0])
	}
}

func TestProductTriageSummaryEndpoint(t *testing.T) {
	service := newTestProductService(t)
	if err := service.seed(); err != nil {
		t.Fatalf("seed service: %v", err)
	}
	server := newTestServerMux(service)

	recordReq := httptest.NewRequest(http.MethodPost, "/v1/ops/events", bytes.NewBufferString(`{
		"events": [
			{"eventId":"evt-open","eventType":"experience","eventName":"page_open","occurredAt":"2026-06-07T08:00:00Z","pageName":"home"},
			{"eventId":"evt-perf","eventType":"experience","eventName":"page_return_perf","occurredAt":"2026-06-07T08:00:01Z","pageName":"home","surfaceId":"homeFeed","payload":{"durationMs":1300}}
		]
	}`))
	recordReq.Header.Set("Content-Type", "application/json")
	recordResp := httptest.NewRecorder()
	server.ServeHTTP(recordResp, recordReq)
	if recordResp.Code != http.StatusOK {
		t.Fatalf("record events status=%d body=%s", recordResp.Code, recordResp.Body.String())
	}

	req := httptest.NewRequest(http.MethodGet, "/v1/control-plane/product/triage/summary?pageName=home&surfaceId=homeFeed", nil)
	resp := httptest.NewRecorder()
	server.ServeHTTP(resp, req)
	if resp.Code != http.StatusOK {
		t.Fatalf("product triage summary status=%d body=%s", resp.Code, resp.Body.String())
	}

	var payload struct {
		EventSummary struct {
			TotalCount int `json:"totalCount"`
		} `json:"eventSummary"`
		RecentEvents []struct {
			EventID   string `json:"eventId"`
			PageName  string `json:"pageName"`
			SurfaceID string `json:"surfaceId"`
		} `json:"recentEvents"`
		BacklogCandidates []struct {
			ID            string `json:"id"`
			Category      string `json:"category"`
			Title         string `json:"title"`
			NextAction    string `json:"nextAction"`
			RunbookRoute  string `json:"runbookRoute"`
			RepairEntry   string `json:"repairEntry"`
			AlertID       string `json:"alertId"`
			AuditRoute    string `json:"auditRoute"`
		} `json:"backlogCandidates"`
		RuntimeReady bool   `json:"runtimeReady"`
		Source       string `json:"source"`
	}
	if err := json.Unmarshal(resp.Body.Bytes(), &payload); err != nil {
		t.Fatalf("unmarshal product triage summary: %v", err)
	}
	if payload.Source == "" {
		t.Fatalf("expected triage source, got %+v", payload)
	}
	if payload.EventSummary.TotalCount == 0 {
		t.Fatalf("expected event summary counts, got %+v", payload)
	}
	if len(payload.RecentEvents) == 0 {
		t.Fatalf("expected recent events, got %+v", payload)
	}
	if len(payload.BacklogCandidates) == 0 {
		t.Fatalf("expected backlog candidates, got %+v", payload)
	}
	if payload.BacklogCandidates[0].ID == "" || payload.BacklogCandidates[0].NextAction == "" || payload.BacklogCandidates[0].RunbookRoute == "" || payload.BacklogCandidates[0].RepairEntry == "" || payload.BacklogCandidates[0].AlertID == "" || payload.BacklogCandidates[0].AuditRoute == "" {
		t.Fatalf("expected backlog candidate details, got %+v", payload.BacklogCandidates[0])
	}
}
