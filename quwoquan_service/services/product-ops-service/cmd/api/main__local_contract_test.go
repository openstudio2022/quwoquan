package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strconv"
	"strings"
	"testing"
	"time"

	generatedcontrolplane "quwoquan_service/generated/control_plane"
	"quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/controlplane"
	controlplanetest "quwoquan_service/runtime/controlplane/testsupport"
	rthealth "quwoquan_service/runtime/health"
	messaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/runtime/operation"
	"quwoquan_service/services/product-ops-service/internal/application"
	telemetrypersistence "quwoquan_service/services/product-ops-service/internal/infrastructure/persistence"
)

func newTestProductService(t *testing.T) *productService {
	t.Helper()
	telemetryStore := telemetrypersistence.NewMemoryTelemetryStore()
	return newProductService(
		controlplanetest.NewFileStore(t.TempDir()+"/product-ops-state.json"),
		application.NewTelemetryServiceWithStoresAndRtcMediaQoeReader(
			telemetryStore,
			telemetryStore,
			telemetryStore,
			telemetryStore,
		),
		newTestExperimentFacade(t),
	)
}

func newTestProductServiceWithPublisher(t *testing.T, publisher messaging.EventPublisher) *productService {
	t.Helper()
	telemetryStore := telemetrypersistence.NewMemoryTelemetryStore()
	return newProductService(
		controlplanetest.NewFileStore(t.TempDir()+"/product-ops-state.json"),
		application.NewTelemetryServiceWithStoresAndRtcMediaQoeReader(
			telemetryStore,
			telemetryStore,
			telemetryStore,
			telemetryStore,
		),
		newTestExperimentFacade(t),
		publisher,
	)
}

func newTestProductServiceWithRuntimeLogs(t *testing.T) *productService {
	t.Helper()
	telemetryStore := telemetrypersistence.NewMemoryTelemetryStore()
	return newProductServiceWithRuntimeLogs(
		controlplanetest.NewFileStore(t.TempDir()+"/product-ops-state.json"),
		application.NewTelemetryServiceWithStoresAndRtcMediaQoeReader(
			telemetryStore,
			telemetryStore,
			telemetryStore,
			telemetryStore,
		),
		application.NewRuntimeLogService(telemetryStore, telemetryStore),
		newTestExperimentFacade(t),
	)
}

func requestAsTestPrincipal(request *http.Request, actor string) *http.Request {
	return request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
		Actor: operation.ActorContext{AccountID: actor},
	}))
}

func requestAsScopedProductOperator(request *http.Request, actor string, scopes ...string) *http.Request {
	return request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
		Claims: rtauth.Claims{
			Roles: []string{"operator"},
			Scope: strings.Join(scopes, " "),
		},
		Actor: operation.ActorContext{AccountID: actor},
	}))
}

type capturePublisher struct {
	events []messaging.DomainEvent
}

type testPrometheusQuery struct{}

func (testPrometheusQuery) Query(_ context.Context, expression string) (float64, error) {
	switch {
	case strings.Contains(expression, "http_server_duration_seconds_bucket"):
		return 700, nil
	case strings.Contains(expression, `status=~"5.."`):
		return 0.5, nil
	default:
		return 5, nil
	}
}

func (p *capturePublisher) Publish(_ context.Context, event messaging.DomainEvent) error {
	p.events = append(p.events, event)
	return nil
}

func newTestServerMux(service *productService) *http.ServeMux {
	return newServerMux(service, rthealth.NewChecker())
}

func TestRtcMediaQoeSummaryRouteUsesGeneratedOperationDescriptor(t *testing.T) {
	method, path := mustOpsOperationRoute(getRtcMediaQoeSummaryOperationID)
	if method != http.MethodGet {
		t.Fatalf("generated method = %q, want GET", method)
	}

	server := newTestServerMux(newTestProductService(t))
	response := httptest.NewRecorder()
	server.ServeHTTP(
		response,
		httptest.NewRequest(method, path, nil),
	)
	if response.Code != http.StatusOK {
		t.Fatalf(
			"GetRtcMediaQoeSummary status=%d body=%s",
			response.Code,
			response.Body.String(),
		)
	}

	wrongMethod := httptest.NewRecorder()
	server.ServeHTTP(
		wrongMethod,
		httptest.NewRequest(http.MethodPost, path, nil),
	)
	if wrongMethod.Code != http.StatusNotFound {
		t.Fatalf("wrong method status=%d, want 404", wrongMethod.Code)
	}
}

func TestRuntimeErrorBoundaryPreservesHTTPStatusClass(t *testing.T) {
	cases := []struct {
		name   string
		status int
	}{
		{name: "bad request", status: http.StatusBadRequest},
		{name: "unauthorized", status: http.StatusUnauthorized},
		{name: "forbidden", status: http.StatusForbidden},
		{name: "not found", status: http.StatusNotFound},
		{name: "conflict", status: http.StatusConflict},
		{name: "internal error", status: http.StatusInternalServerError},
	}
	for _, testCase := range cases {
		t.Run(testCase.name, func(t *testing.T) {
			response := httptest.NewRecorder()
			request := httptest.NewRequest(http.MethodGet, "/contract-status", nil)
			writeRuntimeError(
				response,
				request,
				testCase.status,
				"请求失败",
				testCase.name,
			)
			if response.Code != testCase.status {
				t.Fatalf(
					"runtime error status=%d, want %d",
					response.Code,
					testCase.status,
				)
			}
		})
	}
}

func withTestTelemetryPrincipal(request *http.Request) *http.Request {
	principal := rtauth.Principal{
		Actor: operation.ActorContext{PersonaID: "persona-test-telemetry"},
	}
	return request.WithContext(rtauth.WithPrincipal(request.Context(), principal))
}

func newTelemetryBatchRequest(t *testing.T, events []map[string]any) *http.Request {
	t.Helper()
	body, err := json.Marshal(map[string]any{"events": events})
	if err != nil {
		t.Fatalf("marshal telemetry batch: %v", err)
	}
	canonical, err := canonicalJSON(body)
	if err != nil {
		t.Fatalf("canonicalize telemetry batch: %v", err)
	}
	digest := sha256.Sum256(canonical)
	request := httptest.NewRequest(http.MethodPost, "/ops/events", bytes.NewReader(body))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", hex.EncodeToString(digest[:]))
	return withTestTelemetryPrincipal(request)
}

func newRuntimeLogBatchRequest(t *testing.T, records []map[string]any) *http.Request {
	t.Helper()
	body, err := json.Marshal(map[string]any{"records": records})
	if err != nil {
		t.Fatalf("marshal runtime log batch: %v", err)
	}
	canonical, err := canonicalJSON(body)
	if err != nil {
		t.Fatalf("canonicalize runtime log batch: %v", err)
	}
	digest := sha256.Sum256(canonical)
	request := httptest.NewRequest(http.MethodPost, "/ops/runtime-logs", bytes.NewReader(body))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", hex.EncodeToString(digest[:]))
	return withTestTelemetryPrincipal(request)
}

func runtimeDiagnosticRecord(occurredAt time.Time) map[string]any {
	return map[string]any{
		"schema":     "observability.slim",
		"recordId":   "r.runtime.test",
		"occurredAt": occurredAt.UTC().Format(time.RFC3339Nano),
		"observedAt": occurredAt.UTC().Format(time.RFC3339Nano),
		"logKind":    "exception",
		"severity":   "ERROR",
		"signal":     "app.exception.flutter",
		"message":    "uncaught framework exception",
		"resource": map[string]any{
			"sourceType": "app",
			"service":    "quwoquan_app",
			"appVersion": "1.0.0",
		},
		"errorCode": "APP.RUNTIME.uncaught_exception",
		"attributes": map[string]any{
			"source":        "flutter",
			"exceptionType": "StateError",
		},
	}
}

func telemetryEvent(eventType, logType string, occurredAt time.Time) map[string]any {
	return map[string]any{
		"logType":            logType,
		"eventType":          eventType,
		"sessionId":          "s.Z3Vlc3RfdGVzdA." + strconv.FormatInt(occurredAt.UnixMilli(), 10),
		"pageName":           "home",
		"occurredAt":         occurredAt.UTC().Format(time.RFC3339Nano),
		"deviceManufacturer": "Apple",
		"deviceModel":        "iPhone",
		"appVersion":         "1.0.0",
		"networkClass":       "wifi",
		"devicePlatform":     "ios",
	}
}

