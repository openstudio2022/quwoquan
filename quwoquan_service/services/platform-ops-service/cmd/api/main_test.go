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

func newTestPlatformService(t *testing.T) *platformService {
	t.Helper()
	repoRoot := filepath.Clean(filepath.Join("..", "..", "..", "..", ".."))
	service := &platformService{
		repoRoot: repoRoot,
		store:    controlplane.NewFileStore(filepath.Join(t.TempDir(), "platform-ops-state.json")),
	}
	if err := service.seed(); err != nil {
		t.Fatalf("seed platform service: %v", err)
	}
	return service
}

func TestPlatformCatalogAndTopologyEndpoints(t *testing.T) {
	server := newServerMux(newTestPlatformService(t))

	catalogReq := httptest.NewRequest(http.MethodGet, "/v1/control-plane/platform/catalog/services", nil)
	catalogResp := httptest.NewRecorder()
	server.ServeHTTP(catalogResp, catalogReq)
	if catalogResp.Code != http.StatusOK {
		t.Fatalf("catalog status=%d body=%s", catalogResp.Code, catalogResp.Body.String())
	}

	var catalogPayload struct {
		Items []map[string]any `json:"items"`
	}
	if err := json.Unmarshal(catalogResp.Body.Bytes(), &catalogPayload); err != nil {
		t.Fatalf("unmarshal catalog payload: %v", err)
	}
	if len(catalogPayload.Items) == 0 {
		t.Fatalf("expected catalog items")
	}

	onboardingReq := httptest.NewRequest(http.MethodGet, "/v1/control-plane/platform/onboarding/domains", nil)
	onboardingResp := httptest.NewRecorder()
	server.ServeHTTP(onboardingResp, onboardingReq)
	if onboardingResp.Code != http.StatusOK {
		t.Fatalf("onboarding status=%d body=%s", onboardingResp.Code, onboardingResp.Body.String())
	}

	planeReq := httptest.NewRequest(http.MethodGet, "/v1/control-plane/platform/topology/planes", nil)
	planeResp := httptest.NewRecorder()
	server.ServeHTTP(planeResp, planeReq)
	if planeResp.Code != http.StatusOK {
		t.Fatalf("plane bindings status=%d body=%s", planeResp.Code, planeResp.Body.String())
	}

	templateReq := httptest.NewRequest(http.MethodGet, "/v1/control-plane/platform/governance/templates", nil)
	templateResp := httptest.NewRecorder()
	server.ServeHTTP(templateResp, templateReq)
	if templateResp.Code != http.StatusOK {
		t.Fatalf("governance templates status=%d body=%s", templateResp.Code, templateResp.Body.String())
	}
}

func TestPlatformMutableEndpointsEmitAudit(t *testing.T) {
	server := newServerMux(newTestPlatformService(t))

	configReq := httptest.NewRequest(http.MethodPost, "/v1/control-plane/platform/configs/sys.gateway.timeout.default:update", bytes.NewBufferString(`{"value":900,"status":"warning"}`))
	configReq.Header.Set("Content-Type", "application/json")
	configReq.Header.Set("X-Actor", "platform-admin")
	configResp := httptest.NewRecorder()
	server.ServeHTTP(configResp, configReq)
	if configResp.Code != http.StatusOK {
		t.Fatalf("update config status=%d body=%s", configResp.Code, configResp.Body.String())
	}

	runbookReq := httptest.NewRequest(http.MethodPost, "/v1/control-plane/platform/runbooks/cfg-rollback-drill:runDrill", nil)
	runbookReq.Header.Set("X-Actor", "platform-admin")
	runbookResp := httptest.NewRecorder()
	server.ServeHTTP(runbookResp, runbookReq)
	if runbookResp.Code != http.StatusOK {
		t.Fatalf("run drill status=%d body=%s", runbookResp.Code, runbookResp.Body.String())
	}

	gateReq := httptest.NewRequest(http.MethodPost, "/v1/control-plane/platform/gates/config_release_error_rate:override", bytes.NewBufferString(`{"status":"warning","summary":"manual override"}`))
	gateReq.Header.Set("Content-Type", "application/json")
	gateReq.Header.Set("X-Actor", "platform-admin")
	gateResp := httptest.NewRecorder()
	server.ServeHTTP(gateResp, gateReq)
	if gateResp.Code != http.StatusOK {
		t.Fatalf("override gate status=%d body=%s", gateResp.Code, gateResp.Body.String())
	}

	auditReq := httptest.NewRequest(http.MethodGet, "/v1/control-plane/platform/audits", nil)
	auditResp := httptest.NewRecorder()
	server.ServeHTTP(auditResp, auditReq)
	if auditResp.Code != http.StatusOK {
		t.Fatalf("audit status=%d body=%s", auditResp.Code, auditResp.Body.String())
	}

	var auditPayload struct {
		Items []map[string]any `json:"items"`
	}
	if err := json.Unmarshal(auditResp.Body.Bytes(), &auditPayload); err != nil {
		t.Fatalf("unmarshal audit payload: %v", err)
	}
	if len(auditPayload.Items) < 3 {
		t.Fatalf("expected audit items, got %+v", auditPayload.Items)
	}

	approvalReq := httptest.NewRequest(http.MethodGet, "/v1/control-plane/platform/approvals", nil)
	approvalResp := httptest.NewRecorder()
	server.ServeHTTP(approvalResp, approvalReq)
	if approvalResp.Code != http.StatusOK {
		t.Fatalf("approvals status=%d body=%s", approvalResp.Code, approvalResp.Body.String())
	}

	var approvalPayload struct {
		Items []map[string]any `json:"items"`
	}
	if err := json.Unmarshal(approvalResp.Body.Bytes(), &approvalPayload); err != nil {
		t.Fatalf("unmarshal approvals: %v", err)
	}
	if len(approvalPayload.Items) < 3 {
		t.Fatalf("expected approval items, got %+v", approvalPayload.Items)
	}

	projectionReq := httptest.NewRequest(http.MethodGet, "/v1/control-plane/platform/projections/summary", nil)
	projectionResp := httptest.NewRecorder()
	server.ServeHTTP(projectionResp, projectionReq)
	if projectionResp.Code != http.StatusOK {
		t.Fatalf("projection summary status=%d body=%s", projectionResp.Code, projectionResp.Body.String())
	}
}

