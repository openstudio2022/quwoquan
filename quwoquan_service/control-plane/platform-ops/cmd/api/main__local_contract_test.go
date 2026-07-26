package main

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	generatedcontrolplane "quwoquan_service/generated/control_plane"
	"quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	controlplanetest "quwoquan_service/runtime/controlplane/testsupport"
	"quwoquan_service/runtime/operation"
)

func requestAsTestPrincipal(request *http.Request, actor string) *http.Request {
	return request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
		Actor: operation.ActorContext{AccountID: actor},
	}))
}

func requestAsScopedOperator(request *http.Request, actor string, scopes ...string) *http.Request {
	return request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
		Claims: rtauth.Claims{
			Roles: []string{"operator"},
			Scope: strings.Join(scopes, " "),
		},
		Actor: operation.ActorContext{AccountID: actor},
	}))
}

func TestPlatformOperatorOIDCRequirementMatchesFourEnvironmentPolicy(t *testing.T) {
	for _, appEnv := range []string{"alpha", "beta", "gamma"} {
		if platformOperatorOIDCRequired(appEnv) {
			t.Fatalf("%s must not require external operator OIDC in non-production", appEnv)
		}
	}
	for _, appEnv := range []string{"prod", "staging", ""} {
		if !platformOperatorOIDCRequired(appEnv) {
			t.Fatalf("%q must fail closed when operator OIDC is absent", appEnv)
		}
	}
}

func newTestPlatformService(t *testing.T) *platformService {
	t.Helper()
	repoRoot := resolveRepoRoot()
	configLayer, configLayers := newTestConfigLayerComponents(t)
	service := &platformService{
		repoRoot: repoRoot, store: controlplanetest.NewFileStore(t.TempDir() + "/platform-ops-state.json"),
		configLayer: configLayer, configLayers: configLayers, health: func(context.Context) error { return nil },
	}
	if err := seedTestPlatformService(service); err != nil {
		t.Fatalf("seed platform test fixture: %v", err)
	}
	return service
}

func TestPlatformCatalogAndTopologyEndpoints(t *testing.T) {
	server := newServerMux(newTestPlatformService(t))

	catalogReq := httptest.NewRequest(http.MethodGet, "/control-plane/platform/catalog/services", nil)
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

	planeReq := httptest.NewRequest(http.MethodGet, "/control-plane/platform/topology/planes", nil)
	planeResp := httptest.NewRecorder()
	server.ServeHTTP(planeResp, planeReq)
	if planeResp.Code != http.StatusOK {
		t.Fatalf("plane bindings status=%d body=%s", planeResp.Code, planeResp.Body.String())
	}

	environmentReq := httptest.NewRequest(http.MethodGet, "/control-plane/platform/topology/environments", nil)
	environmentResp := httptest.NewRecorder()
	server.ServeHTTP(environmentResp, environmentReq)
	if environmentResp.Code != http.StatusOK {
		t.Fatalf("environment topologies status=%d body=%s", environmentResp.Code, environmentResp.Body.String())
	}
	var environmentPayload struct {
		Items []map[string]any `json:"items"`
	}
	if err := json.Unmarshal(environmentResp.Body.Bytes(), &environmentPayload); err != nil {
		t.Fatalf("unmarshal environment payload: %v", err)
	}
	if len(environmentPayload.Items) == 0 {
		t.Fatalf("expected environment topology items derived from autonomous deploy entries")
	}
}

// TestControlPlanePrincipalGate 守护生产授权边界：metadata codegen 描述符同时校验
// 已验证 operator principal 与 operation scope；客户端身份头不能越过该边界。
func TestControlPlanePrincipalGate(t *testing.T) {
	server := rtauth.RequireGeneratedOperationAuthorization(append(
		operationsecurity.ForDomain("ops"),
		generatedcontrolplane.PlatformOperationSecurityDescriptors...,
	))(newServerMux(newTestPlatformService(t)))

	anonReq := httptest.NewRequest(http.MethodGet, "/control-plane/platform/releases", nil)
	anonReq.Header.Set("X-Actor", "forged-platform-admin")
	anonResp := httptest.NewRecorder()
	server.ServeHTTP(anonResp, anonReq)
	if anonResp.Code != http.StatusUnauthorized {
		t.Fatalf("anonymous control-plane read must be rejected, got %d", anonResp.Code)
	}

	missingScopeReq := requestAsScopedOperator(
		httptest.NewRequest(http.MethodGet, "/control-plane/platform/releases", nil),
		"operator-1",
	)
	missingScopeResp := httptest.NewRecorder()
	server.ServeHTTP(missingScopeResp, missingScopeReq)
	if missingScopeResp.Code != http.StatusForbidden {
		t.Fatalf("operator without operation scope must be rejected, got %d", missingScopeResp.Code)
	}

	authedReq := requestAsScopedOperator(
		httptest.NewRequest(http.MethodGet, "/control-plane/platform/releases", nil),
		"operator-1",
		"ops.platform.rollout.read",
	)
	authedResp := httptest.NewRecorder()
	server.ServeHTTP(authedResp, authedReq)
	if authedResp.Code != http.StatusOK {
		t.Fatalf("verified principal must pass, got %d body=%s", authedResp.Code, authedResp.Body.String())
	}
}