func TestValidateRequiredRuntimeConfigRejectsMissingMongo(t *testing.T) {
	cfg := config{}
	cfg.Redis.Rec.Mode = "standalone"
	cfg.Redis.Rec.Addr = "127.0.0.1:6379"
	cfg.Redis.General.Mode = "standalone"
	cfg.Redis.General.Addr = "127.0.0.1:6379"

	err := validateRequiredRuntimeConfig(cfg)
	if err == nil || !strings.Contains(err.Error(), "mongodb.uri is required") {
		t.Fatalf("expected missing mongodb uri failure, got %v", err)
	}
}

func TestReportRuntimeLogBatchAcceptsOnlyCanonicalAppDiagnostics(t *testing.T) {
	service := newTestProductServiceWithRuntimeLogs(t)
	server := newTestServerMux(service)
	now := time.Now().UTC()
	request := newRuntimeLogBatchRequest(t, []map[string]any{runtimeDiagnosticRecord(now)})
	response := httptest.NewRecorder()
	server.ServeHTTP(response, request)
	if response.Code != http.StatusOK {
		t.Fatalf("report runtime logs status=%d body=%s", response.Code, response.Body.String())
	}

	invalid := runtimeDiagnosticRecord(now)
	invalid["schemaVersion"] = "1"
	response = httptest.NewRecorder()
	server.ServeHTTP(response, newRuntimeLogBatchRequest(t, []map[string]any{invalid}))
	if response.Code != http.StatusUnprocessableEntity {
		t.Fatalf("versioned runtime log must be rejected, status=%d body=%s", response.Code, response.Body.String())
	}
}

func TestRuntimeLogQueriesKeepCorrelationRedactedByDefault(t *testing.T) {
	service := newTestProductServiceWithRuntimeLogs(t)
	server := newTestServerMux(service)
	now := time.Now().UTC().Truncate(time.Second)
	record := runtimeDiagnosticRecord(now)
	record["correlation"] = map[string]any{"requestId": "req-sensitive"}
	response := httptest.NewRecorder()
	server.ServeHTTP(response, newRuntimeLogBatchRequest(t, []map[string]any{record}))
	if response.Code != http.StatusOK {
		t.Fatalf("report runtime log status=%d body=%s", response.Code, response.Body.String())
	}
	from := now.Add(-time.Minute).Format(time.RFC3339Nano)
	to := now.Add(time.Minute).Format(time.RFC3339Nano)
	summaryRequest := httptest.NewRequest(http.MethodGet, "/ops/runtime-logs/summary?signal=app.exception.flutter&from="+from+"&to="+to, nil)
	response = httptest.NewRecorder()
	server.ServeHTTP(response, summaryRequest)
	if response.Code != http.StatusOK {
		t.Fatalf("runtime summary status=%d body=%s", response.Code, response.Body.String())
	}
	var summary application.RuntimeLogSummary
	if err := json.Unmarshal(response.Body.Bytes(), &summary); err != nil {
		t.Fatalf("decode runtime summary: %v", err)
	}
	if summary.TotalCount != 1 || summary.DimensionCounters["signal"]["app.exception.flutter"] != 1 {
		t.Fatalf("unexpected runtime summary: %#v", summary)
	}
	drilldownRequest := httptest.NewRequest(http.MethodGet, "/ops/runtime-logs/drilldown?signal=app.exception.flutter&from="+from+"&to="+to, nil)
	response = httptest.NewRecorder()
	server.ServeHTTP(response, drilldownRequest)
	if response.Code != http.StatusOK {
		t.Fatalf("runtime drilldown status=%d body=%s", response.Code, response.Body.String())
	}
	var drilldown application.RuntimeLogDrilldown
	if err := json.Unmarshal(response.Body.Bytes(), &drilldown); err != nil {
		t.Fatalf("decode runtime drilldown: %v", err)
	}
	if len(drilldown.Items) != 1 || len(drilldown.Items[0].Correlation) != 0 {
		t.Fatalf("runtime correlation must remain hidden by default: %#v", drilldown)
	}
	deniedRequest := httptest.NewRequest(http.MethodGet, "/ops/runtime-logs/drilldown?signal=app.exception.flutter&from="+from+"&to="+to+"&revealCorrelation=true", nil)
	response = httptest.NewRecorder()
	server.ServeHTTP(response, deniedRequest)
	if response.Code != http.StatusForbidden {
		t.Fatalf("sensitive correlation reveal must be forbidden, status=%d body=%s", response.Code, response.Body.String())
	}
}

// TestRuntimeLogActorAndTextQueries 覆盖日志服务的用户维度与文本检索：
// - ingest 服务端注入已验证 actorHash（覆盖端侧自报）；
// - actorHash 查询是敏感操作（无权限 403，ops_admin 放行且只命中该用户）；
// - messageContains 文本检索命中消息子串。
func TestRuntimeLogActorAndTextQueries(t *testing.T) {
	service := newTestProductServiceWithRuntimeLogs(t)
	server := newTestServerMux(service)
	now := time.Now().UTC().Truncate(time.Second)
	record := runtimeDiagnosticRecord(now)
	record["message"] = "payment flow crashed on submit"
	response := httptest.NewRecorder()
	server.ServeHTTP(response, newRuntimeLogBatchRequest(t, []map[string]any{record}))
	if response.Code != http.StatusOK {
		t.Fatalf("report runtime log status=%d body=%s", response.Code, response.Body.String())
	}

	from := now.Add(-time.Minute).Format(time.RFC3339Nano)
	to := now.Add(time.Minute).Format(time.RFC3339Nano)

	// 复算测试 principal 的 actorHash（与 ingest 注入同一派生）。
	ingestRequest := withTestTelemetryPrincipal(httptest.NewRequest(http.MethodGet, "/", nil))
	actorHash, ok := verifiedTelemetryActorHash(ingestRequest)
	if !ok || actorHash == "" {
		t.Fatalf("test principal must derive an actor hash")
	}

	denied := httptest.NewRequest(http.MethodGet, "/ops/runtime-logs/drilldown?from="+from+"&to="+to+"&actorHash="+actorHash, nil)
	response = httptest.NewRecorder()
	server.ServeHTTP(response, denied)
	if response.Code != http.StatusForbidden {
		t.Fatalf("actor query without sensitive permission must be forbidden, status=%d", response.Code)
	}

	adminContext := rtauth.WithPrincipal(context.Background(), rtauth.Principal{
		Claims: rtauth.Claims{Roles: []string{"ops_admin"}},
		Actor:  operation.ActorContext{AccountID: "ops-admin"},
	})
	allowed := httptest.NewRequest(http.MethodGet, "/ops/runtime-logs/drilldown?from="+from+"&to="+to+"&actorHash="+actorHash, nil).
		WithContext(adminContext)
	response = httptest.NewRecorder()
	server.ServeHTTP(response, allowed)
	if response.Code != http.StatusOK {
		t.Fatalf("actor query with ops_admin status=%d body=%s", response.Code, response.Body.String())
	}
	var byActor application.RuntimeLogDrilldown
	if err := json.Unmarshal(response.Body.Bytes(), &byActor); err != nil {
		t.Fatalf("decode actor drilldown: %v", err)
	}
	if len(byActor.Items) != 1 {
		t.Fatalf("actor query must match the ingested record, got %d items", len(byActor.Items))
	}

	missRequest := httptest.NewRequest(http.MethodGet, "/ops/runtime-logs/drilldown?from="+from+"&to="+to+"&actorHash=a.nonexistent", nil).
		WithContext(adminContext)
	response = httptest.NewRecorder()
	server.ServeHTTP(response, missRequest)
	var missed application.RuntimeLogDrilldown
	if err := json.Unmarshal(response.Body.Bytes(), &missed); err != nil {
		t.Fatalf("decode miss drilldown: %v", err)
	}
	if len(missed.Items) != 0 {
		t.Fatalf("unknown actor must not match records: %#v", missed.Items)
	}

	textHit := httptest.NewRequest(http.MethodGet, "/ops/runtime-logs/drilldown?from="+from+"&to="+to+"&messageContains=payment+flow", nil)
	response = httptest.NewRecorder()
	server.ServeHTTP(response, textHit)
	if response.Code != http.StatusOK {
		t.Fatalf("text query status=%d body=%s", response.Code, response.Body.String())
	}
	var byText application.RuntimeLogDrilldown
	if err := json.Unmarshal(response.Body.Bytes(), &byText); err != nil {
		t.Fatalf("decode text drilldown: %v", err)
	}
	if len(byText.Items) != 1 || !strings.Contains(byText.Items[0].Message, "payment flow") {
		t.Fatalf("text query must match message substring: %#v", byText.Items)
	}

	textMiss := httptest.NewRequest(http.MethodGet, "/ops/runtime-logs/drilldown?from="+from+"&to="+to+"&messageContains=nonexistent-phrase", nil)
	response = httptest.NewRecorder()
	server.ServeHTTP(response, textMiss)
	var textMissed application.RuntimeLogDrilldown
	if err := json.Unmarshal(response.Body.Bytes(), &textMissed); err != nil {
		t.Fatalf("decode text miss drilldown: %v", err)
	}
	if len(textMissed.Items) != 0 {
		t.Fatalf("text query must not match unrelated records: %#v", textMissed.Items)
	}
}