func TestPlatformConfigResolveAndInstanceReports(t *testing.T) {
	server := newServerMux(newTestPlatformService(t))

	resolveReq := httptest.NewRequest(
		http.MethodGet,
		"/v1/control-plane/platform/configs/resolve?env=beta&cluster=beta-control-a&service=product-ops-service&instance=product-ops-service-beta-control-a-0",
		nil,
	)
	resolveResp := httptest.NewRecorder()
	server.ServeHTTP(resolveResp, resolveReq)
	if resolveResp.Code != http.StatusOK {
		t.Fatalf("resolve config status=%d body=%s", resolveResp.Code, resolveResp.Body.String())
	}

	var resolvePayload struct {
		EffectiveHash string            `json:"effectiveHash"`
		DesiredHash   string            `json:"desiredHash"`
		Values        []map[string]any  `json:"values"`
		Scope         map[string]string `json:"scope"`
	}
	if err := json.Unmarshal(resolveResp.Body.Bytes(), &resolvePayload); err != nil {
		t.Fatalf("unmarshal resolve payload: %v", err)
	}
	if resolvePayload.EffectiveHash == "" {
		t.Fatalf("expected effective hash, got %+v", resolvePayload)
	}
	if resolvePayload.DesiredHash == "" {
		t.Fatalf("expected desired hash, got %+v", resolvePayload)
	}
	if len(resolvePayload.Values) == 0 {
		t.Fatalf("expected resolved values")
	}
	if got := resolvePayload.Scope["Environment"]; got != "beta" {
		t.Fatalf("expected environment beta, got %+v", resolvePayload.Scope)
	}

	reportReq := httptest.NewRequest(
		http.MethodPost,
		"/v1/control-plane/platform/configs/instances/product-ops-service-beta-control-a-0:report",
		bytes.NewBufferString(`{"environment":"beta","cluster":"beta-control-a","service":"product-ops-service","desiredHash":"hash-a","effectiveHash":"hash-b","source":"disk-fallback"}`),
	)
	reportReq.Header.Set("Content-Type", "application/json")
	reportResp := httptest.NewRecorder()
	server.ServeHTTP(reportResp, reportReq)
	if reportResp.Code != http.StatusOK {
		t.Fatalf("report config instance status=%d body=%s", reportResp.Code, reportResp.Body.String())
	}

	instancesReq := httptest.NewRequest(http.MethodGet, "/v1/control-plane/platform/configs/instances", nil)
	instancesResp := httptest.NewRecorder()
	server.ServeHTTP(instancesResp, instancesReq)
	if instancesResp.Code != http.StatusOK {
		t.Fatalf("list config instances status=%d body=%s", instancesResp.Code, instancesResp.Body.String())
	}

	var instancePayload struct {
		Items   []map[string]any `json:"items"`
		Summary map[string]any   `json:"summary"`
	}
	if err := json.Unmarshal(instancesResp.Body.Bytes(), &instancePayload); err != nil {
		t.Fatalf("unmarshal config instance payload: %v", err)
	}
	if len(instancePayload.Items) == 0 {
		t.Fatalf("expected config instance items")
	}
	if _, ok := instancePayload.Summary["outOfSyncInstances"]; !ok {
		t.Fatalf("expected drift summary, got %+v", instancePayload.Summary)
	}
}