// TestAlertIngestMachineCredentialGate 验证 Alertmanager 专用机器凭据与 operator
// OIDC 路径物理分离，缺配置或 token 不匹配时均 fail-closed。
func TestAlertIngestMachineCredentialGate(t *testing.T) {
	server := requireControlPlanePrincipal(newServerMux(newTestPlatformService(t)))

	payload := `{"version":"4","status":"firing","alerts":[{"status":"firing","labels":{"alertname":"A"},"annotations":{},"fingerprint":"fp-gate-1"}]}`
	t.Setenv("ALERT_INGEST_TOKEN", "")
	missingTokenResp := httptest.NewRecorder()
	missingTokenReq := httptest.NewRequest(http.MethodPost, "/control-plane/platform/alerts/ingest", bytes.NewBufferString(payload))
	server.ServeHTTP(missingTokenResp, missingTokenReq)
	if missingTokenResp.Code != http.StatusInternalServerError {
		t.Fatalf("missing ALERT_INGEST_TOKEN must fail closed, got %d", missingTokenResp.Code)
	}

	t.Setenv("ALERT_INGEST_TOKEN", "secret-token")
	wrongTokenResp := httptest.NewRecorder()
	wrongTokenReq := httptest.NewRequest(http.MethodPost, "/control-plane/platform/alerts/ingest", bytes.NewBufferString(payload))
	wrongTokenReq.Header.Set(alertIngestTokenHeader, "wrong")
	server.ServeHTTP(wrongTokenResp, wrongTokenReq)
	if wrongTokenResp.Code != http.StatusUnauthorized {
		t.Fatalf("wrong ingest token must be rejected, got %d", wrongTokenResp.Code)
	}

	okResp := httptest.NewRecorder()
	okReq := httptest.NewRequest(http.MethodPost, "/control-plane/platform/alerts/ingest", bytes.NewBufferString(payload))
	okReq.Header.Set(alertIngestTokenHeader, "secret-token")
	okReq.Header.Set("Content-Type", "application/json")
	server.ServeHTTP(okResp, okReq)
	if okResp.Code != http.StatusOK {
		t.Fatalf("valid ingest token must pass, got %d body=%s", okResp.Code, okResp.Body.String())
	}
}

// TestPlatformRetiredSkeletonRoutesAreAbsent 反向守护：恒空 namespace 的骨架
// 端点（governance/runbooks/gates/observability 文档/packages/dependencies）
// 必须保持退场，防止无生产者的假数据面回潮。
func TestPlatformRetiredSkeletonRoutesAreAbsent(t *testing.T) {
	server := newServerMux(newTestPlatformService(t))
	for _, path := range []string{
		"/control-plane/platform/governance/templates",
		"/control-plane/platform/governance/bindings",
		"/control-plane/platform/observability/slos",
		"/control-plane/platform/observability/alerts",
		"/control-plane/platform/observability/dashboards/cards",
		"/control-plane/platform/runbooks",
		"/control-plane/platform/gates",
		"/control-plane/platform/configs/packages",
		"/control-plane/platform/topology/dependencies",
		"/control-plane/platform/topology/capacity",
	} {
		req := httptest.NewRequest(http.MethodGet, path, nil)
		resp := httptest.NewRecorder()
		server.ServeHTTP(resp, req)
		// 精确路由消失后返回 mux 404；命中 /configs/ 前缀守卫时返回结构化
		// route-not-found（HTTP 400）。两者都证明骨架端点没有数据面。
		if resp.Code != http.StatusNotFound && resp.Code != http.StatusBadRequest {
			t.Fatalf("retired route %s must be absent, got %d", path, resp.Code)
		}
	}
}