type testVectorPrometheusQuery struct{}

func (testVectorPrometheusQuery) Query(context.Context, string) (float64, error) { return 1, nil }

func (testVectorPrometheusQuery) QueryVector(_ context.Context, expression string) ([]application.PrometheusVectorSample, error) {
	switch {
	case strings.Contains(expression, "histogram_quantile(0.99"):
		return []application.PrometheusVectorSample{
			{Labels: map[string]string{"route": "/content/posts"}, Value: 180},
			{Labels: map[string]string{"route": "/content/feed"}, Value: 320},
		}, nil
	case strings.Contains(expression, "duration_seconds_sum"):
		return []application.PrometheusVectorSample{
			{Labels: map[string]string{"route": "/content/posts"}, Value: 45},
			{Labels: map[string]string{"route": "/content/feed"}, Value: 80},
		}, nil
	case strings.Contains(expression, `status=~"5.."`):
		return []application.PrometheusVectorSample{
			{Labels: map[string]string{"route": "/content/feed"}, Value: 0.05},
		}, nil
	default:
		return []application.PrometheusVectorSample{
			{Labels: map[string]string{"route": "/content/posts"}, Value: 12},
			{Labels: map[string]string{"route": "/content/feed"}, Value: 5},
		}, nil
	}
}

// TestServiceRouteREDDrilldown 覆盖每接口 RED 下钻：按 route 输出 QPS、
// 平均/P99 延迟与成功率，数据源只允许 Prometheus（service+route 维度）。
func TestServiceRouteREDDrilldown(t *testing.T) {
	service := newTestProductService(t)
	service.prometheus = testVectorPrometheusQuery{}
	server := newTestServerMux(service)

	missing := httptest.NewRecorder()
	server.ServeHTTP(missing, httptest.NewRequest(http.MethodGet, "/control-plane/product/metrics/red-routes", nil))
	if missing.Code == http.StatusOK {
		t.Fatalf("service parameter must be required, got 200")
	}

	response := httptest.NewRecorder()
	server.ServeHTTP(response, httptest.NewRequest(http.MethodGet, "/control-plane/product/metrics/red-routes?service=content-service", nil))
	if response.Code != http.StatusOK {
		t.Fatalf("red routes status=%d body=%s", response.Code, response.Body.String())
	}
	var payload serviceRouteREDResponse
	if err := json.Unmarshal(response.Body.Bytes(), &payload); err != nil {
		t.Fatalf("decode red routes: %v", err)
	}
	if payload.Source != "prometheus" || len(payload.Items) != 2 {
		t.Fatalf("unexpected red routes payload: %+v", payload)
	}
	if payload.Items[0].Route != "/content/posts" || payload.Items[0].QPS != 12 {
		t.Fatalf("items must sort by qps desc: %+v", payload.Items)
	}
	var feed serviceRouteREDItem
	for _, item := range payload.Items {
		if item.Route == "/content/feed" {
			feed = item
		}
	}
	if feed.P99Ms != 320 || feed.AvgMs != 80 {
		t.Fatalf("feed route latency mismatch: %+v", feed)
	}
	if feed.SuccessRate >= 100 || feed.SuccessRate <= 98 {
		t.Fatalf("feed success rate must reflect 5xx ratio: %+v", feed)
	}
}

// TestInternalRuntimeLogIngestTokenGate 覆盖云侧服务日志上云内部通道：
// 机器凭据 fail-closed、幂等摘要校验、app sourceType 拒绝、正常入库可查询。
func TestInternalRuntimeLogIngestTokenGate(t *testing.T) {
	t.Setenv("RUNTIME_LOG_INGEST_TOKEN", "test-ingest-token-32bytes-machine")
	service := newTestProductServiceWithRuntimeLogs(t)
	telemetryStore := telemetrypersistence.NewMemoryTelemetryStore()
	service.runtimeLogStore = telemetryStore
	service.runtimeLogs = application.NewRuntimeLogService(telemetryStore, telemetryStore)
	server := newTestServerMux(service)

	now := time.Now().UTC().Truncate(time.Second)
	serviceRecord := map[string]string{
		"schema":             "observability.slim",
		"recordId":           "r.service.test",
		"occurredAt":         now.Format(time.RFC3339Nano),
		"observedAt":         now.Format(time.RFC3339Nano),
		"logKind":            "exception",
		"severity":           "ERROR",
		"signal":             "service.exception.runtime",
		"message":            "downstream dependency failed",
		"resourceSourceType": "service",
		"resourceService":    "platform-ops-service",
	}
	newIngest := func(records []map[string]string, token string) *http.Request {
		body, err := json.Marshal(map[string]any{"records": records})
		if err != nil {
			t.Fatalf("marshal internal ingest: %v", err)
		}
		digest := sha256.Sum256(body)
		request := httptest.NewRequest(http.MethodPost, "/ops/internal/runtime-logs:ingest", bytes.NewReader(body))
		request.Header.Set("Content-Type", "application/json")
		request.Header.Set("Idempotency-Key", hex.EncodeToString(digest[:]))
		if token != "" {
			request.Header.Set("X-Runtime-Log-Ingest-Token", token)
		}
		return request
	}

	missingToken := httptest.NewRecorder()
	server.ServeHTTP(missingToken, newIngest([]map[string]string{serviceRecord}, ""))
	if missingToken.Code != http.StatusUnauthorized {
		t.Fatalf("missing token must be unauthorized, status=%d", missingToken.Code)
	}
	wrongToken := httptest.NewRecorder()
	server.ServeHTTP(wrongToken, newIngest([]map[string]string{serviceRecord}, "wrong-token"))
	if wrongToken.Code != http.StatusUnauthorized {
		t.Fatalf("wrong token must be unauthorized, status=%d", wrongToken.Code)
	}

	appRecord := map[string]string{}
	for key, value := range serviceRecord {
		appRecord[key] = value
	}
	appRecord["resourceSourceType"] = "app"
	appRejected := httptest.NewRecorder()
	server.ServeHTTP(appRejected, newIngest([]map[string]string{appRecord}, "test-ingest-token-32bytes-machine"))
	if appRejected.Code != http.StatusUnprocessableEntity {
		t.Fatalf("app records must be rejected on the internal channel, status=%d body=%s", appRejected.Code, appRejected.Body.String())
	}
	if !strings.Contains(appRejected.Body.String(), "runtime_log_batch_invalid") {
		t.Fatalf("app rejection must use runtime_log_batch_invalid: %s", appRejected.Body.String())
	}

	accepted := httptest.NewRecorder()
	server.ServeHTTP(accepted, newIngest([]map[string]string{serviceRecord}, "test-ingest-token-32bytes-machine"))
	if accepted.Code != http.StatusOK {
		t.Fatalf("internal ingest status=%d body=%s", accepted.Code, accepted.Body.String())
	}

	from := now.Add(-time.Minute).Format(time.RFC3339Nano)
	to := now.Add(time.Minute).Format(time.RFC3339Nano)
	query := httptest.NewRequest(http.MethodGet, "/ops/runtime-logs/drilldown?sourceType=service&service=platform-ops-service&from="+from+"&to="+to, nil)
	queryResponse := httptest.NewRecorder()
	server.ServeHTTP(queryResponse, query)
	if queryResponse.Code != http.StatusOK {
		t.Fatalf("query ingested service log status=%d body=%s", queryResponse.Code, queryResponse.Body.String())
	}
	var drilldown application.RuntimeLogDrilldown
	if err := json.Unmarshal(queryResponse.Body.Bytes(), &drilldown); err != nil {
		t.Fatalf("decode service log drilldown: %v", err)
	}
	if len(drilldown.Items) != 1 || drilldown.Items[0].Message != "downstream dependency failed" {
		t.Fatalf("service log must be queryable after internal ingest: %#v", drilldown.Items)
	}
}