// TestPlatformAlertIngestAckLoopEmitsAudit 守护 Alertmanager 回流闭环：
// webhook ingest 建立活动告警 → 值班 ack 落审计 → resolved 归档，
// projection summary 的 activeAlerts 与状态机同步。
func TestPlatformAlertIngestAckLoopEmitsAudit(t *testing.T) {
	server := newServerMux(newTestPlatformService(t))

	firingPayload := `{"version":"4","groupKey":"{}:{alertname=\"HTTPErrorRateHigh\"}","status":"firing","alerts":[{"status":"firing","labels":{"alertname":"HTTPErrorRateHigh","severity":"critical","service":"content-service"},"annotations":{"summary":"5xx too high"},"startsAt":"2026-07-19T08:00:00Z","fingerprint":"fp-http-error-1"}]}`
	ingestReq := httptest.NewRequest(http.MethodPost, "/control-plane/platform/alerts/ingest", bytes.NewBufferString(firingPayload))
	ingestReq.Header.Set("Content-Type", "application/json")
	ingestResp := httptest.NewRecorder()
	server.ServeHTTP(ingestResp, ingestReq)
	if ingestResp.Code != http.StatusOK {
		t.Fatalf("ingest alert status=%d body=%s", ingestResp.Code, ingestResp.Body.String())
	}

	activeReq := httptest.NewRequest(http.MethodGet, "/control-plane/platform/alerts/active", nil)
	activeResp := httptest.NewRecorder()
	server.ServeHTTP(activeResp, activeReq)
	if activeResp.Code != http.StatusOK {
		t.Fatalf("list active alerts status=%d body=%s", activeResp.Code, activeResp.Body.String())
	}
	var activePayload struct {
		Items []map[string]any `json:"items"`
	}
	if err := json.Unmarshal(activeResp.Body.Bytes(), &activePayload); err != nil {
		t.Fatalf("unmarshal active alerts: %v", err)
	}
	if len(activePayload.Items) != 1 || activePayload.Items[0]["status"] != "firing" {
		t.Fatalf("expected one firing alert, got %+v", activePayload.Items)
	}

	ackReq := httptest.NewRequest(http.MethodPost, "/control-plane/platform/alerts/fp-http-error-1:ack", nil)
	ackReq = requestAsTestPrincipal(ackReq, "oncall-1")
	ackResp := httptest.NewRecorder()
	server.ServeHTTP(ackResp, ackReq)
	if ackResp.Code != http.StatusOK {
		t.Fatalf("ack alert status=%d body=%s", ackResp.Code, ackResp.Body.String())
	}
	var ackPayload map[string]any
	if err := json.Unmarshal(ackResp.Body.Bytes(), &ackPayload); err != nil {
		t.Fatalf("unmarshal ack payload: %v", err)
	}
	if ackPayload["status"] != "acknowledged" || ackPayload["ackedBy"] != "oncall-1" {
		t.Fatalf("expected acknowledged by oncall-1, got %+v", ackPayload)
	}

	// 同一 firing 周期内的重复推送不得覆盖 ack 状态。
	repeatResp := httptest.NewRecorder()
	repeatReq := httptest.NewRequest(http.MethodPost, "/control-plane/platform/alerts/ingest", bytes.NewBufferString(firingPayload))
	repeatReq.Header.Set("Content-Type", "application/json")
	server.ServeHTTP(repeatResp, repeatReq)
	if repeatResp.Code != http.StatusOK {
		t.Fatalf("repeat ingest status=%d body=%s", repeatResp.Code, repeatResp.Body.String())
	}
	ackedListResp := httptest.NewRecorder()
	server.ServeHTTP(ackedListResp, httptest.NewRequest(http.MethodGet, "/control-plane/platform/alerts/active?status=acknowledged", nil))
	var ackedPayload struct {
		Items []map[string]any `json:"items"`
	}
	if err := json.Unmarshal(ackedListResp.Body.Bytes(), &ackedPayload); err != nil {
		t.Fatalf("unmarshal acked alerts: %v", err)
	}
	if len(ackedPayload.Items) != 1 {
		t.Fatalf("repeated firing push must keep acknowledged state, got %+v", ackedPayload.Items)
	}

	auditReq := httptest.NewRequest(http.MethodGet, "/control-plane/platform/audits", nil)
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
	foundAck := false
	for _, item := range auditPayload.Items {
		if item["action"] == "alert_acknowledged" {
			foundAck = true
		}
	}
	if !foundAck {
		t.Fatalf("expected alert_acknowledged audit event, got %+v", auditPayload.Items)
	}

	projectionReq := httptest.NewRequest(http.MethodGet, "/control-plane/platform/projections/summary", nil)
	projectionResp := httptest.NewRecorder()
	server.ServeHTTP(projectionResp, projectionReq)
	if projectionResp.Code != http.StatusOK {
		t.Fatalf("projection summary status=%d body=%s", projectionResp.Code, projectionResp.Body.String())
	}
	var projectionPayload struct {
		ActiveAlerts int `json:"activeAlerts"`
	}
	if err := json.Unmarshal(projectionResp.Body.Bytes(), &projectionPayload); err != nil {
		t.Fatalf("unmarshal projection summary: %v", err)
	}
	if projectionPayload.ActiveAlerts != 1 {
		t.Fatalf("expected 1 active alert in projection summary, got %d", projectionPayload.ActiveAlerts)
	}

	resolvedPayload := `{"version":"4","groupKey":"{}:{alertname=\"HTTPErrorRateHigh\"}","status":"resolved","alerts":[{"status":"resolved","labels":{"alertname":"HTTPErrorRateHigh","severity":"critical","service":"content-service"},"annotations":{"summary":"5xx recovered"},"startsAt":"2026-07-19T08:00:00Z","endsAt":"2026-07-19T08:30:00Z","fingerprint":"fp-http-error-1"}]}`
	resolvedResp := httptest.NewRecorder()
	resolvedReq := httptest.NewRequest(http.MethodPost, "/control-plane/platform/alerts/ingest", bytes.NewBufferString(resolvedPayload))
	resolvedReq.Header.Set("Content-Type", "application/json")
	server.ServeHTTP(resolvedResp, resolvedReq)
	if resolvedResp.Code != http.StatusOK {
		t.Fatalf("resolved ingest status=%d body=%s", resolvedResp.Code, resolvedResp.Body.String())
	}
	finalProjectionResp := httptest.NewRecorder()
	server.ServeHTTP(finalProjectionResp, httptest.NewRequest(http.MethodGet, "/control-plane/platform/projections/summary", nil))
	var finalProjection struct {
		ActiveAlerts int `json:"activeAlerts"`
	}
	if err := json.Unmarshal(finalProjectionResp.Body.Bytes(), &finalProjection); err != nil {
		t.Fatalf("unmarshal final projection summary: %v", err)
	}
	if finalProjection.ActiveAlerts != 0 {
		t.Fatalf("resolved alert must leave active set, got %d", finalProjection.ActiveAlerts)
	}
}

func TestPlatformGrayRoutingPolicyIsReadOnlySnapshot(t *testing.T) {
	server := newServerMux(newTestPlatformService(t))

	getReq := httptest.NewRequest(http.MethodGet, "/control-plane/platform/rollout/routing-policy", nil)
	getResp := httptest.NewRecorder()
	server.ServeHTTP(getResp, getReq)
	if getResp.Code != http.StatusOK {
		t.Fatalf("gray routing policy status=%d body=%s", getResp.Code, getResp.Body.String())
	}
	var payload struct {
		Policy struct {
			Enabled         bool `json:"enabled"`
			StageDimensions map[string]struct {
				AppVersions []string `json:"appVersions"`
				UserIDs     []string `json:"userIds"`
				Provinces   []string `json:"provinces"`
				Carriers    []string `json:"carriers"`
			} `json:"stageDimensions"`
		} `json:"policy"`
		SourcePath string `json:"sourcePath"`
		RawYaml    string `json:"rawYaml"`
	}
	if err := json.Unmarshal(getResp.Body.Bytes(), &payload); err != nil {
		t.Fatalf("unmarshal gray routing policy: %v", err)
	}
	if payload.SourcePath == "" || payload.RawYaml == "" {
		t.Fatalf("policy must expose IaC source path and raw yaml: %+v", payload)
	}
	for _, stage := range []string{"gray-initial", "carry-on", "full"} {
		dimensions, exists := payload.Policy.StageDimensions[stage]
		if !exists || dimensions.AppVersions == nil || dimensions.UserIDs == nil ||
			dimensions.Provinces == nil || dimensions.Carriers == nil {
			t.Fatalf(
				"policy must expose all four stageDimensions for %s: %s",
				stage,
				getResp.Body.String(),
			)
		}
	}

	postReq := httptest.NewRequest(http.MethodPost, "/control-plane/platform/rollout/routing-policy", nil)
	postResp := httptest.NewRecorder()
	server.ServeHTTP(postResp, postReq)
	if postResp.Code == http.StatusOK {
		t.Fatalf("gray routing policy must be read-only, POST got 200")
	}
}