func TestValidateRequiredRuntimeConfigRejectsMissingRedisEndpoint(t *testing.T) {
	cfg := config{}
	cfg.MongoDB.URI = "mongodb://127.0.0.1:27017"
	cfg.MongoDB.Database = "product_ops"
	cfg.Postgres.DSN = "postgres://quwoquan:quwoquan@127.0.0.1:5432/quwoquan?sslmode=disable"
	cfg.Redis.Rec.Mode = "standalone"
	cfg.Redis.Rec.Addr = "127.0.0.1:6379"
	cfg.Redis.General.Mode = "standalone"
	setTestSLSConfig(&cfg)

	err := validateRequiredRuntimeConfig(cfg)
	if err == nil || !strings.Contains(err.Error(), "redis.general standalone addr is required") {
		t.Fatalf("expected missing redis endpoint failure, got %v", err)
	}
}

func setTestSLSConfig(cfg *config) {
	cfg.SLS.Region = "cn-hangzhou"
	cfg.SLS.Endpoint = "cn-hangzhou.log.aliyuncs.com"
	cfg.SLS.Project = "test-project"
	cfg.SLS.RawLogstore = "app-product-telemetry-raw"
	cfg.SLS.StartupDiagnosticLogstore = "app-startup-diagnostic-raw"
	cfg.SLS.RuntimeLogstore = "runtime-diagnostics-raw"
	cfg.SLS.AggregateLogstore = "app-product-telemetry-hourly"
	cfg.SLS.TimeoutMS = 1200
}

func TestValidateRequiredRuntimeConfigRejectsMissingPostgres(t *testing.T) {
	cfg := config{}
	cfg.MongoDB.URI = "mongodb://127.0.0.1:27017"
	cfg.MongoDB.Database = "product_ops"
	cfg.Redis.Rec.Mode = "standalone"
	cfg.Redis.Rec.Addr = "127.0.0.1:6379"
	cfg.Redis.General.Mode = "standalone"
	cfg.Redis.General.Addr = "127.0.0.1:6379"

	err := validateRequiredRuntimeConfig(cfg)
	if err == nil || !strings.Contains(err.Error(), "postgres.dsn is required") {
		t.Fatalf("expected missing postgres dsn failure, got %v", err)
	}
}

func TestIntegrationRuntimeConfigUsesPostgresTelemetryWithoutSLS(t *testing.T) {
	cfg := config{}
	cfg.MongoDB.URI = "mongodb://127.0.0.1:27017"
	cfg.MongoDB.Database = "product_ops"
	cfg.Postgres.DSN = "postgres://quwoquan:quwoquan@127.0.0.1:5432/quwoquan?sslmode=disable"
	cfg.Redis.Rec.Mode = "standalone"
	cfg.Redis.Rec.Addr = "127.0.0.1:6379"
	cfg.Redis.General.Mode = "standalone"
	cfg.Redis.General.Addr = "127.0.0.1:6379"

	if got := postgresTelemetrySchema("gamma-integration"); got != "telemetry_local_gamma" {
		t.Fatalf("gamma integration schema = %q", got)
	}
	if err := validateRequiredRuntimeConfig(cfg, "gamma-integration"); err != nil {
		t.Fatalf("integration profile must not require SLS credentials: %v", err)
	}
}

func TestBuildRedisSceneConfigUsesClusterAddressOverride(t *testing.T) {
	scene, err := buildRedisSceneConfig("general", redisSceneCfg{
		Mode: "cluster",
		Addr: "redis-a:6379, redis-b:6379",
	})
	if err != nil {
		t.Fatalf("build cluster redis scene: %v", err)
	}
	if scene.Mode != "cluster" || len(scene.Addrs) != 2 || scene.Addr != "" {
		t.Fatalf("unexpected cluster redis scene: %+v", scene)
	}
}

func TestExperimentEndpoints(t *testing.T) {
	service := newTestProductService(t)
	if err := service.seed(); err != nil {
		t.Fatalf("seed service: %v", err)
	}
	server := newTestServerMux(service)

	assignReq := httptest.NewRequest(http.MethodPost, "/ops/experiments/discovery_feed_v3/assignment", nil)
	assignReq.Header.Set("Content-Type", "application/json")
	assignReq = withTestTelemetryPrincipal(assignReq)
	assignResp := httptest.NewRecorder()
	server.ServeHTTP(assignResp, assignReq)
	if assignResp.Code != http.StatusCreated {
		t.Fatalf("assign experiment status=%d body=%s", assignResp.Code, assignResp.Body.String())
	}

	var assignment map[string]any
	if err := json.Unmarshal(assignResp.Body.Bytes(), &assignment); err != nil {
		t.Fatalf("unmarshal assign response: %v", err)
	}
	if assignment["experimentId"] != "discovery_feed_v3" {
		t.Fatalf("unexpected experimentId: %v", assignment["experimentId"])
	}
	if assignment["subjectKey"] != "persona:persona-test-telemetry" {
		t.Fatalf("assignment subject must derive from verified persona: %v", assignment)
	}
	if assignment["variant"] == "" {
		t.Fatalf("variant should not be empty: %v", assignment)
	}
	assignedAt := assignment["assignedAt"]

	replayReq := httptest.NewRequest(http.MethodPost, "/ops/experiments/discovery_feed_v3/assignment", nil)
	replayReq.Header.Set("Content-Type", "application/json")
	replayReq = withTestTelemetryPrincipal(replayReq)
	replayResp := httptest.NewRecorder()
	server.ServeHTTP(replayResp, replayReq)
	if replayResp.Code != http.StatusOK {
		t.Fatalf("replay assignment status=%d body=%s", replayResp.Code, replayResp.Body.String())
	}
	var replayed map[string]any
	if err := json.Unmarshal(replayResp.Body.Bytes(), &replayed); err != nil {
		t.Fatalf("unmarshal replay response: %v", err)
	}
	if replayed["id"] != assignment["id"] || replayed["assignedAt"] != assignedAt {
		t.Fatalf("idempotent replay changed immutable fact: first=%v replay=%v", assignment, replayed)
	}

	getReq := httptest.NewRequest(http.MethodGet, "/ops/experiments/discovery_feed_v3/assignment", nil)
	getReq = withTestTelemetryPrincipal(getReq)
	getResp := httptest.NewRecorder()
	server.ServeHTTP(getResp, getReq)
	if getResp.Code != http.StatusOK {
		t.Fatalf("get assignment status=%d body=%s", getResp.Code, getResp.Body.String())
	}
	unauthorizedGet := httptest.NewRequest(http.MethodGet, "/ops/experiments/discovery_feed_v3/assignment", nil)
	unauthorizedResp := httptest.NewRecorder()
	server.ServeHTTP(unauthorizedResp, unauthorizedGet)
	if unauthorizedResp.Code != http.StatusUnauthorized {
		t.Fatalf("assignment without verified actor status=%d body=%s", unauthorizedResp.Code, unauthorizedResp.Body.String())
	}

	statsReq := httptest.NewRequest(http.MethodGet, "/ops/experiments/discovery_feed_v3/stats", nil)
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

	for index := range 2 {
		recordReq := httptest.NewRequest(http.MethodPost, "/ops/visits", bytes.NewBufferString(`{"targetType":"page","targetKey":"platform-onboarding"}`))
		recordReq.Header.Set("Content-Type", "application/json")
		recordReq.Header.Set("Idempotency-Key", "visit-key-"+strconv.Itoa(index))
		recordReq = withTestTelemetryPrincipal(recordReq)
		recordResp := httptest.NewRecorder()
		server.ServeHTTP(recordResp, recordReq)
		if recordResp.Code != http.StatusOK {
			t.Fatalf("record visit status=%d body=%s", recordResp.Code, recordResp.Body.String())
		}
	}

	statsReq := httptest.NewRequest(http.MethodGet, "/ops/visits/stats?targetType=page&targetKey=platform-onboarding", nil)
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

	occurredAt := time.Now().UTC().Add(-2 * time.Hour)
	pageOpen := telemetryEvent("page_open", "event", occurredAt)
	pageReturn := telemetryEvent("page_return", "event", occurredAt.Add(time.Second))
	pageOpen["networkClass"] = "5g"
	pageReturn["networkClass"] = "4g"
	pageReturn["durationMs"] = 1200
	req := newTelemetryBatchRequest(t, []map[string]any{pageOpen, pageReturn})
	resp := httptest.NewRecorder()
	server.ServeHTTP(resp, req)
	if resp.Code != http.StatusOK {
		t.Fatalf("report events status=%d body=%s", resp.Code, resp.Body.String())
	}

	summaryReq := httptest.NewRequest(http.MethodGet, "/ops/events/summary?pageName=home&from="+occurredAt.Add(-time.Minute).Format(time.RFC3339Nano)+"&to="+occurredAt.Add(time.Hour).Format(time.RFC3339Nano), nil)
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

	drilldownReq := httptest.NewRequest(http.MethodGet, "/ops/events/drilldown?eventType=page_return&from="+occurredAt.Add(-time.Minute).Format(time.RFC3339Nano)+"&to="+occurredAt.Add(time.Hour).Format(time.RFC3339Nano), nil)
	drilldownResp := httptest.NewRecorder()
	server.ServeHTTP(drilldownResp, drilldownReq)
	if drilldownResp.Code != http.StatusOK {
		t.Fatalf("event drilldown status=%d body=%s", drilldownResp.Code, drilldownResp.Body.String())
	}
	var drilldown struct {
		TotalCount int64 `json:"totalCount"`
		Items      []struct {
			RowKey    string `json:"rowKey"`
			EventType string `json:"eventType"`
			SessionID string `json:"sessionId"`
		} `json:"items"`
	}
	if err := json.Unmarshal(drilldownResp.Body.Bytes(), &drilldown); err != nil {
		t.Fatalf("unmarshal event drilldown: %v", err)
	}
	if drilldown.TotalCount != 1 || len(drilldown.Items) != 1 || drilldown.Items[0].EventType != "page_return" || drilldown.Items[0].RowKey == "" || !strings.Contains(drilldown.Items[0].SessionID, "***") {
		t.Fatalf("unexpected drilldown payload: %+v", drilldown)
	}

	removedVPN := telemetryEvent("page_open", "event", occurredAt)
	removedVPN["networkClass"] = "vpn"
	removedVPNReq := newTelemetryBatchRequest(t, []map[string]any{removedVPN})
	removedVPNResp := httptest.NewRecorder()
	server.ServeHTTP(removedVPNResp, removedVPNReq)
	if removedVPNResp.Code != http.StatusUnprocessableEntity {
		t.Fatalf(
			"removed networkClass vpn must be rejected, status=%d body=%s",
			removedVPNResp.Code,
			removedVPNResp.Body.String(),
		)
	}
}

func TestStartupTelemetryEndpointIsAnonymousRestrictedAndIdempotent(t *testing.T) {
	service := newTestProductService(t)
	server := newTestServerMux(service)
	body := `{"events":[{"eventId":"startup_attempt_000001_1","attemptId":"startup_attempt_000001","sequence":1,"phase":"dart_bootstrap","phaseDurationMs":12,"elapsedMs":12,"outcome":"started","occurredAt":"2026-07-17T10:00:00Z","platform":"android","runtimeEnv":"alpha","deadlineOrigin":"android_process"}]}`

	for attempt := 0; attempt < 2; attempt++ {
		request := httptest.NewRequest(
			http.MethodPost,
			"/ops/startup-events",
			bytes.NewBufferString(body),
		)
		request.Header.Set("Content-Type", "application/json")
		request.Header.Set(startupTelemetryProofHeader, "startup_proof_000000000001")
		response := httptest.NewRecorder()
		server.ServeHTTP(response, request)
		if response.Code != http.StatusOK {
			t.Fatalf("startup telemetry status=%d body=%s", response.Code, response.Body.String())
		}
		var ack application.EventBatchAck
		if err := json.Unmarshal(response.Body.Bytes(), &ack); err != nil {
			t.Fatalf("decode startup telemetry ack: %v", err)
		}
		if attempt == 0 && ack.AcceptedCount != 1 {
			t.Fatalf("first startup telemetry ack=%+v", ack)
		}
		if attempt == 1 && !ack.DuplicateBatch {
			t.Fatalf("retry startup telemetry ack=%+v", ack)
		}
	}

	genericRequest := httptest.NewRequest(
		http.MethodPost,
		"/ops/events",
		bytes.NewBufferString(`{"events":[{"eventId":"generic-event","eventType":"experience","eventName":"page_open","priority":"normal","producer":"app","occurredAt":"2026-07-17T10:00:00Z"}]}`),
	)
	genericResponse := httptest.NewRecorder()
	server.ServeHTTP(genericResponse, genericRequest)
	if genericResponse.Code != http.StatusUnauthorized {
		t.Fatalf("generic telemetry must remain authenticated, got %d", genericResponse.Code)
	}
}

func TestStartupTelemetryEndpointRejectsUnknownAndPIILikeFields(t *testing.T) {
	service := newTestProductService(t)
	server := newTestServerMux(service)
	request := httptest.NewRequest(
		http.MethodPost,
		"/ops/startup-events",
		bytes.NewBufferString(`{"events":[{"eventId":"startup_attempt_000001_1","attemptId":"startup_attempt_000001","sequence":1,"phase":"dart_bootstrap","phaseDurationMs":12,"elapsedMs":12,"outcome":"started","occurredAt":"2026-07-17T10:00:00Z","platform":"android","runtimeEnv":"alpha","userId":"must_not_be_accepted"}]}`),
	)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set(startupTelemetryProofHeader, "startup_proof_000000000002")
	response := httptest.NewRecorder()
	server.ServeHTTP(response, request)
	if response.Code != http.StatusBadRequest {
		t.Fatalf("unknown/PII field must be rejected, got %d body=%s", response.Code, response.Body.String())
	}
	var invalidResponse struct {
		Code string `json:"code"`
	}
	if err := json.Unmarshal(response.Body.Bytes(), &invalidResponse); err != nil {
		t.Fatalf("decode startup invalid response: %v", err)
	}
	if invalidResponse.Code != "OPS.USER.startup_event_invalid" {
		t.Fatalf("startup invalid response code=%q", invalidResponse.Code)
	}

	failureCodeRequest := httptest.NewRequest(
		http.MethodPost,
		"/ops/startup-events",
		bytes.NewBufferString(`{"events":[{"eventId":"startup_attempt_000004_1","attemptId":"startup_attempt_000004","sequence":1,"phase":"recovery","phaseDurationMs":12,"elapsedMs":12,"outcome":"shown","occurredAt":"2026-07-17T10:00:00Z","platform":"android","runtimeEnv":"alpha","failureCode":"token_like_diagnostic_must_not_escape"}]}`),
	)
	failureCodeRequest.Header.Set("Content-Type", "application/json")
	failureCodeRequest.Header.Set(
		startupTelemetryProofHeader,
		"startup_proof_000000000005",
	)
	failureCodeResponse := httptest.NewRecorder()
	server.ServeHTTP(failureCodeResponse, failureCodeRequest)
	if failureCodeResponse.Code != http.StatusBadRequest {
		t.Fatalf(
			"unallowlisted failure code must be rejected, got %d body=%s",
			failureCodeResponse.Code,
			failureCodeResponse.Body.String(),
		)
	}

	networkClassRequest := httptest.NewRequest(
		http.MethodPost,
		"/ops/startup-events",
		bytes.NewBufferString(`{"events":[{"eventId":"startup_attempt_000005_1","attemptId":"startup_attempt_000005","sequence":1,"phase":"dart_bootstrap","phaseDurationMs":12,"elapsedMs":12,"outcome":"started","occurredAt":"2026-07-17T10:00:00Z","platform":"android","runtimeEnv":"alpha","networkClass":"user@example.com"}]}`),
	)
	networkClassRequest.Header.Set("Content-Type", "application/json")
	networkClassRequest.Header.Set(
		startupTelemetryProofHeader,
		"startup_proof_000000000006",
	)
	networkClassResponse := httptest.NewRecorder()
	server.ServeHTTP(networkClassResponse, networkClassRequest)
	if networkClassResponse.Code != http.StatusBadRequest {
		t.Fatalf(
			"unallowlisted network class must be rejected, got %d body=%s",
			networkClassResponse.Code,
			networkClassResponse.Body.String(),
		)
	}

	whitespaceLabelRequest := httptest.NewRequest(
		http.MethodPost,
		"/ops/startup-events",
		bytes.NewBufferString(`{"events":[{"eventId":"startup_attempt_000006_1","attemptId":"startup_attempt_000006","sequence":1,"phase":"dart_bootstrap","phaseDurationMs":12,"elapsedMs":12,"outcome":"started","occurredAt":"2026-07-17T10:00:00Z","platform":" android ","runtimeEnv":"alpha"}]}`),
	)
	whitespaceLabelRequest.Header.Set("Content-Type", "application/json")
	whitespaceLabelRequest.Header.Set(
		startupTelemetryProofHeader,
		"startup_proof_000000000007",
	)
	whitespaceLabelResponse := httptest.NewRecorder()
	server.ServeHTTP(whitespaceLabelResponse, whitespaceLabelRequest)
	if whitespaceLabelResponse.Code != http.StatusBadRequest {
		t.Fatalf(
			"whitespace metric label must be rejected, got %d body=%s",
			whitespaceLabelResponse.Code,
			whitespaceLabelResponse.Body.String(),
		)
	}

	mismatchedEventIDRequest := httptest.NewRequest(
		http.MethodPost,
		"/ops/startup-events",
		bytes.NewBufferString(`{"events":[{"eventId":"startup_attempt_000006_99","attemptId":"startup_attempt_000006","sequence":1,"phase":"dart_bootstrap","phaseDurationMs":12,"elapsedMs":12,"outcome":"started","occurredAt":"2026-07-17T10:00:00Z","platform":"android","runtimeEnv":"alpha"}]}`),
	)
	mismatchedEventIDRequest.Header.Set("Content-Type", "application/json")
	mismatchedEventIDRequest.Header.Set(
		startupTelemetryProofHeader,
		"startup_proof_000000000007",
	)
	mismatchedEventIDResponse := httptest.NewRecorder()
	server.ServeHTTP(mismatchedEventIDResponse, mismatchedEventIDRequest)
	if mismatchedEventIDResponse.Code != http.StatusBadRequest {
		t.Fatalf(
			"eventId must be derived from attemptId and sequence, got %d body=%s",
			mismatchedEventIDResponse.Code,
			mismatchedEventIDResponse.Body.String(),
		)
	}
}