func TestPlatformConfigResolveAndInstanceReports(t *testing.T) {
	server := newServerMux(newTestPlatformService(t))

	resolveReq := httptest.NewRequest(
		http.MethodGet,
		"/control-plane/platform/configs/resolve?env=beta&service=product-ops-service",
		nil,
	)
	resolveResp := httptest.NewRecorder()
	server.ServeHTTP(resolveResp, resolveReq)
	if resolveResp.Code != http.StatusOK {
		t.Fatalf("resolve config status=%d body=%s", resolveResp.Code, resolveResp.Body.String())
	}

	var resolvePayload struct {
		EffectiveHash string           `json:"effectiveHash"`
		DesiredHash   string           `json:"desiredHash"`
		Source        string           `json:"source"`
		Values        []map[string]any `json:"values"`
	}
	if err := json.Unmarshal(resolveResp.Body.Bytes(), &resolvePayload); err != nil {
		t.Fatalf("unmarshal resolve payload: %v", err)
	}
	if resolvePayload.EffectiveHash == "" || resolvePayload.DesiredHash == "" {
		t.Fatalf("expected effective+desired hash, got %+v", resolvePayload)
	}
	if resolvePayload.Source != "release-package" {
		t.Fatalf("resolve source must be release-package, got %q", resolvePayload.Source)
	}
	if len(resolvePayload.Values) == 0 {
		t.Fatalf("expected resolved values")
	}

	reportReq := httptest.NewRequest(
		http.MethodPost,
		"/control-plane/platform/configs/instances/product-ops-service-beta-control-a-0:report",
		bytes.NewBufferString(`{"environment":"beta","cluster":"beta-control-a","service":"product-ops-service","desiredHash":"hash-a","effectiveHash":"hash-b","source":"disk-fallback"}`),
	)
	reportReq.Header.Set("Content-Type", "application/json")
	reportResp := httptest.NewRecorder()
	server.ServeHTTP(reportResp, reportReq)
	if reportResp.Code != http.StatusOK {
		t.Fatalf("report config instance status=%d body=%s", reportResp.Code, reportResp.Body.String())
	}

	instancesReq := httptest.NewRequest(http.MethodGet, "/control-plane/platform/configs/instances", nil)
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

func TestPlatformReleaseMutationsAreRetired(t *testing.T) {
	server := newServerMux(newTestPlatformService(t))
	for _, suffix := range []string{":apply", ":rollback"} {
		request := requestAsTestPrincipal(
			httptest.NewRequest(
				http.MethodPost,
				"/control-plane/platform/releases/v2026.02.28.0"+suffix,
				bytes.NewBufferString(`{"service":"content-service"}`),
			),
			"platform-admin",
		)
		response := httptest.NewRecorder()
		server.ServeHTTP(response, request)
		if response.Code != http.StatusNotFound {
			t.Fatalf("retired release mutation %s status=%d body=%s", suffix, response.Code, response.Body.String())
		}
	}
}

func TestPlatformTriageSummaryEndpointIncludesBacklogRepairSemantics(t *testing.T) {
	server := newServerMux(newTestPlatformService(t))

	req := httptest.NewRequest(http.MethodGet, "/control-plane/platform/triage/summary?env=beta&cluster=beta-control-a&service=platform-ops-service", nil)
	resp := httptest.NewRecorder()
	server.ServeHTTP(resp, req)
	if resp.Code != http.StatusOK {
		t.Fatalf("platform triage status=%d body=%s", resp.Code, resp.Body.String())
	}

	var payload struct {
		BacklogCandidates []struct {
			ID             string `json:"id"`
			DrilldownRoute string `json:"drilldownRoute"`
			RepairEntry    string `json:"repairEntry"`
			AlertID        string `json:"alertId"`
			AuditRoute     string `json:"auditRoute"`
		} `json:"backlogCandidates"`
	}
	if err := json.Unmarshal(resp.Body.Bytes(), &payload); err != nil {
		t.Fatalf("unmarshal platform triage payload: %v", err)
	}
	if len(payload.BacklogCandidates) == 0 {
		t.Fatalf("expected platform backlog candidates, got none")
	}
	first := payload.BacklogCandidates[0]
	if first.DrilldownRoute == "" || first.RepairEntry == "" || first.AlertID == "" || first.AuditRoute == "" {
		t.Fatalf("expected backlog repair semantics, got %+v", first)
	}
}