func TestStartupTelemetryEndpointRejectsUnboundedMetricLabels(t *testing.T) {
	service := newTestProductService(t)
	server := newTestServerMux(service)
	request := httptest.NewRequest(
		http.MethodPost,
		"/ops/startup-events",
		bytes.NewBufferString(`{"events":[{"eventId":"startup_attempt_000002_1","attemptId":"startup_attempt_000002","sequence":1,"phase":"dart_bootstrap","phaseDurationMs":12,"elapsedMs":12,"outcome":"attacker_controlled_label","occurredAt":"2026-07-17T10:00:00Z","platform":"android","runtimeEnv":"alpha"}]}`),
	)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set(startupTelemetryProofHeader, "startup_proof_000000000003")
	response := httptest.NewRecorder()
	server.ServeHTTP(response, request)
	if response.Code != http.StatusBadRequest {
		t.Fatalf("unbounded metric label must be rejected, got %d body=%s", response.Code, response.Body.String())
	}
}

func TestStartupTelemetryEndpointAcceptsBoundedJournalDropTerminal(t *testing.T) {
	service := newTestProductService(t)
	server := newTestServerMux(service)
	request := httptest.NewRequest(
		http.MethodPost,
		"/ops/startup-events",
		bytes.NewBufferString(`{"events":[{"eventId":"startup_attempt_000003_3","attemptId":"startup_attempt_000003","sequence":3,"phase":"terminal","phaseDurationMs":0,"elapsedMs":120,"outcome":"journal_drop","occurredAt":"2026-07-17T10:00:00Z","platform":"web","runtimeEnv":"alpha","recoverySurface":"native_recovery","failureCode":"OPS.SYSTEM.startup_native_first_frame_timeout","failureSource":"native_watchdog","deadlineOrigin":"web_bootstrap"}]}`),
	)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set(startupTelemetryProofHeader, "startup_proof_000000000004")
	response := httptest.NewRecorder()
	server.ServeHTTP(response, request)
	if response.Code != http.StatusOK {
		t.Fatalf("bounded journal_drop terminal must be accepted, got %d body=%s", response.Code, response.Body.String())
	}
}

func TestStartupTelemetryRateLimitCannotBeBypassedByChangingProof(t *testing.T) {
	limiter := newStartupTelemetryLimiter()
	now := time.Date(2026, time.July, 17, 10, 0, 0, 0, time.UTC)
	request := httptest.NewRequest(http.MethodPost, "/ops/startup-events", nil)
	request.RemoteAddr = "203.0.113.42:54321"

	if !limiter.allow(
		startupTelemetryRateLimitKey(request, "startup_proof_000000000101"),
		startupTelemetryMaxPerMinute,
		now,
	) {
		t.Fatal("first source window should be allowed")
	}
	if limiter.allow(
		startupTelemetryRateLimitKey(request, "startup_proof_000000000102"),
		1,
		now,
	) {
		t.Fatal("changing an untrusted proof must not bypass source rate limit")
	}
}

func TestControlPlaneWorkflowEndpoints(t *testing.T) {
	service := newTestProductService(t)
	if err := service.seed(); err != nil {
		t.Fatalf("seed service: %v", err)
	}
	server := newTestServerMux(service)

	// 治理/推荐骨架端点已退场：workflow/audit/approval 留痕由真实的
	// premium-pool 运营链路（upsert → 双签 takedown）产生。
	expiresAt := time.Now().UTC().Add(24 * time.Hour).Format(time.RFC3339)
	createBody := `{"contentId":"post_workflow_premium","scope":"global","qualityScore":0.93,"qualityAdmission":"approved","auditId":"audit_workflow_premium","expiresAt":"` + expiresAt + `"}`
	createReq := httptest.NewRequest(http.MethodPost, "/control-plane/product/recommendation/premium-pool", bytes.NewBufferString(createBody))
	createReq.Header.Set("Content-Type", "application/json")
	createReq = requestAsTestPrincipal(createReq, "premium-editor")
	createResp := httptest.NewRecorder()
	server.ServeHTTP(createResp, createReq)
	if createResp.Code != http.StatusOK {
		t.Fatalf("create premium entry status=%d body=%s", createResp.Code, createResp.Body.String())
	}

	firstTakedownReq := httptest.NewRequest(http.MethodPost, "/control-plane/product/recommendation/premium-pool/post_workflow_premium:takedown", nil)
	firstTakedownReq = requestAsTestPrincipal(firstTakedownReq, "ops-approver-1")
	firstTakedownReq.Header.Set("Idempotency-Key", "premium-workflow-takedown")
	firstTakedownResp := httptest.NewRecorder()
	server.ServeHTTP(firstTakedownResp, firstTakedownReq)
	if firstTakedownResp.Code != http.StatusOK {
		t.Fatalf("first takedown status=%d body=%s", firstTakedownResp.Code, firstTakedownResp.Body.String())
	}
	var pendingPayload struct {
		Pending       bool   `json:"pending"`
		ApprovalState string `json:"approvalState"`
		ApprovalCount int    `json:"approvalCount"`
	}
	if err := json.Unmarshal(firstTakedownResp.Body.Bytes(), &pendingPayload); err != nil {
		t.Fatalf("unmarshal pending takedown payload: %v", err)
	}
	if !pendingPayload.Pending || pendingPayload.ApprovalState != "pending_second_principal" || pendingPayload.ApprovalCount != 1 {
		t.Fatalf("single principal takedown must stay pending, got %+v", pendingPayload)
	}

	secondTakedownReq := httptest.NewRequest(http.MethodPost, "/control-plane/product/recommendation/premium-pool/post_workflow_premium:takedown", nil)
	secondTakedownReq = requestAsTestPrincipal(secondTakedownReq, "ops-approver-2")
	secondTakedownReq.Header.Set("Idempotency-Key", "premium-workflow-takedown")
	secondTakedownResp := httptest.NewRecorder()
	server.ServeHTTP(secondTakedownResp, secondTakedownReq)
	if secondTakedownResp.Code != http.StatusOK {
		t.Fatalf("second takedown status=%d body=%s", secondTakedownResp.Code, secondTakedownResp.Body.String())
	}
	var approvedPayload struct {
		Entry   premiumPoolEntry             `json:"entry"`
		Pending bool                         `json:"pending"`
		Receipt controlplane.MutationReceipt `json:"receipt"`
	}
	if err := json.Unmarshal(secondTakedownResp.Body.Bytes(), &approvedPayload); err != nil {
		t.Fatalf("unmarshal takedown entry: %v", err)
	}
	if approvedPayload.Pending || !approvedPayload.Entry.TakedownEjected ||
		approvedPayload.Entry.Status != "takedown_ejected" ||
		approvedPayload.Receipt.IdempotencyKey != "premium-workflow-takedown" {
		t.Fatalf("dual-signed takedown must atomically eject entry, got %+v", approvedPayload)
	}

	workflowReq := httptest.NewRequest(http.MethodGet, "/control-plane/product/workflows", nil)
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

	auditReq := httptest.NewRequest(http.MethodGet, "/control-plane/product/audits", nil)
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
	if len(auditPayload.Items) < 2 {
		t.Fatalf("expected audit events, got %+v", auditPayload.Items)
	}

	approvalReq := httptest.NewRequest(http.MethodGet, "/control-plane/product/approvals", nil)
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
	if len(approvalPayload.Items) < 2 {
		t.Fatalf("expected approvals, got %+v", approvalPayload.Items)
	}

	summaryReq := httptest.NewRequest(http.MethodGet, "/control-plane/product/projections/summary", nil)
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

func TestPremiumPoolTakedownAuthorizationIsMetadataDriven(t *testing.T) {
	service := newTestProductService(t)
	directServer := newTestServerMux(service)
	expiresAt := time.Now().UTC().Add(24 * time.Hour).Format(time.RFC3339)
	createReq := httptest.NewRequest(
		http.MethodPost,
		"/control-plane/product/recommendation/premium-pool",
		bytes.NewBufferString(
			`{"contentId":"post_authz_premium","scope":"global","qualityScore":0.92,"qualityAdmission":"approved","auditId":"audit_authz_premium","expiresAt":"`+expiresAt+`"}`,
		),
	)
	createReq = requestAsTestPrincipal(createReq, "premium-editor")
	createResp := httptest.NewRecorder()
	directServer.ServeHTTP(createResp, createReq)
	if createResp.Code != http.StatusOK {
		t.Fatalf("seed premium entry status=%d body=%s", createResp.Code, createResp.Body.String())
	}

	server := rtauth.RequireGeneratedOperationAuthorization(append(
		operationsecurity.ForDomain("ops"),
		generatedcontrolplane.ProductOperationSecurityDescriptors...,
	))(directServer)
	path := "/control-plane/product/recommendation/premium-pool/post_authz_premium:takedown"

	spoofedReq := httptest.NewRequest(http.MethodPost, path, nil)
	spoofedReq.Header.Set("X-Actor", "forged-product-admin")
	spoofedReq.Header.Set("Idempotency-Key", "authz-premium-takedown")
	spoofedResp := httptest.NewRecorder()
	server.ServeHTTP(spoofedResp, spoofedReq)
	if spoofedResp.Code != http.StatusUnauthorized {
		t.Fatalf("spoofed actor header must not authenticate, status=%d body=%s", spoofedResp.Code, spoofedResp.Body.String())
	}

	missingScopeReq := requestAsScopedProductOperator(
		httptest.NewRequest(http.MethodPost, path, nil),
		"operator-without-scope",
	)
	missingScopeReq.Header.Set("Idempotency-Key", "authz-premium-takedown")
	missingScopeResp := httptest.NewRecorder()
	server.ServeHTTP(missingScopeResp, missingScopeReq)
	if missingScopeResp.Code != http.StatusForbidden {
		t.Fatalf("operator without scope must be forbidden, status=%d body=%s", missingScopeResp.Code, missingScopeResp.Body.String())
	}

	missingKeyReq := requestAsScopedProductOperator(
		httptest.NewRequest(http.MethodPost, path, nil),
		"scoped-operator",
		"ops.reco.write",
	)
	missingKeyResp := httptest.NewRecorder()
	server.ServeHTTP(missingKeyResp, missingKeyReq)
	if missingKeyResp.Code != http.StatusBadRequest {
		t.Fatalf("metadata-required idempotency key must be enforced, status=%d body=%s", missingKeyResp.Code, missingKeyResp.Body.String())
	}

	allowedReq := requestAsScopedProductOperator(
		httptest.NewRequest(http.MethodPost, path, nil),
		"scoped-operator",
		"ops.reco.write",
	)
	allowedReq.Header.Set("X-Actor", "forged-second-actor")
	allowedReq.Header.Set("Idempotency-Key", "authz-premium-takedown")
	allowedResp := httptest.NewRecorder()
	server.ServeHTTP(allowedResp, allowedReq)
	if allowedResp.Code != http.StatusOK {
		t.Fatalf("scoped operator must reach takedown approval, status=%d body=%s", allowedResp.Code, allowedResp.Body.String())
	}
	approvals, err := service.store.ListApprovals("premium_pool_entry", "post_authz_premium")
	if err != nil {
		t.Fatal(err)
	}
	if len(approvals) != 1 || approvals[0].Actor != "scoped-operator" {
		t.Fatalf("approval actor must come only from verified principal, got %+v", approvals)
	}
}

func TestPremiumPoolControlPlaneEndpoints(t *testing.T) {
	publisher := &capturePublisher{}
	service := newTestProductServiceWithPublisher(t, publisher)
	server := newTestServerMux(service)
	expiresAt := time.Now().UTC().Add(24 * time.Hour).Format(time.RFC3339)

	invalidScopeReq := httptest.NewRequest(
		http.MethodPost,
		"/control-plane/product/recommendation/premium-pool",
		bytes.NewBufferString(`{"contentId":"post_bad","scope":"circle","qualityScore":0.95,"qualityAdmission":"approved","auditId":"audit_bad","expiresAt":"`+expiresAt+`"}`),
	)
	invalidScopeResp := httptest.NewRecorder()
	server.ServeHTTP(invalidScopeResp, invalidScopeReq)
	if invalidScopeResp.Code != http.StatusBadRequest {
		t.Fatalf("circle scoped premium pool must be rejected, status=%d body=%s", invalidScopeResp.Code, invalidScopeResp.Body.String())
	}

	lowQualityReq := httptest.NewRequest(
		http.MethodPost,
		"/control-plane/product/recommendation/premium-pool",
		bytes.NewBufferString(`{"contentId":"post_low","scope":"global","qualityScore":0.5,"qualityAdmission":"approved","auditId":"audit_low","expiresAt":"`+expiresAt+`"}`),
	)
	lowQualityResp := httptest.NewRecorder()
	server.ServeHTTP(lowQualityResp, lowQualityReq)
	if lowQualityResp.Code != http.StatusBadRequest {
		t.Fatalf("low quality premium pool must be rejected, status=%d body=%s", lowQualityResp.Code, lowQualityResp.Body.String())
	}

	createBody := `{"contentId":"post_premium_1","scope":"global","qualityScore":0.92,"qualityAdmission":"approved","supplySource":"data_engineering","sourceTaskId":"task_1","auditId":"audit_premium_1","rollbackToken":"rbk-premium-1","expiresAt":"` + expiresAt + `"}`
	createReq := httptest.NewRequest(http.MethodPost, "/control-plane/product/recommendation/premium-pool", bytes.NewBufferString(createBody))
	createReq.Header.Set("X-Actor", "premium-editor")
	createResp := httptest.NewRecorder()
	server.ServeHTTP(createResp, createReq)
	if createResp.Code != http.StatusOK {
		t.Fatalf("create premium pool status=%d body=%s", createResp.Code, createResp.Body.String())
	}
	var created premiumPoolEntry
	if err := json.Unmarshal(createResp.Body.Bytes(), &created); err != nil {
		t.Fatalf("unmarshal create response: %v", err)
	}
	if created.Scope != "global" || created.Status != "active" || created.RollbackToken == "" {
		t.Fatalf("premium entry missing commercial governance fields: %+v", created)
	}

	listReq := httptest.NewRequest(http.MethodGet, "/control-plane/product/recommendation/premium-pool?activeOnly=true", nil)
	listResp := httptest.NewRecorder()
	server.ServeHTTP(listResp, listReq)
	if listResp.Code != http.StatusOK {
		t.Fatalf("list premium pool status=%d body=%s", listResp.Code, listResp.Body.String())
	}
	var listPayload struct {
		Items []premiumPoolEntry `json:"items"`
	}
	if err := json.Unmarshal(listResp.Body.Bytes(), &listPayload); err != nil {
		t.Fatalf("unmarshal list response: %v", err)
	}
	if len(listPayload.Items) != 1 || listPayload.Items[0].ContentID != "post_premium_1" {
		t.Fatalf("expected active premium entry, got %+v", listPayload.Items)
	}

	rollbackReq := httptest.NewRequest(http.MethodPost, "/control-plane/product/recommendation/premium-pool/post_premium_1:rollback", nil)
	rollbackResp := httptest.NewRecorder()
	server.ServeHTTP(rollbackResp, rollbackReq)
	if rollbackResp.Code != http.StatusOK {
		t.Fatalf("rollback premium pool status=%d body=%s", rollbackResp.Code, rollbackResp.Body.String())
	}
	var rolledBack premiumPoolEntry
	if err := json.Unmarshal(rollbackResp.Body.Bytes(), &rolledBack); err != nil {
		t.Fatalf("unmarshal rollback response: %v", err)
	}
	if rolledBack.Status != "rolled_back" {
		t.Fatalf("rollback status=%q", rolledBack.Status)
	}

	createBody2 := `{"contentId":"post_premium_2","scope":"global","qualityScore":0.91,"qualityAdmission":"approved","auditId":"audit_premium_2","expiresAt":"` + expiresAt + `"}`
	createReq2 := httptest.NewRequest(http.MethodPost, "/control-plane/product/recommendation/premium-pool", bytes.NewBufferString(createBody2))
	createResp2 := httptest.NewRecorder()
	server.ServeHTTP(createResp2, createReq2)
	if createResp2.Code != http.StatusOK {
		t.Fatalf("create second premium pool status=%d body=%s", createResp2.Code, createResp2.Body.String())
	}
	// takedown 是双签动作：单 principal 只登记审批并保持 pending，
	// 第二个不同 principal 才真正弹出条目。
	firstTakedownReq := httptest.NewRequest(http.MethodPost, "/control-plane/product/recommendation/premium-pool/post_premium_2:takedown", nil)
	firstTakedownReq = requestAsTestPrincipal(firstTakedownReq, "takedown-approver-1")
	firstTakedownReq.Header.Set("Idempotency-Key", "premium-pool-2-takedown")
	firstTakedownResp := httptest.NewRecorder()
	server.ServeHTTP(firstTakedownResp, firstTakedownReq)
	if firstTakedownResp.Code != http.StatusOK {
		t.Fatalf("first takedown status=%d body=%s", firstTakedownResp.Code, firstTakedownResp.Body.String())
	}
	var pendingTakedown struct {
		Pending bool `json:"pending"`
	}
	if err := json.Unmarshal(firstTakedownResp.Body.Bytes(), &pendingTakedown); err != nil {
		t.Fatalf("unmarshal pending takedown: %v", err)
	}
	if !pendingTakedown.Pending {
		t.Fatalf("single principal takedown must be pending, got %s", firstTakedownResp.Body.String())
	}
	takedownReq := httptest.NewRequest(http.MethodPost, "/control-plane/product/recommendation/premium-pool/post_premium_2:takedown", nil)
	takedownReq = requestAsTestPrincipal(takedownReq, "takedown-approver-2")
	takedownReq.Header.Set("Idempotency-Key", "premium-pool-2-takedown")
	takedownResp := httptest.NewRecorder()
	server.ServeHTTP(takedownResp, takedownReq)
	if takedownResp.Code != http.StatusOK {
		t.Fatalf("takedown premium pool status=%d body=%s", takedownResp.Code, takedownResp.Body.String())
	}
	var ejectedPayload struct {
		Entry   premiumPoolEntry             `json:"entry"`
		Pending bool                         `json:"pending"`
		Receipt controlplane.MutationReceipt `json:"receipt"`
	}
	if err := json.Unmarshal(takedownResp.Body.Bytes(), &ejectedPayload); err != nil {
		t.Fatalf("unmarshal takedown response: %v", err)
	}
	if ejectedPayload.Pending || !ejectedPayload.Entry.TakedownEjected ||
		ejectedPayload.Entry.Status != "takedown_ejected" ||
		ejectedPayload.Receipt.IdempotencyKey != "premium-pool-2-takedown" {
		t.Fatalf("takedown must atomically eject premium entry, got %+v", ejectedPayload)
	}

	auditReq := httptest.NewRequest(http.MethodGet, "/control-plane/product/audits", nil)
	auditResp := httptest.NewRecorder()
	server.ServeHTTP(auditResp, auditReq)
	if auditResp.Code != http.StatusOK {
		t.Fatalf("audit status=%d body=%s", auditResp.Code, auditResp.Body.String())
	}
	var auditPayload struct {
		Items []map[string]any `json:"items"`
	}
	if err := json.Unmarshal(auditResp.Body.Bytes(), &auditPayload); err != nil {
		t.Fatalf("unmarshal audits: %v", err)
	}
	if len(auditPayload.Items) < 4 {
		t.Fatalf("premium pool must audit create/rollback/takedown, got %+v", auditPayload.Items)
	}
	if got, want := premiumPoolEventTypes(publisher.events), []string{
		premiumPoolEntryUpsertedEvent,
		premiumPoolEntryRolledBackEvent,
		premiumPoolEntryUpsertedEvent,
	}; !equalStrings(got, want) {
		t.Fatalf("premium pool events=%v want %v", got, want)
	}
	if sourceTaskID, _ := publisher.events[0].Payload["sourceTaskId"].(string); sourceTaskID != "task_1" {
		t.Fatalf("premium pool event must keep sourceTaskId for data-engineering attribution, payload=%+v", publisher.events[0].Payload)
	}
}

func premiumPoolEventTypes(events []messaging.DomainEvent) []string {
	out := make([]string, 0, len(events))
	for _, event := range events {
		out = append(out, event.Type)
	}
	return out
}

func equalStrings(a, b []string) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}

func TestL1L4MetricsEndpoint(t *testing.T) {
	service := newTestProductService(t)
	service.prometheus = testPrometheusQuery{}
	if err := service.seed(); err != nil {
		t.Fatalf("seed service: %v", err)
	}
	server := newTestServerMux(service)

	occurredAt := time.Now().UTC().Add(-2 * time.Hour)
	performance := telemetryEvent("performance_sample", "event", occurredAt)
	performance["operationId"] = "feed_first_content_ready"
	performance["durationMs"] = 1300
	errorEvent := telemetryEvent("runtime_exception", "error", occurredAt.Add(time.Second))
	errorEvent["errorCode"] = "OPS.SYSTEM.test_failure"
	recordReq := newTelemetryBatchRequest(t, []map[string]any{performance, errorEvent})
	recordResp := httptest.NewRecorder()
	server.ServeHTTP(recordResp, recordReq)
	if recordResp.Code != http.StatusOK {
		t.Fatalf("record metrics events status=%d body=%s", recordResp.Code, recordResp.Body.String())
	}

	req := httptest.NewRequest(http.MethodGet, "/control-plane/product/metrics/l1l4?env=beta&level=L3", nil)
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
	if payload.Alerts[0].RepairEntry == "" || payload.Alerts[0].AlertID == "" || payload.Alerts[0].Owner == "" {
		t.Fatalf("expected alert repair semantics, got %+v", payload.Alerts[0])
	}
}

func TestProductTriageSummaryEndpoint(t *testing.T) {
	service := newTestProductService(t)
	if err := service.seed(); err != nil {
		t.Fatalf("seed service: %v", err)
	}
	server := newTestServerMux(service)

	occurredAt := time.Now().UTC().Add(-5 * time.Minute)
	pageOpen := telemetryEvent("page_open", "event", occurredAt)
	pageReturn := telemetryEvent("page_return", "event", occurredAt.Add(time.Second))
	pageReturn["durationMs"] = 1300
	recordReq := newTelemetryBatchRequest(t, []map[string]any{pageOpen, pageReturn})
	recordResp := httptest.NewRecorder()
	server.ServeHTTP(recordResp, recordReq)
	if recordResp.Code != http.StatusOK {
		t.Fatalf("record events status=%d body=%s", recordResp.Code, recordResp.Body.String())
	}

	req := httptest.NewRequest(http.MethodGet, "/control-plane/product/triage/summary?pageName=home", nil)
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
			RowKey   string `json:"rowKey"`
			PageName string `json:"pageName"`
		} `json:"recentEvents"`
		BacklogCandidates []struct {
			ID          string `json:"id"`
			Category    string `json:"category"`
			Title       string `json:"title"`
			NextAction  string `json:"nextAction"`
			RepairEntry string `json:"repairEntry"`
			AlertID     string `json:"alertId"`
			AuditRoute  string `json:"auditRoute"`
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
	if len(payload.RecentEvents) == 0 {
		t.Fatalf("expected recent events, got %+v", payload)
	}
	if payload.RecentEvents[0].RowKey == "" {
		t.Fatalf("recent events must use temporary row keys, got %+v", payload.RecentEvents)
	}
	if len(payload.BacklogCandidates) > 0 && (payload.BacklogCandidates[0].ID == "" || payload.BacklogCandidates[0].NextAction == "" || payload.BacklogCandidates[0].RepairEntry == "" || payload.BacklogCandidates[0].AlertID == "" || payload.BacklogCandidates[0].AuditRoute == "") {
		t.Fatalf("expected backlog candidate details, got %+v", payload.BacklogCandidates[0])
	}
}
